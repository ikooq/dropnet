"""Card-number masking used before anything is stored or shown."""
from __future__ import annotations

import re

_FULL_PAN = re.compile(r"(?<![\d*])\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}(?![\d*])")


def _mask_pan(m: re.Match) -> str:
    out, digit = [], 0
    for ch in m.group(0):
        if ch.isdigit():
            out.append("*" if 6 <= digit < 12 else ch)
            digit += 1
        else:
            out.append(ch)
    return "".join(out)


def redact(text: str | None) -> str | None:
    """Mask the middle six digits of full card numbers, keeping length and separators."""
    if text is None:
        return None
    return _FULL_PAN.sub(_mask_pan, text)
