"""Write complaints, extracted entities, provenance and bank transfers into Relate."""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Iterable

import relate

from . import embed
from .config import BANKS, TACTICS
from .extract import normalize
from .models import Complaint, Dataset, Extraction, Transfer
from .store import rows


def _bank_for(key: str) -> str:
    return BANKS[int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(BANKS)]


def _account_label(value: str) -> str:
    return "Account" if value.startswith("KZ") else "Card"


def write_complaints(conn: relate.Connection, complaints: Iterable[Complaint]) -> int:
    batch = [{
        "id": c.id, "filed_at": c.filed_at.isoformat(), "region": c.region, "channel": c.channel,
        "amount_kzt": c.amount_kzt, "text": c.text, "text_en": c.text_en, "age": c.victim_age_band,
        "vec": embed.vectorize(c.text),
    } for c in complaints]
    rows(conn, """
        UNWIND $rows AS r
        CREATE (c:Complaint {id: r.id, filed_at: date(r.filed_at), region: r.region, channel: r.channel,
                             amount_kzt: r.amount_kzt, text: r.text, text_en: r.text_en,
                             victim_age_band: r.age, script_vec: r.vec, synthetic: true})
        MERGE (g:Region {name: r.region}) ON CREATE SET g.synthetic = true
        CREATE (c)-[:FILED_IN]->(g)
    """, {"rows": batch})
    return len(batch)


def write_extractions(conn: relate.Connection, extractions: Iterable[Extraction],
                      channels: dict[str, str]) -> None:
    by_kind: dict[str, list[dict]] = {}
    for e in extractions:
        by_kind.setdefault(e.kind, []).append({
            "eid": e.id, "cid": e.complaint_id, "kind": e.kind, "value": e.value, "s": e.span_start,
            "e": e.span_end, "quote": e.quote, "extractor": e.extractor,
            "channel": channels.get(e.complaint_id, "unknown"),
            "bank": _bank_for(e.value), "domain": normalize.domain(e.value) if e.kind == "url" else None,
            "label_ru": TACTICS.get(e.value, ("", ""))[0], "label_en": TACTICS.get(e.value, ("", ""))[1],
        })

    prov = """
        CREATE (x:Extraction {id: r.eid, complaint_id: r.cid, kind: r.kind, value: r.value, span_start: r.s,
                              span_end: r.e, quote: r.quote, extractor: r.extractor, synthetic: true})
        CREATE (x)-[:FROM]->(c)
        CREATE (x)-[:FOUND]->(n)
    """
    if "phone" in by_kind:
        rows(conn, """
            UNWIND $rows AS r MATCH (c:Complaint {id: r.cid})
            MERGE (n:Phone {e164: r.value}) ON CREATE SET n.synthetic = true
            MERGE (c)-[:CONTACTED_BY {channel: r.channel}]->(n)
        """ + prov, {"rows": by_kind["phone"]})
    for kind in ("card", "iban"):
        if kind in by_kind:
            label, key = ("Card", "pan_masked") if kind == "card" else ("Account", "iban")
            rows(conn, f"""
                UNWIND $rows AS r MATCH (c:Complaint {{id: r.cid}})
                MERGE (n:{label} {{{key}: r.value}}) ON CREATE SET n.synthetic = true, n.bank = r.bank
                MERGE (b:Bank {{name: r.bank}}) ON CREATE SET b.synthetic = true
                MERGE (n)-[:ISSUED_BY]->(b)
                MERGE (c)-[:PAID_TO]->(n)
            """ + prov, {"rows": by_kind[kind]})
    if "url" in by_kind:
        rows(conn, """
            UNWIND $rows AS r MATCH (c:Complaint {id: r.cid})
            MERGE (n:Url {url: r.value}) ON CREATE SET n.synthetic = true, n.domain = r.domain
            MERGE (d:Domain {name: r.domain}) ON CREATE SET d.synthetic = true
            MERGE (n)-[:ON_DOMAIN]->(d)
            MERGE (c)-[:VISITED]->(n)
        """ + prov, {"rows": by_kind["url"]})
    if "tactic" in by_kind:
        rows(conn, """
            UNWIND $rows AS r MATCH (c:Complaint {id: r.cid})
            MERGE (n:Tactic {code: r.value}) ON CREATE SET n.synthetic = true, n.label_ru = r.label_ru,
                                                           n.label_en = r.label_en
            MERGE (c)-[:USED_TACTIC]->(n)
        """ + prov, {"rows": by_kind["tactic"]})
    if "amount" in by_kind:
        rows(conn, """
            UNWIND $rows AS r MATCH (c:Complaint {id: r.cid})
            CREATE (x:Extraction {id: r.eid, complaint_id: r.cid, kind: r.kind, value: r.value, span_start: r.s,
                                  span_end: r.e, quote: r.quote, extractor: r.extractor, synthetic: true})
            CREATE (x)-[:FROM]->(c)
            CREATE (x)-[:FOUND]->(c)
        """, {"rows": by_kind["amount"]})


def write_transfers(conn: relate.Connection, transfers: Iterable[Transfer]) -> int:
    batch = [{"src": t.src, "dst": t.dst, "amt": t.amount_kzt, "at": t.at.isoformat(),
              "sl": _account_label(t.src), "dl": _account_label(t.dst),
              "sb": _bank_for(t.src), "db": _bank_for(t.dst)} for t in transfers]
    for sl in ("Card", "Account"):
        for dl in ("Card", "Account"):
            part = [b for b in batch if b["sl"] == sl and b["dl"] == dl]
            if not part:
                continue
            sk = "pan_masked" if sl == "Card" else "iban"
            dk = "pan_masked" if dl == "Card" else "iban"
            rows(conn, f"""
                UNWIND $rows AS r
                MERGE (a:{sl} {{{sk}: r.src}}) ON CREATE SET a.synthetic = true, a.bank = r.sb
                MERGE (b:{dl} {{{dk}: r.dst}}) ON CREATE SET b.synthetic = true, b.bank = r.db
                CREATE (a)-[:FORWARDED_TO {{amount_kzt: r.amt, at: r.at}}]->(b)
            """, {"rows": part})
    return len(batch)


def load_dataset(conn: relate.Connection, ds: Dataset, extractions: list[Extraction]) -> dict[str, int]:
    write_complaints(conn, ds.complaints)
    write_extractions(conn, extractions, {c.id: c.channel for c in ds.complaints})
    write_transfers(conn, ds.transfers)
    counts = Counter()
    for r in rows(conn, "MATCH (n) RETURN labels(n)[0] AS l, count(n) AS c"):
        counts[r["l"]] = r["c"]
    return dict(counts)
