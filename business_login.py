import json
import datetime

BACCOUNTSFILE = "business_accounts.json"

MODULES = {
    "pos":       "Point of Sale (POS)",
    "crm":       "CRM — Customers",
    "finance":   "Financial Management",
    "products":  "Products / Inventory",
    "employees": "Employee Management",
    "marketing": "AI Marketing Tool",
}
MODULE_ORDER = ["products", "pos", "finance", "crm", "employees", "marketing"]

# ─────────────────────── BUSINESS ADMIN ACCOUNTS ──────────────

def load_business_accounts():
    try:
        with open(BACCOUNTSFILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_business_accounts(data):
    with open(BACCOUNTSFILE, "w") as f:
        json.dump(data, f, indent=4)

def get_business_admin(biz):
    return load_business_accounts().get(biz)

def setup_business_admin(biz):
    """First-time manager account setup for a business."""
    print(f"\n--- MANAGER ACCOUNT SETUP: {biz.upper()} ---")
    print("  Create a manager/CEO login for this business.")
    while True:
        username = input("  Username: ").strip().lower()
        if not username:
            print("  Username cannot be empty.")
            continue
        password = input("  Password: ").strip()
        if not password:
            print("  Password cannot be empty.")
            continue
        confirm = input("  Confirm password: ").strip()
        if password != confirm:
            print("  Passwords do not match.")
            continue
        accounts = load_business_accounts()
        accounts[biz] = {"username": username, "password": password}
        save_business_accounts(accounts)
        print(f"  Manager account created for {biz}. Username: {username}")
        return True

def change_admin_password(biz):
    accounts = load_business_accounts()
    if biz not in accounts:
        print("  No manager account found.")
        return
    old = input("  Current password: ").strip()
    if accounts[biz]["password"] != old:
        print("  Incorrect password.")
        return
    new = input("  New password: ").strip()
    confirm = input("  Confirm: ").strip()
    if not new or new != confirm:
        print("  Passwords do not match or empty.")
        return
    accounts[biz]["password"] = new
    save_business_accounts(accounts)
    print("  Manager password changed.")

# ─────────────────────── EMPLOYEE HELPERS ─────────────────────

def _load_employees():
    from business_finance import load_employees
    return load_employees()

def _save_employees(data):
    from business_finance import save_employees
    save_employees(data)

def _load_attendance():
    from business_finance import load_attendance
    return load_attendance()

def _save_attendance(data):
    from business_finance import save_attendance
    save_attendance(data)

# ─────────────────────── ATTENDANCE AUTO RECORD ───────────────

def record_login_attendance(biz, emp_name):
    """Clock in an employee automatically on login."""
    data = _load_attendance()
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%H:%M")
    if biz not in data:
        data[biz] = {}
    if today not in data[biz]:
        data[biz][today] = []
    already_in = any(
        r["employee"] == emp_name and r.get("clock_out") is None
        for r in data[biz][today]
    )
    if not already_in:
        data[biz][today].append({
            "employee": emp_name,
            "clock_in": now,
            "clock_out": None,
            "hours": None,
            "auto": True
        })
        _save_attendance(data)
        print(f"  Attendance: {emp_name} clocked IN at {now}.")

def clock_out_on_logout(biz, emp_name):
    """Clock out an employee automatically on logout."""
    data = _load_attendance()
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%H:%M")
    for r in data.get(biz, {}).get(today, []):
        if r["employee"] == emp_name and r.get("clock_out") is None:
            r["clock_out"] = now
            try:
                fmt = "%H:%M"
                t_in = datetime.datetime.strptime(r["clock_in"], fmt)
                t_out = datetime.datetime.strptime(now, fmt)
                r["hours"] = round((t_out - t_in).seconds / 3600, 2)
            except Exception:
                pass
            _save_attendance(data)
            print(f"  Attendance: {emp_name} clocked OUT at {now}.")
            return

# ─────────────────────── CREDENTIALS MANAGEMENT ───────────────

def set_employee_credentials_menu(biz):
    """Set or reset login username/password for an employee."""
    emps = _load_employees()
    biz_emps = emps.get(biz, [])
    if not biz_emps:
        print("  No employees on record.")
        return
    print("\n--- SET EMPLOYEE LOGIN CREDENTIALS ---")
    for i, e in enumerate(biz_emps, 1):
        status = f"@{e['username']}" if e.get("username") else "(no login)"
        print(f"  {i}. {e['name']} ({e.get('role','')})  {status}")
    try:
        idx = int(input("  Select employee: ")) - 1
        if not (0 <= idx < len(biz_emps)):
            print("  Invalid selection.")
            return
        emp = biz_emps[idx]
    except ValueError:
        print("  Invalid input.")
        return

    print(f"\n  Setting credentials for: {emp['name']}")
    username = input("  Username: ").strip().lower()
    if not username:
        print("  Username cannot be empty.")
        return
    admin = get_business_admin(biz)
    if admin and admin["username"] == username:
        print("  That username is reserved for the manager account.")
        return
    for other in biz_emps:
        if other["name"] != emp["name"] and (other.get("username") or "").lower() == username:
            print(f"  Username already in use by {other['name']}.")
            return
    password = input("  Password: ").strip()
    if not password:
        print("  Password cannot be empty.")
        return
    confirm = input("  Confirm password: ").strip()
    if password != confirm:
        print("  Passwords do not match.")
        return
    emp["username"] = username
    emp["password"] = password
    _save_employees(emps)
    print(f"  Login set for {emp['name']} — username: @{username}")

# ─────────────────────── PERMISSIONS MANAGEMENT ───────────────

def set_employee_permissions_menu(biz):
    """Toggle which modules an employee can access."""
    emps = _load_employees()
    biz_emps = emps.get(biz, [])
    if not biz_emps:
        print("  No employees on record.")
        return
    print("\n--- SET EMPLOYEE PERMISSIONS ---")
    for i, e in enumerate(biz_emps, 1):
        perms = e.get("permissions", [])
        perm_str = ", ".join(MODULES[p] for p in MODULE_ORDER if p in perms) or "None"
        login_str = f"@{e['username']}" if e.get("username") else "(no login)"
        print(f"  {i}. {e['name']} | {login_str} | Access: {perm_str}")
    try:
        idx = int(input("  Select employee: ")) - 1
        if not (0 <= idx < len(biz_emps)):
            print("  Invalid selection.")
            return
        emp = biz_emps[idx]
    except ValueError:
        print("  Invalid input.")
        return

    current = emp.get("permissions", [])
    print(f"\n  Permissions for {emp['name']} — toggle by entering numbers:")
    print("  (Space-separated, or type 'all' / 'none')\n")
    for i, key in enumerate(MODULE_ORDER, 1):
        marker = "[X]" if key in current else "[ ]"
        print(f"  {i}. {marker} {MODULES[key]}")

    raw = input("\n  > ").strip().lower()
    if raw == "all":
        new_perms = list(MODULE_ORDER)
    elif raw == "none":
        new_perms = []
    else:
        new_perms = list(current)
        for token in raw.split():
            try:
                num = int(token) - 1
                if 0 <= num < len(MODULE_ORDER):
                    key = MODULE_ORDER[num]
                    if key in new_perms:
                        new_perms.remove(key)
                    else:
                        new_perms.append(key)
            except ValueError:
                pass
        new_perms = [k for k in MODULE_ORDER if k in new_perms]

    emp["permissions"] = new_perms
    _save_employees(emps)
    perm_str = ", ".join(MODULES[p] for p in new_perms) or "None"
    print(f"  Permissions updated for {emp['name']}: {perm_str}")

# ─────────────────────── MANAGER SETTINGS MENU ────────────────

def manage_business_admin_menu(biz):
    """Manager-only settings: password, employee credentials, permissions."""
    while True:
        admin = get_business_admin(biz)
        print(f"\n--- MANAGER SETTINGS: {biz.upper()} ---")
        print(f"  Manager username: {admin['username'] if admin else 'Not set'}")
        print("1: Change Manager Password")
        print("2: Set Employee Login Credentials")
        print("3: Set Employee Permissions")
        print("4: Back")
        try:
            choice = int(input("  Option: "))
            if choice == 1:
                change_admin_password(biz)
            elif choice == 2:
                set_employee_credentials_menu(biz)
            elif choice == 3:
                set_employee_permissions_menu(biz)
            elif choice == 4:
                break
            else:
                print("  Enter 1-4.")
        except ValueError:
            print("  Invalid input.")

# ─────────────────────── LOGIN FLOW ───────────────────────────

def business_login_flow():
    """
    Select business, then authenticate as manager or staff.
    Returns ("admin", biz, None), ("employee", biz, emp_dict), or (None, None, None).
    """
    try:
        import business_manager as bm
        businesses = bm.load_business()
        biz_list = list(businesses.keys())
    except Exception:
        biz_list = []

    if not biz_list:
        print("  No businesses found. Use System Login to create one first.")
        return None, None, None

    print("\n" + "="*40)
    print("      BUSINESS / STAFF LOGIN")
    print("="*40)
    for i, b in enumerate(biz_list, 1):
        print(f"  {i}. {b}")
    try:
        idx = int(input("  Select business: ")) - 1
        if not (0 <= idx < len(biz_list)):
            print("  Invalid selection.")
            return None, None, None
        biz = biz_list[idx]
    except ValueError:
        print("  Invalid input.")
        return None, None, None

    admin = get_business_admin(biz)
    if not admin:
        prompt = input(f"  No manager account set up for {biz}. Set one up now? (Y/N): ").strip().upper()
        if prompt == "Y":
            setup_business_admin(biz)
            admin = get_business_admin(biz)
        else:
            return None, None, None

    print(f"\n  {biz}")
    for attempt in range(3):
        username = input("  Username: ").strip().lower()
        password = input("  Password: ").strip()

        if username == admin["username"] and password == admin["password"]:
            print(f"\n  Welcome, {username.upper()} (Manager)")
            return "admin", biz, None

        for emp in _load_employees().get(biz, []):
            if (emp.get("username") or "").lower() == username and (emp.get("password") or "") == password:
                perms = emp.get("permissions", [])
                print(f"\n  Welcome, {emp['name']}!")
                if not perms:
                    print("  Note: No modules have been assigned to your account yet.")
                    print("  Contact your manager to set up your access.")
                record_login_attendance(biz, emp["name"])
                return "employee", biz, emp

        remaining = 2 - attempt
        if remaining > 0:
            print(f"  Incorrect credentials. {remaining} attempt(s) left.")
        else:
            print("  Too many failed attempts.")

    return None, None, None
