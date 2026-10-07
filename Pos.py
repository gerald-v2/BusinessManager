import json
import threading
import uuid
import crm
import biz_settings as bs
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
                price = bm.variant_price(details, v)
                cost = bm.variant_cost(details, v)
                return {"product": p_name, "variant": v["name"], "plu": str(plu).strip(),
                        "unit_price": price, "unit_cost": cost, "stock": v.get("units", 0)}
    return None

def validate_plu(name, plu):
    return product_lookup(name, plu) is not None

def record_sale(name, product_name, variant_name, quantity, add_revenue=True):
    businesses = bm.load_business()
    bm.businesses = businesses
    product = businesses.get(name, {}).get("products", {}).get(product_name, {})
    variants = product.get("variants", [])
    for v in variants:
        if v.get("name") == variant_name:
            if v["units"] >= quantity:
                v["units"] -= quantity
                v["sold"] = v.get("sold", 0) + quantity
                product_sale = bm.variant_price(product, v) * quantity
                if add_revenue:
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
        price = bm.variant_price(products[p_name], v)
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
        price = bm.variant_price(p_data, variant_found)
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


# GETTING SALES FROM TIME PERIOD
from datetime import datetime, timedelta


def get_sales_last_n_days(business_id, days):
    sales_data = load_sales()
    business_data = sales_data.get(business_id, [])
    cut_off_date = datetime.now() - timedelta(days=days)

    filtered_sales = []
    for sale in business_data:
        sale_date = sale.get("date")

        if not sale_date:
            continue
        try:
            sale_datetime = datetime.strptime(sale_date, "%Y-%m-%d")
        except ValueError:
            continue
        if sale_datetime >= cut_off_date:
            filtered_sales.append(sale)
    return filtered_sales


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


# ═════════════════════════════════════════════════════════════════════════════
#  WEB POS ENGINE  (used by the web checkout, offline sync and refunds)
#  One code path for every sale: prices, stock, discount, loyalty points, VAT,
#  revenue and the receipt are all worked out on the SERVER.
# ═════════════════════════════════════════════════════════════════════════════

_sale_lock = threading.Lock()
PAYMENT_METHODS = ("Cash", "Card", "Transfer", "Mobile")


def _safe_int(value, default=0):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _find_variant(products, plu=None, product=None, variant=None):
    """Return (product_name, product_dict, variant_dict) or None."""
    plu = str(plu or "").strip()
    if plu:
        for p_name, details in products.items():
            for v in details.get("variants", []):
                if str(v.get("PLU", "")).strip() == plu:
                    return p_name, details, v
    if product and variant:
        details = products.get(product)
        if details:
            for v in details.get("variants", []):
                if v.get("name") == variant:
                    return product, details, v
    return None


def next_receipt_no(biz_sales):
    top = 0
    for s in biz_sales:
        top = max(top, _safe_int(s.get("receipt_no"), 0))
    return max(top, len(biz_sales)) + 1


def format_receipt_no(n):
    return f"{_safe_int(n):06d}" if n else ""


