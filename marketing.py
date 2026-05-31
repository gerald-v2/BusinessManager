#BUSINESS MARKETING MANAGEMENT
import json
import api_handler
import business_manager

business_found = {}

PRICE_FILE = "price_monitor.json"
KEYWORD_FILE = "keywords.json"
SENTIMENT_FILE = "sentiment.json"
CAMPAIGN_FILE = "campaigns.json"

#____STORAGE HELPERS____
def _load_json(filepath):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)

#____BUSINESS INFO____
def get_business_info():
    global business_found
    if not business_found:
        return None, None, None
    return (
        business_found.get("industry"),
        business_found.get("location"),
        business_found.get("targetcustomer")
    )

def check_business():
    global business_found
    name = input("Business Name: ").title()
    business_looking = api_handler.fetch_data()
    if name in business_looking:
        print(f"{name} found.")
        business_found = business_looking[name]
        return name
    else:
        print("Business not found.")
        print("Redirecting to Business Manager...")
        business_manager.business_menu()
        return None

#____MARKETING TOOLS (API-DEPENDENT)____
def generate_email_campaign(name):
    industry, location, target = get_business_info()
    prompt = f"Write a professional marketing email for {name}. They are in the {industry} industry targeting {target}. Mention they are located in {location}."
    print("--- GENERATING EMAIL CAMPAIGN ---")
    print(api_handler.call_api(prompt))

def create_image(name, industry, location, targetcustomer):
    if not name:
        print("Error: No business selected.")
        return
    prompt = f"Create a marketing image for {name} business: They specialise in {industry}, target customers are {targetcustomer}, based in {location}."
    print(f"--- CREATING IMAGE FOR {name.upper()} ---")
    print(api_handler.call_api(prompt))

def create_caption(name, industry, location, targetcustomer):
    if not name:
        print("Error: No business selected.")
        return
    prompt = f"Create a caption for {name} business: specialises in {industry}, based in {location}, target customers are {targetcustomer}."
    print(f"--- CREATING CAPTION FOR {name.upper()} ---")
    print(api_handler.call_api(prompt))

def automarketing():
    print("Automarketing is not yet available (coming soon).")

#____MARKETING PLAN____
def marketing_plan():
    name = check_business()
    if not name:
        return
    industry, location, targetcustomer = get_business_info()
    businesses = api_handler.fetch_data()
    products = businesses.get(name, {}).get("products", {})
    product_list = list(products.keys()) if products else ["No products added yet"]

    print(f"\n{'='*40}")
    print(f"  MARKETING PLAN: {name.upper()}")
    print(f"{'='*40}")
    print(f"  Industry:         {industry}")
    print(f"  Location:         {location}")
    print(f"  Target Customers: {targetcustomer}")
    print(f"  Products:         {', '.join(product_list)}")
    print(f"\n--- RECOMMENDED STRATEGIES ---")
    print(f"  1. Social Media  - Target {targetcustomer} on Instagram, Facebook & TikTok")
    print(f"  2. Local Reach   - Use {location}-based advertising and events")
    print(f"  3. Content       - Post tips and content relevant to {industry}")
    print(f"  4. Email         - Build a mailing list and send regular updates")
    print(f"  5. Referrals     - Incentivise existing customers to refer others")
    print(f"  6. Promotions    - Run seasonal deals to drive traffic")
    print(f"\n--- KEY METRICS TO TRACK ---")
    print(f"  - Customer Acquisition Cost (CAC)")
    print(f"  - Conversion Rate")
    print(f"  - Return on Ad Spend (ROAS)")
    print(f"  - Customer Lifetime Value (CLV)")
    print(f"{'='*40}")

