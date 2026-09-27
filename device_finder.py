# ============================================================
#  device_finder.py  –  Auto-detect the Warden device's IP
#
#  The Warden device's IP changes daily (DHCP), which used to
#  require manually checking the device screen and editing
#  config.py every morning. This module removes that step:
#
#    1. Try the last-known IP from config.py first (fast path —
#       the IP is often unchanged within the same day).
#    2. If that fails, scan the subnet on the configured FTP port and
#       confirm a real Warden device by logging in with the
#       device credentials configured in .env.
#    3. If found, update config.py's DEVICE_IP line on disk so
#       it reflects the working IP for next time too.
#    4. If nothing is found, fall back to the config.py IP as-is
#       (unchanged behaviour — same retry logic as before).
#
#  Safe to import and call from fetch_logs.py / discover_employees.py
#  without changing how those modules already use DEVICE_IP.
# ============================================================

import ftplib
import ipaddress
import logging
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

import config

logger = logging.getLogger(__name__)

FTP_PORT = config.FTP_PORT
FTP_USER = config.FTP_USER
FTP_PASS = config.FTP_PASS

CONNECT_TIMEOUT = 1.5      # seconds — per-host probe timeout during subnet scan
SCAN_WORKERS    = 60       # parallel probes — fast scan of a /24 in a few seconds

CONFIG_FILE = "config.py"
DEVICE_IP_PATTERN = re.compile(r'^DEVICE_IP\s*=\s*["\'].*["\']', re.MULTILINE)


def _can_login(ip: str, port: int = FTP_PORT, timeout: float = CONNECT_TIMEOUT) -> bool:
    """Return True only if an FTP server at ip:port accepts the known device login."""
    ftp = None
    try:
        ftp = ftplib.FTP()
        ftp.connect(ip, port, timeout=timeout)
        ftp.set_pasv(False)
        ftp.login(FTP_USER, FTP_PASS)
        try:
            ftp.quit()
        except Exception:
            pass
        return True
    except Exception:
        if ftp:
            try:
                ftp.close()
            except Exception:
                pass
        return False



def _local_subnet_hosts(sample_ip: str) -> list:
    """
    Build the list of candidate host IPs to scan, based on the /24 subnet
    of the last-known device IP (e.g. 192.168.1.x -> scan .1 to .254).
    """
    try:
        network = ipaddress.ip_network(f"{sample_ip}/24", strict=False)
        return [str(ip) for ip in network.hosts()]
    except ValueError:
        return []


def _scan_subnet_for_device(sample_ip: str) -> str | None:
    """
    Probe every host in the /24 subnet of sample_ip on FTP_PORT in parallel,
    and return the first IP that accepts the Warden device's FTP login.
    """
    hosts = _local_subnet_hosts(sample_ip)
    if not hosts:
        return None

    logger.info("Scanning %d hosts on subnet for the Warden device (port %d)...",
                len(hosts), FTP_PORT)

    found_ip = None
    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
        futures = {pool.submit(_can_login, ip): ip for ip in hosts}
        for future in as_completed(futures):
            ip = futures[future]
            try:
                if future.result():
                    found_ip = ip
                    break
            except Exception:
                continue

    # Cancel/drain remaining futures without waiting on them
    for future in futures:
        future.cancel()

    return found_ip


def _update_config_ip(new_ip: str) -> None:
    """Rewrite the DEVICE_IP line in config.py on disk to the working IP."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        new_content, count = DEVICE_IP_PATTERN.subn(f'DEVICE_IP = "{new_ip}"', content, count=1)

        if count == 0:
            logger.warning("Could not find DEVICE_IP line in %s — skipped auto-update.", CONFIG_FILE)
            return

        if new_content != content:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(new_content)
            logger.info("config.py updated: DEVICE_IP set to %s", new_ip)
    except Exception:
        logger.exception("Failed to auto-update DEVICE_IP in %s", CONFIG_FILE)


def get_device_ip(known_ip: str) -> tuple[str, bool]:
    """
    Return (ip, confirmed_live) for the Warden device.

    1. If known_ip (from config.py) is still reachable, use it — fast path,
       no scanning, no config.py rewrite needed. confirmed_live=True.
    2. Otherwise scan the subnet for the device by FTP login fingerprint.
       If found and different from known_ip, update config.py and return
       the new IP. confirmed_live=True.
    3. If scanning finds nothing, fall back to known_ip unchanged.
       confirmed_live=False — this tells the caller the device is
       genuinely unreachable right now (we just scanned the whole subnet
       and confirmed nothing is there), so retrying the same dead IP
       multiple times with delays in between is pointless. Callers should
       skip/shorten their own retry loop in this case rather than wasting
       ~30s per retry attempt on an IP already proven unreachable.
    """
    if _can_login(known_ip):
        logger.info("Device confirmed reachable at last-known IP %s.", known_ip)
        return known_ip, True

    logger.warning("Device not reachable at last-known IP %s — scanning subnet...", known_ip)

    discovered_ip = _scan_subnet_for_device(known_ip)

    if discovered_ip is None:
        logger.error(
            "Subnet scan found no Warden device anywhere on the subnet. "
            "Device appears genuinely offline — skipping connection retries "
            "this run. Check that it's powered on and connected to WiFi.",
        )
        return known_ip, False

    if discovered_ip == known_ip:
        return discovered_ip, True

    logger.info("Warden device found at new IP %s (was %s).", discovered_ip, known_ip)
    _update_config_ip(discovered_ip)
    return discovered_ip, True