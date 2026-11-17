"""Claude Code hook (UserPromptSubmit): when a prompt mentions a US phone number, give the agent the graph's
evidence about it — and the caution that caller ID is easily spoofed — before it answers."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import config, store
from .ftc.campaigns import CAUTION, assess_number

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


def number_guard(prompt: str, ftc_store: Path | str = config.DATA_DIR / "ftc.rl") -> str | None:
    nums = numbers_in(prompt or "")
    if not nums or not Path(ftc_store).exists():
        return None
    conn = store.open_store(ftc_store, read_only=True)
    try:
        lines = ["Dropnet evidence (real FTC Do Not Call reports, embedded Relate graph):"]
        found = [(n, assess_number(conn, n)) for n in nums]
        if all(a["verdict"] == "unknown" for _, a in found):
            return None  # e.g. an order number: say nothing rather than add noise
        for n, a in found:
            pretty = f"{n[:3]}-{n[3:6]}-{n[6:]}"
            if a["verdict"] == "unknown":
                lines.append(f"- {pretty}: {LABEL['unknown']}.")
                continue
            lines.append(f"- {pretty}: {LABEL[a['verdict']]}; {a['reports']} reports in {a['states']} states, "
                         f"scam types {', '.join(a['subjects'][:3])}; {a['neighbor_share']:.0%} area-code match; "
                         f"block {a['block'][:3]}-{a['block'][3:]} has {a['block_numbers']} reported numbers.")
        lines.append(f"Caution for your answer: {CAUTION} Do not call the number's owner a scammer; describe the "
                     f"reports. Use the dropnet MCP tool assess_number for details.")
        return "\n".join(lines)
    finally:
        conn.close()


def main(argv: list[str] | None = None, ftc_store: Path | str | None = None) -> int:
    try:  # a hook must never break the user's prompt: any failure means "no extra context"
        payload = json.loads(sys.stdin.read() or "{}")
        prompt = payload.get("prompt") if isinstance(payload, dict) else None
        if not isinstance(prompt, str):
            return 0
        ctx = number_guard(prompt, ftc_store or config.DATA_DIR / "ftc.rl")
        if ctx:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}))
    except Exception:  # noqa: BLE001
        return 0
    return 0
