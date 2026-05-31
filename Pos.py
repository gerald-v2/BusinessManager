import json
import crm
import business_manager as bm
import business_finance as bf
from datetime import datetime

SALESFILE = "pos_sales.json"

def load_sales():
    try:
        with open(SALESFILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_sales(data):
    with open(SALESFILE, "w") as f:
        json.dump(data, f, indent=4)

def get_sym(name):
    curr = bm.get_business_currency(name)
    return bm.get_currency_symbol(curr)

def product_lookup(name, plu):
    businesses = bm.load_business()
    for p_name, details in businesses.get(name, {}).get("products", {}).items():
        for v in details.get("variants", []):
            if str(v.get("PLU", "")).strip() == str(plu).strip():
                price_raw = str(details.get("Price", "0")).replace("$", "").strip()
                try:
                    price = float(price_raw)
                except ValueError:
                    price = 0.0
                return {"product": p_name, "variant": v["name"], "plu": plu, "unit_price": price, "stock": v.get("units", 0)}
    return None

def validate_plu(name, plu):
    return product_lookup(name, plu) is not None

def record_sale(name, product_name, variant_name, quantity):
    businesses = bm.load_business()
    bm.businesses = businesses
    product = businesses.get(name, {}).get("products", {}).get(product_name, {})
    variants = product.get("variants", [])
    for v in variants:
        if v.get("name") == variant_name:
            if v["units"] >= quantity:
                v["units"] -= quantity
                v["sold"] = v.get("sold", 0) + quantity
                price_raw = str(product.get("Price", "0")).replace("$", "").strip()
                try:
                    product_sale = float(price_raw) * quantity
                except ValueError:
                    product_sale = 0
                bf.add_revenue(name, product_sale)
                bm.store_business()
                bm.export_to_csv(name)
                return True, product_sale
            else:
                return False, "Not enough stock."
    return False, "Variant not found."

def tax_calculation(subtotal, tax_rate):
    return round(subtotal * (tax_rate / 100), 2)

def discount(subtotal, discount_pct):
    return round(subtotal * (discount_pct / 100), 2)

def receipt(name, items, subtotal, disc_amt, tax_amt, total, payment, change=0.0,
            customer=None, points_earned=0, points_redeemed=0):
    sym = get_sym(name)
    now = datetime.now()
    print("\n" + "="*45)
    print(f"          {name.upper()}")
    print(f"  {now.strftime('%Y-%m-%d  %H:%M')}")
    if customer:
        print(f"  Customer: {customer['name']}")
    print("="*45)
    print(f"  {'Item':<26} {'Qty':>3}  {'Total':>8}")
    print(f"  {'-'*40}")
    for item in items:
        label = f"{item['product']} ({item['variant']})"
        print(f"  {label:<26} {item['qty']:>3}  {sym}{item['subtotal']:>7.2f}")
    print(f"  {'-'*40}")
    print(f"  {'Subtotal':<30} {sym}{subtotal:>7.2f}")
    if disc_amt > 0:
        print(f"  {'Discount':<30}-{sym}{disc_amt:>7.2f}")
    if tax_amt > 0:
        print(f"  {'Tax':<30} {sym}{tax_amt:>7.2f}")
    print(f"  {'TOTAL':<30} {sym}{total:>7.2f}")
    print(f"  {'Payment':<30} {sym}{payment:>7.2f}")
    if change > 0:
        print(f"  {'Change':<30} {sym}{change:>7.2f}")
    if customer:
        print(f"  {'-'*40}")
        if points_redeemed > 0:
            print(f"  Points Used:    -{points_redeemed} pts")
        if points_earned > 0:
            usd_equiv = crm._to_usd_equivalent(name, total)
            curr = crm._get_biz_currency(name)
            if curr != "USD":
                print(f"  Points Earned:  +{points_earned} pts  ({sym}{total:.2f} {curr} ≈ ${usd_equiv:.2f} USD)")
            else:
                print(f"  Points Earned:  +{points_earned} pts")
        new_bal = customer.get("points", 0)
        print(f"  Points Balance: {new_bal} pts")
        next_t = crm.get_next_tier(name, customer)
        if next_t:
            needed = next_t["points"] - new_bal
            print(f"  ({needed} pts to {next_t['label']} — {next_t['discount_pct']}% off)")
    print("="*45)
    print("       Thank you for your purchase!")
    print("="*45)

def add_to_cart(name, cart):
    sym = get_sym(name)
    businesses = bm.load_business()
    bm.businesses = businesses
    print("\n  Add by: 1) PLU code  2) Browse products")
    try:
        method = int(input("  Method: "))
    except ValueError:
        print("  Invalid input.")
        return

    item = None
    if method == 1:
        plu = input("  Enter PLU code: ").strip()
        item = product_lookup(name, plu)
        if not item:
            print(f"  PLU '{plu}' not found.")
            return
    elif method == 2:
        products = businesses.get(name, {}).get("products", {})
        if not products:
            print("  No products available.")
            return
        prod_list = list(products.keys())
        for i, p in enumerate(prod_list, 1):
            print(f"  {i}. {p}")
        try:
            p_idx = int(input("  Select product: ")) - 1
            if not (0 <= p_idx < len(prod_list)):
                print("  Invalid selection.")
                return
            p_name = prod_list[p_idx]
        except ValueError:
            print("  Invalid input.")
            return
        variants = products[p_name].get("variants", [])
        if not variants:
            print("  No variants for this product.")
            return
        for i, v in enumerate(variants, 1):
            print(f"  {i}. [{v.get('PLU','N/A')}] {v['name']} — {v['units']} in stock")
        try:
            v_idx = int(input("  Select variant: ")) - 1
            if not (0 <= v_idx < len(variants)):
                print("  Invalid selection.")
                return
            v = variants[v_idx]
        except ValueError:
            print("  Invalid input.")
            return
        price_raw = str(products[p_name].get("Price", "0")).replace("$", "").strip()
        try:
            price = float(price_raw)
        except ValueError:
            price = 0.0
        item = {"product": p_name, "variant": v["name"], "plu": v.get("PLU", "N/A"), "unit_price": price, "stock": v.get("units", 0)}
    else:
        print("  Invalid method.")
        return

    try:
        qty = int(input(f"  Quantity (max {item['stock']} in stock): "))
    except ValueError:
        print("  Invalid quantity.")
        return
    if qty <= 0:
        print("  Quantity must be at least 1.")
        return
    if qty > item["stock"]:
        print(f"  Only {item['stock']} units available.")
        return

    key = item["plu"]
    if key in cart:
        new_qty = cart[key]["qty"] + qty
        if new_qty > item["stock"]:
            print(f"  Cannot add more — only {item['stock']} units total in stock.")
            return
        cart[key]["qty"] = new_qty
        cart[key]["subtotal"] = round(cart[key]["unit_price"] * new_qty, 2)
        print(f"  Updated {item['product']} ({item['variant']}) quantity to {new_qty}.")
    else:
        cart[key] = {
            "product": item["product"],
            "variant": item["variant"],
            "plu": key,
            "qty": qty,
            "unit_price": item["unit_price"],
            "subtotal": round(item["unit_price"] * qty, 2)
        }
        print(f"  Added: {item['product']} ({item['variant']}) x{qty} — {sym}{cart[key]['subtotal']:.2f}")

def remove_from_cart(cart, sym):
    if not cart:
        print("  Cart is empty.")
        return
    items = list(cart.values())
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item['product']} ({item['variant']}) x{item['qty']} — {sym}{item['subtotal']:.2f}")
    try:
        sel = int(input("  Select item to remove: ")) - 1
        if 0 <= sel < len(items):
            plu = items[sel]["plu"]
            removed = cart.pop(plu)
            print(f"  Removed: {removed['product']} ({removed['variant']})")
        else:
            print("  Invalid selection.")
    except ValueError:
        print("  Invalid input.")

