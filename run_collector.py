"""
run_collector.py
----------------
Launcher for Service 1: Relative Strength Collector Daemon.
Runs in terminal or background console, connects to WebSocket, and streams into MySQL.
"""

from pathlib import Path
import signal
import sys
import time

from collector_daemon import RelativeStrengthCollector
from core.logger import configure_logger

PROJECT_ROOT = Path(__file__).resolve().parent


def main():
    logger = configure_logger(
        project_name="relative_strength_collector",
        project_root=PROJECT_ROOT,
        show_logs_on_terminal=True,
        store_logs_in_file=True,
        log_level="INFO",
    )

    collector = RelativeStrengthCollector()

    def handle_exit(sig, frame):
        print("\n[-] Shutdown signal received. Stopping collector...")
        collector.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    collector.start()

    try:
        while collector.running:
            time.sleep(1.0)
    except KeyboardInterrupt:
        handle_exit(None, None)


if __name__ == "__main__":
    main()
