"""Add one new complaint to a live store and tell the analyst, immediately, what it connects to."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date

import relate

from . import load, tools
from .config import MAX_FORWARD_HOPS, SIMILARITY_K, SIMILARITY_THRESHOLD, TACTICS, VECTOR_INDEX
from .extract import rules
from .link import _summarize
from .models import Complaint
from .store import rows
from .synth.templates import CHANNEL

MAX_TEXT = 20_000


@dataclass
class IngestResult:
    complaint_id: str
    status: str                      # attached | bridge | new_campaign | unlinked
    campaign_id: str | None = None
    bridge_to: list[str] = field(default_factory=list)
    via: str | None = None           # identifier | script
    evidence: dict | None = None
    path_text: str | None = None
    candidates: list[dict] = field(default_factory=list)
    summary_en: str = ""
    links: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return tools.jsonable(asdict(self))


def _next_id(conn: relate.Connection) -> str:
    r = rows(conn, "MATCH (c:Complaint) RETURN max(toInteger(substring(c.id, 4))) AS m")
    return f"CMP-{(r[0]['m'] or 0) + 1:04d}"


def _summary_en(exs) -> str:
    by: dict[str, list[str]] = {}
    for e in exs:
        by.setdefault(e.kind, []).append(e.value)
    parts = []
    if "tactic" in by:
        parts.append("Tactic: " + ", ".join(TACTICS[t][1] for t in by["tactic"]))
    if "phone" in by:
        parts.append("Contacted from " + ", ".join(by["phone"]))
    if "card" in by or "iban" in by:
        parts.append("Paid to " + ", ".join(by.get("card", []) + by.get("iban", [])))
    if "url" in by:
        parts.append("Visited " + ", ".join(by["url"]))
    if "persona" in by:
        parts.append("Alias: " + ", ".join(by["persona"]))
    if "amount" in by:
        parts.append(f"Amount {max(int(a) for a in by['amount']):,} KZT")
    return " · ".join(parts) or "No identifiers found in the text."


def _strong_links(conn: relate.Connection, cid: str) -> list[dict]:
    q = {"id": cid}
    out = []
    out += rows(conn, """
        MATCH (x:Complaint {id: $id})-[:CONTACTED_BY]->(p:Phone)<-[:CONTACTED_BY]-(b:Complaint)
        WHERE coalesce(p.hub, false) = false RETURN DISTINCT b.id AS other, p.e164 AS via""", q)
    out += rows(conn, """
        MATCH (x:Complaint {id: $id})-[:VISITED]->(:Url)-[:ON_DOMAIN]->(d:Domain)<-[:ON_DOMAIN]-(:Url)<-[:VISITED]-(b)
        WHERE coalesce(d.hub, false) = false RETURN DISTINCT b.id AS other, d.name AS via""", q)
    out += rows(conn, f"""
        MATCH (x:Complaint {{id: $id}})-[:PAID_TO]->(a)-[:FORWARDED_TO*0..{MAX_FORWARD_HOPS}]->(k)
              <-[:FORWARDED_TO*0..{MAX_FORWARD_HOPS}]-(y)<-[:PAID_TO]-(b:Complaint)
        WHERE b.id <> $id AND coalesce(a.hub, false) = false AND coalesce(k.hub, false) = false
          AND coalesce(y.hub, false) = false
        RETURN DISTINCT b.id AS other, coalesce(k.pan_masked, k.iban) AS via""", q)
    out += rows(conn, """
        MATCH (x:Complaint {id: $id})-[:MENTIONS_PERSONA]->(p:Persona)<-[:MENTIONS_PERSONA]-(b:Complaint)
        WHERE coalesce(p.hub, false) = false
        MATCH (x)-[:USED_TACTIC]->(:Tactic)<-[:USED_TACTIC]-(b)
        RETURN DISTINCT b.id AS other, 'persona:' + p.name AS via""", q)
    return out


def _add_similar(conn: relate.Connection, cid: str) -> list[dict]:
    hits = rows(conn, f"""
        MATCH (x:Complaint {{id: $id}})
        CALL db.index.vector.queryNodes('{VECTOR_INDEX}', $k, x.script_vec) YIELD node, score
        WHERE node.id <> $id
        OPTIONAL MATCH (node)-[:PART_OF]->(k:Campaign)
        OPTIONAL MATCH (x)-[:USED_TACTIC]->(t:Tactic)<-[:USED_TACTIC]-(node)
        RETURN node.id AS id, score, k.id AS campaign, count(t) > 0 AS same_tactic,
               node.text_en AS text_en, node.region AS region
        ORDER BY score DESC""", {"id": cid, "k": SIMILARITY_K + 1})
    close = [h for h in hits if h["score"] >= SIMILARITY_THRESHOLD]
    if close:
        rows(conn, """UNWIND $rows AS r MATCH (a:Complaint {id: $id}), (b:Complaint {id: r.id})
                      CREATE (a)-[:SIMILAR_SCRIPT {score: r.s}]->(b)""",
             {"id": cid, "rows": [{"id": h["id"], "s": round(float(h["score"]), 4)} for h in close]})
    return hits


def _refresh_campaign(conn: relate.Connection, camp_id: str) -> None:
    members = [r["id"] for r in rows(conn, "MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $id}) RETURN c.id AS id",
                                     {"id": camp_id})]
    s = _summarize(conn, members, set())
    rows(conn, """MATCH (k:Campaign {id: $id})
                  SET k.size = $size, k.damage_kzt = $dmg, k.regions = $regions, k.first_seen = $first,
                      k.last_seen = $last, k.tactics = $tactics""",
         {"id": camp_id, "size": s.size, "dmg": s.damage_kzt, "regions": s.regions, "first": s.first_seen,
          "last": s.last_seen, "tactics": s.tactics})


def ingest_text(conn: relate.Connection, text: str, region: str | None = None, amount_kzt: int | None = None,
                filed_at: date | None = None) -> IngestResult:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty complaint")
    text = text[:MAX_TEXT]
    cid = _next_id(conn)
    exs = rules.extract(cid, text)
    amounts = [int(e.value) for e in exs if e.kind == "amount"]
    tactic = next((e.value for e in exs if e.kind == "tactic"), None)
    summary = _summary_en(exs)
    comp = Complaint(cid, filed_at or date.today(), region or "Unknown", CHANNEL.get(tactic, "unknown"),
                     int(amount_kzt if amount_kzt is not None else max(amounts, default=0)), text, summary,
                     "unknown")
    load.write_complaints(conn, [comp])
    load.write_extractions(conn, exs, {cid: comp.channel})
    hits = _add_similar(conn, cid)
    candidates = [tools.jsonable({k: h[k] for k in ("id", "campaign", "region", "text_en")}) |
                  {"score": round(float(h["score"]), 3)} for h in hits[:5]]

    links = _strong_links(conn, cid)
    camp_of = {r["c"]: r["k"] for r in rows(conn, """
        UNWIND $ids AS i MATCH (c:Complaint {id: i}) OPTIONAL MATCH (c)-[:PART_OF]->(k:Campaign)
        RETURN c.id AS c, k.id AS k""", {"ids": sorted({l["other"] for l in links})})}
    votes = Counter(camp_of[l["other"]] for l in links if camp_of.get(l["other"]))
    res = IngestResult(cid, "unlinked", summary_en=summary, candidates=candidates,
                       links=[{"other": l["other"], "via": l["via"]} for l in links])

    if votes:
        ranked = [k for k, _ in votes.most_common()]
        res.campaign_id, res.bridge_to = ranked[0], ranked[1:]
        res.status = "bridge" if res.bridge_to else "attached"
        res.via = "identifier"
        target = next(l["other"] for l in links if camp_of.get(l["other"]) == res.campaign_id)
    elif links:
        members = sorted({cid, *(l["other"] for l in links)})
        camp = _summarize(conn, members, set())
        rows(conn, """CREATE (k:Campaign {id: $id, size: 0, damage_kzt: 0, regions: [], first_seen: '',
                                          last_seen: '', confidence: 1.0, tactics: [], synthetic: true})""",
             {"id": camp.id})
        rows(conn, """UNWIND $ids AS i MATCH (c:Complaint {id: i}), (k:Campaign {id: $k}) CREATE (c)-[:PART_OF]->(k)""",
             {"ids": [m for m in members if m != cid], "k": camp.id})
        res.status, res.campaign_id, res.via = "new_campaign", camp.id, "identifier"
        target = links[0]["other"]
    else:
        script_votes = Counter(h["campaign"] for h in hits
                               if h["campaign"] and h["same_tactic"] and h["score"] >= SIMILARITY_THRESHOLD)
        if script_votes and script_votes.most_common(1)[0][1] >= 2:
            res.campaign_id = script_votes.most_common(1)[0][0]
            res.status, res.via = "attached", "script"
            target = next(h["id"] for h in hits if h["campaign"] == res.campaign_id)
        else:
            return res

    rows(conn, "MATCH (c:Complaint {id: $c}), (k:Campaign {id: $k}) CREATE (c)-[:PART_OF]->(k)",
         {"c": cid, "k": res.campaign_id})
    _refresh_campaign(conn, res.campaign_id)
    res.evidence = tools.explain_link(conn, cid, target)
    res.path_text = tools.render_path(res.evidence)
    if res.via == "script" and not res.evidence["found"]:
        score = next(h["score"] for h in hits if h["id"] == target)
        res.evidence = {"found": True, "hops": [{"label": "Complaint", "key": cid}, {"label": "Complaint", "key": target}],
                        "rels": ["SIMILAR_SCRIPT"], "forward": [True], "quotes": [], "similarity": round(float(score), 3)}
        res.path_text = tools.render_path(res.evidence)
    return res
