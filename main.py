"""
Amazon Warehouse Jobs Dashboard — Backend + Frontend
======================================================
Fetches hourly warehouse job listings from https://hiring.amazon.ca
using a headless browser (Playwright) since the site is JavaScript-powered.

RENDER DEPLOYMENT:
  Build Command:  pip install -r requirements.txt && playwright install chromium --with-deps
  Start Command:  uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import re
import time
import asyncio
import json
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional
from playwright.async_api import async_playwright

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 600  # 10 minutes


# ── Scraper ────────────────────────────────────────────────────────────────

async def scrape_amazon_ca_jobs(keyword: str = "warehouse") -> list[dict]:
    """
    Opens hiring.amazon.ca in a headless browser, waits for jobs to load,
    captures the API response, and returns the job list.
    """
    jobs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            locale="en-CA",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        api_jobs = []

        # Intercept the network call that hiring.amazon.ca makes for jobs
        async def handle_response(response):
            url = response.url
            if "api/jobs" in url or "jobSearch" in url.lower() or "search" in url and "amazon" in url:
                try:
                    body = await response.json()
                    # Amazon HVH API returns jobs in different shapes — try common keys
                    found = (
                        body.get("jobs")
                        or body.get("jobResults")
                        or body.get("data", {}).get("jobs")
                        or body.get("results")
                        or []
                    )
                    if found:
                        api_jobs.extend(found)
                except Exception:
                    pass

        page = await context.new_page()
        page.on("response", handle_response)

        # Navigate to the job search page with warehouse keyword
        search_url = f"https://hiring.amazon.ca/app#/jobSearch?keywords={keyword}&locale=en-CA"
        await page.goto(search_url, wait_until="networkidle", timeout=30000)

        # Wait a moment for any lazy-loaded content
        await asyncio.sleep(3)

        # If we got data from the API intercept, use that
        if api_jobs:
            for job in api_jobs:
                jobs.append(clean_job(job))
        else:
            # Fallback: parse the DOM directly
            job_cards = await page.query_selector_all("[data-test='job-card'], .job-card, [class*='jobCard'], [class*='job-tile']")
            for card in job_cards:
                title = await card.inner_text()
                jobs.append({
                    "id": "",
                    "title": title.strip()[:80] if title else "Warehouse Associate",
                    "team": "Warehouse",
                    "location": "Canada",
                    "type": "Full-time",
                    "posted": "Recently",
                    "description": "Visit hiring.amazon.ca for full details.",
                    "apply_url": "https://hiring.amazon.ca/app#/jobSearch",
                    "pay": "",
                })

        await browser.close()

    return jobs


def clean_job(job: dict) -> dict:
    """Normalises a raw job object from hiring.amazon.ca into our standard shape."""
    raw_desc = job.get("jobDescription") or job.get("description") or job.get("summary") or ""
    clean_desc = re.sub(r"<[^>]+>", "", raw_desc.replace("<br>", " ")).strip()
    if len(clean_desc) > 220:
        clean_desc = clean_desc[:220].rstrip() + "…"

    job_id = job.get("jobId") or job.get("id") or job.get("requisitionId") or ""
    apply_path = job.get("applyUrl") or job.get("jobUrl") or ""
    apply_url = (
        apply_path if apply_path.startswith("http")
        else f"https://hiring.amazon.ca/app#/jobSearch"
    )

    location_obj = job.get("location") or {}
    if isinstance(location_obj, dict):
        city = location_obj.get("city") or location_obj.get("name") or ""
        province = location_obj.get("state") or location_obj.get("province") or ""
        location = f"{city}, {province}".strip(", ") if city or province else job.get("locationName", "Canada")
    else:
        location = str(location_obj) or job.get("locationName", "Canada")

    pay = job.get("pay") or job.get("payRate") or job.get("basePay") or ""
    if isinstance(pay, dict):
        pay = f"${pay.get('min', '')}–${pay.get('max', '')} {pay.get('unit', '/hr')}".strip()

    return {
        "id": str(job_id),
        "title": job.get("title") or job.get("jobTitle") or "Warehouse Associate",
        "team": job.get("jobType") or job.get("category") or "Warehouse",
        "location": location,
        "type": job.get("scheduleType") or job.get("employmentType") or "Full-time",
        "posted": job.get("postedDate") or job.get("createdAt") or "Recently",
        "description": clean_desc or "Visit hiring.amazon.ca to see the full job description.",
        "apply_url": apply_url,
        "pay": str(pay),
    }


# ── Dashboard HTML ─────────────────────────────────────────────────────────

DASHBOARD_HTML = open("dashboard.html").read()


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serves the full dashboard — just visit your Render URL."""
    return DASHBOARD_HTML


@app.get("/jobs")
async def get_jobs(
    keyword: str = Query(default="warehouse", description="Job keyword to search"),
    team: Optional[str] = Query(default=None),
    job_type: Optional[str] = Query(default=None),
    refresh: bool = Query(default=False),
):
    """
    Returns warehouse job listings from hiring.amazon.ca.

    Examples:
      GET /jobs                         → warehouse jobs (default)
      GET /jobs?keyword=fulfillment     → fulfillment centre jobs
      GET /jobs?refresh=true            → skip cache and re-fetch
    """
    global _cache
    now = time.time()
    cache_expired = (now - _cache["timestamp"]) > CACHE_TTL_SECONDS

    if not refresh and _cache["data"] and not cache_expired:
        jobs = _cache["data"]
    else:
        jobs = await scrape_amazon_ca_jobs(keyword=keyword)
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
