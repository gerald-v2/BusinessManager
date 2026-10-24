import security as sec
import datastore as ds
import json
import os

ACCOUNTSFILE = "accounts.json"

# accounts.json is reserved for the SYSTEM ADMIN login only (/admin/login).
# Business manager/owner accounts live in business_accounts.json and are
# managed via business_login.py + the /admin/accounts route in app.py —
# do not add business-role accounts back into this file.

def load_accounts():
    return ds.load_json(ACCOUNTSFILE, dict)

def save_accounts(data):
    ds.save_json(ACCOUNTSFILE, data)

def first_time_setup():
    """Create the default admin account for web deployment (no terminal input needed)."""
    # Never fall back to a guessable password such as "admin123".
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        import secrets
        password = secrets.token_urlsafe(12)
        print("=" * 60)
        print("[security] ADMIN_PASSWORD is not set. A one-time admin password")
        print(f"[security] was generated for the 'admin' account: {password}")
        print("[security] Set ADMIN_PASSWORD on Render to choose your own.")
        print("=" * 60)
    accounts = {
        "admin": {
            "password": sec.hash_pw(password),
            "role": "admin"
        }
    }
    save_accounts(accounts)
    return accounts

def login():
    """CLI login helper for the single system-admin account. Not used by the Flask app."""
    accounts = load_accounts()
    if not accounts:
        first_time_setup()
        accounts = load_accounts()

    print("\n" + "="*40)
    print("         BIZMANAGER — ADMIN LOGIN")
    print("="*40)
    for attempt in range(3):
        username = input("Username: ").strip().lower()
        password = input("Password: ").strip()
        if username in accounts and sec.verify(accounts[username]["password"], password)[0]:
            print(f"\n  Welcome, {username.upper()}!")
            return username, accounts[username]["role"]
        remaining = 2 - attempt
        if remaining > 0:
            print(f"  Incorrect credentials. {remaining} attempt(s) left.")
        else:
            print("  Too many failed attempts.")
    return None, None
