# Stock Performance Tracker – Deployment Guide for Render

## Overview
This app is a **FastAPI backend + React frontend SPA** that:
- Tracks stock performance vs. purchase price (Jan 2, 2026)
- Updates prices hourly from Yahoo Finance
- Displays a Bloomberg-terminal-style UI with industry + stock breakdowns

## Render Deployment Steps

### 1. Connect Your Repository
- Go to [render.com](https://render.com) and create a **New Web Service**
- Connect your GitHub repo
- Select your repository and branch

### 2. Environment & Build Settings

#### Build Command
```bash
pip install -r requirements.txt \
   && npm --prefix frontend ci --include=dev \
   && npm --prefix frontend run build
```

#### Start Command
```bash
chmod +x render-start.sh && ./render-start.sh
```

Or directly (without the script):
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

#### Python Version
- Use **Python 3.12+** (Render defaults to the latest; 3.13 is OK for this repo)

### 3. Runtime & Dependencies
- Render will run exactly what you put in **Build Command** and **Start Command**.
- The Build Command above installs Python deps + Node deps (including dev deps for TypeScript) and builds the SPA.

### 4. Environment Variables
If needed, add to Render dashboard:
- `DATABASE_URL` (optional; defaults to `data/app.db` on local filesystem)
- `PORT` (Render sets this automatically)

### 5. Disk Persistence
Render ephemeral disks reset on redeploy. For persistent SQLite DB:
- **Option A (Recommended):** Integrate a PostgreSQL database and set `DATABASE_URL`
- **Option B:** Mount a persistent disk in Render dashboard for `/data/`

### 6. First Deploy
1. Render will:
   - Install Python deps from `requirements.txt`
   - Install Node deps from `frontend/package.json`
   - Run **Build Command** → builds React to `frontend/dist/`
   - Run **Start Command** → starts uvicorn on `0.0.0.0:$PORT`

2. Once live, your app will be at `https://<your-service>.onrender.com`

### 7. Accessing the App
- **Frontend (React Terminal UI):** `https://<your-service>.onrender.com/`
- **Backend API:** `https://<your-service>.onrender.com/api/summary`
- **Old Jinja Template Dashboard:** `https://<your-service>.onrender.com/legacy/`

## Notes

### Rate Limiting
Yahoo Finance may rate-limit requests from the same IP. Use:
- `/api/actions/update` (latest prices) – best-effort, may skip
- `/api/actions/backfill` (daily history) – slower, more reliable

### Database Persistence
On Render's ephemeral filesystem, the SQLite DB is lost on redeploy. Consider:
- Migrating to PostgreSQL (Render offers managed databases)
- Or add a persistent disk mount in Render settings

### Hourly Scheduler
The app starts a background scheduler to update prices hourly. This runs while uvicorn is up; Render's free tier may sleep the service if idle, pausing the scheduler.

## Troubleshooting

**503 Service Unavailable / Build Failed:**
- Check Render logs: "Events" tab shows build & runtime output
- Verify `requirements.txt` has all Python deps
- Verify `frontend/package.json` has all Node deps

**Frontend shows "Cannot GET /":**
- Ensure the **Build Command** successfully builds the frontend
- Check that `frontend/dist/index.html` exists after the build step

**API requests fail (CORS / 404):**
- The SPA fallback middleware should route `/api/*` to FastAPI
- If stuck, check app.main.py middleware order

**Database empty / old data:**
- SQLite is ephemeral on Render; use PostgreSQL for persistence
- On deploy, the app re-seeds default stocks

## Next Steps
1. Add secrets (if any) in Render **Environment Variables**
2. Set up a PostgreSQL database in Render for persistent storage
3. Monitor logs after first deploy to catch any issues
4. (Optional) Enable auto-redeploy on push to GitHub