def build_receipt(biz, sale, customer=None):
    """Everything the receipt printer / receipt page needs, in one dict."""
    cfg = bs.get(biz)
    biz_curr = bm.get_business_currency(biz)
    vat_pct = sale.get("tax_pct", 0) or 0
    disc_pct = sale.get("discount_pct", 0) or 0
    cust = None
    if sale.get("customer"):
        cust = {
            "name": sale["customer"],
            "points_earned": sale.get("points_earned", 0) or 0,
            "points_redeemed": sale.get("points_redeemed", 0) or 0,
            "balance": (customer or {}).get("points") if customer else None,
        }
    pay_curr = sale.get("pay_currency") or biz_curr
    return {
        "business": {
            "name": biz,
            "header": cfg.get("receipt_header", ""),
            "address": cfg.get("receipt_address", ""),
            "phone": cfg.get("receipt_phone", ""),
            "vat_number": cfg.get("vat_number", "") if vat_pct else "",
            "footer": cfg.get("receipt_footer", ""),
        },
        "sale_id": sale.get("sale_id", ""),
        "receipt_no": format_receipt_no(sale.get("receipt_no")),
        "date": sale.get("date", ""),
        "time": sale.get("time", ""),
        "cashier": sale.get("cashier", ""),
        "currency": biz_curr,
        "sym": get_sym(biz),
        "items": [
            {
                "product": i.get("product", ""),
                "variant": i.get("variant", ""),
                "qty": i.get("qty", 0),
                "unit_price": i.get("unit_price", 0),
                "subtotal": i.get("subtotal", 0),
            }
            for i in sale.get("items", [])
        ],
        "subtotal": sale.get("subtotal", 0),
        "discount_amt": sale.get("discount_amt", 0) or 0,
        "discount_pct": disc_pct,
        "discount_label": sale.get("discount_label", ""),
        "vat_pct": vat_pct,
        "vat_amt": sale.get("tax_amt", 0) or 0,
        "vat_inclusive": bool(sale.get("vat_inclusive")),
        "total": sale.get("total", 0),
        "payment": sale.get("payment", "Cash"),
        "payment_amount": sale.get("payment_amount", sale.get("total", 0)),
        "change": sale.get("change", 0) or 0,
        "pay_currency": pay_curr,
        "pay_sym": bm.get_currency_symbol(pay_curr),
        "tendered": sale.get("tendered", sale.get("payment_amount", 0)),
        "change_pay": sale.get("change_pay", sale.get("change", 0)),
        "alt_rate": sale.get("alt_rate", 1) or 1,
        "customer": cust,
        "refunded": bool(sale.get("refunded")),
        "paper_width": cfg.get("paper_width", 58),
        "cut": bool(cfg.get("printer_cut", True)),
    }


def process_sale(biz, data, actor=None):
    """Validate and record a sale.  Returns (ok, payload, http_status)."""
    with _sale_lock:
        return _process_sale_locked(biz, data or {}, actor or {})


