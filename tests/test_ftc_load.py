from dropnet import store
from dropnet.ftc import load
from dropnet.ftc.parse import Report


def R(i, number, victim_npa="713", subject="DEBT", day="2026-11-01", robocall=True, state="Texas"):
    return Report(id=f"r{i}", number=number, npa=number[:3], nxx=number[3:6], created=f"{day} 10:00:00",
                  violation_day=day, city="Houston", state=state, victim_npa=victim_npa, subject=subject,
                  robocall=robocall, neighbor=number[:3] == victim_npa, toll_free=number[:3] in {"800", "888"})


def build(tmp_path, reports):
    conn = store.open_store(tmp_path / "f.rl")
    stats = load.load_reports(conn, reports)
    return conn, stats


def one(conn, q, **p):
    return store.rows(conn, q, p)[0]


def test_graph_shape(tmp_path):
    reports = [R(1, "7135550101"), R(2, "7135550101", victim_npa="281", state="Texas"),
               R(3, "7135550199", subject="MEDICAL", day="2026-11-02"), R(4, "8005550100", victim_npa="303",
                                                                         state="Colorado", robocall=None)]
    conn, stats = build(tmp_path, reports)
    assert stats == {"reports": 4, "numbers": 3, "blocks": 2}
    assert one(conn, "MATCH (:Report)-[:FROM_NUMBER]->(n:Number {number: '7135550101'}) RETURN count(*) AS c")["c"] == 2
    assert one(conn, "MATCH (n:Number {number: '7135550101'})-[:IN_BLOCK]->(b:Block)-[:IN_AREA]->(a:AreaCode) "
                     "RETURN b.npa_nxx AS b, a.npa AS a") == {"b": "713555", "a": "713"}
    assert one(conn, "MATCH (n:Number {number: '7135550101'}) RETURN n.reports AS r, n.first_day AS f, "
                     "n.last_day AS l") == {"r": 2, "f": "2026-11-01", "l": "2026-11-01"}
    assert one(conn, "MATCH (r:Report {id: 'r1'})-[:ABOUT]->(s:Subject) RETURN s.code AS c")["c"] == "DEBT"
    assert one(conn, "MATCH (r:Report {id: 'r1'})-[:VICTIM_AREA]->(a:AreaCode) RETURN a.npa AS n")["n"] == "713"
    assert one(conn, "MATCH (r:Report {id: 'r4'})-[:VICTIM_IN]->(s:State) RETURN s.name AS n")["n"] == "Colorado"
    assert one(conn, "MATCH (r:Report {id: 'r1'}) RETURN r.neighbor AS n, r.day AS d")["n"] is True
    assert one(conn, "MATCH (r:Report) WHERE r.robocall IS NULL RETURN count(r) AS c")["c"] == 1
    assert one(conn, "MATCH (r:Report {day: '2026-11-02'}) RETURN count(r) AS c")["c"] == 1
    conn.close()


def test_batches_are_equivalent(tmp_path):
    reports = [R(i, f"71355501{i:02d}") for i in range(30)]
    conn = store.open_store(tmp_path / "b.rl")
    load.load_reports(conn, reports, batch=7)
    assert one(conn, "MATCH (r:Report) RETURN count(r) AS c")["c"] == 30
    assert one(conn, "MATCH (b:Block) RETURN count(b) AS c")["c"] == 1
    conn.close()
