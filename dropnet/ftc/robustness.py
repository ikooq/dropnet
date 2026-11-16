"""Is the hold-out result robust, or one lucky split?

* rolling      — many train/test splits: rules learned on every report before day D, scored on the next 7 days.
* bootstrap    — 95 % intervals for the single headline split, resampling whole test DAYS (reports on one day
                 are correlated, so resampling reports would overstate certainty).
* thresholds   — the pool rule (>= m distinct numbers per block) for m = 3 … 15: coverage vs numbers silenced.
* ablations    — same number of block rules chosen by raw report volume instead of distinct numbers;
                 pools built WITH neighbor-spoofed reports (what a naive system would do).

One Cypher read pulls every report (number, block, day, spoofed flag); everything after is plain Python, so
each split costs milliseconds and the pool rule is re-implemented exactly (tested against campaigns.pool_campaigns).
"""
from __future__ import annotations

import random
from collections import defaultdict

import relate

from ..store import rows
from .parse import TOLL_FREE

BLOCK_SIZE = 10_000


def load(conn: relate.Connection) -> list[tuple[str, str, str, bool]]:
    return [(r["n"], r["b"], r["d"], bool(r["nb"])) for r in rows(conn, """
        MATCH (r:Report)-[:FROM_NUMBER]->(n:Number)-[:IN_BLOCK]->(b:Block)
        RETURN n.number AS n, b.npa_nxx AS b, r.day AS d, r.neighbor AS nb""")]


def pools(train, min_numbers: int = 5, exclude_neighbor: bool = True) -> set[str]:
    nums = defaultdict(set)
    for n, b, _, nb in train:
        if not (exclude_neighbor and nb):
            nums[b].add(n)
    return {b for b, s in nums.items() if len(s) >= min_numbers}


def _score(test, numbers: set[str], blocks: set[str]) -> float:
    return sum(1 for n, b, _, _ in test if n in numbers or b in blocks) / len(test) if test else 0.0


def _split(reports, day: str, until: str | None = None):
    train = [r for r in reports if r[2] < day]
    test = [r for r in reports if r[2] >= day and (until is None or r[2] < until)]
    return train, test


def _numbers(train, min_reports: int = 2) -> set[str]:
    c = defaultdict(int)
    for n, *_ in train:
        c[n] += 1
    return {n for n, k in c.items() if k >= min_reports}


def rolling(reports, min_train_days: int = 7, window: int = 7, min_numbers: int = 5) -> list[dict]:
    days = sorted({r[2] for r in reports})
    out = []
    for i in range(min_train_days, len(days) - 1):
        day, until = days[i], days[min(i + window, len(days) - 1)] if i + window < len(days) else None
        train, test = _split(reports, day, until)
        if len(test) < 1000:
            continue
        nums, blocks = _numbers(train), pools(train, min_numbers)
        geo = {b for b in blocks if b[:3] not in TOLL_FREE}
        out.append({"split_day": day, "train_reports": len(train), "test_reports": len(test),
                    "baseline": round(_score(test, nums, set()), 4),
                    "dropnet_geographic": round(_score(test, nums, geo), 4),
                    "dropnet": round(_score(test, nums, blocks), 4), "pool_blocks": len(blocks)})
    return out


def bootstrap(reports, split_day: str, reps: int = 1000, min_numbers: int = 5, seed: int = 0) -> dict:
    train, test = _split(reports, split_day)
    nums, blocks = _numbers(train), pools(train, min_numbers)
    geo = {b for b in blocks if b[:3] not in TOLL_FREE}
    by_day = defaultdict(lambda: [0, 0, 0, 0])  # total, baseline hits, geographic hits, all-pool hits
    for n, b, d, _ in test:
        x = by_day[d]
        x[0] += 1
        x[1] += n in nums
        x[2] += n in nums or b in geo
        x[3] += n in nums or b in blocks
    days = sorted(by_day)
    rng = random.Random(seed)
    stats = {"baseline": [], "dropnet_geographic": [], "dropnet": [], "lift_geographic": []}
    for _ in range(reps):
        tot = [0, 0, 0, 0]
        for d in (rng.choice(days) for _ in days):
            tot = [a + b for a, b in zip(tot, by_day[d])]
        base, geo_c, all_c = tot[1] / tot[0], tot[2] / tot[0], tot[3] / tot[0]
        stats["baseline"].append(base)
        stats["dropnet_geographic"].append(geo_c)
        stats["dropnet"].append(all_c)
        stats["lift_geographic"].append(geo_c / base if base else 0.0)

    def ci(xs):
        xs = sorted(xs)
        return [round(xs[int(0.025 * len(xs))], 4), round(xs[int(0.975 * len(xs)) - 1], 4)]

    return {"split_day": split_day, "test_days": len(days), "reps": reps, **{k: ci(v) for k, v in stats.items()}}


