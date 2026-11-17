"""Hybrid search over the rented ranges: Relate full-text + vector SEARCH, merged by Reciprocal Rank Fusion.

Every pool gets a plain-English profile written from its graph neighbourhood (scam types people reported, the
states they called into, toll-free or local, how many numbers and reports), stored on the campaign node with a
384-number embedding (BAAI/bge-small-en-v1.5, local ONNX through fastembed, no API key).

    "Medicare back brace calls in Florida"  ->  full-text finds few literal words; the vector side finds MEDICAL
                                                 ranges; the graph then filters to ranges that called Florida.

fastembed is optional: without it, search falls back to the full-text side alone.
"""
from __future__ import annotations

import relate

from ..store import rows
from .parse import SUBJECT_LABEL

MODEL = "BAAI/bge-small-en-v1.5"
DIM = 384
VECTOR_INDEX = "pool_profile_vec"
TEXT_INDEX = "pool_profile_ft"
RRF_K = 60  # standard Reciprocal Rank Fusion constant
FT_WEIGHT = 0.5  # full-text's share in the fusion (vector = 1); set by `sweep` below on the 14 eval queries

# what people actually say about these calls, so a profile reads like the complaints, not like a category code
SUBJECT_WORDS = {
    "DEBT": "debt relief, credit card interest, student loans, mortgage help",
    "IMPOSTER_GOV": "impersonation of government agencies, businesses, family or friends",
    "MEDICAL": "medical offers and prescriptions",
    "WARRANTY": "warranties and extended protection plans",
    "HOME": "home improvement, repairs and cleaning",
    "DROPPED": "dropped calls or silence with no message",
    "TRAVEL": "vacation packages and timeshares",
    "PRIZES": "lotteries, prizes and sweepstakes",
    "ENERGY": "energy, solar and utility bills",
    "TECH": "computer and technical support",
    "WORK": "work from home and business opportunities",
    "NONE": "no subject given",
    "OTHER": "other unwanted calls",
}

_model = None


def embedder():
    """The local embedding model, or None when fastembed / onnxruntime is unavailable."""
    global _model
    if _model is None:
        try:
            from fastembed import TextEmbedding
            _model = TextEmbedding(MODEL)
        except Exception:  # ImportError, DLL load failure, offline first run
            _model = False
    return _model or None


def embed(texts: list[str]) -> list[list[float]] | None:
    m = embedder()
    return [list(map(float, v)) for v in m.embed(texts)] if m else None


def profiles(conn: relate.Connection) -> list[dict]:
    """One English paragraph per pool, from the graph."""
    pools = rows(conn, """MATCH (c:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(b:Block)
                          RETURN c.id AS id, b.npa_nxx AS block, c.numbers AS numbers, c.reports AS reports,
                                 c.toll_free AS toll_free""")
    subj, states = {}, {}
    for r in rows(conn, """MATCH (c:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(:Number)
                                 <-[:FROM_NUMBER]-(r:Report)-[:ABOUT]->(s:Subject)
                           RETURN c.id AS id, s.code AS code, count(r) AS n"""):
        subj.setdefault(r["id"], []).append((r["n"], r["code"]))
    for r in rows(conn, """MATCH (c:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(:Number)
                                 <-[:FROM_NUMBER]-(r:Report)-[:VICTIM_IN]->(s:State)
                           RETURN c.id AS id, s.name AS state, count(r) AS n"""):
        states.setdefault(r["id"], []).append((r["n"], r["state"]))
    out = []
    for p in pools:
        top = [c for _n, c in sorted(subj.get(p["id"], []), reverse=True) if c not in ("OTHER", "NONE")][:3]
        st = [s for _n, s in sorted(states.get(p["id"], []), reverse=True)]
        b = p["block"]
        text = (f"{'Toll-free' if p['toll_free'] else 'Local'} phone number range {b[:3]}-{b[3:]}-xxxx: "
                f"{p['numbers']} numbers reported {p['reports']} times. "
                + (f"Calls about {'; '.join(SUBJECT_WORDS.get(c, SUBJECT_LABEL.get(c, c)) for c in top)}. " if top else "")
                + (f"People called in {', '.join(st[:8])}" + (f" and {len(st) - 8} more states." if len(st) > 8 else ".")
                   if st else ""))
        out.append({"id": p["id"], "text": text, "subjects": top, "states": st})
    return out


def write_profiles(conn: relate.Connection, batch: int = 500, log=print) -> int:
    """Profiles (+ vectors when the model is available) on every pool, and both indexes."""
    ps = profiles(conn)
    vecs = embed([p["text"] for p in ps])
    for i in range(0, len(ps), batch):
        part = [{"id": p["id"], "text": p["text"], "states": p["states"], **({"vec": vecs[i + k]} if vecs else {})}
                for k, p in enumerate(ps[i:i + batch])]
        rows(conn, """UNWIND $p AS p MATCH (c:FtcCampaign {id: p.id})
                      SET c.profile = p.text, c.victim_states = p.states, c.profile_vec = p.vec""", {"p": part})
    rows(conn, f"CREATE FULLTEXT INDEX {TEXT_INDEX} IF NOT EXISTS FOR (c:FtcCampaign) ON EACH [c.profile]")
    if vecs:
        rows(conn, f"""CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS FOR (c:FtcCampaign) ON (c.profile_vec)
                       OPTIONS {{indexConfig: {{`vector.dimensions`: {DIM}, `vector.similarity_function`: 'cosine'}}}}""")
    log(f"profiles: {len(ps)} pools, vectors: {'yes' if vecs else 'no (fastembed unavailable)'}")
    return len(ps)


