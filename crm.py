import json
from datetime import datetime

CRMFILE = "crm_customers.json"

# ─────────────────────── RAW DATA HELPERS ─────────────────────

def _load_raw():
    try:
        with open(CRMFILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_raw(data):
    with open(CRMFILE, "w") as f:
        json.dump(data, f, indent=4)

def load_customers():
    raw = _load_raw()
    return {k: v for k, v in raw.items() if k != "_config"}

def save_customers(data):
    raw = _load_raw()
    for k, v in data.items():
        if k != "_config":
            raw[k] = v
    _save_raw(raw)

# ─────────────────────── POINTS CONFIG ────────────────────────

def default_config():
    return {
        "points_enabled": True,
        "points_per_dollar": 1,
        "tiers": [
            {"points": 100, "discount_pct": 5,  "label": "Silver"},
            {"points": 250, "discount_pct": 10, "label": "Gold"},
            {"points": 500, "discount_pct": 15, "label": "Platinum"}
        ]
    }

def get_biz_config(biz):
    raw = _load_raw()
    cfg = raw.get("_config", {}).get(biz)
    return cfg if cfg is not None else default_config()

def save_biz_config(biz, cfg):
    raw = _load_raw()
    if "_config" not in raw:
        raw["_config"] = {}
    raw["_config"][biz] = cfg
    _save_raw(raw)

# ─────────────────────── CURRENCY HELPER ─────────────────────

def _to_usd_equivalent(biz, amount):
    """Convert a local-currency amount to its USD equivalent using saved rates.
    Falls back to the raw amount if no matching rate exists."""
    try:
        import business_manager as bm
        import business_finance as bf
        curr = bm.get_business_currency(biz)
        if curr.upper() == "USD":
            return amount
        rates = bf.load_exchange_rates()
        key_fwd = f"{curr.upper()}_TO_USD"
        key_rev = f"USD_TO_{curr.upper()}"
        if key_fwd in rates:
            return amount * rates[key_fwd]
        elif key_rev in rates:
            return amount / rates[key_rev]
        return amount
    except Exception:
        return amount

def _get_biz_currency(biz):
    try:
        import business_manager as bm
        return bm.get_business_currency(biz).upper()
    except Exception:
        return "USD"

def _get_biz_sym(biz):
    try:
        import business_manager as bm
        return bm.get_currency_symbol(bm.get_business_currency(biz))
    except Exception:
        return "$"

# ─────────────────────── POINTS HELPERS ───────────────────────

def points_enabled(biz):
    return get_biz_config(biz).get("points_enabled", True)

def get_eligible_discount(biz, customer):
    if not points_enabled(biz):
        return None
    pts = customer.get("points", 0)
    cfg = get_biz_config(biz)
    best = None
    for tier in sorted(cfg.get("tiers", []), key=lambda t: t["points"], reverse=True):
        if pts >= tier["points"]:
            best = tier
            break
    return best

def get_next_tier(biz, customer):
    pts = customer.get("points", 0)
    cfg = get_biz_config(biz)
    for tier in sorted(cfg.get("tiers", []), key=lambda t: t["points"]):
        if pts < tier["points"]:
            return tier
    return None

def award_points(biz, customer_name, amount_spent):
    """Award points based on USD-equivalent of the spend, regardless of the business currency."""
    if not points_enabled(biz):
        return 0
    cfg = get_biz_config(biz)
    usd_equiv = _to_usd_equivalent(biz, amount_spent)
    earned = int(usd_equiv * cfg.get("points_per_dollar", 1))
    if earned <= 0:
        return 0
    raw = _load_raw()
    for c in raw.get(biz, []):
        if c["name"] == customer_name:
            c["points"] = c.get("points", 0) + earned
            _save_raw(raw)
            return earned
    return 0

def deduct_points(biz, customer_name, cost):
    raw = _load_raw()
    for c in raw.get(biz, []):
        if c["name"] == customer_name:
            if c.get("points", 0) >= cost:
                c["points"] -= cost
                _save_raw(raw)
                return True
            return False
    return False

def get_customer_points(biz, customer_name):
    raw = _load_raw()
    for c in raw.get(biz, []):
        if c["name"] == customer_name:
            return c.get("points", 0)
    return 0

# ─────────────────────── CUSTOMER CRUD ────────────────────────

def add_customer(biz):
    raw = _load_raw()
    if biz not in raw:
        raw[biz] = []
    print("\n--- ADD CUSTOMER ---")
    name = input("Customer Name: ").strip().title()
    if not name:
        print("Name cannot be empty.")
        return
    if any(c["name"] == name for c in raw[biz]):
        print(f"  Customer '{name}' already exists for {biz}.")
        return
    phone = input("Phone (press Enter to skip): ").strip()
    email = input("Email (press Enter to skip): ").strip()
    notes = input("Notes (press Enter to skip): ").strip()
    raw[biz].append({
        "name": name,
        "phone": phone,
        "email": email,
        "notes": notes,
        "joined": datetime.now().strftime("%Y-%m-%d"),
        "points": 0,
        "purchases": []
    })
    _save_raw(raw)
    print(f"  Customer '{name}' added to {biz}.")

def register_quick(biz):
    raw = _load_raw()
    if biz not in raw:
        raw[biz] = []
    print("\n--- REGISTER NEW CUSTOMER ---")
    name = input("  Name: ").strip().title()
    if not name:
        print("  Name required.")
        return None
    existing = next((c for c in raw[biz] if c["name"] == name), None)
    if existing:
        print(f"  '{name}' already registered — linking existing record.")
        return existing
    phone = input("  Phone: ").strip()
    new_c = {
        "name": name,
        "phone": phone,
        "email": "",
        "notes": "",
        "joined": datetime.now().strftime("%Y-%m-%d"),
        "points": 0,
        "purchases": []
    }
    raw[biz].append(new_c)
    _save_raw(raw)
    print(f"  Registered: {name}")
    return new_c

def find_customer(biz, query):
    raw = _load_raw()
    q = query.strip().lower()
    return [c for c in raw.get(biz, [])
            if q in c["name"].lower() or q in (c.get("phone") or "").lower()]

def view_customers(biz):
    raw = _load_raw()
    customers = raw.get(biz, [])
    if not customers:
        print(f"  No customers recorded for {biz}.")
        return
    try:
        import business_manager as bm
        sym = bm.get_currency_symbol(bm.get_business_currency(biz))
    except Exception:
        sym = "$"
    print(f"\n--- CUSTOMERS: {biz.upper()} ---")
    print(f"  {'#':<4} {'Name':<22} {'Phone':<15} {'Points':<8} {'Purchases':<10} {'Joined'}")
    print(f"  {'-'*72}")
    for i, c in enumerate(customers, 1):
        phone = c.get("phone") or "N/A"
        pts = c.get("points", 0)
        n_p = len(c.get("purchases", []))
        print(f"  {i:<4} {c['name']:<22} {phone:<15} {pts:<8} {n_p:<10} {c.get('joined','N/A')}")
    print(f"  Total customers: {len(customers)}")

def search_customer(biz):
    raw = _load_raw()
    customers = raw.get(biz, [])
    if not customers:
        print(f"  No customers for {biz}.")
        return None
    query = input("Search name or phone: ").strip()
    if not query:
        return None
    results = find_customer(biz, query)
    if not results:
        print("  No matching customers found.")
        return None
    print(f"\n  Found {len(results)} result(s):")
    for i, c in enumerate(results, 1):
        pts = c.get("points", 0)
        tier = get_eligible_discount(biz, c)
        tier_str = f" [{tier['label']}]" if tier else ""
        print(f"  {i}. {c['name']} | {c.get('phone') or 'N/A'} | {pts} pts{tier_str}")
    if len(results) == 1:
        return results[0]
    try:
        sel = int(input("  Select customer: ")) - 1
        if 0 <= sel < len(results):
            return results[sel]
    except ValueError:
        pass
    return None

def view_customer_profile(biz, customer):
    try:
        import business_manager as bm
        sym = bm.get_currency_symbol(bm.get_business_currency(biz))
    except Exception:
        sym = "$"
    purchases = customer.get("purchases", [])
    total_spent = sum(p.get("total", 0) for p in purchases)
    pts = customer.get("points", 0)
    tier = get_eligible_discount(biz, customer)
    next_t = get_next_tier(biz, customer)
    tier_label = f"{tier['label']} — eligible for {tier['discount_pct']}% discount" if tier else "No tier yet"
    print(f"\n--- CUSTOMER PROFILE: {customer['name'].upper()} ---")
    print(f"  Phone:    {customer.get('phone') or 'N/A'}")
    print(f"  Email:    {customer.get('email') or 'N/A'}")
    print(f"  Notes:    {customer.get('notes') or 'N/A'}")
    print(f"  Joined:   {customer.get('joined','N/A')}")
    print(f"  Points:   {pts} pts  ({tier_label})")
    if next_t:
        needed = next_t["points"] - pts
        print(f"  Progress: {needed} pts to reach {next_t['label']} ({next_t['discount_pct']}% off)")
    print(f"  Purchases: {len(purchases)}  |  Total Spent: {sym}{total_spent:.2f}")
    if purchases:
        print(f"\n  Purchase History:")
        print(f"  {'#':<4} {'Date':<12} {'Items':<30} {'Total':>8}  {'Pts'}")
        print(f"  {'-'*62}")
        for i, p in enumerate(purchases, 1):
            items_str = ", ".join(f"{it['product']} x{it['qty']}" for it in p.get("items", []))
            if len(items_str) > 29:
                items_str = items_str[:26] + "..."
            pts_note = f"+{p['points_earned']}" if p.get("points_earned") else "—"
            print(f"  {i:<4} {p.get('date','N/A'):<12} {items_str:<30} {sym}{p.get('total',0):>7.2f}  {pts_note}")

def log_purchase_to_customer(biz, customer_name, items, total, points_earned=0):
    raw = _load_raw()
    for c in raw.get(biz, []):
        if c["name"] == customer_name:
            c.setdefault("purchases", []).append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M"),
                "items": items,
                "total": total,
                "points_earned": points_earned
            })
            _save_raw(raw)
            return True
    return False

