"""
core/smartstream_ws.py
----------------------
Standalone Angel One SmartStream WebSocket 2.0 Streaming Client.
Pipes binary quote ticks with normalized price scaling (paise -> Rupees).
"""

import json
import struct
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from core.logger import get_logger

logger = get_logger("core.smartstream")

# Subscription Modes
MODE_LTP = 1
MODE_QUOTE = 2
MODE_SNAP_QUOTE = 3
MODE_DEPTH = 4

# Exchange Types
NSE_CM = 1
NSE_FO = 2
BSE_CM = 3
BSE_FO = 4
MCX_FO = 5
NCX_FO = 7
CDE_FO = 13

EXCHANGE_MAP = {
    NSE_CM: "NSE",
    NSE_FO: "NFO",
    BSE_CM: "BSE",
    BSE_FO: "BFO",
    MCX_FO: "MCX",
    NCX_FO: "NCDEX",
    CDE_FO: "CDS",
}


def parse_tick_data(raw_data: Any) -> Dict[str, Any]:
    """Converts a raw SmartWebSocketV2 binary packet into a clean normalized tick dict."""
    recv_ms = int(time.time() * 1000)
    if not isinstance(raw_data, dict):
        return {"received_at_ms": recv_ms, "raw": raw_data}

    exch_type = int(raw_data.get("exchange_type", NSE_CM) or NSE_CM)
    divisor = 10000000.0 if exch_type == CDE_FO else 100.0
    sub_mode = int(raw_data.get("subscription_mode", MODE_LTP) or MODE_LTP)

    raw_ltp = raw_data.get("last_traded_price")
    ltp = round(float(raw_ltp) / divisor, 2) if raw_ltp is not None else (
        round(float(raw_data["ltp"]) / (divisor if float(raw_data["ltp"]) > 250000 else 1.0), 2)
        if raw_data.get("ltp") is not None else 0.0
    )

    tick: Dict[str, Any] = {
        "token": str(raw_data.get("token", "")).strip(),
        "exchange": EXCHANGE_MAP.get(exch_type, "NSE"),
        "subscription_mode": sub_mode,
        "ltp": ltp,
        "received_at_ms": recv_ms,
    }

    if sub_mode in (MODE_QUOTE, MODE_SNAP_QUOTE):
        open_raw = raw_data.get("open_price_of_the_day")
        high_raw = raw_data.get("high_price_of_the_day")
        low_raw = raw_data.get("low_price_of_the_day")
        close_raw = raw_data.get("closed_price")

        tick.update({
            "open": round(float(open_raw) / divisor, 2) if open_raw is not None else None,
            "high": round(float(high_raw) / divisor, 2) if high_raw is not None else None,
            "low": round(float(low_raw) / divisor, 2) if low_raw is not None else None,
            "close": round(float(close_raw) / divisor, 2) if close_raw is not None else None,
            "volume": raw_data.get("volume_trade_for_the_day", 0),
        })

    return tick


def create_user_ticker(
    user: Dict[str, Any],
    on_tick: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_connect: Optional[Callable[[], None]] = None,
    on_error: Optional[Callable[[Any], None]] = None,
    on_close: Optional[Callable[[], None]] = None,
) -> Optional[Any]:
    """Creates an authenticated SmartWebSocketV2 instance for streaming quotes."""
    try:
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2
    except ImportError:
        logger.error("SmartWebSocketV2 not found. Ensure `pip install smartapi-python` is installed.")
        return None

    auth_token = str(user.get("auth_token", "")).replace("Bearer ", "").strip()
    api_key = str(user.get("api_key", "")).strip()
    client_code = str(user.get("client_code", "")).strip()
    feed_token = str(user.get("feed_token", "")).strip()

    if not all([auth_token, api_key, client_code, feed_token]):
        logger.error(f"Cannot initialize ticker: missing tokens for client [{client_code}].")
        return None

    try:
        sws = SmartWebSocketV2(
            auth_token=auth_token,
            api_key=api_key,
            client_code=client_code,
            feed_token=feed_token,
            max_retry_attempt=5,
            retry_strategy=1,
            retry_delay=2,
            retry_multiplier=2,
            retry_duration=30,
        )
        sws._connected_event = threading.Event()
        sws._closed_event = threading.Event()
        sws._intentional_close = False

        def _handle_open():
            logger.info("SmartStream WebSocket connection established.")
            sws._connected_event.set()
            if on_connect:
                on_connect()

        def _handle_tick(raw_data):
            try:
                norm_tick = parse_tick_data(raw_data)
                if on_tick:
                    on_tick(norm_tick)
            except Exception as err:
                logger.debug(f"Tick processing error: {err}")

        def _handle_error(err):
            logger.warning(f"SmartStream WebSocket error: {err}")
            if on_error:
                on_error(err)

        def _handle_close():
            logger.info("SmartStream WebSocket closed.")
            sws._closed_event.set()
            if on_close:
                on_close()

        sws.on_open = _handle_open
        sws.on_data = _handle_tick
        sws.on_error = _handle_error
        sws.on_close = _handle_close

        return sws
    except Exception as exc:
        logger.error(f"Error creating SmartWebSocketV2: {exc}")
        return None


def connect_ticker(sws: Any, threaded: bool = True, wait_for_open: bool = True, timeout: float = 8.0) -> bool:
    """Connects ticker and waits for handshake completion."""
    if not sws:
        return False
    try:
        sws._connected_event.clear()
        if threaded:
            t = threading.Thread(target=sws.connect, daemon=True, name="SmartStreamThread")
            t.start()
        else:
            sws.connect()

        if wait_for_open:
            opened = sws._connected_event.wait(timeout=timeout)
            if not opened:
                logger.warning("SmartStream WebSocket open timeout elapsed.")
                return False
        return True
    except Exception as exc:
        logger.error(f"WebSocket connect error: {exc}")
        return False


def subscribe_tokens(sws: Any, correlation_id: str, mode: int, token_list: List[Dict[str, Any]]) -> bool:
    """Sends token subscription payload to the open SmartStream WebSocket."""
    if not sws:
        return False
    try:
        sws.subscribe(correlation_id=correlation_id, mode=mode, token_list=token_list)
        return True
    except Exception as exc:
        logger.error(f"Subscribe tokens error: {exc}")
        return False


def unsubscribe_tokens(sws: Any, correlation_id: str, mode: int, token_list: List[Dict[str, Any]]) -> bool:
    """Sends token unsubscription payload to the open SmartStream WebSocket."""
    if not sws:
        return False
    try:
        sws.unsubscribe(correlation_id=correlation_id, mode=mode, token_list=token_list)
        return True
    except Exception as exc:
        logger.error(f"Unsubscribe tokens error: {exc}")
        return False


def close_ticker(sws: Any) -> None:
    """Gracefully terminates ticker connection."""
    if not sws:
        return
    try:
        sws._intentional_close = True
        sws.close_connection()
    except Exception as exc:
        logger.debug(f"Error closing ticker: {exc}")
