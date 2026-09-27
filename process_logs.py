# ============================================================
#  process_logs.py  –  Attendance logic & Shift Rules
#
#  Groups by employee_name + date (Employee Code).
#  Calculates Login, Logout, Working Hours, Overtime, Status,
#  Sunday Recognition, Company Holidays, and Auto-Registration.
# ============================================================

import os
import logging
import pandas as pd
from datetime import datetime, time, timedelta, date

import config
import database

logger = logging.getLogger(__name__)

LATE_CUTOFF   = time(9, 45)   # after 9:45 AM → Present (Late)
FULL_DAY_HRS  = getattr(config, "FULL_DAY_HOURS", 9.0)
HALF_DAY_HRS  = getattr(config, "HALF_DAY_HOURS", 4.5)


def _fmt_time(t: time) -> str:
    """Format time as HH:MM."""
    return t.strftime("%H:%M")


def _total_hours_str(login_t: time, logout_t: time) -> str:
    """Return working hours as 'H:MM' string."""
    dummy = datetime(2000, 1, 1)
    delta = datetime.combine(dummy, logout_t) - datetime.combine(dummy, login_t)
    if delta.total_seconds() < 0:
        delta += timedelta(hours=24)
    total_seconds = int(delta.total_seconds())
    h, rem = divmod(total_seconds, 3600)
    m = rem // 60
    return f"{h}:{m:02d}"


def _total_hours_float(login_t: time, logout_t: time) -> float:
    """Return working hours as float."""
    dummy = datetime(2000, 1, 1)
    delta = datetime.combine(dummy, logout_t) - datetime.combine(dummy, login_t)
    if delta.total_seconds() < 0:
        delta += timedelta(hours=24)
    return delta.total_seconds() / 3600


def _derive_status(login_t: time, logout_t: time | None, hours: float, is_sunday: bool, is_holiday: bool, holiday_name: str) -> tuple[str, str]:
    """
    Determine attendance status and remarks, incorporating Sunday/Holiday recognition.
    """
    if is_holiday:
        if logout_t and login_t != logout_t:
            return f"Holiday Work ({holiday_name})", "Punched on Holiday"
        return f"Holiday ({holiday_name})", "Company Holiday"

    if is_sunday:
        if logout_t and login_t != logout_t:
            return "Sunday Work", "Punched on Sunday"
        return "Sunday", "Weekly Off"

    if logout_t is None or login_t == logout_t:
        return "Incomplete", "Missing logout scan"

    late_tag = " (Late)" if login_t > LATE_CUTOFF else ""

    if hours >= FULL_DAY_HRS:
        return f"Present{late_tag}", ""
    elif hours >= HALF_DAY_HRS:
        return "Half Day", ""
    else:
        return "Absent", "Under minimum working hours"


def process_logs(df: pd.DataFrame, emp_map: pd.DataFrame) -> pd.DataFrame:
    """
    Transform raw device logs into structured attendance records.
    Auto-registers unseen employee codes and recognizes Sundays/Holidays.
    """
    if df.empty:
        logger.info("No raw logs to process.")
        return pd.DataFrame()

    df = df.copy()

    # 1. Normalise timestamps
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time

    # 2. Normalise employee name from device
    df["device_name"] = df["employee_name"].str.upper().str.strip()

    # 3. Build name lookup & Auto-discover new employee codes
    emp_map = emp_map.copy()
    emp_map["lookup_name"] = emp_map["employee_name"].str.upper().str.strip()

    known_codes = set(emp_map["lookup_name"].tolist())
    incoming_codes = set(df["device_name"].dropna().unique())

    ignore_placeholder_names = {"STRANGERBABY", "UNKNOWN", "STRANGER"}
    new_codes = (incoming_codes - known_codes) - ignore_placeholder_names

    if new_codes:
        logger.info("Auto-registering %d new employee employee code(s): %s", len(new_codes), sorted(list(new_codes)))
        for new_code in sorted(list(new_codes)):
            database.update_employee_name(new_code, "")
        
        if os.path.exists("employee_map.csv"):
            emp_map = pd.read_csv("employee_map.csv")
            emp_map["lookup_name"] = emp_map["employee_name"].str.upper().str.strip()

    # Filter out inactive employees for new runs
    if "status" in emp_map.columns:
        active_map = emp_map[emp_map["status"].astype(str).str.lower().str.strip() != "inactive"]
        emp_map = active_map

    name_map = dict(zip(emp_map["lookup_name"], emp_map["employee_name"]))

    has_real_name = "real_name" in emp_map.columns
    if has_real_name:
        real_name_df = emp_map[emp_map["real_name"].notna() & (emp_map["real_name"].astype(str).str.strip() != "")]
        real_name_map = real_name_df.drop_duplicates(subset=["lookup_name"]).set_index("lookup_name")["real_name"].to_dict()
    else:
        real_name_map = {}

    df = df[df["device_name"].isin(name_map)]
    if df.empty:
        logger.warning("No active employees found after name matching.")
        return pd.DataFrame()

    df["employee_name"] = df["device_name"].map(name_map)

    # 4. Remove duplicate timestamps
    df = df.drop_duplicates(subset=["employee_name", "timestamp"])
    df_sorted = df.sort_values(["employee_name", "timestamp"])

    # Load holidays lookup
    holidays_df = database.get_holidays()
    holidays_dict = {}
    if not holidays_df.empty:
        holidays_dict = dict(zip(holidays_df["holiday_date"].astype(str), holidays_df["name"]))

    config_holidays = getattr(config, "HOLIDAYS_MAP", {})
    for h_d, h_n in config_holidays.items():
        if h_d not in holidays_dict:
            holidays_dict[h_d] = h_n

    grouped = df_sorted.groupby(["employee_name", "date"])
    results = []

    for (emp_name, date_val), group in grouped:
        scans = group["time"].tolist()

        login_t  = scans[0]
        logout_t = scans[-1] if len(scans) > 1 else None

        if logout_t and login_t != logout_t:
            hours       = _total_hours_float(login_t, logout_t)
            total_hours = _total_hours_str(login_t, logout_t)
        else:
            hours       = 0.0
            total_hours = "N/A"

        date_str = str(date_val)
        is_sunday = date_val.weekday() == 6
        is_holiday = date_str in holidays_dict
        holiday_name = holidays_dict.get(date_str, "")

        status, remarks = _derive_status(login_t, logout_t, hours, is_sunday, is_holiday, holiday_name)
        display_name = real_name_map.get(emp_name.upper().strip(), emp_name)

        results.append({
            "Date":          date_str,
            "Employee ID":   emp_name,
            "Employee Name": display_name,
            "Login Time":    _fmt_time(login_t),
            "Logout Time":   _fmt_time(logout_t) if logout_t else "—",
            "Total Hours":   total_hours,
            "Status":        status,
            "Remarks":       remarks,
            "is_wfh":        1 if "WFH" in status else 0,
            "is_leave":      1 if "Leave" in status else 0,
            "is_sunday":     1 if is_sunday else 0,
            "is_holiday":    1 if is_holiday else 0,
            "holiday_name":  holiday_name,
        })

    result_df = pd.DataFrame(results)
    logger.info("Processed %d attendance records.", len(result_df))
    return result_df