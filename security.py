"""Password helpers: store hashes, but keep old plain-text logins working.

Existing accounts still have plain-text passwords in the JSON files.  On a
successful login they are replaced by a salted hash, so nobody has to reset
anything and nobody is locked out.
"""

import hmac
import threading
import time

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


def hash_plaintext_in(obj):
    """Walk loaded JSON and replace every plain-text "password" value with a hash.
    Returns how many were changed. Empty placeholders are left alone."""
    changed = 0
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "password" and isinstance(value, str) and value and not is_hashed(value):
                obj[key] = hash_pw(value)
                changed += 1
            else:
                changed += hash_plaintext_in(value)
    elif isinstance(obj, list):
        for item in obj:
            changed += hash_plaintext_in(item)
    return changed


# ---- login throttling -------------------------------------------------------
# Stops password guessing: after MAX_FAILS wrong tries for the same
# username + device, further tries are refused for WINDOW seconds.
MAX_FAILS = 8
WINDOW = 15 * 60
_fails = {}
_fails_lock = threading.Lock()


def _recent(key):
    now = time.time()
    hits = [t for t in _fails.get(key, []) if now - t < WINDOW]
    if hits:
        _fails[key] = hits
    else:
        _fails.pop(key, None)
    return hits


def login_blocked(key):
    """Seconds the caller must still wait, or 0 if the login may proceed."""
    with _fails_lock:
        hits = _recent(key)
        if len(hits) >= MAX_FAILS:
            return int(WINDOW - (time.time() - hits[0])) + 1
        return 0


def login_failed(key):
    with _fails_lock:
        _recent(key)
        _fails.setdefault(key, []).append(time.time())


def login_succeeded(key):
    with _fails_lock:
        _fails.pop(key, None)
