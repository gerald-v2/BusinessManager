"""
Firebase Realtime Database sync layer.

Render's free tier wipes the local filesystem on every restart/redeploy.
This module keeps all of BizManager's JSON data files backed up to Firebase:

- On startup: download_all() pulls the latest data from Firebase and
  writes it to the local JSON files, restoring everything (including
  base64 product images) before the app starts handling requests.

- After every data-changing request: upload_all() pushes the current
  contents of all local JSON files back to Firebase in one request.

No Firebase SDK needed - just plain HTTPS calls to the Realtime
Database REST API.
"""

import os
import json
import requests

# Default Firebase Realtime Database URL for BizManager.
# Can be overridden with the FIREBASE_URL environment variable.
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
]


def _key(filename: str) -> str:
    """Firebase keys can't contain '.' - turn 'Businesses.json' into 'Businesses'."""
    return filename[:-5] if filename.endswith('.json') else filename


def download_all():
    """Restore all JSON files from Firebase to local disk. Call once on startup."""
    try:
        resp = requests.get(f"{FIREBASE_URL}/.json", timeout=15)
        if resp.status_code != 200:
            print(f"[firebase_sync] Restore failed: HTTP {resp.status_code}")
            return
        data = resp.json() or {}
        for fname in JSON_FILES:
            key = _key(fname)
            if key in data and data[key] is not None:
                with open(fname, 'w') as f:
                    json.dump(data[key], f, indent=2)
                print(f"[firebase_sync] Restored {fname}")
    except Exception as e:
        print(f"[firebase_sync] Restore failed: {e}")


def upload_all():
    """Push all local JSON files to Firebase (merged, not a full overwrite)."""
    payload = {}
    for fname in JSON_FILES:
        if os.path.exists(fname):
            try:
                with open(fname) as f:
                    payload[_key(fname)] = json.load(f)
            except Exception as e:
                print(f"[firebase_sync] Could not read {fname}: {e}")
    if not payload:
        return
    try:
        requests.patch(f"{FIREBASE_URL}/.json", data=json.dumps(payload), timeout=20)
    except Exception as e:
        print(f"[firebase_sync] Upload failed: {e}")
