"""Campaigns in real FTC reports, computed with Cypher on the Relate graph.

* pool — a concentration of distinct reported numbers in one NPA-NXX block.
  By default reports with matching caller and consumer area codes are excluded; a match is only an indicator,
  not proof of spoofing, ownership, allocation or a common operator.
* repeat — one reported number appearing repeatedly.
* area-code profile — share of reports with matching caller and consumer area codes.
"""
from __future__ import annotations

import relate

from ..store import rows
from .parse import SUBJECT_LABEL, TOLL_FREE

POOL_MIN_NUMBERS = 5
REPEAT_MIN_REPORTS = 100
CAUTION = ("FTC reports are unverified complaints. Caller ID can be spoofed; an area-code match is only a "
           "possible indicator, not proof of spoofing or of the owner's identity or conduct. "
           "A reported range does not establish a common operator. Do not blame a number's owner.")

# Compatibility: verdict names are retained for existing clients; they describe heuristics, not verified facts.
ADVICE = {
    "likely_spoofed": {"block": "nothing", "owner_likely_innocent": None,
                       "say": "The area codes match in each report. This may indicate spoofing, but does not prove it. "
                              "Do not infer the owner's identity or conduct; report suspicious calls."},
    "pool": {"block": "nothing", "owner_likely_innocent": None,
             "say": "The range has a concentration of reported numbers. Investigate the evidence; a range rule "
                    "can affect up to 10,000 numbers, and legitimate-call impact is unknown."},
    "repeat": {"block": "nothing", "owner_likely_innocent": None,
               "say": "This number appears in several complaints. Caller ID can be spoofed; review the evidence "
                      "before making a decision."},
    "single": {"block": "nothing", "owner_likely_innocent": None,
               "say": "There is limited evidence in the loaded reports. Do not infer who made the call."},
    "unknown": {"block": "nothing", "owner_likely_innocent": None,
                "say": "No FTC reports for this number in the loaded window; that does not prove it is safe."},
}


def pool_campaigns(conn: relate.Connection, min_numbers: int = POOL_MIN_NUMBERS, exclude_neighbor: bool = True,
                   until_day: str | None = None, limit: int | None = None) -> list[dict]:
    found = rows(conn, f"""
        MATCH (r:Report)-[:FROM_NUMBER]->(n:Number)-[:IN_BLOCK]->(b:Block)
        WHERE ($ex = false OR r.neighbor = false) AND ($until IS NULL OR r.day < $until)
        WITH b, count(DISTINCT n) AS nums, count(r) AS reps
        WHERE nums >= $m
        RETURN b.npa_nxx AS block, nums, reps ORDER BY reps DESC, block {'LIMIT $lim' if limit else ''}""",
                 {"ex": exclude_neighbor, "until": until_day, "m": min_numbers, "lim": limit})
    return [{"id": f"POOL-{f['block']}", "kind": "pool", "block": f["block"], "numbers": f["nums"],
             "reports": f["reps"], "toll_free": f["block"][:3] in TOLL_FREE} for f in found]


def _details(conn: relate.Connection, block: str) -> dict:
    subj = rows(conn, """
        MATCH (:Block {npa_nxx: $b})<-[:IN_BLOCK]-(:Number)<-[:FROM_NUMBER]-(r:Report)-[:ABOUT]->(s:Subject)
        RETURN s.code AS code, count(r) AS n ORDER BY n DESC LIMIT 3""", {"b": block})
    geo = rows(conn, """
        MATCH (:Block {npa_nxx: $b})<-[:IN_BLOCK]-(:Number)<-[:FROM_NUMBER]-(r:Report)
        OPTIONAL MATCH (r)-[:VICTIM_IN]->(st:State)
        RETURN count(DISTINCT st) AS states, min(r.day) AS first, max(r.day) AS last""", {"b": block})[0]
    return {"subjects": [s["code"] for s in subj], "states": geo["states"], "first_day": geo["first"],
            "last_day": geo["last"]}


