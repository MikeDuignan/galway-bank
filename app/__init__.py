"""Galway Mutual — Flask application factory.

Single Flask app, single SQLite file, single routes module. Five deliberate
bugs flagged with `# BUG-NN:` markers in source. See SPEC.md and docs/bugs.md.
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from .config import Config, load_config
from .db import close_db, init_db_if_missing


def create_app(config_override: Config | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    config = config_override or load_config()
    app.config.from_object(config)

    Path(app.config["GALWAY_BANK_DB"]).parent.mkdir(parents=True, exist_ok=True)

    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db_if_missing()

    from . import routes
    routes.register(app)

    return app
