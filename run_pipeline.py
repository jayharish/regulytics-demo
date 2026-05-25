"""
Full pipeline runner — Bronze → Silver → Gold in one command.
Usage:  python run_pipeline.py
"""

from src.bronze.openfda_ingest import run as bronze_run
from src.silver.transform import run as silver_run
from src.gold.aggregate import run as gold_run

if __name__ == "__main__":
    print("=" * 60)
    print("REGULYTICS — OpenFDA Medallion Pipeline")
    print("=" * 60)

    print("\n[1/3] BRONZE — ingesting from OpenFDA API...")
    run_ts = bronze_run()

    print(f"\n[2/3] SILVER — transforming run {run_ts}...")
    silver_run(run_ts)

    print(f"\n[3/3] GOLD — aggregating KPIs...")
    gold_run(run_ts)

    print("\n" + "=" * 60)
    print(f"✅ Pipeline complete. Run timestamp: {run_ts}")
    print("Next: python dashboard/app.py")
    print("=" * 60)
