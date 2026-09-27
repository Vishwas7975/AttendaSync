# ============================================================
#  notifications.py  –  Alerts & Notification System
#
#  Supports optional Telegram / Webhook daily attendance recap
#  and device connectivity warnings.
# ============================================================

import logging
import requests
import config

logger = logging.getLogger(__name__)


def send_telegram_message(message: str) -> bool:
    """Send a formatted Markdown message via Telegram bot."""
    if not getattr(config, "ENABLE_TELEGRAM", False):
        return False

    token = getattr(config, "TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = getattr(config, "TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        logger.warning("Telegram enabled but bot token or chat ID is missing.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code == 200:
            logger.info("Telegram message sent successfully.")
            return True
        else:
            logger.error("Telegram API error (%d): %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Failed sending Telegram alert: %s", e)
        return False


def send_daily_summary_notification(total: int, present: int, late: int, incomplete: int, absent: int, date_str: str):
    """Send daily attendance summary notification."""
    msg = (
        f"📊 *Attendance Summary for {date_str}*\n\n"
        f"• *Total Recorded:* {total}\n"
        f"• *Present (On Time):* {present - late}\n"
        f"• *Present (Late):* {late}\n"
        f"• *Incomplete Scans:* {incomplete}\n"
        f"• *Absent / Short Hours:* {absent}\n\n"
        f"_Synced automatically via Face Recognition System_"
    )
    send_telegram_message(msg)


def send_device_offline_alert(last_ip: str):
    """Send device offline warning alert."""
    msg = (
        f"⚠️ *Device Offline Warning*\n\n"
        f"The Warden Face Recognition device is not reachable at last-known IP `{last_ip}` "
        f"and auto-discovery could not locate it on the subnet.\n\n"
        f"Please verify device power and WiFi connection."
    )
    send_telegram_message(msg)
