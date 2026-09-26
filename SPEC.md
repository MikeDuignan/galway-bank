# Galway Mutual — Spec

> The "Vulnerable 101" companion to the COMP09031 module. Where `galway-notes`
> teaches breadth (17 bugs, multi-service, ~25 threat-model rows), Galway
> Mutual teaches the **first** loop: pick a screen, spot the bug, exploit it
> in a one-line `curl`, fix it in a one-line diff, rebuild, prove it is gone.

---

## 1. Audience and context

- **Module:** COMP09031 Cybersecurity & Secure Programming, ATU Galway, NFQ Level 9.
- **Slot:** Week 2 practical (replacing OWASP Juice Shop).
- **Time budget:** 90-minute lab. Five bugs, ~15 minutes per bug including the fix.
- **Pre-requisites:** Week 1 lecture (CIA triad), Week 2 lecture (threat
  modelling, STRIDE). No web-security background assumed.

The student should leave the lab able to:

1. Read a Flask request handler and identify obvious classes of vulnerability.
2. Drive an exploit with `curl` (and read the response).
3. Patch a 1–3 line fix and retest.
4. Articulate the CWE class and a one-sentence rationale for the fix.

## 2. Architecture (1 page)

A single Flask process backed by a SQLite file. No microservices, no JWT,
no JS framework. Server-rendered Jinja2 templates. Flask sessions (signed
cookie) carry the logged-in user id. The application code is about 450
lines of Python and about 250 lines of Jinja template.

```
┌────────────────────┐         ┌────────────────────┐
│  Browser           │  HTTPS  │  Flask app          │
│                    │ ──────▶ │   :5000              │
│  session cookie    │         │   sqlite3            │
└────────────────────┘         └─────────┬──────────┘
                                          │
                                ┌─────────▼─────────┐
                                │  /var/lib/galway- │
                                │  bank/bank.db     │
                                └───────────────────┘
```

## 3. Routes

| Method | Path                | Auth required | Purpose |
|--------|---------------------|---------------|---------|
| GET    | `/`                 | no            | Redirect to `/dashboard` if logged in, else `/login`. |
| GET    | `/login`            | no            | Login form. |
| POST   | `/login`            | no            | Authenticate, set session. **BUG-01** lives here. |
| GET    | `/logout`           | no            | Clear session. |
| GET    | `/dashboard`        | yes           | List the current user's accounts and balances. |
| GET    | `/account/<id>`     | yes           | Account detail + recent transactions. **BUG-02** lives here. |
| GET    | `/transfer`         | yes           | Transfer form. |
| POST   | `/transfer`         | yes           | Execute transfer. **BUG-03** sink lives in the transactions template. |
| GET    | `/admin`            | (should be staff-only — **BUG-04**) | Lists every user, every account, every balance. |
| GET    | `/health`           | no            | `{"status":"ok"}`. |

## 4. Data model

Three tables, no exotic constraints.

```
users           id, email (unique), full_name, password_hash, role
accounts        id, user_id (FK users), account_number (unique), balance_cents, account_type
transactions    id, from_account_id (FK accounts), to_account_id (FK accounts),
                amount_cents, memo, created_at
```

Roles: `customer` and `staff`. Account types: `current` and `savings`.
Money is stored in integer cents to avoid float drift.

## 5. The five deliberate bugs

Each bug is marked in source with a `# BUG-NN:` comment.

### BUG-01 — SQL injection on `POST /login`

`app/routes.py:login()` builds the credential check with an f-string:

```python
sql = f"SELECT id, role FROM users WHERE email = '{email}' AND password_hash = '{hash_password(password)}'"
row = db.execute(sql).fetchone()
```

Payload: `' OR '1'='1' --` in the email field with any password. The `--`
comments out the password-hash check entirely; the resulting query returns
the first row of `users` — Aoife, because `seed/seed.py` deliberately
inserts the customers before the staff account.

**Fix:** parameterise the email lookup and verify the password in Python:
`row = db.execute("SELECT id, role, password_hash FROM users WHERE email = ?", (email,)).fetchone()`,
then `verify_password(password, row["password_hash"])`. Keeping the hash
comparison out of the SQL is what lets this fix survive BUG-05's move to
randomly salted hashes.