def _process_sale_locked(biz, data, actor):
    sales_all = load_sales()
    biz_sales = sales_all.setdefault(biz, [])

    sale_id = str(data.get("sale_id") or uuid.uuid4())
    for s in biz_sales:
        if s.get("sale_id") == sale_id:
            return False, {"status": "already_processed", "error": "Sale already recorded.",
                           "sale": s, "receipt": build_receipt(biz, s)}, 409

    businesses = bm.load_business()
    bm.businesses = businesses
    if biz not in businesses:
        return False, {"status": "error", "error": "Business not found."}, 404
    products = businesses[biz].get("products", {})
    cfg = bs.get(biz)
    offline = bool(data.get("offline"))

    # ── 1. items (price & cost always come from the server) ──────────────────
    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return False, {"status": "error", "error": "The cart is empty."}, 400
    merged = {}
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        qty = _safe_int(it.get("qty"), 0)
        if qty <= 0:
            return False, {"status": "error", "error": "Quantity must be at least 1."}, 400
        found = _find_variant(products, it.get("plu"), it.get("product"), it.get("variant"))
        if not found:
            label = it.get("product") or it.get("plu") or "item"
            return False, {"status": "error",
                           "error": f"{label} no longer exists in your products."}, 409
        p_name, p_det, v = found
        key = (p_name, v["name"])
        if key in merged:
            merged[key]["qty"] += qty
        else:
            merged[key] = {"p_name": p_name, "p": p_det, "v": v, "qty": qty}
    if not merged:
        return False, {"status": "error", "error": "The cart is empty."}, 400

    lines = []
    shortfall = []
    for entry in merged.values():
        v, p_det, qty = entry["v"], entry["p"], entry["qty"]
        stock = _safe_int(v.get("units"), 0)
        if qty > stock:
            if offline:
                # The goods already left the shop - record the sale, flag it.
                shortfall.append(f"{entry['p_name']} ({v['name']}): sold {qty}, had {stock}")
            else:
                return False, {"status": "error",
                               "error": f"Only {stock} of {entry['p_name']} ({v['name']}) in stock."}, 409
        price = bm.variant_price(p_det, v)
        cost = bm.variant_cost(p_det, v)
        lines.append({
            "product": entry["p_name"], "variant": v["name"],
            "plu": str(v.get("PLU", "")), "qty": qty,
            "unit_price": round(price, 2), "unit_cost": round(cost, 2),
            "subtotal": round(price * qty, 2),
        })
    subtotal = round(sum(l["subtotal"] for l in lines), 2)

    # ── 2. customer & discount ───────────────────────────────────────────────
    customer = None
    cust_name = str(data.get("customer") or "").strip()
    if cust_name:
        matches = crm.find_customer(biz, cust_name)
        customer = next((c for c in matches if c["name"] == cust_name), matches[0] if matches else None)

    disc_in = data.get("discount") if isinstance(data.get("discount"), dict) else {}
    if not disc_in and bs.parse_number(data.get("discount_pct"), 0) > 0:
        disc_in = {"type": "percent", "value": data.get("discount_pct")}   # older clients
    dtype = str(disc_in.get("type", "none")).lower()
    dvalue = bs.parse_number(disc_in.get("value"), 0.0, 0)
    note = str(disc_in.get("note") or "").strip()[:60]
    points_redeemed = 0
    discount_label = ""

    if dtype == "points":
        if not customer or not crm.points_enabled(biz):
            return False, {"status": "error", "error": "Loyalty points are not available for this sale."}, 400
        tier = crm.get_eligible_discount(biz, customer)
        if not tier:
            return False, {"status": "error", "error": "This customer has no loyalty reward available."}, 400
        dtype, dvalue = "percent", float(tier["discount_pct"])
        points_redeemed = int(tier["points"])
        discount_label = f"Loyalty {tier.get('label', '')}".strip()
    elif dtype in ("percent", "amount"):
        if dtype == "percent":
            dvalue = min(dvalue, 100.0)
        eff_pct = dvalue if dtype == "percent" else (dvalue / subtotal * 100.0 if subtotal > 0 else 0)
        if not actor.get("is_manager") and eff_pct > cfg["max_staff_discount_pct"] + 0.001:
            return False, {"status": "error",
                           "error": f"Discounts above {cfg['max_staff_discount_pct']:g}% need a manager."}, 403
        discount_label = note or "Discount"
    else:
        dtype, dvalue = "none", 0.0

    totals = bs.compute_totals(subtotal, dtype, dvalue,
                               cfg["vat_enabled"], cfg["vat_pct"], cfg["vat_inclusive"])
    total = totals["total"]

    # ── 3. payment (supports paying in the alternate currency) ───────────────
    method = str(data.get("payment") or "Cash").strip()[:30] or "Cash"
    biz_curr = bm.get_business_currency(biz)
    pay_curr = str(data.get("pay_currency") or biz_curr).strip().upper() or biz_curr
    alt_rate = 1.0
    if pay_curr != biz_curr.upper():
        alt_rate = bf.load_exchange_rates().get(f"{biz_curr.upper()}_TO_{pay_curr}")
        if not alt_rate:
            pay_curr, alt_rate = biz_curr, 1.0
    due_pay = round(total * alt_rate, 2)
    if method == "Cash":
        tendered = bs.parse_number(data.get("payment_amount"), due_pay, 0)
        if tendered + 0.005 < due_pay:
            return False, {"status": "error", "error": "The amount tendered is less than the total."}, 400
        change_pay = round(tendered - due_pay, 2)
    else:
        tendered, change_pay = due_pay, 0.0
    payment_amount = round(tendered / alt_rate, 2)
    change = round(change_pay / alt_rate, 2)

    # ── 4. apply: stock → points → revenue → sale record ─────────────────────
    for entry in merged.values():
        v = entry["v"]
        v["units"] = max(0, _safe_int(v.get("units"), 0) - entry["qty"])
        v["sold"] = _safe_int(v.get("sold"), 0) + entry["qty"]
    bm.store_business()

    points_earned = 0
    if customer and crm.points_enabled(biz):
        if points_redeemed:
            crm.deduct_points(biz, customer["name"], points_redeemed)
        points_earned = crm.award_points(biz, customer["name"], totals["net"])

    bf.business_finance = bf.load_business_finance()
    bf.add_revenue(biz, totals["net"])          # revenue is recorded WITHOUT VAT

    now = bs.now()
    offline_at = str(data.get("offline_created_at") or "")
    if offline and offline_at:
        try:   # stamp the time the sale really happened, not the time it synced
            import datetime as _dt
            moment = _dt.datetime.fromisoformat(offline_at.replace("Z", "+00:00"))
            if moment.tzinfo is not None:
                utc_naive = moment.astimezone(_dt.timezone.utc).replace(tzinfo=None)
                offset = bs.now() - _dt.datetime.utcnow()     # local minus UTC
                moment = utc_naive + _dt.timedelta(minutes=round(offset.total_seconds() / 60))
            now = moment
        except Exception:
            pass

    sale = {
        "sale_id": sale_id,
        "receipt_no": next_receipt_no(biz_sales),
        "date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M"),
        "items": lines,
        "subtotal": totals["subtotal"],
        "discount_type": dtype, "discount_pct": totals["discount_pct"],
        "discount_amt": totals["discount_amt"], "discount_label": discount_label,
        "tax_pct": cfg["vat_pct"] if (cfg["vat_enabled"] and cfg["vat_pct"] > 0) else 0,
        "tax_amt": totals["vat_amt"], "vat_inclusive": cfg["vat_inclusive"],
        "net_amount": totals["net"],
        "total": total,
        "payment": method, "payment_amount": payment_amount, "change": change,
        "pay_currency": pay_curr, "alt_rate": alt_rate,
        "tendered": round(tendered, 2), "change_pay": change_pay,
        "customer": customer["name"] if customer else None,
        "points_earned": points_earned, "points_redeemed": points_redeemed,
        "cashier": str(actor.get("name") or "")[:40],
        "refunded": False,
    }
    if offline:
        sale["offline"] = True
    if shortfall:
        sale["stock_shortfall"] = shortfall
    try:
        client_total = float(data.get("client_total"))
        if abs(client_total - total) > 0.011:
            sale["client_total"] = round(client_total, 2)   # price/VAT changed while offline
    except (TypeError, ValueError):
        pass

    biz_sales.append(sale)
    save_sales(sales_all)
    try:
        bm.export_to_csv(biz)
    except Exception as exc:
        print(f"[pos] CSV export skipped: {exc}")

    fresh = None
    if customer:
        crm.log_purchase_to_customer(biz, customer["name"], lines, total, points_earned)
        found = crm.find_customer(biz, customer["name"])
        fresh = next((c for c in found if c["name"] == customer["name"]), None)
    return True, {"status": "ok", "sale": sale, "receipt": build_receipt(biz, sale, fresh)}, 200


