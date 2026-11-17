"""Audit filing-time holdout against event dates without future information in training.

Run: python -m dropnet.ftc.time_audit [raw-directory] [split-day]
The event-date subset is retrospective and restricted to complaints filed in the test window.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .. import config
from .parse import TOLL_FREE, read_reports


def audit(reports, split: str, min_reports: int = 2, min_numbers: int = 5) -> dict:
    date.fromisoformat(split)
    train = Counter()
    by_block = defaultdict(set)
    test = []
    missing_area = 0
    invalid_dates = 0
    future_dates = 0
    lags = []
    for r in reports:
        missing_area += not bool(r.victim_npa)
        if r.created_day < split:
            train[r.number] += 1
            if not r.neighbor:
                by_block[r.number[:6]].add(r.number)
        else:
            test.append(r)
        try:
            filing, event = date.fromisoformat(r.created_day), date.fromisoformat(r.violation_day)
            lag = (filing - event).days
            lags.append(lag)
            future_dates += lag < 0
        except ValueError:
            invalid_dates += 1
    numbers = {n for n, count in train.items() if count >= min_reports}
    blocks = {b for b, nums in by_block.items() if len(nums) >= min_numbers and b[:3] not in TOLL_FREE}
    later = []
    earlier = invalid_test = future_test = 0
    for r in test:
        try:
            event, filing = date.fromisoformat(r.violation_day), date.fromisoformat(r.created_day)
        except ValueError:
            invalid_test += 1
            continue
        if event > filing:
            future_test += 1
        elif event.isoformat() >= split:
            later.append(r)
        else:
            earlier += 1
    def coverage(predicate):
        return round(sum(predicate(r) for r in later) / len(later), 4) if later else None
    lags.sort()
    def quantile(p):
        return lags[int((len(lags)-1)*p)] if lags else None
    return {"split_day": split, "reports": sum(train.values()) + len(test),
            "test_filed": len(test), "test_event_before_split": earlier,
            "test_event_on_or_after_split_valid": len(later), "test_invalid_date": invalid_test,
            "test_event_after_filing": future_test, "all_invalid_date": invalid_dates,
            "all_event_after_filing": future_dates, "missing_consumer_area": missing_area,
            "filing_lag_days_p50_p90_p99": [quantile(.5), quantile(.9), quantile(.99)],
            "event_subset_baseline_coverage": coverage(lambda r: r.number in numbers),
            "event_subset_geographic_coverage": coverage(lambda r: r.number in numbers or r.number[:6] in blocks),
            "geographic_rules": len(blocks),
            "geographic_unique_number_capacity": len(blocks)*10000 + sum(n[:6] not in blocks for n in numbers),
            "note": "Training uses complaints filed before the split. Test includes only valid event dates on or after the split and not after filing, among complaints filed in the test window. It does not measure all calls or legitimate-call blocking. Missing consumer area codes are treated as non-matches by the existing pool heuristic."}


def main():
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else config.DATA_DIR / "ftc" / "raw"
    split = sys.argv[2] if len(sys.argv) > 2 else "2026-11-02"
    print(json.dumps(audit(read_reports(raw.glob("*.csv*")), split), indent=2))


if __name__ == "__main__":
    main()
