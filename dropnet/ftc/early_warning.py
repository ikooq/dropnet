"""Early warning: replay every complaint in filing order and ask what was already known the day before.

For each complaint we check two things that a system could have known on an earlier day only (strictly before
the complaint's filing day, so nothing from the same day leaks in):
  * number rule  — its caller ID had already been reported at least twice (a classic blocklist);
  * range rule   — its six-digit range had already been flagged: at least five distinct numbers from complaints
                   whose caller area code differs from the consumer's (the same rule as the rest of Dropnet).

It is a streaming replay, not a train/test split: every rule exists only from the day after it would have fired.
For the ranges that do get flagged it also reports how long that took and how much of their activity came after.
Like everything else here, these are matches against complaints, not calls blocked or fraud proven.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date

from .parse import TOLL_FREE


def example(reports, min_numbers: int = 5) -> dict | None:
    """The geographic range with the most numbers first seen after it was flagged, as a day-by-day timeline.

    Chosen as the clearest case, not a typical one; the selection rule is returned with it.
    """
    by_block = defaultdict(list)
    for n, b, d, nb in reports:
        if b[:3] not in TOLL_FREE:
            by_block[b].append((d, n, nb))
    best = None
    for b, rows in by_block.items():
        rows.sort()
        distinct, flag, first_seen = set(), None, {}
        for day in sorted({d for d, _, _ in rows}):
            todays = [(n, nb) for d, n, nb in rows if d == day]
            for n, _ in todays:
                first_seen.setdefault(n, day)
            if flag is None:
                distinct |= {n for n, nb in todays if not nb}
                if len(distinct) >= min_numbers:
                    flag = day
        if flag is None:
            continue
        after = sum(d > flag for d in first_seen.values())
        if best is None or after > best[0]:
            best = (after, b, flag, rows, first_seen)
    if best is None:
        return None
    after, b, flag, rows, first_seen = best
    complaints = defaultdict(int)
    for d, _, _ in rows:
        complaints[d] += 1
    days = sorted({d for d, _, _ in rows})
    new = defaultdict(int)
    for d in first_seen.values():
        new[d] += 1
    return {
        "block": b, "first_day": rows[0][0], "flag_day": flag, "last_day": rows[-1][0],
        "window": [min(r[2] for r in reports), max(r[2] for r in reports)],
        "numbers": len(first_seen), "numbers_after_flag": after,
        "complaints": len(rows), "complaints_after_flag": sum(d > flag for d, _, _ in rows),
        "days": [{"day": d, "new_numbers": new.get(d, 0), "complaints": complaints[d]} for d in days],
        "selection": "the geographic range with the most numbers first seen after the day it was flagged",
    }


def replay(reports, min_numbers: int = 5, min_reports: int = 2, geographic_only: bool = True) -> dict:
    """reports: iterable of (number, block, day 'YYYY-MM-DD', area_code_match bool)."""
    by_day = defaultdict(list)
    for r in reports:
        by_day[r[2]].append(r)
    seen = defaultdict(int)           # number -> complaints on earlier days
    distinct = defaultdict(set)       # block  -> distinct non-matching numbers on earlier days
    flagged_on: dict[str, str] = {}   # block  -> day it crossed the threshold
    first_day: dict[str, str] = {}    # block  -> first complaint day
    total = by_num = by_range = by_either = 0
    after_flag = defaultdict(int)     # block -> complaints filed after it was flagged
    in_block = defaultdict(int)
    new_numbers_after = defaultdict(set)
    known_numbers = defaultdict(set)
    for day in sorted(by_day):
        todays = by_day[day]
        for n, b, _d, nb in todays:   # judged with yesterday's knowledge only
            if geographic_only and b[:3] in TOLL_FREE:
                continue
            total += 1
            in_block[b] += 1
            first_day.setdefault(b, day)
            num_hit = seen[n] >= min_reports
            rng_hit = b in flagged_on
            by_num += num_hit
            by_range += rng_hit
            by_either += num_hit or rng_hit
            if rng_hit:
                after_flag[b] += 1
                if n not in known_numbers[b]:
                    new_numbers_after[b].add(n)
            known_numbers[b].add(n)
        for n, b, _d, nb in todays:   # then today's complaints become knowledge for tomorrow
            seen[n] += 1
            if not nb:
                distinct[b].add(n)
                if len(distinct[b]) >= min_numbers and b not in flagged_on:
                    flagged_on[b] = day
    flagged = [b for b in flagged_on if not (geographic_only and b[:3] in TOLL_FREE)]
    lag = [(date.fromisoformat(flagged_on[b]) - date.fromisoformat(first_day[b])).days for b in flagged]
    share = lambda x: round(x / total, 4) if total else 0.0
    in_flagged = sum(in_block[b] for b in flagged)
    return {
        "complaints": total,
        "caught_by_number_rule": share(by_num),
        "caught_by_range_rule": share(by_range),
        "caught_by_either": share(by_either),
        "ranges_flagged": len(flagged),
        "days_first_complaint_to_flag": {
            "median": statistics.median(lag) if lag else None,
            "p25": sorted(lag)[len(lag) // 4] if lag else None,
            "p75": sorted(lag)[3 * len(lag) // 4] if lag else None},
        "flagged_ranges_share_of_their_complaints_after_flag": round(sum(after_flag.values()) / in_flagged, 4) if in_flagged else 0.0,
        "numbers_first_seen_after_flag": sum(len(s) for s in new_numbers_after.values()),
        "note": "Streaming replay over filing days; a rule only counts from the day after it would have fired. "
                "Complaint matches, not calls blocked or fraud proven.",
    }