def show_cart(cart, sym):
    if not cart:
        print("  Cart is empty.")
        return 0.0
    print(f"\n  {'Item':<28} {'Qty':>4}  {'Unit':>8}  {'Total':>9}")
    print(f"  {'-'*54}")
    subtotal = 0.0
    for item in cart.values():
        label = f"{item['product']} ({item['variant']})"
        print(f"  {label:<28} {item['qty']:>4}  {sym}{item['unit_price']:>7.2f}  {sym}{item['subtotal']:>8.2f}")
        subtotal += item["subtotal"]
    print(f"  {'-'*54}")
    print(f"  {'Subtotal':<42} {sym}{subtotal:>8.2f}")
    return round(subtotal, 2)

# ─────────────────────── CRM INTEGRATION ──────────────────────

def link_customer_flow(biz):
    print("\n--- LINK CUSTOMER ---")
    query = input("  Search name or phone: ").strip()
    if not query:
        return None
    results = crm.find_customer(biz, query)
    if results:
        print(f"\n  Found {len(results)} match(es):")
        for i, c in enumerate(results, 1):
            pts = c.get("points", 0)
            tier = crm.get_eligible_discount(biz, c)
            tier_str = f" [{tier['label']}]" if tier else ""
            print(f"  {i}. {c['name']} | {c.get('phone') or 'N/A'} | {pts} pts{tier_str}")
        if len(results) == 1:
            customer = results[0]
        else:
            try:
                sel = int(input("  Select (0 to cancel): ")) - 1
                if sel < 0 or sel >= len(results):
                    return None
                customer = results[sel]
            except ValueError:
                return None
        print(f"  Linked: {customer['name']} ({customer.get('points', 0)} pts)")
        return customer
    else:
        print(f"  No customer found for '{query}'.")
        reg = input("  Register as new customer? (Y/N): ").strip().upper()
        if reg == "Y":
            return crm.register_quick(biz)
        return None

