# Week 2 Practical — Find, Exploit, Fix

> COMP09031 Cybersecurity & Secure Programming. 90 minutes. Pair work
> recommended. By the end of the lab you will have found, exploited, and
> patched five real classes of web vulnerability in a working banking app.
>
> Bring: a laptop with Docker installed, a terminal, and a browser.

---

## What you are looking at

**Galway Mutual** is a small online-banking demo built for this module. It
has five screens — sign in, dashboard, account view, transfer, staff
console — and it is **deliberately broken in five places**. Your job is to
find each break, exploit it, and then patch the code.

This is the simplest possible setup. The whole codebase is about 450
lines of Python and about 250 lines of templates; you can read every
line in a sitting.

> **Why a bank?** Because the consequences are obvious. When the bug lets
> you read someone else's bank balance or move their money, "this is bad"
> needs no further justification.

---

## Setup (5 minutes)

```bash
git clone https://github.com/MikeDuignan/galway-bank.git
cd galway-bank
cp .env.example .env
docker compose up -d --build

# Wait ~5 seconds, then:
curl -fsS http://localhost:5001/health
# {"status":"ok"}
```

Open <http://localhost:5001> in your browser. You should see the Galway
Mutual sign-in page.

### Demo accounts

| Email                  | Password     | Role     |
|------------------------|--------------|----------|
| `aoife@example.ie`     | `Customer1!` | customer |
| `ciaran@example.ie`    | `Customer1!` | customer |
| `niamh@example.ie`     | `Customer1!` | customer |
| `padraig@example.ie`   | `Customer1!` | customer |
| `siobhan@example.ie`   | `Customer1!` | customer |
| `staff@galwaymutual.ie`| `Staff123!`  | staff    |

If something goes sideways, reset to a clean DB with:

```bash
docker compose down -v && docker compose up -d --build
```

---

## The five tasks

Each task follows the same loop:

1. **Find** — read the relevant file, spot the suspicious line.
2. **Exploit** — drive the bug from the browser or `curl`.
3. **Fix** — write a 1–3 line patch.
4. **Rebuild** — `docker compose up -d --build` (or in venv mode, just hit
   refresh — Flask reloads on file change).
5. **Retest** — confirm the exploit no longer works and the app still does.

You will need a notebook or a markdown file to record findings. For each
bug, jot down:

- The CWE number.
- The file and line of the bug.
- The exploit input you used.
- The fix you applied (one or two lines of diff).

That table becomes your lab submission.

---

### Task 1 — Sign in as someone you are not (≈15 min)

**Find.** Open `app/routes.py` and read the `login()` function. Look at how
the SQL is built before it goes to the database. Anything jump out?

**Exploit.** On the sign-in page, try this in the **email** field (with any
non-empty password):

```
' OR '1'='1' --
```

You should land on the dashboard as someone whose email you do not know.
Whose dashboard are you on? Inspect the top-right of the page.

> *Hint.* You are exploiting **SQL injection** — CWE-89. The single-quote
> closes the email literal; `OR '1'='1'` makes the WHERE clause true; `--`
> drops the password check entirely.

**Fix.** In `login()`, replace the **whole** vulnerable block — from the
line `sql = (` down to and including the `row = None` inside the
`except:` — with a parameterised query that fetches the user by **email
alone** and checks the password **in Python** with `verify_password()`.
Delete all nine lines of it (the `try:`/`except:` included):

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

and paste this in its place:

```python
row = get_db().execute(
    "SELECT id, role, password_hash FROM users WHERE email = ?",
    (email,),
).fetchone()
if row is None or not verify_password(password, row["password_hash"]):
    row = None
```

> Replace the whole block, not just the `sql = (...)` assignment. If you
> leave the old `try:`/`except:` lines behind, they still run
> `execute(sql)` — but `sql` no longer exists, and the
> `except Exception:` swallows the resulting `NameError` and sets
> `row = None`. Every login then fails with "Invalid email or password",
> correct password or not, and nothing prints an error. If your retest
> says *every* login is now wrong, you have almost certainly left the
> `try`/`except` behind.

