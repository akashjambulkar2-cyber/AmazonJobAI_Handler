"""
Amazon Canada Warehouse Jobs — Backend + Frontend
===================================================
Calls hiring.amazon.ca's internal REST API directly using requests.
No headless browser needed — works on Render free tier.

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

_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 600  # 10 minutes

# Browser-like headers so Amazon doesn't block the request
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-CA,en;q=0.9",
    "Referer": "https://hiring.amazon.ca/",
    "Origin": "https://hiring.amazon.ca",
}

# hiring.amazon.ca is a React app that calls this internal API for job data
HVH_ENDPOINTS = [
    "https://hiring.amazon.ca/api/jobs",
    "https://hiring.amazon.ca/api/search",
]


def fetch_amazon_ca_jobs(keyword: str = "warehouse") -> list[dict]:
    """
    Calls hiring.amazon.ca's internal job search API and returns clean job list.
    Tries multiple known endpoint patterns.
    """
    params_variants = [
        {"locale": "en-CA", "keywords": keyword, "radius": "50mi", "sort": "RELEVANCE"},
        {"locale": "en-CA", "keyword": keyword, "country": "CA"},
        {"language": "en-CA", "keywords": keyword, "jobType": keyword},
    ]

    raw_jobs = []

    for endpoint in HVH_ENDPOINTS:
        for params in params_variants:
            try:
                resp = requests.get(endpoint, headers=HEADERS, params=params, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    found = (
                        data.get("jobs")
                        or data.get("jobResults")
                        or data.get("results")
                        or data.get("data", {}).get("jobs")
                        or (data if isinstance(data, list) else [])
                    )
                    if found:
                        raw_jobs = found
                        break
            except Exception:
                continue
        if raw_jobs:
            break

    # If direct API didn't work, fall back to amazon.jobs JSON API
    # filtered to warehouse/hourly roles in Canada
    if not raw_jobs:
        try:
            resp = requests.get(
                "https://www.amazon.jobs/en/search.json",
                headers=HEADERS,
                params={
                    "base_query": f"{keyword} canada hourly",
                    "loc_query": "Canada",
                    "result_limit": 25,
                    "sort": "recent",
                    "category[]": "hourly-jobs",
                },
                timeout=15,
            )
            if resp.status_code == 200:
                raw_jobs = resp.json().get("jobs", [])
        except Exception:
            pass

    return [clean_job(j) for j in raw_jobs]


def clean_job(job: dict) -> dict:
    """Normalise a raw job object into a consistent shape for the dashboard."""
    raw_desc = (
        job.get("jobDescription")
        or job.get("description_short")
        or job.get("description")
        or job.get("summary")
        or ""
    )
    clean_desc = re.sub(r"<[^>]+>", "", raw_desc.replace("<br>", " ")).strip()
    if len(clean_desc) > 220:
        clean_desc = clean_desc[:220].rstrip() + "…"

    # Location — hiring.amazon.ca and amazon.jobs store this differently
    loc_obj = job.get("location") or {}
    if isinstance(loc_obj, dict):
        city = loc_obj.get("city") or loc_obj.get("name") or ""
        province = loc_obj.get("state") or loc_obj.get("province") or ""
        location = f"{city}, {province}".strip(", ") or "Canada"
    else:
        location = str(loc_obj) or job.get("locationName") or job.get("location") or "Canada"

    # Pay rate
    pay = job.get("pay") or job.get("payRate") or job.get("basePay") or ""
    if isinstance(pay, dict):
        lo = pay.get("min") or pay.get("low") or ""
        hi = pay.get("max") or pay.get("high") or ""
        unit = pay.get("unit") or "/hr"
        pay = f"${lo}–${hi} {unit}".strip() if lo or hi else ""

    # Apply URL
    job_path = job.get("job_path") or job.get("applyUrl") or job.get("jobUrl") or ""
    if job_path.startswith("http"):
        apply_url = job_path
    elif job_path:
        apply_url = f"https://hiring.amazon.ca{job_path}"
    else:
        apply_url = "https://hiring.amazon.ca/app#/jobSearch"

    # Team / category
    team_raw = job.get("team") or job.get("jobType") or job.get("category") or "Warehouse"
    if isinstance(team_raw, dict):
        team = team_raw.get("label") or "Warehouse"
    else:
        team = str(team_raw)

    return {
        "id": str(job.get("id_icims") or job.get("jobId") or job.get("id") or ""),
        "title": job.get("title") or job.get("jobTitle") or "Warehouse Associate",
        "team": team,
        "location": location,
        "type": job.get("job_schedule_type") or job.get("scheduleType") or job.get("employmentType") or "Full-time",
        "posted": job.get("posted_date") or job.get("postedDate") or job.get("createdAt") or "Recently",
        "description": clean_desc or "Visit hiring.amazon.ca to see the full job description.",
        "apply_url": apply_url,
        "pay": str(pay),
    }


# ── Serve dashboard ────────────────────────────────────────────────────────

DASHBOARD_HTML = open("dashboard.html").read()


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    return DASHBOARD_HTML


@app.get("/jobs")
def get_jobs(
    keyword: str = Query(default="warehouse"),
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
        jobs = fetch_amazon_ca_jobs(keyword=keyword)
        _cache = {"data": jobs, "timestamp": now}

    if team:
        jobs = [j for j in jobs if team.lower() in j["team"].lower()]
    if job_type:
        jobs = [j for j in jobs if job_type.lower() in j["type"].lower()]

    return {
        "success": True,
        "count": len(jobs),
        "source": "hiring.amazon.ca",
        "keyword": keyword,
        "cached": not cache_expired,
        "jobs": jobs,
    }
