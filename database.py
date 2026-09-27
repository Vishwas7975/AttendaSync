# ============================================================
#  database.py  –  Local SQLite Storage & Caching Layer
#
#  Provides zero-latency dashboard loading, offline resilience,
#  payroll 25th-to-25th calculation, admin overrides (WFH/Leaves),
#  and instant query performance alongside Google Sheets sync.
# ============================================================

import os
import sqlite3
import pandas as pd
import logging
from datetime import datetime, date, timedelta

import config

logger = logging.getLogger(__name__)

DB_PATH = getattr(config, "DB_FILE", "attendance.db")


def get_connection():
    """Return a connection to the local SQLite database."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables if they do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Employees table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                employee_name TEXT PRIMARY KEY,   -- Employee Code (e.g. EMP-26-0060)
                employee_id INTEGER,              -- Cosmetic ID
                real_name TEXT,                   -- Real human name
                status TEXT DEFAULT 'active',     -- 'active' or 'inactive'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Holidays table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS holidays (
                holiday_date TEXT PRIMARY KEY,    -- YYYY-MM-DD
                name TEXT NOT NULL,               -- Holiday Name
                holiday_type TEXT DEFAULT 'national'
            )
        """)

        # Pre-load official company holidays from config
        holidays_map = getattr(config, "HOLIDAYS_MAP", {})
        for h_date, h_name in holidays_map.items():
            cursor.execute("""
                INSERT INTO holidays (holiday_date, name, holiday_type)
                VALUES (?, ?, 'national')
                ON CONFLICT(holiday_date) DO UPDATE SET name = excluded.name
            """, (h_date, h_name))

        # 3. Attendance records table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                date TEXT,                        -- YYYY-MM-DD
                employee_id TEXT,                 -- Employee Code (e.g. EMP-26-0060)
                employee_name TEXT,               -- Real name or Employee Code
                login_time TEXT,                  -- HH:MM
                logout_time TEXT,                 -- HH:MM or '—'
                total_hours TEXT,                 -- H:MM or 'N/A'
                hours_float REAL DEFAULT 0.0,     -- Floating hours
                overtime_hours REAL DEFAULT 0.0,  -- Overtime hours
                status TEXT,                      -- Present, Present (Late), Half Day, Absent, Incomplete, Sunday, Holiday, WFH, Leave
                remarks TEXT,                     -- Remarks
                is_wfh INTEGER DEFAULT 0,         -- 1 if WFH
                is_leave INTEGER DEFAULT 0,       -- 1 if Paid/Sick Leave
                leave_type TEXT DEFAULT '',       -- CL, SL, PL, WFH
                is_sunday INTEGER DEFAULT 0,      -- 1 if Sunday
                is_holiday INTEGER DEFAULT 0,     -- 1 if Holiday
                holiday_name TEXT DEFAULT '',     -- Name of holiday if any
                admin_override INTEGER DEFAULT 0, -- 1 if manually set by admin
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (date, employee_id)
            )
        """)

        # Add missing columns defensively if database existed previously
        existing_cols = [row[1] for row in cursor.execute("PRAGMA table_info(attendance)").fetchall()]
        new_cols = [
            ("is_wfh", "INTEGER DEFAULT 0"),
            ("is_leave", "INTEGER DEFAULT 0"),
            ("leave_type", "TEXT DEFAULT ''"),
            ("is_sunday", "INTEGER DEFAULT 0"),
            ("is_holiday", "INTEGER DEFAULT 0"),
            ("holiday_name", "TEXT DEFAULT ''"),
            ("admin_override", "INTEGER DEFAULT 0"),
        ]
        for col_name, col_type in new_cols:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE attendance ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass

        conn.commit()
    logger.info("SQLite database initialized at %s", DB_PATH)


def get_holidays() -> pd.DataFrame:
    """Return all company holidays from database."""
    init_db()
    with get_connection() as conn:
        return pd.read_sql_query("SELECT holiday_date, name, holiday_type FROM holidays ORDER BY holiday_date ASC", conn)


def save_company_holiday(h_date: str, h_name: str, h_type: str = "custom"):
    """Add or update a company holiday."""
    init_db()
    h_date = h_date.strip()
    h_name = h_name.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO holidays (holiday_date, name, holiday_type)
            VALUES (?, ?, ?)
            ON CONFLICT(holiday_date) DO UPDATE SET name = excluded.name, holiday_type = excluded.holiday_type
        """, (h_date, h_name, h_type))
        conn.commit()
    logger.info("Saved holiday: %s - %s", h_date, h_name)


