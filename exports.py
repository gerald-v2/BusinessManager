"""CSV exports for BizManager.

One page (/biz/<biz>/exports) lists every report; each report downloads from
/biz/<biz>/export/<kind>.csv

Common query options
    period = daily | weekly | monthly   (default monthly)
    date   = any date inside the period (default today). Weekly runs Monday-Sunday.
    view   = detail | summary           (only where it makes sense)

Files open cleanly in Excel / Google Sheets (UTF-8 with BOM) and text that
starts with = + - @ is neutralised so a customer called "=1+1" can't run as a
spreadsheet formula.
"""

import csv
import io
import re
from datetime import date, timedelta

from flask import Response, abort, flash, redirect, render_template, request, url_for

import biz_settings as bs
import business_finance as bf
import business_manager as bm
import crm as crm_mod
import employees as emp_mod
import Pos as pos_mod

PERIODS = ("daily", "weekly", "monthly")


# ── helpers ──────────────────────────────────────────────────────────────────
def _safe_cell(value):
    """Text that begins with a formula character gets a leading apostrophe."""
    if isinstance(value, str) and value and value[0] in "=+-@\t\r":
        return "'" + value
    return value


def _fmt(value):
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.2f}"
    if value is None:
        return ""
    return _safe_cell(value)


def csv_response(filename, header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_fmt(c) for c in row])
    data = "\ufeff" + buf.getvalue()                    # BOM -> Excel reads UTF-8
    resp = Response(data, mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-").lower() or "export"


def parse_date(text, default=None):
    try:
        return date.fromisoformat(str(text).strip()[:10])
    except (ValueError, TypeError):
        return default or bs.today()


def period_range(period, anchor):
    """(first_day, last_day) for the day / Mon-Sun week / calendar month of `anchor`."""
    if period == "daily":
        return anchor, anchor
    if period == "weekly":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    first = anchor.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return first, nxt - timedelta(days=1)


def _in_range(day_text, start, end):
    try:
        return start <= date.fromisoformat(str(day_text)[:10]) <= end
    except ValueError:
        return False


def _hours(record):
    try:
        return float(record.get("hours") or 0)
    except (TypeError, ValueError):
        return 0.0


def attendance_rows(biz, start, end):
    """All clock records for the business inside the date range, oldest first."""
    out = []
    for day, records in sorted(bf.load_attendance().get(biz, {}).items()):
        if not _in_range(day, start, end):
            continue
        for rec in records or []:
            out.append((day, rec))
    return out


def attendance_summary(biz, start, end):
    """One row per employee: days worked, total hours, open shifts."""
    names = [e.get("name", "") for e in bf.load_employees().get(biz, [])]
    stats = {n: {"days": set(), "hours": 0.0, "shifts": 0, "open": 0, "auto": 0} for n in names}
    for day, rec in attendance_rows(biz, start, end):
        name = rec.get("employee", "")
        s = stats.setdefault(name, {"days": set(), "hours": 0.0, "shifts": 0, "open": 0, "auto": 0})
        s["days"].add(day)
        s["shifts"] += 1
        s["hours"] += _hours(rec)
        if not rec.get("clock_out"):
            s["open"] += 1
        if rec.get("auto"):
            s["auto"] += 1
    return stats


def _sale_lines(sale):
    return sale.get("items") or []


def _sales_in_range(biz, start, end):
    sales = pos_mod.load_sales().get(biz, [])
    return [s for s in sales if _in_range(s.get("date", ""), start, end)]


# ── registration ─────────────────────────────────────────────────────────────
def register(app, require_biz_access, can_access, sym, load_biz):
    """Attach the export routes. The helpers come from app.py so permissions are
    identical to the rest of the program."""

    def _gate(biz, module):
        r = require_biz_access(biz)
        if r:
            return r
        if not can_access(biz, module):
            flash("You do not have access to that report.", "danger")
            return redirect(url_for("biz_dashboard", biz=biz))
        return None

    def _window():
        period = request.args.get("period", "monthly")
        if period not in PERIODS:
            period = "monthly"
        anchor = parse_date(request.args.get("date"))
        start, end = period_range(period, anchor)
        return period, anchor, start, end

    def _name(biz, kind, period, start, end):
        stamp = start.isoformat() if start == end else f"{start.isoformat()}_to_{end.isoformat()}"
        suffix = f"_{period}_{stamp}" if period else ""
        return f"{_slug(biz)}_{kind}{suffix}.csv"

    # ---------------------------------------------------------------- page
    @app.route("/biz/<biz>/exports")
    def exports_page(biz):
        r = require_biz_access(biz)
        if r:
            return r
        period, anchor, start, end = _window()
        allowed = {m: can_access(biz, m) for m in ("employees", "finance", "products", "crm")}
        if not any(allowed.values()):
            flash("You do not have access to any reports.", "danger")
            return redirect(url_for("biz_dashboard", biz=biz))
        return render_template("exports.html", biz=biz, period=period, anchor=anchor.isoformat(),
                               start=start, end=end, allowed=allowed)

    # ------------------------------------------------------- employees group
    @app.route("/biz/<biz>/export/attendance.csv")
    def export_attendance(biz):
        r = _gate(biz, "employees")
        if r:
            return r
        period, anchor, start, end = _window()
        view = request.args.get("view", "detail")
        if view == "summary":
            stats = attendance_summary(biz, start, end)
            rows = []
            for name, s in sorted(stats.items(), key=lambda kv: kv[0].lower()):
                days = len(s["days"])
                total = round(s["hours"], 2)
                rows.append([name, days, s["shifts"], total,
                             round(total / days, 2) if days else 0.0,
                             s["open"], s["auto"]])
            return csv_response(
                _name(biz, "attendance-summary", period, start, end),
                ["Employee", "Days Worked", "Shifts", "Total Hours", "Avg Hours / Day",
                 "Shifts Not Clocked Out", "Auto Clock-Outs"], rows)
        rows = []
        for day, rec in attendance_rows(biz, start, end):
            d = date.fromisoformat(day[:10])
            rows.append([day, d.strftime("%A"), rec.get("employee", ""),
                         rec.get("clock_in", ""), rec.get("clock_out", ""),
                         _hours(rec) if rec.get("clock_out") else "",
                         "Yes" if rec.get("auto") else "No",
                         "Complete" if rec.get("clock_out") else "Not clocked out"])
        rows.sort(key=lambda x: (x[0], x[3], x[2]))
        return csv_response(_name(biz, "attendance", period, start, end),
                            ["Date", "Day", "Employee", "Clock In", "Clock Out", "Hours",
                             "Auto Clock-Out", "Status"], rows)

    @app.route("/biz/<biz>/export/staff.csv")
    def export_staff(biz):
        r = _gate(biz, "employees")
        if r:
            return r
        rows = []
        for e in bf.load_employees().get(biz, []):
            rows.append([e.get("name", ""), e.get("username", ""), e.get("role", ""),
                         float(e.get("salary") or 0), ", ".join(e.get("permissions") or []),
                         e.get("notes", "")])           # passwords are never exported
        return csv_response(f"{_slug(biz)}_staff.csv",
                            ["Name", "Username", "Role", "Salary", "Access", "Notes"], rows)

    @app.route("/biz/<biz>/export/payroll.csv")
    def export_payroll(biz):
        r = _gate(biz, "employees")
        if r:
            return r
        period, anchor, start, end = _window()
        period = "monthly"
        start, end = period_range("monthly", anchor)
        advances = bf.load_advances()
        stats = attendance_summary(biz, start, end)
        rows = []
        for e in bf.load_employees().get(biz, []):
            name = e.get("name", "")
            salary = float(e.get("salary") or 0)
            owed = float(bf.get_outstanding_advance(biz, name, advances) or 0)
            st = stats.get(name, {"days": set(), "hours": 0.0})
            rows.append([name, e.get("role", ""), salary, owed, salary - owed,
                         len(st["days"]), round(st["hours"], 2)])
        return csv_response(_name(biz, "payroll", period, start, end),
                            ["Employee", "Role", "Salary", "Advances Outstanding", "Net Pay",
                             "Days Worked", "Hours Worked"], rows)

    @app.route("/biz/<biz>/export/advances.csv")
    def export_advances(biz):
        r = _gate(biz, "employees")
        if r:
            return r
        rows = [[a.get("date", ""), a.get("employee", ""), float(a.get("amount") or 0),
                 a.get("reason", ""), bool(a.get("repaid")), a.get("repaid_date") or ""]
                for a in bf.load_advances().get(biz, [])]
        rows.sort(key=lambda x: x[0], reverse=True)
        return csv_response(f"{_slug(biz)}_salary-advances.csv",
                            ["Date", "Employee", "Amount", "Reason", "Repaid", "Repaid Date"], rows)

    @app.route("/biz/<biz>/export/leave.csv")
    def export_leave(biz):
        r = _gate(biz, "employees")
        if r:
            return r
        rows = [[l.get("employee", ""), l.get("type", ""), l.get("start", ""), l.get("end", ""),
                 l.get("days", ""), l.get("status", ""), l.get("reason", ""), l.get("applied", "")]
                for l in emp_mod.load_leave().get(biz, [])]
        return csv_response(f"{_slug(biz)}_leave.csv",
                            ["Employee", "Type", "Start", "End", "Days", "Status", "Reason",
                             "Applied"], rows)

    # ------------------------------------------------------------ sales group
    @app.route("/biz/<biz>/export/sales.csv")
    def export_sales(biz):
        r = _gate(biz, "finance")
        if r:
            return r
        period, anchor, start, end = _window()
        view = request.args.get("view", "receipts")
        sales = _sales_in_range(biz, start, end)
        sales.sort(key=lambda s: (s.get("date", ""), s.get("time", "")))
        if view == "items":
            rows = []
            for s in sales:
                for it in _sale_lines(s):
                    rows.append([s.get("receipt_no", ""), s.get("date", ""), s.get("time", ""),
                                 it.get("plu", ""), it.get("product", ""), it.get("variant", ""),
                                 it.get("qty", 0), float(it.get("unit_price") or 0),
                                 float(it.get("subtotal") or 0), bool(s.get("refunded"))])
            return csv_response(_name(biz, "sales-items", period, start, end),
                                ["Receipt No", "Date", "Time", "PLU", "Product", "Variant", "Qty",
                                 "Unit Price", "Line Total", "Refunded"], rows)
        rows = []
        for s in sales:
            items = "; ".join(f"{i.get('qty', 0)} x {i.get('product', '')} {i.get('variant', '')}".strip()
                              for i in _sale_lines(s))
            rows.append([s.get("receipt_no", ""), s.get("date", ""), s.get("time", ""),
                         s.get("cashier", ""), s.get("customer") or "", s.get("payment", ""),
                         float(s.get("subtotal") or 0), float(s.get("discount_amt") or 0),
                         float(s.get("tax_amt") or 0), float(s.get("total") or 0),
                         float(s.get("tendered") or s.get("payment_amount") or 0),
                         float(s.get("change") or 0), bool(s.get("refunded")), items])
        return csv_response(_name(biz, "sales", period, start, end),
                            ["Receipt No", "Date", "Time", "Cashier", "Customer", "Payment",
                             "Subtotal", "Discount", "VAT", "Total", "Tendered", "Change",
                             "Refunded", "Items"], rows)

    @app.route("/biz/<biz>/export/daily-summary.csv")
    def export_daily_summary(biz):
        """End-of-day style totals: one row per day and payment method."""
        r = _gate(biz, "finance")
        if r:
            return r
        period, anchor, start, end = _window()
        agg = {}
        for s in _sales_in_range(biz, start, end):
            key = (s.get("date", ""), s.get("payment", "") or "Unknown")
            a = agg.setdefault(key, {"n": 0, "sub": 0.0, "disc": 0.0, "tax": 0.0, "total": 0.0,
                                     "ref_n": 0, "ref_total": 0.0})
            if s.get("refunded"):
                a["ref_n"] += 1
                a["ref_total"] += float(s.get("total") or 0)
                continue
            a["n"] += 1
            a["sub"] += float(s.get("subtotal") or 0)
            a["disc"] += float(s.get("discount_amt") or 0)
            a["tax"] += float(s.get("tax_amt") or 0)
            a["total"] += float(s.get("total") or 0)
        rows = [[d, p, a["n"], a["sub"], a["disc"], a["tax"], a["total"], a["ref_n"], a["ref_total"]]
                for (d, p), a in sorted(agg.items())]
        return csv_response(_name(biz, "daily-summary", period, start, end),
                            ["Date", "Payment Method", "Sales", "Subtotal", "Discounts", "VAT",
                             "Total Sales", "Refunds", "Refunded Amount"], rows)

    # -------------------------------------------------------------- inventory
    @app.route("/biz/<biz>/export/stock.csv")
    def export_stock(biz):
        r = _gate(biz, "products")
        if r:
            return r
        products = (load_biz().get(biz, {}) or {}).get("products", {}) or {}
        rows = []
        for pname in sorted(products, key=str.lower):
            p = products[pname]
            for v in p.get("variants", []) or []:
                units = int(v.get("units") or 0)
                price = bm.variant_price(p, v)
                cost = bm.variant_cost(p, v)
                status = "Out of stock" if units <= 0 else ("Low" if units < 5 else "OK")
                rows.append([pname, v.get("name", ""), str(v.get("PLU", "")), price, cost, units,
                             round(cost * units, 2), round(price * units, 2), status])
        return csv_response(f"{_slug(biz)}_stock.csv",
                            ["Product", "Variant", "PLU", "Price", "Cost", "Units",
                             "Stock Value (Cost)", "Stock Value (Retail)", "Status"], rows)

    # -------------------------------------------------------------- customers
    @app.route("/biz/<biz>/export/customers.csv")
    def export_customers(biz):
        r = _gate(biz, "crm")
        if r:
            return r
        rows = []
        for c in crm_mod.load_customers().get(biz, []):
            purchases = c.get("purchases") or []
            spent = 0.0
            for p in purchases:
                try:
                    spent += float(p.get("total", 0)) if isinstance(p, dict) else 0.0
                except (TypeError, ValueError):
                    pass
            rows.append([c.get("name", ""), c.get("phone", ""), c.get("email", ""),
                         c.get("dob", ""), c.get("joined", ""), int(c.get("points") or 0),
                         len(purchases), spent, c.get("notes", "")])
        return csv_response(f"{_slug(biz)}_customers.csv",
                            ["Name", "Phone", "Email", "Date of Birth", "Joined", "Points",
                             "Purchases", "Total Spent", "Notes"], rows)
