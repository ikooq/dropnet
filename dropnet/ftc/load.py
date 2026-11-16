"""Write FTC reports into Relate:

(:Report)-[:FROM_NUMBER]->(:Number)-[:IN_BLOCK]->(:Block {npa_nxx})-[:IN_AREA]->(:AreaCode)
(:Report)-[:ABOUT]->(:Subject), -[:VICTIM_IN]->(:State), -[:VICTIM_AREA]->(:AreaCode), -[:ON_DAY]->(:Day)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import relate

from ..store import rows
from .parse import SUBJECT_LABEL, Report

INDEXES = [("Number", "number"), ("Block", "npa_nxx"), ("AreaCode", "npa"), ("Subject", "code"), ("State", "name"),
           ("Day", "day"), ("Report", "id")]


def ensure_indexes(conn: relate.Connection) -> None:
    for label, prop in INDEXES:
        rows(conn, f"CREATE INDEX {label.lower()}_{prop}_idx IF NOT EXISTS FOR (n:{label}) ON (n.{prop})")


def ensure_fulltext(conn: relate.Connection) -> None:
    """Relate full-text index over scam-type labels (search 'mortgage', 'medical', 'government' …)."""
    rows(conn, "CREATE FULLTEXT INDEX subject_label_ft IF NOT EXISTS FOR (s:Subject) ON EACH [s.label]")


def _chunks(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def load_reports(conn: relate.Connection, reports: Iterable[Report], batch: int = 20_000) -> dict[str, int]:
    reports = list(reports)
    ensure_indexes(conn)
    numbers: dict[str, dict] = {}
    for r in reports:
        n = numbers.setdefault(r.number, {"number": r.number, "npa": r.npa, "block": r.npa + r.nxx, "reports": 0,
                                          "first": r.created_day, "last": r.created_day, "toll_free": r.toll_free})
        n["reports"] += 1
        n["first"] = min(n["first"], r.created_day)
        n["last"] = max(n["last"], r.created_day)
    areas = sorted({r.npa for r in reports} | {r.victim_npa for r in reports if r.victim_npa})
    blocks = sorted({n["block"] for n in numbers.values()})
    rows(conn, "UNWIND $a AS a MERGE (:AreaCode {npa: a})", {"a": areas})
    rows(conn, "UNWIND $s AS s MERGE (x:Subject {code: s.code}) SET x.label = s.label",
         {"s": [{"code": c, "label": SUBJECT_LABEL.get(c, c)} for c in sorted({r.subject for r in reports})]})
    rows(conn, "UNWIND $s AS s MERGE (:State {name: s})", {"s": sorted({r.state for r in reports if r.state})})
    for part in _chunks(blocks, batch):
        rows(conn, """UNWIND $b AS b MATCH (a:AreaCode {npa: substring(b, 0, 3)})
                      MERGE (k:Block {npa_nxx: b}) MERGE (k)-[:IN_AREA]->(a)""", {"b": part})
    for part in _chunks(list(numbers.values()), batch):
        rows(conn, """UNWIND $n AS n MATCH (k:Block {npa_nxx: n.block})
                      MERGE (x:Number {number: n.number})
                      SET x.npa = n.npa, x.reports = coalesce(x.reports, 0) + n.reports,
                          x.first_day = n.first, x.last_day = n.last, x.toll_free = n.toll_free
                      MERGE (x)-[:IN_BLOCK]->(k)""", {"n": part})
    by_shape = defaultdict(list)
    for r in reports:
        by_shape[(bool(r.state), bool(r.victim_npa))].append({
            "id": r.id, "number": r.number, "day": r.created_day, "vday": r.violation_day, "created": r.created,
            "subject": r.subject, "state": r.state, "vnpa": r.victim_npa, "city": r.city, "robocall": r.robocall,
            "neighbor": r.neighbor})
    for (has_state, has_vnpa), items in by_shape.items():
        q = ["UNWIND $r AS r",
             "MATCH (n:Number {number: r.number}), (s:Subject {code: r.subject})"]
        if has_state:
            q.append("MATCH (st:State {name: r.state})")
        if has_vnpa:
            q.append("MATCH (va:AreaCode {npa: r.vnpa})")
        # slim on purpose: the store must fit in a git repo (<95 MB); subject/state/area live on relationships
        q.append("""CREATE (x:Report {id: r.id, day: r.day, violation_day: r.vday,
                                      robocall: r.robocall, neighbor: r.neighbor})
                    CREATE (x)-[:FROM_NUMBER]->(n) CREATE (x)-[:ABOUT]->(s)""")
        if has_state:
            q.append("CREATE (x)-[:VICTIM_IN]->(st)")
        if has_vnpa:
            q.append("CREATE (x)-[:VICTIM_AREA]->(va)")
        for part in _chunks(items, batch):
            rows(conn, "\n".join(q), {"r": part})
    return {"reports": len(reports), "numbers": len(numbers), "blocks": len(blocks)}
