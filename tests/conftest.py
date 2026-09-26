"""Pytest fixtures: a Flask app + client backed by a tmp-file SQLite."""

from __future__ import annotations

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    db_path = tmp_path / "bank.db"
    monkeypatch.setenv("GALWAY_BANK_DB", str(db_path))
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-flask-secret")

    from app import create_app
    from seed.seed import seed

    app = create_app()
    seed(db_path)
    app.config["TESTING"] = True
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()
