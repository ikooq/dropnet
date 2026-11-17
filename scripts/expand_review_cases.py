"""Expand the original review cases without replacing the cards already reviewed."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from dropnet.ftc.parse import SUBJECT_LABEL, read_reports

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'docs' / 'independent-review'
RAW = ROOT / 'data' / 'ftc' / 'raw'


def main():
    selection = json.loads((PACK / 'selection-key.json').read_text(encoding='utf-8'))['selection']
    manifest = json.loads((PACK / 'manifest.json').read_text(encoding='utf-8'))
    paths = sorted(RAW.glob('*.csv.gz'))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    if hashes != manifest['files']:
        raise SystemExit('FTC input files differ from the original review manifest; refusing to regenerate')
    by_block = {item['block']: item for item in selection}
    if len(by_block) != len(selection):
        raise SystemExit('Duplicate selected block')
    reports = defaultdict(list)
    for path in paths:
        for report in read_reports([path]):
            block = report.number[:6]
            if block in by_block:
                reports[block].append((report, path.name))
    if any(not reports[item['block']] for item in selection):
        raise SystemExit('A selected block has no reports')
    cards = ['# Expanded case evidence', '',
             'These expanded cards were created after the original review. They were not shown to that reviewer;',
             'the previous review results apply only to the initial review pack’s `cases.md` cards.', '',
             'Each report is an unverified FTC complaint. Report IDs are generated from source filename and row,',
             'not FTC case identifiers. Filing date and reported call date are separate source fields;',
             'reported call dates may be missing, malformed, or inconsistent. The source provides categories,',
             'not complete complaint narratives. Caller ID can be spoofed. A shared prefix, topic or consumer',
             'area code does not establish a common caller, ownership, spoofing or wrongdoing.', '',
             'For every case, the complete complaint-to-number links are in `case-evidence.csv`.',
             'Each card shows up to five examples chosen deterministically by report ID, not by relevance.', '']
    rows = []
    for item in selection:
        case, block = item['case_id'], item['block']
        entries = sorted(reports[block], key=lambda x: (x[0].id, x[1]))
        rs = [r for r, _ in entries]
        nums = Counter(r.number for r in rs)
        topics = Counter(r.subject for r in rs)
        dates = sorted(r.created_day for r in rs if r.created_day)
        top_code, top_count = sorted(topics.items(), key=lambda x: (-x[1], x[0]))[0]
        label = SUBJECT_LABEL.get(top_code, top_code)
        evidence = f'{len(rs)} complaints, {len(nums)} caller ID(s), {top_count} in the most common category ({label})'
        if len(nums) == 1:
            hypothesis = f'Check whether the {len(rs)} complaint(s) about this reported number warrant follow-up. A single number does not support a cross-number link.'
        else:
            hypothesis = (f'Check whether the complaints involving these {len(nums)} reported numbers deserve a joint review '
                          'based on their shared six-digit prefix and observed complaint patterns; '
                          'they may instead reflect unrelated callers or inaccurate caller IDs.')
        cards += [f'## {case}', '', f'**Hypothesis:** {hypothesis}', '',
                  f'- Shared numbering prefix: `{block}`. Observed evidence: {evidence}.',
                  f'- Filing-date range: {dates[0] if dates else "unknown"} to {dates[-1] if dates else "unknown"}.',
                  '- Topics (complaint counts): ' + '; '.join(f'{SUBJECT_LABEL.get(k,k)}: {v}' for k,v in sorted(topics.items(), key=lambda x:(-x[1], x[0]))) + '.',
                  '- Reported caller IDs → complaint counts: ' + '; '.join(f'`{n}`: {c}' for n,c in sorted(nums.items())) + '.',
                  f'- Complaint → caller ID → six-digit prefix is an observed data link. '
                  f'{sum(r.neighbor for r in rs)} complaint(s) have matching caller/consumer area codes; '
                  f'{sum(not r.victim_npa for r in rs)} lack a consumer area code.',
                  '', '**Example complaint links** (complete rows in the CSV):', '',
                  '| Report ID | Filing date | Reported call date | Caller ID | Topic | Consumer area code |',
                  '|---|---|---|---|---|---|']
        for r, source in entries:
            rows.append([case, r.id, source, r.created_day, r.violation_day, r.number, block,
                         r.subject, SUBJECT_LABEL.get(r.subject, r.subject), r.victim_npa,
                         'yes' if r.neighbor else 'no' if r.victim_npa else 'unknown'])
        for r, _ in entries[:5]:
            cards.append(f'| `{r.id}` | {r.created_day or "unknown"} | {r.violation_day or "unknown"} | '
                         f'`{r.number}` | {SUBJECT_LABEL.get(r.subject, r.subject)} | {r.victim_npa or "unknown"} |')
        cards += ['', '**Limits:** The data do not confirm a common operator, fraud or the caller’s identity. '
                  'A shared filing date is not proof of calls on the same day. Independent corroboration is needed.', '']
    with (PACK / 'case-evidence.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(['case_id','report_id','source_file','filing_date','reported_call_date','reported_caller_id',
                         'six_digit_prefix','subject_code','subject_label','consumer_area_code','area_codes_match'])
        writer.writerows(rows)
    (PACK / 'case-cards-expanded.md').write_text('\n'.join(cards), encoding='utf-8', newline='\n')
    print(f'Generated {len(selection)} cards and {len(rows)} linked complaint rows')


if __name__ == '__main__':
    main()
