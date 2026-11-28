import relate

from dropnet.ftc import numbering
from dropnet.store import rows


def test_unassigned_code_keeps_rate_center_without_a_carrier(tmp_path):
    numbering._write(
        tmp_path / numbering.CODES_CSV,
        ["block", "state", "ocn", "company", "rate_center", "pooled"],
        [{"block": "228228", "state": "MS", "ocn": "", "company": "",
          "rate_center": "GULFPORT", "pooled": False}],
    )
    numbering._write(tmp_path / numbering.SUBBLOCKS_CSV, ["block", "x", "status", "ocn", "company"], [])
    numbering._write(
        tmp_path / numbering.HOLDINGS_CSV,
        ["ocn", "company", "codes"],
        [{"ocn": "", "company": "", "codes": 1}],
    )

    with relate.connect(":memory:") as conn:
        rows(conn, "CREATE (:Block {npa_nxx: '228228'})")
        numbering.link(conn, tmp_path)

        assert rows(conn, "MATCH (c:Carrier) RETURN count(c) AS n") == [{"n": 0}]
        assert rows(conn, """
            MATCH (:Block {npa_nxx: '228228'})-[:IN_RATE_CENTER]->(r:RateCenter)
            RETURN r.id AS id
        """) == [{"id": "MS:GULFPORT"}]