def edit_customer(biz):
    customer = search_customer(biz)
    if not customer:
        return
    raw = _load_raw()
    for c in raw.get(biz, []):
        if c["name"] == customer["name"]:
            print(f"\n  Editing: {c['name']}")
            print("  1: Name  2: Phone  3: Email  4: Notes  5: Cancel")
            try:
                choice = int(input("  Option: "))
                if choice == 1:
                    c["name"] = input("  New name: ").strip().title() or c["name"]
                elif choice == 2:
                    c["phone"] = input("  New phone: ").strip()
                elif choice == 3:
                    c["email"] = input("  New email: ").strip()
                elif choice == 4:
                    c["notes"] = input("  New notes: ").strip()
                elif choice == 5:
                    return
                _save_raw(raw)
                print("  Customer updated.")
            except ValueError:
                print("  Invalid input.")
            return

def remove_customer(biz):
    customer = search_customer(biz)
    if not customer:
        return
    confirm = input(f"  Delete '{customer['name']}'? (Y/N): ").strip().upper()
    if confirm == "Y":
        raw = _load_raw()
        raw[biz] = [c for c in raw.get(biz, []) if c["name"] != customer["name"]]
        _save_raw(raw)
        print(f"  '{customer['name']}' removed.")

# ─────────────────────── POINTS CONFIG MENU ───────────────────