def repeat_order_flow(biz, customer, cart, sym):
    purchases = customer.get("purchases", [])
    if not purchases:
        print(f"  {customer['name']} has no previous purchases on record.")
        return
    recent = purchases[-5:]
    print(f"\n--- PREVIOUS ORDERS: {customer['name'].upper()} ---")
    for i, p in enumerate(recent, 1):
        items_str = ", ".join(
            f"{it['product']} ({it['variant']}) x{it['qty']}" for it in p.get("items", [])
        )
        if len(items_str) > 55:
            items_str = items_str[:52] + "..."
        print(f"  {i}. {p.get('date','N/A')} — {sym}{p.get('total',0):.2f}")
        print(f"     {items_str}")
    print("  0. Cancel")
    try:
        sel = int(input("  Load order #: "))
        if sel == 0 or not (1 <= sel <= len(recent)):
            return
        order = recent[sel - 1]
    except ValueError:
        return

    businesses = bm.load_business()
    added = 0
    for item in order.get("items", []):
        p_data = businesses.get(biz, {}).get("products", {}).get(item["product"])
        if not p_data:
            print(f"  Skipped: {item['product']} — product no longer exists.")
            continue
        variant_found = next((v for v in p_data.get("variants", []) if v["name"] == item["variant"]), None)
        if not variant_found:
            print(f"  Skipped: {item['product']} ({item['variant']}) — variant not found.")
            continue
        stock = variant_found.get("units", 0)
        if stock <= 0:
            print(f"  Skipped: {item['product']} ({item['variant']}) — out of stock.")
            continue
        qty = min(item["qty"], stock)
        if qty < item["qty"]:
            print(f"  Note: {item['product']} ({item['variant']}) reduced to {qty} (stock limit).")
        price_raw = str(p_data.get("Price", "0")).replace("$", "").strip()
        try:
            price = float(price_raw)
        except ValueError:
            price = 0.0
        plu = str(variant_found.get("PLU", "N/A"))
        if plu in cart:
            new_qty = min(cart[plu]["qty"] + qty, stock)
            cart[plu]["qty"] = new_qty
            cart[plu]["subtotal"] = round(cart[plu]["unit_price"] * new_qty, 2)
        else:
            cart[plu] = {
                "product": item["product"],
                "variant": item["variant"],
                "plu": plu,
                "qty": qty,
                "unit_price": price,
                "subtotal": round(price * qty, 2)
            }
        print(f"  Added: {item['product']} ({item['variant']}) x{qty} — {sym}{round(price * qty, 2):.2f}")
        added += 1
    if added == 0:
        print("  No items could be loaded from that order.")
    else:
        print(f"  {added} item(s) loaded into cart.")

