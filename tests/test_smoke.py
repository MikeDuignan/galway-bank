"""Smoke tests for Galway Mutual.

These prove the app boots, persists data, and round-trips a transfer.
They do NOT assert anything about the deliberate vulnerabilities — those
are the point of the lab, not regressions to guard.
"""

from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_index_redirects_to_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302, 308)
    assert "/login" in r.headers["Location"]


def test_login_form_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b"Galway Mutual" in r.data
    assert b"Sign in" in r.data


def test_login_with_valid_credentials(client):
    r = client.post(
        "/login",
        data={"email": "aoife@example.ie", "password": "Customer1!"},
        follow_redirects=False,
    )
    assert r.status_code in (301, 302, 303)
    assert "/dashboard" in r.headers["Location"]


def test_dashboard_lists_owned_accounts(client):
    client.post("/login", data={"email": "ciaran@example.ie", "password": "Customer1!"})
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert b"GW-10010002" in r.data       # Ciaran's current
    assert b"GW-20020002" in r.data       # Ciaran's savings


def test_account_view_renders(client):
    client.post("/login", data={"email": "aoife@example.ie", "password": "Customer1!"})
    r = client.get("/account/1")
    assert r.status_code == 200
    assert b"GW-10010001" in r.data
    assert b"Recent transactions" in r.data


def test_transfer_round_trip(client):
    client.post("/login", data={"email": "aoife@example.ie", "password": "Customer1!"})
    r = client.post(
        "/transfer",
        data={
            "from_account_id": "1",
            "to_account_number": "GW-10010002",
            "amount": "1.23",
            "memo": "smoke-test transfer",
        },
        follow_redirects=False,
    )
    assert r.status_code in (301, 302, 303)
    # Aoife's account view should now show the new transaction.
    r = client.get("/account/1")
    assert b"smoke-test transfer" in r.data


def test_logged_out_dashboard_redirects(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code in (301, 302, 303)
    assert "/login" in r.headers["Location"]
