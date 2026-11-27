"""
projects/06_live_relative_strength_and_heatmap_dashboard/market_scheduler.py
-----------------------------------------------------------------------------
Autonomous Market Scheduling Engine for Relative Strength Collector Daemon:
- Detects Monday-Friday trading hours (09:15 - 15:30 IST).
- Detects Saturday/Sunday weekends and automatically sleeps without API calls.
- Supports NSE/BSE holiday calendar and special trading sessions (e.g. Diwali Muhurat).
- Supports Admin Maintenance Mode toggle for instant pausing without code edits.
- Operates under standard Linux user accounts without requiring sudo privileges.
"""

from datetime import date, datetime, time as dtime, timedelta
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from config import (
    MARKET_CALENDAR_FILE,
    MARKET_CLOSE_TIME,
    MARKET_OPEN_TIME,
)
try:
    from core.logger import get_logger
except ImportError:
    from utils.logger import get_logger

logger = get_logger("relative_strength.scheduler")


class MarketScheduler:
    """Manages trading schedule, holiday detection, and sleep countdowns."""

    def __init__(self, calendar_file: Optional[Path] = None):
        self.calendar_file = calendar_file or MARKET_CALENDAR_FILE
        self._calendar_data: Dict[str, Any] = {}
        self.load_calendar()

    def load_calendar(self, force_reload: bool = True) -> Dict[str, Any]:
        """Loads or reloads market calendar JSON settings dynamically."""
        if not force_reload and self._calendar_data:
            return self._calendar_data
        defaults = {
            "holidays": [
                "2026-01-26", "2026-03-03", "2026-03-27", "2026-04-03",
                "2026-04-14", "2026-05-01", "2026-08-15", "2026-10-02",
                "2026-11-08", "2026-12-25"
            ],
            "special_sessions": {
                "2026-11-08": {
                    "start_time": "18:00:00",
                    "end_time": "19:15:00",
                    "description": "Diwali Laxmi Pujan Muhurat Trading Session",
                }
            },
            "maintenance_mode": False,
            "force_run": False,
            "pre_market_seconds": 60,
            "post_market_seconds": 30,
        }

        if self.calendar_file.exists():
            try:
                with open(self.calendar_file, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                if isinstance(file_data, dict):
                    defaults.update(file_data)
            except Exception as e:
                logger.warning(f"Error loading {self.calendar_file.name}: {e}. Using fallback defaults.")

        self._calendar_data = defaults
        return self._calendar_data

    @property
    def is_maintenance_mode(self) -> bool:
        """Returns True if admin has paused data collection for maintenance."""
        self.load_calendar(force_reload=True)
        return bool(self._calendar_data.get("maintenance_mode", False))

    @property
    def is_force_run(self) -> bool:
        """Returns True if admin has forced immediate execution outside market hours."""
        self.load_calendar(force_reload=True)
        return bool(self._calendar_data.get("force_run", False))

    def is_market_day(
        self, target_date: Optional[date] = None, force_reload: bool = True
    ) -> Tuple[bool, str]:
        """
        Determines whether the given date is an active market trading day.
        Returns: (is_trading_day, reason_description)
        """
        self.load_calendar(force_reload=force_reload)
        t_date = target_date or datetime.now().date()
        date_str = t_date.strftime("%Y-%m-%d")

        # 1. Check special sessions (overrides weekend/holiday)
        special_sessions = self._calendar_data.get("special_sessions", {})
        if date_str in special_sessions:
            desc = special_sessions[date_str].get("description", "Special Trading Session")
            return True, f"Special Session: {desc}"

        # 2. Check Admin Maintenance Mode
        if self._calendar_data.get("maintenance_mode", False):
            return False, "Maintenance Mode Active (Paused by Admin)"

        # 3. Check official stock market holidays
        holidays = self._calendar_data.get("holidays", [])
        if date_str in holidays:
            return False, f"Market Holiday ({date_str})"

        # 4. Check weekends (Saturday = 5, Sunday = 6)
        weekday = t_date.weekday()
        if weekday == 5:
            return False, "Weekend (Saturday)"
        elif weekday == 6:
            return False, "Weekend (Sunday)"

        return True, "Regular NSE/BSE Trading Day"

    def get_session_window(
        self, target_date: Optional[date] = None, force_reload: bool = True
    ) -> Tuple[datetime, datetime, str]:
        """
        Returns (start_datetime, end_datetime, description) for the target date,
        accounting for pre-market buffer and post-market finalization buffer.
        """
        self.load_calendar(force_reload=force_reload)
        t_date = target_date or datetime.now().date()
        date_str = t_date.strftime("%Y-%m-%d")

        special_sessions = self._calendar_data.get("special_sessions", {})
        pre_buf = int(self._calendar_data.get("pre_market_seconds", 60))
        post_buf = int(self._calendar_data.get("post_market_seconds", 30))

        if date_str in special_sessions:
            info = special_sessions[date_str]
            start_str = info.get("start_time", "18:00:00")
            end_str = info.get("end_time", "19:15:00")
            desc = info.get("description", "Special Trading Session")
        else:
            start_str = MARKET_OPEN_TIME
            end_str = MARKET_CLOSE_TIME
            desc = "Regular Trading Session"

        # Parse time strings
        sh, sm, ss = [int(x) for x in start_str.split(":")]
        eh, em, es = [int(x) for x in end_str.split(":")]

        nominal_start = datetime.combine(t_date, dtime(sh, sm, ss))
        nominal_end = datetime.combine(t_date, dtime(eh, em, es))

        actual_start = nominal_start - timedelta(seconds=pre_buf)
        actual_end = nominal_end + timedelta(seconds=post_buf)

        return actual_start, actual_end, desc

    def is_market_open_now(
        self, now_dt: Optional[datetime] = None, force_reload: bool = True
    ) -> Tuple[bool, str, Optional[datetime], Optional[datetime]]:
        """
        Checks whether the market is open right now.
        Returns: (is_open, status_message, session_start, session_end)
        """
        self.load_calendar(force_reload=force_reload)
        now = now_dt or datetime.now()

        # Check Force Run
        if self._calendar_data.get("force_run", False):
            return True, "Force Run Override Active (Testing)", now, now + timedelta(hours=8)

        # Check Maintenance Mode
        if self._calendar_data.get("maintenance_mode", False):
            return False, "Maintenance Mode Active (Admin Paused)", None, None

        is_trading, day_reason = self.is_market_day(now.date(), force_reload=False)
        if not is_trading:
            return False, day_reason, None, None

        session_start, session_end, session_desc = self.get_session_window(now.date(), force_reload=False)

        if now < session_start:
            return False, f"Pre-Market (Session starts at {session_start.strftime('%H:%M:%S')})", session_start, session_end
        elif now > session_end:
            return False, f"Post-Market (Session ended at {session_end.strftime('%H:%M:%S')})", session_start, session_end
        else:
            return True, f"Market Open ({session_desc})", session_start, session_end

    def get_next_trading_session(
        self, now_dt: Optional[datetime] = None, force_reload: bool = True
    ) -> Tuple[datetime, datetime, str]:
        """
        Scans forward day by day to find the next active trading session.
        Returns: (session_start, session_end, description)
        """
        self.load_calendar(force_reload=force_reload)
        now = now_dt or datetime.now()
        current_date = now.date()

        # First check if today has an upcoming or ongoing session
        is_today_trading, today_desc = self.is_market_day(current_date, force_reload=False)
        if is_today_trading:
            start_dt, end_dt, desc = self.get_session_window(current_date, force_reload=False)
            if now < end_dt:
                return start_dt, end_dt, desc

        # Scan subsequent days (up to 30 days ahead)
        check_date = current_date + timedelta(days=1)
        for _ in range(30):
            is_trading, desc = self.is_market_day(check_date, force_reload=False)
            if is_trading:
                start_dt, end_dt, session_desc = self.get_session_window(check_date, force_reload=False)
                return start_dt, end_dt, session_desc
            check_date += timedelta(days=1)

        # Fallback to next Monday 09:14:00 if 30 days scan yields nothing
        days_ahead = (0 - current_date.weekday()) % 7 or 7
        next_mon = current_date + timedelta(days=days_ahead)
        start_dt, end_dt, desc = self.get_session_window(next_mon, force_reload=False)
        return start_dt, end_dt, desc

    @staticmethod
    def format_countdown(seconds: float) -> str:
        """Formats seconds into readable 'Xh Ym Zs' string."""
        if seconds <= 0:
            return "0s"
        total_sec = int(seconds)
        hours, rem = divmod(total_sec, 3600)
        minutes, secs = divmod(rem, 60)
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or hours > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)
