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
USER_CREDENTIALS_FILE = PROJECT_DIR / "USER_CREDENTIALS.json"
CONNECTION_CONFIG_FILE = PROJECT_DIR / "connection_config.json"
MARKET_CALENDAR_FILE = PROJECT_DIR / "market_calendar.json"

# ==============================================================================
# USER CONFIGURATION (SINGLE-DEVICE vs TWO-DEVICE MODE)
# ------------------------------------------------------------------------------
# 1. ANGEL ONE CREDENTIALS:
#    Needed ONLY on the device running 'run_collector.py'!
#    (Leave empty if already saved in credentials.json or USER_CREDENTIALS.json)
# ------------------------------------------------------------------------------
ANGELONE_API_KEY = ""
ANGELONE_CLIENT_CODE = ""
ANGELONE_PASSWORD = ""
ANGELONE_TOTP_SECRET = ""

# ------------------------------------------------------------------------------
# 2. DATABASE CONFIGURATION (MySQL):
#
# • SINGLE-DEVICE MODE (Default - Collector & Dashboard both on SAME machine):
#     DB_HOST = "localhost"
#     DB_PORT = 3306
#
# • TWO-DEVICE MODE (Linux PC collects data, Windows Laptop runs Dashboard):
#     - On Linux PC (Server): Keep DB_HOST = "localhost", DB_PORT = 3306
#     - On Windows Laptop (Client): Set DB_HOST = "192.168.2.130", DB_PORT = 3307
# ------------------------------------------------------------------------------
DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "Admin@123"
DB_NAME = "algo_relative_strength"

# Remote bridge port (started automatically by run_collector.py without sudo)
BRIDGE_PORT = 3307


def get_angelone_credentials(file_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Loads Angel One account credentials.
    Priority:
      1. Direct variables in config.py (ANGELONE_API_KEY, ANGELONE_CLIENT_CODE, etc.)
      2. Explicit `file_path`
      3. Local `credentials.json`
      4. Local `USER_CREDENTIALS.json`
      5. Environment variables (ANGELONE_API_KEY, ANGELONE_CLIENT_CODE, etc.)
    """
    if ANGELONE_API_KEY and ANGELONE_CLIENT_CODE:
        return {
            "api_key": ANGELONE_API_KEY.strip(),
            "client_code": ANGELONE_CLIENT_CODE.strip(),
            "password": ANGELONE_PASSWORD.strip(),
            "totp_secret": ANGELONE_TOTP_SECRET.strip(),
        }

    targets = [t for t in [file_path, LOCAL_CREDENTIALS_FILE, USER_CREDENTIALS_FILE] if t and t.exists()]
    for target in targets:
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                c = data.get("angelone", data.get("credentials", data))
                if "api_key" in c and "client_code" in c:
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

    # Environment Variables
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


def get_host_ip_diagnostics() -> Dict[str, Any]:
    """
    Discovers local network interfaces and IPs for multi-device server setup.
    Returns primary LAN IP, all local IPs, and Tailscale IP (if active).
    """
    import socket
    import subprocess

    lan_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    all_ips = []
    try:
        hostname = socket.gethostname()
        all_ips = socket.gethostbyname_ex(hostname)[2]
    except Exception:
        all_ips = [lan_ip]

    tailscale_ip = None
    for ip in all_ips:
        if ip.startswith("100."):
            tailscale_ip = ip
            break

    if not tailscale_ip:
        try:
            out = subprocess.check_output(["tailscale", "ip", "-4"], stderr=subprocess.DEVNULL, timeout=1.5)
            ts = out.decode("utf-8").strip()
            if ts and ts.startswith("100."):
                tailscale_ip = ts
        except Exception:
            pass

    return {
        "primary_lan_ip": lan_ip,
        "all_ips": all_ips,
        "tailscale_ip": tailscale_ip,
    }


# ==============================================================================
# 1. MYSQL DATABASE CONFIGURATION (Supports Single & Multi-Device via Tailscale/LAN)
# ==============================================================================
def get_database_config() -> Dict[str, Any]:
    """
    Loads MySQL connection parameters.
    Priority:
      1. Local `connection_config.json` inside project folder (if present).
      2. Local `credentials.json` with "mysql" block.
      3. Variables in config.py (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME).
      4. Environment variables (DB_HOST, DB_PORT, etc. or MYSQL_HOST).
    """
    cfg = {
        "host": os.getenv("MYSQL_HOST", os.getenv("DB_HOST", DB_HOST)),
        "port": int(os.getenv("MYSQL_PORT", os.getenv("DB_PORT", DB_PORT))),
        "user": os.getenv("MYSQL_USER", os.getenv("DB_USER", DB_USER)),
        "password": os.getenv("MYSQL_PASSWORD", os.getenv("DB_PASSWORD", DB_PASSWORD)),
        "database": os.getenv("MYSQL_DATABASE", os.getenv("DB_NAME", DB_NAME)),
    }

    # 1. Check connection_config.json
    if CONNECTION_CONFIG_FILE.exists():
        try:
            with open(CONNECTION_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                m = data.get("mysql", data)
                if "host" in m and m["host"]:
                    cfg["host"] = str(m["host"]).strip()
                if "port" in m and m["port"]:
                    cfg["port"] = int(m["port"])
                if "user" in m and m["user"]:
                    cfg["user"] = str(m["user"]).strip()
                if "password" in m and m["password"] is not None:
                    cfg["password"] = str(m["password"]).strip()
                if "database" in m and m["database"]:
                    cfg["database"] = str(m["database"]).strip()
        except Exception:
            pass

    # 2. Check credentials.json
    elif LOCAL_CREDENTIALS_FILE.exists():
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

_load_db_config = get_database_config

DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 10
DB_TIMEOUT = 10

# ==============================================================================
# 2. INGESTION & DATA STORAGE TIMINGS & RETENTION
# ==============================================================================
BATCH_FLUSH_INTERVAL = 1.0        # Seconds between micro-batch flushes to MySQL
EVENT_POLL_INTERVAL = 1.0         # Seconds between checking dynamic token events
BAR_AGGREGATE_INTERVAL = 60       # 1-minute OHLC relative performance bar creation
MARKET_OPEN_TIME = "09:15:00"     # NSE Regular Market Opening Time (IST)
MARKET_CLOSE_TIME = "15:30:00"    # NSE Regular Market Closing Time (IST)

DAYS_TO_KEEP = 5                  # Number of trading days to retain in MySQL database
DEFAULT_SHOW_MULTIDAY = False     # Default GUI state: False = Today only, True = Multi-day continuation

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
