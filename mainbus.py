# 2026 DEVELOPMENT (BETA) TESTING
import marketing
import api_handler
import business_manager
import business_finance
import Pos
import crm
import login
import employees
import business_login

# ─────────────────────── SYSTEM ADMIN MENU ────────────────────

def admin_menu():
    businesses = business_manager.load_business()
    biz_list = list(businesses.keys())
    while True:
        print("\n" + "="*40)
        print("       BUSINESS PROGRAM — ADMIN")
        print("="*40)
        print("1: Business Management")
        print("2: Financial Management")
        print("3: Point of Sale (POS)")
        print("4: AI Marketing Tool")
        print("5: CRM — Customers")
        print("6: Employee Management")
        print("7: Account Management")
        print("8: Logout")

        try:
            selection = int(input("Option: "))
            if selection == 1:
                business_manager.business_menu()
                businesses = business_manager.load_business()
                biz_list = list(businesses.keys())
            elif selection == 2:
                business_finance.business_finance_menu()
            elif selection == 3:
                if not biz_list:
                    print("No businesses found. Create one in Business Management first.")
                else:
                    print("\nBusinesses:")
                    for i, b in enumerate(biz_list, 1):
                        print(f"  {i}. {b}")
                    try:
                        idx = int(input("Select business for POS: ")) - 1
                        if 0 <= idx < len(biz_list):
                            business_manager.businesses = businesses
                            Pos.pos_menu(biz_list[idx])
                        else:
                            print("Invalid selection.")
                    except ValueError:
                        print("Invalid input.")
            elif selection == 4:
                marketing.marketing_menu()
            elif selection == 5:
                if not biz_list:
                    print("No businesses found.")
                else:
                    print("\nBusinesses:")
                    for i, b in enumerate(biz_list, 1):
                        print(f"  {i}. {b}")
                    try:
                        idx = int(input("Select business for CRM: ")) - 1
                        if 0 <= idx < len(biz_list):
                            crm.crm_menu(biz_list[idx])
                        else:
                            print("Invalid selection.")
                    except ValueError:
                        print("Invalid input.")
            elif selection == 6:
                if not biz_list:
                    print("No businesses found.")
                else:
                    print("\nBusinesses:")
                    for i, b in enumerate(biz_list, 1):
                        print(f"  {i}. {b}")
                    try:
                        idx = int(input("Select business for Employee Management: ")) - 1
                        if 0 <= idx < len(biz_list):
                            employees.employee_menu(biz_list[idx])
                        else:
                            print("Invalid selection.")
                    except ValueError:
                        print("Invalid input.")
            elif selection == 7:
                businesses = business_manager.load_business()
                login.account_management_menu(list(businesses.keys()))
            elif selection == 8:
                print("Logged out.")
                break
            else:
                print("Enter 1-8.")
        except ValueError:
            print("Invalid input.")

# ─────────────────────── SYSTEM BUSINESS MENU ─────────────────

def business_menu_scoped(username, linked_businesses):
    businesses = business_manager.load_business()
    valid = [b for b in linked_businesses if b in businesses]
    if not valid:
        print(f"\n  No businesses linked to your account. Contact admin.")
        return

    if len(valid) == 1:
        active_biz = valid[0]
    else:
        print(f"\n  Your businesses:")
        for i, b in enumerate(valid, 1):
            print(f"  {i}. {b}")
        try:
            idx = int(input("Select business to manage: ")) - 1
            if 0 <= idx < len(valid):
                active_biz = valid[idx]
            else:
                print("Invalid selection.")
                return
        except ValueError:
            print("Invalid input.")
            return

    business_manager.businesses = businesses

    while True:
        print(f"\n" + "="*40)
        print(f"  {active_biz.upper()}")
        print("="*40)
        print("1: Products")
        print("2: Point of Sale (POS)")
        print("3: Financial Management")
        print("4: CRM — Customers")
        print("5: Employee Management")
        print("6: AI Marketing Tool")
        print("7: Change Password")
        print("8: Logout")

        try:
            selection = int(input("Option: "))
            if selection == 1:
                business_manager.product_menu(active_biz)
                businesses = business_manager.load_business()
                business_manager.businesses = businesses
            elif selection == 2:
                Pos.pos_menu(active_biz)
            elif selection == 3:
                business_finance_scoped(active_biz)
            elif selection == 4:
                crm.crm_menu(active_biz)
            elif selection == 5:
                employees.employee_menu(active_biz)
            elif selection == 6:
                marketing.marketing_menu()
            elif selection == 7:
                login.change_password(username)
            elif selection == 8:
                print("Logged out.")
                break
            else:
                print("Enter 1-8.")
        except ValueError:
            print("Invalid input.")

# ─────────────────────── FINANCE SCOPED ───────────────────────

