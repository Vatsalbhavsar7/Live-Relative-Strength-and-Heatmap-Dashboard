"""
core/instrument_lookup.py
-------------------------
Standalone Angel One Scrip Master Downloader & Fuzzy Search Index.
Enables real-time dynamic resolution of any NSE equity symbol or token.
"""

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from core.logger import get_logger

logger = get_logger("core.instruments")

OPENAPI_SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"


class InstrumentManager:
    """Manages downloading, local caching, and fast in-memory indexing of NSE instruments."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or (Path(__file__).resolve().parent.parent / "data" / "instruments")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.instruments_by_symbol: Dict[str, Dict[str, Any]] = {}
        self.instruments_by_token: Dict[str, Dict[str, Any]] = {}
        self._loaded: bool = False

    def ensure_loaded(self) -> bool:
        """Loads today's instrument master from cache or downloads it from Angel One."""
        if self._loaded and self.instruments_by_symbol:
            return True

        today_str = datetime.now().strftime("%Y-%m-%d")
        cache_file = self.cache_dir / f"{today_str}_scrip_master.json"

        # Check existing cache
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._build_index(data)
                self._loaded = True
                logger.info(f"Loaded {len(self.instruments_by_symbol)} instruments from local cache.")
                return True
            except Exception as err:
                logger.warning(f"Error loading cache: {err}")

        # Download from Angel One OpenAPIScripMaster
        try:
            logger.info("Downloading latest Scrip Master from Angel One...")
            resp = requests.get(OPENAPI_SCRIP_MASTER_URL, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                self._build_index(data)
                self._loaded = True
                logger.info(f"Downloaded and indexed {len(self.instruments_by_symbol)} instruments.")
                return True
        except Exception as exc:
            logger.warning(f"Could not download scrip master: {exc}")

        return False

    def _build_index(self, data: List[Dict[str, Any]]) -> None:
        """Indexes instruments by token and normalized symbol name for O(1) lookups."""
        for item in data:
            exch = str(item.get("exch_seg", "")).upper()
            if exch != "NSE":
                continue
            token = str(item.get("token", "")).strip()
            symbol = str(item.get("symbol", "")).strip().upper()
            name = str(item.get("name", "")).strip().upper()

            info = {
                "token": token,
                "symbol": symbol,
                "name": name,
                "exchange": "NSE",
                "instrument_type": item.get("instrumenttype", ""),
            }

            self.instruments_by_token[token] = info
            self.instruments_by_symbol[symbol] = info
            # Also index clean root symbol (e.g. 'RELIANCE' from 'RELIANCE-EQ')
            if symbol.endswith("-EQ"):
                root = symbol[:-3]
                if root not in self.instruments_by_symbol:
                    self.instruments_by_symbol[root] = info


_GLOBAL_INST_MGR: Optional[InstrumentManager] = None


def find_instrument(query: str, manager: Optional[InstrumentManager] = None) -> Optional[Dict[str, Any]]:
    """Resolves an instrument query (symbol or token) to complete scrip metadata."""
    global _GLOBAL_INST_MGR
    mgr = manager or _GLOBAL_INST_MGR
    if mgr is None:
        mgr = InstrumentManager()
        _GLOBAL_INST_MGR = mgr

    mgr.ensure_loaded()
    clean = str(query).strip().upper()
    if not clean:
        return None

    # Check token
    if clean in mgr.instruments_by_token:
        return mgr.instruments_by_token[clean]

    # Check symbol direct or with -EQ
    if clean in mgr.instruments_by_symbol:
        return mgr.instruments_by_symbol[clean]
    if f"{clean}-EQ" in mgr.instruments_by_symbol:
        return mgr.instruments_by_symbol[f"{clean}-EQ"]

    return None
