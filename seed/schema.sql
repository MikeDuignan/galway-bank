-- Galway Mutual — schema. SQLite.

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    full_name       TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer','staff')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_number  TEXT NOT NULL UNIQUE,
    account_type    TEXT NOT NULL CHECK (account_type IN ('current','savings')),
    balance_cents   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_accounts_user ON accounts(user_id);

CREATE TABLE IF NOT EXISTS transactions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    from_account_id   INTEGER NOT NULL REFERENCES accounts(id),
    to_account_id     INTEGER NOT NULL REFERENCES accounts(id),
    amount_cents      INTEGER NOT NULL CHECK (amount_cents > 0),
    memo              TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_txns_from ON transactions(from_account_id);
CREATE INDEX IF NOT EXISTS ix_txns_to   ON transactions(to_account_id);