def thresholds(reports, split_day: str, ms=(3, 4, 5, 6, 8, 10, 15)) -> list[dict]:
    train, test = _split(reports, split_day)
    nums = _numbers(train)
    later = defaultdict(int)
    for _, b, _, _ in test:
        later[b] += 1
    out = []
    for m in ms:
        blocks = {b for b in pools(train, m) if b[:3] not in TOLL_FREE}
        out.append({"min_numbers": m, "block_rules": len(blocks), "numbers_silenced": BLOCK_SIZE * len(blocks),
                    "coverage": round(_score(test, nums, blocks), 4),
                    "dormant_share": round(sum(1 for b in blocks if not later[b]) / len(blocks), 4) if blocks else 0.0})
    return out


def ablations(reports, split_day: str, min_numbers: int = 5) -> dict:
    train, test = _split(reports, split_day)
    nums = _numbers(train)
    ours = {b for b in pools(train, min_numbers) if b[:3] not in TOLL_FREE}
    def top_by_volume(skip_spoofed: bool) -> set[str]:
        vol = defaultdict(int)
        for _, b, _, nb in train:
            if b[:3] not in TOLL_FREE and not (skip_spoofed and nb):
                vol[b] += 1
        return set(sorted(vol, key=lambda b: (-vol[b], b))[:len(ours)])

    naive = {b for b in pools(train, min_numbers, exclude_neighbor=False) if b[:3] not in TOLL_FREE}
    spoofed_test = [r for r in test if r[3]]

    def arm(blocks: set[str]) -> dict:
        return {"block_rules": len(blocks), "coverage": round(_score(test, nums, blocks), 4),
                "spoofed_numbers_hit": round(_score(spoofed_test, set(), blocks), 4),
                "overlap_with_pools": round(len(blocks & ours) / len(ours), 4) if ours else 0.0}

    return {
        "pools_distinct_numbers": arm(ours),
        "same_count_by_report_volume": arm(top_by_volume(False)),
        "same_count_by_volume_spoofed_excluded": arm(top_by_volume(True)),
        "pools_including_spoofed": {
            "block_rules": len(naive), "coverage": round(_score(test, nums, naive), 4),
            "extra_blocks": len(naive - ours),
            # share of later SPOOFED calls whose faked number falls in a blocked range: innocent local owners hit
            "spoofed_numbers_hit": round(_score(spoofed_test, set(), naive), 4)},
        "ours_spoofed_numbers_hit": round(_score(spoofed_test, set(), ours), 4),
    }


def run(conn: relate.Connection, split_day: str) -> dict:
    reports = load(conn)
    roll = rolling(reports)
    lifts = [r["dropnet_geographic"] / r["baseline"] for r in roll if r["baseline"]]
    return {"rolling": roll,
            "rolling_summary": {"splits": len(roll),
                                "dropnet_beats_baseline": sum(1 for r in roll if r["dropnet_geographic"] > r["baseline"]),
                                "min_lift": round(min(lifts), 2) if lifts else None,
                                "median_lift": round(sorted(lifts)[len(lifts) // 2], 2) if lifts else None},
            "bootstrap": bootstrap(reports, split_day), "thresholds": thresholds(reports, split_day),
            "ablations": ablations(reports, split_day)}
