"""Independent check: do the FCC's own consumer complaints (a different agency, a different intake) point at the
same number ranges as the pools Dropnet found in FTC reports? Compared against random reported blocks."""
from __future__ import annotations

import gzip
import json
import random
import re
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import relate

from ..store import rows
from .campaigns import pool_campaigns

FCC_URL = "https://opendata.fcc.gov/resource/3xyp-aqkj.json"


def fetch_fcc(start: str, end: str, out: Path, page: int = 50_000) -> list[dict]:
    """FCC consumer complaints (US public data) with a caller ID number, start <= date_created < end."""
    got, offset = [], 0
    while True:
        q = {"$select": "caller_id_number,date_created,issue,state",
             "$where": f"caller_id_number != '' AND date_created >= '{start}' AND date_created < '{end}'",
             "$limit": str(page), "$offset": str(offset), "$order": "id"}
        req = urllib.request.Request(FCC_URL + "?" + urllib.parse.urlencode(q),
                                     headers={"User-Agent": "dropnet-research/0.1", "Accept": "application/json"})
        batch = json.loads(urllib.request.urlopen(req, timeout=120).read())
        got += batch
        if len(batch) < page:
            break
        offset += page
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as f:
        json.dump(got, f)
    return got


def read_fcc(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def fcc_blocks(fcc_rows: list[dict]) -> dict[str, int]:
    c: Counter = Counter()
    for r in fcc_rows:
        d = re.sub(r"\D", "", r.get("caller_id_number") or "")
        if len(d) == 11 and d[0] == "1":
            d = d[1:]
        if len(d) == 10 and d[0] not in "01":
            c[d[:6]] += 1
    return dict(c)


def crosscheck(conn: relate.Connection, fcc: dict[str, int], top: int = 50, seeds: int = 20) -> dict:
    pools = pool_campaigns(conn, exclude_neighbor=True, limit=top)
    confirmed = [{"block": p["block"], "ftc_reports": p["reports"], "fcc_complaints": fcc[p["block"]]}
                 for p in pools if fcc.get(p["block"])]
    pool_set = {p["block"] for p in pool_campaigns(conn, exclude_neighbor=True)}
    candidates = sorted({r["b"] for r in rows(conn, """
        MATCH (r:Report)-[:FROM_NUMBER]->(:Number)-[:IN_BLOCK]->(b:Block) WHERE r.neighbor = false
        RETURN DISTINCT b.npa_nxx AS b""")} - pool_set)
    k = min(len(pools), len(candidates))
    rates = []
    for s in range(seeds):
        pick = random.Random(s).sample(candidates, k) if k else []
        rates.append(sum(1 for b in pick if fcc.get(b)) / k if k else 0.0)
    return {"pools_checked": len(pools), "pools_confirmed": len(confirmed),
            "pool_rate": round(len(confirmed) / len(pools), 3) if pools else 0.0,
            "random_rate": round(sum(rates) / len(rates), 3) if rates else 0.0,
            "random_blocks_per_draw": k, "seeds": seeds, "confirmed": confirmed}
