# ============================================================
#  config.py  –  Central configuration for AttendaSync
#
#  All secrets (FTP login, device IP, Sheet ID, Telegram token)
#  are loaded from a local .env file — never hardcoded here.
#  Copy .env.example to .env and fill in your real values.
#
#  Nothing below has a real-looking default: if .env is missing
#  a value, it comes through as an empty string / 0, and the
#  app will tell you to set it rather than silently using a
#  placeholder that looks like a real network address.
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()  # reads .env in the project root (gitignored)

# ── Face Recognition Device (FTP) ────────────────────────────
DEVICE_IP   = os.getenv("DEVICE_IP", "")               # set in .env — last-known device IP; auto-updated on discovery
FTP_PORT    = int(os.getenv("FTP_PORT", "0") or 0)      # set in .env — the FTP port your device listens on
FTP_USER    = os.getenv("FTP_USER", "")
FTP_PASS    = os.getenv("FTP_PASS", "")

DEVICE_PORT = int(os.getenv("DEVICE_HTTP_PORT", "80"))  # only used by the optional HTTP endpoints below

# Common API endpoints used by ZKTeco / HikVision / similar devices
# The fetcher will try each one in order and use the first that responds.
DEVICE_ENDPOINTS = [
    f"http://{DEVICE_IP}:{DEVICE_PORT}/iclock/getrequest",   # ZKTeco push SDK
    f"http://{DEVICE_IP}:{DEVICE_PORT}/api/v1/attendance",   # generic REST
    f"http://{DEVICE_IP}:{DEVICE_PORT}/att/log",             # alternate path
]

# If your device requires HTTP Basic Auth, set these; otherwise leave blank.
DEVICE_USERNAME = ""
DEVICE_PASSWORD = ""

# How many seconds to wait for the device to respond
DEVICE_TIMEOUT  = 10

# ── Google Sheets ─────────────────────────────────────────────
SHEET_ID          = os.getenv("SHEET_ID", "")
SHEET_NAME        = "Attendance"
CREDENTIALS_FILE  = "credentials.json"

# ── Local Database Caching ────────────────────────────────────
DB_FILE = "attendance.db"               # SQLite database file for local caching

# ── Payroll & Attendance Rules ───────────────────────────────
PAYROLL_CYCLE_START_DAY     = 25        # Payroll cycle runs from 25th of prev month to 25th of current month
DEFAULT_FETCH_LOOKBACK_DAYS = 30        # Routine 5-min sync lookback window (days)
LATE_CUTOFF_TIME            = "09:45"   # Login after 9:45 AM marked as Present (Late)
FULL_DAY_HOURS              = 9.0       # Mandatory hours for Full Day
HALF_DAY_HOURS              = 4.5       # Mandatory hours for Half Day
OVERTIME_THRESHOLD          = 9.0       # Hours exceeding this count as Overtime

# ── Pre-Loaded Official Company Holidays ──────────────────────
HOLIDAYS_MAP = {
    "2026-01-01": "New Year's Day",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-04-03": "Good Friday",
    "2026-05-01": "Labour Day",
    "2026-06-26": "Muharram / Ashura",
    "2026-08-15": "Independence Day",
    "2026-09-09": "Ganesh Chaturthi",
    "2026-10-02": "Gandhi Jayanti",
    "2026-10-09": "Dussehra",
    "2026-10-29": "Diwali",
    "2026-10-30": "Diwali (Laxmi Puja)",
    "2026-12-25": "Christmas Day",
}

# ── Notifications (Optional) ──────────────────────────────────
# Set ENABLE_TELEGRAM = True and fill bot token/chat ID to enable Telegram daily alerts
ENABLE_TELEGRAM    = os.getenv("ENABLE_TELEGRAM", "False") == "True"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")


# ── Scheduling ────────────────────────────────────────────────
FETCH_INTERVAL_MINUTES = 5        # how often to poll the device

# ── Timezone ──────────────────────────────────────────────────
TIMEZONE = "Asia/Kolkata"         # change to your local timezone if needed
