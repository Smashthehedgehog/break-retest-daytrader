"""
Entry point for the trading algo. Run this at ~9:25am ET so the WebSocket
connection is stable before the 9:30 open (Step 3 of deployment).
"""
import sys

import config
import db
from data_stream import start_stream


def _print_startup_banner():
    print("=" * 60)
    print("Break-and-Retest Day Trading Algo")
    print(f"  Ticker:        {config.TICKER}")
    print(f"  Trading mode:  {config.TRADING_MODE.upper()} ({config.BASE_URL})")
    print(f"  Base risk:     ${config.BASE_RISK:.2f}  |  Scaled risk: ${config.SCALED_RISK:.2f} "
          f"after ${config.PROFIT_BUFFER_TARGET:.2f} cumulative profit")
    print(f"  Reward ratio:  {config.REWARD_RATIO}R")
    if config.IS_LIVE:
        print("  *** LIVE TRADING IS ACTIVE -- REAL ORDERS WITH REAL MONEY WILL BE SUBMITTED ***")
    else:
        print("  Paper trading -- no real money at risk.")
    print("=" * 60)


def main():
    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        print("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY. Copy .env.example to .env and fill it in.", file=sys.stderr)
        sys.exit(1)

    db.init_db()
    _print_startup_banner()
    start_stream()


if __name__ == "__main__":
    main()