`verify_password()` lives in `app/auth.py`, so add it to the import line
at the top of `routes.py` — and drop `hash_password`, which `routes.py`
no longer uses after this fix (`app/auth.py` and `seed/seed.py` still
use it; only `routes.py` stops needing it):

```python
from .auth import current_user, require_login, verify_password
```

The email goes through as a bound parameter, so an `'` in it is treated
as data, not as SQL syntax — the payload matches no row and login fails.

Keep the password check **out of the SQL**. `verify_password()` compares
the plaintext against the stored hash, and it handles both the seeded MD5
hashes and the salted hashes Task 5 switches to — so this fix keeps
working for the rest of the lab. (If you instead wrote
`AND password_hash = ?` with `hash_password(password)` as the parameter,
Task 5 would break your login: with a random salt, the hash you compute
is never byte-for-byte equal to the one stored.)

**Retest.** Try the payload again — you should now see "Invalid email or
password." Try a real login — that should still work.

---

### Task 2 — Read someone else's bank balance (≈10 min)

You are logged in as Aoife (or whoever Task 1's exploit let you in as).
Navigate to her current account from the dashboard. Look at the URL —
it ends in `/account/1`.

**Find.** What happens if you change `1` to `2`? `4`? `7`? Open
`app/routes.py:account_view()` to find out why it works.

**Exploit.** Walk the URL by hand:

```
http://localhost:5001/account/1    ← Aoife's current (your own)
http://localhost:5001/account/2    ← Ciaran's current
http://localhost:5001/account/3    ← Ciaran's savings, €15,000
http://localhost:5001/account/4    ← Niamh's current
http://localhost:5001/account/5    ← Padraig's current
http://localhost:5001/account/6    ← Padraig's savings, €80,000
http://localhost:5001/account/7    ← Siobhan's current
```

You are reading other customers' accounts because the route fetches by
primary key without checking *who owns the row*. This is **IDOR** —
CWE-639. It is the same pattern as the 2022 Optus breach.

**Fix.** After the `abort(404)`, add the ownership check:

```python
if account["user_id"] != session["user_id"]:
    abort(403)
```

**Retest.** Hitting `/account/4` should now show a "403 — Forbidden" page.
Hitting your own account ID should still work.

---

### Task 3 — Run JavaScript in someone else's browser (≈15 min)

**Find.** Open `app/templates/account.html`. Look at how the transaction
memo is rendered.

**Exploit.** Sign in as **Aoife** (`aoife@example.ie / Customer1!`). Make a
1-cent transfer to Ciaran (`GW-10010002`) with this **memo**:

```html
<script>alert("XSS — your session cookie is " + document.cookie)</script>
```

Now sign out, sign in as **Ciaran**, and view his current account at
`/account/2`. The script fires.

This is **stored XSS** — CWE-79. The malicious memo lives in the database
and runs every time anyone (including the bank's own staff!) views the
transaction.

**Fix.** In `account.html`, change:

```jinja
<td>{{ tx.memo | safe }}</td>
```

to:

```jinja
<td>{{ tx.memo }}</td>
```

`|safe` told Jinja "trust this string as raw HTML"; removing it lets Jinja
do its default job — auto-escape `<`, `>`, `&`, `"`, `'`. The `<script>`
tag becomes the literal text `&lt;script&gt;` and never runs.

**Retest.** Replay the same memo on a fresh transfer; you should see the
`<script>` text rendered as text, not executed.

---

### Task 4 — See every customer's balance with no login (≈10 min)

**Find.** Browse to `/admin`. You should be redirected to the login page,
right? Try it before reading the next paragraph.

**Exploit.** Open a private/incognito window (no session cookie at all).
Visit:

```
http://localhost:5001/admin
```

You see every customer's name, email, account number, type, and balance.
You are not logged in. There is no role check. This is **missing
authorisation** — CWE-862 — sitting on top of **missing authentication**
— CWE-306.

**Fix.** Open `app/routes.py` and find the `admin()` view. Two changes:

```python
@app.route("/admin")
@require_login                             # ① require any login
def admin():
    me = current_user()
    if me["role"] != "staff":              # ② require the staff role
        abort(403)
    ...
```

**Retest.**

- Logged out: `/admin` redirects to `/login`.
- Logged in as Aoife: `/admin` returns 403 Forbidden.
- Logged in as `staff@galwaymutual.ie / Staff123!`: `/admin` shows the
  staff console.

---

### Task 5 — Crack the password column (≈15 min)

This task chains on top of Task 1. Once you have SQLi, you can dump the
`users` table — and once you have the hashes, you can crack them.

**Find.** Open `app/auth.py`. Read `hash_password()`. What hash function
does it use? What's missing from a security standpoint?

**Exploit (no GPU required).** Look at the column directly. From the host:

```bash
docker compose exec app sqlite3 /var/lib/galway-bank/bank.db \
    "SELECT email, password_hash FROM users LIMIT 3"
```

Now compute MD5 of the customer password yourself:

```bash
python3 -c "import hashlib; print(hashlib.md5(b'Customer1!').hexdigest())"
```

The result matches every customer row exactly. Two observations:

1. **No salt.** All five customers share the same hash because they share
   the same plaintext.
2. **No work factor.** A real attacker would point `hashcat -m 0` at this
   column and a `rockyou.txt` wordlist; on a commodity GPU the entire
   column cracks in seconds.

This is **CWE-916** (insufficient hash strength), compounded by **CWE-759**
(no salt).

**Fix.** Open `app/auth.py` and replace the body of `hash_password` with
Werkzeug's helper:

```python
from werkzeug.security import generate_password_hash

def hash_password(plain: str) -> str:
    return generate_password_hash(plain)        # scrypt by default in Werkzeug 3
```

Leave `verify_password()` as it is — read its body. It routes on the `:`
that Werkzeug hashes always contain (`scrypt:32768:...`) and verifies
those with `check_password_hash`, while still accepting the legacy MD5
rows: exactly the verify-both-formats migration a real system does at
login. Your Task 1 login fix therefore keeps working before *and* after
this change.

Because `generate_password_hash` includes a random salt, the seeded rows
must be re-created for the fix to show in the database — `seed/seed.py`
calls `hash_password()`, so a fresh seed stores scrypt hashes:

```bash
docker compose down -v && docker compose up -d --build
```

(If you are running in venv mode: `python tools/reset_db.py`. Until you
reseed, the old MD5 rows still log in through `verify_password()`'s
legacy branch — that is the migration path working, not a leftover bug.)

**Retest.**

- Log in with `aoife@example.ie / Customer1!`. Should still work.
- `docker compose exec app sqlite3 /var/lib/galway-bank/bank.db "SELECT password_hash FROM users LIMIT 1"`.
  The hash should now start with `scrypt:` and contain a salt and work
  factor. Two users with the same password should now have **different**
  stored hashes.

---

## Submission

A short markdown file with one row per bug:

```
| # | CWE     | Where (see the BUG-NN marker)        | Exploit input                  | Fix (1-2 lines) |
|---|---------|---------------------------------------|--------------------------------|-----------------|
| 1 | CWE-89  | app/routes.py — login()               | email=' OR '1'='1' --          | (paste diff)    |
| 2 | CWE-639 | app/routes.py — account_view()        | /account/4 while logged in     | (paste diff)    |
| 3 | CWE-79  | app/templates/account.html            | memo=<script>alert(1)</script> | (paste diff)    |
| 4 | CWE-862 | app/routes.py — admin()               | curl /admin no cookie          | (paste diff)    |
| 5 | CWE-916 | app/auth.py — hash_password()         | inspect users.password_hash    | (paste diff)    |
```

Upload to Moodle by 17:00 on the day of the lab.

---

## Going further (optional)

- **Chain BUG-01 → BUG-05.** Use the SQLi to dump the `password_hash`
  column with a `UNION SELECT email, password_hash, ...` payload. Then
  crack offline with `hashcat`. The point is to feel the *compounding*
  effect of two bugs that look harmless individually.
- **Read the Optus 2022 incident report** and note where it sits in this
  taxonomy. Is it BUG-02 (IDOR) or BUG-04 (missing auth)? Or both?
- **Compare with `apps/galway-notes/`.** That app has 17 bugs across the
  whole module — this one was just the warm-up. Don't peek at the
  walkthroughs there until your week comes around.

## When you finish, tear down

```bash
docker compose down -v
```

— and grab a coffee. You earned it.
