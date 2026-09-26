# Galway Mutual — architecture (one page)

## Stack

| Layer    | Choice                                | Why |
|----------|---------------------------------------|------|
| Server   | Flask 3 (Python 3.12)                 | Smallest possible web stack. Students can read every request handler in one file. |
| DB       | SQLite (file)                         | No DB service to stand up. The whole DB is `cat`-able. |
| Sessions | Flask signed cookie                   | No JWT, no Redis. `session["user_id"]` is the only auth state. |
| UI       | Jinja2 templates, static CSS          | No JS framework. The browser just renders HTML. |
| Container| `python:3.12-slim` single stage       | One service in compose. SQLite on a named volume. |

## Process model

A single Flask process. Inside it, every request goes through:

```
   request
      │
      ▼
  ┌──────────────┐         ┌────────────────────┐
  │  routes.py   │ ──────▶ │  app/auth.py        │  (require_login, current_user)
  └──────┬───────┘         └─────────┬──────────┘
         │                            │
         ▼                            ▼
  ┌──────────────┐         ┌────────────────────┐
  │  app/db.py   │ ──────▶ │  bank.db (SQLite)  │
  └──────────────┘         └────────────────────┘
         │
         ▼
  ┌──────────────────────────┐
  │  templates/*.html (Jinja)│
  └──────────────────────────┘
         │
         ▼
   response
```

## Request flow — login (with BUG-01)

```
POST /login   email=' OR '1'='1' --   password=anything
   │
   ▼
routes.py:login()  builds SQL with f-string ◀── BUG-01
   │
   ▼
db.py:get_db()  →  cursor.execute(sql)
   │
   ▼
SQLite returns first row of users (Aoife, customer #1)
   │
   ▼
session["user_id"] = 1   →   302 to /dashboard
```

## Request flow — IDOR (BUG-02) chained on top

```
Aoife is logged in (session["user_id"]=1).
   ▼
GET /account/4
   │
   ▼
routes.py:account_view(4)  fetches account 4 by PK ◀── BUG-02 (no ownership check)
   │
   ▼
account 4 is Niamh's current account (user_id 3, €312.78). Aoife sees it.
   Padraig's accounts are 5 (current, €7,612.00) and 6 (savings,
   €80,000.00) — equally reachable by incrementing the URL.
```

## File anatomy

- `app/__init__.py` — `create_app()` factory. About 40 lines.
- `app/config.py` — environment loading. Plain dataclass.
- `app/db.py` — SQLite connection per request, `init_db_if_missing` for first boot.
- `app/auth.py` — `hash_password` (BUG-05), `verify_password`, `current_user`, `require_login` decorator.
- `app/routes.py` — every URL the app serves. About 280 lines. Carries BUGs 01, 02, 04.
- `app/templates/` — five page templates (login, dashboard, account, transfer, admin) + base + error. Carries BUG-03.
- `app/static/style.css` — single stylesheet, navy + gold brand.
- `seed/schema.sql` — three tables.
- `seed/seed.py` — five customers, one staff, 14 demo transactions.
- `tools/reset_db.py` — lab-reset utility.

## Boundaries

| Boundary | What crosses it |
|----------|-----------------|
| Browser → app | URL path, query string, form fields, session cookie. **Treat all as untrusted.** |
| App → SQLite | Parameterised queries (everywhere except BUG-01). |
| App → browser | HTML rendered by Jinja2 with auto-escape (everywhere except BUG-03's `\|safe`). |

## Out of scope

There is no API, no microservice, no JWT, no file upload, no external HTTP
client, no JavaScript. Each of those is an attack surface that *would* expose
real bugs — but pedagogically, having more surface than the student can hold
in their head is exactly what makes Juice Shop frustrating. Galway Mutual
keeps the surface deliberately small.
