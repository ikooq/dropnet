"""Create a reproducible, blinded review pack from the public FTC complaint snapshot."""
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from dropnet.ftc.parse import SUBJECT_LABEL, read_reports

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'ftc' / 'raw'
OUT = ROOT / 'docs' / 'independent-review'
SEED = 20261117
EXCLUDED_BLOCKS = set()


def generate():
    paths = sorted(RAW.glob('*.csv.gz'))
    if not paths:
        raise SystemExit('No FTC CSV files found in data/ftc/raw')
    blocks = defaultdict(list)
    for report in read_reports(paths):
        blocks[report.number[:6]].append(report)
    strata = {'strong': [], 'threshold': [], 'control': []}
    for block, reports in blocks.items():
        if block in EXCLUDED_BLOCKS:
            continue
        count = len({r.number for r in reports if not r.neighbor})
        group = 'strong' if count >= 10 else 'threshold' if count >= 5 else 'control' if count >= 1 else None
        if group:
            strata[group].append(block)
    rng = random.Random(SEED)
    selected = []
    for group, candidates in strata.items():
        candidates.sort()
        if len(candidates) < 10:
            raise SystemExit(f'Not enough candidates for {group}')
        selected.extend((group, b) for b in rng.sample(candidates, 10))
    rng.shuffle(selected)
    OUT.mkdir(parents=True, exist_ok=True)
    answers_path = OUT / 'answers.csv'
    if answers_path.exists():
        with answers_path.open(encoding='utf-8', newline='') as f:
            if any(any(v.strip() for k, v in row.items() if k != 'case_id' and v) for row in csv.DictReader(f)):
                raise SystemExit('answers.csv contains reviewer input; save it elsewhere before regenerating')
    cards = ['# Blinded case cards', '', 'Review each case independently using REVIEWER.md and record answers in answers.csv.',
             'These are unverified public complaints, not findings of fraud, number ownership, spoofing or common control.',
             'Dates below are complaint filing dates, not necessarily call dates. Area-code matches are only an indicator.', '']
    key = []
    with (OUT / 'answers.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(['case_id', 'reviewer_id', 'evidence_clear_yes_no_unsure', 'investigate_yes_no_unsure',
                         'confidence_1_to_5', 'missing_information', 'reason', 'reviewer_expertise'])
        for i, (group, block) in enumerate(selected, 1):
            case = f'C{i:02d}'
            rr = blocks[block]
            nonmatching = [r for r in rr if not r.neighbor]
            numbers = sorted({r.number for r in rr})
            days = sorted(r.created_day for r in rr if r.created_day)
            subjects = Counter(r.subject for r in rr)
            areas = Counter(r.victim_npa for r in rr if r.victim_npa)
            key.append({'case_id': case, 'stratum': group, 'block': block,
                        'eligible_distinct_numbers': len({r.number for r in nonmatching})})
            cards.extend([f'## {case}', '', f'- Reported six-digit range: `{block}`',
                f'- Complaints: {len(rr)}; distinct reported caller IDs: {len(numbers)}.',
                f'- Complaints with matching caller/consumer area codes: {sum(r.neighbor for r in rr)}; '
                f'complaints without consumer area code: {sum(not r.victim_npa for r in rr)}.',
                f'- Filing dates: {days[0] if days else "unknown"} to {days[-1] if days else "unknown"}.',
                '- Complaint subjects (count): ' + ', '.join(f'{SUBJECT_LABEL.get(k, k)}: {v}' for k,v in sorted(subjects.items(), key=lambda x:(-x[1], x[0]))),
                '- Consumer area codes (count; top 5): ' + (', '.join(f'{k}: {v}' for k,v in sorted(areas.items(), key=lambda x:(-x[1], x[0]))[:5]) or 'none provided'),
                '- Reported caller IDs (first 12 in sorted order): ' + ', '.join(f'`{n}`' for n in numbers[:12]) + (f' (and {len(numbers)-12} more)' if len(numbers)>12 else ''),
                '', 'Question: Is there enough information to justify further investigation of this range? Why?', ''])
            writer.writerow([case, '', '', '', '', '', '', ''])
    (OUT / 'cases.md').write_text('\n'.join(cards), encoding='utf-8', newline='\n')
    (OUT / 'selection-key.json').write_text(json.dumps({'seed': SEED, 'selection': key}, indent=2) + '\n', encoding='utf-8', newline='\n')
    manifest = {'seed': SEED, 'candidate_counts': {k: len(v) for k,v in strata.items()},
                'case_counts': {k: 10 for k in strata}, 'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'candidate_counts': manifest['candidate_counts'], 'case_counts': manifest['case_counts']}))

if __name__ == '__main__':
    generate()
