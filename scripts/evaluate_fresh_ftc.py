"""Evaluate the previously fixed Nov 2 rules on later FTC daily files."""
import argparse
import gzip
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

from dropnet.ftc.parse import TOLL_FREE, read_reports
from dropnet.ftc.robustness import _numbers, pools


def evaluate(train, test):
    # Match the original training cutoff and thresholds, without learning from later filings.
    training=[r for r in train if r.created_day < '2026-11-02']
    later=[r for r in test if r.created_day >= '2026-11-13']
    if not training or not later:
        raise ValueError('Training or new-period evaluation set is empty')
    observations=[(r.number,r.number[:6],r.created_day,r.neighbor) for r in training]
    numbers=_numbers(observations,2)
    all_blocks=pools(observations,5)
    geo={b for b in all_blocks if b[:3] not in TOLL_FREE}
    def score(records):
        total=len(records)
        def count(blocks):return sum(r.number in numbers or r.number[:6] in blocks for r in records)
        hits={'baseline':count(set()),'geographic':count(geo),'all_pools':count(all_blocks)}
        return {'reports':total,'hits':hits,'shares':{k:round(v/total,6) if total else None for k,v in hits.items()}}
    valid=[]; dates=Counter()
    for r in later:
        try:
            filing=date.fromisoformat(r.created_day);call=date.fromisoformat(r.violation_day)
        except ValueError:
            dates['invalid_or_missing']+=1;continue
        if call>filing:dates['call_after_filing']+=1
        elif call.isoformat()<'2026-11-13':dates['call_before_new_window']+=1
        else:dates['valid_in_new_window']+=1;valid.append(r)
    return {'training_cutoff_exclusive':'2026-11-02','new_filing_start':'2026-11-13',
            'train_reports':len(training),'baseline_numbers':len(numbers),'geographic_ranges':len(geo),
            'all_ranges':len(all_blocks),'geographic_number_capacity':len(geo)*10000+sum(n[:6] not in geo for n in numbers),
            'new_filing_dates':dict(sorted(Counter(r.created_day for r in later).items())),
            'new_filed':score(later),'event_date_subset':score(valid),'date_audit':dict(dates)}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--train-dir',type=Path,required=True);ap.add_argument('--test-dir',type=Path,required=True)
    args=ap.parse_args(); train_paths=sorted(args.train_dir.glob('*.csv.gz'));test_paths=sorted(args.test_dir.glob('*.csv.gz'))
    if {p.name for p in train_paths}&{p.name for p in test_paths}:raise SystemExit('Training and test filenames overlap')
    result=evaluate(read_reports(train_paths),read_reports(test_paths))
    result['new_source_files']={p.name:hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest() for p in test_paths}
    print(json.dumps(result,indent=2,sort_keys=True))
