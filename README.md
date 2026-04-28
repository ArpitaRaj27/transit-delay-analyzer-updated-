# 🚍 Transit Delay Analyzer

An ETL pipeline + interactive dashboard for analyzing public-transit reliability from GTFS feeds. KPIs, route scorecards, weekly trends, weather-vs-delay correlation, and per-route deep-dives — all in a single Streamlit app.

**Live demo:** _(replace with your Streamlit Cloud URL after deploying — see below)_

---

## What it does

- Ingests GTFS schedule data, simulates real-world arrival times, and joins hourly weather observations
- Computes per-route daily metrics: average delay, P95 delay, and a 0–1 reliability score
- Surfaces them in an interactive dashboard with date/route filters, CSV download, and route detail views

## Tech stack

- **Python** (pandas, SQLAlchemy, Streamlit)
- **PostgreSQL** for the local development pipeline (Dockerized)
- **SQLite** for the public deployed demo (zero-cost hosting)
- **GTFS** sample feed as data source

> **Why two databases?** The full pipeline runs on Postgres + Docker locally — that's the architecture I'd ship in production. For the public demo I bundle the same aggregated data into a SQLite file so the app deploys for free on Streamlit Community Cloud with no DB server to manage.

---

## Project structure

```
.
├── streamlit_app.py     # The dashboard (SQLite-backed)
├── build_db.py          # Rebuilds data/transit.db from the CSVs
├── requirements.txt
├── data/
│   ├── transit.db       # SQLite DB the app reads (committed)
│   ├── stops.csv
│   ├── schedule.csv
│   ├── actual.csv
│   ├── weather.csv
│   └── agg_daily.csv
└── README.md
```

---

## Run locally

```bash
git clone https://github.com/<you>/transit-delay-analyzer.git
cd transit-delay-analyzer
pip install -r requirements.txt
streamlit run streamlit_app.py
```

App opens at `http://localhost:8501`.

If you ever change the CSVs, regenerate the DB:

```bash
python build_db.py
```

---

## Deploy free on Streamlit Community Cloud

1. Push this repo to GitHub (public).
2. Go to [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub.
3. Click **"New app"** → pick the repo, branch `main`, main file path `streamlit_app.py`.
4. Click **Deploy**. ~2 minutes later you have a public URL like `https://<your-app>.streamlit.app`.

No secrets, no environment variables, no database to provision.