#____PRICE MONITOR____
def price_monitor():
    data = _load_json(PRICE_FILE)
    is_running = True
    while is_running:
        print("\n--- PRICE MONITOR ---")
        print("1: Add Competitor Price")
        print("2: View Competitor Prices")
        print("3: Compare With Your Prices")
        print("4: Remove Competitor")
        print("5: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                competitor = input("Competitor name: ").title()
                product = input("Product/Service: ").title()
                price = float(input("Their price ($): "))
                if competitor not in data:
                    data[competitor] = {}
                data[competitor][product] = price
                _save_json(PRICE_FILE, data)
                print(f"Price recorded for {competitor}.")
            elif choice == 2:
                if not data:
                    print("No competitor prices tracked yet.")
                else:
                    print("\n--- COMPETITOR PRICES ---")
                    for comp, products in data.items():
                        print(f"\n  {comp}:")
                        for prod, price in products.items():
                            print(f"    {prod}: ${price:.2f}")
            elif choice == 3:
                name = check_business()
                if not name:
                    continue
                businesses = api_handler.fetch_data()
                your_products = businesses.get(name, {}).get("products", {})
                if not your_products:
                    print("No products found for your business.")
                    continue
                print(f"\n--- PRICE COMPARISON: {name.upper()} ---")
                for p_name, details in your_products.items():
                    your_price = str(details.get("Price", "N/A")).replace("$", "")
                    print(f"\n  Your product: {p_name} — ${your_price}")
                    for comp, comp_products in data.items():
                        if p_name in comp_products:
                            diff = float(your_price or 0) - comp_products[p_name]
                            direction = "higher" if diff > 0 else "lower" if diff < 0 else "same"
                            print(f"    {comp}: ${comp_products[p_name]:.2f} (you are ${abs(diff):.2f} {direction})")
            elif choice == 4:
                if not data:
                    print("No competitors to remove.")
                    continue
                for i, comp in enumerate(data.keys(), 1):
                    print(f"  {i}. {comp}")
                competitor = input("Competitor name to remove: ").title()
                if competitor in data:
                    del data[competitor]
                    _save_json(PRICE_FILE, data)
                    print(f"{competitor} removed.")
                else:
                    print("Not found.")
            elif choice == 5:
                is_running = False
            else:
                print("Enter 1-5.")
        except ValueError:
            print("Invalid input.")

#____CUSTOMER MAPPING____
def customer_mapping():
    name = check_business()
    if not name:
        return
    industry, location, targetcustomer = get_business_info()
    businesses = api_handler.fetch_data()
    products = businesses.get(name, {}).get("products", {})

    print(f"\n{'='*40}")
    print(f"  CUSTOMER MAP: {name.upper()}")
    print(f"{'='*40}")
    print(f"  Primary Target:   {targetcustomer}")
    print(f"  Location:         {location}")
    print(f"  Industry:         {industry}")
    print(f"\n--- WHERE TO FIND THEM ---")
    print(f"  - Local events and markets in {location}")
    print(f"  - Online communities related to {industry}")
    print(f"  - Social platforms where {targetcustomer} spend time")
    print(f"\n--- HOW TO REACH THEM ---")
    print(f"  - Targeted social media ads")
    print(f"  - Local flyers and word-of-mouth in {location}")
    print(f"  - Partnerships with businesses serving {targetcustomer}")
    if products:
        print(f"\n--- PRODUCTS FOR YOUR CUSTOMERS ---")
        for p_name, details in products.items():
            print(f"  - {p_name}: {details.get('Price', 'N/A')}")
    print(f"{'='*40}")

#____KEYWORD IDENTIFIER____
def key_word_identifier():
    data = _load_json(KEYWORD_FILE)
    is_running = True
    while is_running:
        print("\n--- KEYWORD TRACKER ---")
        print("1: Add Keywords")
        print("2: View Keywords")
        print("3: Remove Keyword")
        print("4: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                name = check_business()
                if not name:
                    continue
                print("Enter keywords one at a time. Type Q to stop.")
                if name not in data:
                    data[name] = []
                while True:
                    kw = input("Keyword: ").lower().strip()
                    if kw == "q":
                        break
                    if kw and kw not in data[name]:
                        data[name].append(kw)
                        print(f"  '{kw}' added.")
                    elif kw in data[name]:
                        print("  Keyword already exists.")
                _save_json(KEYWORD_FILE, data)
            elif choice == 2:
                if not data:
                    print("No keywords tracked yet.")
                else:
                    print("\n--- SAVED KEYWORDS ---")
                    for biz, keywords in data.items():
                        print(f"  {biz}: {', '.join(keywords)}")
            elif choice == 3:
                name = input("Business Name: ").title()
                if name in data and data[name]:
                    print(f"  Keywords: {', '.join(data[name])}")
                    kw = input("Keyword to remove: ").lower().strip()
                    if kw in data[name]:
                        data[name].remove(kw)
                        _save_json(KEYWORD_FILE, data)
                        print(f"  '{kw}' removed.")
                    else:
                        print("Keyword not found.")
                else:
                    print("No keywords found for that business.")
            elif choice == 4:
                is_running = False
            else:
                print("Enter 1-4.")
        except ValueError:
            print("Invalid input.")

#____PRODUCT ANALYSIS____
def product_analysis():
    name = check_business()
    if not name:
        return
    businesses = api_handler.fetch_data()
    products = businesses.get(name, {}).get("products", {})
    if not products:
        print(f"No products found for {name}.")
        return
    print(f"\n{'='*40}")
    print(f"  PRODUCT ANALYSIS: {name.upper()}")
    print(f"{'='*40}")
    total_value = 0
    total_units = 0
    for p_name, details in products.items():
        price_str = str(details.get("Price", "0")).replace("$", "").strip()
        try:
            price = float(price_str)
        except ValueError:
            price = 0
        variants = details.get("variants", [])
        units = sum(v.get("units", 0) for v in variants)
        value = price * units
        total_value += value
        total_units += units
        status = "LOW STOCK" if units < 5 else "OK"
        print(f"\n  Product: {p_name}")
        print(f"    Price:             ${price:.2f}")
        print(f"    Units in Stock:    {units}  [{status}]")
        print(f"    Inventory Value:   ${value:.2f}")
        if variants:
            print(f"    Variants:          {', '.join(v.get('name','') for v in variants)}")
    print(f"\n  TOTALS")
    print(f"    Total Units:       {total_units}")
    print(f"    Total Inv. Value:  ${total_value:.2f}")
    print(f"{'='*40}")

#____SPEND AND REVENUE____
def spend_and_revenue():
    import business_finance as bf
    name = check_business()
    if not name:
        return
    finance_data = bf.load_business_finance()
    data = finance_data.get(name, {})
    revenue = data.get("Revenue", 0) or 0
    costs = data.get("Costs", 0) or 0
    profit = revenue - costs
    margin = (profit / revenue * 100) if revenue > 0 else 0
    print(f"\n{'='*40}")
    print(f"  EXPENDITURE & REVENUE: {name.upper()}")
    print(f"{'='*40}")
    print(f"  Revenue: ${revenue:.2f}")
    print(f"  Costs:   ${costs:.2f}")
    print(f"  Profit:  ${profit:.2f}")
    print(f"  Margin:  {margin:.1f}%")
    if profit > 0:
        print("  Status:  PROFITABLE")
    elif profit == 0:
        print("  Status:  BREAKING EVEN")
    else:
        print("  Status:  AT A LOSS")
    print(f"{'='*40}")

#____SENTIMENT TRACKER____
def sentiment_tracker():
    data = _load_json(SENTIMENT_FILE)
    is_running = True
    while is_running:
        print("\n--- SENTIMENT TRACKER ---")
        print("1: Log Customer Feedback")
        print("2: View Sentiment Report")
        print("3: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                name = check_business()
                if not name:
                    continue
                try:
                    rating = int(input("Customer rating (1-5): "))
                    if rating < 1 or rating > 5:
                        print("Rating must be between 1 and 5.")
                        continue
                except ValueError:
                    print("Enter a number 1-5.")
                    continue
                comment = input("Comment (press Enter to skip): ").strip()
                if name not in data:
                    data[name] = []
                data[name].append({"rating": rating, "comment": comment})
                _save_json(SENTIMENT_FILE, data)
                print("Feedback recorded.")
            elif choice == 2:
                name = check_business()
                if not name:
                    continue
                reviews = data.get(name, [])
                if not reviews:
                    print(f"No feedback recorded for {name} yet.")
                else:
                    ratings = [r["rating"] for r in reviews]
                    avg = sum(ratings) / len(ratings)
                    positive = sum(1 for r in ratings if r >= 4)
                    neutral = sum(1 for r in ratings if r == 3)
                    negative = sum(1 for r in ratings if r <= 2)
                    print(f"\n{'='*40}")
                    print(f"  SENTIMENT REPORT: {name.upper()}")
                    print(f"{'='*40}")
                    print(f"  Total Reviews:   {len(reviews)}")
                    print(f"  Average Rating:  {avg:.1f} / 5")
                    print(f"  Positive (4-5):  {positive}")
                    print(f"  Neutral  (3):    {neutral}")
                    print(f"  Negative (1-2):  {negative}")
                    comments = [r for r in reviews if r.get("comment")]
                    if comments:
                        print(f"\n  Recent Comments:")
                        for r in comments[-5:]:
                            print(f"    [{r['rating']}/5] {r['comment']}")
                    print(f"{'='*40}")
            elif choice == 3:
                is_running = False
            else:
                print("Enter 1-3.")
        except ValueError:
            print("Invalid input.")

#____CAMPAIGN TRACKER____
def campaign_tracker():
    data = _load_json(CAMPAIGN_FILE)
    is_running = True
    while is_running:
        print("\n--- CAMPAIGN TRACKER ---")
        print("1: Add Campaign")
        print("2: View Campaigns")
        print("3: Update Campaign Results")
        print("4: Back")
        try:
            choice = int(input("Option: "))
            if choice == 1:
                name = check_business()
                if not name:
                    continue
                campaign_name = input("Campaign name: ").title()
                platform = input("Platform (e.g. Instagram, Email, Flyer): ").title()
                try:
                    budget = float(input("Budget ($): "))
                except ValueError:
                    print("Invalid budget.")
                    continue
                start_date = input("Start date (DD/MM/YYYY): ").strip()
                if name not in data:
                    data[name] = []
                data[name].append({
                    "name": campaign_name,
                    "platform": platform,
                    "budget": budget,
                    "start_date": start_date,
                    "leads": 0,
                    "sales": 0,
                    "revenue": 0.0
                })
                _save_json(CAMPAIGN_FILE, data)
                print(f"Campaign '{campaign_name}' added.")
            elif choice == 2:
                name = check_business()
                if not name:
                    continue
                campaigns = data.get(name, [])
                if not campaigns:
                    print(f"No campaigns for {name}.")
                else:
                    print(f"\n{'='*40}")
                    print(f"  CAMPAIGNS: {name.upper()}")
                    print(f"{'='*40}")
                    for i, c in enumerate(campaigns, 1):
                        roi = ((c["revenue"] - c["budget"]) / c["budget"] * 100) if c["budget"] > 0 else 0
                        print(f"\n  {i}. {c['name']} | {c['platform']} | Started: {c['start_date']}")
                        print(f"     Budget: ${c['budget']:.2f}  Leads: {c['leads']}  Sales: {c['sales']}")
                        print(f"     Revenue: ${c['revenue']:.2f}  ROI: {roi:.1f}%")
                    print(f"{'='*40}")
            elif choice == 3:
                name = check_business()
                if not name:
                    continue
                campaigns = data.get(name, [])
                if not campaigns:
                    print("No campaigns to update.")
                    continue
                for i, c in enumerate(campaigns, 1):
                    print(f"  {i}. {c['name']} ({c['platform']})")
                try:
                    idx = int(input("Select campaign number: ")) - 1
                    if 0 <= idx < len(campaigns):
                        leads = int(input("Total leads generated: "))
                        sales = int(input("Total sales made: "))
                        revenue = float(input("Total revenue generated ($): "))
                        data[name][idx]["leads"] = leads
                        data[name][idx]["sales"] = sales
                        data[name][idx]["revenue"] = revenue
                        _save_json(CAMPAIGN_FILE, data)
                        roi = ((revenue - data[name][idx]["budget"]) / data[name][idx]["budget"] * 100) if data[name][idx]["budget"] > 0 else 0
                        print(f"Campaign updated. ROI: {roi:.1f}%")
                    else:
                        print("Invalid selection.")
                except ValueError:
                    print("Invalid input.")
            elif choice == 4:
                is_running = False
            else:
                print("Enter 1-4.")
        except ValueError:
            print("Invalid input.")

#____MAIN MENU____
def marketing_menu():
    is_running = True
    while is_running:
        print("\nWELCOME TO THE MARKETING MENU")
        print("-------------------------------")
        print("1: BASIC MARKETING TOOLS")
        print("2: MARKETING STRATEGIES AND ANALYSIS")
        print("3: REVENUE DATA")
        print("4: CAMPAIGN TRACKER")
        print("5: EXIT")

        try:
            option = int(input("\nPick an option from 1-5: "))
        except ValueError:
            print("Invalid input. Please enter a number.")
            continue

        if option == 1:
            while True:
                print("\nMARKETING TOOLS")
                print("1: CREATE MARKETING IMAGE")
                print("2: CREATE MARKETING CAPTION")
                print("3: MARKETING PLAN")
                print("4: BACK")
                try:
                    selection = int(input("Pick tool (1-4): "))
                    if selection == 1:
                        name = check_business()
                        if name:
                            industry, location, targetcustomer = get_business_info()
                            create_image(name, industry, location, targetcustomer)
                    elif selection == 2:
                        name = check_business()
                        if name:
                            industry, location, targetcustomer = get_business_info()
                            create_caption(name, industry, location, targetcustomer)
                    elif selection == 3:
                        marketing_plan()
                    elif selection == 4:
                        break
                    else:
                        print("Enter 1-4.")
                except ValueError:
                    print("Invalid input.")

        elif option == 2:
            while True:
                print("\nMARKETING ANALYSIS")
                print("1: PRICE MONITOR")
                print("2: CUSTOMER MAPPING")
                print("3: KEYWORD TRACKER")
                print("4: PRODUCT ANALYSIS")
                print("5: BACK")
                try:
                    selection = int(input("Pick analysis (1-5): "))
                    if selection == 1:
                        price_monitor()
                    elif selection == 2:
                        customer_mapping()
                    elif selection == 3:
                        key_word_identifier()
                    elif selection == 4:
                        product_analysis()
                    elif selection == 5:
                        break
                    else:
                        print("Enter 1-5.")
                except ValueError:
                    print("Invalid input.")

        elif option == 3:
            while True:
                print("\nREVENUE DATA")
                print("1: EXPENDITURE & REVENUE")
                print("2: SENTIMENT TRACKER")
                print("3: BACK")
                try:
                    selection = int(input("Select option (1-3): "))
                    if selection == 1:
                        spend_and_revenue()
                    elif selection == 2:
                        sentiment_tracker()
                    elif selection == 3:
                        break
                    else:
                        print("Enter 1-3.")
                except ValueError:
                    print("Invalid input.")

        elif option == 4:
            campaign_tracker()

        elif option == 5:
            print("Exiting Marketing Module...")
            is_running = False
        else:
            print("Pick between 1-5.")
