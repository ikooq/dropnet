"""Export a compact slice of the real FTC graph for the no-install browser demo (docs/ on GitHub Pages, Relate WASM)."""
from __future__ import annotations

import json
from pathlib import Path

from . import config, store
from .ftc import api, campaigns
from .store import rows

SITE_DATA = config.ROOT / "docs" / "data" / "graph.json"


LOOKUP = config.ROOT / "docs" / "data" / "lookup.txt"
CODES = {"likely_spoofed": "s", "pool": "p", "repeat": "r", "single": "1"}


def export_lookup(ftc_store: Path | str = config.DATA_DIR / "ftc.rl", out: Path | str = LOOKUP) -> dict:
    """Every reported number and every pool block, as a compact text file the browser demo fetches on demand.

    Same verdict rule as campaigns.assess_number:  B <block> <numbers> <reports>  |  <number> <reports> <s|p|r|1>
    """
    conn = store.open_store(ftc_store, read_only=True)
    try:
        pools = {r["b"]: r for r in rows(conn, """
            MATCH (c:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(b:Block)
            RETURN b.npa_nxx AS b, c.numbers AS numbers, c.reports AS reports""")}
        nums = rows(conn, """MATCH (r:Report)-[:FROM_NUMBER]->(n:Number)
                             RETURN n.number AS n, count(r) AS c, sum(CASE WHEN r.neighbor THEN 1 ELSE 0 END) AS nb""")
        span = rows(conn, "MATCH (r:Report) RETURN min(r.day) AS a, max(r.day) AS b")[0]
    finally:
        conn.close()
    lines = [f"# dropnet lookup v1 {span['a']} {span['b']} — FTC Do Not Call reports (US public data)"]
    lines += [f"B {b} {p['numbers']} {p['reports']}" for b, p in sorted(pools.items())]
    counts = {}
    for x in sorted(nums, key=lambda x: x["n"]):
        if x["c"] <= 2 and x["nb"] == x["c"]:
            v = "likely_spoofed"
        elif x["n"][:6] in pools:
            v = "pool"
        elif x["c"] >= 3:
            v = "repeat"
        else:
            v = "single"
        counts[v] = counts.get(v, 0) + 1
        lines.append(f"{x['n']} {x['c']} {CODES[v]}")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"pool_blocks": len(pools), "numbers": len(nums), "verdicts": counts, "bytes": out.stat().st_size}


def export(ftc_store: Path | str = config.DATA_DIR / "ftc.rl", out: Path | str = SITE_DATA,
           eval_path: Path | str = config.DATA_DIR / "ftc" / "eval.json", top: int = 200, per_pool: int = 40) -> dict:
    conn = store.open_store(ftc_store, read_only=True)
    try:
        pools = api.campaign_list(conn, top, "pool")
        for p in pools:
            p["block"] = p["id"].replace("POOL-", "")
            nums = rows(conn, """
                MATCH (:FtcCampaign {id: $id})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(n:Number)<-[:FROM_NUMBER]-(r:Report)
                WITH n, count(r) AS reps, sum(CASE WHEN r.neighbor THEN 1 ELSE 0 END) AS nb
                RETURN n.number AS number, n.reports AS reports,
                       CASE WHEN reps <= 2 AND nb = reps THEN 'likely_spoofed' ELSE 'pool' END AS verdict
                ORDER BY reports DESC, number LIMIT $k""", {"id": p["id"], "k": per_pool})
            keep = {n["number"] for n in nums}
            st = rows(conn, """
                MATCH (:FtcCampaign {id: $id})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(n:Number)<-[:FROM_NUMBER]-(r:Report)
                OPTIONAL MATCH (r)-[:VICTIM_IN]->(s:State)
                RETURN n.number AS number, s.name AS state, count(r) AS c""", {"id": p["id"]})
            sb = rows(conn, """
                MATCH (:FtcCampaign {id: $id})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(n:Number)<-[:FROM_NUMBER]-(r:Report)
                MATCH (r)-[:ABOUT]->(s:Subject)
                RETURN n.number AS number, s.code AS subject, count(r) AS c""", {"id": p["id"]})
            for n in nums:
                n["states"] = {x["state"]: x["c"] for x in st if x["number"] == n["number"] and x["state"]}
                n["subjects"] = {x["subject"]: x["c"] for x in sb if x["number"] == n["number"]}
            p["nums"] = [n for n in nums if n["number"] in keep]  # p["numbers"] stays the pool's total count
        data = {"summary": api.summary(conn), "profile": campaigns.spoofing_profile(conn), "states": api.states(conn),
                "pools": pools, "networks": api.networks(conn),
                "eval": json.loads(Path(eval_path).read_text(encoding="utf-8")) if Path(eval_path).exists() else None,
                "source": "FTC Do Not Call complaint data (US public data)", "caution": campaigns.CAUTION}
    finally:
        conn.close()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return json.loads(out.read_text(encoding="utf-8"))
