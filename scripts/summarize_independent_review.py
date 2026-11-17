"""Summarize completed independent-review responses without inventing missing data."""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY = ROOT / 'docs' / 'independent-review' / 'selection-key.json'
FIELDS = ('evidence_clear_yes_no_unsure', 'investigate_yes_no_unsure')


def summarize(path):
    cases = {item['case_id']: item['stratum'] for item in json.loads(KEY.read_text(encoding='utf-8'))['selection']}
    counts = {group: {field: Counter() for field in FIELDS} for group in sorted(set(cases.values()))}
    seen = set()
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not set(('case_id', *FIELDS)) <= set(reader.fieldnames or []):
            raise ValueError('Missing required CSV columns')
        for row in reader:
            case = row['case_id'].strip()
            if case not in cases or case in seen:
                raise ValueError(f'Unknown or duplicate case: {case}')
            seen.add(case)
            for field in FIELDS:
                value = row[field].strip().lower() or 'missing'
                if value not in ('yes', 'no', 'unsure', 'missing'):
                    raise ValueError(f'Invalid {field} for {case}: {value}')
                counts[cases[case]][field][value] += 1
    for case in cases.keys() - seen:
        for field in FIELDS:
            counts[cases[case]][field]['missing'] += 1
    return {group: {field: {v: counts[group][field][v] for v in ('yes', 'no', 'unsure', 'missing')}
                    for field in FIELDS} for group in counts}


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python scripts/summarize_independent_review.py path/to/completed_answers.csv')
    print(json.dumps(summarize(Path(sys.argv[1])), indent=2))
