"""Read-only views over the FTC graph for the web UI and MCP."""
from __future__ import annotations

import relate

from ..store import rows
from ..tools import jsonable
from .parse import SUBJECT_LABEL


def summary(conn: relate.Connection) -> dict:
    r = rows(conn, """MATCH (r:Report) RETURN count(r) AS reports, min(r.day) AS first, max(r.day) AS last,
                      sum(CASE WHEN r.neighbor THEN 1 ELSE 0 END) AS neighbor,
                      sum(CASE WHEN r.robocall THEN 1 ELSE 0 END) AS robocall""")[0]
    n = rows(conn, """MATCH (n:Number) RETURN count(n) AS numbers,
                      sum(CASE WHEN n.reports = 1 THEN 1 ELSE 0 END) AS single""")[0]
    b = rows(conn, "MATCH (b:Block) RETURN count(b) AS blocks")[0]
    k = rows(conn, "MATCH (c:FtcCampaign) RETURN c.kind AS kind, count(c) AS n")
    return {"reports": r["reports"], "numbers": n["numbers"], "blocks": b["blocks"], "first_day": r["first"],
            "last_day": r["last"], "neighbor_share": round(r["neighbor"] / max(1, r["reports"]), 3),
            "robocall_share": round(r["robocall"] / max(1, r["reports"]), 3),
            "single_report_numbers_share": round(n["single"] / max(1, n["numbers"]), 3),
            "campaigns": {x["kind"]: x["n"] for x in k}}


def campaign_list(conn: relate.Connection, limit: int = 60, kind: str | None = None) -> list[dict]:
    return [jsonable(dict(r["c"].items())) for r in rows(conn, """
        MATCH (c:FtcCampaign) WHERE $k IS NULL OR c.kind = $k
        RETURN c ORDER BY c.reports DESC, c.id LIMIT $lim""", {"k": kind, "lim": int(limit)})]


def campaign_graph(conn: relate.Connection, campaign_id: str, max_numbers: int = 60) -> dict | None:
    camp = rows(conn, "MATCH (c:FtcCampaign {id: $id}) RETURN c", {"id": campaign_id})
    if not camp:
        return None
    nums = rows(conn, """
        MATCH (c:FtcCampaign {id: $id})-[:USES_BLOCK|USES_NUMBER]->(t)
        OPTIONAL MATCH (t)<-[:IN_BLOCK]-(bn:Number)
        WITH collect(DISTINCT CASE WHEN t:Number THEN t ELSE bn END) AS nums
        UNWIND nums AS n
        MATCH (n)-[:IN_BLOCK]->(b:Block)
        RETURN n.number AS number, n.reports AS reports, b.npa_nxx AS block
        ORDER BY reports DESC LIMIT $lim""", {"id": campaign_id, "lim": int(max_numbers)})
    keep_nums = {x["number"] for x in nums}
    # Anchor on the campaign (indexed) — an UNWIND-bound `{number: num}` lookup skips the index in Relate 1.0.1.
    anchor = """MATCH (c:FtcCampaign {id: $id})-[:USES_BLOCK|USES_NUMBER]->(t)
                OPTIONAL MATCH (t)<-[:IN_BLOCK]-(bn:Number)
                WITH CASE WHEN t:Number THEN t ELSE bn END AS n WHERE n IS NOT NULL
                MATCH (n)<-[:FROM_NUMBER]-(r:Report)"""
    states = [s for s in rows(conn, anchor + """ MATCH (r)-[:VICTIM_IN]->(s:State)
              RETURN n.number AS num, s.name AS state, count(r) AS n""", {"id": campaign_id}) if s["num"] in keep_nums]
    subjects = [s for s in rows(conn, anchor + """ MATCH (r)-[:ABOUT]->(s:Subject)
                RETURN n.number AS num, s.code AS subject, count(r) AS n""", {"id": campaign_id})
                if s["num"] in keep_nums]
    nodes, edges = {}, []

    def node(i, kind, label, **kw):
        nodes.setdefault(i, {"id": i, "kind": kind, "label": label, **kw})

    for x in nums:
        node(f"B:{x['block']}", "Block", f"{x['block'][:3]}-{x['block'][3:]}")
        node(f"N:{x['number']}", "Number", x["number"][-4:], reports=x["reports"], number=x["number"])
        edges.append({"source": f"N:{x['number']}", "target": f"B:{x['block']}", "type": "IN_BLOCK"})
    by_state: dict[str, int] = {}
    for s in states:
        by_state[s["state"]] = by_state.get(s["state"], 0) + s["n"]
    keep = {k for k, _ in sorted(by_state.items(), key=lambda kv: -kv[1])[:12]}
    for s in states:
        if s["state"] in keep:
            node(f"S:{s['state']}", "State", s["state"], reports=by_state[s["state"]])
            edges.append({"source": f"N:{s['num']}", "target": f"S:{s['state']}", "type": "CALLED_INTO", "n": s["n"]})
    for s in subjects:
        node(f"T:{s['subject']}", "Subject", SUBJECT_LABEL.get(s["subject"], s["subject"]))
        edges.append({"source": f"N:{s['num']}", "target": f"T:{s['subject']}", "type": "ABOUT", "n": s["n"]})
    return {"campaign": jsonable(dict(camp[0]["c"].items())), "nodes": list(nodes.values()), "edges": edges,
            "states_total": len(by_state)}


