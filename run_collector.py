"""
projects/06_live_relative_strength_and_heatmap_dashboard/run_collector.py
---------------------------------------------------------------------------
Autonomous 24/7 Launcher for Service 1: Relative Strength Collector Daemon.
Supports both single-device (local) and multi-device (headless Linux server) operation:
- Starts automatically at 09:14:00 AM on trading days.
- Streams live SmartStream 2.0 ticks and flushes 1-minute OHLC bars to MySQL.
- Cleanly flushes buffers and disconnects WebSocket at 15:30:30 PM.
- Sleeps automatically on weekends (Saturday/Sunday) & official holidays.
- Supports special trading sessions (e.g. Diwali Muhurat) and Admin Maintenance Mode.
- No sudo privileges required: runs smoothly in tmux, screen, or nohup.
"""

import argparse
from datetime import datetime
import os
from pathlib import Path
import signal
import sys
import time
from typing import Optional
import warnings

# Suppress Python 3.8 CryptographyDeprecationWarning and other third-party deprecation warnings
warnings.filterwarnings("ignore")

try:
    import _bootstrap_path
    from _bootstrap_path import REPO_ROOT
except ImportError:
    REPO_ROOT = Path(__file__).resolve().parent

from collector_daemon import RelativeStrengthCollector
from config import (
    DAYS_TO_KEEP,
    get_angelone_credentials,
    get_host_ip_diagnostics,
)
from market_scheduler import MarketScheduler

try:
    from core.logger import configure_logger, get_logger
except ImportError:
    from utils.logger import configure_logger, get_logger

logger = get_logger("relative_strength.collector")

# Global flag for clean exit
_TERMINATION_REQUESTED = False


def _signal_handler(sig, frame):
    global _TERMINATION_REQUESTED
    sig_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
    print(f"\n[-] Received {sig_name}. Requesting graceful shutdown...")
    _TERMINATION_REQUESTED = True


def print_status_banner(scheduler: MarketScheduler) -> None:
    """Displays human-readable market timing, calendar, and host IP diagnostics."""
    now = datetime.now()
    is_open, status_msg, cur_start, cur_end = scheduler.is_market_open_now(now)
    next_start, next_end, next_desc = scheduler.get_next_trading_session(now)
    time_to_next = (next_start - now).total_seconds()

    net_info = get_host_ip_diagnostics()
    lan_ip = net_info.get("primary_lan_ip", "127.0.0.1")
    ts_ip = net_info.get("tailscale_ip")
    all_ips = net_info.get("all_ips", [lan_ip])

    creds = get_angelone_credentials()
    client_code = creds.get("client_code", "")

    print("\n" + "=" * 78)
    print("  ANGEL ONE - RELATIVE STRENGTH COLLECTOR (SERVICE 1) STATUS")
    print("=" * 78)
    print(f"  Current Local Time : {now.strftime('%Y-%m-%d %H:%M:%S (%A)')}")
    print(f"  Market Status      : {'OPEN' if is_open else 'CLOSED'} ({status_msg})")
    print(f"  Maintenance Mode   : {'ACTIVE (Paused)' if scheduler.is_maintenance_mode else 'OFF'}")
    print(f"  Data Retention     : {DAYS_TO_KEEP} Days")
    print("-" * 78)
    if is_open:
        time_left = (cur_end - now).total_seconds() if cur_end else 0
        print(f"  Active Session Ends: {cur_end.strftime('%H:%M:%S') if cur_end else 'N/A'}")
        print(f"  Time Remaining     : {scheduler.format_countdown(time_left)}")
    else:
        print(f"  Next Session Date  : {next_start.strftime('%Y-%m-%d (%A)')}")
        print(f"  Session Window     : {next_start.strftime('%H:%M:%S')} - {next_end.strftime('%H:%M:%S')}")
        print(f"  Session Type       : {next_desc}")
        print(f"  Countdown to Start : {scheduler.format_countdown(time_to_next)}")
    print("-" * 78)
    print("  HOST IP ADDRESSES FOR CLIENT DASHBOARD (connection_config.json):")
    print(f"    • Office LAN IP    : {lan_ip}  (Use if Laptop and PC are on same office network)")
    if ts_ip:
        print(f"    • Tailscale Mesh IP: {ts_ip}  (Encrypted direct connection anywhere)")
    else:
        print("    • Tailscale Mesh IP: Not Detected (Optional: install Tailscale for remote access)")
    if len(all_ips) > 1:
        other_ips = [ip for ip in all_ips if ip != lan_ip and ip != ts_ip]
        if other_ips:
            print(f"    • Other Host IPs   : {', '.join(other_ips)}")
    print("-" * 78)
    print("  ANGEL ONE ACCOUNT & STATIC IP STATUS:")
    if client_code:
        print(f"    • Client Code / ID : {client_code} (Active in credentials.json / USER_CREDENTIALS.json)")
    else:
        print("    • Client Code / ID : [!] NOT CONFIGURED!")
        print("                         Please copy credentials.example.json -> credentials.json")
        print("                         and set your Angel One api_key, client_code, password, totp_secret.")
    print("    • Static IP Note   : PC (LAN) and Laptop (Wi-Fi) share the same Office Router")
    print("                         outbound static IP. No changes needed in Angel One portal.")
    print("-" * 78)
    print("  [Tip] '--status' is a diagnostic check tool. To start the live collector daemon,")
    print("        run: python3 run_collector.py (without the --status flag)")
    print("=" * 78 + "\n")


