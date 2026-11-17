"""Describe completed timed lookup tasks, including missing and unsure outcomes."""
import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(answers, key_path):
    key={r['task_id']:r for r in json.loads(key_path.read_text(encoding='utf-8'))['cases']}
    groups=defaultdict(list); seen=set(); assignments={}
    with answers.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            task=row['task_id'].strip(); participant=row['participant_id'].strip(); assignment=row['assignment_A_or_B'].strip().upper()
            if not participant and not assignment and not row['method'].strip():
                continue
            if not participant or assignment not in ('A','B') or task not in key or (participant,task) in seen:
                raise ValueError(f'Invalid or duplicate task: {participant}/{task}')
            seen.add((participant,task))
            if participant in assignments and assignments[participant]!=assignment:
                raise ValueError('Participant has multiple assignments')
            assignments[participant]=assignment
            idx=int(task[1:]); expected=('baseline' if idx<=6 else 'dropnet') if assignment=='A' else ('dropnet' if idx<=6 else 'baseline')
            method=row['method'].strip().lower()
            if method != expected: raise ValueError(f'Wrong method for {participant}/{task}: expected {expected}')
            sec=float(row['elapsed_seconds']) if row['elapsed_seconds'].strip() else None
            if sec is not None and (not 0 < sec <= 3600): raise ValueError('Invalid elapsed time')
            count=int(row['report_count']) if row['report_count'].strip() else None
            if count is not None and count < 0: raise ValueError('Negative count')
            choice=row['call_after_filing_yes_no_unsure'].strip().lower() or 'missing'
            if choice not in ('yes','no','unsure','missing'): raise ValueError('Invalid date answer')
            truth='yes' if key[task]['call_after_filing_count'] else 'no'
            groups[(participant,method)].append({'seconds':sec,'count_correct':count==key[task]['report_count'] if count is not None else None,
                                                'date_correct':choice==truth if choice in ('yes','no') else None,'date_response':choice})
    output=[]
    for (p,m),rs in sorted(groups.items()):
        times=[x['seconds'] for x in rs if x['seconds'] is not None]
        output.append({'participant_id':p,'method':m,'tasks_recorded':len(rs),'expected_tasks':6,
                       'time_missing':len(rs)-len(times),'median_seconds':statistics.median(times) if times else None,
                       'count_correct':sum(x['count_correct'] is True for x in rs),
                       'count_missing':sum(x['count_correct'] is None for x in rs),
                       'date_correct':sum(x['date_correct'] is True for x in rs),
                       'date_unsure':sum(x['date_response']=='unsure' for x in rs),
                       'date_missing':sum(x['date_response']=='missing' for x in rs)})
    return output


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('answers',type=Path);ap.add_argument('key',type=Path);args=ap.parse_args()
    print(json.dumps(summarize(args.answers,args.key),ensure_ascii=False,indent=2))
