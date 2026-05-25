"""
Silver layer — Clean and normalise raw OpenFDA adverse event JSON.
Reads all bronze pages for a given run, flattens and cleans, writes Parquet to silver.
"""

import json
import logging
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from io import BytesIO
from azure.storage.blob import BlobServiceClient
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.config import AZURE_CONNECTION_STRING, BRONZE_CONTAINER, SILVER_CONTAINER

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def list_bronze_pages(run_ts: str) -> list[str]:
    client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    container = client.get_container_client(BRONZE_CONTAINER)
    prefix = f"openfda/events/{run_ts}/"
    return [b.name for b in container.list_blobs(name_starts_with=prefix)]


def download_json(blob_name: str) -> dict:
    client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    blob = client.get_blob_client(BRONZE_CONTAINER, blob_name)
    return json.loads(blob.download_blob().readall())


def flatten_record(r: dict) -> dict:
    """Extract key fields from a raw adverse event record."""
    patient = r.get("patient", {})
    return {
        "report_id":        r.get("safetyreportid", ""),
        "receive_date":     r.get("receivedate", ""),
        "serious":          r.get("serious", ""),
        "serious_death":    r.get("seriousnessdeath", "0"),
        "serious_hosp":     r.get("seriousnesshospitalization", "0"),
        "country":          r.get("occurcountry", ""),
        "patient_age":      patient.get("patientonsetage", None),
        "patient_age_unit": patient.get("patientonsetageunit", ""),
        "patient_sex":      patient.get("patientsex", ""),
        "patient_weight":   patient.get("patientweight", None),
        "drug_names":       ", ".join([
            d.get("medicinalproduct", "UNKNOWN")
            for d in r.get("patient", {}).get("drug", [])
        ]),
        "reaction_terms":   ", ".join([
            rx.get("reactionmeddrapt", "")
            for rx in r.get("patient", {}).get("reaction", [])
        ]),
        "num_drugs":        len(r.get("patient", {}).get("drug", [])),
        "num_reactions":    len(r.get("patient", {}).get("reaction", [])),
    }


def clean(df: pd.DataFrame) -> pd.DataFrame:
    # Parse date
    df["receive_date"] = pd.to_datetime(df["receive_date"], format="%Y%m%d", errors="coerce")
    df["year"]  = df["receive_date"].dt.year
    df["month"] = df["receive_date"].dt.month

    # Numeric fields
    df["patient_age"]    = pd.to_numeric(df["patient_age"], errors="coerce")
    df["patient_weight"] = pd.to_numeric(df["patient_weight"], errors="coerce")

    # Boolean-ish fields
    df["serious"]       = df["serious"].astype(str).map({"1": True, "2": False}).fillna(False)
    df["serious_death"] = df["serious_death"].astype(str).map({"1": True, "0": False}).fillna(False)
    df["serious_hosp"]  = df["serious_hosp"].astype(str).map({"1": True, "0": False}).fillna(False)

    # Sex labels
    df["patient_sex"] = df["patient_sex"].astype(str).map(
        {"0": "Unknown", "1": "Male", "2": "Female"}
    ).fillna("Unknown")

    # Age bucketing (for Gold KPIs)
    bins   = [0, 17, 34, 49, 64, 79, 200]
    labels = ["0-17", "18-34", "35-49", "50-64", "65-79", "80+"]
    df["age_group"] = pd.cut(df["patient_age"], bins=bins, labels=labels, right=True)
    df["age_group"] = df["age_group"].astype(str).replace("nan", "Unknown")

    # Drop rows with no report ID
    df = df.dropna(subset=["report_id"])
    df = df.drop_duplicates(subset=["report_id"])

    return df


def upload_silver(df: pd.DataFrame, run_ts: str):
    buf = BytesIO()
    table = pa.Table.from_pandas(df)
    pq.write_table(table, buf)
    buf.seek(0)

    client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    blob_name = f"openfda/events/{run_ts}/silver_events.parquet"
    client.get_blob_client(SILVER_CONTAINER, blob_name).upload_blob(buf.read(), overwrite=True)
    return blob_name


def run(run_ts: str):
    log.info(f"Starting silver transform for run: {run_ts}")

    pages = list_bronze_pages(run_ts)
    log.info(f"Found {len(pages)} bronze pages to process")

    all_records = []
    for page_path in pages:
        raw = download_json(page_path)
        records = raw.get("results", [])
        all_records.extend([flatten_record(r) for r in records])
        log.info(f"  Processed {page_path} — {len(records)} records")

    df = pd.DataFrame(all_records)
    log.info(f"Raw records: {len(df)}")

    df = clean(df)
    log.info(f"Clean records: {len(df)} (after dedup + date parse)")

    blob_path = upload_silver(df, run_ts)
    log.info(f"✅ Silver written → silver/{blob_path}")
    log.info(f"   Shape: {df.shape}  |  Date range: {df['receive_date'].min()} → {df['receive_date'].max()}")
    return df


if __name__ == "__main__":
    import sys
    run_ts = sys.argv[1] if len(sys.argv) > 1 else input("Enter run_ts: ")
    run(run_ts)
