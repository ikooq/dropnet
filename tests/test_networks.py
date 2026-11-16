from dropnet import store
from dropnet.ftc import campaigns, load, networks
from tests.test_ftc_load import R


def build(tmp_path, reports):
    c = store.open_store(tmp_path / "n.rl")
    load.load_reports(c, reports)
    campaigns.write_campaigns(c, min_numbers=3)
    return c


def test_sibling_pools_share_area_day_subject(tmp_path):
    reps, i = [], 0
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        for blk in ("866771", "877578"):  # two ranges hitting the same areas on the same days, same scam
            for k in range(3):
                i += 1
                reps.append(R(i, f"{blk}{k:04d}", victim_npa="303", subject="DEBT", day=day))
    for k in range(3):  # an unrelated pool: different area, subject and days
        i += 1
        reps.append(R(i, f"844515{k:04d}", victim_npa="212", subject="MEDICAL", day="2026-11-09"))
    c = build(tmp_path, reps)
    n = networks.link_pools(c, min_shared=3)
    assert n["links"] == 1 and n["networks"] == 1
    r = store.rows(c, """MATCH (a:FtcCampaign)-[s:SIBLING]-(b:FtcCampaign) WHERE a.id < b.id
                         RETURN a.id AS a, b.id AS b, s.shared AS shared""")
    assert r == [{"a": "POOL-866771", "b": "POOL-877578", "shared": 3}]
    net = store.rows(c, "MATCH (c:FtcCampaign {id: 'POOL-866771'})-[:IN_NETWORK]->(n:PoolNetwork) RETURN n.pools AS p")
    assert net[0]["p"] == 2
    ev = networks.explain_siblings(c, "POOL-866771", "POOL-877578")
    assert ev["shared"] == 3 and ev["examples"][0]["area"] == "303" and ev["examples"][0]["subject"] == "DEBT"
    from dropnet.ftc import api
    nets = api.networks(c)
    assert nets[0]["pools"] == 2 and {m["id"] for m in nets[0]["members"]} == {"POOL-866771", "POOL-877578"}
    networks.link_pools(c, min_shared=3)  # idempotent
    assert store.rows(c, "MATCH ()-[s:SIBLING]->() RETURN count(s) AS n")[0]["n"] == 1
    c.close()
