#BUSINESS FINANCIAL MANAGEMENT
import json

business_finance = {}

FINANCEFILE = "Business_Finance.json"
EMPLOYEEFILE = "employees.json"
EXCHANGEFILE = "exchange_rates.json"
ATTENDANCEFILE = "attendance.json"
ADVANCEFILE = "salary_advances.json"

def get_biz_symbol(name):
    try:
        import business_manager
        return business_manager.get_currency_symbol(business_manager.get_business_currency(name))
    except Exception:
        return "$"

#______REVENUE________
def business_revenue(name):
    global business_finance
    data = business_finance.get(name, {})
    revenue = data.get("Revenue", 0) or 0
    sym = get_biz_symbol(name)
    print(f"\n--- {name.upper()} REVENUE ---")
    print(f"Total Revenue: {sym}{revenue:.2f}")

def business_profit(name):
    global business_finance
    data = business_finance.get(name, {})
    revenue = data.get("Revenue", 0) or 0
    recorded_costs = data.get("Costs", 0) or 0
    payroll = get_monthly_payroll(name)
    total_costs = recorded_costs + payroll
    profit = revenue - total_costs
    sym = get_biz_symbol(name)
    print(f"\n--- {name.upper()} PROFIT ---")
    print(f"  Revenue:         {sym}{revenue:.2f}")
    print(f"  Recorded Costs:  {sym}{recorded_costs:.2f}")
    print(f"  Monthly Payroll: {sym}{payroll:.2f}")
    print(f"  Total Costs:     {sym}{total_costs:.2f}")
    print(f"  Net Profit:      {sym}{profit:.2f}")
    if profit > 0:
        print("  Status: PROFITABLE")
    elif profit == 0:
        print("  Status: BREAKING EVEN")
    else:
        print("  Status: AT A LOSS")

def add_revenue(name, revenue):
    global business_finance
    if name not in business_finance:
        saved = load_business_finance()
        business_finance[name] = saved.get(name, {"Revenue": 0, "Profit": 0, "Costs": 0})
    current = business_finance[name].get("Revenue", 0) or 0
    business_finance[name]["Revenue"] = current + revenue
    update_save_finance(name)

def financial_summary(name):
    global business_finance
    data = business_finance.get(name, {})
    revenue = data.get("Revenue", 0) or 0
    recorded_costs = data.get("Costs", 0) or 0
    payroll = get_monthly_payroll(name)
    total_costs = recorded_costs + payroll
    profit = revenue - total_costs
    margin = (profit / revenue * 100) if revenue > 0 else 0
    sym = get_biz_symbol(name)
    print(f"\n{'='*38}")
    print(f"  FINANCIAL SUMMARY: {name.upper()}")
    print(f"{'='*38}")
    print(f"  Revenue:          {sym}{revenue:.2f}")
    print(f"  Recorded Costs:   {sym}{recorded_costs:.2f}")
    print(f"  Monthly Payroll:  {sym}{payroll:.2f}")
    print(f"  Total Costs:      {sym}{total_costs:.2f}")
    print(f"  Net Profit:       {sym}{profit:.2f}")
    print(f"  Profit Margin:    {margin:.1f}%")
    print(f"{'='*38}")
    if profit > 0:
        print("  Status: PROFITABLE")
    elif profit == 0:
        print("  Status: BREAKING EVEN")
    else:
        print("  Status: AT A LOSS")

#_____COSTS______
def get_monthly_payroll(name):
    employees = load_employees().get(name, [])
    return sum(e.get("salary", 0) for e in employees)

def business_costs(name):
    global business_finance
    data = business_finance.get(name, {})
    recorded = data.get("Costs", 0) or 0
    payroll = get_monthly_payroll(name)
    total = recorded + payroll
    sym = get_biz_symbol(name)
    print(f"\n--- {name.upper()} COSTS ---")
    print(f"  Recorded Costs:  {sym}{recorded:.2f}")
    print(f"  Monthly Payroll: {sym}{payroll:.2f}")
    print(f"  Total Costs:     {sym}{total:.2f}")

