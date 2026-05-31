import json
import csv
import re
FILE1 = "Businesses.json"
businesses = {}

CURRENCY_SYMBOLS = {
    "USD": "$", "GBP": "£", "EUR": "€", "JPY": "¥", "CNY": "¥",
    "CAD": "CA$", "AUD": "A$", "CHF": "Fr", "INR": "₹", "NGN": "₦",
    "ZAR": "R", "KES": "KSh", "GHS": "₵", "MXN": "MX$", "BRL": "R$",
    "SGD": "S$", "HKD": "HK$", "SEK": "kr", "NOK": "kr", "DKK": "kr", "ZWG": "ZiG"
}


def get_currency_symbol(code):
    return CURRENCY_SYMBOLS.get(code.upper(), code + " ")

def get_business_currency(name):
    return businesses.get(name, {}).get("currency", "USD")

def format_price(stored_price, symbol):
    clean = str(stored_price)
    for s in CURRENCY_SYMBOLS.values():
        clean = clean.replace(s, "")
    clean = clean.replace("$", "").strip()
    return f"{symbol}{clean}"

def prompt_currency():
    try:
        import business_finance as bf
        rates = bf.load_exchange_rates()
        available = set()
        for key in rates.keys():
            parts = key.split("_TO_")
            available.update(parts)
        if available:
            print(f"  Currencies from saved rates: {', '.join(sorted(available))}")
    except Exception:
        pass
    print("  Common codes: USD ($), GBP (£), EUR (€), NGN (₦), GHS (₵), KES (KSh)")
    code = input("  Currency code: ").upper().strip()
    return code if code else "USD"

def convert_business_currency(name, old_curr, new_curr):
    import business_finance as bf
    import json as _json
    rates = bf.load_exchange_rates()
    key_fwd = f"{old_curr}_TO_{new_curr}"
    key_rev = f"{new_curr}_TO_{old_curr}"
    if key_fwd in rates:
        rate = rates[key_fwd]
    elif key_rev in rates:
        rate = 1 / rates[key_rev]
    else:
        print(f"  No exchange rate found for {old_curr} → {new_curr}.")
        print(f"  Add it in Finance → Currency Tools → Manage Exchange Rates, then try again.")
        return False
    print(f"  Converting at rate: 1 {old_curr} = {rate:.4f} {new_curr}")
    for p_name, details in businesses[name]["products"].items():
        for field in ["Price", "Cost"]:
            raw = str(details.get(field, "0")).replace("$", "").replace("£", "").replace("€", "").strip()
            try:
                businesses[name]["products"][p_name][field] = f"${float(raw) * rate:.2f}"
            except ValueError:
                pass
    store_business()
    fin_data = bf.load_business_finance()
    if name in fin_data:
        for field in ["Revenue", "Costs", "Profit"]:
            val = fin_data[name].get(field, 0) or 0
            fin_data[name][field] = round(val * rate, 2)
        with open(bf.FINANCEFILE, "w") as f:
            _json.dump(fin_data, f, indent=4)
        bf.business_finance[name] = fin_data[name]
    emp_data = bf.load_employees()
    if name in emp_data:
        for emp in emp_data[name]:
            emp["salary"] = round((emp.get("salary", 0) or 0) * rate, 2)
        bf.save_employees(emp_data)
    print(f"  All monetary values converted from {old_curr} to {new_curr}.")
    return True

def validate_email(email):
    pattern = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
    return re.match(pattern, email) is not None

def input_email():
    while True:
        email = input("Email: ").strip()
        if validate_email(email):
            return email
        else:
            print("Invalid email. Please enter a valid email (e.g. name@example.com)")



# --- CORE FUNCTIONS ---

def export_to_csv(name):
    filename = f"{name}_inventory.csv"
    products = businesses.get(name, {}).get("products", {})
    
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["PLU", "Product", "Selling Price", "Cost Price", "Variant", "Units", "Total Sold"])
        for p_name, details in products.items():
            for v in details.get("variants", []):
                writer.writerow([v.get("PLU", ""), p_name, details.get("Price"), details.get("Cost", "N/A"), v.get("name"), v.get("units"), v.get("sold", 0)])
    print(f"Inventory exported to {filename} successfully.")




