import relate

from dropnet.ftc import numbering
from dropnet.store import rows


def test_related_ranges_are_other_flagged_ranges_of_the_same_ocn():
    with relate.connect(":memory:") as conn:
        rows(conn, """
            CREATE (c:Carrier {ocn: 'A1'}), (other:Carrier {ocn: 'B2'})
            CREATE (q:Block {npa_nxx: '771999'})-[:HELD_BY]->(c)
            CREATE (f1:Block {npa_nxx: '202111'})-[:HELD_BY]->(c)
            CREATE (f2:Block {npa_nxx: '202222'})-[:HELD_BY]->(c)
            CREATE (:Block {npa_nxx: '202333'})-[:HELD_BY]->(c)
            CREATE (x:Block {npa_nxx: '303444'})-[:HELD_BY]->(other)
            CREATE (:FtcCampaign {id: 'POOL-771999', kind: 'pool', reports: 50})-[:USES_BLOCK]->(q)
            CREATE (:FtcCampaign {id: 'POOL-202111', kind: 'pool', reports: 9})-[:USES_BLOCK]->(f1)
            CREATE (:FtcCampaign {id: 'POOL-202222', kind: 'pool', reports: 20})-[:USES_BLOCK]->(f2)
            CREATE (:FtcCampaign {id: 'POOL-303444', kind: 'pool', reports: 99})-[:USES_BLOCK]->(x)
        """)
        net = numbering.range_network(conn, "771999")
    assert net["ocn"] == "A1"
    assert net["related"] == [{"block": "202222", "campaign": "POOL-202222", "reports": 20},
                              {"block": "202111", "campaign": "POOL-202111", "reports": 9}]
