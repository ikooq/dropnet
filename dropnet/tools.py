"""One read-only query layer shared by the CLI, web app, MCP server and agent.

Every function takes an open Relate connection and returns JSON-safe data.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import relate

from . import embed
from .config import VECTOR_INDEX
from .store import rows

LINK_RELS = "CONTACTED_BY|PAID_TO|FORWARDED_TO|VISITED|ON_DOMAIN|MENTIONS_PERSONA"
KEY_OF = {"Complaint": "id", "Phone": "e164", "Card": "pan_masked", "Account": "iban", "Url": "url",
          "Domain": "name", "Persona": "name", "Tactic": "code", "Region": "name", "Bank": "name",
          "Campaign": "id", "Extraction": "id"}

_WRITE = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|FOREACH|INSERT|ALTER|GRANT|REVOKE)\b",
                    re.IGNORECASE)
_CALL = re.compile(r"\bCALL\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
_ALLOWED_CALLS = {"db.index.vector.querynodes", "db.labels", "db.relationshiptypes", "db.schema.visualization",
                  "db.propertykeys"}


# ------------------------------------------------------------------- helpers
_FULL_PAN = re.compile(r"(?<![\d*])\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}(?![\d*])")


def _mask_pan(m: re.Match) -> str:
    out, digit = [], 0
    for ch in m.group(0):
        if ch.isdigit():
            out.append("*" if 6 <= digit < 12 else ch)
            digit += 1
        else:
            out.append(ch)
    return "".join(out)


def redact(text: str | None) -> str | None:
    """Mask the middle six digits of full card numbers, keeping length and separators."""
    if text is None:
        return None
    return _FULL_PAN.sub(_mask_pan, text)


def jsonable(v: Any) -> Any:
    if isinstance(v, str):
        return redact(v)
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items() if k != "script_vec"}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if hasattr(v, "values") and hasattr(v, "dimension"):  # relate.Vector
        return f"<vector dim={v.dimension}>"
    if hasattr(v, "labels") and hasattr(v, "items"):  # relate.Node
        return {"labels": list(v.labels), **{k: jsonable(x) for k, x in dict(v.items()).items() if k != "script_vec"}}
    return str(v)


def _node_ref(n: Any) -> dict:
    labels = list(getattr(n, "labels", []) or [])
    label = labels[0] if labels else "?"
    props = dict(n.items()) if hasattr(n, "items") else dict(n)
    key = props.get(KEY_OF.get(label, "id"))
    return {"label": label, "key": jsonable(key), "hub": bool(props.get("hub")), "role": props.get("role_hint")}


# --------------------------------------------------------------- read cypher
def check_read_only(statement: str) -> None:
    if _WRITE.search(statement):
        raise ValueError("read_cypher is read-only: write clauses are not allowed")
    for m in _CALL.finditer(statement):
        if m.group(1).lower() not in _ALLOWED_CALLS:
            raise ValueError(f"read_cypher: procedure {m.group(1)} is not allowed")


def read_cypher(conn: relate.Connection, statement: str, params: dict | None = None, limit: int = 200) -> dict:
    check_read_only(statement)
    cur = conn.execute(statement, params or {})
    out = cur.data()
    columns = list(out[0].keys()) if out else []
    return {"columns": columns, "rows": [jsonable(r) for r in out[:limit]], "truncated": len(out) > limit}


def get_schema(conn: relate.Connection) -> dict:
    nodes = {r["l"]: r["n"] for r in rows(conn, "MATCH (n) RETURN labels(n)[0] AS l, count(n) AS n")}
    rels = {r["t"]: r["n"] for r in rows(conn, "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n")}
    return {"nodes": nodes, "relationships": rels,
            "keys": KEY_OF, "notes": "Complaint.text is Russian; text_en is an English gloss. All data is synthetic."}


# ------------------------------------------------------------------ queries
def _campaign_props(conn, camp_id: str) -> dict | None:
    r = rows(conn, "MATCH (k:Campaign {id: $id}) RETURN k", {"id": camp_id})
    return jsonable(dict(r[0]["k"].items())) if r else None


def get_complaint(conn: relate.Connection, complaint_id: str) -> dict | None:
    r = rows(conn, """
        MATCH (c:Complaint {id: $id})
        OPTIONAL MATCH (c)-[:PART_OF]->(k:Campaign)
        OPTIONAL MATCH (c)-[:USED_TACTIC]->(t:Tactic)
        RETURN c, k.id AS campaign, collect(DISTINCT t.code) AS tactics""", {"id": complaint_id})
    if not r:
        return None
    c = jsonable(dict(r[0]["c"].items()))
    c["campaign"] = r[0]["campaign"]
    c["tactics"] = r[0]["tactics"]
    c["extractions"] = [jsonable(x) for x in rows(conn, """
        MATCH (x:Extraction)-[:FROM]->(:Complaint {id: $id})
        RETURN x.kind AS kind, x.value AS value, x.quote AS quote, x.span_start AS start, x.span_end AS end
        ORDER BY start""", {"id": complaint_id})]
    return c


def find_campaign(conn: relate.Connection, complaint_id: str) -> dict:
    comp = get_complaint(conn, complaint_id)
    if comp is None:
        raise KeyError(complaint_id)
    camp = _campaign_props(conn, comp["campaign"]) if comp["campaign"] else None
    return {"complaint": {k: comp[k] for k in ("id", "region", "filed_at", "amount_kzt", "text_en", "tactics")},
            "campaign": camp}


def _quote_for(conn, complaint_id: str, label: str, key: Any) -> str | None:
    kind = {"Phone": "phone", "Card": "card", "Account": "iban", "Url": "url", "Persona": "persona"}.get(label)
    if not kind:
        return None
    r = rows(conn, """MATCH (x:Extraction {complaint_id: $c, kind: $k, value: $v}) RETURN x.quote AS q LIMIT 1""",
             {"c": complaint_id, "k": kind, "v": key})
    return redact(r[0]["q"]) if r else None


def explain_link(conn: relate.Connection, a: str, b: str, max_len: int = 8) -> dict:
    """Shortest evidence path between two complaints through identifiers and money flow (never through hubs)."""
    r = rows(conn, f"""
        MATCH p = shortestPath((x:Complaint {{id: $a}})-[:{LINK_RELS}*..{int(max_len)}]-(y:Complaint {{id: $b}}))
        WHERE all(n IN nodes(p) WHERE coalesce(n.hub, false) = false)
        RETURN nodes(p) AS ns, [r IN relationships(p) | type(r)] AS rels,
               [i IN range(0, size(relationships(p)) - 1) |
                    startNode(relationships(p)[i]) = nodes(p)[i]] AS fwd""", {"a": a, "b": b})
    if not r:
        sim = rows(conn, """
            MATCH (x:Complaint {id: $a})-[s:SIMILAR_SCRIPT]-(y:Complaint {id: $b}) RETURN s.score AS score""",
                   {"a": a, "b": b})
        return {"found": bool(sim), "hops": [{"label": "Complaint", "key": a}, {"label": "Complaint", "key": b}]
                if sim else [], "rels": ["SIMILAR_SCRIPT"] if sim else [], "forward": [True] if sim else [],
                "quotes": [], "similarity": sim[0]["score"] if sim else None}
    hops = [_node_ref(n) for n in r[0]["ns"]]
    rels = r[0]["rels"]
    forward = [bool(x) for x in r[0]["fwd"]]
    quotes = []
    for i, h in enumerate(hops):
        if h["label"] != "Complaint":
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(hops) and hops[j]["label"] != "Complaint":
                q = _quote_for(conn, h["key"], hops[j]["label"], hops[j]["key"])
                if q:
                    quotes.append({"complaint": h["key"], "entity": hops[j]["key"], "quote": q})
    return {"found": True, "hops": hops, "rels": rels, "forward": forward, "quotes": quotes, "similarity": None}


def render_path(link: dict) -> str:
    """CMP-0012 —PAID_TO→ 4000 00** **** 1234 ←PAID_TO— CMP-0031"""
    if not link.get("found"):
        return "(no connection found)"
    if link.get("similarity") is not None:
        a, b = link["hops"][0]["key"], link["hops"][1]["key"]
        return f"{a} ≈same script ({link['similarity']:.2f})≈ {b}"
    parts = [str(link["hops"][0]["key"])]
    for rel, fwd, hop in zip(link["rels"], link["forward"], link["hops"][1:]):
        parts.append(f"—{rel}→" if fwd else f"←{rel}—")
        parts.append(str(hop["key"]))
    return " ".join(parts)


def top_mules(conn: relate.Connection, campaign_id: str, n: int = 5) -> list[dict]:
    direct = rows(conn, """
        MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $id})
        MATCH (c)-[:PAID_TO]->(k) WHERE coalesce(k.hub, false) = false
        RETURN coalesce(k.pan_masked, k.iban) AS account, labels(k)[0] AS kind, k.bank AS bank,
               coalesce(k.role_hint, 'payee') AS role, count(DISTINCT c) AS victims, sum(c.amount_kzt) AS received_kzt
        ORDER BY victims DESC, received_kzt DESC""", {"id": campaign_id})
    downstream = rows(conn, """
        MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $id})
        MATCH (c)-[:PAID_TO]->()-[:FORWARDED_TO*1..3]->(k)
        RETURN coalesce(k.pan_masked, k.iban) AS account, labels(k)[0] AS kind, k.bank AS bank,
               coalesce(k.role_hint, 'transit') AS role, count(DISTINCT c) AS victims, 0 AS received_kzt
        ORDER BY victims DESC""", {"id": campaign_id})
    seen, out = set(), []
    for r in direct + downstream:
        if r["account"] not in seen:
            seen.add(r["account"])
            out.append(jsonable(r))
    out.sort(key=lambda r: ({"cashout": 0, "mule": 1}.get(r["role"], 2) if r["victims"] > 1 else 3,
                            -r["victims"]))
    return out[:n]


def similar_scripts(conn: relate.Connection, text: str, k: int = 5) -> list[dict]:
    v = embed.vectorize(text)
    if not any(v):
        return []
    hits = rows(conn, f"""
        CALL db.index.vector.queryNodes('{VECTOR_INDEX}', $k, $v) YIELD node, score
        OPTIONAL MATCH (node)-[:PART_OF]->(c:Campaign)
        RETURN node.id AS id, score, c.id AS campaign, node.text_en AS text_en, node.region AS region""",
                {"k": k, "v": v})
    return [{**jsonable(h), "score": round(float(h["score"]), 3)} for h in hits]


def campaign_graph(conn: relate.Connection, campaign_id: str) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add(n: Any) -> str:
        ref = _node_ref(n)
        nid = f"{ref['label']}:{ref['key']}" if ref["label"] != "Complaint" else ref["key"]
        if nid not in nodes:
            props = dict(n.items())
            nodes[nid] = {"id": nid, "label": ref["label"], "key": ref["key"], "role": ref["role"],
                          "region": props.get("region"), "amount_kzt": props.get("amount_kzt"),
                          "text_en": props.get("text_en")}
        return nid

    for r in rows(conn, f"""
        MATCH (c:Complaint)-[:PART_OF]->(:Campaign {{id: $id}})
        OPTIONAL MATCH (c)-[rel:CONTACTED_BY|PAID_TO|VISITED|MENTIONS_PERSONA]->(e)
        WHERE coalesce(e.hub, false) = false
        RETURN c, type(rel) AS t, e""", {"id": campaign_id}):
        cid = add(r["c"])
        if r["e"] is not None:
            eid = add(r["e"])
            q = _quote_for(conn, cid, nodes[eid]["label"], nodes[eid]["key"])
            edges.append({"source": cid, "target": eid, "type": r["t"], "quote": q})
    for r in rows(conn, """
        MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $id})
        MATCH (c)-[:PAID_TO]->(k0)-[:FORWARDED_TO*1..3]->(k)
        WITH DISTINCT k0, k
        MATCH p = (k0)-[:FORWARDED_TO*1..3]->(k)
        UNWIND relationships(p) AS f
        RETURN DISTINCT startNode(f) AS s, endNode(f) AS e, f.amount_kzt AS amt""", {"id": campaign_id}):
        s, e = add(r["s"]), add(r["e"])
        edges.append({"source": s, "target": e, "type": "FORWARDED_TO", "amount_kzt": r["amt"], "quote": None})
    for r in rows(conn, """
        MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $id})
        MATCH (c)-[:VISITED]->(u:Url)-[:ON_DOMAIN]->(d:Domain)
        RETURN DISTINCT u, d""", {"id": campaign_id}):
        edges.append({"source": add(r["u"]), "target": add(r["d"]), "type": "ON_DOMAIN", "quote": None})
    uniq = {(e["source"], e["target"], e["type"]): e for e in edges}
    return {"campaign": _campaign_props(conn, campaign_id), "nodes": list(nodes.values()),
            "edges": list(uniq.values())}


def list_campaigns(conn: relate.Connection) -> list[dict]:
    return [jsonable(dict(r["k"].items())) for r in
            rows(conn, "MATCH (k:Campaign) RETURN k ORDER BY k.size DESC, k.id")]


def list_complaints(conn: relate.Connection, limit: int = 50, offset: int = 0, campaign: str | None = None) -> dict:
    where = "WHERE k.id = $camp" if campaign else ""
    total = rows(conn, f"""MATCH (c:Complaint) OPTIONAL MATCH (c)-[:PART_OF]->(k:Campaign) {where}
                          WITH c, k {'WHERE k IS NOT NULL' if campaign else ''} RETURN count(c) AS n""",
                 {"camp": campaign})[0]["n"]
    items = rows(conn, f"""
        MATCH (c:Complaint) OPTIONAL MATCH (c)-[:PART_OF]->(k:Campaign) {where}
        WITH c, k {'WHERE k IS NOT NULL' if campaign else ''}
        OPTIONAL MATCH (c)-[:USED_TACTIC]->(t:Tactic)
        RETURN c.id AS id, toString(c.filed_at) AS filed_at, c.region AS region, c.amount_kzt AS amount_kzt,
               c.channel AS channel, c.text AS text, c.text_en AS text_en, k.id AS campaign,
               collect(t.code) AS tactics
        ORDER BY id DESC SKIP $skip LIMIT $lim""", {"camp": campaign, "skip": int(offset), "lim": int(limit)})
    return {"total": total, "items": [jsonable(i) for i in items]}
