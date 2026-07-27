"""
Central configuration. All secrets and tunables are read from environment
variables (populated from a local `.env` file via python-dotenv) so that
nothing sensitive ever ends up committed to this public repository.

Copy `.env.example` to `.env` and fill in your own values before running
anything else.
"""
import os
import sys
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _get_float(name, default):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


# --- Alpaca credentials ---
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")

# --- Trading mode: "paper" (default/safe) or "live" ---
_RAW_MODE = os.getenv("TRADING_MODE", "paper").strip().lower()
TRADING_MODE = _RAW_MODE if _RAW_MODE in ("paper", "live") else "paper"
I_UNDERSTAND_LIVE_RISK = _get_bool("I_UNDERSTAND_LIVE_RISK", False)

# Live trading requires BOTH TRADING_MODE=live AND the explicit risk
# acknowledgement flag. If either is missing, we hard-fall-back to paper.
IS_LIVE = TRADING_MODE == "live" and I_UNDERSTAND_LIVE_RISK

if TRADING_MODE == "live" and not I_UNDERSTAND_LIVE_RISK:
    print(
        "[config] TRADING_MODE=live was set but I_UNDERSTAND_LIVE_RISK is not "
        "true. Refusing to enable live trading -- falling back to PAPER mode. "
        "Set I_UNDERSTAND_LIVE_RISK=true in .env only if you intend to trade "
        "real money and accept full responsibility for doing so.",
        file=sys.stderr,
    )

BASE_URL = "https://api.alpaca.markets" if IS_LIVE else "https://paper-api.alpaca.markets"
# SIP requires a paid live market-data subscription; IEX is the free feed used with paper accounts.
DATA_FEED = "sip" if IS_LIVE else "iex"

# --- Strategy parameters ---
TICKER = os.getenv("TICKER", "SPY").strip().upper()
BASE_RISK = _get_float("BASE_RISK", 50.00)
REWARD_RATIO = _get_float("REWARD_RATIO", 2.0)

# --- Compounding buffer parameters ---
PROFIT_BUFFER_TARGET = _get_float("PROFIT_BUFFER_TARGET", 200.00)
SCALED_RISK = _get_float("SCALED_RISK", 100.00)

# --- Break-and-retest mechanics (not user-configurable via .env; edit here) ---
RANGE_MINUTES = 5            # Length of the opening range block (9:30-9:35 ET)
RETEST_VOLUME_MULTIPLIER = 1.2   # Confirming bar's volume must exceed this x the rolling average
VOLUME_LOOKBACK_BARS = 10        # Rolling average window for volume confirmation
MAX_TRADES_PER_DAY = 1           # One strike per day, per the base strategy
RETEST_TOUCH_TOLERANCE = 0.02    # Dollars of tolerance for "price touched the level"
STOP_BUFFER_DOLLARS = 0.10       # Stop placed this far beyond the broken level (not the opposite side of the range)

# Stop hunting for NEW breakouts this many minutes before the 4:00pm ET close.
# Already-open bracket orders are managed by the broker regardless of this cutoff.
MARKET_TZ = ZoneInfo("America/New_York")
NEW_BREAKOUT_CUTOFF_HOUR = 15
NEW_BREAKOUT_CUTOFF_MINUTE = 45

DB_PATH = os.getenv("DB_PATH", "trade_history.db")