def delete_company_holiday(h_date: str):
    """Delete a company holiday."""
    init_db()
    h_date = h_date.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM holidays WHERE holiday_date = ?", (h_date,))
        conn.commit()
    logger.info("Deleted holiday: %s", h_date)


def sync_employees_from_csv(csv_path="employee_map.csv"):
    """Sync employee_map.csv entries into SQLite database."""
    if not os.path.exists(csv_path):
        return

    try:
        df = pd.read_csv(csv_path)
        with get_connection() as conn:
            cursor = conn.cursor()
            for idx, row in df.iterrows():
                code = str(row.get("employee_name", "")).strip()
                if not code:
                    continue
                c_id = int(row.get("employee_id", idx + 1)) if pd.notna(row.get("employee_id")) else (idx + 1)
                r_name = str(row.get("real_name", "")).strip() if pd.notna(row.get("real_name")) else ""
                st = str(row.get("status", "active")).strip().lower() if pd.notna(row.get("status")) else "active"

                cursor.execute("""
                    INSERT INTO employees (employee_name, employee_id, real_name, status)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(employee_name) DO UPDATE SET
                        real_name = CASE WHEN excluded.real_name != '' THEN excluded.real_name ELSE employees.real_name END,
                        status = excluded.status
                """, (code, c_id, r_name, st))
            conn.commit()
    except Exception as e:
        logger.warning("Error syncing employee_map.csv to DB: %s", e)


def sync_employees_to_csv(csv_path="employee_map.csv"):
    """Export current SQLite employees table back to employee_map.csv."""
    try:
        with get_connection() as conn:
            df = pd.read_sql_query("SELECT employee_id, employee_name, real_name, status FROM employees ORDER BY employee_name", conn)
        
        df["employee_id"] = range(1, len(df) + 1)
        df.to_csv(csv_path, index=False)
        logger.info("Exported updated employee map to %s", csv_path)
    except Exception as e:
        logger.error("Failed writing employee_map.csv: %s", e)


def get_employees() -> pd.DataFrame:
    """Return all employees from local DB as DataFrame."""
    init_db()
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM employees ORDER BY employee_name", conn)


def get_unnamed_employees() -> list[dict]:
    """Return employees where real_name is missing or empty."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT employee_name, status FROM employees WHERE real_name IS NULL OR trim(real_name) = ''")
        return [dict(row) for row in cursor.fetchall()]


def update_employee_name(vai_code: str, real_name: str):
    """Update real name for a employee code in DB and propagate across historical records."""
    init_db()
    vai_code = vai_code.strip().upper()
    real_name = real_name.strip()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO employees (employee_name, real_name, status)
            VALUES (?, ?, 'active')
            ON CONFLICT(employee_name) DO UPDATE SET real_name = excluded.real_name
        """, (vai_code, real_name))

        cursor.execute("""
            UPDATE attendance
            SET employee_name = ?
            WHERE employee_id = ?
        """, (real_name if real_name else vai_code, vai_code))

        conn.commit()

    sync_employees_to_csv()
    logger.info("Updated real name for %s -> '%s'", vai_code, real_name)


def update_employee_status(vai_code: str, new_status: str):
    """Update active/inactive status for an employee."""
    init_db()
    vai_code = vai_code.strip().upper()
    new_status = new_status.strip().lower()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE employees SET status = ? WHERE employee_name = ?", (new_status, vai_code))
        conn.commit()

    sync_employees_to_csv()
    logger.info("Updated status for %s -> '%s'", vai_code, new_status)