def add_costs(name, amount, description=""):
    global business_finance
    if name not in business_finance:
        saved = load_business_finance()
        business_finance[name] = saved.get(name, {"Revenue": 0, "Profit": 0, "Costs": 0})
    current = business_finance[name].get("Costs", 0) or 0
    business_finance[name]["Costs"] = current + amount
    desc_text = f" ({description})" if description else ""
    sym = get_biz_symbol(name)
    print(f"Cost of {sym}{amount:.2f}{desc_text} recorded. Total costs: {sym}{business_finance[name]['Costs']:.2f}")
    update_save_finance(name)

#_____SALARY ADVANCES_____
def load_advances():
    try:
        with open(ADVANCEFILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_advances(data):
    with open(ADVANCEFILE, "w") as f:
        json.dump(data, f, indent=4)

def get_outstanding_advance(biz, emp_name, advances):
    total = sum(
        a["amount"] for a in advances.get(biz, [])
        if a["employee"] == emp_name and not a["repaid"]
    )
    return total

def __removed_placeholder():
    pass

def __removed_advance_menu_kept_for_data_only():
    advances = load_advances()
    while True:
        print(f"\n--- SALARY ADVANCES ---")
        print("1: Record Advance")
        print("2: View Advances")
        print("3: Mark Advance as Repaid")
        print("4: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                if not employees:
                    print("No employees on record.")
                    continue
                print("\nEmployees:")
                for i, e in enumerate(employees, 1):
                    outstanding = get_outstanding_advance(biz, e["name"], advances)
                    net = e["salary"] - outstanding
                    print(f"  {i}. {e['name']} ({e['role']}) | Salary: {sym}{e['salary']:.2f} | Outstanding Advance: {sym}{outstanding:.2f} | Net Payout: {sym}{net:.2f}")
                try:
                    idx = int(input("Select employee: ")) - 1
                    if not (0 <= idx < len(employees)):
                        print("Invalid selection.")
                        continue
                    emp = employees[idx]
                except ValueError:
                    print("Invalid input.")
                    continue
                outstanding = get_outstanding_advance(biz, emp["name"], advances)
                max_advance = emp["salary"] - outstanding
                if max_advance <= 0:
                    print(f"  {emp['name']} has no remaining salary available for an advance.")
                    continue
                print(f"  Max available advance: {sym}{max_advance:.2f}")
                try:
                    amount = float(input(f"Advance amount ({sym}): "))
                except ValueError:
                    print("Invalid amount.")
                    continue
                if amount <= 0:
                    print("Amount must be greater than zero.")
                    continue
                if amount > max_advance:
                    print(f"  Amount exceeds available salary. Max: {sym}{max_advance:.2f}")
                    continue
                reason = input("Reason (press Enter to skip): ").strip()
                import datetime
                date_str = datetime.date.today().isoformat()
                if biz not in advances:
                    advances[biz] = []
                advances[biz].append({
                    "employee": emp["name"],
                    "amount": amount,
                    "date": date_str,
                    "reason": reason if reason else "Not specified",
                    "repaid": False,
                    "repaid_date": None
                })
                save_advances(advances)
                new_outstanding = get_outstanding_advance(biz, emp["name"], advances)
                net = emp["salary"] - new_outstanding
                print(f"\n  Advance recorded for {emp['name']}:")
                print(f"    Advance Given:      {sym}{amount:.2f}")
                print(f"    Total Outstanding:  {sym}{new_outstanding:.2f}")
                print(f"    Net Salary Payout:  {sym}{net:.2f}")

            elif choice == 2:
                biz_advances = advances.get(biz, [])
                if not biz_advances:
                    print(f"  No salary advances recorded for {biz}.")
                    continue
                print(f"\n--- ADVANCE RECORDS: {biz.upper()} ---")
                grouped = {}
                for a in biz_advances:
                    grouped.setdefault(a["employee"], []).append(a)
                for emp_name, records in grouped.items():
                    emp_data = next((e for e in employees if e["name"] == emp_name), None)
                    salary = emp_data["salary"] if emp_data else 0
                    outstanding = sum(a["amount"] for a in records if not a["repaid"])
                    net = salary - outstanding
                    print(f"\n  {emp_name}")
                    print(f"  {'Date':<12} {'Amount':<12} {'Reason':<20} {'Status'}")
                    print(f"  {'-'*58}")
                    for a in records:
                        status = "Repaid" if a["repaid"] else "Outstanding"
                        repaid_note = f" (on {a['repaid_date']})" if a["repaid"] and a["repaid_date"] else ""
                        print(f"  {a['date']:<12} {sym}{a['amount']:<11.2f} {a['reason']:<20} {status}{repaid_note}")
                    print(f"  {'-'*58}")
                    print(f"  Outstanding: {sym}{outstanding:.2f} | Salary: {sym}{salary:.2f} | Net Payout: {sym}{net:.2f}")

            elif choice == 3:
                biz_advances = [a for a in advances.get(biz, []) if not a["repaid"]]
                if not biz_advances:
                    print(f"  No outstanding advances for {biz}.")
                    continue
                print(f"\nOutstanding Advances — {biz}:")
                for i, a in enumerate(biz_advances, 1):
                    print(f"  {i}. {a['employee']} | {sym}{a['amount']:.2f} on {a['date']} | Reason: {a['reason']}")
                try:
                    sel = int(input("Select advance to mark as repaid: ")) - 1
                    if not (0 <= sel < len(biz_advances)):
                        print("Invalid selection.")
                        continue
                    chosen = biz_advances[sel]
                except ValueError:
                    print("Invalid input.")
                    continue
                import datetime
                repaid_date = datetime.date.today().isoformat()
                for a in advances[biz]:
                    if (a["employee"] == chosen["employee"] and
                            a["amount"] == chosen["amount"] and
                            a["date"] == chosen["date"] and
                            not a["repaid"]):
                        a["repaid"] = True
                        a["repaid_date"] = repaid_date
                        break
                save_advances(advances)
                print(f"  Advance of {sym}{chosen['amount']:.2f} for {chosen['employee']} marked as repaid on {repaid_date}.")

            elif choice == 4:
                break
            else:
                print("Enter 1-4.")
        except ValueError:
            print("Invalid input.")

#_____ATTENDANCE_____
def load_attendance():
    try:
        with open(ATTENDANCEFILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_attendance(data):
    with open(ATTENDANCEFILE, "w") as f:
        json.dump(data, f, indent=4)

def __removed_attendance_menu_placeholder():
    pass

def __removed_attendance_menu(businesses):
    import datetime
    data = load_attendance()
    while True:
        print("\n--- ATTENDANCE ---")
        print("1: Clock In")
        print("2: Clock Out")
        print("3: View Attendance (by date)")
        print("4: View Employee History")
        print("5: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                biz = input("Business Name: ").title()
                if biz not in businesses:
                    print("Business not found.")
                    continue
                employees = load_employees().get(biz, [])
                if not employees:
                    print(f"No employees found for {biz}.")
                    continue
                print("Employees:")
                for i, e in enumerate(employees, 1):
                    print(f"  {i}. {e['name']} ({e['role']})")
                try:
                    idx = int(input("Select employee: ")) - 1
                    if not (0 <= idx < len(employees)):
                        print("Invalid selection.")
                        continue
                    emp_name = employees[idx]["name"]
                except ValueError:
                    print("Invalid input.")
                    continue
                today = datetime.date.today().isoformat()
                now = datetime.datetime.now().strftime("%H:%M")
                confirm = input(f"Clock in {emp_name} at {now}? (Y to confirm or enter custom time HH:MM): ").strip()
                clock_time = confirm if (":" in confirm and confirm.upper() != "Y") else now
                if biz not in data:
                    data[biz] = {}
                if today not in data[biz]:
                    data[biz][today] = []
                already_in = any(
                    r["employee"] == emp_name and r.get("clock_out") is None
                    for r in data[biz][today]
                )
                if already_in:
                    print(f"{emp_name} is already clocked in today.")
                else:
                    data[biz][today].append({"employee": emp_name, "clock_in": clock_time, "clock_out": None, "hours": None})
                    save_attendance(data)
                    print(f"  {emp_name} clocked IN at {clock_time} on {today}.")

            elif choice == 2:
                biz = input("Business Name: ").title()
                if biz not in businesses:
                    print("Business not found.")
                    continue
                today = datetime.date.today().isoformat()
                open_records = [
                    (i, r) for i, r in enumerate(data.get(biz, {}).get(today, []))
                    if r.get("clock_out") is None
                ]
                if not open_records:
                    print("No employees currently clocked in today.")
                    continue
                print("Currently clocked in:")
                for j, (_, r) in enumerate(open_records, 1):
                    print(f"  {j}. {r['employee']} (in at {r['clock_in']})")
                try:
                    sel = int(input("Select employee to clock out: ")) - 1
                    if not (0 <= sel < len(open_records)):
                        print("Invalid selection.")
                        continue
                    orig_idx, record = open_records[sel]
                except ValueError:
                    print("Invalid input.")
                    continue
                now = datetime.datetime.now().strftime("%H:%M")
                confirm = input(f"Clock out {record['employee']} at {now}? (Y to confirm or enter custom time HH:MM): ").strip()
                clock_time = confirm if (":" in confirm and confirm.upper() != "Y") else now
                data[biz][today][orig_idx]["clock_out"] = clock_time
                try:
                    fmt = "%H:%M"
                    t_in = datetime.datetime.strptime(record["clock_in"], fmt)
                    t_out = datetime.datetime.strptime(clock_time, fmt)
                    hours = round((t_out - t_in).seconds / 3600, 2)
                    data[biz][today][orig_idx]["hours"] = hours
                    save_attendance(data)
                    print(f"  {record['employee']} clocked OUT at {clock_time}. Hours worked: {hours:.2f}h")
                except Exception:
                    save_attendance(data)
                    print(f"  {record['employee']} clocked OUT at {clock_time}.")

            elif choice == 3:
                biz = input("Business Name: ").title()
                date_input = input("Date (YYYY-MM-DD, or press Enter for today): ").strip()
                if not date_input:
                    date_input = datetime.date.today().isoformat()
                records = data.get(biz, {}).get(date_input, [])
                print(f"\n--- ATTENDANCE: {biz.upper()} | {date_input} ---")
                if not records:
                    print("  No records found for this date.")
                else:
                    print(f"  {'Employee':<20} {'Clock In':<10} {'Clock Out':<12} {'Hours'}")
                    print(f"  {'-'*52}")
                    for r in records:
                        clock_out = r.get("clock_out") or "Still in"
                        hours = f"{r['hours']:.2f}h" if r.get("hours") else "---"
                        print(f"  {r['employee']:<20} {r['clock_in']:<10} {clock_out:<12} {hours}")

            elif choice == 4:
                biz = input("Business Name: ").title()
                employees = load_employees().get(biz, [])
                if not employees:
                    print(f"No employees found for {biz}.")
                    continue
                print("Employees:")
                for i, e in enumerate(employees, 1):
                    print(f"  {i}. {e['name']}")
                try:
                    idx = int(input("Select employee: ")) - 1
                    if not (0 <= idx < len(employees)):
                        print("Invalid selection.")
                        continue
                    emp_name = employees[idx]["name"]
                except ValueError:
                    print("Invalid input.")
                    continue
                biz_records = data.get(biz, {})
                print(f"\n--- ATTENDANCE HISTORY: {emp_name.upper()} ---")
                print(f"  {'Date':<12} {'Clock In':<10} {'Clock Out':<12} {'Hours'}")
                print(f"  {'-'*48}")
                found = False
                total_hours = 0.0
                for date, day_records in sorted(biz_records.items()):
                    for r in day_records:
                        if r["employee"] == emp_name:
                            clock_out = r.get("clock_out") or "Still in"
                            hours = r.get("hours") or 0
                            total_hours += hours
                            hours_str = f"{hours:.2f}h" if hours else "---"
                            print(f"  {date:<12} {r['clock_in']:<10} {clock_out:<12} {hours_str}")
                            found = True
                if not found:
                    print("  No attendance records found.")
                else:
                    print(f"  {'-'*48}")
                    print(f"  Total Hours Recorded: {total_hours:.2f}h")

            elif choice == 5:
                break
            else:
                print("Enter 1-5.")
        except ValueError:
            print("Invalid input.")

#_____PROFIT TIPS____
def revenue_tips(name):
    global business_finance
    revenue = business_finance.get(name, {}).get("Revenue", 0) or 0
    sym = get_biz_symbol(name)
    print(f"\n--- REVENUE TIPS: {name.upper()} ---")
    if revenue == 0:
        print("  - Start recording all sales to track revenue accurately")
        print("  - Set a clear monthly revenue target to work towards")
        print("  - Identify which products or services to lead with")
        print("  - Promote your business on free platforms like social media")
    elif revenue < 1000:
        print("  - Focus on volume — sell more of what already works")
        print("  - Upsell extras to existing customers (e.g. accessories, add-ons)")
        print("  - Ask satisfied customers for referrals")
        print("  - Run a limited-time offer to drive quick sales")
    elif revenue < 10000:
        print("  - Expand your product or service range")
        print("  - Invest a portion of revenue back into marketing")
        print("  - Introduce a loyalty or rewards programme")
        print("  - Look for bulk order or B2B opportunities")
    else:
        print("  - Explore new markets or customer segments")
        print("  - Automate repetitive tasks to scale without extra cost")
        print("  - Build strategic partnerships for broader reach")
        print("  - Consider premium tiers or subscription-based pricing")
    print(f"\n  Current Revenue: {sym}{revenue:.2f}")

def cost_tips(name):
    global business_finance
    data = business_finance.get(name, {})
    revenue = data.get("Revenue", 0) or 0
    recorded_costs = data.get("Costs", 0) or 0
    payroll = get_monthly_payroll(name)
    total_costs = recorded_costs + payroll
    sym = get_biz_symbol(name)
    print(f"\n--- COST TIPS: {name.upper()} ---")
    print("  - Review all recurring expenses monthly and cut what isn't needed")
    print("  - Negotiate better rates with your suppliers")
    print("  - Buy materials in bulk where possible to lower unit costs")
    print("  - Track every expense — small costs add up quickly")
    print("  - Compare quotes from multiple vendors before committing")
    if revenue > 0 and total_costs > 0:
        ratio = (total_costs / revenue) * 100
        print(f"\n  Total Costs (inc. payroll): {sym}{total_costs:.2f}")
        print(f"  Cost-to-Revenue Ratio:      {ratio:.1f}%")
        if ratio > 80:
            print("  WARNING: Costs are very high relative to revenue. Urgent review needed.")
        elif ratio > 60:
            print("  Your costs are moderate. Look for 2-3 areas to reduce.")
        else:
            print("  Your cost ratio is healthy. Keep monitoring it.")

#____FINANCIAL STORAGE____
def load_business_finance():
    try:
        with open(FINANCEFILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def store_business_finance():
    with open(FINANCEFILE, "w") as file:
        json.dump(business_finance, file, indent=4)

def update_save_finance(name):
    existing = business_finance.get(name, {})
    revenue = existing.get("Revenue", 0) or 0
    costs = existing.get("Costs", 0) or 0
    business_finance[name] = {
        "Revenue": round(revenue, 2),
        "Costs": round(costs, 2),
        "Profit": round(revenue - costs, 2)
    }
    store_business_finance()

#____EMPLOYEE STORAGE____
def load_employees():
    try:
        with open(EMPLOYEEFILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_employees(data):
    with open(EMPLOYEEFILE, "w") as f:
        json.dump(data, f, indent=4)

#____CURRENCY TOOLS____
def load_exchange_rates():
    try:
        with open(EXCHANGEFILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_exchange_rates(data):
    with open(EXCHANGEFILE, "w") as f:
        json.dump(data, f, indent=4)

def daily_exchange_rate():
    data = load_exchange_rates()
    is_running = True
    while is_running:
        print("\n--- EXCHANGE RATES ---")
        print("1: Add / Update Rate")
        print("2: View Saved Rates")
        print("3: Remove Rate")
        print("4: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                from_curr = input("From currency (e.g. GBP): ").upper().strip()
                to_curr = input("To currency (e.g. USD): ").upper().strip()
                rate = float(input(f"Rate (1 {from_curr} = ? {to_curr}): "))
                key = f"{from_curr}_TO_{to_curr}"
                data[key] = rate
                save_exchange_rates(data)
                print(f"Saved: 1 {from_curr} = {rate} {to_curr}")
            elif choice == 2:
                if not data:
                    print("No exchange rates saved yet.")
                else:
                    print("\n--- SAVED RATES ---")
                    for key, rate in data.items():
                        parts = key.split("_TO_")
                        print(f"  1 {parts[0]} = {rate} {parts[1]}")
            elif choice == 3:
                if not data:
                    print("No rates to remove.")
                    continue
                keys = list(data.keys())
                for i, k in enumerate(keys, 1):
                    parts = k.split("_TO_")
                    print(f"  {i}. {parts[0]} → {parts[1]}")
                idx = int(input("Select rate to remove: ")) - 1
                if 0 <= idx < len(keys):
                    removed = keys[idx]
                    del data[removed]
                    save_exchange_rates(data)
                    print("Rate removed.")
                else:
                    print("Invalid selection.")
            elif choice == 4:
                is_running = False
            else:
                print("Enter 1-4.")
        except ValueError:
            print("Invalid input.")

def currency_converter():
    data = load_exchange_rates()
    if not data:
        print("No exchange rates saved. Please add rates first (Exchange Rates option).")
        return
    rate_list = list(data.items())
    print("\n--- CURRENCY CONVERTER ---")
    for i, (key, rate) in enumerate(rate_list, 1):
        parts = key.split("_TO_")
        print(f"  {i}. {parts[0]} → {parts[1]} (rate: {rate})")
    try:
        idx = int(input("Select conversion: ")) - 1
        if 0 <= idx < len(rate_list):
            key, rate = rate_list[idx]
            parts = key.split("_TO_")
            amount = float(input(f"Amount in {parts[0]}: $"))
            converted = amount * rate
            print(f"  {amount:.2f} {parts[0]} = {converted:.2f} {parts[1]}")
        else:
            print("Invalid selection.")
    except ValueError:
        print("Invalid input.")

def currency_tools_menu():
    while True:
        print("\n--- CURRENCY TOOLS ---")
        print("1: Manage Exchange Rates")
        print("2: Currency Converter")
        print("3: Back")
        try:
            option = int(input("Option: "))
            if option == 1:
                daily_exchange_rate()
            elif option == 2:
                currency_converter()
            elif option == 3:
                break
            else:
                print("Enter 1-3.")
        except ValueError:
            print("Invalid input.")

#_____MAIN_____
def business_finance_menu():
    import business_manager
    global business_finance
    business_finance = load_business_finance()
    businesses = business_manager.load_business()
    is_running = True
    while is_running:
        try:
            print("\nBUSINESS FINANCE MENU")
            print("OPTIONS")
            print("1: VIEW REVENUE")
            print("2: VIEW PROFIT")
            print("3: VIEW COSTS")
            print("4: ADD COSTS")
            print("5: FINANCIAL SUMMARY")
            print("6: FINANCIAL TIPS")
            print("7: CURRENCY TOOLS")
            print("8: EXIT")

            option = int(input("Option: "))

            if option == 8:
                is_running = False
            elif option == 7:
                currency_tools_menu()
            elif option in [1, 2, 3, 4, 5, 6]:
                business_name = input("Business Name: ").title()
                if business_name not in businesses:
                    print("Business not found.")
                    print("Redirecting to Business Management...")
                    business_manager.business_menu()
                    businesses = business_manager.load_business()
                    continue
                if option == 1:
                    business_revenue(business_name)
                elif option == 2:
                    business_profit(business_name)
                elif option == 3:
                    business_costs(business_name)
                elif option == 4:
                    try:
                        amount = float(input("Cost amount ($): "))
                        description = input("Description (press Enter to skip): ").strip()
                        add_costs(business_name, amount, description)
                    except ValueError:
                        print("Enter a valid amount.")
                elif option == 5:
                    financial_summary(business_name)
                elif option == 6:
                    while True:
                        print("\nFINANCIAL TIPS")
                        print("1: REVENUE TIPS | 2: COST TIPS | 3: BACK")
                        try:
                            tip_option = int(input("Option: "))
                            if tip_option == 1:
                                revenue_tips(business_name)
                            elif tip_option == 2:
                                cost_tips(business_name)
                            elif tip_option == 3:
                                break
                            else:
                                print("Pick 1-3.")
                        except ValueError:
                            print("Enter a number.")
            else:
                print("Enter option from 1-8.")
        except ValueError:
            print("Enter a number.")