# ─────────────────────── CHECKOUT ─────────────────────────────

def checkout_cart(name, cart, active_customer=None):
    if not cart:
        print("  Cart is empty. Add items first.")
        return
    sym = get_sym(name)
    subtotal = show_cart(cart, sym)

    disc_pct = 0.0
    points_redeemed = 0
    tier_used = None

    if active_customer and crm.points_enabled(name):
        tier = crm.get_eligible_discount(name, active_customer)
        if tier:
            pts = active_customer.get("points", 0)
            print(f"\n  {active_customer['name']} has {pts} pts — {tier['label']} tier")
            print(f"  Eligible for {tier['discount_pct']}% discount (costs {tier['points']} pts to redeem)")
            use_pts = input("  Redeem points for discount? (Y/N): ").strip().upper()
            if use_pts == "Y":
                disc_pct = tier["discount_pct"]
                points_redeemed = tier["points"]
                tier_used = tier
                print(f"  {tier['discount_pct']}% discount applied.")
        else:
            pts = active_customer.get("points", 0)
            next_t = crm.get_next_tier(name, active_customer)
            if next_t:
                needed = next_t["points"] - pts
                print(f"\n  {active_customer['name']}: {pts} pts — {needed} more to reach {next_t['label']} ({next_t['discount_pct']}% off)")

    if disc_pct == 0.0:
        apply_disc = input("\n  Apply manual discount? (Y/N): ").strip().upper()
        if apply_disc == "Y":
            try:
                disc_pct = float(input("  Discount %: "))
            except ValueError:
                print("  Invalid — no discount applied.")
                disc_pct = 0.0

    tax_rate = 0.0
    apply_tax = input("  Apply tax? (Y/N): ").strip().upper()
    if apply_tax == "Y":
        try:
            tax_rate = float(input("  Tax %: "))
        except ValueError:
            print("  Invalid — no tax applied.")
            tax_rate = 0.0

    disc_amt = discount(subtotal, disc_pct)
    tax_amt = tax_calculation(subtotal - disc_amt, tax_rate)
    total = round(subtotal - disc_amt + tax_amt, 2)

    print(f"\n  Subtotal:  {sym}{subtotal:.2f}")
    if disc_amt > 0:
        label = f"({tier_used['label']} pts redemption)" if tier_used else f"({disc_pct}%)"
        print(f"  Discount:  -{sym}{disc_amt:.2f} {label}")
    if tax_amt > 0:
        print(f"  Tax:        {sym}{tax_amt:.2f} ({tax_rate}%)")
    print(f"  TOTAL:     {sym}{total:.2f}")

    print("\n  Payment Method:")
    print("  1: Cash  2: Card  3: Cancel")
    try:
        pay_choice = int(input("  Option: "))
    except ValueError:
        print("  Invalid input.")
        return

    if pay_choice == 3:
        print("  Checkout cancelled.")
        return
    elif pay_choice == 1:
        payment_method = "Cash"
        try:
            tendered = float(input(f"  Amount tendered ({sym}): "))
        except ValueError:
            print("  Invalid amount.")
            return
        if tendered < total:
            print(f"  Insufficient payment. Total is {sym}{total:.2f}")
            return
        change = round(tendered - total, 2)
    elif pay_choice == 2:
        payment_method = "Card"
        tendered = total
        change = 0.0
    else:
        print("  Invalid option.")
        return

    items_list = list(cart.values())
    for item in items_list:
        ok, result = record_sale(name, item["product"], item["variant"], item["qty"])
        if not ok:
            print(f"  Warning — {item['product']} ({item['variant']}): {result}")

    points_earned = 0
    if active_customer:
        if points_redeemed > 0:
            crm.deduct_points(name, active_customer["name"], points_redeemed)
        points_earned = crm.award_points(name, active_customer["name"], total)
        crm.log_purchase_to_customer(name, active_customer["name"], items_list, total, points_earned)
        active_customer["points"] = crm.get_customer_points(name, active_customer["name"])

    now = datetime.now()
    sales_data = load_sales()
    if name not in sales_data:
        sales_data[name] = []
    sales_data[name].append({
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "items": items_list,
        "subtotal": subtotal,
        "discount_pct": disc_pct,
        "discount_amt": disc_amt,
        "tax_pct": tax_rate,
        "tax_amt": tax_amt,
        "total": total,
        "payment": payment_method,
        "customer": active_customer["name"] if active_customer else None
    })
    save_sales(sales_data)

    receipt(name, items_list, subtotal, disc_amt, tax_amt, total, tendered, change,
            customer=active_customer, points_earned=points_earned, points_redeemed=points_redeemed)
    cart.clear()

