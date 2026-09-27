# ============================================================
#  dashboard.py  –  Executive Attendance Control Center
#  Run with: streamlit run dashboard.py
# ============================================================

import os
import time
import io
from datetime import datetime, date, timedelta
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

import config
import database

# Try loading Plotly for advanced charts
try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="AttendaSync — Control Center",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Executive Custom CSS ──────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
    --ink-primary: #0f172a;
    --ink-secondary: #475569;
    --bg-main: #f8fafc;
    --bg-card: #ffffff;
    --border-color: #e2e8f0;
    --accent-dark: #0f172a;
}

* { font-family: 'Inter', sans-serif; }
.stApp { background: var(--bg-main); color: var(--ink-primary); }
#MainMenu, footer, header { visibility: hidden; }

/* Banner Alerts */
.alert-banner {
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-left: 4px solid #f97316;
    border-radius: 6px;
    padding: 14px 20px;
    margin-bottom: 20px;
    color: #9a3412;
    font-size: 13.5px;
}
.alert-banner b { color: #c2410c; }

/* Header Component */
.dash-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    border-radius: 8px;
    padding: 24px 32px;
    margin-bottom: 22px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 4px 16px -2px rgba(15, 23, 42, 0.12);
}
.dash-title {
    font-family: 'Outfit', sans-serif;
    font-size: 26px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -0.4px;
}
.dash-subtitle {
    font-size: 12.5px; color: #94a3b8; margin-top: 4px;
    font-family: 'IBM Plex Mono', monospace;
    letter-spacing: 0.5px;
}
.dash-date { font-size: 13px; color: #cbd5e1; text-align: right; line-height: 1.5; }
.dash-date b { color: #ffffff; }

/* Status Cards */
.stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 18px 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.stat-number {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 30px; font-weight: 600; line-height: 1.1; margin-bottom: 6px;
}
.stat-label {
    font-size: 11px; font-weight: 700; color: var(--ink-secondary);
    text-transform: uppercase; letter-spacing: 1.1px;
}
.stat-total      { border-left: 4px solid #2563eb; }
.stat-total .stat-number      { color: #1d4ed8; }
.stat-present    { border-left: 4px solid #10b981; }
.stat-present .stat-number    { color: #047857; }
.stat-incomplete { border-left: 4px solid #f59e0b; }
.stat-incomplete .stat-number { color: #b45309; }
.stat-halfday    { border-left: 4px solid #6366f1; }
.stat-halfday .stat-number    { color: #4338ca; }
.stat-absent     { border-left: 4px solid #ef4444; }
.stat-absent .stat-number     { color: #b91c1c; }

/* Section Headings */
.section-title {
    font-size: 12.5px; font-weight: 700; color: var(--ink-secondary);
    text-transform: uppercase; letter-spacing: 1.2px; margin: 24px 0 14px 0;
    display: flex; align-items: center; gap: 12px;
}
.section-title::after { content: ''; flex: 1; height: 1px; background: var(--border-color); }

/* Badges */
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 16px;
    font-size: 12px; font-weight: 600; font-family: 'Inter', sans-serif;
}
.badge-present    { background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }
.badge-late       { background: #fffbebf; color: #b45309; border: 1px solid #fde68a; }
.badge-half       { background: #eef2ff; color: #4338ca; border: 1px solid #c7d2fe; }
.badge-absent     { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
.badge-incomplete { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
.badge-inactive   { background: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }
.badge-active     { background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }
.badge-sunday     { background: #f3e8ff; color: #7e22ce; border: 1px solid #d8b4fe; }
.badge-holiday    { background: #fce7f3; color: #be185d; border: 1px solid #fbcfe8; }
.badge-wfh        { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }
.badge-leave      { background: #ffedd5; color: #c2410c; border: 1px solid #fed7aa; }

/* Table Container */
.custom-table-container {
    max-height: 480px; overflow-y: auto;
    border: 1px solid var(--border-color); border-radius: 8px; background: #ffffff;
}
table.custom-table { width: 100%; border-collapse: collapse; font-size: 13px; }
table.custom-table th {
    position: sticky; top: 0; background: #f8fafc; z-index: 2;
    padding: 12px 16px; text-align: left; font-size: 11px;
    font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px;
    color: #64748b; border-bottom: 1px solid var(--border-color);
}
table.custom-table td {
    padding: 10px 16px; border-bottom: 1px solid var(--border-color);
    font-family: 'IBM Plex Mono', monospace; font-size: 13px; color: #1e293b;
}
table.custom-table tbody tr:hover { background: #f1f5f9; }

/* Heatmap Grid */
.heatmap-cell {
    width: 22px; height: 22px; border-radius: 4px; display: inline-block;
    margin: 2px; vertical-align: middle;
}
.hm-present { background: #10b981; }
.hm-late    { background: #f59e0b; }
.hm-half    { background: #6366f1; }
.hm-absent  { background: #ef4444; }
.hm-sunday  { background: #a855f7; }
.hm-holiday { background: #ec4899; }
.hm-wfh     { background: #0284c7; }
.hm-leave   { background: #f97316; }
.hm-none    { background: #e2e8f0; }
</style>
""", unsafe_allow_html=True)


# ── Data Processing & Loading ─────────────────────────────────
@st.cache_data(ttl=30)
def load_all_records():
    """Load attendance dataset from local SQLite database or Google Sheets."""
    df = database.load_all_attendance()
    if not df.empty:
        return df

    try:
        creds = Credentials.from_service_account_file(config.CREDENTIALS_FILE, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ])
        client = gspread.authorize(creds)
        ws = client.open_by_key(config.SHEET_ID).worksheet("All Records")
        records = ws.get_all_records()
        if records:
            df = pd.DataFrame(records)
            df.columns = df.columns.str.strip()
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
            df = df.dropna(subset=["Date"])
            database.save_attendance_records(df)
            return df
    except Exception as e:
        st.error(f"Data loading warning: {e}")

    return pd.DataFrame()


@st.cache_data(ttl=15)
def load_employee_mapping():
    return database.get_employees()


def status_badge_html(val: str) -> str:
    val_str = str(val)
    if "WFH" in val_str:
        return f'<span class="badge badge-wfh">{val}</span>'
    elif "Leave" in val_str:
        return f'<span class="badge badge-leave">{val}</span>'
    elif "Holiday" in val_str:
        return f'<span class="badge badge-holiday">{val}</span>'
    elif "Sunday" in val_str:
        return f'<span class="badge badge-sunday">{val}</span>'
    elif "Present" in val_str and "Late" in val_str:
        return f'<span class="badge badge-late">{val}</span>'
    elif "Present" in val_str:
        return f'<span class="badge badge-present">{val}</span>'
    elif val_str == "Incomplete":
        return f'<span class="badge badge-incomplete">{val}</span>'
    elif val_str == "Half Day":
        return f'<span class="badge badge-half">{val}</span>'
    elif val_str == "Absent":
        return f'<span class="badge badge-absent">{val}</span>'
    return val_str


def employment_badge_html(emp_status: str) -> str:
    if str(emp_status).lower() == "inactive":
        return '<span class="badge badge-inactive">Inactive</span>'
    return '<span class="badge badge-active">Active</span>'


def render_table(display_df: pd.DataFrame, height: int = 440):
    rows_html = ""
    for _, row in display_df.iterrows():
        cells = []
        for col in display_df.columns:
            val = row[col]
            if col == "Status":
                cells.append(f"<td>{status_badge_html(val)}</td>")
            elif col == "Employment":
                cells.append(f"<td>{employment_badge_html(val)}</td>")
            else:
                cells.append(f"<td>{val if pd.notna(val) else '—'}</td>")
        rows_html += f"<tr>{''.join(cells)}</tr>"

    headers_html = "".join(f"<th>{c}</th>" for c in display_df.columns)

    table_html = f"""
    <div class="custom-table-container" style="max-height:{height}px;">
    <table class="custom-table">
        <thead><tr>{headers_html}</tr></thead>
        <tbody>{rows_html}</tbody>
    </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ── Load Data ─────────────────────────────────────────────────
df = load_all_records()
emp_df = load_employee_mapping()

# Build lookups
emp_status_map = {}
emp_real_name_map = {}
if not emp_df.empty:
    for _, r in emp_df.iterrows():
        code = str(r["employee_name"]).strip()
        st_val = str(r.get("status", "active")).strip().lower()
        r_name = str(r.get("real_name", "")).strip()
        emp_status_map[code] = st_val
        if r_name:
            emp_real_name_map[code] = r_name

unnamed_list = database.get_unnamed_employees()

# ── Top Header ────────────────────────────────────────────────
st.markdown(f"""
<div class="dash-header">
    <div>
        <div class="dash-title">Attendance Control Center</div>
        <div class="dash-subtitle">FACE RECOGNITION SYSTEM · DEVICE IP: {config.DEVICE_IP}</div>
    </div>
    <div class="dash-date">
        <b>{datetime.now().strftime("%A, %d %B %Y")}</b><br>
        System Active · {datetime.now().strftime("%H:%M:%S")}
    </div>
</div>
""", unsafe_allow_html=True)

# ── Auto-Discovery Banner Alert ───────────────────────────────
if unnamed_list:
    unnamed_codes_str = ", ".join([u["employee_name"] for u in unnamed_list[:4]])
    if len(unnamed_list) > 4:
        unnamed_codes_str += f" (+{len(unnamed_list) - 4} more)"
    st.markdown(f"""
    <div class="alert-banner">
        <b>ATTENTION: {len(unnamed_list)} New Employee(s) Auto-Discovered:</b> <code>{unnamed_codes_str}</code>
        <br><span style="font-size:12.5px;">These profiles are logged under device employee codes. Navigate to the <b>Employee Management</b> tab to assign official names.</span>
    </div>
    """, unsafe_allow_html=True)

# ── Navigation Tabs ───────────────────────────────────────────
tabs = st.tabs([
    "Daily View",
    "Employee Search",
    "Payroll Cycle (25th-25th)",
    "Visual Analytics",
    "Attendance Heatmap",
    "Employee & Holiday Management",
])

# ══════════════════════════════════════════════════════════════
# TAB 1: DAILY VIEW
# ══════════════════════════════════════════════════════════════
with tabs[0]:
    col_filter, col_btn = st.columns([3, 1])

    with col_filter:
        if not df.empty:
            min_date = df["Date"].min()
            max_date = df["Date"].max()
        else:
            min_date = max_date = date.today()

        selected_date = st.date_input(
            "Select Date",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
            label_visibility="collapsed",
        )

    with col_btn:
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    show_inactive = st.checkbox("Include inactive employees", value=False, key="daily_inactive_cb")

    if not df.empty:
        day_df = df[df["Date"] == selected_date].copy()
    else:
        day_df = pd.DataFrame()

    if not day_df.empty:
        day_df["_status"] = day_df["Employee ID"].map(emp_status_map).fillna("active")
        if not show_inactive:
            day_df = day_df[day_df["_status"] != "inactive"]

    # Summary Metrics
    st.markdown('<div class="section-title">Summary Metrics</div>', unsafe_allow_html=True)

    total      = len(day_df)
    present    = len(day_df[day_df["Status"].str.contains("Present", na=False)]) if not day_df.empty else 0
    incomplete = len(day_df[day_df["Status"] == "Incomplete"])                    if not day_df.empty else 0
    half_day   = len(day_df[day_df["Status"] == "Half Day"])                      if not day_df.empty else 0
    absent     = len(day_df[day_df["Status"] == "Absent"])                        if not day_df.empty else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f'<div class="stat-card stat-total"><div class="stat-number">{total}</div><div class="stat-label">Total Records</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-card stat-present"><div class="stat-number">{present}</div><div class="stat-label">Present</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="stat-card stat-incomplete"><div class="stat-number">{incomplete}</div><div class="stat-label">Incomplete</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="stat-card stat-halfday"><div class="stat-number">{half_day}</div><div class="stat-label">Half Day</div></div>', unsafe_allow_html=True)
    with c5:
        st.markdown(f'<div class="stat-card stat-absent"><div class="stat-number">{absent}</div><div class="stat-label">Absent</div></div>', unsafe_allow_html=True)

    # Table
    st.markdown(f'<div class="section-title">Daily Records ({selected_date})</div>', unsafe_allow_html=True)

    if day_df.empty:
        st.info(f"No attendance records found for {selected_date}.")
    else:
        cols = ["Employee Name", "Employee ID", "Login Time", "Logout Time", "Total Hours", "Status", "Remarks"]
        if show_inactive:
            day_df["Employment"] = day_df["_status"]
            cols.append("Employment")

        display_df = day_df[cols].sort_values("Employee Name").reset_index(drop=True)
        render_table(display_df, height=440)


# ══════════════════════════════════════════════════════════════
# TAB 2: EMPLOYEE SEARCH & HISTORY
# ══════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="section-title">Employee Directory & History Search</div>', unsafe_allow_html=True)

    search_col, refresh_col = st.columns([3, 1])
    with search_col:
        search_term = st.text_input(
            "Search by employee name or ID",
            placeholder="Type employee name or ID (e.g. EMP-26-0060)...",
            label_visibility="collapsed",
            key="search_term_input"
        )
    with refresh_col:
        if st.button("Refresh Data", key="refresh_search", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    if not search_term.strip():
        st.info("Enter an employee name or employee code above to load full attendance history.")
    elif df.empty:
        st.info("No attendance records available.")
    else:
        term = search_term.strip().lower()
        matches = df[
            df["Employee Name"].astype(str).str.lower().str.contains(term, na=False)
            | df["Employee ID"].astype(str).str.lower().str.contains(term, na=False)
        ].copy()

        if matches.empty:
            st.warning(f"No records match query '{search_term}'.")
        else:
            matched_names = matches["Employee Name"].unique().tolist()
            for emp_name in sorted(matched_names):
                emp_df_sub = matches[matches["Employee Name"] == emp_name].sort_values("Date")
                emp_id = emp_df_sub["Employee ID"].iloc[0]
                emp_employment_status = emp_status_map.get(emp_id, "active")

                total_days      = len(emp_df_sub)
                present_days    = len(emp_df_sub[emp_df_sub["Status"].str.contains("Present", na=False)])
                half_days       = len(emp_df_sub[emp_df_sub["Status"] == "Half Day"])
                absent_days     = len(emp_df_sub[emp_df_sub["Status"] == "Absent"])
                incomplete_days = len(emp_df_sub[emp_df_sub["Status"] == "Incomplete"])

                st.markdown(f"""
                <div class="section-title" style="margin-top:24px;">
                    {emp_name} &nbsp;·&nbsp;
                    <span style="color:var(--ink-secondary); font-family:'IBM Plex Mono',monospace; font-size:12.5px;">{emp_id}</span>
                    &nbsp;{employment_badge_html(emp_employment_status)}
                </div>
                """, unsafe_allow_html=True)

                s1, s2, s3, s4, s5 = st.columns(5)
                with s1:
                    st.markdown(f'<div class="stat-card stat-total"><div class="stat-number">{total_days}</div><div class="stat-label">Total Days</div></div>', unsafe_allow_html=True)
                with s2:
                    st.markdown(f'<div class="stat-card stat-present"><div class="stat-number">{present_days}</div><div class="stat-label">Present</div></div>', unsafe_allow_html=True)
                with s3:
                    st.markdown(f'<div class="stat-card stat-halfday"><div class="stat-number">{half_days}</div><div class="stat-label">Half Day</div></div>', unsafe_allow_html=True)
                with s4:
                    st.markdown(f'<div class="stat-card stat-absent"><div class="stat-number">{absent_days}</div><div class="stat-label">Absent</div></div>', unsafe_allow_html=True)
                with s5:
                    st.markdown(f'<div class="stat-card stat-incomplete"><div class="stat-number">{incomplete_days}</div><div class="stat-label">Incomplete</div></div>', unsafe_allow_html=True)

                history_df = emp_df_sub[[
                    "Date", "Login Time", "Logout Time", "Total Hours", "Status", "Remarks"
                ]].sort_values("Date", ascending=False).reset_index(drop=True)
                history_df["Date"] = history_df["Date"].astype(str)

                render_table(history_df, height=min(380, 60 + 36 * len(history_df)))


# ══════════════════════════════════════════════════════════════
# TAB 3: PAYROLL CYCLE (25th-25th) & REPORT EXPORT
# ══════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="section-title">Payroll Cycle Summary & Report Download (25th to 25th)</div>', unsafe_allow_html=True)
    st.caption("Salary cycles run from the 25th of the previous month to the 25th of the current month.")

    p_start_default, p_end_default = database.get_payroll_cycle_dates()

    c_p1, c_p2, c_pexport = st.columns([2, 2, 2])
    with c_p1:
        p_start_sel = st.date_input("Cycle Start Date", value=p_start_default, key="p_start_input")
    with c_p2:
        p_end_sel = st.date_input("Cycle End Date", value=p_end_default, key="p_end_input")

    payroll_summary = database.get_payroll_summary_df(p_start_sel, p_end_sel)

    with c_pexport:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if not payroll_summary.empty:
            csv_data = payroll_summary.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Payroll Report (CSV)",
                data=csv_data,
                file_name=f"Payroll_Report_{p_start_sel}_to_{p_end_sel}.csv",
                mime="text/csv",
                use_container_width=True
            )

    if payroll_summary.empty:
        st.info("No payroll records found for selected cycle dates.")
    else:
        render_table(payroll_summary, height=440)


# ══════════════════════════════════════════════════════════════
# TAB 4: VISUAL ANALYTICS
# ══════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="section-title">Visual Analytics & Distribution</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No data available for visual analytics.")
    elif not HAS_PLOTLY:
        st.warning("Install `plotly` to render charts: `pip install plotly`")
    else:
        col_c1, col_c2 = st.columns(2)

        with col_c1:
            st.subheader("Attendance Status Distribution")
            status_counts = df["Status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]

            color_map = {
                "Present": "#10b981",
                "Present (Late)": "#f59e0b",
                "Half Day": "#6366f1",
                "Absent": "#ef4444",
                "Incomplete": "#d97706",
                "Sunday": "#a855f7",
                "Holiday": "#ec4899",
                "WFH": "#0284c7",
                "Leave": "#f97316",
            }

            fig_donut = px.pie(
                status_counts,
                values="Count",
                names="Status",
                hole=0.5,
                color="Status",
                color_discrete_map=color_map,
            )
            fig_donut.update_traces(textposition="inside", textinfo="percent+label")
            fig_donut.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=350)
            st.plotly_chart(fig_donut, use_container_width=True)

        with col_c2:
            st.subheader("Daily Turnout Trend")
            daily_turnout = df.groupby(["Date", "Status"]).size().reset_index(name="Count")
            daily_turnout["Date"] = daily_turnout["Date"].astype(str)

            fig_trend = px.line(
                daily_turnout,
                x="Date",
                y="Count",
                color="Status",
                color_discrete_map=color_map,
                markers=True,
            )
            fig_trend.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=350, xaxis_title="Date", yaxis_title="Records")
            st.plotly_chart(fig_trend, use_container_width=True)

        st.markdown('<div class="section-title">Peak Arrival Hours</div>', unsafe_allow_html=True)
        login_df = df[df["Login Time"].astype(str).str.contains(":", na=False)].copy()
        if not login_df.empty:
            login_df["Hour"] = login_df["Login Time"].astype(str).str.split(":").str[0] + ":00"
            hour_counts = login_df["Hour"].value_counts().reset_index()
            hour_counts.columns = ["Hour", "Count"]
            hour_counts = hour_counts.sort_values("Hour")

            fig_bar = px.bar(
                hour_counts,
                x="Hour",
                y="Count",
                labels={"Hour": "Login Hour", "Count": "Frequency"},
                color_discrete_sequence=["#2563eb"],
            )
            fig_bar.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=300)
            st.plotly_chart(fig_bar, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# TAB 5: ATTENDANCE HEATMAP
# ══════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="section-title">Employee Attendance Heatmap Grid</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No attendance data available.")
    else:
        active_names = sorted(df["Employee Name"].unique().tolist())
        selected_emp = st.selectbox("Select Employee", active_names, key="heatmap_emp_select")

        emp_records = df[df["Employee Name"] == selected_emp].copy()
        if emp_records.empty:
            st.warning("No records found for selected employee.")
        else:
            st.markdown("""
            <b>Legend:</b> &nbsp; 
            <span class='heatmap-cell hm-present'></span> Present &nbsp;&nbsp; 
            <span class='heatmap-cell hm-late'></span> Late &nbsp;&nbsp; 
            <span class='heatmap-cell hm-half'></span> Half Day &nbsp;&nbsp; 
            <span class='heatmap-cell hm-absent'></span> Absent &nbsp;&nbsp; 
            <span class='heatmap-cell hm-wfh'></span> WFH &nbsp;&nbsp; 
            <span class='heatmap-cell hm-leave'></span> Leave &nbsp;&nbsp; 
            <span class='heatmap-cell hm-sunday'></span> Sunday &nbsp;&nbsp; 
            <span class='heatmap-cell hm-holiday'></span> Holiday
            """, unsafe_allow_html=True)
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

            date_status = dict(zip(emp_records["Date"].astype(str), emp_records["Status"]))
            
            today_dt = date.today()
            dates_30 = [today_dt - timedelta(days=i) for i in range(29, -1, -1)]

            cells_html = ""
            for d in dates_30:
                d_str = d.isoformat()
                st_val = date_status.get(d_str, "None")
                cls = "hm-none"
                if "WFH" in st_val:
                    cls = "hm-wfh"
                elif "Leave" in st_val:
                    cls = "hm-leave"
                elif "Holiday" in st_val:
                    cls = "hm-holiday"
                elif "Sunday" in st_val or d.weekday() == 6:
                    cls = "hm-sunday"
                elif "Present" in st_val and "Late" in st_val:
                    cls = "hm-late"
                elif "Present" in st_val:
                    cls = "hm-present"
                elif st_val == "Half Day":
                    cls = "hm-half"
                elif st_val == "Absent":
                    cls = "hm-absent"

                cells_html += f'<div title="{d_str}: {st_val}" class="heatmap-cell {cls}"></div>'

            st.markdown(f'<div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:16px;">{cells_html}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TAB 6: EMPLOYEE & HOLIDAY MANAGEMENT (ADMIN TOOLS)
# ══════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown('<div class="section-title">Admin Management & Control Tools</div>', unsafe_allow_html=True)

    # 1. Admin Manual Override (WFH / Leave / Time Correction)
    st.subheader("Admin Attendance Override (WFH, Leaves, Punch Corrections)")
    st.caption("Manually tag Work From Home, Paid Leaves, or punch fixes. Updates both SQLite Database and Google Sheets instantly.")

    col_a1, col_a2, col_a3 = st.columns([2, 2, 2])
    with col_a1:
        emp_code_options = sorted(emp_df["employee_name"].tolist()) if not emp_df.empty else []
        ov_emp = st.selectbox("Select Employee Code", emp_code_options, key="admin_emp_select")
    with col_a2:
        ov_date = st.date_input("Select Date", value=date.today(), key="admin_date_input")
    with col_a3:
        ov_type = st.selectbox("Override Action", [
            "Work From Home (WFH)",
            "Casual Leave (CL)",
            "Sick Leave (SL)",
            "Paid Leave (PL)",
            "Manual Punch Fix (Present)",
            "Mark Absent"
        ], key="admin_type_select")

    col_t1, col_t2, col_r, col_save = st.columns([2, 2, 3, 2])
    with col_t1:
        ov_login = st.text_input("Login Time (HH:MM)", value="09:30" if "Present" in ov_type or "WFH" in ov_type else "—", key="admin_login_in")
    with col_t2:
        ov_logout = st.text_input("Logout Time (HH:MM)", value="18:30" if "Present" in ov_type or "WFH" in ov_type else "—", key="admin_logout_in")
    with col_r:
        ov_remarks = st.text_input("Remarks", value=f"Admin Logged {ov_type}", key="admin_remarks_in")
    with col_save:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("Apply Override", use_container_width=True):
            if "WFH" in ov_type:
                st_val, is_wfh, is_lv, lv_type = "WFH", 1, 0, "WFH"
            elif "Leave" in ov_type:
                lv_type = ov_type.split("(")[-1].replace(")", "").strip()
                st_val, is_wfh, is_lv = f"Leave ({lv_type})", 0, 1
            elif "Present" in ov_type:
                st_val, is_wfh, is_lv, lv_type = "Present", 0, 0, ""
            else:
                st_val, is_wfh, is_lv, lv_type = "Absent", 0, 0, ""

            database.save_admin_override(
                emp_id=ov_emp,
                date_str=ov_date.isoformat(),
                new_status=st_val,
                login_t=ov_login,
                logout_t=ov_logout,
                remarks=ov_remarks,
                is_wfh=is_wfh,
                is_leave=is_lv,
                leave_type=lv_type
            )
            # Trigger sheet sync update
            try:
                ov_df = database.load_all_attendance()
                if not ov_df.empty:
                    import sheets_writer
                    sheets_writer.upload_to_sheet(ov_df)
            except Exception as e:
                st.warning(f"Sheet update warning: {e}")

            st.success(f"Admin override applied for {ov_emp} on {ov_date} -> {st_val}")
            st.cache_data.clear()
            time.sleep(1)
            st.rerun()

    st.divider()

    # 2. Company Holiday Manager
    st.subheader("Company Holiday Manager (Add / Remove Holidays)")
    st.caption("View official company holidays or manage custom holidays.")

    c_hlist, c_hadd = st.columns([3, 3])

    with c_hlist:
        holidays_curr = database.get_holidays()
        if holidays_curr.empty:
            st.info("No holidays defined.")
        else:
            st.markdown("<b>Current Declared Holidays:</b>", unsafe_allow_html=True)
            render_table(holidays_curr, height=260)

    with c_hadd:
        st.markdown("<b>Add or Delete Holiday:</b>", unsafe_allow_html=True)
        h_date_in = st.date_input("Holiday Date", value=date.today(), key="h_date_input")
        h_name_in = st.text_input("Holiday Name", placeholder="e.g. Founder's Day", key="h_name_input")

        ch_btn1, ch_btn2 = st.columns(2)
        with ch_btn1:
            if st.button("Add Holiday", use_container_width=True):
                if h_name_in.strip():
                    database.save_company_holiday(h_date_in.isoformat(), h_name_in.strip())
                    st.success(f"Holiday saved: {h_date_in} - {h_name_in}")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Please enter a holiday name.")
        with ch_btn2:
            if st.button("Delete Holiday", use_container_width=True):
                database.delete_company_holiday(h_date_in.isoformat())
                st.success(f"Deleted holiday on {h_date_in}")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

    st.divider()

    # 3. Employee Real Name & Status Configuration
    st.subheader("Official Name & Employment Status Config")
    emp_table_df = database.get_employees()

    if not emp_table_df.empty:
        c_code, c_name, c_btn = st.columns([2, 3, 1])
        with c_code:
            code_options = sorted(emp_table_df["employee_name"].tolist())
            selected_code = st.selectbox("Employee Device Code", code_options, key="select_code_mgt")

        current_rname = ""
        matching_row = emp_table_df[emp_table_df["employee_name"] == selected_code]
        if not matching_row.empty:
            current_rname = str(matching_row["real_name"].iloc[0]) if pd.notna(matching_row["real_name"].iloc[0]) else ""

        with c_name:
            new_real_name = st.text_input("Official Name", value=current_rname, key="input_rname_mgt")

        with c_btn:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("Save Name", use_container_width=True):
                if new_real_name.strip():
                    database.update_employee_name(selected_code, new_real_name.strip())
                    st.success(f"Updated {selected_code} -> '{new_real_name.strip()}' across DB & sheets.")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()

        render_df = emp_table_df[["employee_id", "employee_name", "real_name", "status"]].copy()
        render_df.columns = ["ID", "Device Code", "Official Name", "Employment"]
        render_table(render_df, height=300)


# ── Footer ────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; color:#94a3b8; font-size:11px; margin-top:40px; font-family:'IBM Plex Mono',monospace;">
    ATTENDASYNC · LOCAL SQLITE & GOOGLE SHEETS SYNC ACTIVE
</div>
""", unsafe_allow_html=True)