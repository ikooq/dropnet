from dropnet.ftc import campaigns, evaluate, robustness
from tests.test_ftc_campaigns import g  # noqa: F401


def test_python_pool_rule_matches_cypher(g):  # noqa: F811
    reports = robustness.load(g)
    train, _ = robustness._split(reports, "2026-11-05")
    cypher = {p["block"] for p in campaigns.pool_campaigns(g, 5, exclude_neighbor=True, until_day="2026-11-05")}
    assert robustness.pools(train, 5) == cypher == {"866771"}
    # counting spoofed reports too turns the victims' own local block into a "pool"
    assert robustness.pools(train, 5, exclude_neighbor=False) == {"866771", "303555"}


def test_scores_match_the_holdout(g):  # noqa: F811
    reports = robustness.load(g)
    res = evaluate.holdout(g, split_day="2026-11-05")
    train, test = robustness._split(reports, "2026-11-05")
    nums = robustness._numbers(train)
    assert robustness._score(test, nums, set()) == res["baseline"]["coverage"]
    assert robustness._score(test, nums, robustness.pools(train)) == res["dropnet"]["coverage"]


def test_bootstrap_thresholds_ablations(g):  # noqa: F811
    reports = robustness.load(g)
    b = robustness.bootstrap(reports, "2026-11-05", reps=50)
    assert b["test_days"] == 1 and b["dropnet"][0] <= b["dropnet"][1]
    t = robustness.thresholds(reports, "2026-11-05", ms=(3, 5))
    assert [x["min_numbers"] for x in t] == [3, 5]
    a = robustness.ablations(reports, "2026-11-05")
    assert a["pools_including_spoofed"]["extra_blocks"] == 1  # the 303-555 victim-area block
    assert a["pools_including_spoofed"]["spoofed_numbers_hit"] == 1.0  # the later spoofed call lands in it
    assert a["ours_spoofed_numbers_hit"] == 0.0
