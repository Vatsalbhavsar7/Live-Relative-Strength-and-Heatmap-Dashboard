"""
add_token.py
------------
Command-line utility to dynamically add or remove any stock from the live basket
without stopping or restarting `run_collector.py` or `run_dashboard.py`.

Usage:
    python add_token.py BSE              # Look up by symbol and add
    python add_token.py 19585            # Look up by token and add
    python add_token.py IDEA 14366       # Add by symbol and explicit token
    python add_token.py --remove BSE     # Dynamically remove from live basket
    python add_token.py --list           # List all currently active tokens
"""

import argparse
import sys
from basket_manager import BasketManager
from db_manager import DatabaseManager


def main():
    parser = argparse.ArgumentParser(description="Zero-Restart Token Hot-Reload Utility")
    parser.add_argument("query", nargs="?", help="Symbol (e.g. BSE, IDEA, TATAMOTORS) or numeric token ID")
    parser.add_argument("--token", "-t", help="Explicit token ID if known", default=None)
    parser.add_argument("--remove", "-r", action="store_true", help="Remove the token from the active basket")
    parser.add_argument("--list", "-l", action="store_true", help="List all currently active basket tokens")
    args = parser.parse_args()

    db = DatabaseManager()
    basket_mgr = BasketManager(db=db)

    # 1. List active tokens
    if args.list:
        active = db.get_active_basket_tokens()
        print(f"\nCurrently Active Basket ({len(active)} instruments):")
        print("-" * 65)
        print(f"{'TOKEN':<10} | {'SYMBOL':<18} | {'EXCHANGE':<8} | {'PREV CLOSE':<10}")
        print("-" * 65)
        for tok, m in sorted(active.items(), key=lambda x: x[1].get("symbol", "")):
            print(f"{tok:<10} | {m.get('symbol', ''):<18} | {m.get('exchange', 'NSE'):<8} | Rs. {float(m.get('prev_close', 0)):,.2f}")
        print("-" * 65 + "\n")
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    query = args.query.strip().upper()

    # 2. Dynamic Remove
    if args.remove:
        active = db.get_active_basket_tokens()
        target_token = None
        target_symbol = query
        if query in active:
            target_token = query
            target_symbol = active[query].get("symbol", query)
        else:
            for tok, m in active.items():
                if m.get("symbol", "").upper() == query or m.get("symbol", "").upper() == f"{query}-EQ":
                    target_token = tok
                    target_symbol = m.get("symbol")
                    break

        if not target_token:
            print(f"[-] Error: Instrument '{query}' is not currently in the active basket.")
            sys.exit(1)

        ok = db.remove_token_dynamically(target_token)
        if ok:
            print(f"[+] Successfully emitted REMOVE event for {target_symbol} (Token {target_token}).")
            print("   -> Live `run_collector.py` will unsubscribe within 2 seconds.")
            print("   -> Live `run_dashboard.py` will remove it from the chart and watchlist.")
        else:
            print(f"[-] Failed to remove token {target_token}.")
        return

    # 3. Dynamic Add
    print(f"[*] Resolving instrument for query: '{query}'...")
    candidate = basket_mgr.resolve_instrument(query)
    if not candidate and args.token:
        candidate = {
            "token": str(args.token).strip(),
            "symbol": f"{query}-EQ" if not query.endswith("-EQ") else query,
            "name": query,
            "exchange": "NSE",
            "prev_close": 100.0,
            "market_cap_crores": 10000.0,
        }

    if not candidate:
        print(f"[-] Could not resolve instrument '{query}'. Please specify an explicit token with --token <ID>.")
        sys.exit(1)

    print(f"  Found: {candidate['symbol']} (Token: {candidate['token']}) | Exch: {candidate['exchange']} | Prev Close: Rs. {candidate['prev_close']:,.2f}")
    ok = db.add_token_dynamically(candidate)
    if ok:
        print(f"[+] Successfully emitted ADD event for {candidate['symbol']} (Token {candidate['token']})!")
        print("   -> Live `run_collector.py` will hot-subscribe via WebSocket within 2 seconds.")
        print("   -> Live `run_dashboard.py` will display its live line and heatmap tile without restarting.")
    else:
        print(f"[-] Failed to register token {candidate['token']} in MySQL.")


if __name__ == "__main__":
    main()
