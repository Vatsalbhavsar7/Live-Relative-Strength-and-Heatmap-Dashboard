"""
collector_daemon.py
-------------------
Service 1: Standalone Background Ingestion Service:
1. Connects to Angel One SmartStream WebSocket 2.0.
2. Ingests live ticks for all active basket tokens (e.g. Nifty 50 constituents).
3. Computes relative percentage change from previous close in real-time:
   pct_change = ((LTP - PrevClose) / PrevClose) * 100
4. Micro-batches 1-second snapshots into MySQL (`relative_strength_ticks`).
5. Aggregates 1-minute OHLC relative performance bars (`relative_strength_1m_bars`).
6. Watches `basket_events` for zero-restart dynamic token additions & removals.
"""

from datetime import datetime
import signal
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set

from basket_manager import BasketManager
from config import (
    BAR_AGGREGATE_INTERVAL,
    BATCH_FLUSH_INTERVAL,
    DAYS_TO_KEEP,
    EVENT_POLL_INTERVAL,
    get_angelone_credentials,
)
from db_manager import DatabaseManager
from core.angelone_auth import login
from core.smartstream_ws import (
    MODE_QUOTE,
    close_ticker,
    connect_ticker,
    create_user_ticker,
    subscribe_tokens,
    unsubscribe_tokens,
)
from core.logger import get_logger

logger = get_logger("relative_strength.collector")


