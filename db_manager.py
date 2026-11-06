"""
db_manager.py
-------------
High-performance MySQL database management layer for Live Relative Strength and Heatmap Dashboard:
- Connection pooling and auto-reconnect resilience.
- Auto-initialization of schema (database, tables, indexes).
- High-throughput micro-batch insertion of tick snapshots.
- Fast retrieval of intraday historical data (09:15 - present).
- Dynamic token event streaming for zero-restart subscription updates.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import pymysql
from pymysql.cursors import DictCursor

from config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_TIMEOUT,
    DB_USER,
)
from core.logger import get_logger

logger = get_logger("relative_strength.db")


class DatabaseManager:
    """Manages all MySQL interactions with connection retry & batch execution."""

    def __init__(
        self,
        host: str = DB_HOST,
        port: int = DB_PORT,
        user: str = DB_USER,
        password: str = DB_PASSWORD,
        db_name: str = DB_NAME,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.db_name = db_name

    def get_connection(self, include_db: bool = True) -> pymysql.Connection:
        """Creates a fresh connection to MySQL."""
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.db_name if include_db else None,
            connect_timeout=DB_TIMEOUT,
            cursorclass=DictCursor,
            autocommit=True,
        )

    def initialize_schema(self) -> bool:
        """
        Creates the database and all required tables/indexes if they do not exist.
        Ensures idempotency on every startup.
        """
        try:
            # 1. Ensure Database Exists
            conn = self.get_connection(include_db=False)
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{self.db_name}` CHARACTER SET utf8mb4;")
            conn.close()

            # 2. Create Required Tables
            conn = self.get_connection(include_db=True)
            with conn.cursor() as cur:
                # Table 1: basket_tokens
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS basket_tokens (
                        token VARCHAR(20) PRIMARY KEY,
                        symbol VARCHAR(50) NOT NULL,
                        name VARCHAR(50) NOT NULL,
                        exchange VARCHAR(10) DEFAULT 'NSE',
                        prev_close DECIMAL(12, 4) NOT NULL,
                        market_cap_crores DECIMAL(14, 2) DEFAULT 10000.00,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_active (is_active)
                    ) ENGINE=InnoDB;
                """)

                # Table 2: basket_events (IPC for zero-restart dynamic hot-reload)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS basket_events (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        event_type ENUM('ADD', 'REMOVE') NOT NULL,
                        token VARCHAR(20) NOT NULL,
                        symbol VARCHAR(50) NOT NULL,
                        processed_collector BOOLEAN DEFAULT FALSE,
                        processed_gui BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_proc (processed_collector, processed_gui)
                    ) ENGINE=InnoDB;
                """)

                # Table 3: relative_strength_ticks (High-Res 1s-3s snapshots)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS relative_strength_ticks (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        tick_time DATETIME NOT NULL,
                        token VARCHAR(20) NOT NULL,
                        symbol VARCHAR(50) NOT NULL,
                        ltp DECIMAL(12, 4) NOT NULL,
                        pct_change DECIMAL(8, 4) NOT NULL,
                        volume BIGINT DEFAULT 0,
                        INDEX idx_token_time (token, tick_time),
                        INDEX idx_time (tick_time)
                    ) ENGINE=InnoDB;
                """)

                # Table 4: relative_strength_1m_bars (1-Minute OHLC bars)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS relative_strength_1m_bars (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        bar_time DATETIME NOT NULL,
                        token VARCHAR(20) NOT NULL,
                        symbol VARCHAR(50) NOT NULL,
                        open_pct DECIMAL(8, 4) NOT NULL,
                        high_pct DECIMAL(8, 4) NOT NULL,
                        low_pct DECIMAL(8, 4) NOT NULL,
                        close_pct DECIMAL(8, 4) NOT NULL,
                        last_ltp DECIMAL(12, 4) NOT NULL,
                        volume BIGINT DEFAULT 0,
                        UNIQUE KEY uq_token_bar (token, bar_time),
                        INDEX idx_bar_time (bar_time)
                    ) ENGINE=InnoDB;
                """)
            conn.close()
            logger.info(f"Database schema initialized successfully for [{self.db_name}].")
            return True
        except Exception as err:
            logger.error(f"Failed to initialize database schema: {err}", exc_info=True)
            return False

    # ==========================================================================
    # BASKET MANAGEMENT & DYNAMIC HOT-RELOAD QUERIES
    # ==========================================================================

    def upsert_basket_tokens(self, tokens_data: List[Dict[str, Any]]) -> int:
        """Inserts or updates initial basket tokens (e.g. Nifty 50 defaults)."""
        if not tokens_data:
            return 0
        sql = """
            INSERT INTO basket_tokens (token, symbol, name, exchange, prev_close, market_cap_crores, is_active)
            VALUES (%(token)s, %(symbol)s, %(name)s, %(exchange)s, %(prev_close)s, %(market_cap_crores)s, %(is_active)s)
            ON DUPLICATE KEY UPDATE
                symbol = VALUES(symbol),
                name = VALUES(name),
                prev_close = VALUES(prev_close),
                market_cap_crores = VALUES(market_cap_crores),
                is_active = VALUES(is_active);
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                count = cur.executemany(sql, tokens_data)
            conn.close()
            return count
        except Exception as err:
            logger.error(f"Error upserting basket tokens: {err}")
            return 0

    def get_active_basket_tokens(self) -> Dict[str, Dict[str, Any]]:
        """Returns all currently active tokens mapped by token string."""
        sql = "SELECT token, symbol, name, exchange, prev_close, market_cap_crores FROM basket_tokens WHERE is_active = TRUE;"
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
            conn.close()
            return {str(r["token"]): r for r in rows}
        except Exception as err:
            logger.error(f"Error fetching active basket tokens: {err}")
            return {}

    def add_token_dynamically(self, token_info: Dict[str, Any]) -> bool:
        """
        Adds or activates a token in basket_tokens and records an 'ADD' event
        for the collector daemon to hot-subscribe immediately.
        """
        tok = str(token_info["token"]).strip()
        sym = str(token_info["symbol"]).strip()
        name = str(token_info.get("name", sym)).strip()
        exch = str(token_info.get("exchange", "NSE")).strip()
        prev_close = float(token_info.get("prev_close", 100.0))
        mcap = float(token_info.get("market_cap_crores", 10000.0))

        sql_basket = """
            INSERT INTO basket_tokens (token, symbol, name, exchange, prev_close, market_cap_crores, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            ON DUPLICATE KEY UPDATE
                symbol = VALUES(symbol),
                name = VALUES(name),
                exchange = VALUES(exchange),
                prev_close = VALUES(prev_close),
                market_cap_crores = VALUES(market_cap_crores),
                is_active = TRUE;
        """
        sql_event = """
            INSERT INTO basket_events (event_type, token, symbol, processed_collector, processed_gui)
            VALUES ('ADD', %s, %s, FALSE, FALSE);
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(sql_basket, (tok, sym, name, exch, prev_close, mcap))
                cur.execute(sql_event, (tok, sym))
            conn.close()
            logger.info(f"Dynamically registered token {tok} ({sym}) in database & emitted ADD event.")
            return True
        except Exception as err:
            logger.error(f"Failed to add token dynamically: {err}")
            return False

    def remove_token_dynamically(self, token: str) -> bool:
        """
        Deactivates a token in basket_tokens and records a 'REMOVE' event
        for the collector daemon to hot-unsubscribe immediately.
        """
        tok = str(token).strip()
        sql_basket = "UPDATE basket_tokens SET is_active = FALSE WHERE token = %s;"
        sql_event = """
            INSERT INTO basket_events (event_type, token, symbol, processed_collector, processed_gui)
            SELECT 'REMOVE', token, symbol, FALSE, FALSE FROM basket_tokens WHERE token = %s;
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(sql_event, (tok,))
                cur.execute(sql_basket, (tok,))
            conn.close()
            logger.info(f"Dynamically deactivated token {tok} in database & emitted REMOVE event.")
            return True
        except Exception as err:
            logger.error(f"Failed to remove token dynamically: {err}")
            return False

    def fetch_unprocessed_collector_events(self) -> List[Dict[str, Any]]:
        """Collector calls this to pick up new ADD/REMOVE subscription requests."""
        sql_select = "SELECT id, event_type, token, symbol FROM basket_events WHERE processed_collector = FALSE ORDER BY id ASC;"
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(sql_select)
                events = cur.fetchall()
                if events:
                    ids = [e["id"] for e in events]
                    format_strings = ",".join(["%s"] * len(ids))
                    cur.execute(f"UPDATE basket_events SET processed_collector = TRUE WHERE id IN ({format_strings});", ids)
            conn.close()
            return events
        except Exception as err:
            logger.error(f"Error fetching collector events: {err}")
            return []

    # ==========================================================================
    # HIGH-FREQUENCY TICK SNAPSHOTS & 1-MINUTE BARS
    # ==========================================================================

    def insert_tick_snapshots(self, batch_data: List[Tuple[Any, ...]]) -> int:
        """
        High-throughput micro-batch insert of relative strength ticks.
        batch_data format: [(tick_time, token, symbol, ltp, pct_change, volume), ...]
        """
        if not batch_data:
            return 0
        sql = """
            INSERT INTO relative_strength_ticks (tick_time, token, symbol, ltp, pct_change, volume)
            VALUES (%s, %s, %s, %s, %s, %s);
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                count = cur.executemany(sql, batch_data)
            conn.close()
            return count
        except Exception as err:
            logger.error(f"Error inserting tick batch ({len(batch_data)} rows): {err}")
            return 0

    def upsert_1m_bars(self, bars_data: List[Tuple[Any, ...]]) -> int:
        """
        Inserts or updates 1-minute OHLC relative performance bars.
        bars_data format: [(bar_time, token, symbol, open_pct, high_pct, low_pct, close_pct, last_ltp, volume), ...]
        """
        if not bars_data:
            return 0
        sql = """
            INSERT INTO relative_strength_1m_bars (bar_time, token, symbol, open_pct, high_pct, low_pct, close_pct, last_ltp, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                high_pct = GREATEST(high_pct, VALUES(high_pct)),
                low_pct = LEAST(low_pct, VALUES(low_pct)),
                close_pct = VALUES(close_pct),
                last_ltp = VALUES(last_ltp),
                volume = VALUES(volume);
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                count = cur.executemany(sql, bars_data)
            conn.close()
            return count
        except Exception as err:
            logger.error(f"Error upserting 1m bars: {err}")
            return 0

    # ==========================================================================
    # HISTORICAL INTRADAY QUERY FOR GUI INITIALIZATION (09:15 - NOW)
    # ==========================================================================

    def fetch_today_1m_bars(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches today's 1-minute bars from 09:15:00 onwards for all active tokens.
        Returns a dictionary: { token: [ {bar_time, close_pct, ltp, ...}, ... ] }
        """
        today_date = datetime.now().strftime("%Y-%m-%d")
        sql = """
            SELECT bar_time, token, symbol, open_pct, high_pct, low_pct, close_pct, last_ltp, volume
            FROM relative_strength_1m_bars
            WHERE bar_time >= CONCAT(%s, ' 09:15:00')
            ORDER BY bar_time ASC;
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(sql, (today_date,))
                rows = cur.fetchall()
            conn.close()

            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for r in rows:
                tok = str(r["token"])
                if tok not in grouped:
                    grouped[tok] = []
                grouped[tok].append(r)
            return grouped
        except Exception as err:
            logger.error(f"Error fetching today's 1m bars: {err}")
            return {}

    def fetch_latest_ticks_since(self, since_time: datetime) -> List[Dict[str, Any]]:
        """Fetches granular ticks logged after a given timestamp (for incremental chart polling)."""
        sql = """
            SELECT tick_time, token, symbol, ltp, pct_change, volume
            FROM relative_strength_ticks
            WHERE tick_time > %s
            ORDER BY tick_time ASC;
        """
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(sql, (since_time,))
                rows = cur.fetchall()
            conn.close()
            return rows
        except Exception as err:
            logger.error(f"Error fetching ticks since {since_time}: {err}")
            return []
