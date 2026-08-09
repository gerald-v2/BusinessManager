# HANDLING THE PROGRAM FUNCTIONALITY
import re
import os
import json
import base64
import time
import urllib.request
import urllib.error
import business_manager

data = {}

# ── GEMINI (text + image) ───────────────────────────────────────────────────
# Set GEMINI_API_KEY in your environment (Render dashboard / .env).
# Model IDs are overridable via env vars since Google renames/retires them
# periodically — check https://ai.google.dev/gemini-api/docs/models if a
# call starts failing with a 404.

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _gemini_request(model, body, timeout=60):
    req = urllib.request.Request(
        f"{GEMINI_BASE}/{model}:generateContent?key={GEMINI_API_KEY}",
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_api(prompt, temperature=0.9):
    """Text generation (email/caption/plan copy) via Gemini. Falls back to demo text."""
    if not GEMINI_API_KEY:
        return _demo_response(prompt)
    try:
        result = _gemini_request(GEMINI_TEXT_MODEL, {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 1024},
        })
        parts = result["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except Exception as e:
        print(f"[api_handler] Gemini text error: {e}")
        return _demo_response(prompt)


def call_gemini_image(prompt):
    """
    Image generation via Gemini. Returns (image_bytes, mime_type) on success,
    or (None, error_message) on failure — callers must handle the failure
    case explicitly rather than silently showing placeholder text, since a
    business posting a fake product photo is a real-world problem.
    """
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY is not set."
    try:
        result = _gemini_request(GEMINI_IMAGE_MODEL, {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }, timeout=90)
        parts = result["candidates"][0]["content"]["parts"]
        for p in parts:
            inline = p.get("inlineData") or p.get("inline_data")
            if inline and inline.get("data"):
                img_bytes = base64.b64decode(inline["data"])
                mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                return img_bytes, mime
        return None, "Gemini returned no image data for this prompt."
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")[:300]
        print(f"[api_handler] Gemini image HTTP error: {e.code} {detail}")
        return None, f"Image generation failed ({e.code})."
    except Exception as e:
        print(f"[api_handler] Gemini image error: {e}")
        return None, "Image generation failed."


def save_generated_image(img_bytes, mime_type, biz, static_dir="static/generated"):
    """Write generated image bytes to disk and return the relative static path for <img src>."""
    ext = "png" if "png" in mime_type else "jpg"
    safe_biz = re.sub(r"[^A-Za-z0-9_-]", "_", biz)
    folder = os.path.join(static_dir, safe_biz)
    os.makedirs(folder, exist_ok=True)
    filename = f"{int(time.time())}.{ext}"
    path = os.path.join(folder, filename)
    with open(path, "wb") as f:
        f.write(img_bytes)
    return "/" + path.replace(os.sep, "/")


# ── DEMO FALLBACK ────────────────────────────────────────────────────────────

def _demo_response(prompt):
    """Return a helpful placeholder when GEMINI_API_KEY is not configured."""
    if "email" in prompt.lower():
        return (
            "📧 [Demo Mode — Add GEMINI_API_KEY to enable AI generation]\n\n"
            "Subject: Exciting News from Our Store!\n\n"
            "Dear Valued Customer,\n\n"
            "We're thrilled to share our latest offers and updates with you. "
            "As a loyal member of our community, you're the first to hear about our "
            "special promotions. Visit us today and discover amazing deals!\n\n"
            "Best regards,\nThe Team"
        )
    elif "caption" in prompt.lower() or "social" in prompt.lower():
        return (
            "📱 [Demo Mode — Add GEMINI_API_KEY to enable AI generation]\n\n"
            "✨ Bringing you quality you can count on! Stop by and experience "
            "the difference. Tag a friend who needs to know about us! 👇\n"
            "#LocalBusiness #Quality #Community"
        )
    elif "plan" in prompt.lower():
        return (
            "📋 [Demo Mode — Add GEMINI_API_KEY to enable AI generation]\n\n"
            "Month 1: Build your brand presence — set up social media profiles, "
            "post 3x/week, engage with local community groups.\n\n"
            "Month 2: Launch promotions — run a referral discount, collect customer "
            "emails, send your first newsletter.\n\n"
            "Month 3: Measure & scale — review what's working, double down on "
            "top channels, consider paid ads on Facebook/Instagram."
        )
    else:
        return (
            "🖼️ [Demo Mode — Add GEMINI_API_KEY to enable AI generation]\n\n"
            "Concept: A bright, inviting image featuring your products front-and-centre "
            "with warm lighting. Include your logo in the corner and a clear call-to-action "
            "text overlay. Use brand colours for consistency across all marketing materials."
        )


def fetch_data():
    global data
    data = business_manager.load_business()
    return data


def email_verification(mail):
    pattern = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
    return bool(re.match(pattern, mail.strip()))


def industry_trends(industry):
    pass


def level_of_competitors(industry):
    pass


def create_marketing():
    pass
