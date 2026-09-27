# AttendaSync

**Automated Face-Recognition Attendance & Payroll System**

AttendaSync polls a biometric face-recognition device over FTP, caches every punch locally in SQLite, applies configurable payroll and attendance rules (late cutoffs, overtime, holidays, Sundays), keeps a live Google Sheet in sync, and gives admins a Streamlit dashboard for daily review, search, payroll export, and manual overrides.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-ff4b4b)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

---

## About This Project

AttendaSync was built to replace a fully manual, error-prone attendance and payroll process with an end-to-end automated pipeline — from raw biometric device data to a payroll-ready report, with zero manual data entry. It's a real, in-production system (data anonymized for this repo) that demonstrates device/hardware integration, third-party API sync, local data caching, business-rule automation, and a full interactive dashboard — built solo, end to end.

---

## Table of Contents

- [Skills Demonstrated](#skills-demonstrated)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
- [Usage](#usage)
- [24/7 Automated Sync (Windows)](#247-automated-sync-windows)
- [Security & Privacy](#security--privacy)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

---


## Skills Demonstrated

- **Hardware/device integration** — FTP-based polling of a biometric device, with auto-discovery when its IP changes on the network
- **Third-party API integration** — Google Sheets API (service-account auth) with formatted, multi-tab sync
- **Data engineering** — local SQLite caching layer, deduplication, rolling-window incremental sync
- **Business rule automation** — configurable payroll cycles, overtime/late-cutoff logic, holiday and weekend handling
- **Full-stack dashboarding** — Streamlit + Plotly interactive UI with search, analytics, CSV export, and admin workflows
- **Secure configuration practices** — all secrets and PII externalized via `.env` / gitignored files (see [Security & Privacy](#security--privacy))
- **Task automation** — Windows Task Scheduler integration for unattended background sync

---

## Features

**Zero-dropped-punch device sync**
New employees enrolled on the physical device are auto-detected on the fly; every punch is written to SQLite and `employee_map.csv` with no manual step. HR can assign a real name to a device code directly from the dashboard, which retroactively updates all historical records everywhere.

**Configurable payroll cycle & report export**
Salary calculations run over a configurable cycle window (default: 25th to 25th). Per employee, it aggregates present/late/half/absent days, WFH, paid/sick leave, Sunday and holiday work, total hours, and overtime — exportable as a one-click CSV/Excel payroll report.

**Automatic Sunday & holiday tracking**
Sundays are computed automatically from the calendar; company holidays are pre-loaded and editable from the dashboard without touching code.

**Admin overrides**
HR/Admin can tag WFH, Casual/Sick/Paid Leave, or fix a missed punch directly from the UI — changes sync instantly to both the local database and Google Sheets.

**Local-first performance**
All records are cached in SQLite for near-instant dashboard queries, with a rolling lookback sync window that automatically catches late or backlogged device uploads.

**Google Sheets integration**
Keeps four formatted tabs in sync: current payroll cycle, today's live log, a monthly summary, and the full historical archive.

**Executive dashboard (`dashboard.py`)**
A Streamlit control center with daily views, search, Plotly analytics (status breakdown, daily turnout trend, peak arrival hours), and a 30-day attendance heatmap per employee.

---

## Architecture

```
┌───────────────────────────────┐
│   Face Biometrics Device      │  (FTP / IP auto-discovery across subnet)
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│     main.py Sync Engine       │  (routine sync / rolling lookback / --full-sync mode)
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ process_logs.py Logic Engine  │  (late cutoff, overtime, Sunday/holiday tagging,
└──────────────┬────────────────┘   auto-registration of new employee codes)
               │
       ┌───────┴────────┐
       ▼                ▼
┌───────────────┐ ┌───────────────────┐
│ attendance.db │ │   Google Sheets   │  (Current Payroll, Today,
│ (SQLite cache)│ │  (cloud sync)     │   Monthly Summary, All Records)
└───────┬───────┘ └───────────────────┘
        │
        ▼
┌───────────────────────────────┐
│  dashboard.py Control Center  │  (Streamlit UI: daily view, search, payroll export,
└───────────────────────────────┘   analytics, heatmaps, admin overrides)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Local storage | SQLite |
| Cloud sync | Google Sheets API (`gspread`, `google-auth`) |
| Dashboard | Streamlit + Plotly |
| Device link | FTP (`ftplib`) |
| Config | `python-dotenv` |
| Scheduling | Windows Task Scheduler (`schtasks`) / `schedule` |

---

## Project Structure

```
attendance_system/
├── main.py                    # Entry point & sync engine
├── config.py                  # Central config — secrets loaded from .env
├── database.py                # SQLite storage layer
├── device_finder.py           # Auto-resolves device IP on the local subnet
├── fetch_logs.py               # Device FTP client (Passive/Active fallback)
├── process_logs.py            # Attendance logic: cutoffs, overtime, holidays
├── sheets_writer.py           # Google Sheets sync & formatting
├── dashboard.py                # Streamlit web control center
├── notifications.py           # Optional Telegram alerts
├── discover_employees.py      # Standalone device-scanning utility
├── manage_employees.py        # CLI employee management
├── employee_map.example.csv   # Template — copy to employee_map.csv (gitignored)
├── credentials.example.json   # Template — copy to credentials.json (gitignored)
├── .env.example                # Template — copy to .env (gitignored)
├── requirements.txt
├── setup_scheduler.bat        # Windows Task Scheduler helper
└── README.md
```

`employee_map.csv`, `credentials.json`, `.env`, `attendance.db`, and `logs/` are all gitignored — they hold real credentials or personal data and are generated locally on first run. See [Security & Privacy](#security--privacy).

---

## Getting Started

### Prerequisites

- Python 3.10+
- A compatible biometric FTP-based attendance device on your local network
- A Google Cloud service account with access to a target Google Sheet

### Installation

```bash
git clone https://github.com/<your-username>/AttendaSync.git
cd AttendaSync
pip install -r requirements.txt
```

### Configuration

Nothing sensitive ships with this repo — you provide your own values locally:

1. **Environment variables** — copy `.env.example` to `.env` and fill in your device's `FTP_USER`, `FTP_PASS`, `DEVICE_IP`, `FTP_PORT`, and your Google `SHEET_ID`.
2. **Google service account** — in Google Cloud Console → IAM & Admin → Service Accounts, create a key, share your target Sheet with its `client_email`, and save the downloaded JSON as `credentials.json` in the project root (see `credentials.example.json` for the expected shape).
3. **Employee map** — `employee_map.csv` is generated locally by `discover_employees.py` / `main.py` and holds real employee names. It's gitignored; see `employee_map.example.csv` for the column layout.

Other behavior (payroll cycle start day, late cutoff time, full/half-day hour thresholds, holiday list, lookback window) is configured directly in `config.py`.

---

## Usage

**Launch the dashboard**
```bash
streamlit run dashboard.py
```
Then open `http://localhost:8501`.

**Run a routine sync** (rolling lookback window)
```bash
python main.py
```

**Run a full historical sync** (fetches every date folder on the device)
```bash
python main.py --full-sync
```

**CLI employee management**
```bash
python manage_employees.py --list-active
python manage_employees.py --list-dormant
```

---

## 24/7 Automated Sync (Windows)

1. Open `setup_scheduler.bat` and set `PROJECT_DIR` and `PYTHON_EXE` to match your machine.
2. Right-click it and choose **Run as Administrator**.
3. Verify the task was created:
   ```cmd
   schtasks /query /tn "AttendanceAutoSync"
   ```

---

## Security & Privacy

This repository is designed to be safe to publish:

- **No secrets are committed.** FTP login, device IP/port, and the Google Sheet ID are all read from a local `.env` file (gitignored). See `.env.example` for the required keys.
- **No credentials are committed.** The Google service-account key belongs in `credentials.json` (gitignored); `credentials.example.json` shows the expected structure only, with placeholder values.
- **No personal data is committed.** `employee_map.csv` (real names) and `attendance.db` (attendance history) are both gitignored and generated locally on first run. `employee_map.example.csv` shows the expected format with placeholder names.
- **No logs are committed.** The `logs/` directory is gitignored.

If you fork or clone this project, keep that boundary intact — don't commit your own `.env`, `credentials.json`, `employee_map.csv`, or `attendance.db`.

---

## Troubleshooting

- **Device IP changes**: `device_finder.py` automatically scans the local subnet on the configured FTP port to re-locate the device and update `config.py` if its IP changes (e.g. after a DHCP renewal).
- **FTP firewall timeouts**: `fetch_logs.py` automatically falls back between Passive (`PASV`) and Active FTP modes to avoid NAT firewall connection drops.
- **Log inspection**: Sync activity is logged under `logs/` (gitignored — created on first run).

---

## Contributing

Issues and pull requests are welcome. If you're proposing a significant change, please open an issue first to discuss what you'd like to change.

---

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for details.


## Author

**Vishwas S**
Full-Stack Developer | Data Analyst

- GitHub: [github.com/Vishwas7975](https://github.com/Vishwas7975)
- LinkedIn: [linkedin.com/in/vishwas-s-48205327a](https://www.linkedin.com/in/vishwas-s-48205327a)