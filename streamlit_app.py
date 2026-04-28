"""
Transit Delay Analyzer — Streamlit dashboard
SQLite-backed version (zero-cost deploy on Streamlit Community Cloud).
The original architecture uses PostgreSQL + Docker; for the public demo
the same data is served from a bundled SQLite file (data/transit.db).
"""
import os
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# ---------- DB engine ----------
DB_PATH = Path(__file__).parent / "data" / "transit.db"
ENGINE = create_engine(f"sqlite:///{DB_PATH}")


@st.cache_data(ttl=60)
def qdf(sql: str, params: dict | None = None) -> pd.DataFrame:
    with ENGINE.connect() as c:
        return pd.read_sql_query(text(sql), c, params=params)


# ---------- Page setup ----------
st.set_page_config(page_title="Transit Delay Analyzer", layout="wide", page_icon="🚍")
st.title("🚍 Transit Delay Analyzer")
st.caption(
    "ETL pipeline + interactive dashboard for GTFS transit reliability. "
    "Built with Python, SQL, Streamlit. "
    "[GitHub repo →](https://github.com/ArpitaRaj27/transit-delay-analyzer)"
)

# ---------- Discover data range so the app shows charts on first load ----------
range_df = qdf("SELECT MIN(day) AS dmin, MAX(day) AS dmax FROM agg_daily;")
data_min = pd.to_datetime(range_df["dmin"].iloc[0]).date() if range_df["dmin"].iloc[0] else dt.date.today() - dt.timedelta(days=6)
data_max = pd.to_datetime(range_df["dmax"].iloc[0]).date() if range_df["dmax"].iloc[0] else dt.date.today()

# ---------- Sidebar ----------
st.sidebar.header("Filters")
date_from = st.sidebar.date_input("From", data_min, min_value=data_min, max_value=data_max)
date_to = st.sidebar.date_input("To", data_max, min_value=data_min, max_value=data_max)

routes_all = qdf("SELECT DISTINCT route FROM agg_daily ORDER BY route;")
route_options = routes_all["route"].astype(str).tolist() if not routes_all.empty else []
selected_routes = st.sidebar.multiselect(
    "Routes", options=route_options, default=route_options
)

st.sidebar.markdown("---")
st.sidebar.caption(f"Data window: **{data_min}** → **{data_max}**")
st.sidebar.caption("Demo data sourced from a sample GTFS feed.")


def build_where(date_from, date_to, selected_routes):
    """Build WHERE clause + params dict. SQLite-friendly (no ANY())."""
    where = "WHERE day BETWEEN :dfrom AND :dto"
    params = {"dfrom": str(date_from), "dto": str(date_to)}
    if selected_routes:
        # SQLAlchemy expanding bindparam works for IN clauses
        placeholders = ", ".join(f":r{i}" for i in range(len(selected_routes)))
        where += f" AND route IN ({placeholders})"
        for i, r in enumerate(selected_routes):
            params[f"r{i}"] = r
    return where, params


where, base_params = build_where(date_from, date_to, selected_routes)

# ---------- KPIs ----------
kpi = qdf(
    f"""
    SELECT
      ROUND(AVG(avg_delay_min), 2)      AS avg_delay,
      ROUND(AVG(p95_delay_min), 2)      AS p95_delay,
      ROUND(AVG(reliability_score), 3)  AS reliability
    FROM agg_daily
    {where}
    """,
    base_params,
)

c1, c2, c3 = st.columns(3)
c1.metric("Avg delay (min)", kpi["avg_delay"].iloc[0] if not kpi.empty else 0)
c2.metric("P95 delay (min)", kpi["p95_delay"].iloc[0] if not kpi.empty else 0)
c3.metric("Reliability", kpi["reliability"].iloc[0] if not kpi.empty else 0)

# ---------- Scorecard ----------
score = qdf(
    f"""
    SELECT route, day,
           ROUND(avg_delay_min, 2)     AS avg_delay_min,
           ROUND(p95_delay_min, 2)     AS p95_delay_min,
           ROUND(reliability_score, 3) AS reliability_score
    FROM agg_daily
    {where}
    ORDER BY day DESC, route
    """,
    base_params,
)

st.subheader("Scorecard")
st.dataframe(score, width="stretch")
st.download_button(
    "Download CSV",
    score.to_csv(index=False).encode("utf-8"),
    file_name="scorecard.csv",
    mime="text/csv",
)

# ---------- Trends ----------
st.subheader("Trends")
colA, colB = st.columns(2)

trend = qdf(
    f"""
    SELECT day, route,
           ROUND(AVG(avg_delay_min), 2)     AS avg_delay_min,
           ROUND(AVG(p95_delay_min), 2)     AS p95_delay_min,
           ROUND(AVG(reliability_score), 3) AS reliability_score
    FROM agg_daily
    {where}
    GROUP BY day, route
    ORDER BY day, route
    """,
    base_params,
)

if not trend.empty:
    with colA:
        st.markdown("**Avg delay (min) by route over time**")
        st.line_chart(trend.pivot(index="day", columns="route", values="avg_delay_min"))
    with colB:
        worst = qdf(
            f"""
            SELECT route, ROUND(AVG(avg_delay_min), 2) AS avg_delay
            FROM agg_daily
            {where}
            GROUP BY route
            ORDER BY avg_delay DESC
            LIMIT 10
            """,
            base_params,
        )
        if not worst.empty:
            st.markdown("**Worst routes by average delay**")
            st.bar_chart(worst.set_index("route")["avg_delay"])

# ---------- Weather effect ----------
st.subheader("Weather effect")
scatter = qdf(
    f"""
    WITH w AS (
      SELECT DATE(ts) AS d, AVG(precip_mm) AS precip
      FROM weather
      WHERE DATE(ts) BETWEEN :dfrom AND :dto
      GROUP BY DATE(ts)
    ),
    d AS (
      SELECT day, route, AVG(avg_delay_min) AS avg_delay
      FROM agg_daily
      {where}
      GROUP BY day, route
    )
    SELECT d.day, d.route, d.avg_delay, COALESCE(w.precip, 0) AS precip_mm
    FROM d
    LEFT JOIN w ON w.d = d.day
    ORDER BY d.day, d.route
    """,
    base_params,
)

if not scatter.empty:
    st.scatter_chart(
        scatter.rename(columns={"avg_delay": "y", "precip_mm": "x"})[["x", "y"]]
    )
    st.caption("x = precipitation (mm) on that day,  y = avg delay (min)")

# ---------- Route detail ----------
st.subheader("Route details")
sel = st.selectbox("Pick a route", route_options or ["R1"])
detail = qdf(
    """
    SELECT day, avg_delay_min, p95_delay_min, reliability_score
    FROM agg_daily
    WHERE route = :r
    ORDER BY day
    """,
    {"r": sel},
)
if not detail.empty:
    detail = detail.set_index("day")
    st.line_chart(detail[["avg_delay_min"]])
    st.line_chart(detail[["p95_delay_min"]])
    st.line_chart(detail[["reliability_score"]])
else:
    st.info("No data yet for the selected route.")
