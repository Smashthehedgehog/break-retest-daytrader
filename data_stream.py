"""
Live WebSocket listener. Subscribes to 1-min bars and trade ticks for the
strategy's decision-making, plus trade_updates so we can detect when a
bracket order's stop-loss or take-profit leg fills and log the realized P&L
(this is what drives risk compounding -- see risk_manager.get_current_risk_limit).

No REST polling anywhere in this module -- everything is event-driven off the
WebSocket per the latency requirements in the blueprint.
"""
from alpaca_trade_api.stream import Stream

import config
import db
from strategy import BreakRetestStrategy

strategy = BreakRetestStrategy(initial_cumulative_pnl=0.0)


def _is_entry_side(direction, side):
    return (direction == "long" and side == "buy") or (direction == "short" and side == "sell")


async def trade_callback(t):
    strategy.on_trade(t)


async def bar_callback(b):
    print(f"[data_stream] 1-Min Bar Closed: high={b.high} low={b.low} close={b.close} volume={b.volume}")
    strategy.on_bar(b)


async def trade_updates_callback(update):
    if update.event != "fill":
        return

    order = update.order
    symbol = order.get("symbol")
    open_trade = db.find_open_trade_for_ticker(symbol)
    if not open_trade:
        return

    side = order.get("side")
    if _is_entry_side(open_trade["direction"], side):
        return  # this was the entry leg filling, not a closing leg

    filled_avg_price = float(order.get("filled_avg_price") or 0)
    qty = open_trade["qty"]
    if open_trade["direction"] == "long":
        pnl = (filled_avg_price - open_trade["entry_price"]) * qty
    else:
        pnl = (open_trade["entry_price"] - filled_avg_price) * qty

    db.close_trade(open_trade["id"], pnl)
    strategy.cumulative_pnl += pnl
    print(f"[data_stream] Trade closed: {symbol} pnl={pnl:.2f} cumulative={strategy.cumulative_pnl:.2f}")


def start_stream():
    strategy.cumulative_pnl = db.get_cumulative_pnl()
    stream = Stream(
        config.ALPACA_API_KEY,
        config.ALPACA_SECRET_KEY,
        base_url=config.BASE_URL,
        data_feed=config.DATA_FEED,
        raw_data=False,
    )
    stream.subscribe_trades(trade_callback, config.TICKER)
    stream.subscribe_bars(bar_callback, config.TICKER)
    stream.subscribe_trade_updates(trade_updates_callback)
    stream.run()
