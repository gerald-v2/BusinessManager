"""Password helpers: store hashes, but keep old plain-text logins working.

Existing accounts still have plain-text passwords in the JSON files.  On a
successful login they are replaced by a salted hash, so nobody has to reset
anything and nobody is locked out.
"""

import hmac

from werkzeug.security import check_password_hash, generate_password_hash

_PREFIXES = ("scrypt:", "pbkdf2:")


def is_hashed(stored):
    return isinstance(stored, str) and stored.startswith(_PREFIXES)


def hash_pw(password):
    return generate_password_hash(password)


def verify(stored, given):
    """Returns (matches, needs_upgrade)."""
    if not stored or given is None:
        return False, False
    stored = str(stored)
    if is_hashed(stored):
        try:
            return check_password_hash(stored, given), False
        except ValueError:
            return False, False
    ok = hmac.compare_digest(stored.encode("utf-8"), str(given).encode("utf-8"))
    return ok, ok
