from __future__ import annotations

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

API = "https://www.linkedin.com/voyager/api"

COLLECTIONS = {
    "positions": "profilePositions",
    "educations": "profileEducations",
    "skills": "profileSkills",
    "certifications": "profileCertifications",
    "projects": "profileProjects",
    "courses": "profileCourses",
    "honors": "profileHonors",
    "languages": "profileLanguages",
    "volunteer": "profileVolunteerExperiences",
    "publications": "profilePublications",
}

VANITY_RE = re.compile(r"linkedin\.com/in/([^/?#]+)")


class ProfileNotFound(Exception):
    pass


def vanityFromUrl(url: str) -> str:
    match = VANITY_RE.search(url)
    if not match:
        raise ValueError(f"not a LinkedIn profile URL: {url}")
    return match.group(1)


class Voyager:
    def __init__(self, liAt: str, jsessionId: str, timeout: float = 20.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.cookies.set("li_at", liAt, domain=".linkedin.com")
        self.session.cookies.set("JSESSIONID", f'"{jsessionId}"', domain=".linkedin.com")
        self.session.headers.update(
            {
                # Voyager authorises writes and reads off the JSESSIONID value.
                "csrf-token": jsessionId,
                "x-restli-protocol-version": "2.0.0",
                # Asks Voyager for the flat `included` form rather than a nested graph.
                "accept": "application/vnd.linkedin.normalized+json+2.1",
                "user-agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/153.0.0.0 Safari/537.36"
                ),
                "accept-language": "en-US,en;q=0.9",
            }
        )

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        response = self.session.get(
            f"{API}/{path}", params=params, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def resolveProfile(self, vanity: str) -> dict:
        payload = self.get(
            "identity/dash/profiles",
            {"q": "memberIdentity", "memberIdentity": vanity},
        )
        profiles = denormalize(payload)["elements"]
        if not profiles:
            raise ProfileNotFound(vanity)
        return profiles[0]

    def collection(self, resource: str, profileUrn: str, count: int = 100) -> list:
        params = {"q": "viewee", "profileUrn": profileUrn, "count": count}
        payload = self.get(f"identity/dash/{resource}", params)
        return denormalize(payload)["elements"]


def denormalize(payload: dict) -> dict:
    urnIndex = {
        obj["entityUrn"]: obj
        for obj in payload.get("included", [])
        if isinstance(obj, dict) and "entityUrn" in obj
    }

    def resolve(node: Any, seen: frozenset[str]) -> Any:
        if isinstance(node, list):
            return [resolve(item, seen) for item in node]
        if not isinstance(node, dict):
            return node

        resolved: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$type":
                continue
            if key.startswith("*"):
                # Rest.li/Deco marks reference fields with a `*` prefix; the
                # value is a URN pointing into `included`, not inline data.
                fieldName = key[1:]
                urns = value if isinstance(value, list) else [value]
                hydrated = []
                for urn in urns:
                    referenced = urnIndex.get(urn)
                    # A cycle guard is required: Voyager graphs self-reference.
                    if referenced is None or urn in seen:
                        hydrated.append(urn)
                    else:
                        hydrated.append(resolve(referenced, seen | {urn}))
                resolved[fieldName] = (
                    hydrated if isinstance(value, list) else hydrated[0]
                )
            else:
                resolved[key] = resolve(value, seen)
        return resolved

    data = resolve(payload.get("data", {}), frozenset())
    if "elements" not in data:
        data["elements"] = []
    return data


def dateRange(rawRange: dict | None) -> dict | None:
    if not rawRange:
        return None

    def formatPart(endpoint: dict | None) -> str | None:
        if not endpoint:
            return None
        components = [endpoint.get("year"), endpoint.get("month"), endpoint.get("day")]
        return "-".join(
            f"{c:02d}" if i else str(c) for i, c in enumerate(components) if c
        )

    return {
        "start": formatPart(rawRange.get("start")),
        "end": formatPart(rawRange.get("end")),
    }


def pictureUrl(rawPicture: dict | None) -> str | None:
    try:
        vector = rawPicture["displayImageReference"]["vectorImage"]
        artifacts = vector["artifacts"]
        # Voyager exposes each image as several resolutions; take the highest.
        largest = max(artifacts, key=lambda a: a.get("width", 0))
        return vector["rootUrl"] + largest["fileIdentifyingUrlPathSegment"]
    except (KeyError, TypeError, ValueError):
        return None


def shape(profile: dict, collections: dict[str, list]) -> dict:
    return {
        "public_id": profile.get("publicIdentifier"),
        "first_name": profile.get("firstName"),
        "last_name": profile.get("lastName"),
        "headline": profile.get("headline"),
        "summary": profile.get("summary"),
        "location": (profile.get("geoLocation") or {}).get("geo")
        or profile.get("location"),
        "is_premium": profile.get("premium"),
        "is_influencer": profile.get("influencer"),
        "is_creator": profile.get("creator"),
        "profile_picture": pictureUrl(profile.get("profilePicture")),
        "background_picture": pictureUrl(profile.get("backgroundPicture")),
        "experience": [
            {
                "title": position.get("title"),
                "company": position.get("companyName"),
                "location": position.get("locationName"),
                "description": position.get("description"),
                "dates": dateRange(position.get("dateRange")),
            }
            for position in collections["positions"]
        ],
        "education": [
            {
                "school": education.get("schoolName")
                or (education.get("multiLocaleSchoolName") or {}).get("en_US"),
                "degree": education.get("degreeName"),
                "field_of_study": education.get("fieldOfStudy"),
                "grade": (education.get("multiLocaleGrade") or {}).get("en_US"),
                "description": education.get("description"),
                "dates": dateRange(education.get("dateRange")),
            }
            for education in collections["educations"]
        ],
        "skills": [
            skill.get("name") for skill in collections["skills"] if skill.get("name")
        ],
        "certifications": [
            {
                "name": certification.get("name"),
                "authority": certification.get("authority"),
                "url": certification.get("url"),
                "license_number": certification.get("licenseNumber"),
                "dates": dateRange(certification.get("dateRange")),
            }
            for certification in collections["certifications"]
        ],
        "projects": [
            {
                "title": project.get("title"),
                "description": project.get("description"),
                "url": project.get("url"),
                "dates": dateRange(project.get("dateRange")),
            }
            for project in collections["projects"]
        ],
        "honors": [
            {"title": honor.get("title"), "issuer": honor.get("issuer")}
            for honor in collections["honors"]
        ],
        "languages": [
            {"name": language.get("name"), "proficiency": language.get("proficiency")}
            for language in collections["languages"]
        ],
        "publications": [
            {"name": publication.get("name"), "publisher": publication.get("publisher")}
            for publication in collections["publications"]
        ],
        "courses": [
            course.get("name")
            for course in collections["courses"]
            if course.get("name")
        ],
        "volunteer": [
            {
                "role": volunteerExperience.get("role"),
                "organization": volunteerExperience.get("companyName"),
                "cause": volunteerExperience.get("cause"),
                "dates": dateRange(volunteerExperience.get("dateRange")),
            }
            for volunteerExperience in collections["volunteer"]
        ],
    }


def fetchProfile(client: Voyager, url: str) -> dict:
    profile = client.resolveProfile(vanityFromUrl(url))
    profileUrn = profile["entityUrn"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            name: pool.submit(client.collection, resource, profileUrn)
            for name, resource in COLLECTIONS.items()
        }
        collections = {name: future.result() for name, future in futures.items()}

    return shape(profile, collections)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python voyager.py <linkedin profile url>", file=sys.stderr)
        return 2

    liAt = os.environ.get("LI_AT")
    jsessionId = os.environ.get("LI_JSESSIONID")
    if not liAt or not jsessionId:
        print("set LI_AT and LI_JSESSIONID", file=sys.stderr)
        return 2

    client = Voyager(liAt, jsessionId)
    started = time.monotonic()
    result = fetchProfile(client, sys.argv[1])
    elapsed = time.monotonic() - started

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nfetched in {elapsed:.2f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
