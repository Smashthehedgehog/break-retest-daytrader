# Break-and-Retest Day Trading Algo

An automated implementation of the **First 5-Minute Break-and-Retest** intraday
strategy: mark the opening 5-minute range, wait for a breakout, wait for price
to retest the broken level, confirm with volume, and strike with a
risk-sized bracket order (entry + stop-loss + take-profit).

Built from an internal strategy blueprint. See [Deviations from the original blueprint](#deviations-from-the-original-blueprint)
for where and why this implementation differs from that spec.

## ⚠️ Disclaimer

This is a personal / educational software project, **not financial advice**,
and comes with **no warranty of profitability or correctness**. Algorithmic
trading can lose money quickly, including your entire account balance.
Markets, broker APIs, and this code can all fail in ways that cost real money.

- **Defaults to Alpaca paper trading.** No real money is at risk unless you
  deliberately enable live mode (see below).
- If you do enable live trading, you are solely responsible for every order
  it places. Test extensively in paper mode first, understand every line of
  `strategy.py` and `risk_manager.py`, and never risk money you can't afford
  to lose.
- The author(s) are not registered investment advisors and accept no
  liability for losses incurred using this software.

## How the strategy works

1. **Mark:** the first `RANGE_MINUTES` (default 5) one-minute bars after the
   open set the opening range `[range_low, range_high]`.
2. **Hunt:** once the range is set, each subsequent 1-min bar close is checked
   against the range. A close above `range_high` is a long breakout; a close
   below `range_low` is a short breakout.
3. **Await retest:** after a breakout, live trade ticks are watched for price
   to come back and touch the broken level (within `RETEST_TOUCH_TOLERANCE`).
4. **Confirm (volume-weighted):** once touched, the *next* closed bar must (a)
   close back in the breakout direction, **and** (b) have volume greater than
   `RETEST_VOLUME_MULTIPLIER` (default 1.2x) times the rolling average volume
   of the last `VOLUME_LOOKBACK_BARS` bars. This is a deliberate design choice
   to filter out low-conviction retests — see the deviations section below.
   If the bar fails to confirm, the algo resumes hunting for a fresh breakout.
5. **Strike:** on confirmation, position size is computed so that hitting the
   stop loses exactly the current risk limit (see Compounding below), and a
   bracket order (limit entry + stop-loss + take-profit) is submitted.
6. **Update:** when the stop or take-profit leg fills, realized P&L is logged
   to `trade_history.db`, which drives the compounding logic.

Only **one trade per day** is taken (`MAX_TRADES_PER_DAY`), and no new
breakouts are hunted in the last 15 minutes before the close
(`NEW_BREAKOUT_CUTOFF_HOUR`/`MINUTE`) — already-open bracket orders remain
live and are managed by the broker regardless.

## Compounding

Risk per trade starts at `BASE_RISK`. Once cumulative realized P&L (summed
across all closed trades in `trade_history.db`) reaches `PROFIT_BUFFER_TARGET`,
risk per trade scales up to `SCALED_RISK` and stays there.

## Setup

### 1. Prerequisites
- Python 3.10+ (tested on 3.12)
- An [Alpaca](https://alpaca.markets/) account (paper trading is free)

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure secrets and parameters
Copy `.env.example` to `.env` and fill in your own values — **do not commit
`.env`** (it's already git-ignored):
```bash
cp .env.example .env
```

Edit `.env`:
```env
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
TRADING_MODE=paper        # "paper" or "live"
I_UNDERSTAND_LIVE_RISK=false
TICKER=SPY
BASE_RISK=50.00
REWARD_RATIO=2.0
PROFIT_BUFFER_TARGET=200.00
SCALED_RISK=100.00
```

**Live trading requires both `TRADING_MODE=live` AND
`I_UNDERSTAND_LIVE_RISK=true`.** If only one is set, the app logs a warning
and falls back to paper trading. This is intentional — a single typo should
never be able to put real money on the line.

### 4. Initialize the database
```bash
python scripts/init_db.py
```
Creates `trade_history.db` (SQLite) with the `trades` table used to track
P&L and drive compounding.

### 5. Start the algo
Run at ~9:25am ET so the WebSocket connection is stable before the 9:30 open:
```bash
python main_algo.py
```

### 6. Launch the dashboard
In a separate terminal:
```bash
streamlit run dashboard.py
```
Read-only monitor of cumulative P&L, current risk tier, and trade history.

## Running tests
```bash
pytest
```
Covers position sizing, the compounding threshold, and the full breakout →
retest → volume-confirmation → strike state machine (including rejection
paths, the one-trade-per-day cap, the end-of-day cutoff, and day rollover).

## Project layout
| File | Purpose |
|---|---|
| `config.py` | Loads `.env`, resolves paper/live mode, exposes all tunables |
| `strategy.py` | The break-and-retest state machine |
| `data_stream.py` | Alpaca WebSocket subscriptions (bars, trades, order fills) |
| `risk_manager.py` | Position sizing + compounding math (pure functions) |
| `execution.py` | Bracket order submission |
| `db.py` | SQLite persistence for trade history / cumulative P&L |
| `main_algo.py` | Entry point that wires everything together |
| `dashboard.py` | Streamlit monitor |
| `scripts/init_db.py` | One-time DB setup |
| `tests/` | pytest suite |

## Deviations from the original blueprint

The blueprint this was built from left a few things ambiguous or unsafe for
a public repo; these were resolved deliberately rather than left as TODOs:

- **Secrets are never hardcoded.** The blueprint's `config.py` had you paste
  API keys directly into a committed file. Since this repo is public, secrets
  are instead loaded from a git-ignored `.env` via `python-dotenv`, with
  `.env.example` committed as a template.
- **Live trading requires double confirmation** (`TRADING_MODE=live` *and*
  `I_UNDERSTAND_LIVE_RISK=true`), rather than a single `BASE_URL` edit.
- **Retest confirmation is volume-weighted**, not just "buying/selling
  pressure confirmed" (which the blueprint never defined precisely): the
  confirming bar must close back through the level with volume above a
  rolling-average threshold.
- **Stop-loss is placed just beyond the retested/broken level** (with a small
  buffer), not at the opposite end of the 5-minute range. A wide stop at the
  far side of the opening range defeats the purpose of waiting for a tight
  retest entry.
- **No new breakouts are hunted in the last 15 minutes before the close**,
  to avoid opening fresh risk right before the session ends. Already-open
  bracket orders are unaffected.
- **`asyncio` was removed from `requirements.txt`.** It's part of the Python
  standard library since 3.4 — the PyPI backport package the blueprint listed
  is for Python 2/legacy use only and can conflict with modern Python.
- **Trade closes are detected via the `trade_updates` WebSocket stream**
  (not REST polling), matching the "no REST polling" requirement, and drive
  both P&L logging and the compounding threshold.

## Ideas for future improvements (not yet implemented)

Carried over from the original blueprint as scope for later work:

1. **Slippage tolerance:** reject a retest entry if the bid/ask spread has
   widened past a configurable threshold.
2. **Partial profit-taking:** scale out (e.g. 50% at 1.5R, move stop to
   breakeven, let the rest run to 3R) instead of a single hard exit.
3. **Breakout volume confirmation:** require the *breakout* candle itself
   (not just the retest) to exceed average volume, to filter false breaks.
4. **Options integration:** size an options position via Delta (e.g. with
   `py_vollib`) instead of trading shares directly.
