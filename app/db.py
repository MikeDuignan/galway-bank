"""SQLite connection helper.

One connection per Flask request (stored on ``g``), closed at request teardown.
Rows come back as ``sqlite3.Row`` so templates can do ``row["balance_cents"]``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "seed" / "schema.sql"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(
            current_app.config["GALWAY_BANK_DB"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db_if_missing() -> None:
    """Create the schema on first boot. Idempotent."""
    db = get_db()
    cur = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if cur.fetchone() is not None:
        return
    db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.commit()