def save_attendance_records(records_df: pd.DataFrame):
    """Save or update processed attendance records in SQLite DB, preserving admin overrides."""
    if records_df.empty:
        return

    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        for _, row in records_df.iterrows():
            d_val = str(row["Date"]).strip()
            emp_id = str(row["Employee ID"]).strip()
            emp_name = str(row["Employee Name"]).strip()
            login = str(row["Login Time"]).strip()
            logout = str(row["Logout Time"]).strip()
            total_h = str(row["Total Hours"]).strip()
            st = str(row["Status"]).strip()
            rem = str(row.get("Remarks", "")).strip()

            is_wfh = int(row.get("is_wfh", 1 if "WFH" in st else 0))
            is_leave = int(row.get("is_leave", 1 if "Leave" in st else 0))
            leave_type = str(row.get("leave_type", ""))
            is_sunday = int(row.get("is_sunday", 1 if "Sunday" in st else 0))
            is_holiday = int(row.get("is_holiday", 1 if "Holiday" in st else 0))
            holiday_name = str(row.get("holiday_name", ""))
            admin_override = int(row.get("admin_override", 0))

            hours_float = 0.0
            if total_h and total_h != "N/A" and ":" in total_h:
                try:
                    parts = total_h.split(":")
                    hours_float = int(parts[0]) + int(parts[1]) / 60.0
                except (ValueError, IndexError):
                    hours_float = 0.0

            overtime = max(0.0, hours_float - config.OVERTIME_THRESHOLD) if hours_float >= config.OVERTIME_THRESHOLD else 0.0

            # Preserve admin override if row was manually modified previously
            cursor.execute("""
                INSERT INTO attendance (
                    date, employee_id, employee_name, login_time, logout_time,
                    total_hours, hours_float, overtime_hours, status, remarks,
                    is_wfh, is_leave, leave_type, is_sunday, is_holiday, holiday_name, admin_override, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(date, employee_id) DO UPDATE SET
                    employee_name = excluded.employee_name,
                    login_time = CASE WHEN attendance.admin_override = 1 THEN attendance.login_time ELSE excluded.login_time END,
                    logout_time = CASE WHEN attendance.admin_override = 1 THEN attendance.logout_time ELSE excluded.logout_time END,
                    total_hours = CASE WHEN attendance.admin_override = 1 THEN attendance.total_hours ELSE excluded.total_hours END,
                    hours_float = CASE WHEN attendance.admin_override = 1 THEN attendance.hours_float ELSE excluded.hours_float END,
                    overtime_hours = CASE WHEN attendance.admin_override = 1 THEN attendance.overtime_hours ELSE excluded.overtime_hours END,
                    status = CASE WHEN attendance.admin_override = 1 THEN attendance.status ELSE excluded.status END,
                    remarks = CASE WHEN attendance.admin_override = 1 THEN attendance.remarks ELSE excluded.remarks END,
                    updated_at = CURRENT_TIMESTAMP
            """, (d_val, emp_id, emp_name, login, logout, total_h, hours_float, overtime, st, rem,
                  is_wfh, is_leave, leave_type, is_sunday, is_holiday, holiday_name, admin_override))

        conn.commit()


