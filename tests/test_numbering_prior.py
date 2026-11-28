import relate

from dropnet.ftc import numbering
from dropnet.store import rows


def _graph(conn):
    """Two carrier groups with two ranges each. G1's first range is flagged before the split, its second after."""
    rows(conn, """UNWIND [['G1', 'O1', ['201200', '201201']], ['G2', 'O2', ['301300', '301301']]] AS c
                  CREATE (g:CarrierGroup {name: c[0], codes_held: 2})
                  CREATE (x:Carrier {ocn: c[1], name: c[0], codes_held: 2})-[:PART_OF]->(g)
                  WITH x, c UNWIND c[2] AS blk
                  CREATE (:Block {npa_nxx: blk, state: 'NJ'})-[:HELD_BY]->(x)""")

    def report(number, day, i):
        rows(conn, """MATCH (b:Block {npa_nxx: substring($n, 0, 6)})
                      MERGE (n:Number {number: $n})-[:IN_BLOCK]->(b)
                      CREATE (:Report {id: $id, day: $d, neighbor: false})-[:FROM_NUMBER]->(n)""",
             {"n": number, "d": day, "id": f"R{i}"})

    i = 0
    for k in range(5):  # flagged before the split
        report(f"201200{k:04d}", "2026-10-01", i := i + 1)
    report("2012010000", "2026-10-01", i := i + 1)  # seen before, flagged after
    for k in range(1, 5):
        report(f"201201{k:04d}", "2026-10-20", i := i + 1)
    report("3013000000", "2026-10-01", i := i + 1)  # seen before, never flagged
    report("3013010000", "2026-10-01", i := i + 1)
    rows(conn, """MATCH (b:Block) WITH b, COUNT { (b)<-[:IN_BLOCK]-() } AS n WHERE n >= 5
                  CREATE (:FtcCampaign {id: 'POOL-' + b.npa_nxx, kind: 'pool', reports: n, numbers: n})
                         -[:USES_BLOCK]->(b)""")


def test_carrier_prior_uses_only_pre_split_flags_to_pick_leaders():
    with relate.connect(":memory:") as conn:
        _graph(conn)
        p = numbering.carrier_prior(conn, "2026-10-10", top=1, min_held=1)
    assert [x["carrier"] for x in p["leaders"]] == ["G1"]
    assert p["leaders"][0]["flagged_per_100_ranges"] == 50.0
    assert (p["open_ranges"], p["leader_ranges"], p["other_ranges"]) == (3, 1, 2)
    assert (p["leader_flagged_later"], p["other_flagged_later"]) == (1.0, 0.0)
    assert p["new_flagged_ranges"] == 1 and p["new_flagged_held_by_leaders"] == 1


def test_carrier_ranking_normalises_by_ranges_held():
    with relate.connect(":memory:") as conn:
        _graph(conn)
        r = numbering.carrier_ranking(conn)
    assert r == [{"carrier": "G1", "ranges_held": 2, "flagged": 2, "reports": 10, "numbers": 10, "ocns": 1,
                  "states": 1, "flagged_per_100_ranges": 100.0}]
