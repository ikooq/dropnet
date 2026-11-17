"""A carrier-ready list of number ranges: one row per pool with the evidence, the cross-check and the price."""
from __future__ import annotations

import csv
from pathlib import Path

import relate

from ..store import rows

NOTE = ("Evidence from consumer reports, not proof of wrongdoing. A block rule covers all 10,000 numbers of the range; "
        "toll-free ranges are shared by many businesses. spoofed_share is an area-code-match proxy, not verified spoofing. Legitimate-call impact is unknown. Review before blocking.")
FIELDS = ["block", "toll_free", "reported_numbers", "reports", "states", "first_day", "last_day", "subjects",
          "spoofed_share", "fcc_complaints", "network", "note"]


def export_csv(conn: relate.Connection, out: Path | str, fcc: dict[str, int] | None = None, top: int | None = None) -> int:
    fcc = fcc or {}
    pools = rows(conn, f"""MATCH (c:FtcCampaign {{kind: 'pool'}})-[:USES_BLOCK]->(b:Block)
                          RETURN c.id AS id, b.npa_nxx AS block, c.toll_free AS tf, c.numbers AS numbers,
                                 c.reports AS reports, c.states AS states, c.first_day AS first, c.last_day AS last,
                                 c.subjects AS subjects
                          ORDER BY reports DESC {'LIMIT $k' if top else ''}""", {"k": top})
    spoof = {r["id"]: (r["nb"] / r["n"] if r["n"] else 0.0) for r in rows(conn, """
        MATCH (c:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(:Number)<-[:FROM_NUMBER]-(r:Report)
        RETURN c.id AS id, count(r) AS n, sum(CASE WHEN r.neighbor THEN 1 ELSE 0 END) AS nb""")}
    net = {r["p"]: r["n"] for r in rows(conn, "MATCH (c:FtcCampaign)-[:IN_NETWORK]->(n:PoolNetwork) "
                                              "RETURN c.id AS p, n.id AS n")}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for p in pools:
            b = p["block"]
            w.writerow({"block": f"{b[:3]}-{b[3:]}", "toll_free": "yes" if p["tf"] else "no",
                        "reported_numbers": p["numbers"], "reports": p["reports"], "states": p["states"],
                        "first_day": p["first"] or "", "last_day": p["last"] or "",
                        "subjects": " ".join(p["subjects"] or []), "spoofed_share": f"{spoof.get(p['id'], 0):.3f}",
                        "fcc_complaints": fcc.get(b, 0), "network": net.get(p["id"], ""), "note": NOTE})
    return len(pools)
