"""
Builds data/transit.db (SQLite) from the CSVs in data/.
Run once locally to regenerate the database file:  python build_db.py
The committed transit.db is what the deployed Streamlit app reads.
"""
import os
import sqlite3
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
DB_PATH = os.path.join(DATA_DIR, "transit.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS stops (
  stop_id TEXT PRIMARY KEY,
  name TEXT,
  lat REAL,
  lon REAL,
  route TEXT
);
CREATE TABLE IF NOT EXISTS schedule (
  trip_id TEXT,
  stop_id TEXT,
  sched_ts TEXT,
  PRIMARY KEY (trip_id, stop_id, sched_ts)
);
CREATE TABLE IF NOT EXISTS actual (
  trip_id TEXT,
  stop_id TEXT,
  actual_ts TEXT,
  vehicle_id TEXT,
  PRIMARY KEY (trip_id, stop_id, actual_ts)
);
CREATE TABLE IF NOT EXISTS weather (
  ts TEXT PRIMARY KEY,
  lat REAL,
  lon REAL,
  temp_c REAL,
  precip_mm REAL,
  condition TEXT
);
CREATE TABLE IF NOT EXISTS agg_daily (
  route TEXT,
  day TEXT,
  avg_delay_min REAL,
  p95_delay_min REAL,
  reliability_score REAL,
  PRIMARY KEY (route, day)
);
CREATE INDEX IF NOT EXISTS idx_actual_stop_ts   ON actual(stop_id, actual_ts);
CREATE INDEX IF NOT EXISTS idx_schedule_stop_ts ON schedule(stop_id, sched_ts);
"""

TABLES = ["stops", "schedule", "actual", "weather", "agg_daily"]


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    for tbl in TABLES:
        csv_path = os.path.join(DATA_DIR, f"{tbl}.csv")
        if not os.path.exists(csv_path):
            print(f"[skip] {csv_path} not found")
            continue
        df = pd.read_csv(csv_path)
        df.to_sql(tbl, conn, if_exists="append", index=False)
        print(f"[ok]   loaded {len(df):>5} rows into {tbl}")

    conn.commit()
    conn.close()
    print(f"\nWrote {DB_PATH}")


if __name__ == "__main__":
    main()
