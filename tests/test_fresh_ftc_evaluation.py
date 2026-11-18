from scripts.evaluate_fresh_ftc import evaluate
from tests.test_ftc_load import R


def test_fresh_evaluation_freezes_training_and_audits_call_dates():
    train=[R(1,'2178630001',day='2026-10-01'),R(2,'2178630001',day='2026-10-02')]
    # A later observation must not turn a number into a baseline rule.
    train.append(R(3,'2178630002',day='2026-11-03'))
    fresh=[R(4,'2178630001',day='2026-11-13'), R(5,'2178630002',day='2026-11-14'),
           R(6,'2178630001',day='2026-11-15')]
    fresh[0].violation_day='2026-11-12'
    fresh[1].violation_day='2026-11-15'
    fresh[2].violation_day='2026-11-14'
    result=evaluate(train,fresh)
    assert result['train_reports']==2 and result['baseline_numbers']==1
    assert result['new_filed']['reports']==3 and result['new_filed']['hits']['baseline']==2
    assert result['event_date_subset']['reports']==1 and result['event_date_subset']['hits']['baseline']==1
    assert result['date_audit']['call_after_filing']==1 and result['date_audit']['call_before_new_window']==1
