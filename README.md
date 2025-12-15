# CODM Reddit Sentiment Tracker (GitHub Pages + GitHub Actions)

This repo hosts a **static website** (GitHub Pages) that displays:
1) **Latest Reddit posts (by recency)** from a chosen subreddit
2) A **Word Cloud** of most-discussed / most-requested items
3) A **Sentiment score (1–5)** per post (1 = most negative, 5 = most positive)

✅ Your **OpenAI API key is NEVER exposed to the browser**.  
Instead, a **GitHub Action** runs on a schedule, fetches Reddit posts, calls OpenAI for scoring, writes JSON into `/data/`, and the site reads those JSON files.

---

## Quick Start (What you do after downloading this repo)

### 1) Create a new GitHub repo
- Create a new repo on GitHub (public is fine for Pages).

### 2) Upload the files
- Upload everything in this folder into the root of your repo (or `git clone` + copy).

### 3) Add your OpenAI API key as a GitHub Secret
- Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
- Name: `OPENAI_API_KEY`
- Value: your OpenAI key

(Important: API keys must be kept server-side, not in client code.)  
See OpenAI guidance: **API keys are secrets; don’t expose them in client-side code**.  
https://platform.openai.com/docs/api-reference/introduction

### 4) (Optional but recommended) Configure which subreddit to track
By default it tracks `CallOfDutyMobile`.

Change in:
- `.env.example` (for local runs)
- `.github/workflows/update_data.yml` (for Actions)

### 5) Enable GitHub Actions
- Repo → **Actions** → enable workflows if prompted.

### 6) Enable GitHub Pages
- Repo → **Settings** → **Pages**
- Source: **Deploy from a branch**
- Branch: `main`
- Folder: `/docs`
- Save.

### 7) Wait for the data to populate
- Go to **Actions** → open the latest run.
- When it finishes, the website will show posts and analytics.

---

## Local Development (optional)

### 1) Install Node deps (for local preview only)
```bash
cd docs
python -m http.server 8000
# then open http://localhost:8000
```

### 2) Run the data pipeline locally (optional)
```bash
cd scripts
cp ../.env.example .env
# edit .env to set OPENAI_API_KEY + SUBREDDIT
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python fetch_and_analyze.py
```

Outputs are written to `/data/*.json` and the site reads them.

---

## Files

- `docs/` → static site (GitHub Pages)
- `data/` → generated JSON used by the site
- `scripts/fetch_and_analyze.py` → pipeline (Reddit fetch + OpenAI scoring)
- `.github/workflows/update_data.yml` → scheduled GitHub Action

---

## Notes about Reddit fetching
This project uses **Reddit's public JSON endpoints** (e.g. `https://www.reddit.com/r/<subreddit>/new.json`) with a safe User-Agent and caching.
Unauthenticated access is rate-limited and can be throttled. If you hit limits, switch to OAuth (PRAW) later.

A discussion of unauthenticated JSON endpoint limits is here:
https://www.reddit.com/r/redditdev/comments/1mhefh9/is_clientside_fetching_of_reddits_public_json/

---

## License
MIT