def refund_sale_web(biz, sale_id):
    """Reverse a sale: stock, revenue and loyalty points. Returns (ok, message)."""
    with _sale_lock:
        sales_all = load_sales()
        biz_sales = sales_all.get(biz, [])
        sale = next((s for s in biz_sales if s.get("sale_id") == sale_id), None)
        if sale is None:
            return False, "Sale not found."
        if sale.get("refunded"):
            return False, "Sale already refunded."

        businesses = bm.load_business()
        bm.businesses = businesses
        products = businesses.get(biz, {}).get("products", {})
        for item in sale.get("items", []):
            found = _find_variant(products, item.get("plu"), item.get("product"), item.get("variant"))
            if found:
                v = found[2]
                v["units"] = _safe_int(v.get("units"), 0) + _safe_int(item.get("qty"), 0)
                v["sold"] = max(0, _safe_int(v.get("sold"), 0) - _safe_int(item.get("qty"), 0))
        bm.store_business()

        bf.business_finance = bf.load_business_finance()
        fin = bf.business_finance.get(biz, {"Revenue": 0, "Costs": 0})
        back = sale.get("net_amount", sale.get("total", 0)) or 0
        fin["Revenue"] = max(0, (fin.get("Revenue", 0) or 0) - back)
        bf.business_finance[biz] = fin
        bf.update_save_finance(biz)

        name = sale.get("customer")
        if name:
            raw = crm._load_raw()
            for c in raw.get(biz, []):
                if c.get("name") == name:
                    pts = c.get("points", 0) - (sale.get("points_earned", 0) or 0) + (sale.get("points_redeemed", 0) or 0)
                    c["points"] = max(0, pts)
            crm._save_raw(raw)

        sale["refunded"] = True
        sale["refunded_at"] = bs.now().strftime("%Y-%m-%d %H:%M")
        save_sales(sales_all)
        return True, sale
