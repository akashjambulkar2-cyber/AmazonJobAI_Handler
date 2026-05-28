"""
Amazon Jobs Dashboard — Backend + Frontend
============================================
This file does two things:
  1. Serves the dashboard HTML when you visit the root URL /
  2. Provides the /jobs API endpoint that fetches from Amazon Jobs

HOW TO DEPLOY (Render.com):
  Replace your existing main.py on GitHub with this file.
  Render will auto-redeploy in ~2 minutes.

Then just visit: https://amazon.jobai-handler.onrender.com
"""

import re
import time
import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 600

DASHBOARD_HTML = open("dashboard.html").read()


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    return DASHBOARD_HTML


def fetch_amazon_jobs(keyword: str, location: str, limit: int) -> list[dict]:
    url = "https://www.amazon.jobs/en/search.json"
    params = {
        "base_query": keyword,
        "loc_query": location,
        "result_limit": limit,
        "sort": "recent",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.amazon.jobs/en/search",
        "X-Requested-With": "XMLHttpRequest",
    }
    response = requests.get(url, params=params, headers=headers, timeout=15)
    response.raise_for_status()
    raw_jobs = response.json().get("jobs", [])

    clean_jobs = []
    for job in raw_jobs:
        raw_desc = job.get("description_short") or job.get("description") or ""
        clean_desc = re.sub(r"<[^>]+>", "", raw_desc.replace("<br>", " ")).strip()
        if len(clean_desc) > 200:
            clean_desc = clean_desc[:200].rstrip() + "…"
        job_path = job.get("job_path", "")
        clean_jobs.append({
            "id": job.get("id_icims", ""),
            "title": job.get("title", "Unknown Title"),
            "team": job.get("team", {}).get("label", "Amazon") if isinstance(job.get("team"), dict) else job.get("team", "Amazon"),
            "location": job.get("location", location),
            "type": job.get("job_schedule_type", "Full-time"),
            "posted": job.get("posted_date", "Recently"),
            "description": clean_desc,
            "apply_url": f"https://www.amazon.jobs{job_path}" if job_path else "https://www.amazon.jobs/en/search",
        })
    return clean_jobs


@app.get("/jobs")
def get_jobs(
    keyword: str = Query(default="data warehouse"),
    location: str = Query(default="oriana"),
    limit: int = Query(default=20, ge=1, le=50),
    team: Optional[str] = Query(default=None),
    job_type: Optional[str] = Query(default=None),
    refresh: bool = Query(default=False),
):
    global _cache
    now = time.time()
    cache_expired = (now - _cache["timestamp"]) > CACHE_TTL_SECONDS

    if not refresh and _cache["data"] and not cache_expired:
        jobs = _cache["data"]
    else:
        jobs = fetch_amazon_jobs(keyword, location, limit)
        _cache = {"data": jobs, "timestamp": now}

    if team:
        jobs = [j for j in jobs if team.lower() in j["team"].lower()]
    if job_type:
        jobs = [j for j in jobs if job_type.lower() in j["type"].lower()]

    return {
        "success": True,
        "count": len(jobs),
        "keyword": keyword,
        "location": location,
        "cached": not cache_expired,
        "jobs": jobs,
    }
