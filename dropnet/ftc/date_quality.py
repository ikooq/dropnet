"""Validate source dates without modifying them."""
from datetime import date


def chronology(filing, call):
    """Return a status; missing/invalid values cannot establish chronology."""
    if not filing or not call:
        return 'missing'
    try:
        filed = date.fromisoformat(filing)
        called = date.fromisoformat(call)
    except (ValueError, TypeError):
        return 'invalid'
    return 'call_after_filing' if called > filed else 'valid'
