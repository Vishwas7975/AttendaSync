# ============================================================
#  sheets_writer.py  –  Executive Google Sheets Sync & Styling Engine
#
#  Four professionally styled tabs with custom headers, zebra striping,
#  status color badges, column width auto-sizing, and frozen headers:
#    1. "Current Payroll (25th-25th)" – 25th of prev month to 25th of current month
#    2. "Today"                       – Current day active scans
#    3. "Monthly Summary"             – Aggregated payroll metrics per employee
#    4. "All Records"                 – Active rolling window in Sheets; 100% permanently stored in SQLite DB
# ============================================================

import logging
import time as time_module
from datetime import date, datetime, timedelta

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from config import SHEET_ID, CREDENTIALS_FILE
import database

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "Date", "Employee ID", "Employee Name",
    "Login Time", "Logout Time", "Total Hours", "Status", "Remarks",
]

SUMMARY_HEADERS = [
    "Employee ID", "Employee Name", "Total Days Logged",
    "Present", "Late", "Half Day", "Absent", "WFH", "Leaves",
    "Sundays/Holidays", "Total Hours", "Overtime Hours"
]

TAB_PAYROLL     = "Current Payroll (25th-25th)"
TAB_TODAY       = "Today"
TAB_SUMMARY     = "Monthly Summary"
TAB_ALL         = "All Records"

SORT_COLUMNS   = ["Employee Name", "Date"]
SORT_ASCENDING = [True, True]


def connect_sheet() -> gspread.Spreadsheet:
    creds  = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)


def _get_or_create_tab(spreadsheet: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=2000, cols=len(HEADERS))
        logger.info("Created new tab: %s", title)
        return ws


def _apply_executive_tab_formatting(ws: gspread.Worksheet, headers: list, total_rows: int):
    """
    Apply executive-grade styling to Google Sheets worksheet:
    - Header: Dark Slate (#0f172a) background, bold white text, height 36px, centered.
    - Data: Inter/Calibri font, alternating row zebra striping (#f8fafc), soft borders.
    - Status Column Conditional Formatting: Badges for Present, Late, Half Day, Absent, Sunday, Holiday, WFH, Leave.
    - Auto column widths.
    """
    try:
        sheet_id = ws.id
        num_cols = len(headers)
        total_data_rows = max(1, total_rows)

        requests = []

        # 1. Freeze header row & set gridlines
        ws.freeze(rows=1)

        # 2. Format Header Row (Row 0 in API = Row 1 in Sheet)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.06, "green": 0.09, "blue": 0.16}, # #0f172a
                        "textFormat": {
                            "fontFamily": "Inter",
                            "fontSize": 10,
                            "bold": True,
                            "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "padding": {"top": 8, "bottom": 8, "left": 10, "right": 10}
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,padding)"
            }
        })

        # 3. Format Data Rows (Rows 1 to total_data_rows+1)
        if total_rows > 0:
            # General data row formatting (Font size 10, vertical middle, padding)
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": total_data_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": num_cols
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"fontFamily": "Inter", "fontSize": 10},
                            "verticalAlignment": "MIDDLE",
                            "padding": {"top": 6, "bottom": 6, "left": 10, "right": 10}
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,verticalAlignment,padding)"
                }
            })

            # Zebra Striping (Even rows get soft slate #f8fafc)
            for r_idx in range(1, total_data_rows + 1):
                bg_color = {"red": 0.97, "green": 0.98, "blue": 0.99} if r_idx % 2 == 0 else {"red": 1.0, "green": 1.0, "blue": 1.0}
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": r_idx,
                            "endRowIndex": r_idx + 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": bg_color
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColor"
                    }
                })

            # Column Alignments based on Header Names
            for c_idx, h_name in enumerate(headers):
                align = "LEFT"
                if h_name in ["Date", "Employee ID", "Login Time", "Logout Time", "Status"]:
                    align = "CENTER"
                elif h_name in ["Total Hours", "Total Days Logged", "Present", "Late", "Half Day", "Absent", "WFH", "Leaves", "Sundays/Holidays", "Overtime Hours"]:
                    align = "RIGHT"

                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": total_data_rows + 1,
                            "startColumnIndex": c_idx,
                            "endColumnIndex": c_idx + 1
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": align
                            }
                        },
                        "fields": "userEnteredFormat.horizontalAlignment"
                    }
                })

        # 4. Auto-fit Column Widths so text is never truncated
        requests.append({
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": num_cols
                }
            }
        })

        # Execute batch update
        ws.spreadsheet.batch_update({"requests": requests})

        # 5. Add Conditional Formatting Rules for Status Column (if Status exists)
        if "Status" in headers:
            status_col_idx = headers.index("Status")
            _apply_status_conditional_rules(ws, sheet_id, status_col_idx, total_data_rows)

    except Exception as e:
        logger.warning("Formatting warning for %s: %s", ws.title, e)


