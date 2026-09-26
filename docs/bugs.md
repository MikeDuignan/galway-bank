# Galway Mutual — Lecturer's Bug Index

> Lecturer's reference. The five deliberate vulnerabilities in `main` are
> indexed here with file, CWE, exploit recipe, fix outline, and the static-
> analysis signal that should catch each one.
>
> The students do **not** see this file during the Week 2 lab. It is the
> answer key.

Each bug is flagged in source by a `# BUG-NN:` (or `{# BUG-NN: #}` for Jinja)
marker. To enumerate every marker:

```bash
grep -rn "BUG-0" apps/galway-bank/app/
```

---

## BUG-01 — SQL injection on `POST /login`

- **Where:** `app/routes.py`, inside `login()`. The `# BUG-01:` marker sits
  immediately above the f-string SQL.
- **CWE:** CWE-89 — Improper Neutralisation of Special Elements used in an
  SQL Command.
- **Lecture anchor:** Ch 8 — Injection.
- **Practical anchor:** W2 P (the marquee bug for the 101 lab).

### Exploit recipe

In the login form, paste the following into the email field and any value
into the password field:

```
' OR '1'='1' --
```

The backend assembles the literal SQL:

```sql
SELECT id, role FROM users
WHERE email = '' OR '1'='1' --' AND password_hash = '<md5-of-password>'
```

