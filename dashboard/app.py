"""
Regulytics Demo Dashboard — OpenFDA Drug Adverse Events
Reads Gold layer from Azure Blob Storage, renders KPIs with Plotly.
"""

import os
import pandas as pd
import plotly.express as px
import streamlit as st
from io import BytesIO
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Regulytics — FDA Drug Safety Dashboard",
    page_icon="💊",
    layout="wide",
)

# ── Azure connection — works locally (.env) and on Streamlit Cloud (st.secrets)
def get_secret(key: str) -> str:
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, "")

CONN_STR       = get_secret("AZURE_STORAGE_CONNECTION_STRING")
GOLD_CONTAINER = "gold"

@st.cache_data(ttl=3600)
def load_gold(blob_name: str) -> pd.DataFrame:
    client = BlobServiceClient.from_connection_string(CONN_STR)
    buf = BytesIO(
        client.get_blob_client(GOLD_CONTAINER, blob_name)
              .download_blob().readall()
    )
    return pd.read_parquet(buf)

# ── Load KPI tables ─────────────────────────────────────────────────────────────
try:
    monthly  = load_gold("openfda/kpi_monthly_trend/latest.parquet")
    drugs    = load_gold("openfda/kpi_top_drugs/latest.parquet")
    outcomes = load_gold("openfda/kpi_outcomes/latest.parquet")
    age_dist = load_gold("openfda/kpi_age_distribution/latest.parquet")
    sex_dist = load_gold("openfda/kpi_sex_distribution/latest.parquet")
    data_loaded = True
except Exception as e:
    data_loaded = False
    load_error = str(e)

# ── Header ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background: linear-gradient(90deg, #0078d4 0%, #005a9e 100%);
            padding: 1.5rem 2rem; border-radius: 8px; margin-bottom: 1.5rem;">
  <h1 style="color:white; margin:0; font-size:1.8rem;">
    💊 FDA Drug Adverse Events — Live Dashboard
  </h1>
  <p style="color:#c7e0f4; margin:0.3rem 0 0;">
    Source: OpenFDA API &nbsp;·&nbsp; Medallion pipeline: Bronze → Silver → Gold &nbsp;·&nbsp;
    Built by <strong>Regulytics</strong>
  </p>
</div>
""", unsafe_allow_html=True)

if not data_loaded:
    st.error(f"Could not load data from Azure: {load_error}")
    st.info("Run `python run_pipeline.py` first to populate the Gold layer.")
    st.stop()

# ── Metric strip ────────────────────────────────────────────────────────────────
total_events  = int(monthly["total_events"].sum())
serious_count = int(monthly["serious_events"].sum())
death_count   = int(monthly["death_events"].sum())
serious_pct   = serious_count / total_events * 100 if total_events else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Adverse Events",  f"{total_events:,}")
col2.metric("Serious Events",        f"{serious_count:,}",  f"{serious_pct:.1f}%")
col3.metric("Deaths Reported",       f"{death_count:,}")
col4.metric("Drugs Tracked (Top 20)", f"{len(drugs):,}")

st.divider()

# ── Row 1: Trend + Top Drugs ────────────────────────────────────────────────────
r1_left, r1_right = st.columns([3, 2])

with r1_left:
    st.subheader("📈 Adverse Events Over Time")
    monthly_sorted = monthly.sort_values(["year", "month"])
    fig_trend = px.line(
        monthly_sorted, x="year_month", y="total_events",
        labels={"year_month": "Month", "total_events": "Events"},
        color_discrete_sequence=["#0078d4"],
    )
    fig_trend.add_scatter(
        x=monthly_sorted["year_month"], y=monthly_sorted["serious_events"],
        mode="lines", name="Serious", line=dict(color="#d13438", dash="dash")
    )
    fig_trend.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=320,
                            legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_trend, use_container_width=True)

with r1_right:
    st.subheader("⚠️ Outcome Breakdown")
    fig_outcomes = px.pie(
        outcomes, names="outcome", values="count",
        color_discrete_sequence=["#d13438", "#0078d4", "#107c10", "#ff8c00"],
        hole=0.45,
    )
    fig_outcomes.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=320,
                               legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig_outcomes, use_container_width=True)

# ── Row 2: Top Drugs + Demographics ────────────────────────────────────────────
r2_left, r2_right = st.columns([3, 2])

with r2_left:
    st.subheader("💊 Top 20 Drugs by Adverse Event Reports")
    fig_drugs = px.bar(
        drugs.sort_values("event_count"),
        x="event_count", y="drug_name",
        orientation="h",
        labels={"event_count": "Reports", "drug_name": "Drug"},
        color="event_count",
        color_continuous_scale="Blues",
    )
    fig_drugs.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                            height=420, showlegend=False,
                            coloraxis_showscale=False)
    st.plotly_chart(fig_drugs, use_container_width=True)

with r2_right:
    st.subheader("👤 Patient Demographics")

    st.caption("By Age Group")
    age_order = ["0-17", "18-34", "35-49", "50-64", "65-79", "80+", "Unknown"]
    age_dist["age_group"] = pd.Categorical(age_dist["age_group"], categories=age_order, ordered=True)
    fig_age = px.bar(
        age_dist.sort_values("age_group"),
        x="age_group", y="event_count",
        labels={"age_group": "Age Group", "event_count": "Events"},
        color_discrete_sequence=["#0078d4"],
    )
    fig_age.update_layout(margin=dict(l=0, r=0, t=5, b=0), height=180)
    st.plotly_chart(fig_age, use_container_width=True)

    st.caption("By Sex")
    fig_sex = px.pie(
        sex_dist, names="patient_sex", values="event_count",
        color_discrete_sequence=["#0078d4", "#d13438", "#737373"],
        hole=0.5,
    )
    fig_sex.update_layout(margin=dict(l=0, r=0, t=5, b=0), height=180,
                          legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig_sex, use_container_width=True)

# ── Footer ──────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Data source: [OpenFDA Drug Adverse Events API](https://api.fda.gov/drug/event.json) · "
    "Pipeline: Azure ADLS Gen2 (Bronze → Silver → Gold) · "
    "Built with Python, Pandas, Plotly, Streamlit · "
    "© Regulytics 2026"
)
