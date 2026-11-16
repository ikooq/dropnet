"""Canonical forms for identifiers found in complaint text."""
from __future__ import annotations

import re
from urllib.parse import urlparse


def phone(s: str) -> str | None:
    """Kazakh phone in any common shape -> E.164 (+7XXXXXXXXXX)."""
    d = re.sub(r"\D", "", s)
    if len(d) == 11 and d[0] in "78":
        return "+7" + d[1:]
    if len(d) == 10 and d[0] == "7":
        return "+7" + d
    return None


def card(s: str) -> str | None:
    """Full, spaced or masked card number -> '4000 00** **** 1234'."""
    compact = re.sub(r"[\s-]", "", s)
    if not re.fullmatch(r"\d{6}[\d*]{6}\d{4}", compact):
        return None
    return f"{compact[:4]} {compact[4:6]}** **** {compact[-4:]}"


def iban(s: str) -> str | None:
    compact = re.sub(r"\s", "", s).upper()
    return compact if re.fullmatch(r"KZ\d{2}[0-9A-Z]{16}", compact) else None


def domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def amount_kzt(s: str) -> int | None:
    t = s.lower().replace(" ", " ")
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*млн", t)
    if m:
        return int(round(float(m.group(1).replace(",", ".")) * 1_000_000))
    m = re.search(r"(\d[\d ]*)\s*тыс", t)
    if m:
        return int(m.group(1).replace(" ", "")) * 1000
    m = re.search(r"(\d{1,3}(?: \d{3})+|\d+)", t)
    if m:
        return int(m.group(1).replace(" ", ""))
    return None
