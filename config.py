"""
config.py
---------
Configuration parameters for the Live Relative Strength & Heatmap Dashboard:
- MySQL Database connection settings.
- Ingestion rates, batch flushing, and 1-minute bar aggregation.
- Market session hours (09:15 - 15:30 IST).
- Credentials loader supporting `credentials.json` and environment variables.
- GUI styling, color palettes, and interactive thresholds.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_CREDENTIALS_FILE = PROJECT_DIR / "credentials.json"


def get_angelone_credentials(file_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Loads Angel One account credentials.
    Priority:
      1. Explicit `file_path`
      2. Local `credentials.json` (git-ignored)
      3. Environment variables (ANGELONE_API_KEY, ANGELONE_CLIENT_CODE, etc.)
    """
    # 1. Local credentials.json (git-ignored private file)
    target = file_path or LOCAL_CREDENTIALS_FILE
    if target.exists():
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                c = data.get("angelone", data)
                return {
                    "api_key": str(c.get("api_key", "")).strip(),
                    "client_code": str(c.get("client_code", "")).strip(),
                    "password": str(c.get("password", c.get("pin", ""))).strip(),
                    "totp_secret": str(c.get("totp_secret", "")).strip(),
                }
            elif isinstance(data, list):
                for item in data:
                    if str(item.get("broker_name", "")).lower() == "angelone" and item.get("is_active", True):
                        c = item.get("credentials", {})
                        return {
                            "api_key": str(c.get("api_key", "")).strip(),
                            "client_code": str(c.get("client_code", "")).strip(),
                            "password": str(c.get("password", c.get("pin", ""))).strip(),
                            "totp_secret": str(c.get("totp_secret", "")).strip(),
                        }
        except Exception:
            pass

    # 2. Environment Variables
    env_key = os.getenv("ANGELONE_API_KEY")
    env_client = os.getenv("ANGELONE_CLIENT_CODE")
    if env_key and env_client:
        return {
            "api_key": env_key.strip(),
            "client_code": env_client.strip(),
            "password": str(os.getenv("ANGELONE_PASSWORD", "")).strip(),
            "totp_secret": str(os.getenv("ANGELONE_TOTP_SECRET", "")).strip(),
        }

    return {"api_key": "", "client_code": "", "password": "", "totp_secret": ""}


# ==============================================================================
# 1. MYSQL DATABASE CONFIGURATION
# ==============================================================================
def _load_db_config() -> Dict[str, Any]:
    cfg = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "algo_relative_strength"),
    }
    if LOCAL_CREDENTIALS_FILE.exists():
        try:
            with open(LOCAL_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and "mysql" in d:
                m = d["mysql"]
                cfg["host"] = m.get("host", cfg["host"])
                cfg["port"] = int(m.get("port", cfg["port"]))
                cfg["user"] = m.get("user", cfg["user"])
                cfg["password"] = m.get("password", cfg["password"])
                cfg["database"] = m.get("database", cfg["database"])
        except Exception:
            pass
    return cfg

_db_cfg = _load_db_config()
DB_HOST = _db_cfg["host"]
DB_PORT = _db_cfg["port"]
DB_USER = _db_cfg["user"]
DB_PASSWORD = _db_cfg["password"]
DB_NAME = _db_cfg["database"]

DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 10
DB_TIMEOUT = 10

# ==============================================================================
# 2. INGESTION & DATA STORAGE TIMINGS
# ==============================================================================
BATCH_FLUSH_INTERVAL = 1.0        # Seconds between micro-batch flushes to MySQL
EVENT_POLL_INTERVAL = 1.0         # Seconds between checking dynamic token events
BAR_AGGREGATE_INTERVAL = 60       # 1-minute OHLC relative performance bar creation
MARKET_OPEN_TIME = "09:15:00"     # NSE Regular Market Opening Time (IST)
MARKET_CLOSE_TIME = "15:30:00"    # NSE Regular Market Closing Time (IST)

# ==============================================================================
# 3. GUI & VISUALIZATION SETTINGS
# ==============================================================================
UI_POLL_INTERVAL_MS = 500         # GUI tick refresh rate (2 Hz for smooth updates)
DEFAULT_Y_MIN = -6.0              # Default lower % bound
DEFAULT_Y_MAX = 6.0               # Default upper % bound
Y_AXIS_PADDING_PCT = 1.2          # 20% margin when auto-scaling Y-axis

# Heatmap Thresholds (% Change)
HEATMAP_EXTREME_GREEN = 3.0       # > +3.0%
HEATMAP_STRONG_GREEN = 1.5        # +1.5% to +3.0%
HEATMAP_MODERATE_GREEN = 0.5      # +0.5% to +1.5%
HEATMAP_MILD_GREEN = 0.1          # +0.1% to +0.5%
HEATMAP_NEUTRAL = 0.0             # -0.1% to +0.1%
HEATMAP_MILD_RED = -0.1           # -0.5% to -0.1%
HEATMAP_MODERATE_RED = -0.5       # -1.5% to -0.5%
HEATMAP_STRONG_RED = -1.5         # -3.0% to -1.5%
HEATMAP_EXTREME_RED = -3.0        # < -3.0%

# Color Hex Codes
COLOR_BG_DARK = "#121824"
COLOR_PANEL_DARK = "#1E293B"
COLOR_BORDER = "#334155"
COLOR_TEXT_PRIMARY = "#F8FAFC"
COLOR_TEXT_SECONDARY = "#94A3B8"
COLOR_BASELINE_WHITE = "#E2E8F0"

# Heatmap Palette (Hex)
HEATMAP_COLORS: Dict[str, str] = {
    "extreme_green": "#00E676",   # Bright Electric Green
    "strong_green": "#2E7D32",    # Forest Green
    "moderate_green": "#1B5E20",  # Dark Olive Green
    "mild_green": "#144417",      # Deep Green
    "neutral": "#334155",         # Slate Grey
    "mild_red": "#4A1515",        # Deep Maroon
    "moderate_red": "#881313",    # Dark Crimson
    "strong_red": "#C62828",      # Crimson Red
    "extreme_red": "#FF1744",     # Bright Fire Red
}

# 50 High-Contrast Distinct Colors for Multi-Line Chart
LINE_PALETTE = [
    "#38BDF8", "#F59E0B", "#10B981", "#EF4444", "#8B5CF6", "#EC4899", "#14B8A6",
    "#F97316", "#06B6D4", "#84CC16", "#6366F1", "#D946EF", "#EAB308", "#22C55E",
    "#3B82F6", "#A855F7", "#F43F5E", "#0EA5E9", "#65A30D", "#FB923C", "#4ADE80",
    "#2DD4BF", "#A78BFA", "#F472B6", "#FACC15", "#60A5FA", "#C084FC", "#FB7185",
    "#34D399", "#818CF8", "#E879F9", "#475569", "#64748B", "#94A3B8", "#CBD5E1",
    "#93C5FD", "#FCA5A5", "#FDE047", "#86EFAC", "#67E8F9", "#D8B4FE", "#F9A8D4",
    "#FDBA74", "#5EEAD4", "#C4B5FD", "#FDA4AF", "#FCD34D", "#BEF264", "#7DD3FC",
    "#C7D2FE", "#F5D0FE"
]
