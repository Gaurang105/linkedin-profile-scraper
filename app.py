from __future__ import annotations

import os

import requests
from fastapi import FastAPI, HTTPException

from voyager import ProfileNotFound, Voyager, fetchProfile

liAt = os.environ.get("LI_AT")
jsessionId = os.environ.get("LI_JSESSIONID")
if not liAt or not jsessionId:
    raise RuntimeError("set LI_AT and LI_JSESSIONID")

app = FastAPI()
client = Voyager(liAt, jsessionId)


@app.get("/profiles")
def readProfile(url: str) -> dict:
    try:
        return fetchProfile(client, url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ProfileNotFound as error:
        raise HTTPException(status_code=404, detail="profile not found") from error
    except requests.HTTPError as error:
        raise HTTPException(
            status_code=502, detail="linkedin request failed"
        ) from error
