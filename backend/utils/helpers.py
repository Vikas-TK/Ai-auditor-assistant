import re
from datetime import datetime
from typing import Optional

def get_gemini_client():
    """
    Builds a genai.Client configured to fail fast rather than retrying for up
    to ~60s (the SDK default: 5 attempts, exponential backoff to a 60s cap).
    Every caller already has a graceful canned-text fallback for Gemini
    errors, so a slow/exhausted-quota call should reach that fallback in a
    few seconds, not leave the request hanging.
    """
    from google import genai
    from google.genai import types
    from backend.config import settings

    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=10_000,
            # A quota-exceeded (429) error won't resolve within the lifetime of one
            # request, so retrying it is pure wasted latency — fail once, fast, and
            # let the caller's fallback logic (and any batch-level circuit breaker)
            # take over immediately instead of the SDK's default 5-attempt/60s backoff.
            retry_options=types.HttpRetryOptions(attempts=1)
        )
    )


def format_currency(amount: float) -> str:
    """Formats float value as INR (Rupees) currency string."""
    try:
        return f"₹{amount:,.2f}"
    except (ValueError, TypeError):
        return "₹0.00"


def parse_date_safe(date_str: str) -> Optional[datetime]:
    """Safely parses common date format strings into a datetime object."""
    if not date_str:
        return None
    date_str = date_str.strip()
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    return None

def clean_vendor_name(name: str) -> str:
    """Cleans vendor string for fuzzy matching (removes Inc, LLC, Ltd, Corp)."""
    if not name:
        return ""
    cleaned = name.upper()
    cleaned = re.sub(r'\b(INC|LLC|LTD|CORP|CORPORATION|CO|SERVICES|GROUP)\b', '', cleaned)
    cleaned = re.sub(r'[^A-Z0-9\s]', '', cleaned)
    return cleaned.strip()
