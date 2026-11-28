"""Who holds the numbers: NANPA numbering data joined to the FTC graph.

Two public NANPA files (https://nanpa.com/reports) say who a range was given to:

* CO code assignments: each six-digit range (NPA-NXX) -> code holder (OCN, company) and rate center.
* Thousands-block assignments: in pooled ranges, each block of 1,000 numbers (NPA-NXX-X) -> the carrier it went to.

Added to the graph:

(:Block)-[:HELD_BY]->(:Carrier {ocn})-[:PART_OF]->(:CarrierGroup {name})
(:Block)-[:IN_RATE_CENTER]->(:RateCenter {id})
(:Number)-[:IN_SUBBLOCK]->(:SubBlock {id: npa_nxx_x})-[:PART_OF]->(:Block)
(:SubBlock)-[:ASSIGNED_TO]->(:Carrier)          # only for thousands-blocks assigned to a carrier

Limits, said with every answer: this is the carrier a range or block was assigned to, from NANPA's current files.
A number can be ported to another carrier, and caller ID can be faked, so a holder is where a number was issued,
not who made a call. Toll-free numbers are not assigned in ranges and have no holder here.
"""
from __future__ import annotations

import csv
import gzip
import io
import re
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

import relate

from .. import config
from ..store import rows

NANPA_DIR = config.DATA_DIR / "nanpa"
CODES_URL = "https://reports.nanpa.com/public/CoCodeAssignment_Utilized_AllStates_Public.zip"
BLOCKS_URL = "https://reports.nanpa.com/public/ThousandsBlockAssignment_All.zip"
CODES_CSV = "codes.csv.gz"
SUBBLOCKS_CSV = "subblocks.csv.gz"
HOLDINGS_CSV = "holdings.csv.gz"

CAUTION = ("Holder = the carrier NANPA lists for the range or 1,000-number block today. Numbers can be ported and "
           "caller ID can be faked: a holder is where a number was issued, not who placed a call or proof of "
           "wrongdoing. Carriers that resell numbers serve many unrelated customers.")

_SUFFIX = re.compile(r"\s*-\s*[A-Z]{2}$")


def group_name(company: str) -> str:
    """'ONVOY, LLC - CA' -> 'ONVOY, LLC': NANPA lists one OCN per state for some carriers."""
    return _SUFFIX.sub("", company.strip()).strip()


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "dropnet-research/0.1"})
    with urllib.request.urlopen(req, timeout=300) as r:
        dest.write_bytes(r.read())
    return dest


def _codes(zip_path: Path) -> dict[str, dict]:
    with zipfile.ZipFile(zip_path) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    out = {}
    for line in text.splitlines()[1:]:
        f = [x.strip().strip('"').strip() for x in line.split("\t")]
        if len(f) < 11 or not re.fullmatch(r"\d{3}-\d{3}", f[1]):
            continue
        out[f[1].replace("-", "")] = {"block": f[1].replace("-", ""), "state": f[0], "ocn": f[2], "company": f[3],
                                      "rate_center": f[4], "pooled": f[9] == "Y"}
    return out


def _subblocks(zip_path: Path):
    with zipfile.ZipFile(zip_path) as z:
        with z.open(z.namelist()[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="latin-1"))
            next(reader)
            for row in reader:
                if len(row) >= 12:
                    yield {"block": row[0] + row[1], "x": row[2], "status": row[3].strip(),
                           "company": row[10].strip(), "ocn": row[11].strip(), "rate_center": row[7].strip()}


def _write(path: Path, fields: list[str], items) -> int:
    n = 0
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for it in items:
            w.writerow(it)
            n += 1
    return n


