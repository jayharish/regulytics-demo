import os
from dotenv import load_dotenv

load_dotenv()

AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
STORAGE_ACCOUNT_NAME    = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "regulyticsdatalake")

BRONZE_CONTAINER = "bronze"
SILVER_CONTAINER = "silver"
GOLD_CONTAINER   = "gold"

# OpenFDA
OPENFDA_API_KEY      = os.getenv("OPENFDA_API_KEY", "")
OPENFDA_BASE_URL     = "https://api.fda.gov/drug/event.json"
OPENFDA_PAGE_SIZE    = 1000   # max per request with API key (100 without)
OPENFDA_TOTAL_RECORDS = 5000  # records per daily run
