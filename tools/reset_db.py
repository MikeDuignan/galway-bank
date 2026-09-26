"""Drop, recreate, and reseed the Galway Mutual database.

Used at the start of each lab to give every student pair a clean state.

Usage::

    python tools/reset_db.py             # always reset (lab session start)
    python tools/reset_db.py --if-empty  # only seed if users table is empty
                                         # (used as the docker-compose entrypoint)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Make the project root importable so ``from app.auth import ...`` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset and reseed the Galway Mutual DB.")
    parser.add_argument("--if-empty", action="store_true",
                        help="Only seed if the users table is empty.")
    args = parser.parse_args()

    from app import create_app
    from seed.seed import seed

    app = create_app()
    db_path = Path(app.config["GALWAY_BANK_DB"])

    if args.if_empty:
        # The factory already initialises the schema; check the users table.
        conn = sqlite3.connect(db_path)
        existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        if existing > 0:
            print(f"[reset_db] users table already populated ({existing} rows). Skipping seed.")
            return 0
    else:
        if db_path.exists():
            db_path.unlink()
        # Re-create schema by re-running the factory (it initialises on a missing DB).
        app = create_app()
        db_path = Path(app.config["GALWAY_BANK_DB"])

    seed(db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
