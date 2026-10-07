"""
Per-business settings for BizManager.

Stored in biz_settings.json (backed up to Firebase like the other JSON files):

    {
      "House Of Stembii": {
          "vat_enabled": true, "vat_pct": 15.0, "vat_inclusive": false,
          "receipt_footer": "...", "paper_width": 58,
          "daily_costs_enabled": true,
          "daily_costs": [{"id": "ab12", "name": "Rent", "amount": 300, "period": "month"}],
          ...
      }
    }

Also contains:
  * now()            - current LOCAL business time (Africa/Harare by default)
  * vat helpers
  * fixed (recurring) cost accrual - accrue_fixed_costs(biz)
"""

import copy
import datetime
import json
import os
import threading
import uuid
from datetime import timedelta

SETTINGS_FILE = "biz_settings.json"
_lock = threading.RLock()

DEFAULTS = {
    # --- VAT -------------------------------------------------------------
    "vat_enabled": False,
    "vat_pct": 15.0,          # set to your registered VAT rate
    "vat_inclusive": False,   # False = VAT added on top of prices, True = prices already include VAT
    "vat_number": "",         # printed on receipts (optional)
    # --- Receipt ---------------------------------------------------------
    "receipt_header": "",     # extra line under the business name (e.g. slogan)
    "receipt_address": "",
    "receipt_phone": "",
    "receipt_footer": "Thank you for your purchase!",
    "paper_width": 58,        # 58 or 80 (mm) - thermal roll width
    "printer_cut": True,      # send a paper-cut command after each receipt
    "auto_print": False,      # print automatically after every sale
    # --- Discounts -------------------------------------------------------
    "max_staff_discount_pct": 100.0,   # cap on manual discounts for non-manager staff
    # --- Fixed (recurring) costs ----------------------------------------
    "daily_costs_enabled": False,
    "daily_costs": [],                 # [{id, name, amount, period: day|week|month, active}]
    "daily_costs_days": [0, 1, 2, 3, 4, 5, 6],   # weekdays the business operates (Mon=0)
    "daily_costs_last_accrued": None,  # ISO date of the last day already charged
    "daily_costs_log": [],             # newest last: [{date, amount, items}]
}

PERIODS = ("day", "week", "month")
MAX_LOG = 120
MAX_BACKFILL_DAYS = 62


# ---------------------------------------------------------------------------
# Local time
# ---------------------------------------------------------------------------

def now():
    """Current local business time as a naive datetime.

    Render's servers run on UTC, Zimbabwe is UTC+2 - without this, receipts and
    daily summaries are two hours behind. Override with APP_TIMEZONE
    (e.g. 'Africa/Johannesburg') or APP_UTC_OFFSET (hours) if zoneinfo is missing.
    """
    tzname = os.environ.get("APP_TIMEZONE", "Africa/Harare")
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(tzname)).replace(tzinfo=None)
    except Exception:
        try:
            offset = float(os.environ.get("APP_UTC_OFFSET", "2"))
        except ValueError:
            offset = 2.0
        return datetime.datetime.utcnow() + timedelta(hours=offset)


def today():
    return now().date()


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _load_all():
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_all(data):
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, SETTINGS_FILE)


def get(biz):
    """Settings for a business with defaults filled in (always safe to call)."""
    with _lock:
        stored = _load_all().get(biz, {})
    cfg = copy.deepcopy(DEFAULTS)
    if isinstance(stored, dict):
        cfg.update(stored)
    # normalise types so templates / maths never blow up
    cfg["vat_pct"] = _num(cfg.get("vat_pct"), DEFAULTS["vat_pct"], 0, 100)
    cfg["max_staff_discount_pct"] = _num(cfg.get("max_staff_discount_pct"), 100.0, 0, 100)
    cfg["paper_width"] = 80 if str(cfg.get("paper_width")) == "80" else 58
    cfg["vat_enabled"] = bool(cfg.get("vat_enabled"))
    cfg["vat_inclusive"] = bool(cfg.get("vat_inclusive"))
    if not isinstance(cfg.get("daily_costs"), list):
        cfg["daily_costs"] = []
    if not isinstance(cfg.get("daily_costs_log"), list):
        cfg["daily_costs_log"] = []
    return cfg


def update(biz, changes):
    """Merge `changes` into the business' stored settings and save."""
    with _lock:
        data = _load_all()
        entry = data.get(biz)
        if not isinstance(entry, dict):
            entry = {}
        entry.update(changes)
        data[biz] = entry
        _save_all(data)
    return get(biz)


def _num(value, default, lo=None, hi=None):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def parse_number(text, default=None, lo=None, hi=None):
    """Parse user text such as '12', '12.5', '1 200,50' safely."""
    if text is None:
        return default
    s = str(text).strip().replace(" ", "")
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    return _num(s, default, lo, hi)


# ---------------------------------------------------------------------------
# VAT / totals
# ---------------------------------------------------------------------------