def points_config_menu(biz):
    cfg = get_biz_config(biz)
    while True:
        curr = _get_biz_currency(biz)
        sym = _get_biz_sym(biz)
        rate_note = ""
        if curr != "USD":
            try:
                import business_finance as bf
                rates = bf.load_exchange_rates()
                key_fwd = f"{curr}_TO_USD"
                key_rev = f"USD_TO_{curr}"
                if key_fwd in rates:
                    local_per_dollar = round(1 / rates[key_fwd], 2)
                    rate_note = f"  (rate: {sym}{local_per_dollar} {curr} = $1 USD)"
                elif key_rev in rates:
                    local_per_dollar = round(rates[key_rev], 2)
                    rate_note = f"  (rate: {sym}{local_per_dollar} {curr} = $1 USD)"
                else:
                    rate_note = f"  (no {curr}→USD rate saved — points will use raw amount)"
            except Exception:
                rate_note = ""
        enabled = cfg.get("points_enabled", True)
        status = "ON" if enabled else "OFF"
        print(f"\n--- POINTS CONFIGURATION: {biz.upper()} ---")
        print(f"  Points System: {status}")
        print(f"  Currency:      {curr}")
        if enabled:
            print(f"  Earn rate:     {cfg['points_per_dollar']} pt(s) per $1 USD equivalent{rate_note}")
            print(f"\n  Discount Tiers:")
            tiers = cfg.get("tiers", [])
            if tiers:
                for i, t in enumerate(tiers, 1):
                    print(f"    {i}. {t['label']:<12} {t['points']} pts  →  {t['discount_pct']}% off")
            else:
                print("    No tiers configured.")
        print(f"\n  1: Turn points {'OFF' if enabled else 'ON'}")
        print("  2: Change earn rate")
        print("  3: Add tier")
        print("  4: Remove tier")
        print("  5: Reset to defaults")
        print("  6: Back")
        try:
            choice = int(input("  Option: "))
            if choice == 1:
                cfg["points_enabled"] = not enabled
                save_biz_config(biz, cfg)
                new_status = "ON" if cfg["points_enabled"] else "OFF"
                print(f"  Points system turned {new_status} for {biz}.")
            elif choice == 2:
                try:
                    val = float(input("  Points earned per $1 USD equivalent: "))
                    if val <= 0:
                        print("  Must be greater than 0.")
                        continue
                    cfg["points_per_dollar"] = val
                    save_biz_config(biz, cfg)
                    print(f"  Updated: {val} pt(s) per $1 USD equivalent.")
                except ValueError:
                    print("  Invalid input.")
            elif choice == 3:
                label = input("  Tier label (e.g. Silver): ").strip().title() or "Custom"
                try:
                    pts_req = int(input("  Points required to qualify: "))
                    disc = float(input("  Discount % to award: "))
                    if pts_req <= 0 or disc <= 0:
                        print("  Values must be greater than 0.")
                        continue
                    cfg["tiers"].append({"points": pts_req, "discount_pct": disc, "label": label})
                    cfg["tiers"].sort(key=lambda t: t["points"])
                    save_biz_config(biz, cfg)
                    print(f"  Tier '{label}' added.")
                except ValueError:
                    print("  Invalid input.")
            elif choice == 4:
                tiers = cfg.get("tiers", [])
                if not tiers:
                    print("  No tiers to remove.")
                    continue
                try:
                    idx = int(input("  Remove tier #: ")) - 1
                    if 0 <= idx < len(tiers):
                        removed = cfg["tiers"].pop(idx)
                        save_biz_config(biz, cfg)
                        print(f"  Tier '{removed['label']}' removed.")
                    else:
                        print("  Invalid selection.")
                except ValueError:
                    print("  Invalid input.")
            elif choice == 5:
                cfg = default_config()
                save_biz_config(biz, cfg)
                print("  Reset to defaults (Silver 100pts/5%, Gold 250pts/10%, Platinum 500pts/15%).")
            elif choice == 6:
                break
            else:
                print("  Enter 1-6.")
        except ValueError:
            print("  Invalid input.")

