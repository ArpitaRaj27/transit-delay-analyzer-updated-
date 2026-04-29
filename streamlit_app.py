"""
Transit Delay Analyzer — v2 dashboard
Adds auto-generated insights, interactive Altair charts, conditional formatting,
and narrative section headers so the dashboard *explains* the data, not just displays it.
"""
import datetime as dt
from pathlib import Path

import altair as alt
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

# Hero header — leads with a question, not a description
st.title("Transit Delay Analyzer")
st.markdown(
    "##### Which routes are reliable, and how much does weather affect them?"
)
st.caption(
    "ETL pipeline + interactive dashboard for GTFS transit reliability  ·  "
    "Python · SQL · Streamlit  ·  "
    "[GitHub repo →](https://github.com/ArpitaRaj27/transit-delay-analyzer)"
)
st.divider()

# ---------- Data range discovery ----------
range_df = qdf("SELECT MIN(day) AS dmin, MAX(day) AS dmax FROM agg_daily;")
data_min = pd.to_datetime(range_df["dmin"].iloc[0]).date()
data_max = pd.to_datetime(range_df["dmax"].iloc[0]).date()

# ---------- Sidebar filters ----------
st.sidebar.header("Filters")
date_from = st.sidebar.date_input("From", data_min, min_value=data_min, max_value=data_max)
date_to = st.sidebar.date_input("To", data_max, min_value=data_min, max_value=data_max)

routes_all = qdf("SELECT DISTINCT route FROM agg_daily ORDER BY route;")
route_options = routes_all["route"].astype(str).tolist() if not routes_all.empty else []
selected_routes = st.sidebar.multiselect("Routes", options=route_options, default=route_options)

st.sidebar.divider()
st.sidebar.caption(f"Data window: **{data_min}** → **{data_max}**")
st.sidebar.caption("Source: sample GTFS feed + simulated arrivals + Open-Meteo weather.")


def build_where(date_from, date_to, selected_routes):
    where = "WHERE day BETWEEN :dfrom AND :dto"
    params = {"dfrom": str(date_from), "dto": str(date_to)}
    if selected_routes:
        placeholders = ", ".join(f":r{i}" for i in range(len(selected_routes)))
        where += f" AND route IN ({placeholders})"
        for i, r in enumerate(selected_routes):
            params[f"r{i}"] = r
    return where, params


where, base_params = build_where(date_from, date_to, selected_routes)

# ---------- Pull the working dataset once for insights + charts ----------
df = qdf(
    f"""
    SELECT route, day, avg_delay_min, p95_delay_min, reliability_score
    FROM agg_daily
    {where}
    ORDER BY day, route
    """,
    base_params,
)
df["day"] = pd.to_datetime(df["day"])

weather_df = qdf(
    """
    SELECT DATE(ts) AS day, AVG(precip_mm) AS precip_mm, AVG(temp_c) AS temp_c
    FROM weather
    WHERE DATE(ts) BETWEEN :dfrom AND :dto
    GROUP BY DATE(ts)
    """,
    {"dfrom": str(date_from), "dto": str(date_to)},
)
if not weather_df.empty:
    weather_df["day"] = pd.to_datetime(weather_df["day"])

# ============================================================
# 1. AUTO-INSIGHTS — the headline analytical takeaways
# ============================================================
st.subheader("What the data says")

if df.empty:
    st.info("No data for the current filters. Widen the date range or add routes.")
