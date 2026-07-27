"""
Pure, side-effect-free risk math: position sizing and the risk-compounding
threshold. Kept free of I/O so it's trivial to unit test.
"""
import math


def calculate_shares(entry_price, stop_loss_price, current_risk_limit):
    """Shares to buy/short so that hitting the stop loses exactly current_risk_limit dollars."""
    risk_per_share = abs(entry_price - stop_loss_price)
    if risk_per_share <= 0:
        return 0
    return math.floor(current_risk_limit / risk_per_share)


def get_current_risk_limit(cumulative_pnl, base_risk, profit_buffer_target, scaled_risk):
    """Once cumulative realized P&L crosses the buffer target, scale risk up."""
    return scaled_risk if cumulative_pnl >= profit_buffer_target else base_risk


def calculate_take_profit(entry_price, stop_loss_price, direction, reward_ratio):
    """Take-profit price that is reward_ratio x the stop distance from entry."""
    risk_per_share = abs(entry_price - stop_loss_price)
    if direction == "long":
        return entry_price + risk_per_share * reward_ratio
    if direction == "short":
        return entry_price - risk_per_share * reward_ratio
    raise ValueError(f"Unknown direction: {direction!r}")