# ─────────────────────── ANALYTICS ────────────────────────────

def trending_products(biz):
    try:
        import business_manager as bm
        businesses = bm.load_business()
        sym = bm.get_currency_symbol(bm.get_business_currency(biz))
    except Exception:
        businesses = {}
        sym = "$"
    all_variants = []
    for p_name, details in businesses.get(biz, {}).get("products", {}).items():
        price_raw = str(details.get("Price", "0")).replace("$", "").strip()
        try:
            price = float(price_raw)
        except ValueError:
            price = 0.0
        for v in details.get("variants", []):
            sold = v.get("sold", 0)
            all_variants.append({
                "product": p_name,
                "variant": v.get("name", ""),
                "plu": v.get("PLU", "N/A"),
                "sold": sold,
                "revenue": round(sold * price, 2)
            })
    if not all_variants:
        print(f"  No product sales data for {biz}.")
        return
    all_variants.sort(key=lambda x: x["sold"], reverse=True)
    top = all_variants[:10]
    print(f"\n--- TRENDING PRODUCTS: {biz.upper()} ---")
    print(f"  {'Rank':<5} {'PLU':<8} {'Product / Variant':<28} {'Sold':>6} {'Revenue':>12}")
    print(f"  {'-'*63}")
    for i, item in enumerate(top, 1):
        label = f"{item['product']} ({item['variant']})"
        if len(label) > 27:
            label = label[:24] + "..."
        print(f"  {i:<5} {item['plu']:<8} {label:<28} {item['sold']:>6} {sym}{item['revenue']:>11.2f}")
    total_sold = sum(x["sold"] for x in all_variants)
    total_rev = sum(x["revenue"] for x in all_variants)
    print(f"  {'-'*63}")
    print(f"  Total Units Sold: {total_sold}  |  Total Revenue: {sym}{total_rev:.2f}")

