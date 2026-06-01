import os
import sys
import json
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from flask import (Flask, render_template, redirect, url_for,
                   request, session, flash)

import business_manager as bm
import business_finance as bf
import crm as crm_mod
import Pos as pos_mod
import business_login as bl
import login as sys_login
import api_handler

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'biz_program_secret_key_2026')

# Register enumerate as a Jinja2 filter so templates can use: list | enumerate
app.jinja_env.filters['enumerate'] = enumerate

# ── DATA HELPERS ─────────────────────────────────────────────────────────────

def _load_biz():
    businesses = bm.load_business()
    bm.businesses = businesses
    return businesses

def _load_finance():
    bf.business_finance = bf.load_business_finance()
    return bf.business_finance

def _sym(biz):
    businesses = _load_biz()
    return bm.get_currency_symbol(bm.get_business_currency(biz))

# ── AUTH HELPERS ──────────────────────────────────────────────────────────────

def _require_login():
    if not session.get('user_type'):
        flash('Please log in first.', 'warning')
        return redirect(url_for('portal'))
    return None

def _require_biz_access(biz):
    r = _require_login()
    if r:
        return r
    ut = session.get('user_type')
    if ut == 'system_admin':
        return None
    if session.get('biz') != biz:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    return None

def _can_access(biz, module):
    ut = session.get('user_type')
    if ut in ('system_admin', 'system_business', 'biz_admin'):
        return True
    if ut == 'biz_staff' and session.get('biz') == biz:
        return module in session.get('permissions', [])
    return False

def _is_manager(biz=None):
    ut = session.get('user_type')
    if ut in ('system_admin', 'system_business'):
        return True
    if ut == 'biz_admin':
        return biz is None or session.get('biz') == biz
    return False

@app.context_processor
def inject_globals():
    return {'can_access': _can_access, 'is_manager': _is_manager, 'enumerate': enumerate}

# ── PORTAL & AUTH ─────────────────────────────────────────────────────────────

@app.route('/')
def portal():
    if session.get('user_type'):
        return redirect(url_for('dashboard'))
    return render_template('portal.html')

@app.route('/system-login', methods=['GET', 'POST'])
def system_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()
        accounts = sys_login.load_accounts()
        if not accounts:
            sys_login.first_time_setup()
            accounts = sys_login.load_accounts()
        if username in accounts and accounts[username]['password'] == password:
            acc = accounts[username]
            session.clear()
            session['user_type'] = 'system_admin' if acc['role'] == 'admin' else 'system_business'
            session['username'] = username
            session['linked_businesses'] = acc.get('businesses', [])
            flash(f'Welcome, {username.upper()}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Incorrect username or password.', 'danger')
    return render_template('login.html', mode='system', biz_list=[])

@app.route('/business-login', methods=['GET', 'POST'])
def business_login_route():
    businesses = _load_biz()
    biz_list = list(businesses.keys())
    if not biz_list:
        flash('No businesses found. Use System Login to create one first.', 'warning')
        return redirect(url_for('portal'))
    if request.method == 'POST':
        biz = request.form.get('biz', '').strip()
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()
        if biz not in businesses:
            flash('Business not found.', 'danger')
            return render_template('login.html', mode='business', biz_list=biz_list)
        admin = bl.get_business_admin(biz)
        if not admin:
            flash(f'No manager account set for {biz}. Use System Login → Manager Settings to create one.', 'warning')
            return render_template('login.html', mode='business', biz_list=biz_list)
        if username == admin['username'] and password == admin['password']:
            session.clear()
            session['user_type'] = 'biz_admin'
            session['username'] = username
            session['biz'] = biz
            flash(f'Welcome, {username.upper()} (Manager)', 'success')
            return redirect(url_for('biz_dashboard', biz=biz))
        emps = bf.load_employees().get(biz, [])
        for emp in emps:
            if (emp.get('username') or '').lower() == username and (emp.get('password') or '') == password:
                session.clear()
                session['user_type'] = 'biz_staff'
                session['username'] = username
                session['biz'] = biz
                session['emp_name'] = emp['name']
                session['permissions'] = emp.get('permissions', [])
                bl.record_login_attendance(biz, emp['name'])
                flash(f'Welcome, {emp["name"]}!', 'success')
                return redirect(url_for('biz_dashboard', biz=biz))
        flash('Incorrect credentials.', 'danger')
    return render_template('login.html', mode='business', biz_list=biz_list)

@app.route('/logout')
def logout():
    biz = session.get('biz')
    emp = session.get('emp_name')
    if biz and emp:
        bl.clock_out_on_logout(biz, emp)
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('portal'))

# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@app.route('/dashboard')
def dashboard():
    r = _require_login()
    if r:
        return r
    ut = session.get('user_type')
    if ut == 'system_admin':
        businesses = _load_biz()
        _load_finance()
        stats = {}
        for name in businesses:
            fin = bf.business_finance.get(name, {})
            rev = fin.get('Revenue', 0) or 0
            costs = fin.get('Costs', 0) or 0
            payroll = bf.get_monthly_payroll(name)
            stats[name] = {
                'revenue': rev, 'costs': costs,
                'profit': rev - costs - payroll,
                'products': len(businesses[name].get('products', {})),
                'sym': bm.get_currency_symbol(bm.get_business_currency(name)),
            }
        return render_template('admin_dashboard.html', businesses=businesses, stats=stats)
    if ut == 'system_business':
        linked = session.get('linked_businesses', [])
        businesses = _load_biz()
        valid = [b for b in linked if b in businesses]
        if not valid:
            flash('No businesses linked to your account.', 'warning')
            return render_template('portal.html')
        if len(valid) == 1:
            session['biz'] = valid[0]
            return redirect(url_for('biz_dashboard', biz=valid[0]))
        return render_template('biz_select.html', businesses=valid)
    biz = session.get('biz')
    if biz:
        return redirect(url_for('biz_dashboard', biz=biz))
    return redirect(url_for('portal'))

@app.route('/select/<biz>')
def select_biz(biz):
    r = _require_login()
    if r:
        return r
    linked = session.get('linked_businesses', [])
    if biz in linked or session.get('user_type') == 'system_admin':
        session['biz'] = biz
    return redirect(url_for('biz_dashboard', biz=biz))

