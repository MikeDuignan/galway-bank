"""Galway Mutual — demo data.

Customers are inserted FIRST so that the SQL-injection payload
``' OR '1'='1' --`` on the login form returns Aoife (the first row), not
the staff account. This keeps BUG-01 (SQLi) and BUG-04 (missing admin auth)
as two distinct lessons rather than collapsing into one.

Idempotent: drops the demo rows and recreates them on every run.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.auth import hash_password


# Customers come first; staff comes last. See BUG-01 note above.
CUSTOMERS = [
    # email, full_name, accounts: list of (type, number, balance_cents)
    ("aoife@example.ie",   "Aoife Ni Chathain", [("current", "GW-10010001", 425000)]),
    ("ciaran@example.ie",  "Ciaran Boyle", [
        ("current", "GW-10010002",  394050),
        ("savings", "GW-20020002", 1500000),
    ]),
    ("niamh@example.ie",   "Niamh Murphy", [("current", "GW-10010003", 31278)]),
    ("padraig@example.ie", "Padraig O'Connor", [
        ("current", "GW-10010004",   761200),
        ("savings", "GW-20020004",  8000000),
    ]),
    ("siobhan@example.ie", "Siobhan Kelly", [("current", "GW-10010005", 200510)]),
]

STAFF_EMAIL = "staff@galwaymutual.ie"
STAFF_NAME = "Mary O'Donnell"
STAFF_PASSWORD = "Staff123!"
CUSTOMER_PASSWORD = "Customer1!"


# Realistic transaction history, chosen so the memos demo legitimate use of
# the field. The XSS payload (BUG-03) looks visibly out of place when injected
# into this flow.
DEMO_TRANSACTIONS = [
    # (from_email, from_account_number, to_email, to_account_number, amount_cents, memo, days_ago)
    ("ciaran@example.ie",  "GW-10010002", "aoife@example.ie",   "GW-10010001",  60000, "Rent — March",          12),
    ("ciaran@example.ie",  "GW-10010002", "aoife@example.ie",   "GW-10010001",  60000, "Rent — April",          5),
    ("aoife@example.ie",   "GW-10010001", "siobhan@example.ie", "GW-10010005",   3500, "Coffee + scone",         3),
    ("padraig@example.ie", "GW-10010004", "ciaran@example.ie",  "GW-10010002",  25000, "Lunch in Spanish Arch",  9),
    ("niamh@example.ie",   "GW-10010003", "padraig@example.ie", "GW-10010004",   1200, "Bus ticket I owe you",   7),
    ("siobhan@example.ie", "GW-10010005", "padraig@example.ie", "GW-10010004",   8500, "Splitting taxi",         4),
    ("ciaran@example.ie",  "GW-20020002", "ciaran@example.ie",  "GW-10010002", 100000, "Move from savings",      6),
    ("padraig@example.ie", "GW-20020004", "padraig@example.ie", "GW-10010004", 200000, "Move from savings",      8),
    ("aoife@example.ie",   "GW-10010001", "ciaran@example.ie",  "GW-10010002",  12000, "Birthday whip-round",    2),
    ("ciaran@example.ie",  "GW-10010002", "niamh@example.ie",   "GW-10010003",   4500, "Cinema tickets",         11),
    ("padraig@example.ie", "GW-10010004", "siobhan@example.ie", "GW-10010005",  15000, "Splitting Airbnb",       14),
    ("siobhan@example.ie", "GW-10010005", "aoife@example.ie",   "GW-10010001",   2200, "Returning your fiver",   1),
    ("ciaran@example.ie",  "GW-10010002", "padraig@example.ie", "GW-10010004",  35000, "Concert tickets",       10),
    ("niamh@example.ie",   "GW-10010003", "siobhan@example.ie", "GW-10010005",   1800, "Coffee",                 6),
]


def seed(db_path: str | Path) -> None:
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    _wipe(conn)

    user_ids: dict[str, int] = {}
    account_ids: dict[str, int] = {}

    # Hash once PER USER, not once per password: a salted hash (Werkzeug,
    # after the BUG-05 fix) must differ between two users who share a
    # plaintext. With the shipped unsalted MD5 the digest is deterministic,
    # so per-user hashing leaves the BUG-05 observation (all five
    # customers share one hash) unchanged.
    for email, full_name, accounts in CUSTOMERS:
        cur = conn.execute(
            "INSERT INTO users (email, full_name, password_hash, role) VALUES (?, ?, ?, 'customer')",
            (email, full_name, hash_password(CUSTOMER_PASSWORD)),
        )
        user_ids[email] = cur.lastrowid
        for acc_type, acc_number, balance in accounts:
            cur = conn.execute(
                "INSERT INTO accounts (user_id, account_number, account_type, balance_cents) VALUES (?, ?, ?, ?)",
                (user_ids[email], acc_number, acc_type, balance),
            )
            account_ids[acc_number] = cur.lastrowid

    # Staff last, so BUG-01 SQLi returns a customer (Aoife) by default.
    conn.execute(
        "INSERT INTO users (email, full_name, password_hash, role) VALUES (?, ?, ?, 'staff')",
        (STAFF_EMAIL, STAFF_NAME, hash_password(STAFF_PASSWORD)),
    )

    for from_email, from_num, to_email, to_num, amount, memo, days_ago in DEMO_TRANSACTIONS:
        conn.execute(
            "INSERT INTO transactions (from_account_id, to_account_id, amount_cents, memo, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now', ?))",
            (account_ids[from_num], account_ids[to_num], amount, memo, f"-{days_ago} days"),
        )

    conn.commit()
    n_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    n_accs = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    n_txns = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()
    print(f"[seed] {n_users} users, {n_accs} accounts, {n_txns} transactions inserted at {db_path}")


def _wipe(conn: sqlite3.Connection) -> None:
    for table in ("transactions", "accounts", "users"):
        conn.execute(f"DELETE FROM {table}")
        conn.execute(f"DELETE FROM sqlite_sequence WHERE name = ?", (table,))
    conn.commit()


if __name__ == "__main__":
    import os
    db_path = os.environ.get("GALWAY_BANK_DB", "/tmp/galway-bank.db")
    seed(db_path)