def customer_stats(biz):
    raw = _load_raw()
    customers = raw.get(biz, [])
    if not customers:
        print(f"  No customer data for {biz}.")
        return
    try:
        import business_manager as bm
        sym = bm.get_currency_symbol(bm.get_business_currency(biz))
    except Exception:
        sym = "$"
    rows = []
    for c in customers:
        spent = sum(p.get("total", 0) for p in c.get("purchases", []))
        rows.append((c["name"], spent, len(c.get("purchases", [])), c.get("points", 0)))
    rows.sort(key=lambda x: x[1], reverse=True)
    print(f"\n--- CUSTOMER STATS: {biz.upper()} ---")
    print(f"  Total Customers: {len(customers)}")
    print(f"  {'Name':<22} {'Purchases':<12} {'Points':<8} {'Total Spent'}")
    print(f"  {'-'*56}")
    for name, spent, n_p, pts in rows:
        print(f"  {name:<22} {n_p:<12} {pts:<8} {sym}{spent:.2f}")
    grand = sum(x[1] for x in rows)
    print(f"  {'-'*56}")
    print(f"  Grand Total Spent by All Customers: {sym}{grand:.2f}")

# ─────────────────────── MENU ─────────────────────────────────

def crm_menu(biz):
    while True:
        print(f"\n--- CRM: {biz.upper()} ---")
        print("1: Add Customer")
        print("2: View All Customers")
        print("3: Search / View Profile")
        print("4: Edit Customer")
        print("5: Remove Customer")
        print("6: Points Configuration")
        print("7: Trending Products")
        print("8: Customer Stats")
        print("9: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                add_customer(biz)
            elif choice == 2:
                view_customers(biz)
            elif choice == 3:
                customer = search_customer(biz)
                if customer:
                    view_customer_profile(biz, customer)
            elif choice == 4:
                edit_customer(biz)
            elif choice == 5:
                remove_customer(biz)
            elif choice == 6:
                points_config_menu(biz)
            elif choice == 7:
                trending_products(biz)
            elif choice == 8:
                customer_stats(biz)
            elif choice == 9:
                break
            else:
                print("Enter 1-9.")
        except ValueError:
            print("Invalid input.")