def networks(conn: relate.Connection) -> list[dict]:
    """Pool networks: ranges that hit the same victim area codes, on the same days, with the same scam."""
    out = []
    for n in rows(conn, "MATCH (n:PoolNetwork) RETURN n.id AS id, n.pools AS pools, n.reports AS reports, "
                        "n.numbers AS numbers ORDER BY reports DESC"):
        n["members"] = rows(conn, """MATCH (c:FtcCampaign)-[:IN_NETWORK]->(:PoolNetwork {id: $id})
                                     RETURN c.id AS id, c.reports AS reports, c.numbers AS numbers, c.subjects AS subjects
                                     ORDER BY reports DESC""", {"id": n["id"]})
        n["links"] = rows(conn, """MATCH (a:FtcCampaign)-[:IN_NETWORK]->(:PoolNetwork {id: $id})
                                   MATCH (a)-[s:SIBLING]->(b:FtcCampaign)
                                   RETURN a.id AS a, b.id AS b, s.shared AS shared ORDER BY shared DESC""", {"id": n["id"]})
        out.append(n)
    return out


def search_pools(conn: relate.Connection, text: str, limit: int = 20) -> dict:
    """Full-text search (Relate FULLTEXT index on Subject.label) then graph hops to the pools behind those scams."""
    text = (text or "").strip()
    if not text:
        return {"subjects": [], "pools": []}
    subjects = rows(conn, """CALL db.index.fulltext.queryNodes('subject_label_ft', $q) YIELD node, score
                             RETURN node.code AS code, node.label AS label, score ORDER BY score DESC LIMIT 5""",
                    {"q": text})
    codes = [s["code"] for s in subjects]
    pools = rows(conn, """MATCH (c:FtcCampaign {kind: 'pool'}) WHERE any(s IN c.subjects WHERE s IN $codes)
                          RETURN c.id AS id, c.reports AS reports, c.numbers AS numbers, c.subjects AS subjects
                          ORDER BY reports DESC LIMIT $lim""", {"codes": codes, "lim": int(limit)}) if codes else []
    return {"subjects": subjects, "pools": pools}


FTC_TOOL_NAMES = ["ftc_summary", "ftc_campaigns", "assess_number", "whatif_block"]


def dispatch_ftc(conn: relate.Connection, name: str, args: dict):
    from . import campaigns, whatif
    if name == "ftc_summary":
        return {**summary(conn), "profile": campaigns.spoofing_profile(conn)}
    if name == "ftc_campaigns":
        return campaign_list(conn, int(args.get("limit", 20)), args.get("kind"))
    if name == "assess_number":
        return campaigns.assess_number(conn, args["number"])
    if name == "whatif_block":
        return whatif.whatif(conn, blocks=args.get("blocks"), numbers=args.get("numbers"),
                             since_day=args.get("since_day"))
    raise LookupError(name)


def states(conn: relate.Connection) -> list[dict]:
    out = rows(conn, """
        MATCH (r:Report)-[:VICTIM_IN]->(s:State)
        RETURN s.name AS state, count(r) AS reports, sum(CASE WHEN r.neighbor THEN 1 ELSE 0 END) AS neighbor
        ORDER BY reports DESC""")
    for o in out:
        o["neighbor_share"] = round(o["neighbor"] / o["reports"], 3) if o["reports"] else 0.0
    return out
