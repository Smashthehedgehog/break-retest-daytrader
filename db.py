"""
SQLite persistence for trade history and the running cumulative P&L that
drives the risk-compounding decision (see risk_manager.get_current_risk_limit).
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('long', 'short')),
    entry_price REAL NOT NULL,
    stop_price REAL NOT NULL,
    take_profit_price REAL NOT NULL,
    qty INTEGER NOT NULL,
    risk_dollars REAL NOT NULL,
    entry_order_id TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'rejected')),
    pnl REAL,
    opened_at TEXT NOT NULL,
    closed_at TEXT
);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.execute(SCHEMA)


def log_trade_opened(ticker, direction, entry_price, stop_price, take_profit_price, qty, risk_dollars, entry_order_id=None):
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO trades
                (ticker, direction, entry_price, stop_price, take_profit_price,
                 qty, risk_dollars, entry_order_id, status, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                ticker, direction, entry_price, stop_price, take_profit_price,
                qty, risk_dollars, entry_order_id, datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def close_trade(trade_id, pnl):
    with _connect() as conn:
        conn.execute(
            "UPDATE trades SET status = 'closed', pnl = ?, closed_at = ? WHERE id = ?",
            (pnl, datetime.now(timezone.utc).isoformat(), trade_id),
        )


def find_open_trade_by_order_id(order_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM trades WHERE entry_order_id = ? AND status = 'open'", (order_id,)
        ).fetchone()
        return dict(row) if row else None


def find_open_trade_for_ticker(ticker):
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM trades WHERE ticker = ? AND status = 'open' ORDER BY opened_at DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return dict(row) if row else None


def get_cumulative_pnl():
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) AS total FROM trades WHERE status = 'closed'"
        ).fetchone()
        return row["total"]


def has_open_trade_today():
    today = datetime.now(timezone.utc).date().isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM trades WHERE status = 'open' AND opened_at LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return row["n"] > 0


def count_trades_today():
    today = datetime.now(timezone.utc).date().isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM trades WHERE opened_at LIKE ?", (f"{today}%",)
        ).fetchone()
        return row["n"]


def get_all_trades():
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM trades ORDER BY opened_at DESC").fetchall()
        return [dict(r) for r in rows]