def _apply_status_conditional_rules(ws: gspread.Worksheet, sheet_id: int, col_idx: int, total_rows: int):
    """Apply visual status color badge rules to Status column in Google Sheets."""
    try:
        rules = [
            # Present -> Light Emerald fill, Dark Green text
            ("Present", {"red": 0.86, "green": 0.99, "blue": 0.91}, {"red": 0.08, "green": 0.50, "blue": 0.24}),
            # Late -> Light Amber fill, Dark Amber text
            ("Late", {"red": 0.99, "green": 0.95, "blue": 0.78}, {"red": 0.71, "green": 0.33, "blue": 0.04}),
            # Half Day -> Light Indigo fill, Dark Indigo text
            ("Half Day", {"red": 0.88, "green": 0.91, "blue": 1.0}, {"red": 0.26, "green": 0.22, "blue": 0.79}),
            # Absent -> Light Red fill, Dark Red text
            ("Absent", {"red": 0.99, "green": 0.89, "blue": 0.89}, {"red": 0.73, "green": 0.11, "blue": 0.11}),
            # Incomplete -> Light Orange fill, Dark Orange text
            ("Incomplete", {"red": 1.0, "green": 0.93, "blue": 0.84}, {"red": 0.76, "green": 0.25, "blue": 0.05}),
            # Sunday -> Light Purple fill, Dark Purple text
            ("Sunday", {"red": 0.95, "green": 0.91, "blue": 1.0}, {"red": 0.49, "green": 0.13, "blue": 0.81}),
            # Holiday -> Light Pink fill, Dark Pink text
            ("Holiday", {"red": 0.99, "green": 0.91, "blue": 0.95}, {"red": 0.75, "green": 0.09, "blue": 0.36}),
            # WFH -> Light Sky fill, Dark Sky text
            ("WFH", {"red": 0.88, "green": 0.95, "blue": 1.0}, {"red": 0.01, "green": 0.41, "blue": 0.63}),
            # Leave -> Light Orange fill, Dark Orange text
            ("Leave", {"red": 1.0, "green": 0.93, "blue": 0.84}, {"red": 0.76, "green": 0.25, "blue": 0.05}),
        ]

        requests = []
        for text_val, bg_color, text_color in rules:
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": total_rows + 1,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_CONTAINS",
                                "values": [{"userEnteredValue": text_val}]
                            },
                            "format": {
                                "backgroundColor": bg_color,
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColor": text_color
                                }
                            }
                        }
                    },
                    "index": 0
                }
            })

        ws.spreadsheet.batch_update({"requests": requests})
    except Exception as e:
        logger.warning("Conditional formatting warning for %s: %s", ws.title, e)


