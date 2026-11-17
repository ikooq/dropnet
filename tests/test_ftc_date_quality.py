from dropnet.ftc.date_quality import chronology
from dropnet.ftc import campaigns, load
from tests.test_ftc_load import R


def test_chronology_checks_dates_without_repair():
    assert chronology('2026-10-15', '2026-10-16') == 'call_after_filing'
    assert chronology('2026-10-15', '2026-10-15') == 'valid'
    assert chronology('2026-10-15', '2026-10-14') == 'valid'
    assert chronology('2026-10-15', '') == 'missing'
    assert chronology('2026-02-30', '2026-01-01') == 'invalid'


def test_number_assessment_reports_inconsistent_dates(tmp_path):
    from dropnet import store
    conn = store.open_store(tmp_path / 'dates.rl')
    try:
        first = R(1, '2178637210', day='2026-10-15')
        first.violation_day = '2026-10-16'
        second = R(2, '2178637210', day='2026-10-15')
        second.violation_day = ''
        load.load_reports(conn, [first, second])
        quality = campaigns.assess_number(conn, first.number)['date_quality']
        assert quality['call_after_filing'] == 1 and quality['missing'] == 1
        assert quality['examples'][0]['filing_date'] == '2026-10-15'
        assert quality['examples'][0]['reported_call_date'] == '2026-10-16'
    finally:
        conn.close()
