import json
import os

ACCOUNTSFILE = "accounts.json"

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
    """Create a default admin account for web deployment (no terminal input needed)."""
    accounts = {
        "admin": {
            "password": os.environ.get("ADMIN_PASSWORD", "admin123"),
            "role": "admin",
            "businesses": []
        }
    }
    save_accounts(accounts)
    return accounts

def login():
    accounts = load_accounts()
    if not accounts:
        first_time_setup()
        accounts = load_accounts()

    print("\n" + "="*40)
    print("         BIZMANAGER — LOGIN")
    print("="*40)
    for attempt in range(3):
        username = input("Username: ").strip().lower()
        password = input("Password: ").strip()
        if username in accounts and accounts[username]["password"] == password:
            acc = accounts[username]
            print(f"\n  Welcome, {username.upper()}!")
            return username, acc["role"], acc.get("businesses", [])
        remaining = 2 - attempt
        if remaining > 0:
            print(f"  Incorrect credentials. {remaining} attempt(s) left.")
        else:
            print("  Too many failed attempts.")
    return None, None, None

def create_account(businesses_list):
    accounts = load_accounts()
    print("\n--- CREATE ACCOUNT ---")
    username = input("New username: ").strip().lower()
    if not username:
        print("Username cannot be empty.")
        return
    if username in accounts:
        print("Username already exists.")
        return
    password = input("Password: ").strip()
    if not password:
        print("Password cannot be empty.")
        return
    linked = []
    accounts[username] = {"password": password, "role": "business", "businesses": linked}
    save_accounts(accounts)
    print(f"  Account '{username}' created.")

def view_accounts():
    accounts = load_accounts()
    if not accounts:
        print("No accounts found.")
        return
    for username, data in accounts.items():
        role = data.get("role", "business")
        bizzes = ", ".join(data.get("businesses", [])) or "None"
        print(f"  {username:<20} {role:<10} {bizzes}")

def delete_account(username):
    accounts = load_accounts()
    if username == "admin":
        print("  Cannot delete the admin account.")
        return
    if username in accounts:
        del accounts[username]
        save_accounts(accounts)
        print(f"  Account '{username}' deleted.")

def change_password(username):
    accounts = load_accounts()
    if username not in accounts:
        return
    accounts[username]["password"] = input("New password: ").strip()
    save_accounts(accounts)

def update_business_links(username, businesses_list):
    pass

def account_management_menu(businesses_list):
    pass
