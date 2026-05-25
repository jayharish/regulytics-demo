"""
Bronze layer — OpenFDA Drug Adverse Events ingestion.
Pulls raw JSON from the FDA API and lands it in Azure Blob Storage (bronze container).
No transformation — raw data only.
"""

import json
import requests
import logging
from datetime import datetime, timezone
from azure.storage.blob import BlobServiceClient
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.config import AZURE_CONNECTION_STRING, BRONZE_CONTAINER, OPENFDA_BASE_URL, OPENFDA_PAGE_SIZE, OPENFDA_TOTAL_RECORDS, OPENFDA_API_KEY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (regulytics-pipeline/1.0; contact: jayh.jethva@gmail.com)",
    "Accept": "application/json",
}

def fetch_openfda_page(skip: int, limit: int) -> dict:
    """Fetch one page of adverse event records from OpenFDA."""
    params = {"limit": limit, "skip": skip}
    if OPENFDA_API_KEY:
        params["api_key"] = OPENFDA_API_KEY
    resp = requests.get(OPENFDA_BASE_URL, params=params, headers=HEADERS, timeout=30)
    if not resp.ok:
        log.error(f"HTTP {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    return resp.json()


def upload_to_bronze(data: dict, run_ts: str, page: int) -> str:
    """Upload raw JSON page to bronze container. Returns blob path."""
    client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    container = client.get_container_client(BRONZE_CONTAINER)

    blob_name = f"openfda/events/{run_ts}/page_{page:04d}.json"
    blob_client = container.get_blob_client(blob_name)
    blob_client.upload_blob(json.dumps(data), overwrite=True)
    return blob_name


def run():
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log.info(f"Starting bronze ingestion run: {run_ts}")

    total_fetched = 0
    page = 0

    while total_fetched < OPENFDA_TOTAL_RECORDS:
        remaining = OPENFDA_TOTAL_RECORDS - total_fetched
        limit = min(OPENFDA_PAGE_SIZE, remaining)

        log.info(f"Fetching page {page} — skip={total_fetched}, limit={limit}")
        data = fetch_openfda_page(skip=total_fetched, limit=limit)

        records_in_page = len(data.get("results", []))
        if records_in_page == 0:
            log.info("No more records returned — stopping early.")
            break

        blob_path = upload_to_bronze(data, run_ts, page)
        log.info(f"  ✅ Uploaded {records_in_page} records → bronze/{blob_path}")

        total_fetched += records_in_page
        page += 1

        if records_in_page < limit:
            log.info("Last page reached.")
            break

    log.info(f"Bronze ingestion complete. Total records: {total_fetched} across {page} pages.")
    log.info(f"Run timestamp: {run_ts}  (use this to find your files in bronze/openfda/events/{run_ts}/)")
    return run_ts


if __name__ == "__main__":
    run()