def write_campaigns(conn: relate.Connection, min_numbers: int = POOL_MIN_NUMBERS,
                    repeat_min: int = REPEAT_MIN_REPORTS, detail_top: int = 300) -> int:
    rows(conn, "MATCH (c:FtcCampaign) DETACH DELETE c")
    pools = pool_campaigns(conn, min_numbers)
    for i, p in enumerate(pools):
        p.update(_details(conn, p["block"]) if i < detail_top else {"subjects": [], "states": 0,
                                                                    "first_day": None, "last_day": None})
    if pools:
        rows(conn, """UNWIND $p AS p MATCH (b:Block {npa_nxx: p.block})
                      CREATE (c:FtcCampaign {id: p.id, kind: 'pool', numbers: p.numbers, reports: p.reports,
                              toll_free: p.toll_free, subjects: p.subjects, states: p.states,
                              first_day: p.first_day, last_day: p.last_day})-[:USES_BLOCK]->(b)""", {"p": pools})
    reps = rows(conn, """MATCH (n:Number) WHERE n.reports >= $k
                         CREATE (c:FtcCampaign {id: 'NUM-' + n.number, kind: 'repeat', numbers: 1,
                                 reports: n.reports, toll_free: n.toll_free})-[:USES_NUMBER]->(n)
                         RETURN count(c) AS n""", {"k": repeat_min})[0]["n"]
    return len(pools) + reps


def spoofing_profile(conn: relate.Connection) -> list[dict]:
    out = rows(conn, """
        MATCH (r:Report)-[:ABOUT]->(s:Subject)
        RETURN s.code AS subject, count(r) AS reports,
               sum(CASE WHEN r.neighbor THEN 1 ELSE 0 END) AS neighbor
        ORDER BY reports DESC""")
    for o in out:
        o["label"] = SUBJECT_LABEL.get(o["subject"], o["subject"])
        o["neighbor_share"] = round(o["neighbor"] / o["reports"], 3) if o["reports"] else 0.0
    return out


def assess_number(conn: relate.Connection, number: str) -> dict:
    """Evidence about one reported number — and how careful to be with it."""
    from .parse import _number
    d = _number(number)
    if not d:
        raise ValueError("Enter a valid 10-digit North American number (optionally prefixed by 1).")
    r = rows(conn, """
        MATCH (n:Number {number: $n})-[:IN_BLOCK]->(b:Block)
        OPTIONAL MATCH (n)<-[:FROM_NUMBER]-(rep:Report)
        OPTIONAL MATCH (rep)-[:ABOUT]->(s:Subject)
        OPTIONAL MATCH (rep)-[:VICTIM_IN]->(st:State)
        RETURN n.reports AS reports, n.first_day AS first, n.last_day AS last, n.toll_free AS toll_free,
               b.npa_nxx AS block, count(DISTINCT st) AS states, collect(DISTINCT s.code) AS subjects,
               sum(CASE WHEN rep.neighbor THEN 1 ELSE 0 END) AS neighbor""", {"n": d})
    if not r or r[0]["reports"] is None:
        # The number may be absent while its prefix has a concentration of other reports.
        block = d[:6]
        range_rows = rows(conn, """
            MATCH (:Block {npa_nxx: $b})<-[:IN_BLOCK]-(n:Number)<-[:FROM_NUMBER]-(rep:Report)
            WHERE rep.neighbor = false RETURN count(DISTINCT n) AS nums""", {"b": block})
        count = range_rows[0]["nums"] if range_rows else 0
        return {"number": d, "verdict": "unknown", "advice": ADVICE["unknown"], "reports": 0,
                "block": block, "block_numbers": count, "in_pool_range": count >= POOL_MIN_NUMBERS,
                "caution": CAUTION}
    a = r[0]
    pool = rows(conn, """
        MATCH (b:Block {npa_nxx: $b})<-[:IN_BLOCK]-(n:Number)<-[:FROM_NUMBER]-(rep:Report)
        WHERE rep.neighbor = false RETURN count(DISTINCT n) AS nums""", {"b": a["block"]})[0]["nums"]
    neighbor_share = a["neighbor"] / a["reports"] if a["reports"] else 0
    if a["reports"] <= 2 and neighbor_share == 1:
        verdict = "likely_spoofed"
    elif pool >= POOL_MIN_NUMBERS:
        verdict = "pool"
    elif a["reports"] >= 3:
        verdict = "repeat"
    else:
        verdict = "single"
    return {"number": d, "verdict": verdict, "advice": ADVICE[verdict], "reports": a["reports"], "first_day": a["first"],
            "last_day": a["last"], "states": a["states"], "subjects": a["subjects"],
            "neighbor_share": round(neighbor_share, 3), "block": a["block"], "block_numbers": pool,
            "toll_free": a["toll_free"], "caution": CAUTION}
