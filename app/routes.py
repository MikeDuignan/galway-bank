"""All HTTP routes for Galway Mutual.

Routes carry BUG-01 (SQLi in /login), BUG-02 (IDOR in /account/<id>) and
BUG-04 (missing auth on /admin). BUG-03 (stored XSS in transfer memo)
sinks in app/templates/account.html. BUG-05 lives in app/auth.py.
"""

from __future__ import annotations

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .auth import current_user, hash_password, require_login
from .db import get_db


def register(app: Flask) -> None:
    """Attach routes to the Flask app."""

    @app.route("/")
    def index():
        if current_user() is not None:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    # ----- AUTH ------------------------------------------------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            email = request.form.get("email", "")
            password = request.form.get("password", "")

            # BUG-01: SQL injection. The email and the (MD5-hashed) password
            # are spliced straight into the SQL string with f-string
            # interpolation. A payload of ``' OR '1'='1' --`` in the email
            # field makes the WHERE clause unconditionally true and comments
            # out the password-hash check, returning the first row of users.
            #
            # Fix: replace the WHOLE block below — from `sql = (` down to
            # and including the `row = None` inside the except, try/except
            # included — with a parameterised email lookup plus a password
            # check in Python with verify_password() (add it to the .auth
            # import above; hash_password is then unused in routes.py and
            # can drop off that import). Do not leave the try/except
            # behind: it re-runs execute(sql) with sql now undefined, the
            # except Exception swallows the NameError into row = None, and
            # every login fails silently. Verifying in Python (not in the
            # SQL) also keeps this fix working after Task 5, whose random
            # salt means two hashes of one password are never equal::
            #
            #     row = get_db().execute(
            #         "SELECT id, role, password_hash FROM users WHERE email = ?",
            #         (email,),
            #     ).fetchone()
            #     if row is None or not verify_password(password, row["password_hash"]):
            #         row = None
            sql = (
                "SELECT id, role FROM users "
                f"WHERE email = '{email}' "
                f"AND password_hash = '{hash_password(password)}'"
            )
            try:
                row = get_db().execute(sql).fetchone()
            except Exception:
                row = None

            if row is None:
                error = "Invalid email or password."
            else:
                session.clear()
                session["user_id"] = row["id"]
                return redirect(url_for("dashboard"))

        return render_template("login.html", error=error)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ----- DASHBOARD -------------------------------------------------------

    @app.route("/dashboard")
    @require_login
    def dashboard():
        me = current_user()
        accounts = get_db().execute(
            "SELECT id, account_number, account_type, balance_cents "
            "FROM accounts WHERE user_id = ? ORDER BY id",
            (me["id"],),
        ).fetchall()
        return render_template("dashboard.html", user=me, accounts=accounts)

    # ----- ACCOUNT VIEW ----------------------------------------------------

    @app.route("/account/<int:account_id>")
    @require_login
    def account_view(account_id: int):
        db = get_db()
        account = db.execute(
            "SELECT id, user_id, account_number, account_type, balance_cents "
            "FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        if account is None:
            abort(404)

        # BUG-02: missing authorisation check. The account is fetched by
        # primary key with no test that account.user_id == session["user_id"].
        # A logged-in customer can read any other customer's account by
        # incrementing /account/<id> in the URL bar.
        #
        # Fix: insert the ownership check before rendering::
        #
        #     if account["user_id"] != session["user_id"]:
        #         abort(403)
        #
        # (Staff may legitimately need cross-account read; gate that with a
        # role check, do not remove the ownership check.)

        owner = db.execute(
            "SELECT id, full_name, email FROM users WHERE id = ?",
            (account["user_id"],),
        ).fetchone()

        transactions = db.execute(
            """
            SELECT t.id,
                   t.amount_cents,
                   t.memo,
                   t.created_at,
                   t.from_account_id,
                   t.to_account_id,
                   fa.account_number AS from_number,
                   ta.account_number AS to_number
            FROM transactions t
            JOIN accounts fa ON fa.id = t.from_account_id
            JOIN accounts ta ON ta.id = t.to_account_id
            WHERE t.from_account_id = ? OR t.to_account_id = ?
            ORDER BY t.created_at DESC, t.id DESC
            LIMIT 50
            """,
            (account_id, account_id),
        ).fetchall()

        return render_template(
            "account.html",
            user=current_user(),
            account=account,
            owner=owner,
            transactions=transactions,
        )

    # ----- TRANSFER --------------------------------------------------------

    @app.route("/transfer", methods=["GET", "POST"])
    @require_login
    def transfer():
        me = current_user()
        db = get_db()
        my_accounts = db.execute(
            "SELECT id, account_number, account_type, balance_cents "
            "FROM accounts WHERE user_id = ? ORDER BY id",
            (me["id"],),
        ).fetchall()

        error = None
        if request.method == "POST":
            from_id = request.form.get("from_account_id", type=int)
            to_number = (request.form.get("to_account_number") or "").strip()
            amount_str = (request.form.get("amount") or "").strip()
            memo = request.form.get("memo") or ""

            from_account = db.execute(
                "SELECT id, user_id, balance_cents FROM accounts WHERE id = ?",
                (from_id,),
            ).fetchone()
            to_account = db.execute(
                "SELECT id, balance_cents FROM accounts WHERE account_number = ?",
                (to_number,),
            ).fetchone()

            try:
                amount_cents = int(round(float(amount_str) * 100))
            except (TypeError, ValueError):
                amount_cents = 0

            if from_account is None or from_account["user_id"] != me["id"]:
                error = "Pick one of your own accounts to transfer from."
            elif to_account is None:
                error = f"No Galway Mutual account with number {to_number!r}."
            elif amount_cents <= 0:
                error = "Amount must be positive."
            elif from_account["balance_cents"] < amount_cents:
                error = "Insufficient funds."
            else:
                db.execute(
                    "UPDATE accounts SET balance_cents = balance_cents - ? WHERE id = ?",
                    (amount_cents, from_account["id"]),
                )
                db.execute(
                    "UPDATE accounts SET balance_cents = balance_cents + ? WHERE id = ?",
                    (amount_cents, to_account["id"]),
                )
                db.execute(
                    "INSERT INTO transactions "
                    "(from_account_id, to_account_id, amount_cents, memo, created_at) "
                    "VALUES (?, ?, ?, ?, datetime('now'))",
                    (from_account["id"], to_account["id"], amount_cents, memo),
                )
                db.commit()
                flash(f"Transferred €{amount_cents/100:.2f} to {to_number}.")
                return redirect(url_for("account_view", account_id=from_account["id"]))

        return render_template(
            "transfer.html",
            user=me,
            my_accounts=my_accounts,
            error=error,
        )

    # ----- ADMIN -----------------------------------------------------------

    # BUG-04: no @require_login decorator and no role check. Anyone — including
    # an unauthenticated visitor — can browse /admin and read every customer's
    # name, email, account numbers and balances.
    #
    # Fix: add the @require_login decorator and refuse non-staff::
    #
    #     @app.route("/admin")
    #     @require_login
    #     def admin():
    #         me = current_user()
    #         if me["role"] != "staff":
    #             abort(403)
    #         ...
    @app.route("/admin")
    def admin():
        db = get_db()
        rows = db.execute(
            """
            SELECT u.id          AS user_id,
                   u.full_name   AS full_name,
                   u.email       AS email,
                   u.role        AS role,
                   a.id          AS account_id,
                   a.account_number AS account_number,
                   a.account_type   AS account_type,
                   a.balance_cents  AS balance_cents
            FROM users u
            LEFT JOIN accounts a ON a.user_id = u.id
            ORDER BY u.id, a.id
            """
        ).fetchall()
        return render_template("admin.html", user=current_user(), rows=rows)

    # ----- ERROR HANDLERS --------------------------------------------------

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403, message="Forbidden"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="Not found"), 404
