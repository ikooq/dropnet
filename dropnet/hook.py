"""Claude Code hook (UserPromptSubmit): when a prompt mentions a US phone number, give the agent the graph's
evidence about it — and the caution that caller ID is easily spoofed — before it answers."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import config

WEB_URL = "http://127.0.0.1:8000"  # `python -m dropnet serve`: answers in milliseconds, the graph is already loaded

US_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?([2-9]\d{2})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})(?!\d)")
LABEL = {"likely_spoofed": "POSSIBLE LOCAL AREA-CODE MATCH — one or two reports from the same area code",
         "pool": "part of a NUMBER POOL (many reported numbers in the same NPA-NXX block)",
         "repeat": "REPEATEDLY reported", "single": "reported once", "unknown": "not in the FTC reports"}


def numbers_in(text: str) -> list[str]:
    seen, out = set(), []
    for m in US_PHONE.finditer(text[:20_000]):
        n = "".join(m.groups())
        if n not in seen:
            seen.add(n)
            out.append(n)
            if len(out) == 5:
                break
    return out


def _from_app(nums: list[str], web_url: str) -> list[tuple[str, dict]] | None:
    """Ask a running Dropnet app; None when none is running (then the hook opens the graph itself)."""
    import urllib.request
    try:
        out = []
        for n in nums:
            with urllib.request.urlopen(f"{web_url}/api/ftc/number/{n}", timeout=1) as r:
                out.append((n, json.loads(r.read())))
        return out
    except Exception:  # noqa: BLE001 - not running, or an older app: fall back to the file
        return None


def _from_file(nums: list[str], ftc_store: Path | str) -> list[tuple[str, dict]]:
    from . import store
    from .ftc.campaigns import assess_number
    conn = store.open_store(ftc_store, read_only=True)
    try:
        return [(n, assess_number(conn, n)) for n in nums]
    finally:
        conn.close()


def number_guard(prompt: str, ftc_store: Path | str = config.DATA_DIR / "ftc.rl",
                 web_url: str | None = None) -> str | None:
    from .ftc.campaigns import CAUTION
    nums = numbers_in(prompt or "")
    if not nums:
        return None
    found = _from_app(nums, web_url) if web_url else None
    if found is None:
        if not Path(ftc_store).exists():
            return None
        found = _from_file(nums, ftc_store)
    lines = ["Dropnet evidence (real FTC Do Not Call reports, embedded Relate graph):"]
    if all(a["verdict"] == "unknown" and not a.get("in_pool_range") for _, a in found):
        return None  # e.g. an order number: say nothing rather than add noise
    for n, a in found:
        pretty = f"{n[:3]}-{n[3:6]}-{n[6:]}"
        if a["verdict"] == "unknown":
            context = (f" Its range contains {a['block_numbers']} reported numbers meeting the pool criteria."
                       if a.get("in_pool_range") else "")
            lines.append(f"- {pretty}: {LABEL['unknown']}.{context}")
            continue
        lines.append(f"- {pretty}: {LABEL[a['verdict']]}; {a['reports']} reports in {a['states']} states, "
                     f"scam types {', '.join(a['subjects'][:3])}; {a['neighbor_share']:.0%} area-code match; "
                     f"block {a['block'][:3]}-{a['block'][3:]} has {a['block_numbers']} reported numbers.")
        h = a.get("holder")
        if h and h.get("range_holder"):
            assigned = (f"; its 1,000-number block was assigned to {h['block_carrier']}"
                        if h.get("block_carrier") and h["block_carrier"] != h["range_holder"] else "")
            lines.append(f"  NANPA lists {h['range_holder']} as the range's holder ({h.get('rate_center')}, "
                         f"{h.get('state')}){assigned}. A holder issued numbers; it is not the caller.")
    lines.append(f"Caution for your answer: {CAUTION} Do not call the number's owner a scammer; describe the "
                 f"reports. Use the dropnet MCP tool assess_number for details.")
    return "\n".join(lines)


def main(argv: list[str] | None = None, ftc_store: Path | str | None = None) -> int:
    try:  # a hook must never break the user's prompt: any failure means "no extra context"
        payload = json.loads(sys.stdin.read() or "{}")
        prompt = payload.get("prompt") if isinstance(payload, dict) else None
        if not isinstance(prompt, str):
            return 0
        # A running app answers at once; tests and explicit stores read the file only.
        ctx = number_guard(prompt, ftc_store or config.DATA_DIR / "ftc.rl", web_url=None if ftc_store else WEB_URL)
        if ctx:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}))
    except Exception:  # noqa: BLE001
        return 0
    return 0
