# ============================================================
#  manage_employees.py  –  Activate / deactivate employees and
#                           detect dormant ones automatically
#
#  Background:
#  The Warden device keeps a face enrolled even after someone
#  leaves, so old/former employees can keep generating scan
#  records forever. employee_map.csv now has a 'status' column
#  (active / inactive). process_logs.py skips inactive employees
#  when building NEW attendance records — their old history in
#  All Records is untouched, they just stop accumulating new rows.
#
#  This script is how you manage that status column without
#  hand-editing the CSV every time.
#
#  Usage:
#    python manage_employees.py --list
#    python manage_employees.py --list-active
#    python manage_employees.py --list-inactive
#    python manage_employees.py --list-dormant [DAYS]      (default 7)
#    python manage_employees.py --deactivate EMP-26-0069
#    python manage_employees.py --activate EMP-26-0069
#    python manage_employees.py --set-name EMP-26-0069 "Full Name Here"
# ============================================================

import argparse
import csv
import sys
from datetime import datetime, date, timedelta

EMP_MAP_FILE = "employee_map.csv"
FIELDNAMES = ["employee_id", "employee_name", "real_name", "status"]


def _load_employees() -> list[dict]:
    try:
        with open(EMP_MAP_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"ERROR: {EMP_MAP_FILE} not found in the current directory.")
        sys.exit(1)

    # Tolerate an older employee_map.csv that doesn't have 'status' yet —
    # treat everyone as active until explicitly changed.
    for row in rows:
        if "status" not in row or not row.get("status"):
            row["status"] = "active"
    return rows


def _save_employees(rows: list[dict]) -> None:
    with open(EMP_MAP_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    try:
        import database
        database.sync_employees_from_csv()
    except Exception:
        pass



def _find_employee(rows: list[dict], code: str) -> dict | None:
    code_upper = code.strip().upper()
    for row in rows:
        if row["employee_name"].strip().upper() == code_upper:
            return row
    return None


def cmd_list(rows: list[dict], status_filter: str | None = None):
    filtered = rows
    if status_filter:
        filtered = [r for r in rows if r["status"].lower().strip() == status_filter]

    if not filtered:
        print(f"No employees found{f' with status={status_filter}' if status_filter else ''}.")
        return

    print(f"{'Code':<18} {'Name':<30} {'Status'}")
    print("-" * 60)
    for r in sorted(filtered, key=lambda r: r["employee_name"]):
        name = r["real_name"].strip() or "(unnamed)"
        print(f"{r['employee_name']:<18} {name:<30} {r['status']}")
    print(f"\nTotal: {len(filtered)}")


def cmd_set_status(rows: list[dict], code: str, new_status: str):
    emp = _find_employee(rows, code)
    if emp is None:
        print(f"ERROR: No employee found with code '{code}'.")
        sys.exit(1)

    old_status = emp["status"]
    emp["status"] = new_status

    _save_employees(rows)

    name = emp["real_name"].strip() or "(unnamed)"
    print(f"Updated {emp['employee_name']} ({name}): {old_status} -> {new_status}")


def cmd_set_name(rows: list[dict], code: str, new_name: str):
    emp = _find_employee(rows, code)
    if emp is None:
        print(f"ERROR: No employee found with code '{code}'.")
        sys.exit(1)

    old_name = emp["real_name"].strip() or "(unnamed)"
    emp["real_name"] = new_name

    _save_employees(rows)
    print(f"Updated {emp['employee_name']}: name '{old_name}' -> '{new_name}'")


def cmd_list_dormant(rows: list[dict], days: int):
    """
    Find currently-active employees who haven't scanned in `days`+ days,
    by checking the All Records tab in Google Sheets. These are
    CANDIDATES for deactivation — review before deactivating, since
    someone on long leave would also show up here.
    """
    try:
        import sheets_writer
    except ImportError:
        print("ERROR: Could not import sheets_writer.py — run this from the project folder.")
        sys.exit(1)

    print("Connecting to Google Sheet...")
    try:
        spreadsheet = sheets_writer.connect_sheet()
        ws = spreadsheet.worksheet(sheets_writer.TAB_ALL)
        records = ws.get_all_records()
    except Exception as e:
        print(f"ERROR: Could not read All Records tab: {e}")
        sys.exit(1)

    if not records:
        print("All Records tab is empty — nothing to check.")
        return

    last_seen: dict[str, str] = {}
    for rec in records:
        code = str(rec.get("Employee ID", "")).strip().upper()
        d = str(rec.get("Date", "")).strip()
        if not code or not d:
            continue
        if code not in last_seen or d > last_seen[code]:
            last_seen[code] = d

    cutoff = date.today() - timedelta(days=days)
    active_rows = [r for r in rows if r["status"].lower().strip() != "inactive"]

    dormant = []
    for r in active_rows:
        code = r["employee_name"].strip().upper()
        last_date_str = last_seen.get(code)
        if last_date_str is None:
            dormant.append((r, "never scanned"))
            continue
        try:
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if last_date < cutoff:
            dormant.append((r, f"last scan {last_date_str}"))

    if not dormant:
        print(f"No active employees are dormant ({days}+ days with no scan). Good — nothing to clean up.")
        return

    print(f"\nActive employees with no scan in {days}+ days (candidates for --deactivate):")
    print(f"{'Code':<18} {'Name':<30} {'Last activity'}")
    print("-" * 65)
    for r, reason in sorted(dormant, key=lambda x: x[0]["employee_name"]):
        name = r["real_name"].strip() or "(unnamed)"
        print(f"{r['employee_name']:<18} {name:<30} {reason}")
    print(f"\nTotal dormant: {len(dormant)}")
    print("\nReview this list before deactivating — someone on long leave would also show up here.")
    print("To deactivate one: python manage_employees.py --deactivate <CODE>")


def main():
    parser = argparse.ArgumentParser(description="Manage employee_map.csv status and names.")
    parser.add_argument("--list", action="store_true", help="List all employees.")
    parser.add_argument("--list-active", action="store_true", help="List only active employees.")
    parser.add_argument("--list-inactive", action="store_true", help="List only inactive employees.")
    parser.add_argument("--list-dormant", nargs="?", const=7, type=int, metavar="DAYS",
                         help="List active employees with no scan in DAYS+ days (default 7).")
    parser.add_argument("--deactivate", metavar="CODE", help="Mark an employee inactive, e.g. EMP-26-0069")
    parser.add_argument("--activate", metavar="CODE", help="Mark an employee active, e.g. EMP-26-0069")
    parser.add_argument("--set-name", nargs=2, metavar=("CODE", "NAME"), help="Set an employee's real name.")

    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    rows = _load_employees()

    if args.list:
        cmd_list(rows)
    if args.list_active:
        cmd_list(rows, status_filter="active")
    if args.list_inactive:
        cmd_list(rows, status_filter="inactive")
    if args.list_dormant is not None:
        cmd_list_dormant(rows, args.list_dormant)
    if args.deactivate:
        cmd_set_status(rows, args.deactivate, "inactive")
    if args.activate:
        cmd_set_status(rows, args.activate, "active")
    if args.set_name:
        code, name = args.set_name
        cmd_set_name(rows, code, name)


if __name__ == "__main__":
    main()