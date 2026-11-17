from dropnet.ftc.time_audit import audit
from tests.test_ftc_load import R


def test_event_subset_excludes_earlier_and_future_events():
    train = [R(i, f"303555{i:04d}", victim_npa="212", day="2026-11-01") for i in range(5)]
    later = R(10, "3035550001", victim_npa="212", day="2026-11-03")
    later.violation_day = "2026-11-02"
    prior = R(11, "3035550002", victim_npa="212", day="2026-11-03")
    prior.violation_day = "2026-11-01"
    impossible = R(12, "3035550003", victim_npa="212", day="2026-11-03")
    impossible.violation_day = "2026-11-04"
    r = audit(train + [later, prior, impossible], "2026-11-02")
    assert r["test_filed"] == 3
    assert r["test_event_before_split"] == 1
    assert r["test_event_after_filing"] == 1
    assert r["test_event_on_or_after_split_valid"] == 1
    assert r["event_subset_geographic_coverage"] == 1.0