def void_cart(cart):
    if not cart:
        print("  Cart is already empty.")
        return
    confirm = input("  Void entire cart? All items will be removed. (Y/N): ").strip().upper()
    if confirm == "Y":
        cart.clear()
        print("  Cart voided.")

def view_sales(name):
    sym = get_sym(name)
    sales_data = load_sales()
    records = sales_data.get(name, [])
    if not records:
        print(f"\n  No sales recorded for {name}.")
        return
    print(f"\n--- SALES HISTORY: {name.upper()} ---")
    print(f"  {'#':<4} {'Date':<12} {'Time':<7} {'Customer':<18} {'Items':<6} {'Total':>10} {'Payment'}")
    print(f"  {'-'*66}")
    for i, sale in enumerate(records, 1):
        n_items = sum(item["qty"] for item in sale["items"])
        cust = sale.get("customer") or "—"
        if len(cust) > 17:
            cust = cust[:14] + "..."
        print(f"  {i:<4} {sale['date']:<12} {sale['time']:<7} {cust:<18} {n_items:<6} {sym}{sale['total']:>9.2f} {sale['payment']}")
    grand_total = sum(s["total"] for s in records)
    print(f"  {'-'*66}")
    print(f"  Total transactions: {len(records)}  |  Grand Total: {sym}{grand_total:.2f}")

    see_detail = input("\n  View a specific transaction? (enter # or N): ").strip()
    if see_detail.upper() == "N" or not see_detail:
        return
    try:
        idx = int(see_detail) - 1
        if 0 <= idx < len(records):
            s = records[idx]
            receipt(name, s["items"], s["subtotal"], s["discount_amt"], s["tax_amt"], s["total"], s["total"])
        else:
            print("  Invalid number.")
    except ValueError:
        pass

