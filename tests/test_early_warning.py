from dropnet.ftc import early_warning


def test_rules_only_count_from_the_next_day():
    reps = [(f"2125550{k:03d}", "212555", "2026-11-01", False) for k in range(5)]  # 5 numbers on day 1
    reps += [("2125550999", "212555", "2026-11-01", False)]                       # same day: not yet flagged
    reps += [("2125550500", "212555", "2026-11-02", False)]                       # next day: flagged range
    r = early_warning.replay(reps)
    assert r["ranges_flagged"] == 1
    assert r["complaints"] == 7
    assert r["caught_by_range_rule"] == round(1 / 7, 4)
    assert r["numbers_first_seen_after_flag"] == 1
    assert r["days_first_complaint_to_flag"]["median"] == 0


def test_area_code_matches_never_flag_a_range_and_number_rule_needs_two_prior_days():
    reps = [(f"3035550{k:03d}", "303555", "2026-11-01", True) for k in range(8)]  # all match the consumer area
    reps += [("4155550000", "415555", d, False) for d in ("2026-11-01", "2026-11-02", "2026-11-03")]
    r = early_warning.replay(reps)
    assert r["ranges_flagged"] == 0
    assert r["caught_by_number_rule"] == round(1 / 11, 4)  # only the third report of 415-555-0000


def test_toll_free_is_left_out_of_the_geographic_replay():
    reps = [(f"8667710{k:03d}", "866771", "2026-11-01", False) for k in range(6)]
    assert early_warning.replay(reps)["complaints"] == 0
    assert early_warning.replay(reps, geographic_only=False)["complaints"] == 6


def test_example_picks_range_with_most_numbers_after_flag():
    reps = [(f"303555{k:04d}", "303555", "2026-11-01", False) for k in range(5)]          # flagged Nov 1
    reps += [(f"303555{k:04d}", "303555", "2026-11-03", False) for k in range(5, 12)]     # 7 new after
    reps += [(f"720555{k:04d}", "720555", "2026-11-01", False) for k in range(6)]         # flagged, nothing after
    reps += [(f"800555{k:04d}", "800555", "2026-11-01", False) for k in range(20)]        # toll-free, ignored
    ex = early_warning.example(reps)
    assert ex["block"] == "303555" and ex["flag_day"] == "2026-11-01"
    assert ex["numbers_after_flag"] == 7 and ex["complaints_after_flag"] == 7
    assert [d["new_numbers"] for d in ex["days"]] == [5, 7]
