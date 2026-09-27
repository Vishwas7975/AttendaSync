# ============================================================
#  discover_employees.py
#  Scans ALL files on the device FTP, finds every unique
#  employee employee code, and updates employee_map.csv
#
#  IMPORTANT: The device assigns a different RANDOM numeric ID
#  to the same person on every scan (see README / process_logs.py).
#  So we must key discovery by the employee code (e.g. EMP-26-0060),
#  never by the numeric ID in the filename — keying by numeric ID
#  causes massive false "new employee" counts because one person's
#  scans land under dozens of different numeric IDs.
#
#  Run once:
#      python discover_employees.py
# ============================================================

import ftplib
import csv
import os

import config
from device_finder import get_device_ip

# ── FTP config (IP read from config.py — update IP only there) ─
# NOTE: FTP_HOST is resolved fresh each run via get_device_ip(), which
# auto-detects the device if it's moved to a new IP and falls back to
# config.DEVICE_IP if detection fails.
# Credentials themselves live in .env (see config.py), never hardcoded here.
FTP_PORT = config.FTP_PORT
FTP_USER = config.FTP_USER
FTP_PASS = config.FTP_PASS
FTP_BASE = "/IdentifyRecords"

OUTPUT_CSV = "employee_map.csv"

# Known non-employee / unregistered-face placeholder names some
# devices write when a face isn't matched to a registered profile.
IGNORE_NAMES = {"STRANGERBABY", "UNKNOWN", "STRANGER"}


def connect_ftp():
    host, confirmed_live = get_device_ip(config.DEVICE_IP)
    if not confirmed_live:
        print(
            f"WARNING: Could not confirm the device anywhere on the subnet. "
            f"Attempting {host} anyway, but this will likely fail — "
            f"check that the device is powered on and connected to WiFi."
        )
    ftp = ftplib.FTP()
    ftp.connect(host, FTP_PORT, timeout=30)
    ftp.set_pasv(False)
    ftp.login(FTP_USER, FTP_PASS)
    print(f"Connected to FTP {host}:{FTP_PORT}")
    return ftp


def list_dir(ftp, path):
    try:
        return ftp.nlst(path)
    except ftplib.error_perm:
        return []


def parse_filename(filename):
    """
    Parse: 091909_128_EMP-26-0060.txt
    Returns the employee code (employee_name), e.g. 'EMP-26-0060'.
    The leading numeric ID is IGNORED — it's random per scan,
    not a stable employee identifier.
    """
    if not filename.endswith(".txt"):
        return None
    base = filename.replace(".txt", "")
    parts = base.split("_", 2)
    if len(parts) < 3:
        return None
    try:
        int(parts[1])  # validate the ID field is numeric, but discard it
    except ValueError:
        return None
    emp_code = parts[2].replace("_", " ").upper().strip()
    return emp_code


def discover_all_employees():
    ftp = connect_ftp()

    # employee code -> scan count (just for visibility)
    employees = {}

    date_folders = list_dir(ftp, FTP_BASE)
    print(f"Found {len(date_folders)} date folders on device\n")

    for date_path in sorted(date_folders):
        hour_folders = list_dir(ftp, date_path)
        for hour_path in sorted(hour_folders):
            files = list_dir(ftp, hour_path)
            for file_path in files:
                filename = file_path.split("/")[-1]
                emp_code = parse_filename(filename)
                if emp_code and emp_code not in IGNORE_NAMES:
                    employees[emp_code] = employees.get(emp_code, 0) + 1

    ftp.quit()
    return employees


def save_employee_map(employees):
    """
    employees: dict of employee code -> scan count

    employee_map.csv layout:
        employee_id    -> simple sequential row number (cosmetic)
        employee_name  -> employee code (device-side identifier, stable)
        real_name      -> human name, filled in manually
    """
    # Load existing CSV — preserve employee code -> real_name mapping
    existing_real_names = {}   # vai_code -> real_name
    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                vai_code = (row.get("employee_name") or "").strip().upper()
                if vai_code:
                    existing_real_names[vai_code] = row.get("real_name", "")

    all_codes = set(existing_real_names.keys()) | set(employees.keys())

    new_codes = sorted(c for c in all_codes if c not in existing_real_names)
    new_count = len(new_codes)

    # Write updated CSV with fresh sequential employee_id
    sorted_codes = sorted(all_codes)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["employee_id", "employee_name", "real_name"])
        for i, vai_code in enumerate(sorted_codes, start=1):
            real_name = existing_real_names.get(vai_code, "")
            writer.writerow([i, vai_code, real_name])

    return sorted_codes, new_count, new_codes


def main():
    print("=" * 55)
    print("  Employee Discovery Script")
    print("  Scanning all FTP records...")
    print("=" * 55)

    employees = discover_all_employees()

    print(f"\nFound {len(employees)} unique employee codes on device:")
    for vai_code in sorted(employees.keys()):
        print(f"  {vai_code}  ({employees[vai_code]} scans)")

    all_codes, new_count, new_codes = save_employee_map(employees)

    print(f"\n✓ employee_map.csv updated")
    print(f"  Total employees : {len(all_codes)}")
    print(f"  New codes added : {new_count}")

    if new_codes:
        print(f"\n  ⚠ Fill real_name in employee_map.csv for these new entries:")
        for vai_code in new_codes:
            print(f"    {vai_code}")

    print(f"\nNow open employee_map.csv, fill real_name for new employees,")
    print(f"then run: python main.py")
    print("=" * 55)


if __name__ == "__main__":
    main()