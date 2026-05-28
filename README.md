# Amazon Jobs Dashboard — Backend API

A lightweight Python API that fetches Data Warehouse job listings
from Amazon Jobs and serves them to your dashboard.

---

## Files

| File | What it does |
|---|---|
| `main.py` | The API server (all the logic lives here) |
| `requirements.txt` | Python libraries this project needs |
| `README.md` | This guide |

---

## Step-by-Step: Deploy to Render.com (Free)

### Step 1 — Create a GitHub repository

1. Go to https://github.com and sign in (or create a free account)
2. Click the **+** button (top right) → **New repository**
3. Name it: `amazon-jobs-api`
4. Set it to **Public**
5. Click **Create repository**
6. On the next screen, click **uploading an existing file**
7. Upload both `main.py` and `requirements.txt`
8. Click **Commit changes**

---

### Step 2 — Deploy on Render.com

1. Go to https://render.com and sign in with your GitHub account
2. Click **New +** → **Web Service**
3. Select your `amazon-jobs-api` repository
4. Fill in the form:
   - **Name**: `amazon-jobs-api` (or anything you like)
   - **Region**: Choose the one closest to you
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Choose the **Free** plan
6. Click **Create Web Service**
7. Wait about 2–3 minutes for deployment
8. You'll see a URL like: `https://amazon-jobs-api.onrender.com`

**That's your backend URL — copy it!**

---

### Step 3 — Test your backend

Open your browser and visit:

```
https://YOUR-APP-NAME.onrender.com/
```

You should see:
```json
{"status": "ok", "message": "Amazon Jobs Dashboard API is running!"}
```

Then test the jobs endpoint:
```
https://YOUR-APP-NAME.onrender.com/jobs
```

You should see a list of Data Warehouse jobs in JSON format.

---

### Step 4 — Connect the Dashboard

Once you have your Render URL, go back to the dashboard Claude built
and paste your Render URL where it says `YOUR_BACKEND_URL`.

---

## API Endpoints

| Endpoint | What it does |
|---|---|
| `GET /` | Health check — confirms the server is running |
| `GET /jobs` | Returns Data Warehouse jobs |
| `GET /jobs?keyword=etl` | Search for ETL jobs |
| `GET /jobs?team=Data+Engineering` | Filter by team |
| `GET /jobs?refresh=true` | Force a fresh fetch (bypass cache) |
| `GET /categories` | Returns all filter options |

---

## Running Locally (Optional)

If you want to test on your own computer before deploying:

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open: http://localhost:8000

---

## Troubleshooting

**"No jobs found"** — Amazon Jobs may not have listings for Oriana yet.
Try changing `loc_query` to a nearby city or leave it blank to search globally.

**Server sleeps after 15 min on free tier** — Render's free plan spins down
inactive servers. The first request after a period of inactivity may take
15–20 seconds. This is normal.

**CORS error still showing** — Make sure you copied the full Render URL
(including `https://`) into the dashboard's backend URL field.
