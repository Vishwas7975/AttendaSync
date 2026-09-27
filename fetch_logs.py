# ============================================================
#  fetch_logs.py  –  Pull attendance logs from Warden device
#                    via FTP (IP is read from config.py)
#
#  FTP Structure:
#    /IdentifyRecords/YYYY-MM-DD/HH/HHMMSS_ID_NAME.txt
#
#  All data is extracted from the filename itself:
#    085606_718_STRANGERBABY.txt
#    ^^^^^^ ^^^ ^^^^^^^^^^^^
#    time   ID  Name
# ============================================================

import logging
import ftplib
import time
import pandas as pd
from datetime import datetime, timedelta

import config
from device_finder import get_device_ip

logger = logging.getLogger(__name__)

# ── FTP credentials ───────────────────────────────────────────
# NOTE: FTP_HOST is no longer a frozen constant. The device IP can change
# daily, so the actual host is resolved fresh on every connection attempt
# via get_device_ip() (auto-detect + fallback to config.DEVICE_IP).
# Credentials themselves live in .env (see config.py), never hardcoded here.
FTP_PORT    = config.FTP_PORT
FTP_USER    = config.FTP_USER
FTP_PASS    = config.FTP_PASS
FTP_BASE    = "/IdentifyRecords"

# ── Retry config ──────────────────────────────────────────────
MAX_RETRIES = 3       # try 3 times
RETRY_DELAY = 30      # wait 30 seconds between retries


def _connect_ftp(host: str, timeout: int = 30) -> ftplib.FTP:
    ftp = ftplib.FTP()
    ftp.connect(host, FTP_PORT, timeout=timeout)
    ftp.set_pasv(False)   # ← change True to False
    ftp.login(FTP_USER, FTP_PASS)
    logger.info("FTP connected to %s:%s", host, FTP_PORT)
    return ftp


def _connect_ftp_with_retry() -> ftplib.FTP:
    """
    Resolve the device IP once (auto-detect + fallback to config.DEVICE_IP),
    then try connecting up to MAX_RETRIES times with RETRY_DELAY seconds
    between attempts. The IP is not re-resolved between retries — if the
    device dropped mid-scan rather than changed address, re-scanning the
    subnet on every retry would just slow things down for no benefit.

    If device_finder already scanned the whole subnet and found nothing
    (confirmed_live=False), the device is genuinely offline right now —
    retrying the same dead IP 3 times with 30s delays would just waste
    ~90 seconds for no chance of success, so we make a single quick
    attempt instead (in case it came back online in the last second)
    and fail fast otherwise.
    """
    host, confirmed_live = get_device_ip(config.DEVICE_IP)

    if not confirmed_live:
        logger.warning(
            "Skipping full retry cycle — device was not found anywhere on the "
            "subnet during auto-detect. Making one quick attempt only."
        )
        try:
            return _connect_ftp(host, timeout=5)
        except Exception as e:
            logger.error("FTP connection failed (device offline): %s", e)
            raise

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _connect_ftp(host)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning(
                    "FTP connection attempt %d/%d failed: %s — retrying in %ds...",
                    attempt, MAX_RETRIES, e, RETRY_DELAY
                )
                time.sleep(RETRY_DELAY)
            else:
                logger.error(
                    "FTP connection failed after %d attempts: %s",
                    MAX_RETRIES, e
                )
    raise last_error


def _list_dir(ftp: ftplib.FTP, path: str) -> list:
    try:
        return ftp.nlst(path)
    except (ftplib.error_perm, TimeoutError, OSError):
        try:
            # Toggle passive mode setting and retry
            ftp.set_pasv(not ftp.passiveserver)
            return ftp.nlst(path)
        except Exception:
            return []



def _parse_filename(filename: str, date_str: str) -> dict | None:
    """
    Parse a record filename like:
        085606_718_STRANGERBABY.txt
    into:
        { employee_id: 718, employee_name: 'STRANGERBABY', timestamp: datetime }
    """
    if not filename.endswith(".txt"):
        return None

    base = filename.replace(".txt", "")
    parts = base.split("_", 2)

    if len(parts) < 3:
        return None

    time_str, emp_id_str, emp_name = parts[0], parts[1], parts[2]

    try:
        hour   = int(time_str[0:2])
        minute = int(time_str[2:4])
        second = int(time_str[4:6])

        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        ts   = datetime(date.year, date.month, date.day, hour, minute, second)

        return {
            "employee_id":   int(emp_id_str),
            "employee_name": emp_name.replace("_", " ").upper(),
            "timestamp":     ts,
        }
    except (ValueError, IndexError) as e:
        logger.warning("Could not parse filename '%s': %s", filename, e)
        return None


def fetch_logs(since: datetime | None = None) -> pd.DataFrame:
    """
    Fetch attendance logs from the Warden face recognition device FTP.
    Retries up to 3 times with 30 second delay if FTP is unavailable.

    Walks: /IdentifyRecords/YYYY-MM-DD/HH/HHMMSS_ID_NAME.txt

    Returns pd.DataFrame with columns:
        employee_id (int), employee_name (str), timestamp (datetime)
    """
    # If since is None, fetch ALL dates from device (no filter)
    fetch_all = since is None

    records = []

    try:
        ftp = _connect_ftp_with_retry()
    except Exception:
        return pd.DataFrame()

    try:
        date_folders = _list_dir(ftp, FTP_BASE)

        for date_path in sorted(date_folders):
            date_str = date_path.split("/")[-1]

            try:
                folder_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            if not fetch_all and folder_date < since.date():
                continue

            hour_folders = _list_dir(ftp, date_path)

            for hour_path in sorted(hour_folders):
                files = _list_dir(ftp, hour_path)

                for file_path in files:
                    filename = file_path.split("/")[-1]
                    record = _parse_filename(filename, date_str)

                    if record is None:
                        continue

                    if not fetch_all and record["timestamp"] < since:
                        continue

                    records.append(record)

        logger.info("Fetched %d raw records from FTP.", len(records))

    except Exception as e:
        logger.exception("Error reading FTP: %s", e)
    finally:
        try:
            ftp.quit()
        except Exception:
            pass

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df = df.drop_duplicates()
    return df