# ============================================================
# BIZMANAGER API HANDLER
# OpenAI text + image generation
# ============================================================

import re
import os
import base64
import time

import business_manager
from openai import OpenAI


# ============================================================
# CONFIGURATION
# ============================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

OPENAI_TEXT_MODEL = os.environ.get(
    "OPENAI_TEXT_MODEL",
    "gpt-5.6-luna"
)

OPENAI_IMAGE_MODEL = os.environ.get(
    "OPENAI_IMAGE_MODEL",
    "gpt-image-2"
)


# ============================================================
# OPENAI CLIENT
# ============================================================

client = None

if OPENAI_API_KEY:
    client = OpenAI(
        api_key=OPENAI_API_KEY
    )


# ============================================================
# GLOBAL BUSINESS DATA
# ============================================================

data = {}


# ============================================================
# TEXT GENERATION
# ============================================================

def call_api(prompt, temperature=0.9):
    """
    Generate text using OpenAI.

    If OPENAI_API_KEY is not configured,
    the application automatically uses demo mode.
    """

    if not client:
        return _demo_response(prompt)

    try:

        response = client.responses.create(
            model=OPENAI_TEXT_MODEL,
            input=prompt,
            max_output_tokens=1024
        )

        answer = response.output_text.strip()

        if not answer:
            return "The AI did not return a response."

        return answer

    except Exception as e:

        print(
            f"[api_handler] OpenAI text error: {e}"
        )

        return _demo_response(prompt)


# ============================================================
# IMAGE GENERATION
# ============================================================

def call_openai_image(prompt):
    """
    Generate an image using OpenAI.

    Returns:

        (image_bytes, mime_type)

    on success.

    Returns:

        (None, error_message)

    on failure.
    """

    if not client:

        return (
            None,
            "OPENAI_API_KEY is not configured."
        )

    try:

        result = client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024"
        )

        if not result.data:

            return (
                None,
                "OpenAI returned no image data."
            )

        image_data = result.data[0].b64_json

        if not image_data:

            return (
                None,
                "OpenAI returned an empty image."
            )

        image_bytes = base64.b64decode(
            image_data
        )

        return (
            image_bytes,
            "image/png"
        )

    except Exception as e:

        print(
            f"[api_handler] OpenAI image error: {e}"
        )

        return (
            None,
            "Image generation failed."
        )


# ============================================================
# SAVE GENERATED IMAGE
# ============================================================

def save_generated_image(
    img_bytes,
    mime_type,
    biz,
    static_dir="static/generated"
):
    """
    Save a generated image to the static folder.

    Returns the URL that can be used by <img src="">.
    """

    if not img_bytes:
        return None

    if "png" in mime_type:
        ext = "png"

    elif "jpeg" in mime_type or "jpg" in mime_type:
        ext = "jpg"

    else:
        ext = "png"

    safe_biz = re.sub(
        r"[^A-Za-z0-9_-]",
        "_",
        biz
    )

    folder = os.path.join(
        static_dir,
        safe_biz
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    filename = (
        f"{int(time.time() * 1000)}.{ext}"
    )

    path = os.path.join(
        folder,
        filename
    )

    with open(path, "wb") as f:

        f.write(img_bytes)

    return "/" + path.replace(
        os.sep,
        "/"
    )


# ============================================================
# DEMO FALLBACK
# ============================================================

def _demo_response(prompt):
    """
    Demo response used when an OpenAI API key
    isn't configured or an API request fails.
    """

    prompt_lower = prompt.lower()


    if "email" in prompt_lower:

        return (
            "📧 [Demo Mode — Add OPENAI_API_KEY "
            "to enable AI generation]\n\n"

            "Subject: Exciting News from Our Store!\n\n"

            "Dear Valued Customer,\n\n"

            "We're thrilled to share our latest "
            "offers and updates with you. As a "
            "loyal member of our community, you're "
            "the first to hear about our special "
            "promotions.\n\n"

            "Visit us today and discover amazing deals!\n\n"

            "Best regards,\n"
            "The Team"
        )


    if (
        "caption" in prompt_lower
        or "social" in prompt_lower
    ):

        return (
            "📱 [Demo Mode — Add OPENAI_API_KEY "
            "to enable AI generation]\n\n"

            "✨ Bringing you quality you can count on! "
            "Stop by and experience the difference.\n\n"

            "Tag a friend who needs to know about us! 👇\n\n"

            "#LocalBusiness #Quality #Community"
        )


    if "plan" in prompt_lower:

        return (
            "📋 [Demo Mode — Add OPENAI_API_KEY "
            "to enable AI generation]\n\n"

            "Month 1: Build your brand presence — "
            "set up social media profiles, post 3x/week, "
            "and engage with your local community.\n\n"

            "Month 2: Launch promotions — run a referral "
            "discount, collect customer emails, and send "
            "your first newsletter.\n\n"

            "Month 3: Measure & scale — review what's "
            "working, focus on your top channels, and "
            "consider paid advertising."
        )


    return (
        "🧠 [Demo Mode — Add OPENAI_API_KEY "
        "to enable AI generation]\n\n"

        "The AI Business Assistant is currently "
        "running in demo mode."
    )


# ============================================================
# LOAD BUSINESS DATA
# ============================================================

def fetch_data():

    global data

    data = business_manager.load_business()

    return data


# ============================================================
# EMAIL VALIDATION
# ============================================================

def email_verification(mail):

    pattern = (
        r'^[^@\s]+@[^@\s]+\.[^@\s]+$'
    )

    return bool(
        re.match(
            pattern,
            mail.strip()
        )
    )


# ============================================================
# AI BUSINESS ASSISTANT
# ============================================================

def ask_business_ai(
    user_message,
    business_data
):

    prompt = f"""
You are the AI Business Assistant inside BizManager.

Your job is to help a business owner understand
and improve their business.

You have been given business data below.

BUSINESS DATA:
{business_data}

BUSINESS OWNER'S QUESTION:
{user_message}

INSTRUCTIONS:

1. Use the provided business data.
2. Do not invent numbers.
3. If information is missing, clearly say that
   the information is unavailable.
4. Give practical business advice.
5. Keep the answer easy to understand.
6. Use numbers from the data when useful.
7. Point out important problems or opportunities.
8. If discussing sales, inventory, finance,
   customers, employees, or marketing, explain
   what the business owner should consider doing.
9. Do not claim that you performed an action
   unless the system actually performed it.

Give a useful answer to the business owner.
"""

    return call_api(prompt)


# ============================================================
# FUTURE BUSINESS INTELLIGENCE FUNCTIONS
# ============================================================

def industry_trends(industry):
    pass


def level_of_competitors(industry):
    pass


def create_marketing():
    pass