@app.route('/biz/<biz>')
def biz_dashboard(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    businesses = _load_biz()
    _load_finance()
    if biz not in businesses:
        flash('Business not found.', 'danger')
        return redirect(url_for('dashboard'))
    fin = bf.business_finance.get(biz, {})
    revenue = fin.get('Revenue', 0) or 0
    costs = fin.get('Costs', 0) or 0
    payroll = bf.get_monthly_payroll(biz)
    profit = revenue - costs - payroll
    sym = _sym(biz)
    products = businesses[biz].get('products', {})
    low_stock = []
    for p_name, details in products.items():
        for v in details.get('variants', []):
            if v.get('units', 0) < 5:
                low_stock.append({'product': p_name, 'variant': v['name'], 'units': v.get('units', 0)})
    biz_sales = pos_mod.load_sales().get(biz, [])
    recent_sales = list(reversed(biz_sales))[:5]

    # ── SALES CHART: last 30 days ─────────────────────────────────────────────
    today = datetime.date.today()
    chart_days = request.args.get('chart_days', '7')
    chart_days = 30 if chart_days == '30' else 7
    chart_labels = []
    chart_data = []
    for i in range(chart_days - 1, -1, -1):
        d = today - datetime.timedelta(days=i)
        label = d.strftime('%d %b')
        day_total = sum(
            s.get('total', 0) for s in biz_sales
            if s.get('date') == d.strftime('%Y-%m-%d') and not s.get('refunded')
        )
        chart_labels.append(label)
        chart_data.append(round(day_total, 2))

    # ── BIRTHDAY ALERTS: customers with birthday this week ───────────────────
    birthday_alerts = []
    try:
        raw_customers = crm_mod._load_raw().get(biz, [])
        this_month = today.month
        this_day   = today.day
        for c in raw_customers:
            dob = c.get('dob', '')
            if not dob:
                continue
            try:
                parts = dob.split('-')
                if len(parts) == 3:
                    bday_month = int(parts[1])
                    bday_day   = int(parts[2])
                    days_until = (datetime.date(today.year, bday_month, bday_day) - today).days
                    if days_until < 0:
                        days_until = (datetime.date(today.year + 1, bday_month, bday_day) - today).days
                    if 0 <= days_until <= 7:
                        birthday_alerts.append({
                            'name': c['name'],
                            'phone': c.get('phone', ''),
                            'days_until': days_until,
                            'label': 'Today! 🎂' if days_until == 0 else f'In {days_until} day{"s" if days_until > 1 else ""}'
                        })
            except Exception:
                continue
        birthday_alerts.sort(key=lambda x: x['days_until'])
    except Exception:
        birthday_alerts = []

    return render_template('dashboard.html', biz=biz, biz_data=businesses[biz],
                           revenue=revenue, costs=costs, profit=profit, payroll=payroll,
                           sym=sym, low_stock=low_stock, recent_sales=recent_sales,
                           products=products, chart_labels=chart_labels,
                           chart_data=chart_data, chart_days=chart_days,
                           birthday_alerts=birthday_alerts)

# ── DAILY SUMMARY ─────────────────────────────────────────────────────────────

@app.route('/biz/<biz>/daily-summary')
def daily_summary(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    businesses = _load_biz()
    _load_finance()
    if biz not in businesses:
        flash('Business not found.', 'danger')
        return redirect(url_for('dashboard'))
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    sym = _sym(biz)
    all_sales = pos_mod.load_sales().get(biz, [])
    # Today's sales
    today_sales = [s for s in all_sales if s.get('date') == today.strftime('%Y-%m-%d') and not s.get('refunded')]
    yest_sales  = [s for s in all_sales if s.get('date') == yesterday.strftime('%Y-%m-%d') and not s.get('refunded')]
    today_rev  = sum(s.get('total', 0) for s in today_sales)
    yest_rev   = sum(s.get('total', 0) for s in yest_sales)
    # Top products today
    product_totals = {}
    for s in today_sales:
        for item in s.get('items', []):
            key = item.get('product', 'Unknown')
            product_totals[key] = product_totals.get(key, 0) + item.get('subtotal', 0)
    top_products = sorted(product_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    # Finance snapshot
    fin = bf.business_finance.get(biz, {})
    revenue = fin.get('Revenue', 0) or 0
    costs   = fin.get('Costs', 0) or 0
    payroll = bf.get_monthly_payroll(biz)
    profit  = revenue - costs - payroll
    # Low stock
    products = businesses[biz].get('products', {})
    low_stock = []
    for p_name, details in products.items():
        for v in details.get('variants', []):
            if v.get('units', 0) < 5:
                low_stock.append({'product': p_name, 'variant': v['name'], 'units': v.get('units', 0)})
    # Birthday alerts
    birthday_alerts = []
    try:
        for c in crm_mod._load_raw().get(biz, []):
            dob = c.get('dob', '')
            if not dob:
                continue
            parts = dob.split('-')
            if len(parts) == 3:
                days_until = (datetime.date(today.year, int(parts[1]), int(parts[2])) - today).days
                if days_until < 0:
                    days_until += 365
                if 0 <= days_until <= 7:
                    birthday_alerts.append({'name': c['name'], 'phone': c.get('phone',''), 'days_until': days_until})
    except Exception:
        pass
    rev_change = ((today_rev - yest_rev) / yest_rev * 100) if yest_rev > 0 else None
    return render_template('daily_summary.html', biz=biz, sym=sym,
                           today=today.strftime('%A, %d %B %Y'),
                           today_rev=today_rev, yest_rev=yest_rev,
                           today_count=len(today_sales), yest_count=len(yest_sales),
                           rev_change=rev_change, top_products=top_products,
                           revenue=revenue, costs=costs, profit=profit,
                           low_stock=low_stock, birthday_alerts=birthday_alerts,
                           biz_data=businesses[biz])

# ── PRODUCTS ──────────────────────────────────────────────────────────────────

@app.route('/biz/<biz>/products')
def products(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'products'):
        flash('You do not have access to Products.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    businesses = _load_biz()
    sym = _sym(biz)
    prods = businesses.get(biz, {}).get('products', {})
    return render_template('products.html', biz=biz, products=prods, sym=sym)

@app.route('/biz/<biz>/products/add', methods=['POST'])
def add_product(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'products'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    businesses = _load_biz()
    name = request.form.get('product_name', '').strip().title()
    price_str = request.form.get('price', '0').strip()
    cost_str = request.form.get('cost', '0').strip()
    if not name:
        flash('Product name is required.', 'danger')
        return redirect(url_for('products', biz=biz))
    if name in businesses.get(biz, {}).get('products', {}):
        flash(f'"{name}" already exists.', 'warning')
        return redirect(url_for('products', biz=biz))
    try:
        price_f = float(price_str)
        cost_f = float(cost_str)
    except ValueError:
        flash('Invalid price or cost.', 'danger')
        return redirect(url_for('products', biz=biz))
    businesses[biz]['products'][name] = {
        'Price': f'${price_f:.2f}', 'Cost': f'${cost_f:.2f}', 'variants': []
    }
    bm.store_business()
    bm.export_to_csv(biz)
    flash(f'Product "{name}" added.', 'success')
    return redirect(url_for('products', biz=biz))

@app.route('/biz/<biz>/products/<product>/add-variant', methods=['POST'])
def add_variant(biz, product):
    r = _require_biz_access(biz)
    if r:
        return r
    businesses = _load_biz()
    v_name = request.form.get('variant_name', '').strip().title()
    plu = request.form.get('plu', '').strip()
    units_str = request.form.get('units', '0').strip()
    if not v_name or not plu:
        flash('Variant name and PLU are required.', 'danger')
        return redirect(url_for('products', biz=biz))
    owner = bm.find_plu_owner(biz, plu)
    if owner:
        flash(f'PLU {plu} already used by: {owner}', 'danger')
        return redirect(url_for('products', biz=biz))
    try:
        units = int(units_str)
    except ValueError:
        flash('Units must be a whole number.', 'danger')
        return redirect(url_for('products', biz=biz))
    businesses[biz]['products'][product]['variants'].append(
        {'name': v_name, 'units': units, 'PLU': plu, 'sold': 0}
    )
    bm.store_business()
    bm.export_to_csv(biz)
    cost_str = str(businesses[biz]['products'][product].get('Cost', '0')).replace('$', '').strip()
    try:
        _load_finance()
        bf.add_costs(biz, float(cost_str) * units, f'{product} stock ({v_name}, {units} units)')
    except Exception:
        pass
    flash(f'Variant "{v_name}" [PLU:{plu}] added.', 'success')
    return redirect(url_for('products', biz=biz))

@app.route('/biz/<biz>/products/<product>/edit-variant', methods=['POST'])
def edit_variant(biz, product):
    r = _require_biz_access(biz)
    if r:
        return r
    businesses = _load_biz()
    v_name = request.form.get('variant_name', '').strip()
    field = request.form.get('field', '').strip()
    value = request.form.get('value', '').strip()
    prods = businesses.get(biz, {}).get('products', {})
    if product not in prods:
        flash('Product not found.', 'danger')
        return redirect(url_for('products', biz=biz))
    variants = prods[product].get('variants', [])
    target = next((v for v in variants if v['name'] == v_name), None)
    if not target:
        flash('Variant not found.', 'danger')
        return redirect(url_for('products', biz=biz))
    ok = True
    if field == 'units':
        try:
            target['units'] = int(value)
        except ValueError:
            flash('Invalid units.', 'danger')
            ok = False
    elif field == 'price':
        try:
            prods[product]['Price'] = f'${float(value):.2f}'
        except ValueError:
            flash('Invalid price.', 'danger')
            ok = False
    elif field == 'cost':
        try:
            prods[product]['Cost'] = f'${float(value):.2f}'
        except ValueError:
            flash('Invalid cost.', 'danger')
            ok = False
    elif field == 'plu':
        owner = bm.find_plu_owner(biz, value, skip_product=product, skip_variant=v_name)
        if owner:
            flash(f'PLU {value} already used by {owner}.', 'danger')
            ok = False
        else:
            target['PLU'] = value
    elif field == 'name':
        target['name'] = value.title()
    if ok:
        bm.store_business()
        bm.export_to_csv(biz)
        flash('Updated successfully.', 'success')
    return redirect(url_for('products', biz=biz))

@app.route('/biz/<biz>/products/<product>/remove', methods=['POST'])
def remove_product(biz, product):
    r = _require_biz_access(biz)
    if r:
        return r
    businesses = _load_biz()
    if product in businesses.get(biz, {}).get('products', {}):
        del businesses[biz]['products'][product]
        bm.store_business()
        bm.export_to_csv(biz)
        flash(f'"{product}" removed.', 'success')
    else:
        flash('Product not found.', 'danger')
    return redirect(url_for('products', biz=biz))

@app.route('/biz/<biz>/products/<product>/<variant>/remove', methods=['POST'])
def remove_variant_route(biz, product, variant):
    r = _require_biz_access(biz)
    if r:
        return r
    businesses = _load_biz()
    variants = businesses.get(biz, {}).get('products', {}).get(product, {}).get('variants', [])
    before = len(variants)
    businesses[biz]['products'][product]['variants'] = [v for v in variants if v['name'] != variant]
    if len(businesses[biz]['products'][product]['variants']) < before:
        bm.store_business()
        bm.export_to_csv(biz)
        flash(f'Variant "{variant}" removed.', 'success')
    return redirect(url_for('products', biz=biz))

# ── POS ───────────────────────────────────────────────────────────────────────

@app.route('/biz/<biz>/pos')
def pos(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'pos'):
        flash('You do not have access to POS.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    businesses = _load_biz()
    prods = businesses.get(biz, {}).get('products', {})
    sym = _sym(biz)
    cart = session.get(f'cart_{biz}', {})
    active_customer = session.get(f'customer_{biz}')
    subtotal = sum(item['subtotal'] for item in cart.values())
    pts_enabled = crm_mod.points_enabled(biz)
    tier = crm_mod.get_eligible_discount(biz, active_customer) if active_customer and pts_enabled else None
    return render_template('pos.html', biz=biz, products=prods, sym=sym, cart=cart,
                           subtotal=subtotal, active_customer=active_customer,
                           pts_enabled=pts_enabled, tier=tier)

@app.route('/biz/<biz>/pos/lookup', methods=['POST'])
def pos_lookup(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    plu = request.form.get('plu', '').strip()
    qty_str = request.form.get('qty', '1').strip()
    item = pos_mod.product_lookup(biz, plu)
    if not item:
        flash(f'PLU "{plu}" not found.', 'danger')
        return redirect(url_for('pos', biz=biz))
    try:
        qty = max(1, int(qty_str))
    except ValueError:
        qty = 1
    if qty > item['stock']:
        flash(f'Only {item["stock"]} units in stock.', 'warning')
        return redirect(url_for('pos', biz=biz))
    cart = session.get(f'cart_{biz}', {})
    key = item['plu']
    if key in cart:
        new_qty = cart[key]['qty'] + qty
        if new_qty > item['stock']:
            flash(f'Cannot add more — only {item["stock"]} in stock total.', 'warning')
            return redirect(url_for('pos', biz=biz))
        cart[key]['qty'] = new_qty
        cart[key]['subtotal'] = round(cart[key]['unit_price'] * new_qty, 2)
    else:
        cart[key] = {
            'product': item['product'], 'variant': item['variant'],
            'plu': key, 'qty': qty,
            'unit_price': item['unit_price'],
            'subtotal': round(item['unit_price'] * qty, 2)
        }
    session[f'cart_{biz}'] = cart
    flash(f'Added {item["product"]} ({item["variant"]}) ×{qty}.', 'success')
    return redirect(url_for('pos', biz=biz))

@app.route('/biz/<biz>/pos/add-browse', methods=['POST'])
def pos_add_browse(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    product = request.form.get('product', '').strip()
    variant = request.form.get('variant', '').strip()
    plu = request.form.get('plu', '').strip()
    qty_str = request.form.get('qty', '1').strip()
    price_str = request.form.get('price', '0').strip()
    stock_str = request.form.get('stock', '0').strip()
    try:
        qty = max(1, int(qty_str))
        price = float(price_str)
        stock = int(stock_str)
    except ValueError:
        flash('Invalid input.', 'danger')
        return redirect(url_for('pos', biz=biz))
    if qty > stock:
        flash(f'Only {stock} units in stock.', 'warning')
        return redirect(url_for('pos', biz=biz))
    cart = session.get(f'cart_{biz}', {})
    key = plu
    if key in cart:
        new_qty = cart[key]['qty'] + qty
        if new_qty > stock:
            flash(f'Cannot add more — only {stock} in stock.', 'warning')
            return redirect(url_for('pos', biz=biz))
        cart[key]['qty'] = new_qty
        cart[key]['subtotal'] = round(price * new_qty, 2)
    else:
        cart[key] = {
            'product': product, 'variant': variant,
            'plu': plu, 'qty': qty,
            'unit_price': price,
            'subtotal': round(price * qty, 2)
        }
    session[f'cart_{biz}'] = cart
    flash(f'Added {product} ({variant}) ×{qty}.', 'success')
    return redirect(url_for('pos', biz=biz))

@app.route('/biz/<biz>/pos/remove/<plu>', methods=['POST'])
def pos_remove(biz, plu):
    r = _require_biz_access(biz)
    if r:
        return r
    cart = session.get(f'cart_{biz}', {})
    if plu in cart:
        removed = cart.pop(plu)
        session[f'cart_{biz}'] = cart
        flash(f'Removed {removed["product"]} ({removed["variant"]}).', 'info')
    return redirect(url_for('pos', biz=biz))

@app.route('/biz/<biz>/pos/clear', methods=['POST'])
def pos_clear(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    session.pop(f'cart_{biz}', None)
    session.pop(f'customer_{biz}', None)
    flash('Cart cleared.', 'info')
    return redirect(url_for('pos', biz=biz))

@app.route('/biz/<biz>/pos/link-customer', methods=['POST'])
def pos_link_customer(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    query = request.form.get('query', '').strip()
    if not query:
        session.pop(f'customer_{biz}', None)
        flash('Customer unlinked.', 'info')
        return redirect(url_for('pos', biz=biz))
    results = crm_mod.find_customer(biz, query)
    if not results:
        flash('No customers found.', 'warning')
    else:
        session[f'customer_{biz}'] = results[0]
        flash(f'Linked: {results[0]["name"]}', 'success')
    return redirect(url_for('pos', biz=biz))

@app.route('/biz/<biz>/pos/checkout', methods=['GET', 'POST'])
def pos_checkout(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'pos'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    cart = session.get(f'cart_{biz}', {})
    if not cart:
        flash('Cart is empty.', 'warning')
        return redirect(url_for('pos', biz=biz))
    sym = _sym(biz)
    active_customer = session.get(f'customer_{biz}')
    subtotal = sum(item['subtotal'] for item in cart.values())
    pts_enabled = crm_mod.points_enabled(biz)
    tier = crm_mod.get_eligible_discount(biz, active_customer) if active_customer and pts_enabled else None

    # ── MULTI-CURRENCY: compute ZWG equivalent ───────────────────────────────
    biz_currency = bm.get_business_currency(biz)
    exchange_rates = bf.load_exchange_rates()
    alt_currency = None
    alt_sym = None
    alt_rate = None
    alt_subtotal = None
    if biz_currency == 'USD':
        usd_to_zwg = exchange_rates.get('USD_TO_ZWG')
        if usd_to_zwg:
            alt_currency = 'ZWG'
            alt_sym = bm.get_currency_symbol('ZWG')
            alt_rate = usd_to_zwg
            alt_subtotal = round(subtotal * usd_to_zwg, 2)
    elif biz_currency == 'ZWG':
        zwg_to_usd = exchange_rates.get('ZWG_TO_USD')
        if zwg_to_usd:
            alt_currency = 'USD'
            alt_sym = '$'
            alt_rate = zwg_to_usd
            alt_subtotal = round(subtotal * zwg_to_usd, 2)

    if request.method == 'GET':
        return render_template('pos_checkout.html', biz=biz, cart=cart, sym=sym,
                               subtotal=subtotal, active_customer=active_customer,
                               pts_enabled=pts_enabled, tier=tier,
                               alt_currency=alt_currency, alt_sym=alt_sym,
                               alt_rate=alt_rate, alt_subtotal=alt_subtotal,
                               biz_currency=biz_currency)
    # POST — process payment
    use_points = request.form.get('use_points') == 'yes' and tier is not None
    manual_disc = request.form.get('manual_discount_pct', '0').strip()
    tax_pct_str = request.form.get('tax_pct', '0').strip()
    payment_method = request.form.get('payment_method', 'Cash').strip()
    payment_amt_str = request.form.get('payment_amount', '0').strip()
    pay_currency = request.form.get('pay_currency', biz_currency).strip()
    try:
        disc_pct = tier['discount_pct'] if use_points else float(manual_disc)
    except (ValueError, TypeError):
        disc_pct = 0.0
    try:
        tax_pct = float(tax_pct_str)
    except ValueError:
        tax_pct = 0.0
    disc_amt = round(subtotal * disc_pct / 100, 2)
    after_disc = subtotal - disc_amt
    tax_amt = round(after_disc * tax_pct / 100, 2)
    total = round(after_disc + tax_amt, 2)
    try:
        payment_amt = float(payment_amt_str)
    except ValueError:
        payment_amt = total
    change = round(payment_amt - total, 2) if payment_method == 'Cash' and payment_amt >= total else 0.0
    # Record items
    _load_finance()
    for item in cart.values():
        pos_mod.record_sale(biz, item['product'], item['variant'], item['qty'])
    # Points
    points_redeemed = 0
    points_earned = 0
    if active_customer and pts_enabled:
        if use_points and tier:
            crm_mod.deduct_points(biz, active_customer['name'], tier['points'])
            points_redeemed = tier['points']
        points_earned = crm_mod.award_points(biz, active_customer['name'], total)
    if active_customer:
        crm_mod.log_purchase_to_customer(biz, active_customer['name'],
                                         list(cart.values()), total, points_earned)
    # Save sale
    sales = pos_mod.load_sales()
    if biz not in sales:
        sales[biz] = []
    now = datetime.datetime.now()
    sale_record = {
        'date': now.strftime('%Y-%m-%d'), 'time': now.strftime('%H:%M'),
        'items': list(cart.values()),
        'subtotal': subtotal, 'discount_pct': disc_pct, 'discount_amt': disc_amt,
        'tax_pct': tax_pct, 'tax_amt': tax_amt,
        'total': total, 'payment': payment_method,
        'payment_amount': payment_amt, 'change': change,
        'customer': active_customer['name'] if active_customer else None,
        'points_earned': points_earned, 'points_redeemed': points_redeemed,
        'refunded': False,
    }
    sales[biz].append(sale_record)
    pos_mod.save_sales(sales)
    updated_customer = None
    if active_customer:
        results = crm_mod.find_customer(biz, active_customer['name'])
        if results:
            updated_customer = results[0]
    cart_items = list(cart.values())
    session.pop(f'cart_{biz}', None)
    session.pop(f'customer_{biz}', None)
    return render_template('pos_receipt.html', biz=biz, sale=sale_record, sym=sym,
                           customer=updated_customer, cart_items=cart_items,
                           points_earned=points_earned, points_redeemed=points_redeemed)

@app.route('/biz/<biz>/pos/sales')
def pos_sales(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'pos'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    sales = pos_mod.load_sales().get(biz, [])
    sym = _sym(biz)
    return render_template('pos_sales.html', biz=biz, sales=list(reversed(sales)), sym=sym)

@app.route('/biz/<biz>/pos/refund/<int:display_idx>', methods=['POST'])
def pos_refund(biz, display_idx):
    r = _require_biz_access(biz)
    if r:
        return r
    sales_data = pos_mod.load_sales()
    biz_sales = sales_data.get(biz, [])
    real_idx = len(biz_sales) - 1 - display_idx
    if 0 <= real_idx < len(biz_sales):
        sale = biz_sales[real_idx]
        if sale.get('refunded'):
            flash('Sale already refunded.', 'warning')
        else:
            _load_finance()
            businesses = _load_biz()
            for item in sale.get('items', []):
                for p_name, details in businesses.get(biz, {}).get('products', {}).items():
                    if p_name == item['product']:
                        for v in details.get('variants', []):
                            if v['name'] == item['variant']:
                                v['units'] += item['qty']
                                v['sold'] = max(0, v.get('sold', 0) - item['qty'])
            bm.store_business()
            fin = bf.business_finance.get(biz, {'Revenue': 0, 'Costs': 0})
            fin['Revenue'] = max(0, (fin.get('Revenue', 0) or 0) - sale['total'])
            bf.business_finance[biz] = fin
            bf.update_save_finance(biz)
            biz_sales[real_idx]['refunded'] = True
            pos_mod.save_sales(sales_data)
            flash(f'Refund of {_sym(biz)}{sale["total"]:.2f} processed.', 'success')
    else:
        flash('Sale not found.', 'danger')
    return redirect(url_for('pos_sales', biz=biz))

# ── FINANCE ───────────────────────────────────────────────────────────────────

@app.route('/biz/<biz>/finance')
def finance(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'finance'):
        flash('You do not have access to Finance.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    _load_finance()
    sym = _sym(biz)
    fin = bf.business_finance.get(biz, {})
    revenue = fin.get('Revenue', 0) or 0
    costs = fin.get('Costs', 0) or 0
    payroll = bf.get_monthly_payroll(biz)
    total_costs = costs + payroll
    profit = revenue - total_costs
    margin = (profit / revenue * 100) if revenue > 0 else 0
    rates = bf.load_exchange_rates()
    businesses = _load_biz()
    curr = bm.get_business_currency(biz)
    return render_template('finance.html', biz=biz, sym=sym, curr=curr,
                           revenue=revenue, costs=costs, payroll=payroll,
                           total_costs=total_costs, profit=profit, margin=margin,
                           rates=rates)

@app.route('/biz/<biz>/finance/add-cost', methods=['POST'])
def add_cost(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    try:
        amount = float(request.form.get('amount', '0'))
        if amount <= 0:
            raise ValueError
    except ValueError:
        flash('Enter a valid positive amount.', 'danger')
        return redirect(url_for('finance', biz=biz))
    desc = request.form.get('description', '').strip()
    _load_finance()
    bf.add_costs(biz, amount, desc)
    flash(f'Cost of {_sym(biz)}{amount:.2f} recorded.', 'success')
    return redirect(url_for('finance', biz=biz))

@app.route('/biz/<biz>/finance/add-rate', methods=['POST'])
def add_exchange_rate(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    from_c = request.form.get('from_curr', '').strip().upper()
    to_c = request.form.get('to_curr', '').strip().upper()
    try:
        rate = float(request.form.get('rate', '0'))
        if rate <= 0:
            raise ValueError
    except ValueError:
        flash('Invalid rate.', 'danger')
        return redirect(url_for('finance', biz=biz))
    rates = bf.load_exchange_rates()
    rates[f'{from_c}_TO_{to_c}'] = rate
    bf.save_exchange_rates(rates)
    flash(f'Rate saved: 1 {from_c} = {rate} {to_c}', 'success')
    return redirect(url_for('finance', biz=biz))

# ── CRM ───────────────────────────────────────────────────────────────────────

@app.route('/biz/<biz>/crm')
def crm(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'crm'):
        flash('You do not have access to CRM.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    _load_biz()
    raw = crm_mod._load_raw()
    customers = raw.get(biz, [])
    sym = _sym(biz)
    pts_enabled = crm_mod.points_enabled(biz)
    return render_template('crm.html', biz=biz, customers=customers, sym=sym, pts_enabled=pts_enabled)

@app.route('/biz/<biz>/crm/add', methods=['POST'])
def crm_add(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    name = request.form.get('name', '').strip().title()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    notes = request.form.get('notes', '').strip()
    dob   = request.form.get('dob', '').strip()
    if not name:
        flash('Name is required.', 'danger')
        return redirect(url_for('crm', biz=biz))
    raw = crm_mod._load_raw()
    if biz not in raw:
        raw[biz] = []
    if any(c['name'] == name for c in raw[biz]):
        flash(f'"{name}" already exists.', 'warning')
        return redirect(url_for('crm', biz=biz))
    raw[biz].append({
        'name': name, 'phone': phone, 'email': email, 'notes': notes,
        'dob': dob,
        'joined': datetime.datetime.now().strftime('%Y-%m-%d'),
        'points': 0, 'purchases': []
    })
    crm_mod._save_raw(raw)
    flash(f'"{name}" added.', 'success')
    return redirect(url_for('crm', biz=biz))

@app.route('/biz/<biz>/crm/<int:idx>')
def crm_profile(biz, idx):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'crm'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    _load_biz()
    raw = crm_mod._load_raw()
    customers = raw.get(biz, [])
    if not (0 <= idx < len(customers)):
        flash('Customer not found.', 'danger')
        return redirect(url_for('crm', biz=biz))
    customer = customers[idx]
    sym = _sym(biz)
    pts_enabled = crm_mod.points_enabled(biz)
    tier = crm_mod.get_eligible_discount(biz, customer) if pts_enabled else None
    next_tier = crm_mod.get_next_tier(biz, customer) if pts_enabled else None
    total_spent = sum(p.get('total', 0) for p in customer.get('purchases', []))
    return render_template('crm_profile.html', biz=biz, customer=customer, idx=idx,
                           sym=sym, tier=tier, next_tier=next_tier,
                           total_spent=total_spent, pts_enabled=pts_enabled)

@app.route('/biz/<biz>/crm/<int:idx>/edit', methods=['POST'])
def crm_edit(biz, idx):
    r = _require_biz_access(biz)
    if r:
        return r
    raw = crm_mod._load_raw()
    customers = raw.get(biz, [])
    if not (0 <= idx < len(customers)):
        flash('Customer not found.', 'danger')
        return redirect(url_for('crm', biz=biz))
    c = customers[idx]
    c['name'] = request.form.get('name', c['name']).strip().title() or c['name']
    c['phone'] = request.form.get('phone', c.get('phone', '')).strip()
    c['email'] = request.form.get('email', c.get('email', '')).strip()
    c['notes'] = request.form.get('notes', c.get('notes', '')).strip()
    c['dob']   = request.form.get('dob',   c.get('dob',   '')).strip()
    crm_mod._save_raw(raw)
    flash('Customer updated.', 'success')
    return redirect(url_for('crm_profile', biz=biz, idx=idx))

@app.route('/biz/<biz>/crm/<int:idx>/remove', methods=['POST'])
def crm_remove(biz, idx):
    r = _require_biz_access(biz)
    if r:
        return r
    raw = crm_mod._load_raw()
    customers = raw.get(biz, [])
    if 0 <= idx < len(customers):
        removed = customers.pop(idx)
        crm_mod._save_raw(raw)
        flash(f'"{removed["name"]}" removed.', 'success')
    return redirect(url_for('crm', biz=biz))

@app.route('/biz/<biz>/crm/points', methods=['GET', 'POST'])
def crm_points(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'crm'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    _load_biz()
    cfg = crm_mod.get_biz_config(biz)
    sym = _sym(biz)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'toggle':
            cfg['points_enabled'] = not cfg.get('points_enabled', True)
            crm_mod.save_biz_config(biz, cfg)
            flash(f'Points system turned {"ON" if cfg["points_enabled"] else "OFF"}.', 'success')
        elif action == 'earn_rate':
            try:
                rate = int(request.form.get('rate', '1'))
                if rate > 0:
                    cfg['points_per_dollar'] = rate
                    crm_mod.save_biz_config(biz, cfg)
                    flash(f'Earn rate: {rate} pt(s) per $1 USD.', 'success')
                else:
                    flash('Rate must be > 0.', 'danger')
            except ValueError:
                flash('Invalid rate.', 'danger')
        elif action == 'add_tier':
            try:
                label = request.form.get('tier_label', 'Custom').strip().title()
                pts = int(request.form.get('tier_pts', '0'))
                disc = float(request.form.get('tier_disc', '0'))
                if pts > 0 and disc > 0:
                    cfg['tiers'].append({'points': pts, 'discount_pct': disc, 'label': label})
                    cfg['tiers'].sort(key=lambda t: t['points'])
                    crm_mod.save_biz_config(biz, cfg)
                    flash(f'Tier "{label}" added.', 'success')
                else:
                    flash('Points and discount must be > 0.', 'danger')
            except ValueError:
                flash('Invalid tier data.', 'danger')
        elif action == 'remove_tier':
            try:
                idx = int(request.form.get('tier_idx', '-1'))
                if 0 <= idx < len(cfg['tiers']):
                    removed = cfg['tiers'].pop(idx)
                    crm_mod.save_biz_config(biz, cfg)
                    flash(f'Tier "{removed["label"]}" removed.', 'success')
            except ValueError:
                flash('Invalid selection.', 'danger')
        elif action == 'reset':
            from crm import default_config
            crm_mod.save_biz_config(biz, default_config())
            flash('Reset to defaults.', 'success')
        return redirect(url_for('crm_points', biz=biz))
    curr = bm.get_business_currency(biz)
    rates = bf.load_exchange_rates()
    rate_key = f'{curr}_TO_USD'
    rev_key = f'USD_TO_{curr}'
    exchange_rate = rates.get(rate_key) or (1 / rates[rev_key] if rev_key in rates else None)
    return render_template('crm_points.html', biz=biz, cfg=cfg, sym=sym,
                           curr=curr, exchange_rate=exchange_rate)

# ── EMPLOYEES ────────────────────────────────────────────────────────────────

@app.route('/biz/<biz>/employees')
def employees_list(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'employees'):
        flash('You do not have access to Employees.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    emps = bf.load_employees().get(biz, [])
    advances = bf.load_advances()
    sym = _sym(biz)
    emp_data = []
    for e in emps:
        outstanding = bf.get_outstanding_advance(biz, e['name'], advances)
        emp_data.append({**e, 'outstanding': outstanding, 'net': e['salary'] - outstanding})
    return render_template('employees.html', biz=biz, employees=emp_data, sym=sym)

@app.route('/biz/<biz>/employees/add', methods=['POST'])
def employees_add(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    name = request.form.get('name', '').strip().title()
    role = request.form.get('role', '').strip().title()
    notes = request.form.get('notes', '').strip()
    try:
        salary = float(request.form.get('salary', '0'))
    except ValueError:
        flash('Invalid salary.', 'danger')
        return redirect(url_for('employees_list', biz=biz))
    if not name or not role:
        flash('Name and role are required.', 'danger')
        return redirect(url_for('employees_list', biz=biz))
    data = bf.load_employees()
    if biz not in data:
        data[biz] = []
    data[biz].append({'name': name, 'role': role, 'salary': salary, 'notes': notes,
                      'username': '', 'password': '', 'permissions': []})
    bf.save_employees(data)
    flash(f'{name} added.', 'success')
    return redirect(url_for('employees_list', biz=biz))

@app.route('/biz/<biz>/employees/<int:emp_idx>/edit', methods=['POST'])
def employees_edit(biz, emp_idx):
    r = _require_biz_access(biz)
    if r:
        return r
    data = bf.load_employees()
    emps = data.get(biz, [])
    if not (0 <= emp_idx < len(emps)):
        flash('Employee not found.', 'danger')
        return redirect(url_for('employees_list', biz=biz))
    emp = emps[emp_idx]
    emp['name'] = request.form.get('name', emp['name']).strip().title() or emp['name']
    emp['role'] = request.form.get('role', emp['role']).strip().title() or emp['role']
    emp['notes'] = request.form.get('notes', emp.get('notes', '')).strip()
    try:
        emp['salary'] = float(request.form.get('salary', str(emp['salary'])))
    except ValueError:
        pass
    bf.save_employees(data)
    flash(f'{emp["name"]} updated.', 'success')
    return redirect(url_for('employees_list', biz=biz))

@app.route('/biz/<biz>/employees/<int:emp_idx>/remove', methods=['POST'])
def employees_remove(biz, emp_idx):
    r = _require_biz_access(biz)
    if r:
        return r
    data = bf.load_employees()
    emps = data.get(biz, [])
    if 0 <= emp_idx < len(emps):
        removed = emps.pop(emp_idx)
        bf.save_employees(data)
        flash(f'{removed["name"]} removed.', 'success')
    return redirect(url_for('employees_list', biz=biz))

@app.route('/biz/<biz>/employees/attendance')
def attendance(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'employees'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    data = bf.load_attendance()
    date_filter = request.args.get('date', datetime.date.today().isoformat())
    records = data.get(biz, {}).get(date_filter, [])
    emps = bf.load_employees().get(biz, [])
    return render_template('attendance.html', biz=biz, records=records,
                           date_filter=date_filter, emps=emps)

@app.route('/biz/<biz>/employees/clock-in', methods=['POST'])
def clock_in(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    emp_name = request.form.get('emp_name', '').strip()
    custom_time = request.form.get('clock_time', '').strip()
    data = bf.load_attendance()
    today = datetime.date.today().isoformat()
    now = custom_time if custom_time else datetime.datetime.now().strftime('%H:%M')
    if biz not in data:
        data[biz] = {}
    if today not in data[biz]:
        data[biz][today] = []
    if any(rec['employee'] == emp_name and rec.get('clock_out') is None for rec in data[biz][today]):
        flash(f'{emp_name} is already clocked in.', 'warning')
    else:
        data[biz][today].append({'employee': emp_name, 'clock_in': now, 'clock_out': None, 'hours': None})
        bf.save_attendance(data)
        flash(f'{emp_name} clocked in at {now}.', 'success')
    return redirect(url_for('attendance', biz=biz))

@app.route('/biz/<biz>/employees/clock-out', methods=['POST'])
def clock_out(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    emp_name = request.form.get('emp_name', '').strip()
    custom_time = request.form.get('clock_time', '').strip()
    data = bf.load_attendance()
    today = datetime.date.today().isoformat()
    now = custom_time if custom_time else datetime.datetime.now().strftime('%H:%M')
    for rec in data.get(biz, {}).get(today, []):
        if rec['employee'] == emp_name and rec.get('clock_out') is None:
            rec['clock_out'] = now
            try:
                t_in = datetime.datetime.strptime(rec['clock_in'], '%H:%M')
                t_out = datetime.datetime.strptime(now, '%H:%M')
                rec['hours'] = round((t_out - t_in).seconds / 3600, 2)
            except Exception:
                pass
            bf.save_attendance(data)
            flash(f'{emp_name} clocked out at {now}. Hours: {rec.get("hours", "N/A")}', 'success')
            return redirect(url_for('attendance', biz=biz))
    flash(f'{emp_name} is not clocked in today.', 'warning')
    return redirect(url_for('attendance', biz=biz))

@app.route('/biz/<biz>/employees/payroll')
def payroll(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'employees'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    emps = bf.load_employees().get(biz, [])
    advances = bf.load_advances()
    sym = _sym(biz)
    emp_data = []
    total_salary = total_outstanding = 0
    for e in emps:
        out = bf.get_outstanding_advance(biz, e['name'], advances)
        emp_data.append({**e, 'outstanding': out, 'net': e['salary'] - out})
        total_salary += e['salary']
        total_outstanding += out
    return render_template('payroll.html', biz=biz, employees=emp_data, sym=sym,
                           total_salary=total_salary, total_outstanding=total_outstanding)

@app.route('/biz/<biz>/employees/advances', methods=['GET', 'POST'])
def salary_advances(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'employees'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    emps = bf.load_employees().get(biz, [])
    advances = bf.load_advances()
    sym = _sym(biz)
    if request.method == 'POST':
        action = request.form.get('action')
        emp_name = request.form.get('emp_name', '').strip()
        if action == 'add':
            emp = next((e for e in emps if e['name'] == emp_name), None)
            if not emp:
                flash('Employee not found.', 'danger')
            else:
                try:
                    amount = float(request.form.get('amount', '0'))
                    reason = request.form.get('reason', 'Not specified').strip()
                    out = bf.get_outstanding_advance(biz, emp_name, advances)
                    max_adv = emp['salary'] - out
                    if amount <= 0:
                        flash('Amount must be > 0.', 'danger')
                    elif amount > max_adv:
                        flash(f'Exceeds max. Available: {sym}{max_adv:.2f}', 'danger')
                    else:
                        if biz not in advances:
                            advances[biz] = []
                        advances[biz].append({
                            'employee': emp_name, 'amount': amount,
                            'date': datetime.date.today().isoformat(),
                            'reason': reason or 'Not specified',
                            'repaid': False, 'repaid_date': None
                        })
                        bf.save_advances(advances)
                        flash(f'Advance of {sym}{amount:.2f} recorded for {emp_name}.', 'success')
                except ValueError:
                    flash('Invalid amount.', 'danger')
        elif action == 'repay':
            adv_date = request.form.get('adv_date', '').strip()
            for adv in advances.get(biz, []):
                if adv['employee'] == emp_name and adv['date'] == adv_date and not adv['repaid']:
                    adv['repaid'] = True
                    adv['repaid_date'] = datetime.date.today().isoformat()
                    bf.save_advances(advances)
                    flash(f'Advance for {emp_name} marked repaid.', 'success')
                    break
        return redirect(url_for('salary_advances', biz=biz))
    emp_advances = {}
    for e in emps:
        out = bf.get_outstanding_advance(biz, e['name'], advances)
        emp_advances[e['name']] = {
            'salary': e['salary'], 'outstanding': out, 'net': e['salary'] - out,
            'records': [a for a in advances.get(biz, []) if a['employee'] == e['name']]
        }
    return render_template('advances.html', biz=biz, sym=sym,
                           emp_advances=emp_advances, employees=emps)

@app.route('/biz/<biz>/employees/leave', methods=['GET', 'POST'])
def leave(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'employees'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    import employees as emp_mod
    leave_data = emp_mod.load_leave()
    emps = bf.load_employees().get(biz, [])
    if request.method == 'POST':
        action = request.form.get('action')
        emp_name = request.form.get('emp_name', '').strip()
        if action == 'request':
            leave_type = request.form.get('leave_type', 'Annual').strip()
            start = request.form.get('start_date', '').strip()
            end = request.form.get('end_date', '').strip()
            reason = request.form.get('reason', '').strip()
            try:
                s = datetime.date.fromisoformat(start)
                e_d = datetime.date.fromisoformat(end)
                days = (e_d - s).days + 1
                if days <= 0:
                    flash('End date must be after start date.', 'danger')
                else:
                    if biz not in leave_data:
                        leave_data[biz] = []
                    leave_data[biz].append({
                        'employee': emp_name, 'type': leave_type,
                        'start': start, 'end': end, 'days': days,
                        'reason': reason, 'status': 'Pending',
                        'applied': datetime.date.today().isoformat()
                    })
                    emp_mod.save_leave(leave_data)
                    flash(f'Leave requested for {emp_name} ({days} days).', 'success')
            except ValueError:
                flash('Invalid dates.', 'danger')
        elif action in ('approve', 'reject'):
            try:
                idx = int(request.form.get('leave_idx', '-1'))
                biz_leaves = leave_data.get(biz, [])
                if 0 <= idx < len(biz_leaves):
                    biz_leaves[idx]['status'] = 'Approved' if action == 'approve' else 'Rejected'
                    emp_mod.save_leave(leave_data)
                    flash(f'Leave {biz_leaves[idx]["status"].lower()}.', 'success')
            except ValueError:
                flash('Invalid.', 'danger')
        return redirect(url_for('leave', biz=biz))
    biz_leaves = leave_data.get(biz, [])
    return render_template('leave.html', biz=biz, leaves=biz_leaves, emps=emps)

# ── MARKETING ────────────────────────────────────────────────────────────────

@app.route('/biz/<biz>/marketing', methods=['GET', 'POST'])
def marketing(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'marketing'):
        flash('You do not have access to Marketing.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    businesses = _load_biz()
    biz_data = businesses.get(biz, {})
    result = None
    import marketing as mkt
    if request.method == 'POST':
        tool = request.form.get('tool')
        industry = biz_data.get('industry', '')
        location = biz_data.get('location', '')
        target = biz_data.get('targetcustomer', '')
        prompts = {
            'email': f"Write a professional marketing email for {biz}. They are in the {industry} industry targeting {target} customers, located in {location}.",
            'caption': f"Create a social media caption for {biz}: specialises in {industry}, based in {location}, targets {target} customers. Keep it engaging and under 150 words.",
            'image': f"Describe in detail a marketing image concept for {biz}: specialises in {industry}, located in {location}, targets {target}.",
            'plan': f"Create a 3-month marketing plan for {biz} in the {industry} industry. Target: {target}. Location: {location}. Include channels, budget, and weekly actions.",
        }
        if tool in prompts:
            result = api_handler.call_api(prompts[tool])
        elif tool == 'sentiment':
            review = request.form.get('review', '').strip()
            rating_str = request.form.get('rating', '').strip()
            if review and rating_str:
                try:
                    rating = float(rating_str)
                    data = mkt._load_json(mkt.SENTIMENT_FILE)
                    if biz not in data:
                        data[biz] = []
                    data[biz].append({
                        'rating': rating, 'review': review,
                        'date': datetime.date.today().isoformat()
                    })
                    mkt._save_json(mkt.SENTIMENT_FILE, data)
                    flash('Feedback recorded.', 'success')
                except ValueError:
                    flash('Invalid rating.', 'danger')
    sent_data = mkt._load_json(mkt.SENTIMENT_FILE).get(biz, [])
    avg_rating = round(sum(s['rating'] for s in sent_data) / len(sent_data), 2) if sent_data else None
    return render_template('marketing.html', biz=biz, biz_data=biz_data,
                           result=result, sentiment=sent_data, avg_rating=avg_rating)

# ── MANAGER SETTINGS ────────────────────────────────────────────────────────

@app.route('/biz/<biz>/manager-settings')
def manager_settings(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _is_manager(biz):
        flash('Manager access required.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    emps = bf.load_employees().get(biz, [])
    admin = bl.get_business_admin(biz)
    return render_template('manager_settings.html', biz=biz, employees=emps,
                           admin=admin, modules=bl.MODULES, module_order=bl.MODULE_ORDER)

@app.route('/biz/<biz>/manager-settings/setup-admin', methods=['POST'])
def setup_manager(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '').strip()
    confirm = request.form.get('confirm', '').strip()
    if not username or not password:
        flash('Username and password required.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    if password != confirm:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    accounts = bl.load_business_accounts()
    accounts[biz] = {'username': username, 'password': password}
    bl.save_business_accounts(accounts)
    flash(f'Manager account created for {biz}.', 'success')
    return redirect(url_for('manager_settings', biz=biz))

@app.route('/biz/<biz>/manager-settings/credentials', methods=['POST'])
def set_credentials(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _is_manager(biz):
        flash('Manager access required.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    emp_idx = int(request.form.get('emp_idx', '-1'))
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '').strip()
    confirm = request.form.get('confirm', '').strip()
    if not username or not password:
        flash('Username and password required.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    if password != confirm:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    data = bf.load_employees()
    emps = data.get(biz, [])
    if not (0 <= emp_idx < len(emps)):
        flash('Invalid employee.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    admin = bl.get_business_admin(biz)
    if admin and admin['username'] == username:
        flash('Username reserved for manager.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    for i, other in enumerate(emps):
        if i != emp_idx and (other.get('username') or '').lower() == username:
            flash(f'Username already used by {other["name"]}.', 'danger')
            return redirect(url_for('manager_settings', biz=biz))
    emps[emp_idx]['username'] = username
    emps[emp_idx]['password'] = password
    bf.save_employees(data)
    flash(f'Login set for {emps[emp_idx]["name"]} (@{username}).', 'success')
    return redirect(url_for('manager_settings', biz=biz))

@app.route('/biz/<biz>/manager-settings/permissions', methods=['POST'])
def set_permissions(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _is_manager(biz):
        flash('Manager access required.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    emp_idx = int(request.form.get('emp_idx', '-1'))
    perms = request.form.getlist('permissions')
    data = bf.load_employees()
    emps = data.get(biz, [])
    if not (0 <= emp_idx < len(emps)):
        flash('Invalid employee.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    valid = set(bl.MODULE_ORDER)
    emps[emp_idx]['permissions'] = [p for p in perms if p in valid]
    bf.save_employees(data)
    flash(f'Permissions updated for {emps[emp_idx]["name"]}.', 'success')
    return redirect(url_for('manager_settings', biz=biz))

@app.route('/biz/<biz>/manager-settings/change-password', methods=['POST'])
def change_manager_pw(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _is_manager(biz):
        flash('Manager access required.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    old = request.form.get('old_password', '').strip()
    new = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm', '').strip()
    accounts = bl.load_business_accounts()
    if biz not in accounts or accounts[biz]['password'] != old:
        flash('Current password incorrect.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    if not new or new != confirm:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    accounts[biz]['password'] = new
    bl.save_business_accounts(accounts)
    flash('Manager password changed.', 'success')
    return redirect(url_for('manager_settings', biz=biz))

# ── SYSTEM ADMIN ────────────────────────────────────────────────────────────

@app.route('/admin/businesses', methods=['GET', 'POST'])
def admin_businesses():
    r = _require_login()
    if r:
        return r
    if session.get('user_type') != 'system_admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('dashboard'))
    businesses = _load_biz()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name', '').strip().title()
            industry = request.form.get('industry', '').strip().title()
            location = request.form.get('location', '').strip().title()
            target = request.form.get('target', '').strip().title()
            email = request.form.get('email', '').strip()
            currency = request.form.get('currency', 'USD').strip().upper()
            if not name:
                flash('Business name required.', 'danger')
            elif name in businesses:
                flash(f'"{name}" already exists.', 'warning')
            else:
                bm.add_business(name, industry, location, target, email, currency)
                flash(f'"{name}" created.', 'success')
        elif action == 'delete':
            name = request.form.get('name', '').strip()
            if name in businesses:
                del businesses[name]
                bm.store_business()
                flash(f'"{name}" deleted.', 'success')
        return redirect(url_for('admin_businesses'))
    return render_template('admin_businesses.html', businesses=_load_biz())

@app.route('/admin/accounts', methods=['GET', 'POST'])
def admin_accounts():
    r = _require_login()
    if r:
        return r
    if session.get('user_type') != 'system_admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('dashboard'))
    businesses = _load_biz()
    accounts = sys_login.load_accounts()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            uname = request.form.get('username', '').strip().lower()
            pw = request.form.get('password', '').strip()
            linked = request.form.getlist('businesses')
            if not uname or not pw:
                flash('Username and password required.', 'danger')
            elif uname in accounts:
                flash('Username already exists.', 'warning')
            else:
                accounts[uname] = {'password': pw, 'role': 'business', 'businesses': linked}
                sys_login.save_accounts(accounts)
                flash(f'Account "{uname}" created.', 'success')
        elif action == 'delete':
            uname = request.form.get('username', '').strip()
            if uname == 'admin':
                flash('Cannot delete admin account.', 'danger')
            elif uname in accounts:
                del accounts[uname]
                sys_login.save_accounts(accounts)
                flash(f'Account "{uname}" deleted.', 'success')
        elif action == 'change_pw':
            uname = request.form.get('username', '').strip()
            new_pw = request.form.get('new_password', '').strip()
            if uname in accounts and new_pw:
                accounts[uname]['password'] = new_pw
                sys_login.save_accounts(accounts)
                flash(f'Password for "{uname}" updated.', 'success')
        return redirect(url_for('admin_accounts'))
    return render_template('admin_accounts.html', accounts=accounts,
                           businesses=list(businesses.keys()))

# ── RUN ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
