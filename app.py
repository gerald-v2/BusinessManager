import os
import sys
import json
import datetime
import base64
import secrets
import smtplib
import threading
import uuid
from dotenv import load_dotenv
load_dotenv()
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import firebase_sync
from ai_business import AIBusiness

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from flask import (Flask, render_template, redirect, url_for,
                   request, session, flash, send_from_directory)

import business_manager as bm
import business_finance as bf
import biz_settings as bs
import security as sec
import feedback as fb
import crm as crm_mod
import Pos as pos_mod
import business_login as bl
import login as sys_login
import api_handler

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'biz_program_secret_key_2026')

# Register enumerate as a Jinja2 filter so templates can use: list | enumerate
app.jinja_env.filters['enumerate'] = enumerate

# ── FIREBASE PERSISTENCE ──────────────────────────────────────────────────────
# Render's free tier wipes local files on every restart/redeploy, so restore
# everything from Firebase before handling any requests.
firebase_sync.download_all()

@app.after_request
def _sync_to_firebase(response):
    """After any data-changing request, push all local JSON files to Firebase
    in a background thread so the response isn't delayed."""
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        threading.Thread(target=firebase_sync.upload_all, daemon=True).start()
    return response


# ── EMAIL / PASSWORD RESET CONFIG ────────────────────────────────────────────
# Set these as environment variables on Render — never hardcode credentials
GMAIL_USER     = os.environ.get('GMAIL_USER', '')      # your Gmail address
GMAIL_APP_PASS = os.environ.get('GMAIL_APP_PASS', '')  # Gmail App Password
APP_BASE_URL   = os.environ.get('APP_BASE_URL', 'https://bizmanager.onrender.com')

# In-memory token store: { token: { 'biz': ..., 'expires': datetime } }
# Tokens are single-use and expire after 30 minutes.
RESET_TOKENS: dict = {}
RESET_TOKEN_TTL = datetime.timedelta(minutes=30)