def business_finance_scoped(biz):
    business_finance.business_finance = business_finance.load_business_finance()
    businesses = business_manager.load_business()
    sym = business_manager.get_currency_symbol(business_manager.get_business_currency(biz))
    while True:
        print(f"\n--- FINANCIAL MANAGEMENT: {biz.upper()} ---")
        print("1: View Revenue")
        print("2: View Profit")
        print("3: View Costs")
        print("4: Add Costs")
        print("5: Financial Summary")
        print("6: Financial Tips")
        print("7: Currency Tools")
        print("8: Back")
        try:
            opt = int(input("Option: "))
            if opt == 8:
                break
            elif opt == 1:
                business_finance.business_revenue(biz)
            elif opt == 2:
                business_finance.business_profit(biz)
            elif opt == 3:
                business_finance.business_costs(biz)
            elif opt == 4:
                try:
                    amount = float(input(f"Cost amount ({sym}): "))
                    desc = input("Description (press Enter to skip): ").strip()
                    business_finance.add_costs(biz, amount, desc)
                except ValueError:
                    print("Enter a valid amount.")
            elif opt == 5:
                business_finance.financial_summary(biz)
            elif opt == 6:
                while True:
                    print("\nFINANCIAL TIPS")
                    print("1: Revenue Tips | 2: Cost Tips | 3: Back")
                    try:
                        tip = int(input("Option: "))
                        if tip == 1:
                            business_finance.revenue_tips(biz)
                        elif tip == 2:
                            business_finance.cost_tips(biz)
                        elif tip == 3:
                            break
                        else:
                            print("Enter 1-3.")
                    except ValueError:
                        print("Invalid input.")
            elif opt == 7:
                business_finance.currency_tools_menu()
            else:
                print("Enter 1-8.")
        except ValueError:
            print("Invalid input.")

# ─────────────────────── BUSINESS ADMIN MENU ──────────────────

def business_admin_menu(biz):
    """Full-access menu for a business manager/CEO."""
    businesses = business_manager.load_business()
    business_manager.businesses = businesses
    while True:
        print(f"\n{'='*40}")
        print(f"  {biz.upper()} — MANAGER")
        print(f"{'='*40}")
        print("1: Products")
        print("2: Point of Sale (POS)")
        print("3: Financial Management")
        print("4: CRM — Customers")
        print("5: Employee Management")
        print("6: AI Marketing Tool")
        print("7: Manager Settings")
        print("8: Logout")
        try:
            selection = int(input("Option: "))
            if selection == 1:
                business_manager.product_menu(biz)
                businesses = business_manager.load_business()
                business_manager.businesses = businesses
            elif selection == 2:
                Pos.pos_menu(biz)
            elif selection == 3:
                business_finance_scoped(biz)
            elif selection == 4:
                crm.crm_menu(biz)
            elif selection == 5:
                employees.employee_menu(biz)
            elif selection == 6:
                marketing.marketing_menu()
            elif selection == 7:
                business_login.manage_business_admin_menu(biz)
            elif selection == 8:
                print(f"  Logged out of {biz}.")
                break
            else:
                print("Enter 1-8.")
        except ValueError:
            print("Invalid input.")

# ─────────────────────── BUSINESS STAFF MENU ──────────────────

def business_staff_menu(biz, emp):
    """Permission-gated menu for a business employee."""
    perms = emp.get("permissions", [])
    if not perms:
        print(f"\n  No modules have been assigned to {emp['name']} yet.")
        print("  Contact your manager to set up your access.")
        input("  Press Enter to return...")
        return

    businesses = business_manager.load_business()
    business_manager.businesses = businesses

    MODULE_ORDER = business_login.MODULE_ORDER
    MODULES = business_login.MODULES

    active = [(key, MODULES[key]) for key in MODULE_ORDER if key in perms]

    while True:
        print(f"\n{'='*40}")
        print(f"  {biz.upper()}")
        print(f"  Staff: {emp['name']}  |  {emp.get('role','')}")
        print(f"{'='*40}")
        for i, (key, label) in enumerate(active, 1):
            print(f"{i}: {label}")
        logout_num = len(active) + 1
        print(f"{logout_num}: Logout")

        try:
            selection = int(input("Option: "))
            if selection == logout_num:
                business_login.clock_out_on_logout(biz, emp["name"])
                print(f"  Goodbye, {emp['name']}!")
                break
            elif 1 <= selection <= len(active):
                key = active[selection - 1][0]
                if key == "products":
                    business_manager.product_menu(biz)
                    businesses = business_manager.load_business()
                    business_manager.businesses = businesses
                elif key == "pos":
                    Pos.pos_menu(biz)
                elif key == "finance":
                    business_finance_scoped(biz)
                elif key == "crm":
                    crm.crm_menu(biz)
                elif key == "employees":
                    employees.employee_menu(biz)
                elif key == "marketing":
                    marketing.marketing_menu()
            else:
                print(f"  Enter 1-{logout_num}.")
        except ValueError:
            print("  Invalid input.")

# ─────────────────────── MAIN PORTAL ──────────────────────────

def main():
    print("\n" + "="*40)
    print("     WELCOME TO BUSINESS PROGRAM")
    print("="*40)
    while True:
        print("\n1: System Login")
        print("2: Business / Staff Login")
        print("3: Exit")
        try:
            choice = int(input("Option: "))
        except ValueError:
            print("Invalid input.")
            continue

        if choice == 1:
            while True:
                username, role, linked_businesses = login.login()
                if username is None:
                    break
                if role == "admin":
                    admin_menu()
                elif role == "business":
                    business_menu_scoped(username, linked_businesses)
                again = input("\nLog in again? (Y/N): ").strip().upper()
                if again != "Y":
                    break

        elif choice == 2:
            login_type, biz, emp = business_login.business_login_flow()
            if login_type == "admin":
                business_admin_menu(biz)
            elif login_type == "employee":
                business_staff_menu(biz, emp)

        elif choice == 3:
            print("Goodbye!")
            break
        else:
            print("Enter 1-3.")

main()