# words every profile contains (or plain English glue): matching them ranks everything alike and drowns the signal
_NOISE = set("""a an and are as at be by call called calls caller calling for from got i in is it its me my number numbers
of on or our phone range ranges reported reports said say says some someone that the they this times to was we were
what who with you your xxxx people""".split())


def _fulltext(conn, text: str, k: int) -> list[str]:
    import re
    words = [w for w in re.findall(r"[A-Za-z0-9]+", text) if w.lower() not in _NOISE]
    q = " ".join(words)  # the index's query language must not see stray syntax
    if not q:
        return []
    return [r["id"] for r in rows(conn, f"""MATCH (c:FtcCampaign) SEARCH c IN (FULLTEXT INDEX {TEXT_INDEX} FOR $q LIMIT $k)
                                            SCORE AS s RETURN c.id AS id ORDER BY s DESC""", {"q": q, "k": k})]


def _vector(conn, vec: list[float], k: int) -> list[str]:
    return [r["id"] for r in rows(conn, f"""MATCH (c:FtcCampaign) SEARCH c IN (VECTOR INDEX {VECTOR_INDEX} FOR $v LIMIT $k)
                                            SCORE AS s RETURN c.id AS id ORDER BY s DESC""", {"v": vec, "k": k})]


# How people describe the call, not the FTC category name; the right answer is a range whose main scam type matches.
EVAL_QUERIES = [
    ("lower my credit card interest rate", "DEBT"), ("student loan forgiveness program", "DEBT"),
    ("Medicare back brace for free", "MEDICAL"), ("cheap prescription drugs pharmacy", "MEDICAL"),
    ("someone pretending to be the IRS", "IMPOSTER_GOV"), ("your Social Security number is suspended", "IMPOSTER_GOV"),
    ("your car warranty is about to expire", "WARRANTY"), ("lower my electricity bill with solar panels", "ENERGY"),
    ("you won a free cruise", "TRAVEL"), ("you have won a sweepstakes prize", "PRIZES"),
    ("Microsoft says my computer has a virus", "TECH"), ("roof repair and new windows", "HOME"),
    ("earn money working from home", "WORK"), ("the line goes silent and hangs up", "DROPPED"),
]


def evaluate(conn: relate.Connection, k: int = 10) -> dict:
    """Precision@k per mode: share of the top k ranges whose most-reported scam type is the one the query describes."""
    top = {p["id"]: (p["subjects"] or [None])[0] for p in profiles(conn)}
    out = {}
    for mode in ("fulltext", "vector", "hybrid"):
        per = []
        for q, code in EVAL_QUERIES:
            res = search(conn, q, limit=k, mode=mode)["results"]
            per.append(sum(1 for r in res if top.get(r["id"]) == code) / k)
        out[mode] = {"precision_at_10": round(sum(per) / len(per), 3), "per_query": [round(x, 2) for x in per]}
    out["queries"] = [q for q, _ in EVAL_QUERIES]
    return out


def search(conn: relate.Connection, text: str, limit: int = 10, mode: str = "hybrid", state: str | None = None,
           depth: int = 200) -> dict:
    """mode: hybrid | fulltext | vector. `state` keeps only ranges that called into that state (a graph filter)."""
    text = (text or "").strip()
    if not text:
        return {"mode": mode, "results": []}
    lists = []  # (weight, ranked ids)
    if mode in ("hybrid", "fulltext"):
        lists.append((FT_WEIGHT if mode == "hybrid" else 1.0, _fulltext(conn, text, depth)))
    used = mode
    if mode in ("hybrid", "vector"):
        v = embed([text])
        if v:
            lists.append((1.0, _vector(conn, v[0], depth)))
        elif mode == "vector":
            return {"mode": "vector", "results": [], "note": "fastembed unavailable"}
        else:
            used = "fulltext (no model)"
    fused: dict[str, float] = {}
    for w, lst in lists:
        for rank, cid in enumerate(lst):
            fused[cid] = fused.get(cid, 0.0) + w / (RRF_K + rank + 1)
    ranked = sorted(fused, key=lambda c: -fused[c])
    if not ranked:
        return {"mode": used, "results": []}
    found = rows(conn, """UNWIND $ids AS id MATCH (c:FtcCampaign {id: id})
                          WHERE $st IS NULL OR $st IN c.victim_states
                          RETURN c.id AS id, c.numbers AS numbers, c.reports AS reports, c.profile AS profile""",
                 {"ids": ranked, "st": state})
    by = {f["id"]: f for f in found}
    out = [dict(by[c], score=round(fused[c], 5)) for c in ranked if c in by][:limit]
    return {"mode": used, "results": out}
