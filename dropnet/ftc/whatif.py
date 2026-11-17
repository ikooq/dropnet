"""What-if analysis inside a Relate transaction, and one-file case export.

whatif() writes candidate blocking rules as :Rule nodes in an explicit transaction, measures which
historical reports they match by graph traversal, and rolls back — the store is never changed, and other readers never see the
hypothetical rules (Relate isolates uncommitted state).
"""
from __future__ import annotations

import re
from pathlib import Path

import relate

from .. import store
from ..store import rows


def _clean(values, n: int, what: str) -> list[str]:
    out = []
    for v in values or []:
        d = re.sub(r"\D", "", str(v))
        if len(d) != n:
            raise ValueError(f"{what} must have {n} digits: {v!r}")
        out.append(d)
    return list(dict.fromkeys(out))


def whatif(conn: relate.Connection, blocks=None, numbers=None, since_day: str | None = None) -> dict:
    blocks, numbers = _clean(blocks, 6, "block (NPA-NXX)"), _clean(numbers, 10, "number")
    if not blocks and not numbers:
        raise ValueError("give at least one block or number")
    conn.autocommit = False
    try:
        rows(conn, "UNWIND $b AS b MATCH (k:Block {npa_nxx: b}) CREATE (:Rule {kind: 'block', value: b})-[:BLOCKS]->(k)",
             {"b": blocks})
        rows(conn, "UNWIND $n AS n MATCH (x:Number {number: n}) CREATE (:Rule {kind: 'number', value: n})-[:BLOCKS]->(x)",
             {"n": numbers})
        matched_rules = rows(conn, "MATCH (r:Rule) RETURN r.kind AS kind, r.value AS value")
        applied_blocks = {r["value"] for r in matched_rules if r["kind"] == "block"}
        applied_numbers = {r["value"] for r in matched_rules if r["kind"] == "number"}
        hit = rows(conn, """
            MATCH (rule:Rule)-[:BLOCKS]->(t)
            OPTIONAL MATCH (t)<-[:IN_BLOCK]-(viaBlock:Number)
            WITH collect(DISTINCT CASE WHEN t:Number THEN t ELSE viaBlock END) AS nums
            UNWIND nums AS n
            MATCH (n)<-[:FROM_NUMBER]-(r:Report) WHERE $since IS NULL OR r.day >= $since
            RETURN count(DISTINCT n) AS numbers, count(DISTINCT r) AS reports,
                   sum(CASE WHEN r.neighbor THEN 1 ELSE 0 END) AS spoofed""", {"since": since_day})[0]
        covered = rows(conn, """
            MATCH (rule:Rule)-[:BLOCKS]->(t)
            OPTIONAL MATCH (t)<-[:IN_BLOCK]-(viaBlock:Number)
            WITH collect(DISTINCT CASE WHEN t:Number THEN t ELSE viaBlock END) AS nums
            RETURN size(nums) AS n""")[0]["n"]
        touched = [r["id"] for r in rows(conn, """
            MATCH (:Rule)-[:BLOCKS]->(t)
            MATCH (c:FtcCampaign)-[:USES_BLOCK|USES_NUMBER]->(t) RETURN DISTINCT c.id AS id ORDER BY id""")]
    finally:
        conn.rollback()
        conn.autocommit = True
    return {"rules": len(blocks) + len(numbers), "applied_rules": len(matched_rules),
            "unknown_blocks": [b for b in blocks if b not in applied_blocks],
            "unknown_numbers": [n for n in numbers if n not in applied_numbers],
            "reports_stopped": hit["reports"], "numbers_covered": covered,
            "numbers_with_reports_in_period": hit["numbers"],
            "spoofed_reports_in_scope": hit["spoofed"] or 0, "campaigns_touched": touched, "since_day": since_day,
            "note": "Historical complaint matches only, not prevented calls; unknown rules have no matching node in the loaded graph. The transaction was rolled back."}


def export_case(conn: relate.Connection, campaign_id: str, out: Path) -> dict:
    """Write one campaign's subgraph to its own single-file Relate store (hand it over, archive it, delete it)."""
    camp = rows(conn, "MATCH (c:FtcCampaign {id: $id}) RETURN c", {"id": campaign_id})
    if not camp:
        raise KeyError(campaign_id)
    props = dict(camp[0]["c"].items())
    data = rows(conn, """
        MATCH (c:FtcCampaign {id: $id})-[:USES_BLOCK|USES_NUMBER]->(t)
        OPTIONAL MATCH (t)<-[:IN_BLOCK]-(bn:Number)
        WITH c, t, collect(DISTINCT CASE WHEN t:Number THEN t ELSE bn END) AS nums
        UNWIND nums AS n
        MATCH (n)-[:IN_BLOCK]->(b:Block)
        MATCH (n)<-[:FROM_NUMBER]-(r:Report)-[:ABOUT]->(s:Subject)
        OPTIONAL MATCH (r)-[:VICTIM_IN]->(st:State)
        RETURN b.npa_nxx AS block, n.number AS number, n.reports AS nrep, r.id AS id, r.day AS day,
               r.violation_day AS vday, r.robocall AS robocall, r.neighbor AS neighbor, s.code AS subject,
               st.name AS state""", {"id": campaign_id})
    out = Path(out)
    store.reset_store(out)
    dst = store.open_store(out)
    try:
        rows(dst, "CREATE (:FtcCampaign $p)", {"p": props})
        rows(dst, """UNWIND $d AS d
                     MERGE (b:Block {npa_nxx: d.block})
                     MERGE (n:Number {number: d.number}) SET n.reports = d.nrep
                     MERGE (n)-[:IN_BLOCK]->(b)
                     MERGE (s:Subject {code: d.subject})
                     CREATE (r:Report {id: d.id, day: d.day, violation_day: d.vday, robocall: d.robocall,
                                       neighbor: d.neighbor})
                     CREATE (r)-[:FROM_NUMBER]->(n) CREATE (r)-[:ABOUT]->(s)
                     FOREACH (_ IN CASE WHEN d.state IS NULL THEN [] ELSE [1] END |
                        MERGE (st:State {name: d.state}) CREATE (r)-[:VICTIM_IN]->(st))""", {"d": data})
        link = "USES_BLOCK" if props.get("kind") == "pool" else "USES_NUMBER"
        target = "Block" if link == "USES_BLOCK" else "Number"
        rows(dst, f"MATCH (c:FtcCampaign), (t:{target}) CREATE (c)-[:{link}]->(t)")
        stats = {"reports": len(data), "numbers": len({d["number"] for d in data}),
                 "blocks": len({d["block"] for d in data})}
    finally:
        dst.close()
    return stats
