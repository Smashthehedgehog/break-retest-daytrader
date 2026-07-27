"""
The First 5-Minute Break-and-Retest state machine.

Phases per trading day:
  MARKING              -- collecting the first RANGE_MINUTES 1-min bars to set the opening range
  HUNTING              -- watching for a 1-min bar to close outside the range (breakout)
  AWAITING_TOUCH        -- breakout seen; watching live trade ticks for price to revisit the broken level
  AWAITING_CONFIRMATION -- level touched; watching the next closed bar for a volume-weighted confirmation
  DONE_FOR_DAY          -- a trade was taken (or the day is over / cutoff passed) -- no more action today

Retest confirmation is volume-weighted (per user's design choice): the confirming
bar must close back in the breakout direction AND its volume must exceed
RETEST_VOLUME_MULTIPLIER times the rolling average volume of the preceding bars.
"""
from collections import deque
from datetime import datetime

import config
import db
import execution
import risk_manager


class Phase:
    MARKING = "marking"
    HUNTING = "hunting"
    AWAITING_TOUCH = "awaiting_touch"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    DONE_FOR_DAY = "done_for_day"


def _as_datetime(ts):
    if hasattr(ts, "to_pydatetime"):
        return ts.to_pydatetime()
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts))


class BreakRetestStrategy:
    def __init__(self, ticker=None, execution_module=None, initial_cumulative_pnl=0.0):
        self.ticker = ticker or config.TICKER
        self.execution = execution_module or execution
        self.cumulative_pnl = initial_cumulative_pnl

        self._current_day = None
        self._volume_window = deque(maxlen=config.VOLUME_LOOKBACK_BARS)
        self._reset_for_new_day()

    def _reset_for_new_day(self):
        self.phase = Phase.MARKING
        self._bars_today = []
        self._range_high = None
        self._range_low = None
        self._breakout_direction = None
        self._breakout_level = None
        self._touch_seen = False
        self._trades_taken_today = 0
        self._volume_window.clear()

    def _maybe_roll_day(self, dt):
        bar_date = dt.date()
        if self._current_day is None:
            self._current_day = bar_date
        elif bar_date != self._current_day:
            self._current_day = bar_date
            self._reset_for_new_day()

    def _past_new_breakout_cutoff(self, dt):
        et = dt.astimezone(config.MARKET_TZ)
        cutoff = et.replace(
            hour=config.NEW_BREAKOUT_CUTOFF_HOUR,
            minute=config.NEW_BREAKOUT_CUTOFF_MINUTE,
            second=0, microsecond=0,
        )
        return et >= cutoff

    def on_bar(self, bar):
        """bar: object with .high, .low, .close, .volume, .timestamp (1-min closed bar)."""
        dt = _as_datetime(bar.timestamp)
        self._maybe_roll_day(dt)

        if self.phase == Phase.DONE_FOR_DAY:
            return

        if self.phase != Phase.MARKING and self._past_new_breakout_cutoff(dt) and not self._touch_seen:
            self.phase = Phase.DONE_FOR_DAY
            return

        if self.phase == Phase.MARKING:
            self._bars_today.append(bar)
            if len(self._bars_today) >= config.RANGE_MINUTES:
                self._range_high = max(b.high for b in self._bars_today)
                self._range_low = min(b.low for b in self._bars_today)
                self.phase = Phase.HUNTING
            return

        if self.phase == Phase.HUNTING:
            self._volume_window.append(bar.volume)
            if bar.close > self._range_high:
                self._breakout_direction = "long"
                self._breakout_level = self._range_high
                self.phase = Phase.AWAITING_TOUCH
            elif bar.close < self._range_low:
                self._breakout_direction = "short"
                self._breakout_level = self._range_low
                self.phase = Phase.AWAITING_TOUCH
            return

        if self.phase == Phase.AWAITING_TOUCH:
            self._volume_window.append(bar.volume)
            return

        if self.phase == Phase.AWAITING_CONFIRMATION:
            confirmed = self._check_confirmation(bar)
            self._volume_window.append(bar.volume)
            if confirmed:
                self._strike(bar.close)
            else:
                # Retest failed to confirm this bar -- resume hunting for a fresh breakout.
                self._breakout_direction = None
                self._breakout_level = None
                self._touch_seen = False
                self.phase = Phase.HUNTING
            return

    def on_trade(self, trade):
        """trade: object with .price (live tick)."""
        if self.phase != Phase.AWAITING_TOUCH:
            return
        if abs(trade.price - self._breakout_level) <= config.RETEST_TOUCH_TOLERANCE:
            self._touch_seen = True
            self.phase = Phase.AWAITING_CONFIRMATION

    def _check_confirmation(self, bar):
        if not self._touch_seen:
            return False
        avg_volume = (sum(self._volume_window) / len(self._volume_window)) if self._volume_window else 0
        volume_ok = avg_volume > 0 and bar.volume > avg_volume * config.RETEST_VOLUME_MULTIPLIER
        if self._breakout_direction == "long":
            direction_ok = bar.close > self._breakout_level
        else:
            direction_ok = bar.close < self._breakout_level
        return direction_ok and volume_ok

    def _strike(self, entry_price):
        direction = self._breakout_direction
        buffer = config.STOP_BUFFER_DOLLARS
        stop_price = (
            self._breakout_level - buffer if direction == "long" else self._breakout_level + buffer
        )
        take_profit = risk_manager.calculate_take_profit(entry_price, stop_price, direction, config.REWARD_RATIO)
        risk_limit = risk_manager.get_current_risk_limit(
            self.cumulative_pnl, config.BASE_RISK, config.PROFIT_BUFFER_TARGET, config.SCALED_RISK
        )
        qty = risk_manager.calculate_shares(entry_price, stop_price, risk_limit)
        if qty <= 0:
            self.phase = Phase.DONE_FOR_DAY
            return

        side = "buy" if direction == "long" else "sell"
        order = self.execution.submit_bracket_order(
            ticker=self.ticker,
            qty=qty,
            side=side,
            limit_price=round(entry_price, 2),
            stop_price=round(stop_price, 2),
            take_profit=round(take_profit, 2),
        )
        order_id = getattr(order, "id", None)
        db.log_trade_opened(
            ticker=self.ticker,
            direction=direction,
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit_price=take_profit,
            qty=qty,
            risk_dollars=risk_limit,
            entry_order_id=order_id,
        )
        self._trades_taken_today += 1
        self.phase = Phase.DONE_FOR_DAY