def remove_product(name, product_name):
    if product_name in businesses[name]["products"]:
        businesses[name]["products"].pop(product_name)
        print(f"The product {product_name} has been removed")
        store_business()
    else:
        print("Error: Invalid Product")

def edit_variant(name, product_name, variant_name):
    product = businesses.get(name, {}).get("products", {}).get(product_name, {})
    variants = product.get("variants", [])
    target_variant = next((v for v in variants if isinstance(v, dict) and v.get("name") == variant_name), None)
    
    if target_variant:
        while True:
            product_data = businesses[name]["products"][product_name]
            sell_price = product_data.get("Price", "Not Set")
            cost_price = product_data.get("Cost", "Not Set")
            plu = target_variant.get("PLU", "N/A")
            print(f"\nEditing '{variant_name}' in {product_name}")
            print(f"  PLU: {plu} | Selling Price: {sell_price} | Cost Price: {cost_price}")
            print("1: Update Name")
            print("2: Update Units")
            print("3: Update Selling Price")
            print("4: Update Cost Price")
            print("5: Update PLU Code")
            print("6: Cancel")
            try:
                choice = int(input("Pick an option (1-6): "))
                if choice == 1:
                    new_name = input("Enter new name: ").title()
                    target_variant["name"] = new_name
                    print(f"Name updated to {new_name}")
                    store_business(); break
                elif choice == 2:
                    units = int(input(f"How many units for {variant_name}: "))
                    target_variant["units"] = units
                    print(f"Units updated to {units}")
                    store_business()
                    export_to_csv(name)
                    break
                elif choice == 3:
                    curr = get_business_currency(name)
                    sym = get_currency_symbol(curr)
                    raw = input(f"New selling price ({curr}): ").replace("$", "").replace(sym, "").strip()
                    try:
                        product_data["Price"] = f"${float(raw):.2f}"
                        print(f"Selling price updated to {sym}{float(raw):.2f}")
                        store_business()
                        export_to_csv(name)
                        break
                    except ValueError:
                        print("Invalid price.")
                elif choice == 4:
                    curr = get_business_currency(name)
                    sym = get_currency_symbol(curr)
                    raw = input(f"New cost price ({curr}): ").replace("$", "").replace(sym, "").strip()
                    try:
                        product_data["Cost"] = f"${float(raw):.2f}"
                        print(f"Cost price updated to {sym}{float(raw):.2f}")
                        store_business()
                        export_to_csv(name)
                        break
                    except ValueError:
                        print("Invalid price.")
                elif choice == 5:
                    new_plu = prompt_unique_plu(name, variant_name, skip_product=product_name, skip_variant=variant_name)
                    target_variant["PLU"] = new_plu
                    print(f"PLU code updated to {new_plu}")
                    store_business()
                    export_to_csv(name)
                    break
                elif choice == 6:
                    return
            except ValueError:
                print("Invalid input.")
    else:
        print(f"Variant '{variant_name}' not found.")

def view_product(name):
    print(f"\n-----{name.upper()} PRODUCTS:")
    sym = get_currency_symbol(get_business_currency(name))
    products = businesses[name].get("products", {})
    if not products:
        print(f"There are no products in {name.title()}")
    else:
        for p_name, details in products.items():
            sell_price = format_price(details.get('Price', 'Not Set'), sym)
            cost_price = format_price(details.get('Cost', 'Not Set'), sym)
            print(f"PRODUCT: {p_name} -- Selling Price: {sell_price} | Cost Price: {cost_price}")
            variants = details.get("variants", [])
            if variants:
                for v in variants:
                    plu = v.get('PLU', 'N/A')
                    sold = v.get('sold', 0)
                    print(f"    [{plu}] {v['name']}: {v['units']} units | sold: {sold}")