def extract(codes_zip: Path, blocks_zip: Path, blocks: set[str], subblocks: set[str], out_dir: Path = NANPA_DIR) -> dict:
    """Keep only what the graph needs: ranges with reports and the 1,000-blocks that hold reported numbers.

    Holdings (codes per carrier across the whole NANP) are kept for every carrier, so counts can be normalised.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    codes = _codes(codes_zip)
    held = Counter((c["ocn"], c["company"]) for c in codes.values())
    n_codes = _write(out_dir / CODES_CSV, ["block", "state", "ocn", "company", "rate_center", "pooled"],
                     (codes[b] for b in sorted(blocks) if b in codes))
    n_sub = _write(out_dir / SUBBLOCKS_CSV, ["block", "x", "status", "ocn", "company"],
                   (s for s in _subblocks(blocks_zip) if s["block"] + s["x"] in subblocks))
    n_hold = _write(out_dir / HOLDINGS_CSV, ["ocn", "company", "codes"],
                    ({"ocn": o, "company": c, "codes": k} for (o, c), k in sorted(held.items())))
    return {"codes": n_codes, "subblocks": n_sub, "carriers": n_hold}


def _read(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _chunks(xs: list, n: int = 5_000):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def link(conn: relate.Connection, nanpa_dir: Path = NANPA_DIR) -> dict:
    """Write carriers, rate centers and 1,000-number blocks into the graph (idempotent)."""
    nanpa_dir = Path(nanpa_dir)
    codes, subs, holds = (_read(nanpa_dir / CODES_CSV), _read(nanpa_dir / SUBBLOCKS_CSV),
                          _read(nanpa_dir / HOLDINGS_CSV))
    for label, prop in (("Carrier", "ocn"), ("CarrierGroup", "name"), ("RateCenter", "id"), ("SubBlock", "id")):
        rows(conn, f"CREATE INDEX {label.lower()}_{prop}_idx IF NOT EXISTS FOR (n:{label}) ON (n.{prop})")
    for q in ("MATCH (s:SubBlock) DETACH DELETE s", "MATCH (c:Carrier) DETACH DELETE c",
              "MATCH (g:CarrierGroup) DETACH DELETE g", "MATCH (r:RateCenter) DETACH DELETE r"):
        rows(conn, q)
    carriers: dict[str, dict] = {}
    for h in holds:
        if not h["ocn"]:
            continue
        carriers[h["ocn"]] = {"ocn": h["ocn"], "name": h["company"], "group": group_name(h["company"]),
                              "codes_held": int(h["codes"])}
    for s in subs:  # a block can go to a carrier that holds no whole range
        if s["ocn"] and s["ocn"] not in carriers:
            carriers[s["ocn"]] = {"ocn": s["ocn"], "name": s["company"], "group": group_name(s["company"]),
                                  "codes_held": 0}
    groups = Counter()
    for c in carriers.values():
        groups[c["group"]] += c["codes_held"]
    rows(conn, "UNWIND $g AS g CREATE (:CarrierGroup {name: g.name, codes_held: g.codes})",
         {"g": [{"name": k, "codes": v} for k, v in groups.items()]})
    for part in _chunks(list(carriers.values())):
        rows(conn, """UNWIND $c AS c MATCH (g:CarrierGroup {name: c.group})
                      CREATE (x:Carrier {ocn: c.ocn, name: c.name, codes_held: c.codes_held})-[:PART_OF]->(g)""",
             {"c": part})
    centers = {(c["state"], c["rate_center"]) for c in codes if c["rate_center"]}
    rows(conn, "UNWIND $r AS r CREATE (:RateCenter {id: r.id, name: r.name, state: r.state})",
         {"r": [{"id": f"{s}:{n}", "name": n, "state": s} for s, n in sorted(centers)]})
    for part in _chunks(codes):
        rows(conn, """UNWIND $c AS c MATCH (b:Block {npa_nxx: c.block})
                      SET b.pooled = c.pooled = 'True', b.state = c.state
                      WITH b, c WHERE c.ocn <> ''
                      MATCH (x:Carrier {ocn: c.ocn})
                      CREATE (b)-[:HELD_BY]->(x)""", {"c": part})
        rows(conn, """UNWIND $c AS c MATCH (b:Block {npa_nxx: c.block}), (r:RateCenter {id: c.state + ':' + c.rc})
                      CREATE (b)-[:IN_RATE_CENTER]->(r)""",
             {"c": [{"block": c["block"], "state": c["state"], "rc": c["rate_center"]} for c in part
                    if c["rate_center"]]})
    sub_rows = [{"id": s["block"] + s["x"], "block": s["block"], "x": s["x"], "status": s["status"],
                 "ocn": s["ocn"] if s["status"] == "AS" else ""} for s in subs]
    for part in _chunks(sub_rows):
        rows(conn, """UNWIND $s AS s MATCH (b:Block {npa_nxx: s.block})
                      CREATE (x:SubBlock {id: s.id, status: s.status})-[:PART_OF]->(b)""", {"s": part})
        rows(conn, """UNWIND $s AS s MATCH (x:SubBlock {id: s.id}), (c:Carrier {ocn: s.ocn})
                      CREATE (x)-[:ASSIGNED_TO]->(c)""", {"s": [s for s in part if s["ocn"]]})
    nums = [r["n"] for r in rows(conn, "MATCH (n:Number) WHERE n.toll_free = false RETURN n.number AS n")]
    for part in _chunks(nums, 10_000):
        rows(conn, """UNWIND $n AS num MATCH (n:Number {number: num}), (s:SubBlock {id: substring(num, 0, 7)})
                      CREATE (n)-[:IN_SUBBLOCK]->(s)""", {"n": part})
    return {"carriers": len(carriers), "groups": len(groups), "rate_centers": len(centers), "codes": len(codes),
            "subblocks": len(sub_rows),
            "numbers_in_subblocks": rows(conn, "MATCH (:Number)-[r:IN_SUBBLOCK]->() RETURN count(r) AS n")[0]["n"]}


def has_numbering(conn: relate.Connection) -> bool:
    return bool(rows(conn, "MATCH (c:Carrier) RETURN c.ocn AS o LIMIT 1"))


def range_network(conn: relate.Connection, block: str, limit: int = 6) -> dict | None:
    assignment = rows(conn, """
        MATCH (b:Block {npa_nxx: $block})
        OPTIONAL MATCH (b)-[:HELD_BY]->(c:Carrier)
        OPTIONAL MATCH (b)-[:IN_RATE_CENTER]->(rc:RateCenter)
        RETURN c.ocn AS ocn, c.name AS holder, rc.id AS rate_center_id, rc.name AS rate_center
    """, {"block": block})
    if not assignment or not (assignment[0]["ocn"] or assignment[0]["rate_center_id"]):
        return None
    result = assignment[0]
    # Start from the ~4.7k flagged ranges, not from every range the OCN holds: a large holder has thousands, and
    # walking them took 5 s for OCN 965H; this order returns the same rows in milliseconds.
    result["related"] = rows(conn, """
        MATCH (p:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(b:Block)-[:HELD_BY]->(:Carrier {ocn: $ocn})
        WHERE b.npa_nxx <> $block
        RETURN b.npa_nxx AS block, p.id AS campaign, p.reports AS reports
        ORDER BY reports DESC, block LIMIT $limit
    """, {"block": block, "ocn": result["ocn"], "limit": limit}) if result["ocn"] else []
    return result


# ---------------------------------------------------------------- questions that need the graph

def carrier_ranking(conn: relate.Connection, limit: int = 25) -> list[dict]:
    """Carrier groups by flagged geographic ranges they hold, normalised by how many ranges they hold in total.

    Path: (FtcCampaign)-[:USES_BLOCK]->(Block)-[:HELD_BY]->(Carrier)-[:PART_OF]->(CarrierGroup)
    """
    out = rows(conn, """
        MATCH (p:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(b:Block)-[:HELD_BY]->(c:Carrier)-[:PART_OF]->(g:CarrierGroup)
        WITH g, count(DISTINCT b) AS flagged, sum(p.reports) AS reports, sum(p.numbers) AS numbers,
             count(DISTINCT c) AS ocns, collect(DISTINCT b.state) AS states
        RETURN g.name AS carrier, g.codes_held AS ranges_held, flagged, reports, numbers, ocns, size(states) AS states
        ORDER BY flagged DESC, reports DESC LIMIT $k""", {"k": int(limit)})
    for o in out:
        o["flagged_per_100_ranges"] = round(100 * o["flagged"] / o["ranges_held"], 1) if o["ranges_held"] else None
    return out


def carrier_detail(conn: relate.Connection, carrier: str, limit: int = 40) -> dict:
    """One carrier group: its flagged ranges, where they sit, what the complaints were about."""
    ranges = rows(conn, """
        MATCH (g:CarrierGroup {name: $g})<-[:PART_OF]-(c:Carrier)<-[:HELD_BY]-(b:Block)<-[:USES_BLOCK]-(p:FtcCampaign)
        OPTIONAL MATCH (b)-[:IN_RATE_CENTER]->(rc:RateCenter)
        RETURN b.npa_nxx AS block, p.reports AS reports, p.numbers AS numbers, p.subjects AS subjects,
               c.ocn AS ocn, rc.name AS rate_center, b.state AS state
        ORDER BY reports DESC LIMIT $k""", {"g": carrier, "k": int(limit)})
    # Complaint categories of the listed ranges' reports (bounded by `limit`, so large carriers stay fast).
    # Anchored on the indexed carrier group: an UNWIND-bound Block lookup skips the index and takes ~90 s.
    subjects = rows(conn, """
        MATCH (:CarrierGroup {name: $g})<-[:PART_OF]-(:Carrier)<-[:HELD_BY]-(b:Block) WHERE b.npa_nxx IN $blocks
        MATCH (b)<-[:IN_BLOCK]-(:Number)<-[:FROM_NUMBER]-(r:Report) WHERE r.neighbor = false
        MATCH (r)-[:ABOUT]->(s:Subject)
        RETURN s.code AS subject, count(r) AS reports ORDER BY reports DESC LIMIT 5""",
                    {"g": carrier, "blocks": [r["block"] for r in ranges]})
    return {"carrier": carrier, "ranges": ranges, "subjects": subjects, "caution": CAUTION}


def pooled_reassignment(conn: relate.Connection, limit: int = 15) -> list[dict]:
    """In pooled ranges the code holder is not the whole story: which carriers got the 1,000-blocks that hold the
    reported numbers of flagged ranges? Five hops: campaign -> range -> number -> 1,000-block -> carrier -> group."""
    return rows(conn, """
        MATCH (p:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(b:Block)<-[:IN_BLOCK]-(n:Number)
              -[:IN_SUBBLOCK]->(:SubBlock)-[:ASSIGNED_TO]->(:Carrier)-[:PART_OF]->(g:CarrierGroup)
        MATCH (b)-[:HELD_BY]->(:Carrier)-[:PART_OF]->(h:CarrierGroup)
        RETURN g.name AS block_carrier, count(DISTINCT n) AS reported_numbers, count(DISTINCT b) AS flagged_ranges,
               count(DISTINCT CASE WHEN g <> h THEN n END) AS numbers_not_with_range_holder
        ORDER BY reported_numbers DESC LIMIT $k""", {"k": int(limit)})


def number_holder(conn: relate.Connection, number: str) -> dict | None:
    """Range holder, 1,000-block carrier and rate center for one number (reported or not)."""
    block, sub = number[:6], number[:7]
    r = rows(conn, """
        MATCH (b:Block {npa_nxx: $b})-[:HELD_BY]->(c:Carrier)-[:PART_OF]->(g:CarrierGroup)
        OPTIONAL MATCH (b)-[:IN_RATE_CENTER]->(rc:RateCenter)
        OPTIONAL MATCH (s:SubBlock {id: $s})-[:ASSIGNED_TO]->(sc:Carrier)-[:PART_OF]->(sg:CarrierGroup)
        OPTIONAL MATCH (g)<-[:PART_OF]-(:Carrier)<-[:HELD_BY]-(fb:Block)<-[:USES_BLOCK]-(:FtcCampaign {kind: 'pool'})
        RETURN c.ocn AS ocn, g.name AS range_holder, rc.name AS rate_center, rc.state AS state,
               sg.name AS block_carrier, sc.ocn AS block_ocn,
               g.codes_held AS holder_ranges, count(DISTINCT fb) AS holder_flagged""",
             {"b": block, "s": sub})
    if not r:
        return None
    x = r[0]
    block_ocn = x.pop("block_ocn")
    x["prefix_holder"] = {"name": x["range_holder"], "prefix": block, "ocn": x["ocn"],
                          "rate_center": x["rate_center"], "state": x["state"],
                          "ranges_held": x["holder_ranges"], "flagged_ranges_held": x["holder_flagged"]}
    x["thousands_block_assignee"] = ({"name": x["block_carrier"], "block": sub, "ocn": block_ocn}
                                     if x["block_carrier"] else None)
    x["carrier"] = x["block_carrier"] or x["range_holder"]
    x["caution"] = CAUTION
    return x


def carrier_prior(conn: relate.Connection, split_day: str, top: int = 10, min_held: int = 100) -> dict:
    """Does the range holder say anything about ranges that are not flagged yet?

    Learn, from complaints before `split_day` only, each carrier group's flagged ranges per range it holds. Take the
    `top` groups (holding >= `min_held` ranges). Among geographic ranges that had a report before the split but were
    not flagged, compare how often those held by the top groups become flagged once later complaints are added.
    The holders come from today's NANPA files; assignments do not depend on complaints, but a few may have changed.
    """
    from .campaigns import pool_campaigns
    from .parse import TOLL_FREE

    def geo(ps):
        return {p["block"] for p in ps if p["block"][:3] not in TOLL_FREE}

    before = geo(pool_campaigns(conn, until_day=split_day))
    after = geo(pool_campaigns(conn)) - before
    holder = {r["b"]: (r["g"], r["held"]) for r in rows(conn, """
        MATCH (b:Block)-[:HELD_BY]->(:Carrier)-[:PART_OF]->(g:CarrierGroup)
        RETURN b.npa_nxx AS b, g.name AS g, g.codes_held AS held""")}
    flagged = Counter(holder[b][0] for b in before if b in holder)
    held = {g: h for g, h in holder.values()}
    rate = {g: flagged[g] / held[g] for g in flagged if held[g] >= min_held}
    leaders = [g for g, _ in sorted(rate.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]
    seen = {r["b"] for r in rows(conn, """
        MATCH (r:Report)-[:FROM_NUMBER]->(:Number)-[:IN_BLOCK]->(b:Block) WHERE r.day < $s
        RETURN DISTINCT b.npa_nxx AS b""", {"s": split_day})}
    open_ = [b for b in seen if b in holder and b not in before and b[:3] not in TOLL_FREE]
    lead = [b for b in open_ if holder[b][0] in leaders]
    rest = [b for b in open_ if holder[b][0] not in leaders]

    def later(xs):
        return round(sum(b in after for b in xs) / len(xs), 4) if xs else None

    return {"split_day": split_day, "leaders": [{"carrier": g, "flagged_per_100_ranges": round(100 * rate[g], 1)}
                                                for g in leaders],
            "open_ranges": len(open_), "leader_ranges": len(lead), "other_ranges": len(rest),
            "leader_flagged_later": later(lead), "other_flagged_later": later(rest),
            "lift": round(later(lead) / later(rest), 1) if later(rest) else None,
            "new_flagged_ranges": len(after),
            "new_flagged_held_by_leaders": sum(1 for b in after if b in holder and holder[b][0] in leaders)}
