"""Temporal hold-out: rules learned from earlier reports, scored on later reports.

Baseline  = block every number reported >= `min_reports` times before the split (a classic blocklist).
Dropnet   = the same numbers + every pool block (>= `min_numbers` distinct numbers from reports without an area-code match before the split).
"""
from __future__ import annotations

from collections import Counter

import relate

from ..store import rows
from .campaigns import pool_campaigns
from .parse import TOLL_FREE

BLOCK_SIZE = 10_000


def controls(conn: relate.Connection, split_day: str, min_numbers: int = 5, seeds: int = 5) -> dict:
    """Is a pool more than a random reported block? Same number of blocks, drawn at random from every block with a
    report without an area-code match before the split; and how many pool rules never catch anything later (dormant)."""
    import random
    pools = {p["block"] for p in pool_campaigns(conn, min_numbers, exclude_neighbor=True, until_day=split_day)}
    candidates = sorted({r["b"] for r in rows(conn, """
        MATCH (r:Report)-[:FROM_NUMBER]->(:Number)-[:IN_BLOCK]->(b:Block) WHERE r.day < $s AND r.neighbor = false
        RETURN DISTINCT b.npa_nxx AS b""", {"s": split_day})})
    later = {}
    for r in rows(conn, """MATCH (r:Report)-[:FROM_NUMBER]->(:Number)-[:IN_BLOCK]->(b:Block) WHERE r.day >= $s
                           RETURN b.npa_nxx AS b, count(r) AS c""", {"s": split_day}):
        later[r["b"]] = r["c"]
    total = sum(later.values()) or 1
    pool_cov = sum(later.get(b, 0) for b in pools) / total
    rand = []
    for seed in range(seeds):
        pick = random.Random(seed).sample(candidates, min(len(pools), len(candidates)))
        rand.append(sum(later.get(b, 0) for b in pick) / total)
    return {"pool_blocks": len(pools), "candidate_blocks": len(candidates),
            "pool_blocks_coverage": round(pool_cov, 4), "random_blocks_coverage": round(sum(rand) / len(rand), 4),
            "lift": round(pool_cov / (sum(rand) / len(rand)), 1) if sum(rand) else None,
            "dormant_share": round(sum(1 for b in pools if not later.get(b)) / len(pools), 4) if pools else 0.0}


def holdout(conn: relate.Connection, split_day: str, min_numbers: int = 5, min_reports: int = 2) -> dict:
    train_counts = {r["n"]: r["c"] for r in rows(conn, """
        MATCH (r:Report)-[:FROM_NUMBER]->(n:Number) WHERE r.day < $s
        RETURN n.number AS n, count(r) AS c""", {"s": split_day})}
    numbers = {n for n, c in train_counts.items() if c >= min_reports}
    blocks = {p["block"] for p in pool_campaigns(conn, min_numbers, exclude_neighbor=True, until_day=split_day)}
    geographic = {b for b in blocks if b[:3] not in TOLL_FREE}
    # Each key in train_counts is a distinct number. Keep all reports when ranking the comparison prefixes.
    counts = Counter(n[:6] for n in train_counts if n[:3] not in TOLL_FREE)
    ranked = sorted(counts, key=lambda b: (-counts[b], b))
    naive = set(ranked[:len(geographic)])
    test = rows(conn, """
        MATCH (r:Report)-[:FROM_NUMBER]->(n:Number)-[:IN_BLOCK]->(b:Block) WHERE r.day >= $s
        RETURN n.number AS n, b.npa_nxx AS b, r.neighbor AS nb""", {"s": split_day})
    total = len(test)

    def share(x):
        return round(len(x) / total, 4) if total else 0.0

    def ruleset(block_set: set[str]) -> dict:
        hit = [t for t in test if t["n"] in numbers or t["b"] in block_set]
        # Count each covered number once when it is already inside a selected prefix.
        capacity = sum(n[:6] not in block_set for n in numbers) + BLOCK_SIZE * len(block_set)
        return {"rules": len(numbers) + len(block_set), "number_rules": len(numbers), "block_rules": len(block_set),
                "numbers_blocked": capacity,
                "matches_per_million_numbers": round(len(hit) * 1_000_000 / capacity, 1) if capacity else None,
                "covered": len(hit), "coverage": share(hit),
                "new_numbers_caught": sum(1 for t in hit if t["n"] not in train_counts),
                # Legacy key: reports with an area-code match; not verified spoofing or a count of innocent owners.
                "spoofed_caught": sum(1 for t in hit if t["nb"] and t["n"] not in numbers)}

    base = ruleset(set())
    return {
        "split_day": split_day, "train_reports": sum(train_counts.values()), "test_reports": total,
        "baseline": {key: base[key] for key in ("rules", "numbers_blocked", "covered", "coverage",
                                               "matches_per_million_numbers")},
        "dropnet": ruleset(blocks),
        "dropnet_geographic": ruleset(geographic),
        "naive_geographic": ruleset(naive),
        "blocklist_all_seen": {"rules": len(train_counts),
                               "coverage": share([t for t in test if t["n"] in train_counts])},
    }