def add_product(name, product_name):
    curr = get_business_currency(name)
    sym = get_currency_symbol(curr)
    raw_price = input(f"Selling price ({curr}): ").replace("$", "").replace(sym, "").strip()
    raw_cost = input(f"Cost price — what it costs you to make/buy it ({curr}): ").replace("$", "").replace(sym, "").strip()
    try:
        price = float(raw_price)
        try:
            cost = float(raw_cost)
        except ValueError:
            cost = 0.0
            print(f"Invalid cost price — defaulting to {sym}0.00")
        businesses[name]["products"][product_name] = {
            "Price": f"${price:.2f}",
            "Cost": f"${cost:.2f}",
            "variants": []
        }
        store_business()
        export_to_csv(name)
        print(f"Product {product_name} stored — Selling: {sym}{price:.2f} | Cost: {sym}{cost:.2f}")
    except ValueError:
        print("Enter a numerical price value")

def get_inventory_value(name):
    print(f"\n--- INVENTORY BREAKDOWN: {name.upper()} ---")
    grand_total = 0
    for p_name, details in businesses[name]["products"].items():
        product_total = sum(v.get("units", 0) for v in details.get("variants", []))
        print(f"{p_name}: {product_total} units")
        grand_total += product_total
    print(f"TOTAL ACROSS ALL PRODUCTS: {grand_total} units")

def low_stock_report(name, threshold=5):
    print(f"\n--- LOW STOCK REPORT (Under {threshold} units) ---")
    found = False
    for p_name, details in businesses[name]["products"].items():
        for v in details.get("variants", []):
            if v.get("units", 0) < threshold:
                print(f"ALERT: {p_name} ({v.get('name')}) - Only {v.get('units')} units left!")
                found = True
    if not found:
        print("All stock levels are healthy.")

def find_plu_owner(name, plu, skip_product=None, skip_variant=None):
    for p_name, details in businesses[name].get("products", {}).items():
        for v in details.get("variants", []):
            if v.get("PLU", "").strip() == plu.strip():
                if p_name == skip_product and v.get("name") == skip_variant:
                    continue
                return f"{p_name} → {v.get('name')}"
    return None

def prompt_unique_plu(name, label, skip_product=None, skip_variant=None):
    while True:
        plu = input(f"  PLU code for '{label}' (e.g. 0001): ").strip()
        owner = find_plu_owner(name, plu, skip_product, skip_variant)
        if owner:
            print(f"  PLU '{plu}' is already used by: {owner}")
            ans = input("  Would you like to enter a different PLU? (Y/N): ").strip().upper()
            if ans != "Y":
                print("  PLU codes must be unique. Please enter a different PLU.")
        else:
            return plu

def add_variant(name, product_variant):
    current_variants = businesses[name]["products"][product_variant].get("variants", [])
    while True:
        variant = input("What is the name of the variant (Q to quit): ").title()
        if variant == "Q": break
        plu = prompt_unique_plu(name, variant)
        try:
            units = int(input("  Number of units: "))
            current_variants.append({"name": variant, "units": units, "PLU": plu, "sold": 0})
            businesses[name]["products"][product_variant]["variants"] = current_variants
            print(f"Variant '{variant}' [PLU: {plu}] added.")
            store_business()
            export_to_csv(name)
            cost_str = str(businesses[name]["products"][product_variant].get("Cost", "0")).replace("$", "").strip()
            try:
                stock_cost = float(cost_str) * units
                import business_finance as bf
                bf.add_costs(name, stock_cost, f"{product_variant} stock ({variant}, {units} units)")
            except ValueError:
                pass
        except ValueError:
            print("Please enter a numeric value.")

def remove_variant(name, product_variant, variant_name):
    product = businesses[name]["products"].get(product_variant)
    if product and "variants" in product:
        for v in product["variants"]:
            if v.get("name") == variant_name:
                product["variants"].remove(v)
                store_business()
                export_to_csv(name)
                print(f"Variant '{variant_name}' removed.")
                return
    print("Variant or product not found.")

