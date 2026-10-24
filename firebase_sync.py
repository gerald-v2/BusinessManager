"""
Firebase Realtime Database sync layer.

Render's free tier wipes the local filesystem on every restart/redeploy, so
BizManager keeps a copy of every JSON data file in Firebase:

* On startup  download_all() restores the files from Firebase.
* After every data-changing request schedule_upload() pushes changed files back.

Safety rules (these exist because a sync layer that gets it wrong destroys data)
-------------------------------------------------------------------------------
1. FAIL CLOSED.  Until a restore has succeeded the app does NOT upload anything.
   Otherwise a failed restore leaves stale/seed files on disk and the next save
   would overwrite your real data in Firebase with them.  app.py also refuses
   changes (HTTP 503) until the restore has worked, and retries it.
2. AUTHENTICATED.  Set FIREBASE_AUTH on Render (database secret or access token)
   and lock the database rules - see CHANGES.md.  Without it requests are
   anonymous and only work while your rules are open to the whole internet.
3. ORDERED.  One upload at a time, always reading the newest files at send time,
   so a slow old upload can never land after (and overwrite) a newer one.
4. NEVER PUSH EMPTY OR DAMAGED FILES.  An empty object deletes the node in
   Firebase, so empty/unreadable files are skipped.
5. ANY NAME WORKS.  Firebase rejects keys containing . $ # [ ] / so product and
   business names such as "Coke 1.5L" used to make EVERY backup fail.  Those
   characters are escaped on upload and restored on download.

Environment variables
---------------------
FIREBASE_URL   database URL (defaults to the original one)
FIREBASE_AUTH  database secret / access token, sent as ?auth=...
FIREBASE_SYNC  set to "off" to disable sync (local development)
"""

import hashlib
import json
import os
import re
import threading
import time

import requests

import datastore as ds

FIREBASE_URL = os.environ.get(
    'FIREBASE_URL',
    'https://biz-manager-ec82d-default-rtdb.europe-west1.firebasedatabase.app'
).rstrip('/')

# Every local JSON data file that should be backed up / restored.
JSON_FILES = [
    "Businesses.json",
    "business_accounts.json",
    "accounts.json",
    "employees.json",
    "Business_Finance.json",
    "exchange_rates.json",
    "attendance.json",
    "salary_advances.json",
    "crm_customers.json",
    "leave.json",
    "pos_sales.json",
    "price_monitor.json",
    "keywords.json",
    "sentiment.json",
    "campaigns.json",
    "biz_settings.json",
]


def enabled():
    return os.environ.get('FIREBASE_SYNC', 'on').strip().lower() not in ('off', '0', 'false', 'no')


def _params():
    token = os.environ.get('FIREBASE_AUTH', '').strip()
    return {'auth': token} if token else None


def _key(filename: str) -> str:
    """Firebase keys can't contain '.' - turn 'Businesses.json' into 'Businesses'."""
    return filename[:-5] if filename.endswith('.json') else filename


# ── key escaping ─────────────────────────────────────────────────────────────
_UNSAFE = set('.$#[]/%')
_DECODE = re.compile(r'%(2E|24|23|5B|5D|2F|25|[01][0-9A-F]|7F)')


def _enc_key(k):
    k = str(k)
    if k == '':
        return '%00EMPTY'
    return ''.join(f'%{ord(c):02X}' if (c in _UNSAFE or ord(c) < 32 or ord(c) == 127) else c
                   for c in k)


def _dec_key(k):
    if k == '%00EMPTY':
        return ''
    return _DECODE.sub(lambda m: chr(int(m.group(1), 16)), k)


def _walk(obj, fn):
    if isinstance(obj, dict):
        return {fn(k): _walk(v, fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v, fn) for v in obj]
    return obj


def encode_keys(obj):
    return _walk(obj, _enc_key)


def decode_keys(obj):
    return _walk(obj, _dec_key)


def _sig(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True).encode('utf-8')).hexdigest()


# ── state ────────────────────────────────────────────────────────────────────
_restored = not enabled()          # True once local files can be trusted
_last_restore_try = 0.0
_last_sent = {}                    # Firebase key -> signature of what Firebase holds
_upload_lock = threading.Lock()
_state_lock = threading.Lock()
_dirty = False
_worker_running = False
last_error = ''


def is_ready():
    return _restored