def _send_reset_email(to_email: str, reset_url: str, biz: str) -> bool:
    """Send a password reset email. Returns True on success."""
    if not GMAIL_USER or not GMAIL_APP_PASS:
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'BizManager — Reset Your Password'
        msg['From']    = f'BizManager <{GMAIL_USER}>'
        msg['To']      = to_email
        html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto">
          <h2 style="color:#0d6efd">BizManager</h2>
          <p>Hi <strong>{biz}</strong> manager,</p>
          <p>We received a request to reset your password. Click the button below.
             This link expires in <strong>30 minutes</strong>.</p>
          <a href="{reset_url}"
             style="display:inline-block;background:#0d6efd;color:#fff;padding:12px 28px;
                    border-radius:6px;text-decoration:none;font-weight:600;margin:16px 0">
            Reset Password
          </a>
          <p style="color:#888;font-size:0.85rem">
            If you didn't request this, ignore this email — your password won't change.<br>
            Link: {reset_url}
          </p>
        </div>"""
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASS)
            smtp.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        app.logger.error(f'Email send failed: {e}')
        return False

def _clean_expired_tokens():
    now = datetime.datetime.utcnow()
    expired = [t for t, v in RESET_TOKENS.items() if v['expires'] < now]
    for t in expired:
        del RESET_TOKENS[t]

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
    return {'can_access': _can_access, 'is_manager': _is_manager, 'enumerate': enumerate,
            'variant_price': bm.variant_price, 'variant_cost': bm.variant_cost,
            'has_own_value': bm.has_own_value, 'to_money': bm.to_money}

# ── PORTAL & AUTH ─────────────────────────────────────────────────────────────
# REPAIR BUSINESSES DAMAGED

@app.route('/admin/repair-businesses')
def repair_businesses():
    r = _require_login()
    if r:
        return r
    if session.get('user_type') != 'system_admin':
        return "Forbidden", 403

    businesses = bm.load_business()
    report = []
    for name, val in list(businesses.items()):
        if isinstance(val, list):
            real = next((item for item in val if isinstance(item, dict)), None)
            if real:
                businesses[name] = real
                report.append(f"Repaired: {name}")
            else:
                report.append(f"COULD NOT repair {name} — raw value: {val}")
    bm.businesses = businesses
    bm.store_business()
    return "<br>".join(report) if report else "No corrupted records found."

# ── FIREBASE DIAGNOSTIC (remove after confirming sync works) ─────────────────
@app.route('/admin/firebase-test')
def firebase_test():
    r = _require_login()
    if r: return r
    if session.get('user_type') != 'system_admin':
        return 'Admin only', 403
    import requests as req_lib
    url = firebase_sync.FIREBASE_URL
    results = []
    results.append(f"FIREBASE_URL = {url}")
    try:
        # Write a test value
        resp = req_lib.put(f"{url}/ping.json",
                           data='{"status": "connected"}', timeout=10)
        results.append(f"PUT /ping: HTTP {resp.status_code} — {resp.text[:100]}")
    except Exception as e:
        results.append(f"PUT failed: {e}")
    try:
        # Force upload all files
        firebase_sync.upload_all()
        results.append("upload_all() called — check Firebase console")
    except Exception as e:
        results.append(f"upload_all() failed: {e}")
    return "<br>".join(results)


@app.route('/')
def portal():
    if session.get('user_type'):
        return redirect(url_for('dashboard'))
    return render_template('portal.html')

# ── Hidden system admin portal (not linked anywhere on the public site) ───────
@app.route('/admin/login', methods=['GET', 'POST'])
def system_login():
    if session.get('user_type'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()
        accounts = sys_login.load_accounts()
        if not accounts:
            sys_login.first_time_setup()
            accounts = sys_login.load_accounts()
        pw_ok, pw_upgrade = sec.verify(accounts.get(username, {}).get('password'), password) \
            if username in accounts else (False, False)
        if pw_ok:
            acc = accounts[username]
            if pw_upgrade:
                acc['password'] = sec.hash_pw(password)
                sys_login.save_accounts(accounts)
            session.clear()
            session['user_type'] = 'system_admin' if acc['role'] == 'admin' else 'system_business'
            session['username'] = username
            session['linked_businesses'] = acc.get('businesses', [])
            flash(f'Welcome, {username.upper()}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Incorrect username or password.', 'danger')
    return render_template('admin_login.html')

# ── Business / staff login — auto-detects business from credentials ───────────
@app.route('/business-login', methods=['GET', 'POST'])
def business_login_route():
    businesses = _load_biz()
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()

        # 1) Check business admin accounts (business_accounts.json)
        biz_accounts = bl.load_business_accounts()
        for biz, admin in biz_accounts.items():
            pw_ok, pw_upgrade = sec.verify(admin.get('password'), password)
            if (admin.get('username') or '').lower() == username and pw_ok:
                if pw_upgrade:
                    admin['password'] = sec.hash_pw(password)
                    bl.save_business_accounts(biz_accounts)
                session.clear()
                session['user_type'] = 'biz_admin'
                session['username'] = username
                session['biz'] = biz
                flash(f'Welcome back!', 'success')
                return redirect(url_for('biz_dashboard', biz=biz))

        # 2) Check staff / employee accounts across all businesses
        all_emps = bf.load_employees()
        for biz, emp_list in all_emps.items():
            for emp in emp_list:
                pw_ok, pw_upgrade = sec.verify(emp.get('password'), password)
                if (emp.get('username') or '').lower() == username and pw_ok:
                    if pw_upgrade:
                        emp['password'] = sec.hash_pw(password)
                        bf.save_employees(all_emps)
                    session.clear()
                    session['user_type'] = 'biz_staff'
                    session['username'] = username
                    session['biz'] = biz
                    session['emp_name'] = emp['name']
                    session['permissions'] = emp.get('permissions', [])
                    bl.record_login_attendance(biz, emp['name'])
                    flash(f'Welcome, {emp["name"]}!', 'success')
                    return redirect(url_for('biz_dashboard', biz=biz))

        flash('Incorrect username or password.', 'danger')
    return render_template('portal.html')

@app.route('/logout')
def logout():
    biz = session.get('biz')
    emp = session.get('emp_name')
    if biz and emp:
        bl.clock_out_on_logout(biz, emp)
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('portal'))

# ── FORGOT / RESET PASSWORD (managers only) ──────────────────────────────────

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if session.get('user_type'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        _clean_expired_tokens()
        # Find the business whose manager has this email
        accounts = bl.load_business_accounts()
        matched_biz = None
        for biz, acct in accounts.items():
            if (acct.get('email') or '').lower() == email:
                matched_biz = biz
                break
        # Always show the same message — don't reveal whether email exists
        if matched_biz:
            token = secrets.token_urlsafe(32)
            RESET_TOKENS[token] = {
                'biz': matched_biz,
                'expires': datetime.datetime.utcnow() + RESET_TOKEN_TTL
            }
            reset_url = f"{APP_BASE_URL}/reset-password/{token}"
            sent = _send_reset_email(email, reset_url, matched_biz)
            if not sent:
                flash('Could not send email. Check server email config.', 'danger')
                return render_template('forgot_password.html')
        flash('If that email is registered, a reset link has been sent. Check your inbox.', 'info')
        return render_template('forgot_password.html', sent=True)
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if session.get('user_type'):
        return redirect(url_for('dashboard'))
    _clean_expired_tokens()
    entry = RESET_TOKENS.get(token)
    if not entry or entry['expires'] < datetime.datetime.utcnow():
        flash('This reset link is invalid or has expired. Please request a new one.', 'danger')
        return redirect(url_for('forgot_password'))
    biz = entry['biz']
    if request.method == 'POST':
        new_pw  = request.form.get('new_password', '').strip()
        confirm = request.form.get('confirm', '').strip()
        if len(new_pw) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('reset_password.html', token=token)
        if new_pw != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
        accounts = bl.load_business_accounts()
        if biz in accounts:
            accounts[biz]['password'] = sec.hash_pw(new_pw)
            bl.save_business_accounts(accounts)
        del RESET_TOKENS[token]
        flash('Password updated successfully. You can now sign in.', 'success')
        return redirect(url_for('portal'))
    return render_template('reset_password.html', token=token)

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
            biz_data = businesses[name]
            if isinstance(biz_data, dict):
                products_count = len(biz_data.get('products', {}))
            elif isinstance(biz_data, list):
                products_count = 0
            else:
                products_count = 0
            fin = bf.business_finance.get(name, {})
            rev = fin.get('Revenue', 0) or 0
            costs = fin.get('Costs', 0) or 0
            payroll = bf.get_monthly_payroll(name)
            stats[name] = {
                'revenue': rev, 'costs': costs,
                'profit': rev - costs - payroll,
                'products': products_count,
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
    today = bs.today()
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
    today = bs.today()
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

    # Make sure the business exists
    if biz not in businesses:
        flash(f'Business "{biz}" was not found.', 'danger')
        return redirect(url_for('dashboard'))

    # Make sure the products dictionary exists
    businesses[biz].setdefault('products', {})

    name = request.form.get(
        'product_name',
        ''
    ).strip().title()

    price_str = request.form.get(
        'price',
        '0'
    ).strip()

    cost_str = request.form.get(
        'cost',
        '0'
    ).strip()

    # Product name validation
    if not name:
        flash(
            'Product name is required.',
            'danger'
        )

        return redirect(
            url_for(
                'products',
                biz=biz
            )
        )

    # Check duplicate product
    if name in businesses[biz]['products']:

        flash(
            f'"{name}" already exists.',
            'warning'
        )

        return redirect(
            url_for(
                'products',
                biz=biz
            )
        )

    # Validate price and cost
    try:

        price_f = float(price_str)
        cost_f = float(cost_str)

    except ValueError:

        flash(
            'Invalid price or cost.',
            'danger'
        )

        return redirect(
            url_for(
                'products',
                biz=biz
            )
        )

    # Prevent negative values
    if price_f < 0 or cost_f < 0:

        flash(
            'Price and cost cannot be negative.',
            'danger'
        )

        return redirect(
            url_for(
                'products',
                biz=biz
            )
        )

    # Create product
    businesses[biz]['products'][name] = {
        'Price': f'${price_f:.2f}',
        'Cost': f'${cost_f:.2f}',
        'variants': []
    }

    # Save
    bm.store_business()

    bm.export_to_csv(biz)

    flash(
        f'Product "{name}" added.',
        'success'
    )

    return redirect(
        url_for(
            'products',
            biz=biz
        )
    )

@app.route('/biz/<biz>/products/<product>/add-variant', methods=['POST'])
def add_variant(biz, product):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'products'):
        flash('You do not have access to Products.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
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
    if product not in businesses.get(biz, {}).get('products', {}):
        flash('Product not found.', 'danger')
        return redirect(url_for('products', biz=biz))
    if units < 0:
        flash('Units cannot be negative.', 'danger')
        return redirect(url_for('products', biz=biz))
    existing = businesses[biz]['products'][product].setdefault('variants', [])
    if any(v.get('name') == v_name for v in existing):
        flash(f'"{v_name}" already exists for {product}.', 'danger')
        return redirect(url_for('product_detail', biz=biz, product=product))
    new_variant = {'name': v_name, 'units': units, 'PLU': plu, 'sold': 0}
    # optional own selling price / cost - blank means "same as the product"
    for form_key, key in (('price', 'Price'), ('cost', 'Cost')):
        raw = request.form.get(form_key, '').strip()
        if raw:
            amount = bs.parse_number(raw, None, 0, 100000000)
            if amount is None:
                flash(f'Invalid {form_key}.', 'danger')
                return redirect(url_for('product_detail', biz=biz, product=product))
            new_variant[key] = f'${amount:.2f}'
    existing.append(new_variant)
    bm.store_business()
    bm.export_to_csv(biz)
    try:
        _load_finance()
        unit_cost = bm.variant_cost(businesses[biz]['products'][product], new_variant)
        if unit_cost * units > 0:
            bf.add_costs(biz, unit_cost * units, f'{product} stock ({v_name}, {units} units)')
    except Exception:
        pass
    flash(f'Variant "{v_name}" [PLU:{plu}] added.', 'success')
    return redirect(url_for('product_detail', biz=biz, product=product))

@app.route('/biz/<biz>/products/<product>/edit-variant', methods=['POST'])
def edit_variant(biz, product):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'products'):
        flash('You do not have access to Products.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    businesses = _load_biz()
    v_name = request.form.get('variant_name', '').strip()
    field = request.form.get('field', '').strip()
    value = request.form.get('value', '').strip()
    prods = businesses.get(biz, {}).get('products', {})
    if product not in prods:
        flash('Product not found.', 'danger')
        return redirect(url_for('products', biz=biz))

    # Older pages sent the PRODUCT price/cost through this route with a dummy
    # variant name - keep that working by handing it to the product editor.
    if v_name == '__product__' and field in ('price', 'cost'):
        return _save_product_money(biz, product, **{field: value})

    variants = prods[product].get('variants', [])
    target = next((v for v in variants if v.get('name') == v_name), None)
    if not target:
        flash('Variant not found.', 'danger')
        return redirect(url_for('product_detail', biz=biz, product=product))
    ok = True
    if field == 'units':
        try:
            units = int(value)
            if units < 0:
                raise ValueError
            target['units'] = units
        except ValueError:
            flash('Units must be a whole number (0 or more).', 'danger')
            ok = False
    elif field in ('price', 'cost'):
        key = 'Price' if field == 'price' else 'Cost'
        if value == '':
            target.pop(key, None)          # blank = use the product's price/cost again
            flash(f'{key} reset - this variant now uses the product {key.lower()}.', 'info')
        else:
            amount = bs.parse_number(value, None, 0, 100000000)
            if amount is None:
                flash(f'Invalid {field}.', 'danger')
                ok = False
            else:
                target[key] = f'${amount:.2f}'
    elif field == 'plu':
        owner = bm.find_plu_owner(biz, value, skip_product=product, skip_variant=v_name)
        if not value:
            flash('PLU cannot be empty.', 'danger')
            ok = False
        elif owner:
            flash(f'PLU {value} already used by {owner}.', 'danger')
            ok = False
        else:
            target['PLU'] = value
    elif field == 'name':
        if not value:
            flash('Name cannot be empty.', 'danger')
            ok = False
        elif any(v.get('name') == value.title() and v is not target for v in variants):
            flash('Another variant already has that name.', 'danger')
            ok = False
        else:
            target['name'] = value.title()
    else:
        flash('Unknown field.', 'danger')
        ok = False
    if ok:
        bm.store_business()
        bm.export_to_csv(biz)
        flash('Updated successfully.', 'success')
    return redirect(url_for('product_detail', biz=biz, product=product))

def _save_product_money(biz, product, price=None, cost=None, reset_variants=False):
    """Change the product-level selling price / cost price (variants without
    their own price follow automatically)."""
    businesses = _load_biz()
    prods = businesses.get(biz, {}).get('products', {})
    if product not in prods:
        flash('Product not found.', 'danger')
        return redirect(url_for('products', biz=biz))
    details = prods[product]
    changed = []
    for label, key, raw in (('price', 'Price', price), ('cost', 'Cost', cost)):
        if raw is None or str(raw).strip() == '':
            continue
        amount = bs.parse_number(raw, None, 0, 100000000)
        if amount is None:
            flash(f'Invalid {label}: "{raw}".', 'danger')
            return redirect(url_for('product_detail', biz=biz, product=product))
        details[key] = f'${amount:.2f}'
        changed.append(label)
    if reset_variants:
        for v in details.get('variants', []):
            v.pop('Price', None)
            v.pop('Cost', None)
    if not changed and not reset_variants:
        flash('Nothing to change.', 'info')
        return redirect(url_for('product_detail', biz=biz, product=product))
    bm.store_business()
    bm.export_to_csv(biz)
    msg = ' and '.join(changed).capitalize() + ' updated.' if changed else 'Variant prices reset.'
    if bm.to_money(details.get('Price')) < bm.to_money(details.get('Cost')):
        msg += ' Warning: the selling price is below the cost price.'
        flash(msg, 'warning')
    else:
        flash(msg, 'success')
    return redirect(url_for('product_detail', biz=biz, product=product))

@app.route('/biz/<biz>/products/<product>/edit', methods=['POST'])
def edit_product(biz, product):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'products'):
        flash('You do not have access to Products.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    return _save_product_money(biz, product,
                               price=request.form.get('price'),
                               cost=request.form.get('cost'),
                               reset_variants=bool(request.form.get('reset_variants')))

@app.route('/biz/<biz>/products/<product>/remove', methods=['POST'])
def remove_product(biz, product):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'products'):
        flash('You do not have access to Products.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
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
    if not _can_access(biz, 'products'):
        flash('You do not have access to Products.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    businesses = _load_biz()
    if product not in businesses.get(biz, {}).get('products', {}):
        flash('Product not found.', 'danger')
        return redirect(url_for('products', biz=biz))
    variants = businesses[biz]['products'][product].get('variants', [])
    before = len(variants)
    businesses[biz]['products'][product]['variants'] = [v for v in variants if v.get('name') != variant]
    if len(businesses[biz]['products'][product]['variants']) < before:
        bm.store_business()
        bm.export_to_csv(biz)
        flash(f'Variant "{variant}" removed.', 'success')
    return redirect(url_for('product_detail', biz=biz, product=product))

@app.route('/biz/<biz>/products/<product>')
def product_detail(biz, product):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'products'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    businesses = _load_biz()
    prods = businesses.get(biz, {}).get('products', {})
    if product not in prods:
        flash('Product not found.', 'danger')
        return redirect(url_for('products', biz=biz))
    sym = _sym(biz)
    return render_template('product_detail.html', biz=biz, p_name=product,
                           details=prods[product], sym=sym, all_products=list(prods.keys()))

@app.route('/biz/<biz>/products/<product>/upload-image', methods=['POST'])
def upload_variant_image(biz, product):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'products'):
        flash('You do not have access to Products.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    businesses = _load_biz()
    if product not in businesses.get(biz, {}).get('products', {}):
        flash('Product not found.', 'danger')
        return redirect(url_for('products', biz=biz))
    variant_name = request.form.get('variant_name', '').strip()
    file = request.files.get('image')
    if not file or not file.filename:
        flash('No image selected.', 'danger')
        return redirect(url_for('product_detail', biz=biz, product=product))
    allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in allowed:
        flash('Image must be PNG, JPG, GIF or WEBP.', 'danger')
        return redirect(url_for('product_detail', biz=biz, product=product))
    img_data = file.read()
    if len(img_data) > 2 * 1024 * 1024:
        flash('Image must be under 2MB.', 'danger')
        return redirect(url_for('product_detail', biz=biz, product=product))
    b64 = base64.b64encode(img_data).decode('utf-8')
    mime = f'image/{ext}' if ext != 'jpg' else 'image/jpeg'
    data_url = f'data:{mime};base64,{b64}'
    variants = businesses[biz]['products'][product].get('variants', [])
    if variant_name == '__product__':
        businesses[biz]['products'][product]['image'] = data_url
    else:
        for v in variants:
            if v.get('name') == variant_name:
                v['image'] = data_url
                break
    bm.store_business()
    flash('Image uploaded.', 'success')
    return redirect(url_for('product_detail', biz=biz, product=product))

@app.before_request
def _accrue_fixed_costs_hook():
    """Charge any fixed daily costs that are due (no background job needed)."""
    try:
        if request.method == 'GET' and session.get('user_type') and request.path.startswith('/biz/'):
            parts = request.path.split('/')
            if len(parts) > 2 and parts[2]:
                bs.accrue_fixed_costs(parts[2])
    except Exception as exc:
        print(f'[fixed costs] skipped: {exc}')

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
    curr = bm.get_business_currency(biz)
    cfg = bs.get(biz)
    pts_enabled = crm_mod.points_enabled(biz)

    # fresh copy of the linked customer (points change after every sale)
    active_customer = None
    linked = session.get(f'customer_{biz}')
    if linked:
        found = [c for c in crm_mod.find_customer(biz, linked.get('name', ''))
                 if c['name'] == linked.get('name')]
        active_customer = found[0] if found else None
        if active_customer is None:
            session.pop(f'customer_{biz}', None)
    tier = crm_mod.get_eligible_discount(biz, active_customer) if active_customer and pts_enabled else None

    # prices: every variant can have its own price; otherwise the product price
    base_prices, variant_prices, price_labels = {}, {}, {}
    for p_name, details in prods.items():
        base_prices[p_name] = bm.to_money(details.get('Price'))
        vp = {v['name']: bm.variant_price(details, v) for v in details.get('variants', [])}
        variant_prices[p_name] = vp
        lo, hi = (min(vp.values()), max(vp.values())) if vp else (base_prices[p_name],) * 2
        price_labels[p_name] = f'{lo:.2f}' if abs(hi - lo) < 0.005 else f'{lo:.2f} - {hi:.2f}'

    rates = bf.load_exchange_rates()
    alt_currencies = []
    for key, rate in rates.items():
        if key.startswith(f'{curr.upper()}_TO_') and rate:
            code = key.split('_TO_', 1)[1]
            alt_currencies.append({'code': code, 'rate': rate,
                                   'sym': bm.get_currency_symbol(code)})

    pos_cfg = {
        'currency': curr,
        'sym': sym,
        'vat': {'enabled': cfg['vat_enabled'], 'pct': cfg['vat_pct'],
                'inclusive': cfg['vat_inclusive']},
        'is_manager': _is_manager(biz),
        'max_staff_discount_pct': cfg['max_staff_discount_pct'],
        'alt_currencies': alt_currencies,
        'points_enabled': bool(pts_enabled),
        'customer': ({'name': active_customer['name'],
                      'points': active_customer.get('points', 0),
                      'tier': tier} if active_customer else None),
        'cashier': session.get('emp_name') or session.get('username') or '',
        'paper_width': cfg['paper_width'],
        'cut': cfg['printer_cut'],
        'auto_print': cfg['auto_print'],
        'receipt_biz': {'name': biz, 'header': cfg['receipt_header'],
                        'address': cfg['receipt_address'], 'phone': cfg['receipt_phone'],
                        'vat_number': cfg['vat_number'] if cfg['vat_enabled'] else '',
                        'footer': cfg['receipt_footer']},
    }
    return render_template('pos.html', biz=biz, products=prods, sym=sym,
                           active_customer=active_customer, pts_enabled=pts_enabled,
                           tier=tier, pos_cfg=pos_cfg, base_prices=base_prices,
                           variant_prices=variant_prices, price_labels=price_labels,
                           cart={}, subtotal=0)

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
    """The old separate checkout page was replaced by the checkout window on the
    POS screen (discount, loyalty, VAT, receipt). Old bookmarks land here."""
    r = _require_biz_access(biz)
    if r:
        return r
    return redirect(url_for('pos', biz=biz))

# ── OFFLINE SYNC API ──────────────────────────────────────────────────────────
# Accepts queued cash sales made while offline (see static/offline-sync.js).
# Scope: cash sales only, full amount, no discount/points/currency conversion —
# those still require being online and go through the normal /pos/checkout flow.
from flask import jsonify

@app.route('/api/sync/sale', methods=['POST'])
def api_sync_sale():
    """Record a sale (online checkout OR a sale queued while offline).

    Everything is recalculated on the server: prices, stock, discount, loyalty
    points, VAT and revenue.  Returns the saved sale plus a ready-to-print receipt.
    """
    if not session.get('user_type'):
        return jsonify({'status': 'error', 'error': 'not logged in'}), 401

    data = request.get_json(silent=True) or {}
    biz = data.get('biz')
    if not biz:
        return jsonify({'status': 'error', 'error': 'missing business'}), 400
    if not data.get('sale_id'):
        return jsonify({'status': 'error', 'error': 'missing sale_id'}), 400
    if not data.get('items'):
        return jsonify({'status': 'error', 'error': 'no items'}), 400
    if _require_biz_access(biz) or not _can_access(biz, 'pos'):
        return jsonify({'status': 'error', 'error': 'access denied'}), 403

    actor = {
        'name': session.get('emp_name') or session.get('username') or '',
        'is_manager': _is_manager(biz),
    }
    ok, payload, status = pos_mod.process_sale(biz, data, actor)
    return jsonify(payload), status

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
    if not _can_access(biz, 'pos'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    biz_sales = pos_mod.load_sales().get(biz, [])
    real_idx = len(biz_sales) - 1 - display_idx
    if not (0 <= real_idx < len(biz_sales)):
        flash('Sale not found.', 'danger')
        return redirect(url_for('pos_sales', biz=biz))
    sale = biz_sales[real_idx]
    if not sale.get('sale_id'):
        sale_id = None
    else:
        sale_id = sale['sale_id']
    if sale_id is None:      # very old sales without an id: give them one first
        data = pos_mod.load_sales()
        data[biz][real_idx]['sale_id'] = str(uuid.uuid4())
        pos_mod.save_sales(data)
        sale_id = data[biz][real_idx]['sale_id']
    ok, result = pos_mod.refund_sale_web(biz, sale_id)
    if ok:
        flash(f'Refund of {_sym(biz)}{result["total"]:.2f} processed.', 'success')
    else:
        flash(result, 'warning')
    return redirect(url_for('pos_sales', biz=biz))

def _sale_by_id(biz, sale_id):
    for s_ in pos_mod.load_sales().get(biz, []):
        if s_.get('sale_id') == sale_id:
            return s_
    return None

@app.route('/biz/<biz>/pos/receipt/<sale_id>')
def pos_receipt_view(biz, sale_id):
    """Show / reprint the receipt of any past sale."""
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'pos'):
        flash('Access denied.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    sale = _sale_by_id(biz, sale_id)
    if sale is None:
        flash('Sale not found.', 'danger')
        return redirect(url_for('pos_sales', biz=biz))
    customer = None
    if sale.get('customer'):
        found = [c for c in crm_mod.find_customer(biz, sale['customer'])
                 if c['name'] == sale['customer']]
        customer = found[0] if found else None
    receipt = pos_mod.build_receipt(biz, sale, customer)
    if customer is None and receipt.get('customer'):
        receipt['customer']['balance'] = None
    return render_template('pos_receipt.html', biz=biz, receipt=receipt, sale=sale,
                           sym=_sym(biz))

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
    fx = bs.get(biz)
    return render_template('finance.html', biz=biz, sym=sym, curr=curr,
                           revenue=revenue, costs=costs, payroll=payroll,
                           total_costs=total_costs, profit=profit, margin=margin,
                           rates=rates, fx=fx,
                           fx_preview=bs.daily_cost_preview(fx),
                           fx_log=list(reversed(fx['daily_costs_log']))[:10],
                           fx_logged_total=round(sum(e.get('amount', 0) for e in fx['daily_costs_log']), 2))

def _fixed_costs_guard(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'finance'):
        flash('You do not have access to Finance.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    return None

@app.route('/biz/<biz>/finance/fixed-costs/settings', methods=['POST'])
def fixed_costs_settings(biz):
    """Switch fixed daily costs on/off and choose the days the business trades."""
    r = _fixed_costs_guard(biz)
    if r:
        return r
    turn_on = bool(request.form.get('enabled'))
    days = []
    for d in request.form.getlist('days'):
        try:
            if 0 <= int(d) <= 6:
                days.append(int(d))
        except ValueError:
            pass
    changes = {'daily_costs_enabled': turn_on, 'daily_costs_days': sorted(set(days)) or list(range(7))}
    if turn_on and not bs.get(biz)['daily_costs_enabled']:
        changes['daily_costs_last_accrued'] = None      # start from today, never back-charge
    bs.update(biz, changes)
    flash('Fixed daily costs are ON - they are added automatically each trading day.'
          if turn_on else 'Fixed daily costs are OFF. Nothing more will be charged.',
          'success' if turn_on else 'info')
    return redirect(url_for('finance', biz=biz) + '#fixed-costs')

@app.route('/biz/<biz>/finance/fixed-costs/add', methods=['POST'])
def fixed_costs_add(biz):
    r = _fixed_costs_guard(biz)
    if r:
        return r
    name = request.form.get('name', '').strip()
    amount = bs.parse_number(request.form.get('amount'), None, 0, 100000000)
    period = request.form.get('period', 'day')
    if not name or amount is None or amount <= 0:
        flash('Enter a name and an amount above 0.', 'danger')
        return redirect(url_for('finance', biz=biz) + '#fixed-costs')
    cfg = bs.get(biz)
    items = cfg['daily_costs'] + [bs.new_cost_item(name, amount, period)]
    bs.update(biz, {'daily_costs': items})
    flash(f'"{name}" added.', 'success')
    return redirect(url_for('finance', biz=biz) + '#fixed-costs')

@app.route('/biz/<biz>/finance/fixed-costs/<item_id>/<action>', methods=['POST'])
def fixed_costs_item(biz, item_id, action):
    r = _fixed_costs_guard(biz)
    if r:
        return r
    cfg = bs.get(biz)
    items = cfg['daily_costs']
    if action == 'remove':
        items = [i for i in items if i.get('id') != item_id]
    elif action == 'toggle':
        for i in items:
            if i.get('id') == item_id:
                i['active'] = not i.get('active', True)
    bs.update(biz, {'daily_costs': items})
    return redirect(url_for('finance', biz=biz) + '#fixed-costs')

@app.route('/biz/<biz>/finance/add-cost', methods=['POST'])
def add_cost(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'finance'):
        flash('You do not have access to Finance.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    amount = bs.parse_number(request.form.get('amount'), None, 0, 1000000000)
    if amount is None or amount <= 0:
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
    if not _can_access(biz, 'finance'):
        flash('You do not have access to Finance.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
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
        'joined': bs.now().strftime('%Y-%m-%d'),
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
    date_filter = request.args.get('date', bs.today().isoformat())
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
    today = bs.today().isoformat()
    now = custom_time if custom_time else bs.now().strftime('%H:%M')
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
    today = bs.today().isoformat()
    now = custom_time if custom_time else bs.now().strftime('%H:%M')
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
                            'date': bs.today().isoformat(),
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
                    adv['repaid_date'] = bs.today().isoformat()
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
                        'applied': bs.today().isoformat()
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
    image_url = None
    import marketing as mkt
    if request.method == 'POST':
        tool = request.form.get('tool')
        product = request.form.get('product', '').strip() or None
        promo_type = request.form.get('promo_type', '').strip() or None
        tone = request.form.get('tone', '').strip() or None
        platform = request.form.get('platform', '').strip() or None

        if tool in ('email', 'caption', 'plan'):
            prompt = mkt.build_prompt(tool, biz, biz_data, product, promo_type, tone, platform)
            result = api_handler.call_api(prompt)
        elif tool == 'image':
            prompt = mkt.build_prompt('image', biz, biz_data, product, promo_type, tone, platform)
            img_bytes, mime_or_error = api_handler.call_openai_image(prompt)
            if img_bytes:
                image_url = api_handler.save_generated_image(img_bytes, mime_or_error, biz)
            else:
                flash(mime_or_error, 'danger')
    sent_data = fb.load(biz)
    avg_rating = round(sum(s['rating'] for s in sent_data) / len(sent_data), 2) if sent_data else None
    products = list(biz_data.get('products', {}).keys())
    return render_template('marketing.html', biz=biz, biz_data=biz_data,
                           result=result, image_url=image_url,
                           products=products, promo_types=mkt.PROMO_TYPES,
                           tones=mkt.TONES, platforms=mkt.PLATFORMS,
                           sentiment=sent_data, avg_rating=avg_rating)

# ── CUSTOMER FEEDBACK ───────────────────────────────────────────────────────

def _feedback_guard(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _can_access(biz, 'marketing'):
        flash('You do not have access to Customer Feedback.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    return None

@app.route('/biz/<biz>/feedback')
def feedback_page(biz):
    r = _feedback_guard(biz)
    if r:
        return r
    entries = fb.load(biz)
    stats = fb.stats(entries)
    flt = request.args.get('filter', 'all')
    shown = list(reversed(entries))
    if flt == 'attention':
        shown = [e for e in shown if e['rating'] <= 2 and not e.get('resolved')]
    elif flt in ('1', '2', '3', '4', '5'):
        shown = [e for e in shown if int(round(e['rating'])) == int(flt)]
    else:
        flt = 'all'
    businesses = _load_biz()
    products = list(businesses.get(biz, {}).get('products', {}).keys())
    customers = [c['name'] for c in crm_mod.find_customer(biz, '')] if hasattr(crm_mod, 'find_customer') else []
    return render_template('feedback.html', biz=biz, entries=shown, stats=stats, flt=flt,
                           products=products, customers=customers, sources=fb.SOURCES,
                           label=fb.sentiment_label)

@app.route('/biz/<biz>/feedback/add', methods=['POST'])
def feedback_add(biz):
    r = _feedback_guard(biz)
    if r:
        return r
    entry = fb.add(biz, request.form.get('rating'), request.form.get('review'),
                   request.form.get('customer', ''), request.form.get('product', ''),
                   request.form.get('source', 'In shop'))
    if entry is None:
        flash('Please choose a star rating from 1 to 5.', 'danger')
    else:
        flash('Feedback saved.' + (' It is marked "needs follow-up".' if not entry['resolved'] else ''), 'success')
    return redirect(url_for('feedback_page', biz=biz))

@app.route('/biz/<biz>/feedback/<entry_id>/resolve', methods=['POST'])
def feedback_resolve(biz, entry_id):
    r = _feedback_guard(biz)
    if r:
        return r
    current = next((e for e in fb.load(biz) if e['id'] == entry_id), None)
    if current:
        fb.update(biz, entry_id, resolved=not current.get('resolved'))
    return redirect(request.referrer or url_for('feedback_page', biz=biz))

@app.route('/biz/<biz>/feedback/<entry_id>/delete', methods=['POST'])
def feedback_delete(biz, entry_id):
    r = _feedback_guard(biz)
    if r:
        return r
    if fb.delete(biz, entry_id):
        flash('Feedback removed.', 'info')
    return redirect(url_for('feedback_page', biz=biz))

@app.route('/biz/<biz>/feedback/<entry_id>/reply', methods=['POST'])
def feedback_reply(biz, entry_id):
    r = _feedback_guard(biz)
    if r:
        return jsonify({'error': 'access denied'}), 403
    entry = next((e for e in fb.load(biz) if e['id'] == entry_id), None)
    if not entry:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'reply': fb.draft_reply(entry, biz)})

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
                           admin=admin, modules=bl.MODULES, module_order=bl.MODULE_ORDER,
                           cfg=bs.get(biz))

@app.route('/biz/<biz>/manager-settings/sales', methods=['POST'])
def manager_sales_settings(biz):
    """VAT, receipt wording / paper width, printer options and discount limit."""
    r = _require_biz_access(biz)
    if r:
        return r
    if not _is_manager(biz):
        flash('Manager access required.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    f = request.form
    vat_pct = bs.parse_number(f.get('vat_pct'), None, 0, 100)
    if f.get('vat_enabled') and (vat_pct is None or vat_pct <= 0):
        flash('Enter a VAT rate above 0% (for example 15) or switch VAT off.', 'danger')
        return redirect(url_for('manager_settings', biz=biz) + '#sales-settings')
    bs.update(biz, {
        'vat_enabled': bool(f.get('vat_enabled')),
        'vat_pct': vat_pct if vat_pct is not None else bs.DEFAULTS['vat_pct'],
        'vat_inclusive': f.get('vat_inclusive') == '1',
        'vat_number': f.get('vat_number', '').strip()[:40],
        'receipt_header': f.get('receipt_header', '').strip()[:80],
        'receipt_address': f.get('receipt_address', '').strip()[:120],
        'receipt_phone': f.get('receipt_phone', '').strip()[:40],
        'receipt_footer': f.get('receipt_footer', '').strip()[:120],
        'paper_width': 80 if f.get('paper_width') == '80' else 58,
        'printer_cut': bool(f.get('printer_cut')),
        'auto_print': bool(f.get('auto_print')),
        'max_staff_discount_pct': bs.parse_number(f.get('max_staff_discount_pct'), 100.0, 0, 100),
    })
    flash('Sales & receipt settings saved.', 'success')
    return redirect(url_for('manager_settings', biz=biz) + '#sales-settings')

@app.route('/biz/<biz>/manager-settings/setup-admin', methods=['POST'])
def setup_manager(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if bl.get_business_admin(biz) and not _is_manager(biz):
        flash('Manager access required.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '').strip()
    confirm  = request.form.get('confirm', '').strip()
    email    = request.form.get('email', '').strip().lower()
    if not username or not password:
        flash('Username and password required.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    if password != confirm:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    accounts = bl.load_business_accounts()
    accounts[biz] = {'username': username, 'password': sec.hash_pw(password), 'email': email}
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
    try:
        emp_idx = int(request.form.get('emp_idx', '-1'))
    except (TypeError, ValueError):
        emp_idx = -1
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
    emps[emp_idx]['password'] = sec.hash_pw(password)
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
    try:
        emp_idx = int(request.form.get('emp_idx', '-1'))
    except (TypeError, ValueError):
        emp_idx = -1
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
    if biz not in accounts or not sec.verify(accounts[biz].get('password'), old)[0]:
        flash('Current password incorrect.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    if not new or new != confirm:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    accounts[biz]['password'] = sec.hash_pw(new)
    bl.save_business_accounts(accounts)
    flash('Manager password changed.', 'success')
    return redirect(url_for('manager_settings', biz=biz))

@app.route('/biz/<biz>/manager-settings/update-email', methods=['GET', 'POST'])
def update_manager_email(biz):
    r = _require_biz_access(biz)
    if r:
        return r
    if not _is_manager(biz):
        flash('Manager access required.', 'danger')
        return redirect(url_for('biz_dashboard', biz=biz))
    if request.method == 'GET':
        return redirect(url_for('manager_settings', biz=biz))
    email = request.form.get('email', '').strip().lower()
    accounts = bl.load_business_accounts()
    if biz not in accounts:
        flash('No manager account found.', 'danger')
        return redirect(url_for('manager_settings', biz=biz))
    accounts[biz]['email'] = email
    bl.save_business_accounts(accounts)
    flash('Recovery email updated.', 'success')
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
    """
    System-admin screen for creating BUSINESS MANAGER accounts.

    accounts.json is reserved exclusively for the system-admin login
    (/admin/login) — it is never written to from here. Every account
    created on this page is a manager/owner login for one business,
    stored in business_accounts.json (the same store business-login,
    password-reset, and manager-settings all read from), one manager
    account per business.
    """
    r = _require_login()
    if r:
        return r
    if session.get('user_type') != 'system_admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('dashboard'))
    businesses = _load_biz()
    accounts = bl.load_business_accounts()          # {biz: {username, password, email?}}
    unassigned = [b for b in businesses if b not in accounts]

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            biz = request.form.get('business', '').strip()
            uname = request.form.get('username', '').strip().lower()
            pw = request.form.get('password', '').strip()
            email = request.form.get('email', '').strip().lower()
            if not biz or not uname or not pw:
                flash('Business, username and password are required.', 'danger')
            elif biz not in businesses:
                flash('Select a valid business.', 'danger')
            elif biz in accounts:
                flash(f'"{biz}" already has a manager account. Use "Change Password" or delete it first.', 'warning')
            elif any((a.get('username') or '').lower() == uname for a in accounts.values()):
                flash('That username is already used by another business manager.', 'warning')
            else:
                accounts[biz] = {'username': uname, 'password': sec.hash_pw(pw), 'email': email}
                bl.save_business_accounts(accounts)
                firebase_sync.upload_all()
                flash(f'Manager account created for "{biz}" (username: {uname}).', 'success')
        elif action == 'delete':
            biz = request.form.get('business', '').strip()
            if biz in accounts:
                del accounts[biz]
                bl.save_business_accounts(accounts)
                firebase_sync.upload_all()
                flash(f'Manager account for "{biz}" deleted.', 'success')
        elif action == 'change_pw':
            biz = request.form.get('business', '').strip()
            new_pw = request.form.get('new_password', '').strip()
            if biz in accounts and new_pw:
                accounts[biz]['password'] = sec.hash_pw(new_pw)
                bl.save_business_accounts(accounts)
                firebase_sync.upload_all()
                flash(f'Password for "{biz}" manager updated.', 'success')
        return redirect(url_for('admin_accounts'))
    return render_template('admin_accounts.html', accounts=accounts,
                           businesses=list(businesses.keys()),
                           unassigned_businesses=unassigned)


#(TESTING NEW) AI BUSINESS MANAGER

@app.route("/biz/<biz>/ai-business")
def ai_business(biz):

    r = _require_biz_access(biz)

    if r:
        return r

    return render_template(
        "ai_business.html",
        biz=biz
    )

@app.route("/biz/<biz>/ai-business/ask", methods=["POST"])
def ask_ai(biz):

    r = _require_biz_access(biz)

    if r:
        return jsonify({
            "error": "Access denied"
        }), 403

    data = request.get_json(silent=True) or {}

    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({
            "error": "No message provided"
        }), 400

    ai = AIBusiness(biz)

    answer = ai.ask(message)

    return jsonify({
        "response": answer
    })

# ----- NEW OFFLINE SYNC METHOD --------
@app.route("/api/offline-sync", methods=["POST"])
def offline_sync():
    data = request.get_json(silent=True) or {}

    # Process queued transactions

    return {
        "success": True
    }
# Serve the service worker from the site root so it can control /biz/.../pos
# (a worker served from /static/ can only control URLs under /static/).
@app.route('/service-worker.js')
def service_worker():
    resp = send_from_directory(os.path.join(BASE_DIR, 'static'), 'service-worker.js',
                               mimetype='application/javascript')
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

# ── RUN ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
