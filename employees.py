import json
import datetime

LEAVEFILE = "leave.json"

def _load_employees():
    from business_finance import load_employees
    return load_employees()

def _save_employees(data):
    from business_finance import save_employees
    save_employees(data)

def _get_sym(biz):
    from business_finance import get_biz_symbol
    return get_biz_symbol(biz)

def _load_advances():
    from business_finance import load_advances
    return load_advances()

def _save_advances(data):
    from business_finance import save_advances
    save_advances(data)

def _get_outstanding(biz, name, advances):
    from business_finance import get_outstanding_advance
    return get_outstanding_advance(biz, name, advances)

def _load_attendance():
    from business_finance import load_attendance
    return load_attendance()

def _save_attendance(data):
    from business_finance import save_attendance
    save_attendance(data)

def load_leave():
    try:
        with open(LEAVEFILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_leave(data):
    with open(LEAVEFILE, "w") as f:
        json.dump(data, f, indent=4)

# ─────────────────────────────────────────────
# SALARY ADVANCES
# ─────────────────────────────────────────────
def salary_advance_menu(biz, employees, sym):
    advances = _load_advances()
    while True:
        print(f"\n--- SALARY ADVANCES: {biz.upper()} ---")
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
                    outstanding = _get_outstanding(biz, e["name"], advances)
                    net = e["salary"] - outstanding
                    print(f"  {i}. {e['name']} ({e['role']}) | Salary: {sym}{e['salary']:.2f} | Outstanding: {sym}{outstanding:.2f} | Net Payout: {sym}{net:.2f}")
                try:
                    idx = int(input("Select employee: ")) - 1
                    if not (0 <= idx < len(employees)):
                        print("Invalid selection.")
                        continue
                    emp = employees[idx]
                except ValueError:
                    print("Invalid input.")
                    continue
                outstanding = _get_outstanding(biz, emp["name"], advances)
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
                _save_advances(advances)
                new_outstanding = _get_outstanding(biz, emp["name"], advances)
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
                repaid_date = datetime.date.today().isoformat()
                for a in advances[biz]:
                    if (a["employee"] == chosen["employee"] and
                            a["amount"] == chosen["amount"] and
                            a["date"] == chosen["date"] and
                            not a["repaid"]):
                        a["repaid"] = True
                        a["repaid_date"] = repaid_date
                        break
                _save_advances(advances)
                print(f"  Advance of {sym}{chosen['amount']:.2f} for {chosen['employee']} marked as repaid on {repaid_date}.")

            elif choice == 4:
                break
            else:
                print("Enter 1-4.")
        except ValueError:
            print("Invalid input.")

# ─────────────────────────────────────────────
# ATTENDANCE
# ─────────────────────────────────────────────
def attendance_menu(biz):
    data = _load_attendance()
    employees = _load_employees().get(biz, [])
    while True:
        print(f"\n--- ATTENDANCE: {biz.upper()} ---")
        print("1: Clock In")
        print("2: Clock Out")
        print("3: View Attendance (by date)")
        print("4: View Employee History")
        print("5: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                employees = _load_employees().get(biz, [])
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
                    print(f"  {emp_name} is already clocked in today.")
                else:
                    data[biz][today].append({"employee": emp_name, "clock_in": clock_time, "clock_out": None, "hours": None})
                    _save_attendance(data)
                    print(f"  {emp_name} clocked IN at {clock_time} on {today}.")

            elif choice == 2:
                today = datetime.date.today().isoformat()
                open_records = [
                    (i, r) for i, r in enumerate(data.get(biz, {}).get(today, []))
                    if r.get("clock_out") is None
                ]
                if not open_records:
                    print("  No employees currently clocked in today.")
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
                    _save_attendance(data)
                    print(f"  {record['employee']} clocked OUT at {clock_time}. Hours worked: {hours:.2f}h")
                except Exception:
                    _save_attendance(data)
                    print(f"  {record['employee']} clocked OUT at {clock_time}.")

            elif choice == 3:
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
                employees = _load_employees().get(biz, [])
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

# ─────────────────────────────────────────────
# LEAVE MANAGEMENT
# ─────────────────────────────────────────────
def leave_menu(biz, employees, sym):
    leave_data = load_leave()
    while True:
        print(f"\n--- LEAVE MANAGEMENT: {biz.upper()} ---")
        print("1: Record Leave")
        print("2: View Leave History")
        print("3: Leave Summary (all employees)")
        print("4: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                if not employees:
                    print("No employees on record.")
                    continue
                print("\nEmployees:")
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
                print("  Leave type: 1) Annual  2) Sick  3) Unpaid  4) Other")
                type_map = {"1": "Annual", "2": "Sick", "3": "Unpaid", "4": "Other"}
                t_choice = input("  Type: ").strip()
                leave_type = type_map.get(t_choice, "Other")
                start = input("  Start date (YYYY-MM-DD): ").strip()
                end = input("  End date (YYYY-MM-DD): ").strip()
                try:
                    fmt = "%Y-%m-%d"
                    d_start = datetime.datetime.strptime(start, fmt).date()
                    d_end = datetime.datetime.strptime(end, fmt).date()
                    days = (d_end - d_start).days + 1
                    if days <= 0:
                        print("  End date must be after start date.")
                        continue
                except ValueError:
                    print("  Invalid date format.")
                    continue
                reason = input("  Reason (press Enter to skip): ").strip()
                if biz not in leave_data:
                    leave_data[biz] = {}
                if emp_name not in leave_data[biz]:
                    leave_data[biz][emp_name] = []
                leave_data[biz][emp_name].append({
                    "type": leave_type,
                    "start": start,
                    "end": end,
                    "days": days,
                    "reason": reason if reason else "Not specified",
                    "recorded": datetime.date.today().isoformat()
                })
                save_leave(leave_data)
                print(f"  {emp_name}: {days} day(s) of {leave_type} leave recorded ({start} to {end}).")

            elif choice == 2:
                if not employees:
                    print("No employees.")
                    continue
                print("\nEmployees:")
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
                records = leave_data.get(biz, {}).get(emp_name, [])
                if not records:
                    print(f"  No leave records for {emp_name}.")
                    continue
                print(f"\n  --- LEAVE HISTORY: {emp_name.upper()} ---")
                print(f"  {'Type':<10} {'Start':<12} {'End':<12} {'Days':<6} {'Reason'}")
                print(f"  {'-'*58}")
                totals = {}
                for r in records:
                    print(f"  {r['type']:<10} {r['start']:<12} {r['end']:<12} {r['days']:<6} {r['reason']}")
                    totals[r["type"]] = totals.get(r["type"], 0) + r["days"]
                print(f"  {'-'*58}")
                for ltype, total_days in totals.items():
                    print(f"  {ltype}: {total_days} day(s) total")

            elif choice == 3:
                biz_leave = leave_data.get(biz, {})
                if not biz_leave:
                    print(f"  No leave records for {biz}.")
                    continue
                print(f"\n--- LEAVE SUMMARY: {biz.upper()} ---")
                print(f"  {'Employee':<20} {'Annual':<8} {'Sick':<8} {'Unpaid':<8} {'Other':<8} {'Total'}")
                print(f"  {'-'*60}")
                for emp_name, records in biz_leave.items():
                    ann = sum(r["days"] for r in records if r["type"] == "Annual")
                    sick = sum(r["days"] for r in records if r["type"] == "Sick")
                    unpaid = sum(r["days"] for r in records if r["type"] == "Unpaid")
                    other = sum(r["days"] for r in records if r["type"] == "Other")
                    total = ann + sick + unpaid + other
                    print(f"  {emp_name:<20} {ann:<8} {sick:<8} {unpaid:<8} {other:<8} {total}")

            elif choice == 4:
                break
            else:
                print("Enter 1-4.")
        except ValueError:
            print("Invalid input.")

# ─────────────────────────────────────────────
# EMPLOYEE PROFILE
# ─────────────────────────────────────────────
def employee_profile(biz, emp, sym):
    advances = _load_advances()
    attendance = _load_attendance()
    leave_data = load_leave()
    name = emp["name"]

    outstanding = _get_outstanding(biz, name, advances)
    net_pay = emp["salary"] - outstanding

    biz_att = attendance.get(biz, {})
    total_hours = 0.0
    days_present = 0
    for day_records in biz_att.values():
        for r in day_records:
            if r["employee"] == name and r.get("hours"):
                total_hours += r["hours"]
                days_present += 1

    leave_records = leave_data.get(biz, {}).get(name, [])
    total_leave_days = sum(r["days"] for r in leave_records)

    advance_records = [a for a in advances.get(biz, []) if a["employee"] == name]

    print(f"\n{'='*45}")
    print(f"  EMPLOYEE PROFILE: {name.upper()}")
    print(f"{'='*45}")
    print(f"  Role:              {emp['role']}")
    print(f"  Monthly Salary:    {sym}{emp['salary']:.2f}")
    print(f"  Outstanding Adv.:  {sym}{outstanding:.2f}")
    print(f"  Net Payout:        {sym}{net_pay:.2f}")
    print(f"  Notes:             {emp.get('notes') or 'None'}")
    print(f"  {'─'*40}")
    print(f"  Attendance:")
    print(f"    Days Recorded:   {days_present}")
    print(f"    Total Hours:     {total_hours:.2f}h")
    print(f"  {'─'*40}")
    print(f"  Leave Days Taken:  {total_leave_days}")
    print(f"  Advances Taken:    {len(advance_records)} ({sum(a['amount'] for a in advance_records):.2f} total)")
    print(f"{'='*45}")

# ─────────────────────────────────────────────
# EDIT EMPLOYEE
# ─────────────────────────────────────────────
def edit_employee(biz, employees, sym):
    if not employees:
        print("No employees to edit.")
        return
    print("\nEmployees:")
    for i, e in enumerate(employees, 1):
        print(f"  {i}. {e['name']} ({e['role']})")
    try:
        idx = int(input("Select employee: ")) - 1
        if not (0 <= idx < len(employees)):
            print("Invalid selection.")
            return
        emp = employees[idx]
    except ValueError:
        print("Invalid input.")
        return
    data = _load_employees()
    while True:
        print(f"\n  Editing: {emp['name']}")
        print(f"  1: Name  2: Role  3: Salary  4: Notes  5: Done")
        try:
            choice = int(input("  Option: "))
            if choice == 1:
                new_name = input("  New name: ").strip().title()
                if new_name:
                    emp["name"] = new_name
                    _save_employees(data)
                    print(f"  Name updated to {new_name}.")
            elif choice == 2:
                new_role = input("  New role/position: ").strip().title()
                if new_role:
                    emp["role"] = new_role
                    _save_employees(data)
                    print(f"  Role updated to {new_role}.")
            elif choice == 3:
                try:
                    new_salary = float(input(f"  New monthly salary ({sym}): "))
                    emp["salary"] = new_salary
                    _save_employees(data)
                    print(f"  Salary updated to {sym}{new_salary:.2f}/month.")
                except ValueError:
                    print("  Invalid salary.")
            elif choice == 4:
                note = input("  Notes: ").strip()
                emp["notes"] = note
                _save_employees(data)
                print("  Notes saved.")
            elif choice == 5:
                break
            else:
                print("  Enter 1-5.")
        except ValueError:
            print("  Invalid input.")

# ─────────────────────────────────────────────
# MAIN EMPLOYEE MENU
# ─────────────────────────────────────────────
def employee_menu(biz):
    while True:
        sym = _get_sym(biz)
        data = _load_employees()
        employees = data.get(biz, [])
        print(f"\n{'='*40}")
        print(f"  EMPLOYEE MANAGEMENT: {biz.upper()}")
        print(f"{'='*40}")
        print(f"  Staff on record: {len(employees)}")
        print("1: Add Employee")
        print("2: View Employees")
        print("3: Edit Employee")
        print("4: Remove Employee")
        print("5: Employee Profile")
        print("6: Payroll Summary")
        print("7: Salary Advances")
        print("8: Attendance")
        print("9: Leave Management")
        print("10: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                name = input("Employee Name: ").strip().title()
                if not name:
                    print("Name cannot be empty.")
                    continue
                role = input("Role/Position: ").strip().title()
                try:
                    salary = float(input(f"Monthly Salary ({sym}): "))
                except ValueError:
                    print("Invalid salary.")
                    continue
                notes = input("Notes (press Enter to skip): ").strip()
                if biz not in data:
                    data[biz] = []
                data[biz].append({
                    "name": name,
                    "role": role,
                    "salary": salary,
                    "notes": notes,
                    "username": "",
                    "password": "",
                    "permissions": []
                })
                _save_employees(data)
                print(f"  {name} added to {biz}.")
                print(f"  (Set their login & permissions via Manager Settings in Business/Staff Login.)")

            elif choice == 2:
                if not employees:
                    print(f"  No employees recorded for {biz}.")
                else:
                    advances = _load_advances()
                    print(f"\n--- EMPLOYEES: {biz.upper()} ---")
                    print(f"  {'#':<4} {'Name':<20} {'Role':<15} {'Salary':>10}  {'Advance':>9}  {'Net Pay':>9}  {'Login':<12} {'Permissions'}")
                    print(f"  {'-'*95}")
                    for i, e in enumerate(employees, 1):
                        outstanding = _get_outstanding(biz, e["name"], advances)
                        net = e["salary"] - outstanding
                        adv_str = f"{sym}{outstanding:.2f}" if outstanding > 0 else "---"
                        login_str = f"@{e['username']}" if e.get("username") else "(none)"
                        perms = e.get("permissions", [])
                        perm_str = ", ".join(p.upper() for p in perms) if perms else "—"
                        if len(perm_str) > 22:
                            perm_str = perm_str[:19] + "..."
                        print(f"  {i:<4} {e['name']:<20} {e['role']:<15} {sym}{e['salary']:>9.2f}  {adv_str:>9}  {sym}{net:>8.2f}  {login_str:<12} {perm_str}")

            elif choice == 3:
                edit_employee(biz, employees, sym)

            elif choice == 4:
                if not employees:
                    print("No employees to remove.")
                    continue
                for i, e in enumerate(employees, 1):
                    print(f"  {i}. {e['name']} ({e['role']})")
                try:
                    idx = int(input("Select employee to remove: ")) - 1
                    if 0 <= idx < len(employees):
                        confirm = input(f"  Remove {employees[idx]['name']}? (Y/N): ").strip().upper()
                        if confirm == "Y":
                            removed = data[biz].pop(idx)
                            _save_employees(data)
                            print(f"  {removed['name']} removed.")
                    else:
                        print("Invalid selection.")
                except ValueError:
                    print("Enter a number.")

            elif choice == 5:
                if not employees:
                    print("No employees on record.")
                    continue
                print("\nEmployees:")
                for i, e in enumerate(employees, 1):
                    print(f"  {i}. {e['name']}")
                try:
                    idx = int(input("Select employee: ")) - 1
                    if 0 <= idx < len(employees):
                        employee_profile(biz, employees[idx], sym)
                    else:
                        print("Invalid selection.")
                except ValueError:
                    print("Invalid input.")

            elif choice == 6:
                advances = _load_advances()
                if not employees:
                    print(f"No employees for {biz}.")
                else:
                    total_salary = sum(e["salary"] for e in employees)
                    total_advances = sum(_get_outstanding(biz, e["name"], advances) for e in employees)
                    print(f"\n--- PAYROLL SUMMARY: {biz.upper()} ---")
                    for e in employees:
                        outstanding = _get_outstanding(biz, e["name"], advances)
                        net = e["salary"] - outstanding
                        adv_note = f" | Advance: {sym}{outstanding:.2f} | Net: {sym}{net:.2f}" if outstanding > 0 else ""
                        print(f"  {e['name']} ({e['role']}): {sym}{e['salary']:.2f}/month{adv_note}")
                    print(f"  {'─'*48}")
                    print(f"  Total Monthly Payroll:     {sym}{total_salary:.2f}")
                    if total_advances > 0:
                        print(f"  Outstanding Advances:      {sym}{total_advances:.2f}")
                        print(f"  Net Payroll This Month:    {sym}{total_salary - total_advances:.2f}")
                    print(f"  Annual Payroll:            {sym}{total_salary * 12:.2f}")

            elif choice == 7:
                salary_advance_menu(biz, employees, sym)

            elif choice == 8:
                attendance_menu(biz)

            elif choice == 9:
                leave_menu(biz, employees, sym)

            elif choice == 10:
                break
            else:
                print("Enter 1-10.")
        except ValueError:
            print("Invalid input.")
