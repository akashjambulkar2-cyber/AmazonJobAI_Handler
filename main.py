"""
Amazon Jobs Dashboard - Backend API
====================================
This server fetches Data Warehouse job listings from Amazon Jobs
and serves them to your dashboard. It runs as a middleware so the
browser's CORS restriction is bypassed (the server fetches, not your browser).

HOW TO RUN LOCALLY:
  pip install -r requirements.txt
  uvicorn main:app --reload

HOW TO DEPLOY (Render.com):
  Follow the steps in README.md
"""

import time
import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

# ── App setup ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Amazon Jobs Dashboard API",
    description="Fetches Data Warehouse jobs from Amazon Jobs",
    version="1.0.0"
)

# Allow your dashboard (running in any browser) to call this API.
# "*" means all origins are allowed — fine for a personal project.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Simple in-memory cache ─────────────────────────────────────────────────
# Stores the last fetched jobs so we don't hammer Amazon Jobs on every request.
# The cache expires after 10 minutes (600 seconds).
_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 600  # 10 minutes


# ── Helper: fetch jobs from Amazon Jobs ────────────────────────────────────
def fetch_amazon_jobs(keyword: str, location: str, limit: int) -> list[dict]:
    """
    Calls the Amazon Jobs JSON endpoint and returns a clean list of jobs.

    Amazon Jobs has an unofficial JSON API at /en/search.json
    It accepts query parameters like:
      base_query  → job keyword (e.g. "data warehouse")
      loc_query   → city/region (e.g. "oriana")
      result_limit → how many jobs to return
    """
    url = "https://www.amazon.jobs/en/search.json"

    params = {
        "base_query": keyword,
        "loc_query": location,
        "result_limit": limit,
        "sort": "recent",        # show newest jobs first
    }

    headers = {
        # Pretend to be a normal browser so Amazon doesn't block us
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
    response.raise_for_status()  # raises an error if status code is 4xx/5xx

    raw_jobs = response.json().get("jobs", [])

    # Clean and reshape each job into a simple dictionary
    clean_jobs = []
    for job in raw_jobs:
        # Strip HTML tags from the description
        raw_desc = job.get("description_short") or job.get("description") or ""
        clean_desc = raw_desc.replace("<br>", " ").replace("</br>", " ")
        # Remove any remaining HTML tags simply
        import re
        clean_desc = re.sub(r"<[^>]+>", "", clean_desc).strip()
        # Limit description length for the card display
        if len(clean_desc) > 200:
            clean_desc = clean_desc[:200].rstrip() + "…"

        job_path = job.get("job_path", "")
        clean_jobs.append({
            "id": job.get("id_icims", ""),
            "title": job.get("title", "Unknown Title"),
            "team": job.get("team", {}).get("label", "Amazon") if isinstance(job.get("team"), dict) else job.get("team", "Amazon"),
            "location": job.get("location", location),
            "city": job.get("city", ""),
            "country": job.get("country_code", ""),
            "type": job.get("job_schedule_type", "Full-time"),
            "posted": job.get("posted_date", "Recently"),
            "description": clean_desc,
            "apply_url": f"https://www.amazon.jobs{job_path}" if job_path else "https://www.amazon.jobs/en/search",
            "category": job.get("category", {}).get("label", "") if isinstance(job.get("category"), dict) else "",
        })

    return clean_jobs


# ── API Routes ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Health check — visit this URL to confirm the server is running."""
    return {"status": "ok", "message": "Amazon Jobs Dashboard API is running!"}


@app.get("/jobs")
def get_jobs(
    keyword: str = Query(default="data warehouse", description="Job search keyword"),
    location: str = Query(default="oriana", description="City or region to search in"),
    limit: int = Query(default=20, ge=1, le=50, description="Max number of jobs to return"),
    team: Optional[str] = Query(default=None, description="Filter by team name"),
    job_type: Optional[str] = Query(default=None, description="Filter by job type (Full-time, Contract, etc.)"),
    refresh: bool = Query(default=False, description="Set to true to skip cache and re-fetch"),
):
    """
    Main endpoint — returns a list of Data Warehouse jobs from Amazon Jobs.

    Example calls:
      GET /jobs                          → default data warehouse jobs in Oriana
      GET /jobs?keyword=etl              → ETL jobs
      GET /jobs?team=Data+Engineering    → filter by team
      GET /jobs?refresh=true             → force a fresh fetch (skip cache)
    """
    global _cache

    cache_key = f"{keyword}_{location}_{limit}"
    now = time.time()
    cache_expired = (now - _cache["timestamp"]) > CACHE_TTL_SECONDS

    # Return cached result if still fresh (and refresh not forced)
    if not refresh and _cache["data"] and not cache_expired:
        jobs = _cache["data"]
    else:
        # Fetch fresh data from Amazon Jobs
        jobs = fetch_amazon_jobs(keyword, location, limit)
        # Store in cache
        _cache = {"data": jobs, "timestamp": now}

    # Apply optional filters
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


@app.get("/categories")
def get_categories():
    """
    Returns the predefined job categories for the dashboard filter dropdowns.
    These match common Data Warehouse / Analytics team names on Amazon Jobs.
    """
    return {
        "teams": [
            "Data Engineering",
            "Business Intelligence",
            "Analytics",
            "Cloud Infrastructure",
            "Machine Learning",
            "Software Development",
            "Operations",
        ],
        "types": ["Full-time", "Part-time", "Contract"],
        "keywords": [
            "data warehouse",
            "ETL",
            "business intelligence",
            "data engineer",
            "analytics engineer",
            "redshift",
            "dbt",
        ]
    }
