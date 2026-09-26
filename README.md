# Galway Mutual — a deliberately-vulnerable bank

The "Vulnerable 101" web app for the COMP09031 *Cybersecurity & Secure
Programming* module at ATU Galway. Five obvious bugs, one per screen, designed
for a single 90-minute Week 2 practical. The stakes are clear (it is a bank);
the surface area is small (login, dashboard, view account, transfer, admin).

This is the **easier** sister of `galway-notes`. Use this in Week 2 to teach
the loop *find → exploit → fix → rebuild*, then graduate to `galway-notes`
later in the module for the harder, more realistic surface.

---

## The five bugs at a glance

| # | Where | Class | Find it by |
|---|---|---|---|
| BUG-01 | Login form | SQL injection | `' OR '1'='1' --` in the email field |
| BUG-02 | `/account/<id>` | IDOR (broken authorisation) | Increment the account ID in the URL |
| BUG-03 | Transfer memo | Stored XSS | Send a transfer with `<script>alert(1)</script>` in the memo |
| BUG-04 | `/admin` | Missing authentication | Browse to `/admin` while logged out |
| BUG-05 | Password storage | MD5, unsalted | Inspect `users.password_hash`; crack with hashcat -m 0 |

Each bug is flagged in source with a `# BUG-NN:` comment. To enumerate:

```bash
grep -rn "BUG-0" app/
```

The full lecturer's answer key lives in [`docs/bugs.md`](docs/bugs.md). The
student-facing walkthrough is [`docs/walkthroughs/wk02-practical.md`](docs/walkthroughs/wk02-practical.md).

---

## Run the published image in Docker Desktop

Install and start Docker Desktop with Linux containers enabled. The image is
published at `ghcr.io/mikeduignan/galway-bank:latest` for Linux AMD64 and ARM64.
Run this in a terminal:

```sh
docker run -d --name galway-bank -p 127.0.0.1:5001:5000 -v galway-bank-data:/var/lib/galway-bank ghcr.io/mikeduignan/galway-bank:latest
```

Open <http://127.0.0.1:5001>. Sign in with `aoife@example.ie` / `Customer1!`.
The container appears in Docker Desktop, where you can stop and start it.
The bank uses fictional data and deliberate vulnerabilities. Keep it local;
the supplied port mapping binds only to your own computer.

Alternatively, download [compose.published.yml](compose.published.yml) and run:

```sh
docker compose -f compose.published.yml up -d
```

Use one startup method at a time because both use port 5001. To get an updated
image with the Compose method, run `docker compose -f compose.published.yml pull`
and then run the startup command again.

## Build from source (for the exploit-and-fix practical)

Use this route when students need to edit the Python source and rebuild their
repairs. The published image is useful for running and exploring the baseline.

```bash
git clone https://github.com/MikeDuignan/galway-bank.git
cd galway-bank

# Optional: copy .env.example to .env and edit FLASK_SECRET_KEY.
# The fictional local lab also starts with its supplied defaults.

docker compose build
docker compose up -d

# Wait ~5 seconds for the DB to seed itself, then:
curl -fsS http://localhost:5001/health
# {"status":"ok"}
```

Open <http://localhost:5001> and log in with one of the demo accounts.

After editing source, run `docker compose up -d --build` to apply your changes.

### Demo accounts (seeded on first run)

| Email                 | Password      | Role     | Balance |
|-----------------------|---------------|----------|---------|
| `aoife@example.ie`    | `Customer1!`  | customer | €4,250.00 |
| `ciaran@example.ie`   | `Customer1!`  | customer | €18,940.50 |
| `niamh@example.ie`    | `Customer1!`  | customer | €312.78 |
| `padraig@example.ie`  | `Customer1!`  | customer | €87,612.00 |
| `siobhan@example.ie`  | `Customer1!`  | customer | €2,005.10 |
| `staff@galwaymutual.ie` | `Staff123!` | staff    | — |

Bring the stack down with `docker compose down`. To wipe data and start
fresh: `docker compose down -v`.

---

## Quick start (venv fallback)

If Docker is not available:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

export GALWAY_BANK_DB=$(pwd)/bank.db
export FLASK_SECRET_KEY=dev-flask-secret

python tools/reset_db.py
python -m flask --app app:create_app run --port 5001
```

---

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

The smoke suite covers: app boots, `/health` returns 200, login flow works,
dashboard renders, transfer flow inserts a transaction.

---

## Resetting between lab sessions

To give every student pair a clean state:

```bash
docker compose down -v && docker compose up -d
```

Or, in venv mode:

```bash
python tools/reset_db.py
```

---

## Licence

MIT.
