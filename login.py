import json
import os

ACCOUNTSFILE = "accounts.json"

# accounts.json is reserved for the SYSTEM ADMIN login only (/admin/login).
# Business manager/owner accounts live in business_accounts.json and are
# managed via business_login.py + the /admin/accounts route in app.py —
# do not add business-role accounts back into this file.

def load_accounts():
    try:
        with open(ACCOUNTSFILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_accounts(data):
    with open(ACCOUNTSFILE, "w") as f:
        json.dump(data, f, indent=4)

def first_time_setup():
    """Create the default admin account for web deployment (no terminal input needed)."""
    accounts = {
        "admin": {
            "password": os.environ.get("ADMIN_PASSWORD", "admin123"),
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
        if username in accounts and accounts[username]["password"] == password:
            print(f"\n  Welcome, {username.upper()}!")
            return username, accounts[username]["role"]
        remaining = 2 - attempt
        if remaining > 0:
            print(f"  Incorrect credentials. {remaining} attempt(s) left.")
        else:
            print("  Too many failed attempts.")
    return None, None
