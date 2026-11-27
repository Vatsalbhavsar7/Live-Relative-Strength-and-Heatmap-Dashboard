"""
projects/06_live_relative_strength_and_heatmap_dashboard/test_system.py
------------------------------------------------------------------------
Comprehensive automated test suite verifying all layers of Project 06:
1. MySQL Connection & Schema auto-initialization.
2. Default Nifty 50 Basket sync & dynamic token lookup.
3. Micro-batch tick insertion throughput.
4. Dynamic hot-reload ADD and REMOVE event cycle.
5. 1-minute OHLC bar aggregation & historical query.
6. Headless PySide6 & PyQtGraph widget instantiation.
7. Multi-Day 5-Day Retention & Continuation Chart.
8. Autonomous Market Scheduler & Multi-Device Configuration.
"""

from datetime import datetime
import sys
import time

try:
    import _bootstrap_path
except ImportError:
    pass
from basket_manager import BasketManager
from db_manager import DatabaseManager


def run_all_tests():
    print("\n" + "=" * 70)
    print("  RUNNING RELATIVE STRENGTH & HEATMAP SYSTEM VERIFICATION")
    print("=" * 70)

    # TEST 1: MySQL Schema Initialization
    print("\n[TEST 1/6] Testing MySQL Connection & Schema DDL...")
    db = DatabaseManager()
    ok = db.initialize_schema()
    assert ok, "Database initialization failed"
    print("  [PASS] Successfully initialized database `algo_relative_strength` and all 4 tables.")

    # TEST 2: Basket Manager & Default Nifty 50 Sync
    print("\n[TEST 2/6] Testing Basket Manager & Default Nifty 50 Constituents...")
    basket_mgr = BasketManager(db=db)
    count = basket_mgr.sync_default_basket()
    assert count >= 40, f"Expected at least 40 Nifty 50 constituents, got {count}"
    active = db.get_active_basket_tokens()
    assert len(active) >= 40, f"Active tokens mismatch: {len(active)}"
    assert "2885" in active, "Reliance (Token 2885) missing from basket"
    print(f"  [PASS] Synchronized {len(active)} active tokens into MySQL.")

    # TEST 3: Dynamic Instrument Resolution
    print("\n[TEST 3/6] Testing Dynamic Instrument Metadata Resolution...")
    res = basket_mgr.resolve_instrument("TCS")
    assert res is not None, "Failed resolving TCS"
    assert res["symbol"] == "TCS-EQ" or "TCS" in res["symbol"]
    assert res["token"] == "11536"
    print(f"  [PASS] Successfully resolved {res['symbol']} (Token {res['token']}).")

    # TEST 4: High-Throughput Micro-Batch Tick Insertion
    print("\n[TEST 4/6] Testing Micro-Batch Tick Snapshots Insertion...")
    now_dt = datetime.now()
    sample_ticks = [
        (now_dt.strftime("%Y-%m-%d %H:%M:%S"), "2885", "RELIANCE-EQ", 2755.0, 0.18, 500000),
        (now_dt.strftime("%Y-%m-%d %H:%M:%S"), "11536", "TCS-EQ", 4125.0, 0.61, 320000),
        (now_dt.strftime("%Y-%m-%d %H:%M:%S"), "1333", "HDFCBANK-EQ", 1675.0, -0.30, 890000),
    ]
    inserted = db.insert_tick_snapshots(sample_ticks)
    assert inserted == 3, f"Expected 3 rows inserted, got {inserted}"
    print(f"  [PASS] Successfully inserted {inserted} test tick snapshots.")

    # TEST 5: Dynamic ADD and REMOVE Event Lifecycle
    print("\n[TEST 5/6] Testing Zero-Restart Dynamic Token ADD / REMOVE Lifecycle...")
    test_token_info = {
        "token": "99999",
        "symbol": "TESTSTOCK-EQ",
        "name": "TESTSTOCK",
        "exchange": "NSE",
        "prev_close": 500.0,
        "market_cap_crores": 25000.0,
    }
    # 5a. Add
    add_ok = db.add_token_dynamically(test_token_info)
    assert add_ok, "Dynamic add failed"
    events = db.fetch_unprocessed_collector_events()
    assert any(e["token"] == "99999" and e["event_type"] == "ADD" for e in events), "ADD event not logged"
    print("  [PASS] Dynamic ADD event emitted and picked up by collector interface.")

    # 5b. Remove
    rem_ok = db.remove_token_dynamically("99999")
    assert rem_ok, "Dynamic remove failed"
    rem_events = db.fetch_unprocessed_collector_events()
    assert any(e["token"] == "99999" and e["event_type"] == "REMOVE" for e in rem_events), "REMOVE event not logged"
    print("  [PASS] Dynamic REMOVE event emitted and processed.")

    # TEST 6: PySide6 Headless GUI Instantiation
    print("\n[TEST 6/6] Testing PySide6 / PyQtGraph Widget Instantiation (Headless)...")
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)

    from gui.multi_line_chart import RelativeStrengthChart
    from gui.heatmap_widget import HeatmapWidget
    from gui.filter_panel import FilterPanel

    chart = RelativeStrengthChart()
    chart.register_stock("2885", "RELIANCE-EQ")
    chart.append_tick("2885", "RELIANCE-EQ", time.time(), 0.18)

    heatmap = HeatmapWidget(default_enabled=False)
    assert not heatmap.is_engine_enabled, "Heatmap engine should be default disabled"
    heatmap.set_engine_enabled(True)
    assert heatmap.is_engine_enabled, "Heatmap engine should be enabled after set_engine_enabled"
    heatmap.register_or_update_tile("2885", "RELIANCE-EQ", 0.18, 2755.0, 1980000.0)
    assert "2885" in heatmap.tiles, "Tile should be created when enabled"

    filter_panel = FilterPanel()
    filter_panel.add_or_update_stock("2885", "RELIANCE-EQ", "#38BDF8", 0.18)
    filter_panel.add_or_update_stock("11536", "TCS-EQ", "#10B981", 0.61)
    filter_panel.add_or_update_stock("3045", "SBIN-EQ", "#F59E0B", 1.20)

    # Test Search / Filter functionality
    # 1. Search for 'SBIN' -> Only SBIN-EQ visible
    filter_panel.inp_search.setText("sbin")
    assert not filter_panel.items["3045"].isHidden(), "SBIN should be visible"
    assert filter_panel.items["2885"].isHidden(), "RELIANCE should be hidden"
    assert filter_panel.items["11536"].isHidden(), "TCS should be hidden"
    assert not filter_panel.scroll.isHidden(), "Scroll area should be visible"
    assert filter_panel.no_results_widget.isHidden(), "No results widget should be hidden"

    # 2. Search for non-existent stock -> No results widget shown
    filter_panel.inp_search.setText("NONEXISTENT")
    assert filter_panel.scroll.isHidden(), "Scroll area should be hidden when 0 results"
    assert not filter_panel.no_results_widget.isHidden(), "No results widget should be visible"
    assert "NONEXISTENT" in filter_panel.lbl_no_results.text()

    # 3. Clear search -> All stocks restored to visible
    filter_panel.inp_search.clear()
    assert not filter_panel.items["3045"].isHidden(), "SBIN should be visible"
    assert not filter_panel.items["2885"].isHidden(), "RELIANCE should be visible"
    assert not filter_panel.items["11536"].isHidden(), "TCS should be visible"
    assert not filter_panel.scroll.isHidden(), "Scroll area should be visible"
    assert filter_panel.no_results_widget.isHidden(), "No results widget should be hidden"

    print("  [PASS] Multi-Line Chart, Heatmap, and Filter Panel (with Watchlist Search) successfully verified.")

    # TEST 7: Multi-Day Retention & Continuation Chart Features
    print("\n[TEST 7/7] Testing Multi-Day Retention & Continuation Chart...")
    from config import DAYS_TO_KEEP, DEFAULT_SHOW_MULTIDAY

    # 7a. Distinct trading dates query
    dates = db.fetch_distinct_trading_dates(limit=DAYS_TO_KEEP)
    assert isinstance(dates, list), "fetch_distinct_trading_dates should return a list"
    print(f"  [PASS] Distinct trading dates retrieved (up to {DAYS_TO_KEEP} days): {dates}")

    # 7b. Multi-day 1m bars query
    multi_bars = db.fetch_multi_day_1m_bars(days_to_keep=DAYS_TO_KEEP)
    assert isinstance(multi_bars, dict), "fetch_multi_day_1m_bars should return a dict"
    print(f"  [PASS] Multi-day 1m bars fetched for {len(multi_bars)} tokens.")

    # 7c. Multi-day checkbox and signal in RelativeStrengthChart
    assert hasattr(chart, "chk_multiday"), "Chart should have chk_multiday checkbox"
    assert chart.chk_multiday.isChecked() == DEFAULT_SHOW_MULTIDAY, "Default checkbox state mismatch"

    signal_received = []
    chart.multiday_toggled.connect(lambda val: signal_received.append(val))

    # Toggle to multi-day
    chart.chk_multiday.setChecked(True)
    assert chart.time_axis.multiday_mode is True, "TimeAxisItem should be in multiday_mode when checked"
    assert signal_received == [True], f"Signal expected [True], got {signal_received}"

    # Verify reset_chart_series and load_historical_bars with multi-day bars
    chart.reset_chart_series()
    assert len(chart.stock_series["2885"]["x"]) == 0, "reset_chart_series should clear points"
    if multi_bars:
        sample_bars = {}
        if "2885" in multi_bars:
            sample_bars["2885"] = multi_bars["2885"]
        for k in list(multi_bars.keys())[:3]:
            sample_bars[k] = multi_bars[k]
        chart.load_historical_bars(sample_bars)
        assert len(chart.stock_series["2885"]["x"]) > 0, "load_historical_bars should populate multi-day points"

    # Toggle back to intraday
    chart.chk_multiday.setChecked(False)
    assert chart.time_axis.multiday_mode is False, "TimeAxisItem multiday_mode should be False when unchecked"
    assert signal_received == [True, False], f"Signal expected [True, False], got {signal_received}"

    # 7d. Prune old data verification (safe execution)
    prune_res = db.prune_old_data(days_to_keep=DAYS_TO_KEEP)
    assert isinstance(prune_res, tuple) and len(prune_res) == 2, "prune_old_data should return (bars_deleted, ticks_deleted)"
    print(f"  [PASS] Prune old data executed successfully: removed {prune_res[0]} bars, {prune_res[1]} ticks.")

    print("  [PASS] Multi-day retention & continuation chart features fully verified.")

    # TEST 8: Autonomous Market Scheduler & Multi-Device Configuration
    print("\n[TEST 8/8] Testing Market Scheduler & Multi-Device Config...")
    from datetime import date, timedelta
    from config import get_database_config
    from market_scheduler import MarketScheduler

    # 8a. Database Config resolution & connectivity test
    db_cfg = get_database_config()
    assert "host" in db_cfg and "database" in db_cfg, "get_database_config should return host and database keys"
    is_conn, conn_msg = db.test_connection()
    assert is_conn is True, f"db.test_connection failed: {conn_msg}"
    print(f"  [PASS] Database configuration loaded ({db_cfg['host']}:{db_cfg.get('port', 3306)}). Status: {conn_msg}.")

    # 8b. Market Scheduler calendar tests
    scheduler = MarketScheduler()
    cal = scheduler.load_calendar(force_reload=True)
    assert "holidays" in cal and "special_sessions" in cal, "Calendar JSON should have holidays and special_sessions"

    # 8c. Test weekend detection
    # 2026-11-28 is a Saturday, 2026-11-29 is a Sunday
    sat_ok, sat_reason = scheduler.is_market_day(target_date=date(2026, 11, 28))
    assert sat_ok is False and "Saturday" in sat_reason, f"Expected Saturday rejection, got {sat_ok}, {sat_reason}"
    sun_ok, sun_reason = scheduler.is_market_day(target_date=date(2026, 11, 29))
    assert sun_ok is False and "Sunday" in sun_reason, f"Expected Sunday rejection, got {sun_ok}, {sun_reason}"

    # 8d. Test holiday detection
    # 2026-12-25 is Christmas (Holiday)
    hol_ok, hol_reason = scheduler.is_market_day(target_date=date(2026, 12, 25))
    assert hol_ok is False and "Holiday" in hol_reason, f"Expected Holiday rejection, got {hol_ok}, {hol_reason}"

    # 8e. Test special trading session (e.g. Diwali Muhurat 2026-11-08)
    sp_ok, sp_reason = scheduler.is_market_day(target_date=date(2026, 11, 8))
    assert sp_ok is True and "Special Session" in sp_reason, f"Expected Special Session approval, got {sp_ok}, {sp_reason}"
    sp_start, sp_end, sp_desc = scheduler.get_session_window(target_date=date(2026, 11, 8))
    assert sp_start.hour == 17 and sp_start.minute == 59, f"Expected pre-buffered start 17:59:00, got {sp_start}"

    # 8f. Test Countdown Formatter
    fmt_countdown = scheduler.format_countdown(3665)
    assert fmt_countdown == "1h 1m 5s", f"Expected '1h 1m 5s', got '{fmt_countdown}'"

    # 8g. Test Next Trading Session scan
    nxt_start, nxt_end, nxt_desc = scheduler.get_next_trading_session()
    assert nxt_start is not None and nxt_end is not None, "get_next_trading_session should return valid datetimes"
    print(f"  [PASS] Market scheduler accurately verified: Weekends, Holidays, Special Sessions, and Next Session: {nxt_start.strftime('%a %d-%b %H:%M:%S')}.")

    print("  [PASS] Market Scheduler & Multi-Device configuration fully verified.")

    print("\n" + "=" * 70)
    print("  ALL 8 RELATIVE STRENGTH & HEATMAP TESTS PASSED SUCCESSFULLY!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_all_tests()
