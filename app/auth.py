"""Authentication helpers — password hashing and the @require_login decorator.

Carries BUG-05.
"""

from __future__ import annotations

import hashlib
from functools import wraps

from flask import g, redirect, session, url_for
from werkzeug.security import check_password_hash

from .db import get_db


# BUG-05: passwords hashed with raw MD5 and no salt.
#
# MD5 is a fast, broken hash for password storage: it has no work factor,
# no salt, and modern GPUs compute ~50 GH/s. An attacker who reads the
# users table (e.g. via BUG-01 SQLi) can crack the whole column with
# `hashcat -m 0 hashes.txt rockyou.txt` in seconds.
#
# Fix: switch to werkzeug.security.generate_password_hash /
# check_password_hash, which use scrypt by default in Werkzeug 3.x.
def hash_password(plain: str) -> str:
    return hashlib.md5(plain.encode("utf-8")).hexdigest()


def verify_password(plain: str, stored_hash: str) -> bool:
    """Check ``plain`` against a stored hash, in either format this lab uses.

    Werkzeug hashes (``scrypt:...`` / ``pbkdf2:...``, what Task 5 switches
    ``hash_password`` to) always contain a ``:``; the seeded BUG-05 hashes
    are bare 32-char MD5 hex digests. Routing on the ``:`` makes the
    Task 1 login fix work both before and after Task 5. A real system
    would re-hash and write back on the MD5 branch; the lab reseeds
    instead — see docs/bugs.md, BUG-05.
    """
    if ":" in stored_hash:
        return check_password_hash(stored_hash, plain)
    return hashlib.md5(plain.encode("utf-8")).hexdigest() == stored_hash


def current_user():
    """Return the logged-in user row, or None. Cached on ``g`` per request."""
    if "user" in g:
        return g.user
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
        return None
    g.user = get_db().execute(
        "SELECT id, email, full_name, role FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return g.user


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped
