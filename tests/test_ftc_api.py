from dropnet.ftc import api, campaigns
from tests.test_ftc_campaigns import g  # noqa: F401


def test_summary(g):  # noqa: F811
    s = api.summary(g)
    assert s["reports"] == 35 and s["numbers"] == 18 and s["first_day"] == "2026-11-01"
    assert 0 < s["neighbor_share"] < 1 and 0 < s["single_report_numbers_share"] <= 1


def test_campaign_list_and_graph(g):  # noqa: F811
    campaigns.write_campaigns(g, min_numbers=5)
    lst = api.campaign_list(g)
    assert lst[0]["id"] == "POOL-866771" and lst[0]["numbers"] == 7
    gr = api.campaign_graph(g, "POOL-866771")
    kinds = {n["kind"] for n in gr["nodes"]}
    assert {"Block", "Number", "State", "Subject"} <= kinds
    ids = {n["id"] for n in gr["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in gr["edges"])
    assert api.campaign_graph(g, "POOL-000000") is None


def test_campaign_graph_is_fast_on_the_real_snapshot():
    """On the real 249k-number graph an UNWIND-bound property lookup skipped the index (44 s)."""
    import time

    import pytest

    from dropnet import config, store
    snap = config.DATA_DIR / "ftc.rl"
    if not snap.exists():
        pytest.skip("real FTC snapshot not built")
    c = store.open_store(snap, read_only=True)
    try:
        t = time.perf_counter()
        gr = api.campaign_graph(c, "POOL-217863")
        elapsed = time.perf_counter() - t
    finally:
        c.close()
    assert gr and any(n["kind"] == "State" for n in gr["nodes"])
    assert elapsed < 2.0, elapsed


def test_states(g):  # noqa: F811
    st = {s["state"]: s for s in api.states(g)}
    assert st["Colorado"]["reports"] > 0 and 0 <= st["Colorado"]["neighbor_share"] <= 1
