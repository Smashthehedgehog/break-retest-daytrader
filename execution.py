"""
Order execution against Alpaca. Targets whichever account config.BASE_URL
resolves to -- paper by default, live only if the double-confirmation flags
in .env are both set (see config.py).
"""
import alpaca_trade_api as tradeapi

import config

_api = None


def get_api():
    global _api
    if _api is None:
        _api = tradeapi.REST(
            config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, config.BASE_URL, api_version="v2"
        )
    return _api


def submit_bracket_order(ticker, qty, side, limit_price, stop_price, take_profit):
    """Submit a limit entry with an attached stop-loss / take-profit bracket."""
    api = get_api()
    try:
        order = api.submit_order(
            symbol=ticker,
            qty=qty,
            side=side,
            type="limit",
            time_in_force="day",
            limit_price=limit_price,
            order_class="bracket",
            stop_loss={"stop_price": stop_price},
            take_profit={"limit_price": take_profit},
        )
        print(
            f"[execution] Bracket order submitted: {side} {qty} {ticker} @ {limit_price} "
            f"(stop {stop_price}, target {take_profit}) mode={config.TRADING_MODE}"
        )
        return order
    except Exception as e:
        print(f"[execution] Order submission FAILED: {e}")
        return None
