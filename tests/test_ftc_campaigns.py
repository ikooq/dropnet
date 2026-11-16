import pytest

from dropnet import store
from dropnet.ftc import campaigns, evaluate, load
from tests.test_ftc_load import R


@pytest.fixture
def g(tmp_path):
    reports = []
    i = 0
    # a real-looking pool: 6 numbers in toll-free block 866-771, many reports, not spoofed
    for k in range(6):
        for _ in range(3):
            i += 1
            reports.append(R(i, f"866771{k:04d}", victim_npa="303", state="Colorado",
                             day="2026-11-0" + str(1 + i % 3)))
    # spoofed local calls: each number once, number area == victim area
    for k in range(8):
        i += 1
        reports.append(R(i, f"303555{k:04d}", victim_npa="303", subject="MEDICAL", day="2026-11-02"))
    # a heavy single number
    for _ in range(5):
        i += 1
        reports.append(R(i, "2178637210", victim_npa="415", state="California", day="2026-11-03"))
    # later (test period): a NEW number in the same pool block + a new spoofed number + the heavy number
    reports += [R(900, "8667719999", victim_npa="303", day="2026-11-08"),
                R(901, "3035559999", victim_npa="303", subject="MEDICAL", day="2026-11-08"),
                R(902, "2178637210", victim_npa="415", day="2026-11-08"),
                R(903, "4155550000", victim_npa="212", day="2026-11-08")]
    conn = store.open_store(tmp_path / "c.rl")
    load.load_reports(conn, reports)
    yield conn
    conn.close()


def test_pool_campaigns_exclude_spoofed_blocks(g):
    pools = campaigns.pool_campaigns(g, min_numbers=5)
    ids = [p["id"] for p in pools]
    assert ids == ["POOL-866771"]
    assert pools[0]["numbers"] == 7 and pools[0]["toll_free"] is True  # 6 + the later one
    assert campaigns.pool_campaigns(g, min_numbers=5, exclude_neighbor=False)[-1]["id"] == "POOL-303555" or \
        "POOL-303555" in [p["id"] for p in campaigns.pool_campaigns(g, min_numbers=5, exclude_neighbor=False)]


def test_pool_campaigns_respect_until_day(g):
    pools = campaigns.pool_campaigns(g, min_numbers=5, until_day="2026-11-05")
    assert pools[0]["numbers"] == 6


def test_write_campaigns(g):
    n = campaigns.write_campaigns(g, min_numbers=5)
    assert n >= 1
    r = store.rows(g, "MATCH (c:FtcCampaign {id: 'POOL-866771'})-[:USES_BLOCK]->(b:Block) "
                      "RETURN c.kind AS k, c.reports AS reps, b.npa_nxx AS b")
    assert r == [{"k": "pool", "reps": 19, "b": "866771"}]
    campaigns.write_campaigns(g, min_numbers=5)  # idempotent
    assert store.rows(g, "MATCH (c:FtcCampaign) RETURN count(c) AS n")[0]["n"] == n


def test_spoofing_profile(g):
    prof = {p["subject"]: p for p in campaigns.spoofing_profile(g)}
    assert prof["MEDICAL"]["neighbor_share"] == 1.0
    assert prof["DEBT"]["neighbor_share"] < 0.2


def test_assess_number_spoofed_vs_pool(g):
    a = campaigns.assess_number(g, "3035550003")
    assert a["verdict"] == "likely_spoofed" and a["reports"] == 1
    b = campaigns.assess_number(g, "8667710002")
    assert b["verdict"] == "pool" and b["block_numbers"] == 7
    c = campaigns.assess_number(g, "2178637210")
    assert c["verdict"] == "repeat" and c["reports"] == 6
    assert campaigns.assess_number(g, "9999999999")["verdict"] == "unknown"


def test_holdout_evaluation(g):
    res = evaluate.holdout(g, split_day="2026-11-05", min_numbers=5, min_reports=2)
    base, ours = res["baseline"], res["dropnet"]
    assert res["test_reports"] == 4
    assert base["covered"] == 1  # only the heavy number
    assert ours["covered"] == 2  # heavy number + new number in the pool block
    assert ours["new_numbers_caught"] == 1
    assert ours["spoofed_caught"] == 0  # we never block local spoofed blocks