def best_sellers(name):
    sym = get_currency_symbol(get_business_currency(name))
    all_variants = []
    for p_name, details in businesses[name].get("products", {}).items():
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
        print("No sales recorded yet.")
        return
    all_variants.sort(key=lambda x: x["sold"], reverse=True)
    print(f"\n--- BEST SELLERS: {name.upper()} ---")
    print(f"  {'Rank':<5} {'PLU':<8} {'Product / Variant':<30} {'Sold':>6} {'Revenue':>12}")
    print(f"  {'-'*65}")
    for i, item in enumerate(all_variants, 1):
        label = f"{item['product']} ({item['variant']})"
        print(f"  {i:<5} {item['plu']:<8} {label:<30} {item['sold']:>6} {sym}{item['revenue']:>11.2f}")

def group_menu(name):
    if "groups" not in businesses[name]:
        businesses[name]["groups"] = {}
    groups = businesses[name]["groups"]
    while True:
        print(f"\n--- PRODUCT GROUPS: {name.upper()} ---")
        print("1: Create Group")
        print("2: Add Product to Group")
        print("3: View Group")
        print("4: Remove Product from Group")
        print("5: Delete Group")
        print("6: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                g_name = input("Group name: ").title()
                if g_name in groups:
                    print("Group already exists.")
                else:
                    groups[g_name] = []
                    store_business()
                    print(f"Group '{g_name}' created.")
            elif choice == 2:
                if not groups:
                    print("No groups yet. Create one first.")
                    continue
                print("Groups:", ", ".join(groups.keys()))
                g_name = input("Group name: ").title()
                if g_name not in groups:
                    print("Group not found.")
                    continue
                products = list(businesses[name]["products"].keys())
                if not products:
                    print("No products in this business.")
                    continue
                print("Products:", ", ".join(products))
                p_name = input("Product to add: ").title()
                if p_name not in businesses[name]["products"]:
                    print("Product not found.")
                elif p_name in groups[g_name]:
                    print(f"'{p_name}' is already in '{g_name}'.")
                else:
                    groups[g_name].append(p_name)
                    store_business()
                    print(f"'{p_name}' added to '{g_name}'.")
            elif choice == 3:
                if not groups:
                    print("No groups created yet.")
                    continue
                print("Groups:", ", ".join(groups.keys()))
                g_name = input("Group to view: ").title()
                if g_name not in groups:
                    print("Group not found.")
                    continue
                products_in_group = groups[g_name]
                sym = get_currency_symbol(get_business_currency(name))
                print(f"\n  --- GROUP: {g_name.upper()} ---")
                if not products_in_group:
                    print("  No products in this group yet.")
                else:
                    for p_name in products_in_group:
                        details = businesses[name]["products"].get(p_name, {})
                        sell_price = format_price(details.get("Price", "Not Set"), sym)
                        print(f"  PRODUCT: {p_name} -- {sell_price}")
                        for v in details.get("variants", []):
                            plu = v.get("PLU", "N/A")
                            print(f"    [{plu}] {v['name']}: {v['units']} units | sold: {v.get('sold', 0)}")
            elif choice == 4:
                if not groups:
                    print("No groups yet.")
                    continue
                print("Groups:", ", ".join(groups.keys()))
                g_name = input("Group name: ").title()
                if g_name not in groups:
                    print("Group not found.")
                    continue
                if not groups[g_name]:
                    print("Group is empty.")
                    continue
                print("Products in group:", ", ".join(groups[g_name]))
                p_name = input("Product to remove: ").title()
                if p_name in groups[g_name]:
                    groups[g_name].remove(p_name)
                    store_business()
                    print(f"'{p_name}' removed from '{g_name}'.")
                else:
                    print("Product not in this group.")
            elif choice == 5:
                if not groups:
                    print("No groups yet.")
                    continue
                print("Groups:", ", ".join(groups.keys()))
                g_name = input("Group to delete: ").title()
                if g_name in groups:
                    del groups[g_name]
                    store_business()
                    print(f"Group '{g_name}' deleted.")
                else:
                    print("Group not found.")
            elif choice == 6:
                break
            else:
                print("Enter 1-6.")
        except ValueError:
            print("Invalid input.")

# --- BUSINESS MANAGEMENT FUNCTIONS ---

def add_business(name, industry, location, targetcustomer, businessmail, currency="USD"):
    global businesses
    businesses[name] = {
        "industry": industry,
        "location": location,
        "targetcustomer": targetcustomer,
        "businessmail": businessmail,
        "currency": currency,
        "products": {},
        "groups": {}
    }
    store_business()
    export_to_csv(name)
    sym = get_currency_symbol(currency)
    print(f"Business '{name}' created with currency: {currency} ({sym})")

def edit_business(name):
    if name in businesses:
        print(f"\nEditing {name}")
        curr = businesses[name].get("currency", "USD")
        sym = get_currency_symbol(curr)
        print(f"1: Industry\n2: Target Customers\n3: Location\n4: Email\n5: Products\n6: Currency (current: {curr} {sym})\n7: Exit")
        try:
            option = int(input("Pick an option: "))
            if option == 1:
                businesses[name]["industry"] = input("New industry: ").title()
            elif option == 2:
                businesses[name]["targetcustomer"] = input("New target: ").title()
            elif option == 3:
                businesses[name]["location"] = input("New location: ").title()
            elif option == 4:
                businesses[name]["businessmail"] = input_email()
            elif option == 5:
                product_menu(name)
            elif option == 6:
                print(f"Current currency: {curr} ({sym})")
                new_curr = prompt_currency()
                if new_curr == curr:
                    print("Currency unchanged.")
                else:
                    success = convert_business_currency(name, curr, new_curr)
                    if success:
                        businesses[name]["currency"] = new_curr
                        new_sym = get_currency_symbol(new_curr)
                        store_business()
                        export_to_csv(name)
                        print(f"Currency changed to {new_curr} ({new_sym})")
            if option in [1, 2, 3, 4]:
                store_business()
                export_to_csv(name)
        except ValueError:
            print("Invalid input.")
    else:
        print("Business not found.")

def get_all_business():
    if not businesses:
        print("No businesses stored.")
    for name in businesses:
        print(f"- {name}")

def delete_business(name):
    if name in businesses:
        businesses.pop(name)
        store_business()
        print(f"{name} removed.")
    else:
        print("Not found.")

def search_business(name):
    if name in businesses:
        print(f"Found: {name} ({businesses[name]['industry']})")
    else:
        print("Not found.")

def store_business():
    with open(FILE1, "w") as file:
        json.dump(businesses, file, indent=4)
        print(f"Data saved to {FILE1}")

def load_business():
    try:
        with open(FILE1, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def count_businesses():
    print(f"Total Businesses: {len(businesses)}")

def business_menu():
    global businesses
    businesses = load_business()
    is_running = True
    while is_running:
        try:
            print("\nBUSINESS MANAGEMENT SYSTEM")
            print("1: Add Business | 2: Products | 3: Delete | 4: Search | 5: Count | 6: List | 7: Edit | 8: Exit")
            option = int(input("Option: "))
            if option == 1:
                name = input("Name: ").title()
                if name in businesses:
                    print("Exists already.")
                else:
                    industry = input("Industry: ").title()
                    location = input("Location: ").title()
                    target = input("Target: ").title()
                    email = input_email()
                    print("Select currency for this business:")
                    currency = prompt_currency()
                    add_business(name, industry, location, target, email, currency)
            elif option == 2:
                name = input("Business Name: ").title()
                if name in businesses: product_menu(name)
                else: print("Invalid Business.")
            elif option == 3: delete_business(input("Name to delete: ").title())
            elif option == 4: search_business(input("Search: ").title())
            elif option == 5: count_businesses()
            elif option == 6: get_all_business()
            elif option == 7: edit_business(input("Edit which business: ").title())
            elif option == 8: is_running = False
        except ValueError:
            print("Enter a number.")


def product_menu(name):
    is_running = True

    while is_running:
        try:
            print("\nWELCOME TO PRODUCT MENU")
            print("-------------------------")
            print("OPTIONS")
            print("1: ADD NEW PRODUCT(S)")
            print("2: ADD VARIANT TO PRODUCT(S)")
            print("3: EDIT EXISTING VARIANT(S)")
            print("4: REMOVE PRODUCT(S)")
            print("5: VIEW PRODUCT(S)")
            print("6: REMOVE VARIANT")
            print("7: EXPORT TO CSV (EXCEL)")
            print("8: TOTAL INVENTORY COUNT")
            print("9: LOW STOCK REPORT")
            print("10: BEST SELLERS")
            print("11: PRODUCT GROUPS")
            print("12: EXIT")

            option = int(input("Pick option from 1-12: "))

            if option == 1:
                product_name = input("What is the product (Q to exit): ").title()
                if product_name == "Q":
                    continue
                add_product(name, product_name)

            elif option == 2:
                print("\nAVAILABLE PRODUCTS")
                for p_name in businesses[name]["products"].keys():
                    print(f"--{p_name}--")

                product_variant = input("What product do you want to edit: ").title()
                if product_variant in businesses[name]["products"]:
                    add_variant(name, product_variant)
                else:
                    print("PRODUCT NOT FOUND")

            elif option == 3:
                view_product(name)
                try:
                    product_to_edit = input("What product do you want to edit: ").title()
                    if product_to_edit in businesses[name]["products"]:
                        current_variants = businesses[name]["products"][product_to_edit].get("variants", [])

                        if current_variants:
                            v_names = [v['name'] for v in current_variants if isinstance(v, dict)]
                            print(f"Current Variants: {', '.join(v_names)}")

                            while True:
                                v_edit = input("What variant do you want to edit (Q to quit): ").title()
                                if v_edit == "Q":
                                    break

                                if v_edit in v_names:
                                    edit_variant(name, product_to_edit, v_edit)
                                    break 
                                else:
                                    print("Invalid variant entered.")
                        else:
                            print("There are no variants stored for this product.")
                    else:
                        print("Entered product not found.")
                except Exception as e:
                    print(f"An error occurred: {e}")

            elif option == 4:
                print("\nAVAILABLE PRODUCTS")
                for p_name in businesses[name]["products"].keys():
                    print(f"--{p_name}--")
                product_name = input("What is the name of the product you are removing: ").title()
                remove_product(name, product_name)

            elif option == 5:
                view_product(name)

            elif option == 6:
                print("\nAVAILABLE PRODUCTS")
                for p_name in businesses[name]["products"].keys():
                    print(f"--{p_name}--")

                product_name = input("Which product's variant do you want to remove: ").title()
                if product_name in businesses[name]["products"]:
                    current_variants = businesses[name]["products"][product_name].get("variants", [])
                    if current_variants:
                        v_names = [v['name'] if isinstance(v, dict) else str(v) for v in current_variants]
                        print(f"Current Variants: {', '.join(v_names)}")
                        variant_to_remove = input("Which variant do you want to remove: ").title()
                        if variant_to_remove in v_names:
                            remove_variant(name, product_name, variant_to_remove)
                        else:
                            print("Variant not found in list.")
                    else:
                        print("NO AVAILABLE VARIANTS for this product.")
                else:
                    print("Error: Invalid Product Name")

            elif option == 7:
                export_to_csv(name)

            elif option == 8:
                get_inventory_value(name)

            elif option == 9:
                try:
                    limit = int(input("Enter threshold for low stock (default 5): "))
                    low_stock_report(name, threshold=limit)
                except ValueError:
                    low_stock_report(name)

            elif option == 10:
                best_sellers(name)

            elif option == 11:
                group_menu(name)

            elif option == 12:
                print("EXITING PRODUCT MENU....")
                is_running = False

            else:
                print("Enter number between 1-12")

        except ValueError:
            print("Enter a numeric value")

if __name__ == "__main__":
    business_menu()
