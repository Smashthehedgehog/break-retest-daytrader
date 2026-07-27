import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import db


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point db.py at a throwaway sqlite file so tests never touch a real trade_history.db."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test_trades.db"))
    db.init_db()
    return db