`-- ` opens an SQL line comment so the password-hash predicate is dropped.
`'1'='1'` evaluates to true. SQLite returns the first row of `users`, which
the seed deliberately makes Aoife (`aoife@example.ie`, customer #1) — see
`seed/seed.py` for the ordering rationale. The session cookie is then issued
for Aoife and the attacker lands on the dashboard.

```bash
# Same attack via curl. --data-urlencode percent-encodes the quotes and
# spaces in the payload (plain -d would send the body exactly as typed).
curl -i -c jar --data-urlencode "email=' OR '1'='1' --" \
  -d "password=anything" http://localhost:5001/login
# Expect: 302 Location: /dashboard with Set-Cookie: session=...
```

### Why it works

`routes.py:login()` builds the WHERE clause with f-string interpolation:

```python
sql = (
    "SELECT id, role FROM users "
    f"WHERE email = '{email}' "
    f"AND password_hash = '{hash_password(password)}'"
)
try:
    row = get_db().execute(sql).fetchone()
except Exception:
    row = None
```

The string is then handed to `sqlite3.Connection.execute(sql)` — note the
single-argument form, which sends the literal SQL with no parameter
binding. The `try`/`except` folds any database error into `row = None`
(login simply fails) — which is also why a careless fix that breaks the
query fails silently; see the fix outline below.

### Fix outline

Replace the **whole** block quoted above — from `sql = (` down to and
including the `row = None` inside the `except:`, the `try:`/`except:`
lines included — with a parameterised email lookup that verifies the
password **in Python** rather than comparing hashes inside the SQL:

```python
row = get_db().execute(
    "SELECT id, role, password_hash FROM users WHERE email = ?",
    (email,),
).fetchone()
if row is None or not verify_password(password, row["password_hash"]):
    row = None
```

Also update the import at the top of `routes.py` to
`from .auth import current_user, require_login, verify_password` —
`hash_password` is no longer used in `routes.py` after this fix.

The replacement must include the `try`/`except`. A student who replaces
only the `sql = (...)` assignment leaves the old `try:` block executing
`execute(sql)` with `sql` now undefined; the `except Exception:` swallows
the `NameError` into `row = None`, and **every** login — correct
credentials included — fails silently with "Invalid email or password".
That silent total-login-failure is the symptom of a half-applied fix.

The `?` placeholder is bound by the SQLite driver at the C API layer,
where the value cannot escape its position. The same payload then matches
literally against the `email` column and the row count is zero.

Keeping the hash comparison out of the query matters for composition with
BUG-05's fix: once `hash_password()` produces salted hashes, no two
hashes of the same password are ever equal, so a `password_hash = ?`
predicate could never match. `verify_password()` accepts both the legacy
MD5 digests and the Werkzeug format, so this fix works before and after
the student patches BUG-05.

### Detection signal

Bandit B608 (`hardcoded_sql_expressions`) flags string-formatted SQL.
Semgrep `python.lang.security.audit.formatted-sql-query.formatted-sql-query`
fires on the f-string sink. ZAP's active scan also catches this as a
classic SQLi during W6 P.

---

## BUG-02 — IDOR on `GET /account/<id>`

- **Where:** `app/routes.py`, inside `account_view()`. The `# BUG-02:` marker
  sits above the spot where the ownership check is missing.
- **CWE:** CWE-639 — Authorization Bypass Through User-Controlled Key
  (Insecure Direct Object Reference).
- **Lecture anchor:** Ch 17 — Authorisation.
- **Practical anchor:** W2 P.

### Exploit recipe

```bash
# Log in as Aoife.
curl -s -c jar -d 'email=aoife@example.ie&password=Customer1!' \
  http://localhost:5001/login >/dev/null

# Walk every account by primary key.
for i in 1 2 3 4 5 6 7; do
  curl -s -b jar http://localhost:5001/account/$i \
    | grep -oE 'Held by [^<]+|€[0-9.]+' | head -3
  echo "---"
done
```

Account #5 is Padraig's current (€7,612.00); account #6 is his savings of
€80,000.00. Aoife (logged in as account-owner of #1) reads both with no
escalation other than incrementing the URL.

### Why it works

`account_view()` fetches the account by primary key and renders it without
checking ownership:

```python
account = db.execute(
    "SELECT id, user_id, ... FROM accounts WHERE id = ?",
    (account_id,),
).fetchone()
if account is None:
    abort(404)
# (no ownership check)
return render_template("account.html", ...)
```

The numeric ID is the *only* protection. This is the Optus 2022 pattern
(`/customer/<id>` enumerable across 9.8 M customers).

### Fix outline

```python
if account["user_id"] != session["user_id"]:
    abort(403)
```

Place the check immediately after the `abort(404)`. If staff legitimately
need cross-account read, gate that on `current_user()["role"] == "staff"`,
do not delete the ownership check.

### Detection signal

No SAST tool catches IDOR reliably — it is an authorisation pattern, not
a code pattern. DAST tools such as ZAP or Burp's Autorize plugin catch it
during W6 P. The teaching point is that authorisation bugs need *thinking*,
not scanning.

---

## BUG-03 — Stored XSS in transfer memo

- **Where:** `app/templates/account.html`. The `{# BUG-03: #}` marker sits
  above the `{{ tx.memo | safe }}` sink. The source is `POST /transfer` in
  `app/routes.py` (the memo is captured into the DB with no sanitisation).
- **CWE:** CWE-79 — Improper Neutralisation of Input During Web Page
  Generation (Cross-site Scripting).
- **Lecture anchor:** Ch 8 — Injection.
- **Practical anchor:** W2 P.

### Exploit recipe

```bash
# Log in as Aoife.
curl -s -c jar -d 'email=aoife@example.ie&password=Customer1!' \
  http://localhost:5001/login >/dev/null

# Send a tiny transfer to Ciaran with a stored-XSS payload in the memo.
curl -s -b jar -i \
  -d 'from_account_id=1&to_account_number=GW-10010002&amount=0.01' \
  --data-urlencode 'memo=<script>alert("XSS — "+document.cookie)</script>' \
  http://localhost:5001/transfer
```

Now log out, log in as Ciaran (`ciaran@example.ie / Customer1!`), and view
his current account at `/account/2`. The `<script>` tag fires on page load.

### Why it works

The memo is stored verbatim in the `transactions.memo` column. The
template renders it through Jinja's `|safe` filter:

```jinja
<td>{{ tx.memo | safe }}</td>
```

`|safe` is a `Markup` cast — it tells Jinja "this string is already trusted
HTML, do not auto-escape". The user-controlled bytes pass through to the
DOM intact.

### Fix outline

Drop the `|safe` filter. Jinja's default auto-escape will then HTML-encode
`<`, `>`, `"`, `'`, `&` and produce `&lt;script&gt;…&lt;/script&gt;` in the
rendered page. A one-token diff:

```jinja
<td>{{ tx.memo }}</td>
```

A defence-in-depth move (worth mentioning in the recap) is to add a strict
Content-Security-Policy header that forbids inline `<script>`. That is not
required for the fix; it would, however, neutralise an `onerror=` payload
even if the auto-escape were bypassed elsewhere.

### Detection signal

Semgrep `python.flask.security.audit.render-template-string.render-template-string`
flags `|safe` on user-controlled context. Bandit does not catch XSS
directly — this is a Semgrep / ZAP find.

---

## BUG-04 — Missing authentication on `/admin`

- **Where:** `app/routes.py`, the `admin()` view. The `# BUG-04:` marker
  heads the explanatory comment block a few lines above the
  `@app.route("/admin")` decorator. Note that `@require_login` is
  **absent**.
- **CWE:** CWE-862 (Missing Authorization) compounded by CWE-306 (Missing
  Authentication for Critical Function).
- **Lecture anchor:** Ch 17 — Authorisation.
- **Practical anchor:** W2 P.

### Exploit recipe

No login required. Open a fresh browser (or `curl` with no cookie):

```bash
curl -s http://localhost:5001/admin | grep -oE '€[0-9.]+|GW-[0-9]+|@example\.ie'
```

Expected: every customer's email, every account number, every balance.
The page is the staff console — but the staff console gates on nothing.

### Why it works

```python
# (no @require_login)
@app.route("/admin")
def admin():
    db = get_db()
    rows = db.execute("SELECT u.full_name, u.email, ... FROM users u LEFT JOIN accounts a ...").fetchall()
    return render_template("admin.html", ...)
```

Two missing controls. The decorator that would refuse anonymous callers
is not applied; the role check that would refuse non-staff is not present.
The route also does not gate the table query — the SQL itself willingly
returns every row.

### Fix outline

Two lines:

```python
@app.route("/admin")
@require_login
def admin():
    me = current_user()
    if me["role"] != "staff":
        abort(403)
    ...
```

Both controls matter. `@require_login` denies anonymous callers; the role
check denies authenticated *customers*. Stripping either one re-opens the
hole.

### Detection signal

No SAST tool catches missing authorisation reliably. DAST (ZAP / Burp
Autorize) catches it by issuing the same request with and without
credentials and comparing responses. The lecture point is that
authorisation testing is largely a manual inventory exercise: every
sensitive route gets matched against the role matrix in the threat model.

---

## BUG-05 — MD5, unsalted password hashing

- **Where:** `app/auth.py`, `hash_password()`. The `# BUG-05:` marker
  heads the explanatory comment block a few lines above
  `def hash_password`.
- **CWE:** CWE-916 — Use of Password Hash With Insufficient Computational
  Effort. Compounds with CWE-759 (no salt).
- **Lecture anchor:** Ch 11 — Identity, AuthN, secrets.
- **Practical anchor:** W2 P (this lab); revisited in W4 P.

### Exploit recipe

This bug becomes useful as a chain on top of BUG-01: once SQLi gives you
arbitrary read of the `users` table, you can dump the column and crack
the lot offline.

```bash
# Confirm the format. The seed plants password Customer1! for every
# customer; here is its raw MD5:
python3 -c "import hashlib; print(hashlib.md5(b'Customer1!').hexdigest())"
# 128d3578f0162b52a02d3cb606933c3d

# That hex string is exactly what is stored in users.password_hash.
# Real attack:
hashcat -m 0 hashes.txt rockyou.txt    # ~seconds on a commodity GPU
```

The point is not the speed of MD5 alone — it is the absence of a *salt*
and a *work factor*. Two users with the same password share a hash;
rainbow tables solve them in O(1).

### Why it works

```python
def hash_password(plain: str) -> str:
    return hashlib.md5(plain.encode("utf-8")).hexdigest()
```

Three problems compound:

1. **MD5** is computationally cheap (~50 GH/s on a single GPU).
2. **No salt** means identical plaintexts produce identical hashes — so a
   pre-computed table works, and the column is shareable across leaks.
3. **No work factor** means the attacker's hardware advantage scales
   linearly with their budget; the defender has no knob to turn.

### Fix outline

Replace the hash function with a modern one:

```python
from werkzeug.security import generate_password_hash

def hash_password(plain: str) -> str:
    return generate_password_hash(plain)            # scrypt by default in Werkzeug 3
```

`verify_password()` needs no change: it already routes on the `:` that
Werkzeug hashes always contain and calls `check_password_hash` for them,
while still verifying the legacy MD5 digests — the same
verify-then-upgrade migration a real system performs at login, minus the
write-back. Because `seed/seed.py` hashes through `hash_password()`, the
student must wipe and reseed so the stored column is actually scrypt:

```bash
docker compose down -v && docker compose up -d --build
```

(Once every row is reseeded, `verify_password()` could be simplified to
`return check_password_hash(stored, plain)` — optional in the lab.)

### Detection signal

Bandit B303 (`use of insecure MD2, MD4, MD5, or SHA1 hash function`) fires
on the `hashlib.md5` call. Semgrep
`python.lang.security.audit.md5-used-as-password.md5-used-as-password` is
the targeted rule.

---

## Cross-reference

| BUG | Class | CWE | File | Marker |
|-----|-------|-----|------|--------|
| 01 | SQLi             | CWE-89  | `app/routes.py`            | `# BUG-01:` in `login()` |
| 02 | IDOR             | CWE-639 | `app/routes.py`            | `# BUG-02:` in `account_view()` |
| 03 | Stored XSS       | CWE-79  | `app/templates/account.html` | `{# BUG-03: #}` above `\|safe` |
| 04 | Missing auth     | CWE-862, CWE-306 | `app/routes.py` | `# BUG-04:` above `admin()` |
| 05 | Weak hash        | CWE-916, CWE-759 | `app/auth.py`   | `# BUG-05:` above `hash_password()` |

## Recommended Week-2 lab order

1. **BUG-01** — quick win, dramatic visual (the page logs you in as a
   stranger). Sets up the chain to BUG-05.
2. **BUG-02** — once logged in as Aoife, walk to Padraig's accounts. Makes
   the consequence visceral (€87k of someone else's money).
3. **BUG-03** — same screen as 02 (the account view). Cheap to switch context.
4. **BUG-04** — a separate concern; the warm-up for "auth is one thing,
   authorisation is another".
5. **BUG-05** — closes the loop on BUG-01 ("now we know how to log in as
   anyone, but what if we wanted to log in as them *correctly*?"). The
   crack-the-hash payoff lives here.

The fixes can be applied in the same order; each is 1–3 lines.