def save_admin_override(emp_id: str, date_str: str, new_status: str, login_t: str = "09:30", logout_t: str = "18:30", remarks: str = "Admin Override", is_wfh: int = 0, is_leave: int = 0, leave_type: str = ""):
    """Save an admin manual override (WFH, Leave, Punch Correction) in DB."""
    init_db()
    emp_id = emp_id.strip().upper()
    date_str = date_str.strip()

    # Determine real_name
    emp_df = get_employees()
    emp_name = emp_id
    if not emp_df.empty:
        match = emp_df[emp_df["employee_name"] == emp_id]
        if not match.empty and pd.notna(match["real_name"].iloc[0]) and str(match["real_name"].iloc[0]).strip():
            emp_name = str(match["real_name"].iloc[0]).strip()

    hours_float = 0.0
    total_hours = "N/A"
    if login_t != "—" and logout_t != "—" and ":" in login_t and ":" in logout_t:
        try:
            h1, m1 = map(int, login_t.split(":"))
            h2, m2 = map(int, logout_t.split(":"))
            dt1 = datetime(2000, 1, 1, h1, m1)
            dt2 = datetime(2000, 1, 1, h2, m2)
            delta = (dt2 - dt1).total_seconds() / 3600.0
            if delta > 0:
                hours_float = delta
                h = int(delta)
                m = int((delta - h) * 60)
                total_hours = f"{h}:{m:02d}"
        except Exception:
            pass

    overtime = max(0.0, hours_float - config.OVERTIME_THRESHOLD) if hours_float >= config.OVERTIME_THRESHOLD else 0.0

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO attendance (
                date, employee_id, employee_name, login_time, logout_time,
                total_hours, hours_float, overtime_hours, status, remarks,
                is_wfh, is_leave, leave_type, admin_override, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(date, employee_id) DO UPDATE SET
                employee_name = excluded.employee_name,
                login_time = excluded.login_time,
                logout_time = excluded.logout_time,
                total_hours = excluded.total_hours,
                hours_float = excluded.hours_float,
                overtime_hours = excluded.overtime_hours,
                status = excluded.status,
                remarks = excluded.remarks,
                is_wfh = excluded.is_wfh,
                is_leave = excluded.is_leave,
                leave_type = excluded.leave_type,
                admin_override = 1,
                updated_at = CURRENT_TIMESTAMP
        """, (date_str, emp_id, emp_name, login_t, logout_t, total_hours, hours_float, overtime, new_status, remarks, is_wfh, is_leave, leave_type))
        conn.commit()
    logger.info("Admin override saved for %s on %s -> %s", emp_id, date_str, new_status)


def get_payroll_cycle_dates(ref_date: date | None = None) -> tuple[date, date]:
    """
    Calculate 25th-to-25th payroll cycle range for ref_date (default today).
    If ref_date day >= 25, cycle is 25th of current month to 25th of next month.
    If ref_date day < 25, cycle is 25th of prev month to 25th of current month.
    """
    if ref_date is None:
        ref_date = date.today()

    start_day = getattr(config, "PAYROLL_CYCLE_START_DAY", 25)

    if ref_date.day >= start_day:
        start_d = date(ref_date.year, ref_date.month, start_day)
        # Next month 25th
        if ref_date.month == 12:
            end_d = date(ref_date.year + 1, 1, start_day)
        else:
            end_d = date(ref_date.year, ref_date.month + 1, start_day)
    else:
        end_d = date(ref_date.year, ref_date.month, start_day)
        # Prev month 25th
        if ref_date.month == 1:
            start_d = date(ref_date.year - 1, 12, start_day)
        else:
            start_d = date(ref_date.year, ref_date.month - 1, start_day)

    return start_d, end_d


def load_all_attendance() -> pd.DataFrame:
    """Load all attendance records from SQLite database."""
    init_db()
    with get_connection() as conn:
        df = pd.read_sql_query("""
            SELECT 
                date as Date,
                employee_id as "Employee ID",
                employee_name as "Employee Name",
                login_time as "Login Time",
                logout_time as "Logout Time",
                total_hours as "Total Hours",
                hours_float,
                overtime_hours as "Overtime Hours",
                status as Status,
                remarks as Remarks,
                is_wfh, is_leave, leave_type, is_sunday, is_holiday, holiday_name, admin_override
            FROM attendance
            ORDER BY employee_name, date ASC
        """, conn)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    return df


def get_payroll_summary_df(start_date: date, end_date: date) -> pd.DataFrame:
    """Calculate payroll summary statistics for 25th-to-25th date range per employee."""
    df = load_all_attendance()
    if df.empty:
        return pd.DataFrame()

    sub = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)].copy()
    if sub.empty:
        return pd.DataFrame()

    emp_df = get_employees()
    active_codes = set(emp_df[emp_df["status"] != "inactive"]["employee_name"].tolist()) if not emp_df.empty else set(sub["Employee ID"].unique())

    sub = sub[sub["Employee ID"].isin(active_codes)]

    results = []
    for (emp_id, emp_name), group in sub.groupby(["Employee ID", "Employee Name"]):
        total_records = len(group)
        present_count = len(group[group["Status"].str.contains("Present", na=False)])
        late_count    = len(group[group["Status"].str.contains("Late", na=False)])
        half_count    = len(group[group["Status"] == "Half Day"])
        absent_count  = len(group[group["Status"] == "Absent"])
        wfh_count     = len(group[(group["Status"].str.contains("WFH", na=False)) | (group["is_wfh"] == 1)])
        leave_count   = len(group[(group["Status"].str.contains("Leave", na=False)) | (group["is_leave"] == 1)])
        sunday_count  = len(group[(group["Status"].str.contains("Sunday", na=False)) | (group["is_sunday"] == 1)])
        holiday_count = len(group[(group["Status"].str.contains("Holiday", na=False)) | (group["is_holiday"] == 1)])
        
        tot_hrs = group["hours_float"].sum()
        tot_ot  = group["Overtime Hours"].sum()

        results.append({
            "Employee ID": emp_id,
            "Employee Name": emp_name,
            "Total Days Logged": total_records,
            "Present": present_count,
            "Late": late_count,
            "Half Day": half_count,
            "Absent": absent_count,
            "WFH": wfh_count,
            "Leaves": leave_count,
            "Sundays/Holidays": sunday_count + holiday_count,
            "Total Hours": round(tot_hrs, 2),
            "Overtime Hours": round(tot_ot, 2),
        })

    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df = res_df.sort_values("Employee Name").reset_index(drop=True)
    return res_df
