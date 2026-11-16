"""Temporal hold-out: rules learned from earlier reports, scored on later reports.

Baseline  = block every number reported >= `min_reports` times before the split (a classic blocklist).
Dropnet   = the same numbers + every pool block (>= `min_numbers` distinct non-spoofed numbers before the split).
"""
from __future__ import annotations

import relate

from ..store import rows
from .campaigns import pool_campaigns

BLOCK_SIZE = 10_000


def holdout(conn: relate.Connection, split_day: str, min_numbers: int = 5, min_reports: int = 2) -> dict:
    train_counts = {r["n"]: r["c"] for r in rows(conn, """
        MATCH (r:Report)-[:FROM_NUMBER]->(n:Number) WHERE r.day < $s
        RETURN n.number AS n, count(r) AS c""", {"s": split_day})}
    numbers = {n for n, c in train_counts.items() if c >= min_reports}
    blocks = {p["block"] for p in pool_campaigns(conn, min_numbers, exclude_neighbor=True, until_day=split_day)}
    test = rows(conn, """
        MATCH (r:Report)-[:FROM_NUMBER]->(n:Number)-[:IN_BLOCK]->(b:Block) WHERE r.day >= $s
        RETURN n.number AS n, b.npa_nxx AS b, r.neighbor AS nb""", {"s": split_day})
    total = len(test)

    def share(x):
        return round(len(x) / total, 4) if total else 0.0

    def ruleset(block_set: set[str]) -> dict:
        hit = [t for t in test if t["n"] in numbers or t["b"] in block_set]
        return {"rules": len(numbers) + len(block_set), "number_rules": len(numbers), "block_rules": len(block_set),
                # a block rule silences all 10,000 numbers of an NPA-NXX — reported as the price of the rule
                "numbers_blocked": len(numbers) + BLOCK_SIZE * len(block_set),
                "covered": len(hit), "coverage": share(hit),
                "new_numbers_caught": sum(1 for t in hit if t["n"] not in train_counts),
                # calls whose (spoofed) caller ID sits in a pool block: the block rule would also hit that number's owner
                "spoofed_caught": sum(1 for t in hit if t["nb"] and t["n"] not in numbers)}

    from .parse import TOLL_FREE
    base = [t for t in test if t["n"] in numbers]
    return {
        "split_day": split_day, "train_reports": sum(train_counts.values()), "test_reports": total,
        "baseline": {"rules": len(numbers), "numbers_blocked": len(numbers), "covered": len(base),
                     "coverage": share(base)},
        "dropnet": ruleset(blocks),
        "dropnet_geographic": ruleset({b for b in blocks if b[:3] not in TOLL_FREE}),
        "blocklist_all_seen": {"rules": len(train_counts),
                               "coverage": share([t for t in test if t["n"] in train_counts])},
    }