class RelativeStrengthCollector:
    """Headless background daemon collecting and calculating live relative performance."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.basket_mgr = BasketManager(db=self.db)

        self.user: Dict[str, Any] = {}
        self.active_sws: Optional[Any] = None
        self.running: bool = False

        # In-memory tracking
        self.active_tokens: Dict[str, Dict[str, Any]] = {}  # token -> metadata
        self.live_state: Dict[str, Dict[str, Any]] = {}     # token -> latest tick snapshot
        self.minute_bars_buffer: Dict[str, Dict[str, Any]] = {}  # token -> current minute bar accumulator
        self.current_bar_minute: Optional[str] = None

        # Threads
        self._flush_thread: Optional[threading.Thread] = None
        self._event_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Initializes database schema, logs in, and connects WebSocket."""
        logger.info("Initializing Relative Strength Collector Daemon...")
        print("\n" + "=" * 80)
        print("  ANGEL ONE - RELATIVE STRENGTH INGESTION DAEMON (SERVICE 1)")
        print("=" * 80)

        # 1. Initialize MySQL schema
        if not self.db.initialize_schema():
            logger.error("Database schema initialization failed. Terminating.")
            return

        # 2. Sync official Nifty 50 constituents (50 stocks)
        self.basket_mgr.sync_default_basket(force_reset_to_nifty50=True)
        self.active_tokens = self.db.get_active_basket_tokens()
        logger.info(f"Loaded {len(self.active_tokens)} active official Nifty 50 tokens from MySQL.")

        # 2b. Enforce database retention policy (keep last DAYS_TO_KEEP trading days)
        try:
            bars_del, ticks_del = self.db.prune_old_data(days_to_keep=DAYS_TO_KEEP)
            if bars_del > 0 or ticks_del > 0:
                logger.info(f"Enforced database retention ({DAYS_TO_KEEP} days): removed {bars_del} bars, {ticks_del} ticks.")
        except Exception as prune_err:
            logger.warning(f"Failed to enforce data retention policy: {prune_err}")

        # 3. Authenticate with Angel One
        if not self._authenticate():
            logger.error("Authentication failed. Cannot connect to SmartStream WebSocket.")
            return

        self.running = True

        # 4. Connect WebSocket
        self._connect_websocket()

        # 5. Launch background workers
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True, name="DBBatchFlusher")
        self._flush_thread.start()

        self._event_thread = threading.Thread(target=self._dynamic_events_loop, daemon=True, name="EventWatcher")
        self._event_thread.start()

        print(f"  [+] Tracking {len(self.active_tokens)} tokens live.")
        print(f"  [+] Micro-batch flush rate: every {BATCH_FLUSH_INTERVAL}s.")
        print(f"  [+] 1-minute OHLC bar aggregator: active.")
        print("=" * 80 + "\n")
        sys.stdout.flush()

    def stop(self) -> None:
        """Cleanly stops workers and terminates WebSocket."""
        logger.info("Stopping Relative Strength Collector Daemon...")
        self.running = False

        if self.active_sws:
            try:
                close_ticker(self.active_sws)
                logger.info("SmartStream WebSocket closed.")
            except Exception as err:
                logger.debug(f"Error closing ticker: {err}")

        logger.info("Collector daemon stopped cleanly.")

    # ==========================================================================
    # AUTHENTICATION & WEBSOCKET SETUP
    # ==========================================================================

    def _authenticate(self) -> bool:
        """Loads credentials and authenticates Angel One session."""
        creds = get_angelone_credentials()
        api_key = creds.get("api_key", "")
        client_code = creds.get("client_code", "")
        password = creds.get("password", "")
        totp_secret = creds.get("totp_secret", "")

        if not api_key or not client_code:
            logger.error("No active Angel One credentials found in credentials.json.")
            return False

        user_dict = {
            "name": client_code,
            "user_name": client_code,
            "api_key": api_key,
            "client_code": client_code,
            "password": password,
            "totp_secret": totp_secret,
        }

        logger.info(f"Authenticating collector daemon for Client [{client_code}]...")
        if login(user_dict):
            self.user = user_dict
            logger.info(f"Collector authenticated successfully as [{client_code}].")
            return True
        else:
            err = user_dict.get("last_login_error") or "Authentication failed"
            logger.error(f"Collector authentication failed: {err}")
            return False

    def _connect_websocket(self) -> None:
        """Creates SmartStream 2.0 ticker and subscribes initial token basket."""
        try:
            logger.info("Connecting SmartStream 2.0 WebSocket...")
            self.active_sws = create_user_ticker(self.user, on_tick=self._on_ws_tick)
            ok = connect_ticker(self.active_sws, threaded=True, wait_for_open=True, timeout=8.0)
            if ok:
                logger.info("SmartStream WebSocket connected successfully.")
                self._subscribe_active_tokens()
        except Exception as err:
            logger.error(f"WebSocket connection error: {err}")

    def _subscribe_active_tokens(self) -> None:
        """Sends subscription payload for all currently active tokens in basket."""
        if not self.active_sws or not self.active_tokens:
            return

        nse_tokens = [tok for tok in self.active_tokens.keys()]
        if nse_tokens:
            try:
                sub_list = [{"exchangeType": 1, "tokens": nse_tokens}]
                subscribe_tokens(
                    self.active_sws,
                    correlation_id="rel_strength_collector",
                    mode=MODE_QUOTE,
                    token_list=sub_list,
                )
                logger.info(f"Subscribed {len(nse_tokens)} tokens to SmartStream WebSocket.")
            except Exception as err:
                logger.error(f"Subscription error: {err}")

    # ==========================================================================
    # WEBSOCKET TICK INGESTION & RELATIVE % CALCULATION
    # ==========================================================================

    def _on_ws_tick(self, *args, **kwargs) -> None:
        """
        Processes real-time ticks, calculates relative percentage change from previous close,
        and caches the latest snapshot.
        Supports both (tick) and (ws, tick) callback signatures.
        """
        if len(args) == 1:
            tick = args[0]
        elif len(args) >= 2:
            tick = args[1]
        else:
            tick = kwargs.get("tick", {})

        if not isinstance(tick, dict):
            return

        token = str(tick.get("token", "")).strip()
        if not token or token not in self.active_tokens:
            return

        # 1. Resolve LTP in Rupees (float with 2 decimals)
        raw_ltp = tick.get("ltp")
        if raw_ltp is None or float(raw_ltp) <= 0:
            raw_ltp = tick.get("last_traded_price", 0.0)
        ltp = float(raw_ltp or 0.0)
        if ltp > 250000.0:  # Detect & convert raw integer paise to Rupees
            ltp = ltp / 100.0
        ltp = round(ltp, 2)
        if ltp <= 0:
            return

        meta = self.active_tokens[token]

        # 2. Resolve genuine Previous Close in Rupees from WebSocket Quote mode
        raw_close = tick.get("close")
        if raw_close is None or float(raw_close) <= 0:
            raw_close = tick.get("closed_price")
        if raw_close is not None and float(raw_close) > 0:
            c_val = float(raw_close)
            if c_val > 250000.0:  # Detect & convert raw integer paise to Rupees
                c_val = c_val / 100.0
            prev_close = round(c_val, 2)
            meta["prev_close"] = prev_close
        else:
            prev_close = float(meta.get("prev_close") or 100.0)

        # 3. Clean double-digit percentage change from previous close
        pct_change = round(((ltp - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
        volume = int(tick.get("volume", tick.get("vol_traded_today", 0)) or 0)
        now_dt = datetime.now()

        # Cache live snapshot
        self.live_state[token] = {
            "tick_time": now_dt,
            "token": token,
            "symbol": meta["symbol"],
            "ltp": ltp,
            "pct_change": pct_change,
            "volume": volume,
        }

        # Update 1-minute OHLC relative accumulator
        minute_str = now_dt.strftime("%Y-%m-%d %H:%M:00")
        if self.current_bar_minute != minute_str:
            self._flush_completed_minute_bar()
            self.current_bar_minute = minute_str

        if token not in self.minute_bars_buffer:
            self.minute_bars_buffer[token] = {
                "bar_time": minute_str,
                "token": token,
                "symbol": meta["symbol"],
                "open_pct": pct_change,
                "high_pct": pct_change,
                "low_pct": pct_change,
                "close_pct": pct_change,
                "last_ltp": ltp,
                "volume": volume,
            }
        else:
            b = self.minute_bars_buffer[token]
            b["high_pct"] = max(b["high_pct"], pct_change)
            b["low_pct"] = min(b["low_pct"], pct_change)
            b["close_pct"] = pct_change
            b["last_ltp"] = ltp
            b["volume"] = max(b["volume"], volume)

    # ==========================================================================
    # BACKGROUND FLUSH TO MYSQL
    # ==========================================================================

    def _flush_loop(self) -> None:
        """Periodically flushes in-memory snapshots to MySQL table `relative_strength_ticks`."""
        while self.running:
            try:
                time.sleep(BATCH_FLUSH_INTERVAL)
                if not self.live_state:
                    continue

                # Prepare micro-batch rows
                batch_rows = []
                for s in list(self.live_state.values()):
                    batch_rows.append((
                        s["tick_time"].strftime("%Y-%m-%d %H:%M:%S"),
                        s["token"],
                        s["symbol"],
                        s["ltp"],
                        s["pct_change"],
                        s["volume"],
                    ))

                if batch_rows:
                    self.db.insert_tick_snapshots(batch_rows)

            except Exception as err:
                logger.debug(f"Flush loop error: {err}")

    def _flush_completed_minute_bar(self) -> None:
        """Persists the aggregated 1-minute OHLC relative performance bars into MySQL."""
        if not self.minute_bars_buffer:
            return

        bars_data = []
        for b in list(self.minute_bars_buffer.values()):
            bars_data.append((
                b["bar_time"],
                b["token"],
                b["symbol"],
                round(b["open_pct"], 4),
                round(b["high_pct"], 4),
                round(b["low_pct"], 4),
                round(b["close_pct"], 4),
                round(b["last_ltp"], 2),
                b["volume"],
            ))

        if bars_data:
            self.db.upsert_1m_bars(bars_data)
            logger.debug(f"Persisted {len(bars_data)} 1m bars for minute [{bars_data[0][0]}].")

        self.minute_bars_buffer.clear()

    # ==========================================================================
    # DYNAMIC HOT-RELOAD & ZERO-RESTART SUBSCRIPTION WATCHER
    # ==========================================================================

    def _dynamic_events_loop(self) -> None:
        """Watches `basket_events` for real-time ADD/REMOVE token commands from GUI."""
        while self.running:
            try:
                time.sleep(EVENT_POLL_INTERVAL)
                events = self.db.fetch_unprocessed_collector_events()
                for ev in events:
                    ev_type = ev["event_type"]
                    tok = str(ev["token"]).strip()
                    sym = str(ev["symbol"]).strip()

                    if ev_type == "ADD":
                        self._handle_dynamic_add(tok, sym)
                    elif ev_type == "REMOVE":
                        self._handle_dynamic_remove(tok, sym)

            except Exception as err:
                logger.debug(f"Dynamic events loop error: {err}")

    def _handle_dynamic_add(self, token: str, symbol: str) -> None:
        """Hot-subscribes a newly added token to the active WebSocket session."""
        all_active = self.db.get_active_basket_tokens()
        if token in all_active:
            self.active_tokens[token] = all_active[token]

            if self.active_sws:
                try:
                    sub_list = [{"exchangeType": 1, "tokens": [token]}]
                    subscribe_tokens(
                        self.active_sws,
                        correlation_id=f"hot_add_{token}",
                        mode=MODE_QUOTE,
                        token_list=sub_list,
                    )
                    now_str = time.strftime("%H:%M:%S")
                    print(f"[{now_str}] [HOT-RELOAD] Dynamically subscribed token {token} ({symbol}) to WebSocket.")
                    sys.stdout.flush()
                except Exception as err:
                    logger.error(f"Error subscribing dynamic token {token}: {err}")

    def _handle_dynamic_remove(self, token: str, symbol: str) -> None:
        """Hot-unsubscribes a removed token from the active WebSocket session."""
        if token in self.active_tokens:
            del self.active_tokens[token]
        if token in self.live_state:
            del self.live_state[token]

        if self.active_sws:
            try:
                unsub_list = [{"exchangeType": 1, "tokens": [token]}]
                unsubscribe_tokens(
                    self.active_sws,
                    correlation_id=f"hot_remove_{token}",
                    mode=MODE_QUOTE,
                    token_list=unsub_list,
                )
                now_str = time.strftime("%H:%M:%S")
                print(f"[{now_str}] [HOT-RELOAD] Dynamically unsubscribed token {token} ({symbol}) from WebSocket.")
                sys.stdout.flush()
            except Exception as err:
                logger.error(f"Error unsubscribing dynamic token {token}: {err}")