else:
    insights = []

    # Best & worst route by avg delay
    by_route = df.groupby("route")["avg_delay_min"].mean().sort_values()
    best_route, best_val = by_route.index[0], by_route.iloc[0]
    worst_route, worst_val = by_route.index[-1], by_route.iloc[-1]
    insights.append(
        f"➡️ **Most reliable: Route {best_route}** averages just "
        f"**{best_val:.2f} min** delay across the window."
    )
    insights.append(
        f"➡️ **Least reliable: Route {worst_route}** averages "
        f"**{worst_val:.2f} min** delay — about **{(worst_val - best_val):.1f}× higher** "
        f"than Route {best_route}."
    )

    # Biggest single-day disruption
    worst_idx = df["avg_delay_min"].idxmax()
    worst_row = df.loc[worst_idx]
    if worst_row["avg_delay_min"] > 5:
        insights.append(
            f"➡️ **Biggest disruption: Route {worst_row['route']} on "
            f"{worst_row['day'].date()}** — average delay spiked to "
            f"**{worst_row['avg_delay_min']:.1f} min** (P95: {worst_row['p95_delay_min']:.1f} min)."
        )

    # Weather correlation
    if not weather_df.empty:
        daily = df.groupby("day")["avg_delay_min"].mean().reset_index()
        merged = daily.merge(weather_df[["day", "precip_mm"]], on="day", how="inner")
        if len(merged) >= 3 and merged["precip_mm"].std() > 0:
            corr = merged["avg_delay_min"].corr(merged["precip_mm"])
            if pd.notna(corr):
                if corr > 0.4:
                    insights.append(
                        f"**Weather matters:** delay correlates with precipitation "
                        f"(r = {corr:+.2f}) — wet days run noticeably slower."
                    )
                elif corr < -0.4:
                    insights.append(
                        f"**Counterintuitive:** delay *negatively* correlates with "
                        f"precipitation (r = {corr:+.2f}) in this window — likely a "
                        f"small-sample artifact worth more data."
                    )
                else:
                    insights.append(
                        f"**Weather signal is weak** in this window "
                        f"(precip↔delay r = {corr:+.2f}) — other factors dominate."
                    )

    # System-wide reliability
    sys_rel = df["reliability_score"].mean()
    rel_label = "strong" if sys_rel >= 0.9 else "moderate" if sys_rel >= 0.75 else "weak"
    insights.append(
        f"**System-wide reliability is {rel_label}** "
        f"(avg score **{sys_rel:.1%}** across {df['route'].nunique()} routes, "
        f"{df['day'].nunique()} days)."
    )

    for line in insights:
        st.markdown(f"- {line}")

st.divider()

# ============================================================
# 2. KPI ROW — with context, not just numbers
# ============================================================
st.subheader("Headline metrics")

if df.empty:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg delay (min)", "–")
    c2.metric("P95 delay (min)", "–")
    c3.metric("Reliability", "–")
    c4.metric("Routes tracked", "–")
