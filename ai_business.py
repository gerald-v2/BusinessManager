import api_handler
import business_manager
import business_finance
import crm
import Pos
import employees
import marketing


class AIBusiness:

    def __init__(self, business_name):
        self.business_name = business_name


    # BUSINESS


    def get_business_info(self):
        businesses = business_manager.load_business()

        return businesses.get(self.business_name, {})


    # SALES


    def get_sales(self):
        sales = Pos.load_sales()

        return sales.get(self.business_name, [])

    # INVENTORY

    def get_inventory(self):
        businesses = business_manager.load_business()

        return businesses.get(
            self.business_name,
            {}
        ).get("products", {})

    def get_low_stock(self):
        businesses = business_manager.load_business()
        print("BUSINESS KEYS:")
        print(businesses.keys())
        return business_manager.low_stock_report(
            self.business_name
        )

    def get_best_sellers(self):
        return business_manager.best_sellers(
            self.business_name
        )


    # FINANCE

    def get_financial_data(self):
        finance = business_finance.load_business_finance()

        return finance.get(
            self.business_name,
            {}
        )


    # CRM

    def get_customers(self):

        customers = crm.load_customers()

        return customers.get(
            self.business_name,
            []
        )


    # EMPLOYEES

    def get_employees(self):
        employees_data = employees._load_employees()

        return employees_data.get(
            self.business_name,
            []
        )
    # MARKETING

    def set_marketing_objectives(self):

        result = {
            "Business ID": self.business_name,
            "Products": [],
            "Sales": [],
            "Pricing": [],
            "Business Info": {}
        }

        # PRODUCT DATA
        product_data = business_manager.load_business()
        product_business = product_data.get(self.business_name, {})

        products = product_business.get("products", {})

        for product_name, product_details in products.items():
            result["Products"].append({
                "Product Name": product_name,
                "Price": product_details.get("Price"),
                "Cost": product_details.get("Cost"),
                "Variants": product_details.get("variants", [])
            })

        # SALES DATA
        promotional_data = Pos.load_sales()
        promotional_business = promotional_data.get(self.business_name, [])

        for sale in promotional_business:
            result["Sales"].append(sale)

        # BUSINESS INFORMATION
        industry, location, targetcustomer = marketing.get_business_info()

        result["Business Info"] = {
            "Industry": industry,
            "Location": location,
            "Target Customer": targetcustomer
        }

        return result


    def get_sales_last_7_days(self):
        return Pos.get_sales_last_n_days(self.business_name, 7)

    def get_sales_last_14_days(self):
        return Pos.get_sales_last_n_days(self.business_name, 14)

    def get_sales_last_30_days(self):
        return Pos.get_sales_last_n_days(self.business_name, 30)

    #PROMPT

    def ask(self, user_message):

        business_data = self.get_business_context()

        return api_handler.ask_business_ai(
            user_message,
            business_data
        )

    def get_business_context(self):

        return {
            "business": self.get_business_info(),

            "sales": {
                "last_7_days": self.get_sales_last_7_days(),
                "last_30_days": self.get_sales_last_30_days()
            },

            "inventory": self.get_inventory(),

            "low_stock": self.get_low_stock(),

            "best_sellers": self.get_best_sellers(),

            "finance": self.get_financial_data(),

            "customers": self.get_customers(),

            "employees": self.get_employees()
        }
ai = AIBusiness("Apple")