def refund_sale(name):
    sym = get_sym(name)
    sales_data = load_sales()
    records = sales_data.get(name, [])
    if not records:
        print(f"  No sales to refund for {name}.")
        return
    print(f"\n--- REFUND — {name.upper()} ---")
    recent = records[-10:]
    for i, sale in enumerate(recent, 1):
        n_items = sum(item["qty"] for item in sale["items"])
        cust = sale.get("customer") or "—"
        print(f"  {i}. {sale['date']} {sale['time']} | {cust} | {n_items} items | {sym}{sale['total']:.2f} | {sale['payment']}")
    try:
        sel = int(input("  Select transaction to refund: ")) - 1
        if not (0 <= sel < len(recent)):
            print("  Invalid selection.")
            return
        sale = recent[sel]
    except ValueError:
        print("  Invalid input.")
        return

    print(f"\n  Refunding {sym}{sale['total']:.2f} from {sale['date']} {sale['time']}")
    print("  Items in this transaction:")
    for item in sale["items"]:
        print(f"    {item['product']} ({item['variant']}) x{item['qty']}")
    confirm = input("  Confirm full refund? (Y/N): ").strip().upper()
    if confirm != "Y":
        print("  Refund cancelled.")
        return

    businesses = bm.load_business()
    bm.businesses = businesses
    for item in sale["items"]:
        p = businesses.get(name, {}).get("products", {}).get(item["product"])
        if p:
            for v in p.get("variants", []):
                if v["name"] == item["variant"]:
                    v["units"] += item["qty"]
                    v["sold"] = max(0, v.get("sold", 0) - item["qty"])
                    break
    bm.store_business()
    bm.export_to_csv(name)

    bf_data = bf.load_business_finance()
    if name in bf_data:
        bf_data[name]["Revenue"] = max(0, (bf_data[name].get("Revenue") or 0) - sale["total"])
        with open(bf.FINANCEFILE, "w") as f:
            json.dump(bf_data, f, indent=4)
        bf.business_finance[name] = bf_data[name]

    orig_idx = len(records) - len(recent) + sel
    sales_data[name].pop(orig_idx)
    save_sales(sales_data)
    print(f"  Refund of {sym}{sale['total']:.2f} processed. Stock restored.")

# ─────────────────────── MENU ─────────────────────────────────

def pos_menu(name):
    businesses = bm.load_business()
    bm.businesses = businesses
    sym = get_sym(name)
    cart = {}
    active_customer = None

    while True:
        print(f"\n--- POS SYSTEM: {name.upper()} ---")
        if active_customer:
            if crm.points_enabled(name):
                pts = active_customer.get("points", 0)
                tier = crm.get_eligible_discount(name, active_customer)
                tier_str = f" [{tier['label']}]" if tier else ""
                print(f"  Customer: {active_customer['name']} ({pts} pts{tier_str})")
            else:
                print(f"  Customer: {active_customer['name']}")
        else:
            print(f"  Customer: (none linked)")
        cart_count = sum(item["qty"] for item in cart.values())
        cart_total = sum(item["subtotal"] for item in cart.values())
        if cart_count > 0:
            print(f"  Cart: {cart_count} item(s) | {sym}{cart_total:.2f}")
        print("1: Link / Change Customer")
        print("2: Add Item to Cart")
        print("3: View / Edit Cart")
        print("4: Checkout")
        print("5: View Sales History")
        print("6: Refund")
        print("7: Void Cart")
        print("8: Exit POS")

        try:
            option = int(input("Option: "))
            if option == 1:
                linked = link_customer_flow(name)
                if linked:
                    fresh = crm.find_customer(name, linked["name"])
                    active_customer = fresh[0] if fresh else linked
                    if active_customer.get("purchases"):
                        repeat = input(f"  Load a previous order for {active_customer['name']}? (Y/N): ").strip().upper()
                        if repeat == "Y":
                            repeat_order_flow(name, active_customer, cart, sym)
            elif option == 2:
                add_to_cart(name, cart)
            elif option == 3:
                if not cart:
                    print("  Cart is empty.")
                else:
                    show_cart(cart, sym)
                    remove = input("  Remove an item? (Y/N): ").strip().upper()
                    if remove == "Y":
                        remove_from_cart(cart, sym)
            elif option == 4:
                checkout_cart(name, cart, active_customer)
                if not cart:
                    active_customer = None
            elif option == 5:
                view_sales(name)
            elif option == 6:
                refund_sale(name)
            elif option == 7:
                void_cart(cart)
            elif option == 8:
                if cart:
                    confirm = input("  Cart has items. Exit anyway? (Y/N): ").strip().upper()
                    if confirm != "Y":
                        continue
                print("  Exiting POS.")
                break
            else:
                print("  Enter 1-8.")
        except ValueError:
            print("  Invalid input.")
