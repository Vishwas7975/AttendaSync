# ============================================================
#  main.py  –  Entry point for AttendaSync
# ============================================================
"""
Usage
-----
  # Full historical sync (fetches ALL dates from device):
  python main.py --full-sync

  # Run once for today only (default):
  python main.py

  # Run on a schedule every N minutes (today only each run):
  python main.py --schedule
"""

import argparse
import logging
import os
import time
import traceback
from datetime import datetime, timedelta

import pandas as pd

import config
from config import FETCH_INTERVAL_MINUTES
from fetch_logs import fetch_logs

from process_logs import process_logs
from sheets_writer import connect_sheet, upload_to_sheet

# ── Logging setup ─────────────────────────────────────────────

os.makedirs("logs", exist_ok=True)
log_filename = datetime.now().strftime("logs/attendance_%Y-%m-%d.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("main")


# ── Core run logic ────────────────────────────────────────────

def run_once(full_sync: bool = False):
    logger.info("=" * 60)
    logger.info("Attendance sync started%s", " [FULL SYNC]" if full_sync else "")

    # 0. Initialize local database & employee mapping sync
    try:
        import database
        database.init_db()
        database.sync_employees_from_csv()
    except Exception as e:
        logger.warning("Database init warning: %s", e)

    # 1. Verify Google Sheet connection
    try:
        spreadsheet = connect_sheet()
        logger.info("Google Sheet connected OK")
    except Exception:
        logger.error("Cannot connect to Google Sheet:\n%s", traceback.format_exc())
        return


    # 2. Fetch logs from device
    #    --full-sync  → fetch ALL dates from device FTP (all 70+ days back)
    #    normal run   → fetch past 30 days / current payroll cycle (fast & captures late scans)
    if full_sync:
        since = None
        logger.info("Fetching ALL dates from device (full sync).")
    else:
        lookback_days = getattr(config, "DEFAULT_FETCH_LOOKBACK_DAYS", 30)
        since = datetime.now() - timedelta(days=lookback_days)
        logger.info("Fetching logs from past %d days (since %s).", lookback_days, since.strftime("%Y-%m-%d"))

    logs_df = fetch_logs(since=since)


    if logs_df.empty:
        logger.warning("No logs retrieved – nothing to process.")
        return

    logger.info("Retrieved %d raw log entries.", len(logs_df))

    # 3. Load employee mapping
    emp_map_path = "employee_map.csv"
    if not os.path.exists(emp_map_path):
        logger.error("employee_map.csv not found!")
        return

    emp_map = pd.read_csv(emp_map_path)
    logger.info("Loaded %d employees from mapping file.", len(emp_map))

    # 4. Process / transform
    processed = process_logs(logs_df, emp_map)

    if processed.empty:
        logger.warning("Processing returned 0 records.")
        return

    logger.info("Processed %d attendance records.", len(processed))
    print("\n-- Processed attendance --")
    print(processed.to_string(index=False))
    print()

    # 5. Upload to Google Sheets (Today + This Month + All Records tabs)
    try:
        upload_to_sheet(processed)
        logger.info("Upload complete.")
    except Exception:
        logger.error("Upload failed:\n%s", traceback.format_exc())

    logger.info("Attendance sync finished.")
    logger.info("=" * 60)


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AttendaSync — Attendance Automation System")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help=f"Keep running every {FETCH_INTERVAL_MINUTES} minutes (today-only fetches)",
    )
    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="Fetch ALL dates from device and upload everything (use once for initial setup)",
    )
    args = parser.parse_args()

    if args.schedule:
        logger.info(
            "Scheduler started – will sync every %d minute(s) (today's data only).",
            FETCH_INTERVAL_MINUTES,
        )
        while True:
            run_once(full_sync=False)
            next_run = datetime.now() + timedelta(minutes=FETCH_INTERVAL_MINUTES)
            logger.info("Next sync at %s", next_run.strftime("%H:%M:%S"))
            time.sleep(FETCH_INTERVAL_MINUTES * 60)
    else:
        run_once(full_sync=args.full_sync)


if __name__ == "__main__":
    main()