def compute_totals(subtotal, discount_type="none", discount_value=0.0,
                   vat_enabled=False, vat_pct=0.0, vat_inclusive=False):
    """Pure maths for a sale. All amounts in the business currency.

    discount_type: 'none' | 'percent' | 'amount'
    Order: discount first, then VAT.
      * VAT on top:  total = (subtotal - discount) + VAT
      * VAT inclusive: prices already contain VAT; total = subtotal - discount,
        and VAT is the part of that total that is tax.
    """
    subtotal = round(float(subtotal or 0), 2)
    value = max(0.0, float(discount_value or 0))
    if discount_type == "percent":
        disc = round(subtotal * min(value, 100.0) / 100.0, 2)
    elif discount_type == "amount":
        disc = round(value, 2)
    else:
        disc = 0.0
    disc = min(max(disc, 0.0), subtotal)
    after = round(subtotal - disc, 2)

    rate = float(vat_pct or 0)
    if vat_enabled and rate > 0:
        if vat_inclusive:
            vat = round(after - after / (1 + rate / 100.0), 2)
            total = after
        else:
            vat = round(after * rate / 100.0, 2)
            total = round(after + vat, 2)
    else:
        vat = 0.0
        total = after

    net = round(total - vat, 2)
    eff_pct = round(disc / subtotal * 100.0, 2) if subtotal > 0 else 0.0
    return {
        "subtotal": subtotal,
        "discount_amt": disc,
        "discount_pct": eff_pct,
        "after_discount": after,
        "vat_amt": vat,
        "total": total,
        "net": net,
    }


# ---------------------------------------------------------------------------
# Fixed (recurring) costs
# ---------------------------------------------------------------------------

def _days_in_month(d):
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (nxt - timedelta(days=1)).day


def daily_amount(item, on_date):
    """What one cost item charges for a single day."""
    amount = _num(item.get("amount"), 0.0, 0)
    period = item.get("period", "day")
    if period == "week":
        return round(amount / 7.0, 2)
    if period == "month":
        return round(amount / _days_in_month(on_date), 2)
    return round(amount, 2)


def daily_cost_preview(cfg, on_date=None):
    """Total that will be charged for a normal operating day."""
    on_date = on_date or today()
    return round(sum(daily_amount(i, on_date) for i in cfg.get("daily_costs", [])
                     if i.get("active", True)), 2)


def new_cost_item(name, amount, period="day"):
    return {
        "id": uuid.uuid4().hex[:8],
        "name": (name or "").strip()[:60],
        "amount": round(float(amount), 2),
        "period": period if period in PERIODS else "day",
        "active": True,
    }


def accrue_fixed_costs(biz):
    """Charge every operating day since the last accrual (up to today).

    Called lazily whenever someone opens a business page, so it works on hosts
    that sleep (no background scheduler needed) and never double-charges: the
    last charged date is stored.  Turning the feature on starts charging from
    TODAY - it never back-charges history.

    Returns the total amount charged by this call (0 if nothing was due).
    """
    with _lock:
        data = _load_all()
        entry = data.get(biz)
        if not isinstance(entry, dict) or not entry.get("daily_costs_enabled"):
            return 0.0
        cfg = get(biz)
        items = [i for i in cfg["daily_costs"] if i.get("active", True)]
        t = today()
        last_raw = cfg.get("daily_costs_last_accrued")
        try:
            last = datetime.date.fromisoformat(last_raw) if last_raw else None
        except ValueError:
            last = None
        if last is None:
            # first run after switching on: start charging from today
            last = t - timedelta(days=1)
        if last >= t:
            return 0.0
        start = max(last + timedelta(days=1), t - timedelta(days=MAX_BACKFILL_DAYS - 1))
        days_on = set(cfg.get("daily_costs_days") or range(7))

        charged_total = 0.0
        log = list(cfg.get("daily_costs_log", []))
        day = start
        while day <= t:
            if items and day.weekday() in days_on:
                parts = [{"name": i["name"], "amount": daily_amount(i, day)} for i in items]
                parts = [p for p in parts if p["amount"] > 0]
                amount = round(sum(p["amount"] for p in parts), 2)
                if amount > 0:
                    log.append({"date": day.isoformat(), "amount": amount, "items": parts})
                    charged_total += amount
            day += timedelta(days=1)

        entry["daily_costs_last_accrued"] = t.isoformat()
        entry["daily_costs_log"] = log[-MAX_LOG:]
        data[biz] = entry
        _save_all(data)

    charged_total = round(charged_total, 2)
    if charged_total > 0:
        try:
            import business_finance as bf
            bf.business_finance = bf.load_business_finance()
            bf.add_costs(biz, charged_total, "Fixed daily costs")
        except Exception as exc:  # never break a page because of bookkeeping
            print(f"[biz_settings] could not record fixed costs for {biz}: {exc}")
    return charged_total