def download_all():
    """Restore all JSON files from Firebase to local disk.

    Returns True only if Firebase answered successfully (even if it held no
    data yet).  Returns False on any failure - callers must then NOT upload.
    """
    global _restored, _last_restore_try, last_error
    _last_restore_try = time.time()
    if not enabled():
        _restored = True
        return True
    try:
        resp = requests.get(f"{FIREBASE_URL}/.json", params=_params(), timeout=20)
        if resp.status_code != 200:
            last_error = f"restore HTTP {resp.status_code}"
            print(f"[firebase_sync] Restore failed: HTTP {resp.status_code} {resp.text[:120]}")
            return False
        data = resp.json() or {}
        if not isinstance(data, dict):
            last_error = "restore: unexpected data shape"
            print("[firebase_sync] Restore failed: unexpected data shape")
            return False
        for fname in JSON_FILES:
            key = _key(fname)
            if data.get(key) is not None:
                ds.save_json(fname, decode_keys(data[key]), indent=2)
                _last_sent[key] = _sig(data[key])
                print(f"[firebase_sync] Restored {fname}")
        _restored = True
        last_error = ''
        return True
    except Exception as e:                      # network down, bad JSON, disk error...
        last_error = f"restore: {e}"
        print(f"[firebase_sync] Restore failed: {e}")
        return False


def ensure_restored(min_interval=10):
    """Retry the restore (at most every `min_interval` seconds) until it works."""
    if _restored:
        return True
    if time.time() - _last_restore_try < min_interval:
        return False
    return download_all()


def upload_all():
    """Push every changed data file to Firebase.  Returns True on success."""
    global last_error
    if not enabled():
        return True
    if not _restored:
        print("[firebase_sync] Upload skipped: data has not been restored from Firebase yet")
        return False
    with _upload_lock:
        payload, sigs = {}, {}
        for fname in JSON_FILES:
            if not os.path.exists(fname):
                continue
            try:
                data = ds.load_json(fname, dict)
            except ds.DataCorruptError as e:
                print(f"[firebase_sync] Not uploading {fname}: {e}")
                continue
            if not data:
                continue                       # an empty object would DELETE the node
            enc = encode_keys(data)
            key = _key(fname)
            sig = _sig(enc)
            if _last_sent.get(key) != sig:
                payload[key] = enc
                sigs[key] = sig
        if not payload:
            return True
        try:
            resp = requests.patch(f"{FIREBASE_URL}/.json", params=_params(),
                                  data=json.dumps(payload), timeout=60)
        except Exception as e:
            last_error = f"upload: {e}"
            print(f"[firebase_sync] Upload exception: {e}")
            return False
        if resp.status_code == 200:
            _last_sent.update(sigs)
            last_error = ''
            print(f"[firebase_sync] Upload OK - keys: {list(payload.keys())}")
            return True
        last_error = f"upload HTTP {resp.status_code}"
        print(f"[firebase_sync] Upload FAILED: HTTP {resp.status_code} - {resp.text[:300]}")
        return False


def schedule_upload():
    """Request an upload in the background.  Many requests in a row collapse
    into as few uploads as possible, and uploads never overlap."""
    global _dirty, _worker_running
    with _state_lock:
        _dirty = True
        if _worker_running:
            return
        _worker_running = True
    threading.Thread(target=_worker, daemon=True).start()


def _worker():
    global _dirty, _worker_running
    while True:
        with _state_lock:
            if not _dirty:
                _worker_running = False
                return
            _dirty = False
        try:
            upload_all()
        except Exception as e:                   # never let the worker die silently
            print(f"[firebase_sync] Upload worker error: {e}")


_mtimes = {}


def files_changed():
    """True if any data file changed on disk since the last time this was asked.
    Cheap (16 stat calls) - lets us back up writes made by ANY request type."""
    changed = False
    for fname in JSON_FILES:
        try:
            m = os.stat(fname).st_mtime_ns
        except OSError:
            m = None
        if _mtimes.get(fname, 'unset') != m:
            if fname in _mtimes:
                changed = True
            _mtimes[fname] = m
    return changed


def status():
    return {
        'enabled': enabled(),
        'restored': _restored,
        'authenticated': bool(os.environ.get('FIREBASE_AUTH', '').strip()),
        'url': FIREBASE_URL,
        'last_error': last_error,
    }
