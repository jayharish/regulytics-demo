"""
Gold layer — KPI aggregations from Silver, ready for Power BI / Streamlit.
Writes one Parquet per KPI table to the gold container.
"""

import logging
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from io import BytesIO
from azure.storage.blob import BlobServiceClient
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.config import AZURE_CONNECTION_STRING, SILVER_CONTAINER, GOLD_CONTAINER

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def read_silver(run_ts: str) -> pd.DataFrame:
    client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    blob_name = f"openfda/events/{run_ts}/silver_events.parquet"
    buf = BytesIO(client.get_blob_client(SILVER_CONTAINER, blob_name).download_blob().readall())
    return pd.read_parquet(buf)


def upload_gold(df: pd.DataFrame, name: str, run_ts: str):
    buf = BytesIO()
    pq.write_table(pa.Table.from_pandas(df), buf)
    buf.seek(0)
    client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    blob_name = f"openfda/{name}/latest.parquet"
    client.get_blob_client(GOLD_CONTAINER, blob_name).upload_blob(buf.read(), overwrite=True)
    log.info(f"  ✅ gold/{blob_name}  ({len(df)} rows)")


def run(run_ts: str):
    log.info(f"Starting gold aggregation for run: {run_ts}")
    df = read_silver(run_ts)

    # KPI 1 — Events by month (trend)
    monthly = (
        df.groupby(["year", "month"])
          .agg(total_events=("report_id", "count"),
               serious_events=("serious", "sum"),
               death_events=("serious_death", "sum"))
          .reset_index()
    )
    monthly["year_month"] = (
        monthly["year"].astype(str) + "-" +
        monthly["month"].astype(str).str.zfill(2)
    )
    upload_gold(monthly, "kpi_monthly_trend", run_ts)

    # KPI 2 — Top 20 drugs by event count
    drug_series = df["drug_names"].dropna().str.split(", ").explode()
    top_drugs = (
        drug_series[drug_series.str.strip() != ""]
        .value_counts()
        .head(20)
        .reset_index()
    )
    top_drugs.columns = ["drug_name", "event_count"]
    upload_gold(top_drugs, "kpi_top_drugs", run_ts)

    # KPI 3 — Outcome breakdown
    outcomes = pd.DataFrame({
        "outcome": ["Serious", "Non-serious", "Death", "Hospitalisation"],
        "count": [
            int(df["serious"].sum()),
            int((~df["serious"]).sum()),
            int(df["serious_death"].sum()),
            int(df["serious_hosp"].sum()),
        ]
    })
    upload_gold(outcomes, "kpi_outcomes", run_ts)

    # KPI 4 — Events by age group
    age_dist = (
        df.groupby("age_group")
          .agg(event_count=("report_id", "count"))
          .reset_index()
    )
    upload_gold(age_dist, "kpi_age_distribution", run_ts)

    # KPI 5 — Events by sex
    sex_dist = (
        df.groupby("patient_sex")
          .agg(event_count=("report_id", "count"))
          .reset_index()
    )
    upload_gold(sex_dist, "kpi_sex_distribution", run_ts)

    log.info("Gold aggregation complete — 5 KPI tables written.")


if __name__ == "__main__":
    run_ts = sys.argv[1] if len(sys.argv) > 1 else input("Enter run_ts: ")
    run(run_ts)
