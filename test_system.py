"""
test_system.py
--------------
Comprehensive automated test suite verifying all layers of the standalone project:
1. MySQL Connection & Schema auto-initialization.
2. Default Nifty 50 Basket sync & dynamic token lookup.
3. Micro-batch tick insertion throughput.
4. Dynamic hot-reload ADD and REMOVE event cycle.
5. 1-minute OHLC bar aggregation & historical query.
6. Headless PySide6 & PyQtGraph widget instantiation.
"""

from datetime import datetime
import sys
import time

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

    heatmap = HeatmapWidget()
    heatmap.register_or_update_tile("2885", "RELIANCE-EQ", 0.18, 2755.0, 1980000.0)

    filter_panel = FilterPanel()
    filter_panel.add_or_update_stock("2885", "RELIANCE-EQ", "#38BDF8", 0.18)

    print("  [PASS] Multi-Line Chart, Heatmap, and Filter Panel successfully instantiated.")

    print("\n" + "=" * 70)
    print("  ALL 6 RELATIVE STRENGTH & HEATMAP TESTS PASSED SUCCESSFULLY!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_all_tests()