else:
    avg_delay = df["avg_delay_min"].mean()
    p95_delay = df["p95_delay_min"].mean()
    reliability = df["reliability_score"].mean()
    n_routes = df["route"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg delay (min)", f"{avg_delay:.2f}", help="Mean of daily route averages")
    c2.metric("P95 delay (min)", f"{p95_delay:.2f}", help="95th-percentile delay — the bad-day experience")
    c3.metric("Reliability", f"{reliability:.1%}", help="0–1 score; >90% is strong")
    c4.metric("Routes tracked", n_routes)

st.divider()

# ============================================================
# 3. INTERACTIVE TRENDS — Altair with tooltips
# ============================================================
st.subheader("How did each route trend?")
st.caption("Hover any point for the exact value.")

if df.empty:
    st.info("No trend data.")
else:
    line = (
        alt.Chart(df)
        .mark_line(point=alt.OverlayMarkDef(size=70, filled=True))
        .encode(
            x=alt.X("day:T", title="Date"),
            y=alt.Y("avg_delay_min:Q", title="Avg delay (min)"),
            color=alt.Color("route:N", title="Route", scale=alt.Scale(scheme="tableau10")),
            tooltip=[
                alt.Tooltip("day:T", title="Date"),
                alt.Tooltip("route:N", title="Route"),
                alt.Tooltip("avg_delay_min:Q", title="Avg delay (min)", format=".2f"),
                alt.Tooltip("p95_delay_min:Q", title="P95 delay (min)", format=".2f"),
                alt.Tooltip("reliability_score:Q", title="Reliability", format=".1%"),
            ],
        )
        .properties(height=380)
        .interactive()
    )
    st.altair_chart(line, width="stretch")

# Two-column: ranking + reliability heatmap
colA, colB = st.columns([1, 1])

with colA:
    st.subheader("Routes ranked")
    if not df.empty:
        ranking = (
            df.groupby("route")
            .agg(avg_delay=("avg_delay_min", "mean"), reliability=("reliability_score", "mean"))
            .reset_index()
            .sort_values("avg_delay", ascending=False)
        )
        bar = (
            alt.Chart(ranking)
            .mark_bar()
            .encode(
                x=alt.X("avg_delay:Q", title="Avg delay (min)"),
                y=alt.Y("route:N", sort="-x", title="Route"),
                color=alt.Color(
                    "avg_delay:Q",
                    scale=alt.Scale(scheme="redyellowgreen", reverse=True),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("route:N", title="Route"),
                    alt.Tooltip("avg_delay:Q", title="Avg delay (min)", format=".2f"),
                    alt.Tooltip("reliability:Q", title="Reliability", format=".1%"),
                ],
            )
            .properties(height=320)
        )
        st.altair_chart(bar, width="stretch")

with colB:
    st.subheader("Reliability heatmap")
    if not df.empty:
        heat = (
            alt.Chart(df)
            .mark_rect()
            .encode(
                x=alt.X("day:T", title="Date"),
                y=alt.Y("route:N", title="Route"),
                color=alt.Color(
                    "reliability_score:Q",
                    scale=alt.Scale(scheme="redyellowgreen", domain=[0.5, 1.0]),
                    legend=alt.Legend(title="Reliability"),
                ),
                tooltip=[
                    alt.Tooltip("day:T", title="Date"),
                    alt.Tooltip("route:N", title="Route"),
                    alt.Tooltip("reliability_score:Q", title="Reliability", format=".1%"),
                    alt.Tooltip("avg_delay_min:Q", title="Avg delay (min)", format=".2f"),
                ],
            )
            .properties(height=320)
        )
        st.altair_chart(heat, width="stretch")

st.divider()

# ============================================================
# 4. WEATHER EFFECT — interactive scatter
# ============================================================
st.subheader("Does precipitation hurt performance?")

if df.empty or weather_df.empty:
    st.info("Not enough overlapping weather + delay data for the current filters.")
else:
    daily_route = df.copy()
    merged = daily_route.merge(weather_df[["day", "precip_mm"]], on="day", how="left").fillna({"precip_mm": 0})
    if not merged.empty:
        scatter = (
            alt.Chart(merged)
            .mark_circle(size=110, opacity=0.75)
            .encode(
                x=alt.X("precip_mm:Q", title="Precipitation (mm)"),
                y=alt.Y("avg_delay_min:Q", title="Avg delay (min)"),
                color=alt.Color("route:N", title="Route", scale=alt.Scale(scheme="tableau10")),
                tooltip=[
                    alt.Tooltip("day:T", title="Date"),
                    alt.Tooltip("route:N", title="Route"),
                    alt.Tooltip("precip_mm:Q", title="Precipitation (mm)", format=".2f"),
                    alt.Tooltip("avg_delay_min:Q", title="Avg delay (min)", format=".2f"),
                ],
            )
            .properties(height=340)
        )
        # Add a regression line if there's enough variation
        if merged["precip_mm"].std() > 0:
            reg = scatter.transform_regression("precip_mm", "avg_delay_min").mark_line(
                color="#888", strokeDash=[4, 4]
            )
            st.altair_chart(scatter + reg, width="stretch")
        else:
            st.altair_chart(scatter, width="stretch")
        st.caption("Each dot = one route on one day. Dashed line = linear regression.")

st.divider()

# ============================================================
# 5. SCORECARD — with conditional formatting
# ============================================================
st.subheader("Full scorecard")
st.caption("Color-coded: 🟢 strong reliability / fast, 🔴 weak reliability / slow. Sortable by clicking column headers.")

if df.empty:
    st.info("No rows in the current selection.")
else:
    score_df = (
        df.assign(day=df["day"].dt.date)
        [["route", "day", "avg_delay_min", "p95_delay_min", "reliability_score"]]
        .sort_values(["day", "route"], ascending=[False, True])
        .reset_index(drop=True)
    )

    styled = (
        score_df.style
        .background_gradient(subset=["avg_delay_min"], cmap="RdYlGn_r", vmin=0, vmax=6)
        .background_gradient(subset=["p95_delay_min"], cmap="RdYlGn_r", vmin=0, vmax=10)
        .background_gradient(subset=["reliability_score"], cmap="RdYlGn", vmin=0.5, vmax=1.0)
        .format({
            "avg_delay_min": "{:.2f}",
            "p95_delay_min": "{:.2f}",
            "reliability_score": "{:.1%}",
        })
    )
    st.dataframe(styled, width="stretch", hide_index=True)
    st.download_button(
        "Download as CSV ⬇️",
        score_df.to_csv(index=False).encode("utf-8"),
        file_name=f"scorecard_{date_from}_{date_to}.csv",
        mime="text/csv",
    )

# ============================================================
# 6. PER-ROUTE DRILL-DOWN
# ============================================================
st.divider()
st.subheader("Drill into a single route")
sel = st.selectbox("Pick a route", route_options or ["–"])
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
    detail["day"] = pd.to_datetime(detail["day"])
    long = detail.melt(id_vars="day", var_name="metric", value_name="value")
    drill = (
        alt.Chart(long)
        .mark_line(point=True)
        .encode(
            x=alt.X("day:T", title="Date"),
            y=alt.Y("value:Q", title=None),
            color=alt.Color("metric:N", title="Metric"),
            tooltip=[
                alt.Tooltip("day:T", title="Date"),
                alt.Tooltip("metric:N", title="Metric"),
                alt.Tooltip("value:Q", title="Value", format=".2f"),
            ],
        )
        .properties(height=320)
        .facet(row=alt.Row("metric:N", header=alt.Header(title=None, labelAngle=0)))
        .resolve_scale(y="independent")
    )
    st.altair_chart(drill, width="stretch")
else:
    st.info("No data for the selected route.")
