"""Count heuristic categories in a sample; this is not an evaluation against independent truth."""
from __future__ import annotations

import random
from collections import Counter

import relate

from ..store import rows
from .campaigns import assess_number


def run(conn: relate.Connection, n: int = 1000, seed: int = 0) -> dict:
    numbers = sorted(r["n"] for r in rows(conn, "MATCH (x:Number) RETURN x.number AS n"))
    sample = random.Random(seed).sample(numbers, min(n, len(numbers)))
    verdicts = Counter()
    blames, dismisses = 0, 0
    for num in sample:
        a = assess_number(conn, num)
        verdicts[a["verdict"]] += 1
        if a["verdict"] == "likely_spoofed":
            blames += 1  # naive accusation on an area-code match: ownership is unknown
        if a["reports"] == 1 and a["verdict"] == "pool":
            dismisses += 1  # naive: "only one report" -> ignores a pool member
    k = len(sample)
    return {"sampled": k, "seed": seed, "verdicts": dict(verdicts),
            "naive_blames_likely_spoofed": blames, "naive_blames_share": round(blames / k, 4) if k else 0.0,
            "naive_dismisses_pool_members": dismisses, "naive_dismiss_share": round(dismisses / k, 4) if k else 0.0,
            "dropnet_flags_spoofed": verdicts["likely_spoofed"],
            "note": "Dropnet's hook and MCP tool return these verdicts with the spoofing caution before the agent answers."}
