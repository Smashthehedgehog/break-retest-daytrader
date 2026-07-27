from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from strategy import BreakRetestStrategy, Phase

# 9:30 ET on a Tuesday, expressed in UTC (ET is UTC-5 in January, no DST).
DAY1_930_UTC = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)


def bar(minute_offset, high, low, close, volume, day_start=DAY1_930_UTC):
    return SimpleNamespace(
        high=high, low=low, close=close, volume=volume,
        timestamp=day_start + timedelta(minutes=minute_offset),
    )


def trade(price, minute_offset=6, day_start=DAY1_930_UTC):
    return SimpleNamespace(price=price, timestamp=day_start + timedelta(minutes=minute_offset))


@pytest.fixture
def fake_execution():
    exec_mod = MagicMock()
    exec_mod.submit_bracket_order.return_value = SimpleNamespace(id="fake-order-1")
    return exec_mod


@pytest.fixture
def strategy(fake_execution, isolated_db):
    return BreakRetestStrategy(ticker="SPY", execution_module=fake_execution, initial_cumulative_pnl=0.0)


def _mark_range(strategy, high=101.0, low=99.0):
    """Feed 5 bars that establish a 99-101 opening range."""
    for i in range(5):
        strategy.on_bar(bar(i, high=high, low=low, close=100.0, volume=100))


def test_marks_opening_range_then_hunts(strategy):
    _mark_range(strategy)
    assert strategy.phase == Phase.HUNTING
    assert strategy._range_high == 101.0
    assert strategy._range_low == 99.0


def test_full_breakout_retest_confirm_strikes(strategy, fake_execution, isolated_db):
    _mark_range(strategy)

    # Breakout bar closes above range high (101) -> awaiting retest touch.
    strategy.on_bar(bar(5, high=101.6, low=101.0, close=101.5, volume=500))
    assert strategy.phase == Phase.AWAITING_TOUCH

    # One more bar while awaiting touch (builds volume history).
    strategy.on_bar(bar(6, high=101.6, low=101.2, close=101.4, volume=500))

    # Live tick touches the broken level (101.0) -> awaiting volume-confirmed close.
    strategy.on_trade(trade(price=101.0, minute_offset=7))
    assert strategy.phase == Phase.AWAITING_CONFIRMATION

    # Confirming bar: closes back above the level AND volume >> rolling average (500).
    strategy.on_bar(bar(8, high=101.8, low=101.0, close=101.6, volume=700))

    assert strategy.phase == Phase.DONE_FOR_DAY
    fake_execution.submit_bracket_order.assert_called_once()
    call_kwargs = fake_execution.submit_bracket_order.call_args.kwargs
    assert call_kwargs["side"] == "buy"
    assert call_kwargs["limit_price"] == 101.6
    assert call_kwargs["stop_price"] == 100.90  # breakout level (101.0) - 0.10 buffer

    trades = isolated_db.get_all_trades()
    assert len(trades) == 1
    assert trades[0]["direction"] == "long"


def test_low_volume_confirmation_fails_and_resumes_hunting(strategy, fake_execution):
    _mark_range(strategy)
    strategy.on_bar(bar(5, high=101.6, low=101.0, close=101.5, volume=500))
    strategy.on_trade(trade(price=101.0, minute_offset=6))
    assert strategy.phase == Phase.AWAITING_CONFIRMATION

    # Closes in the right direction but volume is NOT above the 1.2x threshold.
    strategy.on_bar(bar(7, high=101.6, low=101.0, close=101.6, volume=300))

    assert strategy.phase == Phase.HUNTING
    fake_execution.submit_bracket_order.assert_not_called()


def test_short_breakout(strategy, fake_execution):
    _mark_range(strategy)
    # Breakout bar closes below range low (99) -> short setup.
    strategy.on_bar(bar(5, high=99.0, low=98.4, close=98.5, volume=500))
    assert strategy._breakout_direction == "short"

    strategy.on_trade(trade(price=99.0, minute_offset=6))
    assert strategy.phase == Phase.AWAITING_CONFIRMATION

    strategy.on_bar(bar(7, high=99.0, low=98.3, close=98.4, volume=700))
    assert strategy.phase == Phase.DONE_FOR_DAY
    call_kwargs = fake_execution.submit_bracket_order.call_args.kwargs
    assert call_kwargs["side"] == "sell"
    assert call_kwargs["stop_price"] == 99.10  # breakout level (99.0) + 0.10 buffer


def test_one_trade_per_day_cap(strategy, fake_execution):
    _mark_range(strategy)
    strategy.on_bar(bar(5, high=101.6, low=101.0, close=101.5, volume=500))
    strategy.on_trade(trade(price=101.0, minute_offset=6))
    strategy.on_bar(bar(7, high=101.8, low=101.0, close=101.6, volume=700))
    assert strategy.phase == Phase.DONE_FOR_DAY

    # Any further bars/ticks today must not trigger a second order.
    strategy.on_bar(bar(8, high=105.0, low=104.0, close=104.5, volume=900))
    strategy.on_trade(trade(price=104.5, minute_offset=9))
    fake_execution.submit_bracket_order.assert_called_once()


def test_new_day_resets_state(strategy):
    _mark_range(strategy)
    strategy.on_bar(bar(5, high=101.6, low=101.0, close=101.5, volume=500))
    assert strategy.phase == Phase.AWAITING_TOUCH

    day2_930_utc = DAY1_930_UTC + timedelta(days=1)
    strategy.on_bar(bar(0, high=102.0, low=100.0, close=101.0, volume=100, day_start=day2_930_utc))
    assert strategy.phase == Phase.MARKING
    assert strategy._breakout_direction is None


def test_no_new_breakout_after_cutoff(strategy, fake_execution):
    _mark_range(strategy)
    # 15:50 ET on day 1 (14:30 UTC + 6h20m = 20:50 UTC), well past the 15:45 ET cutoff.
    late_bar = bar(6 * 60 + 20, high=101.6, low=101.0, close=101.5, volume=500)
    strategy.on_bar(late_bar)
    assert strategy.phase == Phase.DONE_FOR_DAY
    fake_execution.submit_bracket_order.assert_not_called()