**CWE:** CWE-89.

### BUG-02 — IDOR on `GET /account/<id>`

`app/routes.py:account_view()` looks up the account by primary key without
checking that the account belongs to `session["user_id"]`. Any logged-in
customer can read any account by incrementing the URL.

**Fix:** add `if account["user_id"] != session["user_id"]: abort(403)`.

**CWE:** CWE-639.

### BUG-03 — Stored XSS in transfer memo

`app/templates/account.html` renders the memo with `{{ tx.memo|safe }}`. The
memo is user-controlled at `POST /transfer`. A memo of
`<script>alert(document.cookie)</script>` fires for every viewer of either
side of the transfer.

**Fix:** drop the `|safe` filter. Jinja's default auto-escape is sufficient.

**CWE:** CWE-79.

### BUG-04 — Missing authentication on `/admin`

`app/routes.py:admin()` has no `@require_login` decorator and no role check.
Any visitor — logged in or not — can browse every customer's name, email,
account numbers and balances.

**Fix:** add the `@require_login` decorator, then `me = current_user()`
and `if me["role"] != "staff": abort(403)`.

**CWE:** CWE-862 (Missing Authorization) compounded by CWE-306 (Missing
Authentication for Critical Function).

### BUG-05 — MD5, unsalted password hashing

`app/auth.py:hash_password()` uses `hashlib.md5(...).hexdigest()` with no
salt, and the seed data stores those digests. Compounds with BUG-01 —
once you have SQLi you can dump the column with a
`UNION SELECT password_hash …` and crack the lot in seconds.

**Fix:** replace `hash_password()`'s body with
`werkzeug.security.generate_password_hash` (scrypt by default in
Flask 3 / Werkzeug 3); `verify_password()` already verifies both the
legacy MD5 rows and the new format, so only the hash function changes.
Reseed so the stored column is scrypt.

**CWE:** CWE-916 compounded with CWE-759 (no salt).

## 6. Build phases

Unlike `galway-notes` (clean baseline, then bug injection, then fix), Galway
Mutual ships **all five bugs in `main` from day one**. The 101 audience does
not need a "before" branch — the point is to get to the exploit fast.

A `secure` branch will land before Week 2 of 2026-27 with the five fixes
applied so the lecturer can demo the diff.

## 7. Out of scope (deliberately)

These are taught later via `galway-notes`, not here:

- CSRF, SSRF, command injection, path traversal, ReDoS.
- Mass assignment, open redirect, weak JWT.
- Verbose error pages, supply-chain (CVE-pinned dependencies).
- Multi-service threat models, microservices, container escape.

The 101 stays small on purpose. Adding "just one more bug" turns it into Juice Shop.

## 8. Layout

```
apps/galway-bank/
├── README.md                    Quick start + demo accounts
├── SPEC.md                      You are here
├── pyproject.toml               Flask 3.0, python-dotenv, pytest
├── Dockerfile                   Single-stage python:3.12-slim
├── docker-compose.yml           Single service + sqlite volume
├── .env.example
├── app/
│   ├── __init__.py              Flask factory
│   ├── config.py
│   ├── db.py                    sqlite3 connection helper
│   ├── auth.py                  hash_password, verify_password (BUG-05)
│   ├── routes.py                All routes (BUGs 01–04)
│   ├── templates/               base, login, dashboard, account, transfer, admin, error
│   └── static/style.css         Galway Mutual brand
├── seed/
│   ├── schema.sql               DDL — three tables
│   └── seed.py                  Demo data (5 customers, 1 staff, 14 txns)
├── tests/
│   ├── conftest.py              Test app fixture, sqlite in tmp file
│   └── test_smoke.py            Boot, /health, login, dashboard, transfer
├── tools/
│   └── reset_db.py              `--if-empty` for compose; bare for lab reset
└── docs/
    ├── architecture.md          1-page diagram + request flow
    ├── bugs.md                  Lecturer's answer key (full exploit/fix per bug)
    └── walkthroughs/
        └── wk02-practical.md    Student-facing find→exploit→fix loop
```
