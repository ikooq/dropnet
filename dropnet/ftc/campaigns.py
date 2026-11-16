"""Campaigns in real FTC reports, computed with Cypher on the Relate graph.

* pool    — many different numbers from one NPA-NXX block reported for unwanted calls (a rented number range).
            Built from NON-spoofed reports only: a spoofer dials from random numbers in the victim's own area,
            and blocking those blocks would hit innocent local subscribers.
* repeat  — one number reported again and again.
* spoofing profile — how much of each scam type arrives from a number faked to look local.
"""
from __future__ import annotations

import relate

from ..store import rows
from .parse import SUBJECT_LABEL, TOLL_FREE

POOL_MIN_NUMBERS = 5
REPEAT_MIN_REPORTS = 100
CAUTION = ("Caller ID is easily faked. A number reported once, from the victim's own area code, is most likely "
           "spoofed — its real owner may be innocent. Treat this as evidence about a call, not about a person.")


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
    import re
    d = re.sub(r"\D", "", number)[-10:]
    r = rows(conn, """
        MATCH (n:Number {number: $n})-[:IN_BLOCK]->(b:Block)
        OPTIONAL MATCH (n)<-[:FROM_NUMBER]-(rep:Report)
        OPTIONAL MATCH (rep)-[:ABOUT]->(s:Subject)
        OPTIONAL MATCH (rep)-[:VICTIM_IN]->(st:State)
        RETURN n.reports AS reports, n.first_day AS first, n.last_day AS last, n.toll_free AS toll_free,
               b.npa_nxx AS block, count(DISTINCT st) AS states, collect(DISTINCT s.code) AS subjects,
               sum(CASE WHEN rep.neighbor THEN 1 ELSE 0 END) AS neighbor""", {"n": d})
    if not r or r[0]["reports"] is None:
        return {"number": d, "verdict": "unknown", "reports": 0, "caution": CAUTION}
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
    return {"number": d, "verdict": verdict, "reports": a["reports"], "first_day": a["first"], "last_day": a["last"],
            "states": a["states"], "subjects": a["subjects"], "neighbor_share": round(neighbor_share, 3),
            "block": a["block"], "block_numbers": pool, "toll_free": a["toll_free"], "caution": CAUTION}
