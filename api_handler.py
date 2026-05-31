# HANDLING THE PROGRAM FUNCTIONALITY
import re
import os
import json
import business_manager

data = {}

def call_api(prompt):
    """Call Claude API via Anthropic. Falls back gracefully if unavailable."""
    try:
        import urllib.request
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return _demo_response(prompt)
        
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")
        
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["content"][0]["text"]
    except Exception as e:
        return _demo_response(prompt)


def _demo_response(prompt):
    """Return a helpful placeholder when the API key is not configured."""
    if "email" in prompt.lower():
        return (
            "📧 [Demo Mode — Add ANTHROPIC_API_KEY to enable AI generation]\n\n"
            "Subject: Exciting News from Our Store!\n\n"
            "Dear Valued Customer,\n\n"
            "We're thrilled to share our latest offers and updates with you. "
            "As a loyal member of our community, you're the first to hear about our "
            "special promotions. Visit us today and discover amazing deals!\n\n"
            "Best regards,\nThe Team"
        )
    elif "caption" in prompt.lower() or "social" in prompt.lower():
        return (
            "📱 [Demo Mode — Add ANTHROPIC_API_KEY to enable AI generation]\n\n"
            "✨ Bringing you quality you can count on! Stop by and experience "
            "the difference. Tag a friend who needs to know about us! 👇\n"
            "#LocalBusiness #Quality #Community"
        )
    elif "plan" in prompt.lower():
        return (
            "📋 [Demo Mode — Add ANTHROPIC_API_KEY to enable AI generation]\n\n"
            "Month 1: Build your brand presence — set up social media profiles, "
            "post 3x/week, engage with local community groups.\n\n"
            "Month 2: Launch promotions — run a referral discount, collect customer "
            "emails, send your first newsletter.\n\n"
            "Month 3: Measure & scale — review what's working, double down on "
            "top channels, consider paid ads on Facebook/Instagram."
        )
    else:
        return (
            "🖼️ [Demo Mode — Add ANTHROPIC_API_KEY to enable AI generation]\n\n"
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
