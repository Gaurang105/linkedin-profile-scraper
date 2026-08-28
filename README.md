# LinkedIn Profile Scraper

A small API that fetches a public LinkedIn profile (experience, education, skills, etc.) and returns it as clean JSON.

It works by calling LinkedIn's own internal "Voyager" API — the same API LinkedIn's website uses — using your logged-in session cookies. This is not the official LinkedIn API.

## How it works (approach)

1. You give it a LinkedIn profile URL, e.g. `https://www.linkedin.com/in/someone`.
2. It pulls out the "vanity name" (`someone`) from the URL.
3. It uses your `li_at` and `JSESSIONID` cookies (from a real logged-in browser session) to ask LinkedIn's Voyager API to resolve that name to a profile.
4. It then fetches each section of the profile (positions, education, skills, certifications, projects, courses, honors, languages, volunteer work, publications) in parallel.
5. LinkedIn's raw response is a "normalized" graph — most fields are just references (URNs) pointing to objects elsewhere in the response. The code resolves ("denormalizes") these references back into a normal nested JSON structure.
6. Finally, it reshapes everything into one clean, predictable JSON object and returns it.

This same logic can be run two ways:
- As a one-off command line script (`voyager.py`)
- As a small web API (`app.py`), so any app can call it over HTTP

## Setup

**1. Install Python dependencies**

```bash
pip install -r requirements.txt
```

**2. Get your LinkedIn session cookies**

You need to be logged into LinkedIn in a browser, then grab two cookies from DevTools (Application/Storage → Cookies → `linkedin.com`):

- `li_at` — your session token
- `JSESSIONID` — looks like `ajax:1234567890123456789` (copy it without the surrounding quotes)

**3. Create your `.env` file**

Copy the example file and fill in the two values:

```bash
cp .env.example .env
```

```
LI_AT=your_li_at_value
LI_JSESSIONID=ajax:1234567890123456789
```

**4. Run it**

As a command line tool:

```bash
python voyager.py "https://www.linkedin.com/in/someone"
```

As a web API:

```bash
uvicorn app:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## API documentation

### `GET /`

Returns a simple welcome message so the base URL doesn't look broken.

### `GET /profiles?url=<linkedin-profile-url>`

Fetches a LinkedIn profile and returns it as JSON.

**Query parameter**

| Name | Required | Description |
|------|----------|--------------|
| `url` | yes | Full LinkedIn profile URL, e.g. `https://www.linkedin.com/in/someone` |

**Example request**

```
GET /profiles?url=https://www.linkedin.com/in/someone
```

**Example response (shortened)**

```json
{
  "public_id": "someone",
  "first_name": "Jane",
  "last_name": "Doe",
  "headline": "Software Engineer",
  "summary": "...",
  "location": "San Francisco, California",
  "is_premium": false,
  "is_influencer": false,
  "is_creator": false,
  "profile_picture": "https://...",
  "background_picture": "https://...",
  "experience": [
    { "title": "Software Engineer", "company": "Acme Inc", "location": "Remote", "description": "...", "dates": { "start": "2022-01", "end": null } }
  ],
  "education": [
    { "school": "Some University", "degree": "B.S.", "field_of_study": "Computer Science", "grade": null, "description": null, "dates": { "start": "2018", "end": "2022" } }
  ],
  "skills": ["Python", "FastAPI"],
  "certifications": [],
  "projects": [],
  "honors": [],
  "languages": [],
  "publications": [],
  "courses": [],
  "volunteer": []
}
```

**Error responses**

| Status | When |
|--------|------|
| 400 | The `url` isn't a valid LinkedIn profile URL |
| 404 | Profile could not be found |
| 502 | LinkedIn's API request failed (e.g. cookies expired, rate limited, blocked) |

## Known limitations

- **Depends on personal login cookies, not an official API.** LinkedIn doesn't offer a public API for this. If LinkedIn changes its internal Voyager API, or your cookies expire/get invalidated, this will break.
- **Cookies expire.** You'll need to refresh `LI_AT` and `LI_JSESSIONID` from your browser periodically (e.g. when requests start failing).
- **Risk of account restrictions.** Because this uses your real logged-in session to scrape, LinkedIn may flag or restrict the account if used too often or too aggressively. Use responsibly and avoid scraping at high volume.
- **Single account, single session.** There's no support for rotating cookies/accounts or handling multiple concurrent users' sessions.
- **Only handles public-style profile data.** It captures the common sections (experience, education, skills, etc.) but not every possible LinkedIn profile section, and some fields may come back empty if LinkedIn's response shape changes.
- **No caching or rate limiting built in.** Every request hits LinkedIn live; repeated requests for the same profile will re-fetch everything each time.
- **No retries on failure.** If a request to LinkedIn fails (timeout, rate limit, etc.), it simply returns an error rather than retrying.
