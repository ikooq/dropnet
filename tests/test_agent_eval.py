from dropnet.ftc import agent_eval, campaigns
from tests.test_ftc_campaigns import g  # noqa: F401


def test_agent_eval_counts(g):  # noqa: F811
    campaigns.write_campaigns(g, min_numbers=5)
    r = agent_eval.run(g, n=1000, seed=0)
    assert r["sampled"] == 18  # every number in the fixture (fewer than n)
    # 8 one-off spoofed numbers + 1 later spoofed one -> a naive "reported = scammer" agent blames 9 innocents
    assert r["naive_blames_likely_spoofed"] == 9
    # pool numbers reported once ("not worth a look" for a naive agent) that Dropnet ties to a pool
    assert r["naive_dismisses_pool_members"] == 1
    assert r["dropnet_flags_spoofed"] == r["naive_blames_likely_spoofed"]
    assert set(r["verdicts"]) <= {"likely_spoofed", "pool", "repeat", "single"}


def test_agent_eval_is_deterministic(g):  # noqa: F811
    assert agent_eval.run(g, n=5, seed=1) == agent_eval.run(g, n=5, seed=1)
