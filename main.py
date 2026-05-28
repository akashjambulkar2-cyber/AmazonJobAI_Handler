"""
Amazon Canada — Ontario Warehouse Jobs Dashboard
==================================================
Fetches warehouse, associate, and flextime jobs from hiring.amazon.ca
filtered to Ontario, Canada using the amazon.jobs JSON API.

RENDER DEPLOYMENT:
  Build Command:  pip install -r requirements.txt
  Start Command:  uvicorn main:app --host 0.0.0.0 --port $PORT
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

_cache: dict = {}          # keyed by keyword so each tab caches separately
CACHE_TTL_SECONDS = 600    # 10 minutes

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-CA,en;q=0.9",
    "Referer": "https://www.amazon.jobs/en/search",
    "X-Requested-With": "XMLHttpRequest",
}

# Job categories shown in the dashboard sidebar
JOB_KEYWORDS = {
    "warehouse":           "Warehouse Associate Ontario",
    "fulfillment":         "Fulfillment Centre Associate Ontario",
    "sortation":           "Sortation Centre Associate Ontario",
    "delivery":            "Delivery Station Associate Ontario",
    "flex":                "Flex Time Associate Ontario",
    "part-time":           "Part Time Warehouse Ontario",
    "night-shift":         "Night Shift Warehouse Ontario",
}


def fetch_jobs(keyword: str) -> list[dict]:
    """
    Calls the amazon.jobs JSON API for hourly warehouse roles in Ontario, Canada.
    Returns a cleaned list of job dicts.
    """
    search_term = JOB_KEYWORDS.get(keyword, f"{keyword} Ontario Canada")

    try:
        resp = requests.get(
            "https://www.amazon.jobs/en/search.json",
            headers=HEADERS,
            params={
                "base_query":   search_term,
                "loc_query":    "Ontario, Canada",
                "result_limit": 25,
                "sort":         "recent",
            },
            timeout=15,
        )
        resp.raise_for_status()
        raw_jobs = resp.json().get("jobs", [])
    except Exception as e:
        raise RuntimeError(f"Could not fetch jobs from Amazon: {e}")

    return [_clean(j) for j in raw_jobs]


def _clean(job: dict) -> dict:
    """Normalise a raw amazon.jobs object into a consistent shape."""
    raw_desc = job.get("description_short") or job.get("description") or ""
    clean_desc = re.sub(r"<[^>]+>", "", raw_desc.replace("<br>", " ")).strip()
    if len(clean_desc) > 250:
        clean_desc = clean_desc[:250].rstrip() + "…"

    job_path = job.get("job_path", "")
    apply_url = (
        f"https://www.amazon.jobs{job_path}"
        if job_path
        else "https://hiring.amazon.ca/app#/jobSearch"
    )

    team_raw = job.get("team") or {}
    team = team_raw.get("label") if isinstance(team_raw, dict) else str(team_raw or "Hourly")

    schedule = job.get("job_schedule_type") or "Full-time"

    return {
        "id":          str(job.get("id_icims", "")),
        "title":       job.get("title") or "Warehouse Associate",
        "team":        team or "Hourly",
        "location":    job.get("location") or "Ontario, Canada",
        "type":        schedule,
        "posted":      job.get("posted_date") or "Recently",
        "description": clean_desc or "Visit Amazon Jobs for full details.",
        "apply_url":   apply_url,
        "pay":         "",
    }


# ── Serve dashboard ────────────────────────────────────────────────────────

DASHBOARD_HTML = open("dashboard.html").read()


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    return DASHBOARD_HTML


@app.get("/jobs")
def get_jobs(
    keyword:  str            = Query(default="warehouse"),
    job_type: Optional[str]  = Query(default=None),
    refresh:  bool           = Query(default=False),
):
    """
    Returns Ontario warehouse jobs from Amazon.
    keyword options: warehouse | fulfillment | sortation | delivery | flex | part-time | night-shift
    """
    global _cache
    now          = time.time()
    cached_entry = _cache.get(keyword)
    cache_valid  = cached_entry and (now - cached_entry["ts"]) < CACHE_TTL_SECONDS

    if not refresh and cache_valid:
        jobs   = cached_entry["jobs"]
        cached = True
    else:
        jobs   = fetch_jobs(keyword)
        _cache[keyword] = {"jobs": jobs, "ts": now}
        cached = False

    if job_type:
        jobs = [j for j in jobs if job_type.lower() in j["type"].lower()]

    return {
        "success":  True,
        "count":    len(jobs),
        "source":   "amazon.jobs → Ontario, Canada",
        "keyword":  keyword,
        "cached":   cached,
        "jobs":     jobs,
    }


@app.get("/categories")
def get_categories():
    return {"keywords": list(JOB_KEYWORDS.keys())}
