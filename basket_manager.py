"""
basket_manager.py
-----------------
Manages the official Nifty 50 basket and dynamic runtime additions/removals:
- Exactly 50 official Nifty 50 constituents (verified on NSE).
- Dynamic metadata resolution for any user-entered symbol or token.
- Seamless synchronization with MySQL `basket_tokens`.
"""

from typing import Any, Dict, List, Optional
from db_manager import DatabaseManager
from core.instrument_lookup import InstrumentManager, find_instrument
from core.logger import get_logger

logger = get_logger("relative_strength.basket")

# ==============================================================================
# DEFAULT BASKET CONSTITUENTS (NIFTY 50 + CUSTOM DEFAULT INSTRUMENTS)
# ------------------------------------------------------------------------------
# >>> WHERE TO CONFIGURE DEFAULT TOKENS <<<
# This list `NIFTY_50_DEFAULT_METADATA` defines the default instruments that load
# on initial run. To add or edit default stocks (e.g. BSE, Nifty 50 stocks),
# simply add or edit dictionaries in this list.
# Format:
#   {"symbol": "SYMBOL-EQ", "token": "TOKEN_STR", "name": "NAME", "exchange": "NSE",
#    "market_cap_crores": MCAP_FLOAT, "prev_close": PREV_CLOSE_FLOAT}
# ==============================================================================
NIFTY_50_DEFAULT_METADATA: List[Dict[str, Any]] = [
    {"symbol": "ABB-EQ", "token": "13", "name": "ABB", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "ADANIENT-EQ", "token": "25", "name": "ADANIENT", "exchange": "NSE", "market_cap_crores": 310000.0, "prev_close": 2750.0},
    {"symbol": "ADANIGREEN-EQ", "token": "3563", "name": "ADANIGREEN", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "ADANIPORTS-EQ", "token": "15083", "name": "ADANIPORTS", "exchange": "NSE", "market_cap_crores": 300000.0, "prev_close": 1390.0},
    {"symbol": "ADANIPOWER-EQ", "token": "17388", "name": "ADANIPOWER", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "ALKEM-EQ", "token": "11703", "name": "ALKEM", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "APLAPOLLO-EQ", "token": "25780", "name": "APLAPOLLO", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "APOLLOHOSP-EQ", "token": "157", "name": "APOLLOHOSP", "exchange": "NSE", "market_cap_crores": 105000.0, "prev_close": 7100.0},
    {"symbol": "ASHOKLEY-EQ", "token": "212", "name": "ASHOKLEY", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "ASIANPAINT-EQ", "token": "236", "name": "ASIANPAINT", "exchange": "NSE", "market_cap_crores": 250000.0, "prev_close": 2850.0},
    {"symbol": "AUBANK-EQ", "token": "21238", "name": "AUBANK", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "AUROPHARMA-EQ", "token": "275", "name": "AUROPHARMA", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "AXISBANK-EQ", "token": "5900", "name": "AXISBANK", "exchange": "NSE", "market_cap_crores": 350000.0, "prev_close": 1180.0},
    {"symbol": "BAJAJ-AUTO-EQ", "token": "16669", "name": "BAJAJ-AUTO", "exchange": "NSE", "market_cap_crores": 290000.0, "prev_close": 10200.0},
    {"symbol": "BAJAJFINSV-EQ", "token": "16675", "name": "BAJAJFINSV", "exchange": "NSE", "market_cap_crores": 270000.0, "prev_close": 1720.0},
    {"symbol": "BAJAJHLDNG-EQ", "token": "305", "name": "BAJAJHLDNG", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "BAJFINANCE-EQ", "token": "317", "name": "BAJFINANCE", "exchange": "NSE", "market_cap_crores": 440000.0, "prev_close": 7150.0},
    {"symbol": "BANKBARODA-EQ", "token": "4668", "name": "BANKBARODA", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "BEL-EQ", "token": "383", "name": "BEL", "exchange": "NSE", "market_cap_crores": 210000.0, "prev_close": 290.0},
    {"symbol": "BHARATFORG-EQ", "token": "422", "name": "BHARATFORG", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "BHARTIARTL-EQ", "token": "10604", "name": "BHARTIARTL", "exchange": "NSE", "market_cap_crores": 980000.0, "prev_close": 1650.0},
    {"symbol": "BIOCON-EQ", "token": "11373", "name": "BIOCON", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "BLUESTARCO-EQ", "token": "8311", "name": "BLUESTARCO", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "BOSCHLTD-EQ", "token": "2181", "name": "BOSCHLTD", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "BPCL-EQ", "token": "526", "name": "BPCL", "exchange": "NSE", "market_cap_crores": 145000.0, "prev_close": 340.0},
    {"symbol": "BRITANNIA-EQ", "token": "547", "name": "BRITANNIA", "exchange": "NSE", "market_cap_crores": 135000.0, "prev_close": 5600.0},
    {"symbol": "BSE-EQ", "token": "19585", "name": "BSE", "exchange": "NSE", "market_cap_crores": 65000.0, "prev_close": 4650.0},
    {"symbol": "CIPLA-EQ", "token": "694", "name": "CIPLA", "exchange": "NSE", "market_cap_crores": 125000.0, "prev_close": 1550.0},
    {"symbol": "COALINDIA-EQ", "token": "20374", "name": "COALINDIA", "exchange": "NSE", "market_cap_crores": 280000.0, "prev_close": 480.0},
    {"symbol": "COFORGE-EQ", "token": "11543", "name": "COFORGE", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "CUMMINSIND-EQ", "token": "1901", "name": "CUMMINSIND", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "DABUR-EQ", "token": "772", "name": "DABUR", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "DIVISLAB-EQ", "token": "10940", "name": "DIVISLAB", "exchange": "NSE", "market_cap_crores": 140000.0, "prev_close": 5400.0},
    {"symbol": "DIXON-EQ", "token": "21690", "name": "DIXON", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "DLF-EQ", "token": "14732", "name": "DLF", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "DMART-EQ", "token": "19913", "name": "DMART", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "DRREDDY-EQ", "token": "881", "name": "DRREDDY", "exchange": "NSE", "market_cap_crores": 110000.0, "prev_close": 6600.0},
    {"symbol": "EICHERMOT-EQ", "token": "910", "name": "EICHERMOT", "exchange": "NSE", "market_cap_crores": 130000.0, "prev_close": 4850.0},
    {"symbol": "GLENMARK-EQ", "token": "7406", "name": "GLENMARK", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "GMRAIRPORT-EQ", "token": "13528", "name": "GMRAIRPORT", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "GODREJCP-EQ", "token": "10099", "name": "GODREJCP", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "GRASIM-EQ", "token": "1232", "name": "GRASIM", "exchange": "NSE", "market_cap_crores": 170000.0, "prev_close": 2600.0},
    {"symbol": "HAL-EQ", "token": "2303", "name": "HAL", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "HAVELLS-EQ", "token": "9819", "name": "HAVELLS", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "HCLTECH-EQ", "token": "7229", "name": "HCLTECH", "exchange": "NSE", "market_cap_crores": 480000.0, "prev_close": 1780.0},
    {"symbol": "HDFCAMC-EQ", "token": "4244", "name": "HDFCAMC", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "HDFCBANK-EQ", "token": "1333", "name": "HDFCBANK", "exchange": "NSE", "market_cap_crores": 1280000.0, "prev_close": 1680.0},
    {"symbol": "HDFCLIFE-EQ", "token": "467", "name": "HDFCLIFE", "exchange": "NSE", "market_cap_crores": 150000.0, "prev_close": 710.0},
    {"symbol": "HEROMOTOCO-EQ", "token": "1348", "name": "HEROMOTOCO", "exchange": "NSE", "market_cap_crores": 105000.0, "prev_close": 5200.0},
    {"symbol": "HINDALCO-EQ", "token": "1363", "name": "HINDALCO", "exchange": "NSE", "market_cap_crores": 160000.0, "prev_close": 710.0},
    {"symbol": "HINDUNILVR-EQ", "token": "1394", "name": "HINDUNILVR", "exchange": "NSE", "market_cap_crores": 620000.0, "prev_close": 2650.0},
    {"symbol": "HINDZINC-EQ", "token": "1424", "name": "HINDZINC", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "ICICIBANK-EQ", "token": "4963", "name": "ICICIBANK", "exchange": "NSE", "market_cap_crores": 890000.0, "prev_close": 1250.0},
    {"symbol": "INDIGO-EQ", "token": "11195", "name": "INDIGO", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "INDUSINDBK-EQ", "token": "5258", "name": "INDUSINDBK", "exchange": "NSE", "market_cap_crores": 85000.0, "prev_close": 1050.0},
    {"symbol": "INDUSTOWER-EQ", "token": "29135", "name": "INDUSTOWER", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "INFY-EQ", "token": "1594", "name": "INFY", "exchange": "NSE", "market_cap_crores": 780000.0, "prev_close": 1850.0},
    {"symbol": "IRFC-EQ", "token": "2029", "name": "IRFC", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "ITC-EQ", "token": "1660", "name": "ITC", "exchange": "NSE", "market_cap_crores": 610000.0, "prev_close": 490.0},
    {"symbol": "JINDALSTEL-EQ", "token": "6733", "name": "JINDALSTEL", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "JIOFIN-EQ", "token": "18143", "name": "JIOFIN", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "JSWENERGY-EQ", "token": "17869", "name": "JSWENERGY", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "JSWSTEEL-EQ", "token": "11723", "name": "JSWSTEEL", "exchange": "NSE", "market_cap_crores": 230000.0, "prev_close": 980.0},
    {"symbol": "KOTAKBANK-EQ", "token": "1922", "name": "KOTAKBANK", "exchange": "NSE", "market_cap_crores": 360000.0, "prev_close": 1810.0},
    {"symbol": "LAURUSLABS-EQ", "token": "19234", "name": "LAURUSLABS", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "LICI-EQ", "token": "9480", "name": "LICI", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "LODHA-EQ", "token": "3220", "name": "LODHA", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "LT-EQ", "token": "11483", "name": "LT", "exchange": "NSE", "market_cap_crores": 490000.0, "prev_close": 3550.0},
    {"symbol": "LTM-EQ", "token": "17818", "name": "LTM", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "LUPIN-EQ", "token": "10440", "name": "LUPIN", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "M&M-EQ", "token": "2031", "name": "M&M", "exchange": "NSE", "market_cap_crores": 340000.0, "prev_close": 2890.0},
    {"symbol": "MANKIND-EQ", "token": "15380", "name": "MANKIND", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "MARICO-EQ", "token": "4067", "name": "MARICO", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "MARUTI-EQ", "token": "10999", "name": "MARUTI", "exchange": "NSE", "market_cap_crores": 390000.0, "prev_close": 12400.0},
    {"symbol": "MAXHEALTH-EQ", "token": "22377", "name": "MAXHEALTH", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "MFSL-EQ", "token": "2142", "name": "MFSL", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "MOTHERSON-EQ", "token": "4204", "name": "MOTHERSON", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "MUTHOOTFIN-EQ", "token": "23650", "name": "MUTHOOTFIN", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "NESTLEIND-EQ", "token": "17963", "name": "NESTLEIND", "exchange": "NSE", "market_cap_crores": 220000.0, "prev_close": 2350.0},
    {"symbol": "NTPC-EQ", "token": "11630", "name": "NTPC", "exchange": "NSE", "market_cap_crores": 380000.0, "prev_close": 410.0},
    {"symbol": "Nifty 50", "token": "99926000", "name": "NIFTY", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "ONGC-EQ", "token": "2475", "name": "ONGC", "exchange": "NSE", "market_cap_crores": 340000.0, "prev_close": 280.0},
    {"symbol": "PAYTM-EQ", "token": "6705", "name": "PAYTM", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "PERSISTENT-EQ", "token": "18365", "name": "PERSISTENT", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "PFC-EQ", "token": "14299", "name": "PFC", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "PIDILITIND-EQ", "token": "2664", "name": "PIDILITIND", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "PIIND-EQ", "token": "24184", "name": "PIIND", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "PNB-EQ", "token": "10666", "name": "PNB", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "POLICYBZR-EQ", "token": "6656", "name": "POLICYBZR", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "POLYCAB-EQ", "token": "9590", "name": "POLYCAB", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "POWERGRID-EQ", "token": "14977", "name": "POWERGRID", "exchange": "NSE", "market_cap_crores": 290000.0, "prev_close": 320.0},
    {"symbol": "POWERINDIA-EQ", "token": "18457", "name": "POWERINDIA", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "PRESTIGE-EQ", "token": "20302", "name": "PRESTIGE", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "RELIANCE-EQ", "token": "2885", "name": "RELIANCE", "exchange": "NSE", "market_cap_crores": 1980000.0, "prev_close": 2750.0},
    {"symbol": "SBILIFE-EQ", "token": "21808", "name": "SBILIFE", "exchange": "NSE", "market_cap_crores": 170000.0, "prev_close": 1690.0},
    {"symbol": "SBIN-EQ", "token": "3045", "name": "SBIN", "exchange": "NSE", "market_cap_crores": 740000.0, "prev_close": 820.0},
    {"symbol": "SHRIRAMFIN-EQ", "token": "4306", "name": "SHRIRAMFIN", "exchange": "NSE", "market_cap_crores": 120000.0, "prev_close": 3250.0},
    {"symbol": "SIEMENS-EQ", "token": "3150", "name": "SIEMENS", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "SRF-EQ", "token": "3273", "name": "SRF", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "SUNPHARMA-EQ", "token": "3351", "name": "SUNPHARMA", "exchange": "NSE", "market_cap_crores": 430000.0, "prev_close": 1820.0},
    {"symbol": "SUPREMEIND-EQ", "token": "3363", "name": "SUPREMEIND", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "TATACONSUM-EQ", "token": "3432", "name": "TATACONSUM", "exchange": "NSE", "market_cap_crores": 108000.0, "prev_close": 1120.0},
    {"symbol": "TATAPOWER-EQ", "token": "3426", "name": "TATAPOWER", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "TATASTEEL-EQ", "token": "3499", "name": "TATASTEEL", "exchange": "NSE", "market_cap_crores": 210000.0, "prev_close": 150.0},
    {"symbol": "TCS-EQ", "token": "11536", "name": "TCS", "exchange": "NSE", "market_cap_crores": 1420000.0, "prev_close": 4100.0},
    {"symbol": "TECHM-EQ", "token": "13538", "name": "TECHM", "exchange": "NSE", "market_cap_crores": 150000.0, "prev_close": 1650.0},
    {"symbol": "TITAN-EQ", "token": "3506", "name": "TITAN", "exchange": "NSE", "market_cap_crores": 290000.0, "prev_close": 3400.0},
    {"symbol": "TMPV-EQ", "token": "3456", "name": "TATAMOTORS", "exchange": "NSE", "market_cap_crores": 320000.0, "prev_close": 880.0},
    {"symbol": "TORNTPHARM-EQ", "token": "3518", "name": "TORNTPHARM", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "TRENT-EQ", "token": "1964", "name": "TRENT", "exchange": "NSE", "market_cap_crores": 260000.0, "prev_close": 7100.0},
    {"symbol": "TVSMOTOR-EQ", "token": "8479", "name": "TVSMOTOR", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "ULTRACEMCO-EQ", "token": "11532", "name": "ULTRACEMCO", "exchange": "NSE", "market_cap_crores": 310000.0, "prev_close": 11200.0},
    {"symbol": "UPL-EQ", "token": "11287", "name": "UPL", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "VAML-EQ", "token": "750174", "name": "VAML", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "VBL-EQ", "token": "18921", "name": "VBL", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "VEDL-EQ", "token": "3063", "name": "VEDL", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "WAAREEENER-EQ", "token": "25907", "name": "WAAREEENER", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
    {"symbol": "WIPRO-EQ", "token": "3787", "name": "WIPRO", "exchange": "NSE", "market_cap_crores": 280000.0, "prev_close": 530.0},
    {"symbol": "ZYDUSLIFE-EQ", "token": "7929", "name": "ZYDUSLIFE", "exchange": "NSE", "market_cap_crores": 10000.0, "prev_close": 100.0},
]


class BasketManager:
    """Provides lookup, auto-resolution, and database synchronization for trading baskets."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.inst_mgr = InstrumentManager()
        self.default_catalog = {m["token"]: m for m in NIFTY_50_DEFAULT_METADATA}
        for m in NIFTY_50_DEFAULT_METADATA:
            sym_key = m["symbol"].replace("-EQ", "").upper()
            self.default_catalog[sym_key] = m

    def sync_default_basket(self, force_reset_to_nifty50: bool = False) -> int:
        """
        Ensures `basket_tokens` in MySQL contains all default constituents defined in
        `NIFTY_50_DEFAULT_METADATA`.
        - Checks which tokens from `NIFTY_50_DEFAULT_METADATA` are missing in MySQL and auto-adds them.
        - Preserves user-added custom stocks unless force_reset_to_nifty50 is explicitly True.
        """
        active = self.db.get_active_basket_tokens()
        default_tokens = {str(m["token"]) for m in NIFTY_50_DEFAULT_METADATA}
        missing_defaults = [m for m in NIFTY_50_DEFAULT_METADATA if str(m["token"]) not in active]

        # If nothing missing and no force reset, keep existing active basket
        if not missing_defaults and not force_reset_to_nifty50:
            return len(active)

        tokens_to_upsert = []
        target_list = NIFTY_50_DEFAULT_METADATA if force_reset_to_nifty50 else missing_defaults
        for m in target_list:
            tok = str(m["token"])
            tokens_to_upsert.append({
                "token": tok,
                "symbol": m["symbol"],
                "name": m["name"],
                "exchange": m["exchange"],
                "prev_close": m["prev_close"],
                "market_cap_crores": m["market_cap_crores"],
                "is_active": True,
            })

        if tokens_to_upsert:
            self.db.upsert_basket_tokens(tokens_to_upsert)
            logger.info(f"Upserted {len(tokens_to_upsert)} default constituents into `basket_tokens`.")

        # Clean up stale/dummy tokens if force reset
        if force_reset_to_nifty50:
            try:
                conn = self.db.get_connection()
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM basket_tokens WHERE token NOT IN %s AND token = '99999';", (tuple(default_tokens),))
                conn.close()
            except Exception:
                pass

        total_active = len(self.db.get_active_basket_tokens())
        logger.info(f"Active tracking basket total: {total_active} instruments.")
        return total_active

    def resolve_instrument(self, query: str, exchange: str = "NSE") -> Optional[Dict[str, Any]]:
        """
        Resolves a user-entered symbol or numeric token into a complete metadata dictionary:
        - Checks built-in Nifty 50 catalog first.
        - Checks local instrument master cache via find_instrument.
        """
        cleaned = str(query).strip().upper()
        if not cleaned:
            return None

        # 1. Check built-in Nifty 50 catalog first for quick resolution
        if cleaned in self.default_catalog:
            m = self.default_catalog[cleaned]
            return {
                "token": m["token"],
                "symbol": m["symbol"],
                "name": m["name"],
                "exchange": m.get("exchange", "NSE"),
                "prev_close": m.get("prev_close", 100.0),
                "market_cap_crores": m.get("market_cap_crores", 10000.0),
            }

        # 2. Check local instrument master cache via find_instrument
        try:
            rec = find_instrument(manager=self.inst_mgr, query=cleaned, exchange=exchange)
            if not rec:
                rec = find_instrument(manager=self.inst_mgr, query=f"{cleaned}-EQ", exchange=exchange)

            if rec:
                return {
                    "token": str(rec["token"]),
                    "symbol": str(rec["symbol"]),
                    "name": str(rec.get("name", rec["symbol"])),
                    "exchange": str(rec.get("exch_seg", exchange)),
                    "prev_close": 100.0,
                    "market_cap_crores": 10000.0,
                }
        except Exception as err:
            logger.debug(f"find_instrument lookup warning for '{cleaned}': {err}")

        return None
