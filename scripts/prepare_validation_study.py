"""Prepare a fresh, blinded review and counterbalanced lookup study; never fabricate results."""
import argparse
import csv
import hashlib
import importlib.util
import json
import random
from collections import defaultdict
from pathlib import Path

from dropnet.ftc.date_quality import chronology
from dropnet.ftc.parse import read_reports

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'ftc' / 'raw'
PACK = ROOT / 'docs' / 'independent-review'
SEED = 20261118


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(out):
    if out.exists() and any(out.iterdir()):
        raise SystemExit('Output directory is not empty; preserve existing study materials and responses')
    paths = sorted(RAW.glob('*.csv.gz'))
    original_manifest = json.loads((PACK / 'manifest.json').read_text(encoding='utf-8'))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    if hashes != original_manifest['files']:
        raise SystemExit('Raw data differ from original snapshot')
    excluded = set()
    for p in [PACK / 'selection-key.json', PACK / 'holdout' / 'selection-key.json']:
        excluded |= {x['block'] for x in json.loads(p.read_text(encoding='utf-8'))['selection']}
    by_number = defaultdict(list)
    for r in read_reports(paths):
        if r.number[:6] not in excluded:
            by_number[r.number].append(r)
    strata = defaultdict(list)
    for n, rr in by_number.items():
        statuses = [chronology(r.created_day, r.violation_day) for r in rr]
        # Do not treat unavailable dates as normal. Keep tasks manageable for a manual reviewer.
        if any(x in ('invalid','missing') for x in statuses) or len(rr) > 30:
            continue
        strata[(any(x == 'call_after_filing' for x in statuses), len(rr) >= 3)].append(n)
    rng = random.Random(SEED)
    # Six anomaly and six clean cases, each half with repeated reports; no shared six-digit blocks.
    picked = defaultdict(list)
    used_blocks = set(excluded)
    for group in ((True, True), (True, False), (False, True), (False, False)):
        candidates = sorted(strata[group]); rng.shuffle(candidates)
        for n in candidates:
            if n[:6] not in used_blocks:
                picked[group].append(n); used_blocks.add(n[:6])
                if len(picked[group]) == 3: break
        if len(picked[group]) != 3:
            raise SystemExit(f'Insufficient eligible cases in {group}')
    first, second = [], []
    # Both halves have the same distribution: one repeated and two non-repeated or vice versa.
    for group, nums in picked.items():
        (first if group[1] else second).extend(nums[:2])
        (second if group[1] else first).extend(nums[2:])
    assert len(first) == len(second) == 6
    assert sum(any(chronology(r.created_day,r.violation_day)=='call_after_filing' for r in by_number[n]) for n in first) == 3
    rng.shuffle(first); rng.shuffle(second)
    selected = first + second
    out.mkdir(parents=True)
    for directory in ['reviewer', 'coordinator']:
        (out / directory).mkdir()
    reviewer, coordinator = out / 'reviewer', out / 'coordinator'
    with (reviewer/'lookup_tasks.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['task_id','reported_caller_id'])
        for i,n in enumerate(selected,1):w.writerow([f'T{i:02}',n])
    with (reviewer/'baseline_complaints.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['report_id','reported_caller_id','filing_date','reported_call_date'])
        records = [(r.id,r.number,r.created_day,r.violation_day) for n in selected for r in by_number[n]]
        for row in sorted(records):w.writerow(row)
    with (reviewer/'lookup_answers.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['participant_id','assignment_A_or_B','task_id','method','elapsed_seconds','report_count','call_after_filing_yes_no_unsure','confidence_1_to_5','comments'])
        for i in range(1,13):w.writerow(['','',f'T{i:02}','','','','','',''])
    key=[]
    for i,n in enumerate(selected,1):
        rr=by_number[n]
        key.append({'task_id':f'T{i:02}','number':n,'report_count':len(rr),
                    'call_after_filing_count':sum(chronology(r.created_day,r.violation_day)=='call_after_filing' for r in rr)})
    (coordinator/'lookup-key.json').write_text(json.dumps({'seed':SEED,'cases':key,'source_sha256':hashes},indent=2)+'\n',encoding='utf-8',newline='\n')
    # Qualitative review uses fresh ranges as well, disjoint from all timed-study numbers.
    gen=module('review_generate','generate_independent_review.py')
    gen.OUT=out/'expert-review';gen.SEED=20261119;gen.EXCLUDED_BLOCKS=used_blocks
    gen.generate()
    exp=module('review_expand','expand_review_cases.py');exp.PACK=gen.OUT;exp.main()
    print(f'Created 12 timed tasks ({len(records)} baseline complaint rows), 30 separate expert-review cases')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args().output.resolve())
