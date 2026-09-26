"""Runtime configuration for Galway Mutual.

Loaded from environment (or .env via python-dotenv if present). The Flask
session signing key MUST be set in production; in development we fall back
to a fixed dev value so the app boots out-of-the-box.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class Config:
    GALWAY_BANK_DB: str
    SECRET_KEY: str
    TESTING: bool = False


def load_config() -> Config:
    return Config(
        GALWAY_BANK_DB=os.environ.get("GALWAY_BANK_DB", "/tmp/galway-bank.db"),
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev-flask-secret-change-me"),
    )
