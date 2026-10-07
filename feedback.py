"""
Customer feedback for BizManager.

Stored in sentiment.json (same file the old "Customer Feedback Log" used, so
nothing already recorded is lost):

    { "House Of Stembii": [
        {"id": "a1b2c3d4", "rating": 5, "review": "...", "date": "2026-10-06",
         "customer": "Herald", "product": "Lights", "source": "In shop",
         "resolved": false}, ... ] }

Old entries (rating / review / date only) keep working - missing fields are
treated as "unknown".
"""

import json
import os
import re
import threading
import uuid

import biz_settings as bs

FEEDBACK_FILE = "sentiment.json"
SOURCES = ["In shop", "WhatsApp", "Facebook", "Phone call", "Other"]
_lock = threading.RLock()

# theme -> words that mention it (lower case)
THEMES = {
    "Price": ["price", "prices", "expensive", "cheap", "overpriced", "affordable", "costly", "value"],
    "Service": ["service", "staff", "rude", "friendly", "helpful", "slow", "attitude", "polite", "waiting", "queue"],
    "Quality": ["quality", "broke", "broken", "damaged", "defective", "durable", "fresh", "stale", "fake", "faded"],
    "Stock": ["stock", "sold out", "unavailable", "out of", "didn't have", "did not have", "range", "selection"],
    "Delivery": ["delivery", "deliver", "late", "delayed", "fast", "arrived", "waiting"],
    "Cleanliness": ["clean", "dirty", "smell", "tidy", "messy"],
}


def _load_all():
    try:
        with open(FEEDBACK_FILE, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_all(data):
    tmp = FEEDBACK_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, FEEDBACK_FILE)


def sentiment_label(rating):
    if rating >= 4:
        return "positive"
    if rating >= 3:
        return "neutral"
    return "negative"


def load(biz):
    """Entries for a business, oldest first. Gives old entries an id."""
    with _lock:
        data = _load_all()
        entries = data.get(biz, [])
        if not isinstance(entries, list):
            entries = []
        changed = False
        for e in entries:
            if not e.get("id"):
                e["id"] = uuid.uuid4().hex[:8]
                changed = True
            try:
                e["rating"] = max(1.0, min(5.0, float(e.get("rating", 0))))
            except (TypeError, ValueError):
                e["rating"] = 3.0
                changed = True
            e.setdefault("review", "")
            e.setdefault("resolved", False)
        if changed:
            data[biz] = entries
            _save_all(data)
        return entries


def add(biz, rating, review, customer="", product="", source="In shop"):
    try:
        rating = int(round(float(rating)))
    except (TypeError, ValueError):
        return None
    if not 1 <= rating <= 5:
        return None
    review = (review or "").strip()[:600]
    if not review and rating >= 4:
        review = "(no comment)"
    with _lock:
        data = _load_all()
        entries = data.setdefault(biz, [])
        entry = {
            "id": uuid.uuid4().hex[:8],
            "rating": rating,
            "review": review,
            "date": bs.today().isoformat(),
            "customer": (customer or "").strip()[:60],
            "product": (product or "").strip()[:80],
            "source": source if source in SOURCES else "Other",
            "resolved": rating >= 3,       # only unhappy customers need follow-up
        }
        entries.append(entry)
        _save_all(data)
    return entry


def update(biz, entry_id, **changes):
    with _lock:
        data = _load_all()
        for e in data.get(biz, []):
            if e.get("id") == entry_id:
                e.update(changes)
                _save_all(data)
                return True
    return False


def delete(biz, entry_id):
    with _lock:
        data = _load_all()
        before = len(data.get(biz, []))
        data[biz] = [e for e in data.get(biz, []) if e.get("id") != entry_id]
        if len(data[biz]) != before:
            _save_all(data)
            return True
    return False


def stats(entries):
    """Average, distribution, month-on-month and themes."""
    n = len(entries)
    out = {"count": n, "avg": None, "dist": {i: 0 for i in range(1, 6)},
           "pct_positive": 0, "needs_attention": 0, "this_month": None,
           "last_month": None, "themes": [], "products": []}
    if not n:
        return out
    out["avg"] = round(sum(e["rating"] for e in entries) / n, 2)
    for e in entries:
        out["dist"][int(round(e["rating"]))] += 1
    out["pct_positive"] = round(sum(1 for e in entries if e["rating"] >= 4) / n * 100)
    out["needs_attention"] = sum(1 for e in entries if e["rating"] <= 2 and not e.get("resolved"))

    today = bs.today()
    this_key = today.strftime("%Y-%m")
    prev = (today.replace(day=1) - __import__("datetime").timedelta(days=1)).strftime("%Y-%m")
    def month_avg(key):
        vals = [e["rating"] for e in entries if str(e.get("date", "")).startswith(key)]
        return (round(sum(vals) / len(vals), 2), len(vals)) if vals else None
    out["this_month"], out["last_month"] = month_avg(this_key), month_avg(prev)

    themes = []
    for name, words in THEMES.items():
        hits = []
        for e in entries:
            text = e.get("review", "").lower()
            if any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words):
                hits.append(e["rating"])
        if hits:
            themes.append({"name": name, "mentions": len(hits),
                           "avg": round(sum(hits) / len(hits), 1)})
    out["themes"] = sorted(themes, key=lambda t: -t["mentions"])[:6]

    by_product = {}
    for e in entries:
        if e.get("product"):
            by_product.setdefault(e["product"], []).append(e["rating"])
    out["products"] = sorted(
        [{"name": k, "count": len(v), "avg": round(sum(v) / len(v), 1)} for k, v in by_product.items()],
        key=lambda p: (-p["count"], p["name"]))[:6]
    return out


def draft_reply(entry, business):
    """Polite reply text. Uses the AI if configured, otherwise a sensible template."""
    name = (entry.get("customer") or "").strip() or "there"
    rating = entry.get("rating", 3)
    comment = entry.get("review", "")
    try:
        import api_handler
        if getattr(api_handler, "client", None):
            prompt = (
                f"Write a short, warm, professional reply (max 70 words) from the owner of "
                f"'{business}' to this customer feedback. Customer: {name}. Rating: {int(rating)}/5. "
                f"Comment: \"{comment}\". "
                + ("Thank them and invite them back." if rating >= 4 else
                   "Apologise sincerely, address the specific issue and offer to put it right. "
                   "Do not make promises about refunds. Plain text only.")
            )
            text = api_handler.call_api(prompt, temperature=0.6)
            if text and "did not return" not in text:
                return text
    except Exception as exc:
        print(f"[feedback] AI reply failed: {exc}")
    if rating >= 4:
        return (f"Hi {name}, thank you so much for the kind feedback! We're delighted you had a "
                f"good experience at {business} and we look forward to seeing you again soon.")
    if rating >= 3:
        return (f"Hi {name}, thank you for your feedback. We're glad parts of your visit went well "
                f"and we'd love to hear how we can make it better next time.")
    return (f"Hi {name}, we're sorry your experience at {business} fell short. Thank you for telling "
            f"us - we take this seriously and would like to put things right. "
            f"Please contact us so we can sort this out.")
