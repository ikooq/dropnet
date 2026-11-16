"""Offline, deterministic extraction: regexes for identifiers, a lexicon for tactics."""
from __future__ import annotations

import re

from ..models import Extraction
from . import normalize

PHONE_RE = re.compile(r"(?<![\d*])(?:\+7|8)[ (-]{0,2}\d{3}\)?[ -]{0,2}\d{3}[ -]?\d{2}[ -]?\d{2}(?![\d*])")
CARD_RE = re.compile(r"(?<![\d*])\d{4}[ -]?\d{2}[\d*]{2}[ -]?[\d*]{4}[ -]?\d{4}(?![\d*])")
IBAN_RE = re.compile(r"\bKZ\d{2}(?: ?[0-9A-Z]{4}){4}\b")
URL_RE = re.compile(r"https?://[^\s,;«»\"']+")
AMOUNT_RE = re.compile(
    r"(?<![\d*])(?:\d+(?:[.,]\d+)?\s*млн|\d[\d ]*\s*тыс\.?|\d{1,3}(?: \d{3})+|\d{4,})\s*(?:тг|тенге|₸|KZT)",
    re.IGNORECASE,
)

TACTIC_LEXICON: dict[str, list[str]] = {
    "BANK_SECURITY": [r"служб\w* безопасности", r"финансов\w* мониторинг", r"код из SMS", r"пытаются снять"],
    "SAFE_ACCOUNT": [r"безопасн\w* сч[её]т", r"защищ[её]нн\w* (?:депозитн\w* )?сч[её]т", r"Нацбанк",
                     r"Национальн\w* банк"],
    "LOAN_STATUS_SMS": [r"статус\w* (?:вашего )?займа", r"сообщение о займе"],
    "MARKETPLACE_PREPAY": [r"предоплат", r"объявлени", r"выкупить заказ"],
    "POLICE_THREAT": [r"следовател", r"уголовн\w* дел", r"из полиции"],
    "INVESTMENT": [r"доход\w*", r"криптобирж", r"инвест", r"invest", r"куратор"],
    "ATM_DROP_HELP": [r"(?:у|возле) банкомата"],
}
_TACTIC_RES = {k: re.compile("|".join(v), re.IGNORECASE) for k, v in TACTIC_LEXICON.items()}

# Scammer personas: a gazetteer of common Kazakh given names (with Russian case endings).
# Gangs re-use their aliases, so a shared alias + shared tactic is evidence.
PERSONA_NAMES = ["Ерлан", "Нурлан", "Санжар", "Данияр", "Арман", "Марат", "Бауыржан", "Асхат", "Ержан",
                 "Динара", "Алия", "Камила", "Айгерим", "Асель", "Мадина", "Жанна", "Гульнара", "Сауле"]


def _name_re(name: str) -> str:
    stem = name[:-1] if name[-1] in "аяь" else name
    return stem + r"(?:а|я|у|ю|ом|ем|ой|ей|е|ы|и)?" if stem != name else name + r"(?:а|у|ом|е|ым)?"


PERSONA_RE = re.compile(r"(?<![А-Яа-яЁё])(" + "|".join(f"(?P<n{i}>{_name_re(n)})" for i, n in enumerate(PERSONA_NAMES))
                        + r")(?![А-Яа-яЁё])")


# A sentence ends at . ! ? or newline — but not after common abbreviations like "тыс." or "млн.".
_SENT_END = re.compile(r"(?<!тыс)(?<!млн)(?<!руб)(?<!г)(?<!ул)[.!?](?=\s|$)|\n")


def _quote(text: str, start: int, end: int, limit: int = 240) -> str:
    """The sentence around a span, clipped to `limit` chars but always containing the span."""
    ends = [m.end() for m in _SENT_END.finditer(text)]
    s = max([e for e in ends if e <= start], default=0)
    e = min([x for x in ends if x >= end], default=len(text))
    q = text[s:e].strip()
    if len(q) <= limit:
        return q
    lo = max(s, start - (limit - (end - start)) // 2)
    return text[lo:lo + limit].strip()


def _ex(cid: str, kind: str, value: str, m: re.Match, text: str) -> Extraction:
    return Extraction(cid, kind, value, m.start(), m.end(), _quote(text, m.start(), m.end()))


def extract(complaint_id: str, text: str) -> list[Extraction]:
    out: list[Extraction] = []
    taken: list[tuple[int, int]] = []

    def free(m: re.Match) -> bool:
        return all(m.end() <= a or m.start() >= b for a, b in taken)

    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".)!?")
        out.append(Extraction(complaint_id, "url", url, m.start(), m.start() + len(url),
                              _quote(text, m.start(), m.start() + len(url))))
        taken.append((m.start(), m.end()))
    for m in IBAN_RE.finditer(text):
        v = normalize.iban(m.group(0))
        if v:
            out.append(_ex(complaint_id, "iban", v, m, text))
            taken.append(m.span())
    for m in CARD_RE.finditer(text):
        v = normalize.card(m.group(0))
        if v and free(m):
            out.append(_ex(complaint_id, "card", v, m, text))
            taken.append(m.span())
    for m in PHONE_RE.finditer(text):
        v = normalize.phone(m.group(0))
        if v and free(m):
            out.append(_ex(complaint_id, "phone", v, m, text))
            taken.append(m.span())
    for m in AMOUNT_RE.finditer(text):
        v = normalize.amount_kzt(m.group(0))
        if v and free(m):
            out.append(_ex(complaint_id, "amount", str(v), m, text))
    seen_personas: set[str] = set()
    for m in PERSONA_RE.finditer(text):
        name = next(PERSONA_NAMES[int(k[1:])] for k, v in m.groupdict().items() if v)
        if name not in seen_personas:
            seen_personas.add(name)
            out.append(_ex(complaint_id, "persona", name, m, text))
    for code, rx in _TACTIC_RES.items():
        m = rx.search(text)
        if m:
            out.append(_ex(complaint_id, "tactic", code, m, text))
    out.sort(key=lambda e: e.span_start)
    return out