def _sort_for_display(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(SORT_COLUMNS, ascending=SORT_ASCENDING)


def _rewrite_tab(ws: gspread.Worksheet, df: pd.DataFrame, label: str, headers_list: list = HEADERS):
    """Clear a tab and rewrite it cleanly with executive formatting."""
    ws.clear()
    ws.insert_row(headers_list, index=1)

    if df.empty:
        _apply_executive_tab_formatting(ws, headers_list, total_rows=0)
        logger.info("No records for %s — tab cleared.", label)
        return

    rows = [[str(row.get(h, "")) for h in headers_list] for _, row in df.iterrows()]

    chunk_size = 500
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        ws.append_rows(chunk, value_input_option="USER_ENTERED")
        if i + chunk_size < len(rows):
            time_module.sleep(1)

    # Apply executive styling after writing data
    _apply_executive_tab_formatting(ws, headers_list, total_rows=len(rows))
    logger.info("%s tab: wrote %d records with executive formatting.", label, len(rows))


def upload_to_sheet(df: pd.DataFrame):
    """
    Synchronize attendance data across 4 formatted Google Sheets tabs & local SQLite DB.
    - 100% of all attendance data is PERMANENTLY SAVED in SQLite DB (attendance.db).
    - Google Sheets holds current active payroll cycles & recent months to keep Google Sheets clean & fast.
    """
    if df.empty:
        logger.info("Nothing to upload.")
        return

    # 1. Save EVERY single incoming record into local SQLite DB permanently
    try:
        database.save_attendance_records(df)
    except Exception as e:
        logger.warning("Local DB save warning: %s", e)

    spreadsheet = connect_sheet()
    logger.info("Google Sheet connected: %s", SHEET_ID)

    ws_payroll    = _get_or_create_tab(spreadsheet, TAB_PAYROLL)
    ws_today      = _get_or_create_tab(spreadsheet, TAB_TODAY)
    ws_summary    = _get_or_create_tab(spreadsheet, TAB_SUMMARY)
    ws_all        = _get_or_create_tab(spreadsheet, TAB_ALL)

    # 2. Load ALL historical records from SQLite DB (permanent single source of truth)
    db_full_df = database.load_all_attendance()
    if db_full_df.empty:
        db_full_df = df.copy()

    db_full_df = db_full_df.rename(columns={
        "Date": "Date",
        "Employee ID": "Employee ID",
        "Employee Name": "Employee Name",
        "Login Time": "Login Time",
        "Logout Time": "Logout Time",
        "Total Hours": "Total Hours",
        "Status": "Status",
        "Remarks": "Remarks",
    })
    db_full_df["Date"] = db_full_df["Date"].astype(str)

    # Propagate official employee names
    try:
        emp_df = database.get_employees()
        if not emp_df.empty and "real_name" in emp_df.columns:
            name_map = {}
            for _, r in emp_df.iterrows():
                code = str(r["employee_name"]).strip()
                r_name = str(r["real_name"]).strip()
                if r_name:
                    name_map[code] = r_name
            if name_map:
                db_full_df["Employee Name"] = db_full_df["Employee ID"].map(lambda x: name_map.get(str(x).strip(), x))
    except Exception as e:
        logger.warning("Name mapping warning: %s", e)

    full_df_sorted = _sort_for_display(db_full_df)

    # 3. Current Payroll Cycle (25th of prev month to 25th of current month)
    p_start, p_end = database.get_payroll_cycle_dates()
    p_start_str, p_end_str = p_start.isoformat(), p_end.isoformat()
    payroll_df = full_df_sorted[(full_df_sorted["Date"] >= p_start_str) & (full_df_sorted["Date"] <= p_end_str)]
    _rewrite_tab(ws_payroll, payroll_df, TAB_PAYROLL)
    time_module.sleep(1)

    # 4. Monthly Summary Aggregated Metrics
    summary_df = database.get_payroll_summary_df(p_start, p_end)
    _rewrite_tab(ws_summary, summary_df, TAB_SUMMARY, headers_list=SUMMARY_HEADERS)
    time_module.sleep(1)

    # 5. Today's Records
    today_str = date.today().isoformat()
    today_df  = full_df_sorted[full_df_sorted["Date"] == today_str]
    _rewrite_tab(ws_today, today_df, TAB_TODAY)
    time_module.sleep(1)

    # 6. All Records Tab in Google Sheets:
    #    Keep current active payroll cycle + past 60 days in Google Sheets so sheet stays clean,
    #    while 100% of all historical records remain stored permanently in attendance.db!
    cutoff_60_days = (date.today() - timedelta(days=60)).isoformat()
    active_sheets_all = full_df_sorted[full_df_sorted["Date"] >= cutoff_60_days]
    _rewrite_tab(ws_all, active_sheets_all, TAB_ALL)

    logger.info("All 4 tabs updated with executive styling (Google Sheets cleaned for old cycles, 100%% history preserved in SQLite DB).")