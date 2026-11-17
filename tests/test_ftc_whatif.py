from dropnet import store
from dropnet.ftc import campaigns, whatif
from tests.test_ftc_campaigns import g  # noqa: F401  (fixture)


def test_whatif_counts_and_rolls_back(g):  # noqa: F811
    r = whatif.whatif(g, blocks=["866771"], numbers=["2178637210"])
    assert r["reports_stopped"] == 19 + 6
    assert r["numbers_covered"] == 7 + 1
    assert r["campaigns_touched"] == []  # campaigns not written in this fixture
    assert store.rows(g, "MATCH (r:Rule) RETURN count(r) AS n")[0]["n"] == 0
    assert g.autocommit is True


def test_whatif_since_day_and_campaigns(g):  # noqa: F811
    campaigns.write_campaigns(g, min_numbers=5)
    r = whatif.whatif(g, blocks=["866771"], since_day="2026-11-05")
    assert r["reports_stopped"] == 1
    assert r["campaigns_touched"] == ["POOL-866771"]


def test_whatif_rejects_bad_input(g):  # noqa: F811
    import pytest
    with pytest.raises(ValueError):
        whatif.whatif(g, blocks=["86677"])
    with pytest.raises(ValueError):
        whatif.whatif(g)


def test_export_case_single_file(g, tmp_path):  # noqa: F811
    campaigns.write_campaigns(g, min_numbers=5)
    out = tmp_path / "POOL-866771.rl"
    stats = whatif.export_case(g, "POOL-866771", out)
    assert stats == {"reports": 19, "numbers": 7, "blocks": 1}
    c = store.open_store(out, read_only=True)
    assert store.rows(c, "MATCH (:FtcCampaign {id: 'POOL-866771'})-[:USES_BLOCK]->(b:Block)<-[:IN_BLOCK]-(n:Number)"
                         "<-[:FROM_NUMBER]-(r:Report) RETURN count(r) AS n")[0]["n"] == 19
    c.close()


def test_whatif_deduplicates_and_discloses_unknown_rules(g):
    r = whatif.whatif(g, blocks=["866771", "866-771", "999999"], numbers=["9999999999"])
    assert r["rules"] == 3 and r["applied_rules"] == 1
    assert r["unknown_blocks"] == ["999999"]
    assert r["unknown_numbers"] == ["9999999999"]
    assert r["reports_stopped"] == 19
    assert store.rows(g, "MATCH (r:Rule) RETURN count(r) AS n")[0]["n"] == 0
