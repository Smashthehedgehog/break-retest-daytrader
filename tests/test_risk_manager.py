import math

import risk_manager


def test_calculate_shares_basic():
    # $1 risk per share, $50 risk limit -> 50 shares
    assert risk_manager.calculate_shares(entry_price=100.0, stop_loss_price=99.0, current_risk_limit=50.0) == 50


def test_calculate_shares_floors_down():
    # $3 risk per share, $50 limit -> floor(16.67) = 16
    assert risk_manager.calculate_shares(entry_price=100.0, stop_loss_price=97.0, current_risk_limit=50.0) == 16


def test_calculate_shares_zero_risk_per_share():
    assert risk_manager.calculate_shares(entry_price=100.0, stop_loss_price=100.0, current_risk_limit=50.0) == 0


def test_get_current_risk_limit_below_buffer():
    assert risk_manager.get_current_risk_limit(
        cumulative_pnl=199.99, base_risk=50.0, profit_buffer_target=200.0, scaled_risk=100.0
    ) == 50.0


def test_get_current_risk_limit_at_buffer():
    assert risk_manager.get_current_risk_limit(
        cumulative_pnl=200.0, base_risk=50.0, profit_buffer_target=200.0, scaled_risk=100.0
    ) == 100.0


def test_calculate_take_profit_long():
    tp = risk_manager.calculate_take_profit(entry_price=100.0, stop_loss_price=99.0, direction="long", reward_ratio=2.0)
    assert math.isclose(tp, 102.0)


def test_calculate_take_profit_short():
    tp = risk_manager.calculate_take_profit(entry_price=100.0, stop_loss_price=101.0, direction="short", reward_ratio=2.0)
    assert math.isclose(tp, 98.0)