def run_single_session_blocking(collector: RelativeStrengthCollector, max_duration_sec: Optional[float] = None) -> None:
    """Runs data collection until collector stops or max duration / termination."""
    global _TERMINATION_REQUESTED
    collector.start()
    start_time = time.time()

    try:
        while collector.running and not _TERMINATION_REQUESTED:
            time.sleep(1.0)
            if max_duration_sec and (time.time() - start_time) >= max_duration_sec:
                logger.info(f"Session window duration limit ({max_duration_sec}s) reached.")
                break
    finally:
        collector.stop()


def run_scheduled_daemon(scheduler: MarketScheduler) -> None:
    """
    24/7 autonomous loop: sleeps when market is closed, wakes up before market open,
    runs the collector during trading hours, and shuts down cleanly after market close.
    """
    global _TERMINATION_REQUESTED
    logger.info("Starting Autonomous 24/7 Market Collector Daemon...")
    print("\n[*] Starting Autonomous 24/7 Market Collector Daemon.")
    print("    Press Ctrl+C to terminate cleanly at any time.")

    last_countdown_log = 0.0

    while not _TERMINATION_REQUESTED:
        now = datetime.now()
        is_open, status_msg, cur_start, cur_end = scheduler.is_market_open_now(now)

        if is_open:
            logger.info(f"Market is OPEN ({status_msg}). Starting Relative Strength Collector...")
            print(f"\n[+] [{now.strftime('%H:%M:%S')}] Market is OPEN! Launching collector...")

            active_collector = RelativeStrengthCollector()
            active_collector.start()

            # Ingest ticks until session end or termination
            while active_collector.running and not _TERMINATION_REQUESTED:
                # Sleep in short slices for responsive shutdown
                for _ in range(5):
                    if _TERMINATION_REQUESTED:
                        break
                    time.sleep(1.0)

                if _TERMINATION_REQUESTED:
                    break

                # Check if market has closed
                loop_now = datetime.now()
                is_still_open, _, _, _ = scheduler.is_market_open_now(loop_now)
                if not is_still_open:
                    print(f"\n[-] [{loop_now.strftime('%H:%M:%S')}] Trading session has concluded.")
                    logger.info("Trading session window closed. Finalizing collector...")
                    break

            # Cleanly stop collector and flush buffers
            active_collector.stop()
            print(f"[*] [{datetime.now().strftime('%H:%M:%S')}] Collector stopped and flushed. Ready for next session.")

        else:
            # Market is closed (pre-market, post-market, night, weekend, holiday, maintenance)
            next_start, next_end, next_desc = scheduler.get_next_trading_session(now)
            secs_to_start = max(0.0, (next_start - now).total_seconds())

            # Log periodic countdown every 60 seconds
            if (time.time() - last_countdown_log) >= 60.0:
                last_countdown_log = time.time()
                countdown_str = scheduler.format_countdown(secs_to_start)
                status_note = f"Market is CLOSED ({status_msg})."
                if scheduler.is_maintenance_mode:
                    status_note = "MAINTENANCE MODE ACTIVE (Paused by Admin)."

                print(f"[{now.strftime('%H:%M:%S')}] {status_note} Next session in: {countdown_str} ({next_start.strftime('%a %d-%b %H:%M:%S')})")
                sys.stdout.flush()

            # Sleep in responsive 2-second chunks
            sleep_chunk = min(2.0, secs_to_start) if secs_to_start > 0 else 1.0
            time.sleep(sleep_chunk)

    print("\n[+] Daemon stopped cleanly. Goodbye.")


def main():
    global _TERMINATION_REQUESTED

    parser = argparse.ArgumentParser(
        description="Relative Strength Collector Daemon (Service 1) - Autonomous Market Engine"
    )
    parser.add_argument(
        "--now", "--force",
        action="store_true",
        help="Force immediate run right now regardless of market hours (useful for testing/dry runs)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print current market calendar status, next trading session countdown, and exit"
    )
    args = parser.parse_args()

    configure_logger(
        project_name="relative_strength_collector",
        project_root=REPO_ROOT,
        show_logs_on_terminal=True,
        store_logs_in_file=True,
        log_level="INFO",
    )

    scheduler = MarketScheduler()

    # Register OS signals for graceful shutdown
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    if args.status:
        print_status_banner(scheduler)
        return

    print_status_banner(scheduler)

    creds = get_angelone_credentials()
    if not creds.get("client_code") or not creds.get("api_key"):
        print("\n" + "!" * 78)
        print("  [ERROR] Angel One credentials are not configured!")
        print("  To fix this:")
        print("    1. Copy the example credentials file:")
        print("       cp credentials.example.json credentials.json")
        print("    2. Open 'credentials.json' and fill in:")
        print("       - api_key")
        print("       - client_code (Angel One User ID)")
        print("       - password (PIN or password)")
        print("       - totp_secret (TOTP Authenticator Secret Key)")
        print("  Then run 'python3 run_collector.py' again.")
        print("!" * 78 + "\n")
        sys.exit(1)

    if args.now:
        print("[!] --force / --now flag specified: Running collector immediately outside schedule...")
        collector = RelativeStrengthCollector()
        run_single_session_blocking(collector)
    else:
        run_scheduled_daemon(scheduler)


if __name__ == "__main__":
    main()
