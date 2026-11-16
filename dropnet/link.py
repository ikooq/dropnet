"""Connect complaints into campaigns.

Strong links: a shared phone, a shared phishing domain, or money that ends up in
the same account (directly or within a few FORWARDED_TO hops).
Weak links: a near-identical scam script (vector index) with the same tactic.
Hubs (e.g. a legitimate support line mentioned in many unrelated complaints) are
detected and excluded so they cannot glue campaigns together.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import relate

from .config import (HUB_MIN_REGIONS, HUB_MIN_TACTICS, MAX_FORWARD_HOPS, SCRIPT_ONLY_THRESHOLD, SIMILARITY_K,
                     SIMILARITY_THRESHOLD, VECTOR_INDEX)
from .models import Campaign
from .store import rows

ENTITY_KEYS = {"Phone": "e164", "Card": "pan_masked", "Account": "iban", "Domain": "name", "Persona": "name"}


# ------------------------------------------------------------------ similarity
def add_similarity(conn: relate.Connection, k: int = SIMILARITY_K,
                   threshold: float = SIMILARITY_THRESHOLD) -> int:
    """Write SIMILAR_SCRIPT edges (score = Relate's rebounded cosine) between near-duplicate scripts."""
    rows(conn, "MATCH ()-[s:SIMILAR_SCRIPT]->() DELETE s")
    items = rows(conn, "MATCH (c:Complaint) RETURN c.id AS id, c.script_vec AS v ORDER BY id")
    pairs: dict[tuple[str, str], float] = {}
    for it in items:
        hits = rows(conn, f"CALL db.index.vector.queryNodes('{VECTOR_INDEX}', $k, $v) YIELD node, score "
                          "RETURN node.id AS id, score", {"k": k + 1, "v": list(it["v"])})
        for h in hits:
            if h["id"] == it["id"] or h["score"] < threshold:
                continue
            a, b = sorted((it["id"], h["id"]))
            pairs[(a, b)] = max(pairs.get((a, b), 0.0), round(float(h["score"]), 4))
    if pairs:
        rows(conn, """
            UNWIND $rows AS r
            MATCH (a:Complaint {id: r.a}), (b:Complaint {id: r.b})
            CREATE (a)-[:SIMILAR_SCRIPT {score: r.s}]->(b)
        """, {"rows": [{"a": a, "b": b, "s": s} for (a, b), s in sorted(pairs.items())]})
    return len(pairs)


# ------------------------------------------------------------------------ hubs
def find_hubs(conn: relate.Connection, min_tactics: int = HUB_MIN_TACTICS,
              min_regions: int = HUB_MIN_REGIONS) -> set[str]:
    """Entities shared by complaints that are too diverse to be one gang. Marks them `hub = true`."""
    hubs: set[str] = set()
    for label, key in ENTITY_KEYS.items():
        if label == "Domain":
            pattern = "(c:Complaint)-[:VISITED]->(:Url)-[:ON_DOMAIN]->(n:Domain)"
        elif label == "Phone":
            pattern = "(c:Complaint)-[:CONTACTED_BY]->(n:Phone)"
        elif label == "Persona":
            pattern = "(c:Complaint)-[:MENTIONS_PERSONA]->(n:Persona)"
        else:
            pattern = f"(c:Complaint)-[:PAID_TO]->(n:{label})"
        found = rows(conn, f"""
            MATCH {pattern}
            OPTIONAL MATCH (c)-[:USED_TACTIC]->(t:Tactic)
            WITH n, count(DISTINCT c) AS cs, count(DISTINCT t) AS ts, count(DISTINCT c.region) AS rs
            WHERE cs >= 3 AND ts >= $mt AND rs >= $mr
            RETURN n.{key} AS key
        """, {"mt": min_tactics, "mr": min_regions})
        for f in found:
            hubs.add(f["key"])
            rows(conn, f"MATCH (n:{label} {{{key}: $k}}) SET n.hub = true", {"k": f["key"]})
    return hubs


def _clear_hubs(conn: relate.Connection) -> None:
    for label in ENTITY_KEYS:
        rows(conn, f"MATCH (n:{label}) WHERE n.hub = true SET n.hub = false")


# ---------------------------------------------------------------- strong pairs
def strong_pairs(conn: relate.Connection, max_hops: int = MAX_FORWARD_HOPS) -> list[tuple[str, str, str]]:
    """(complaint a, complaint b, entity that connects them), hubs excluded, a < b."""
    out: set[tuple[str, str, str]] = set()
    for r in rows(conn, """
        MATCH (a:Complaint)-[:CONTACTED_BY]->(p:Phone)<-[:CONTACTED_BY]-(b:Complaint)
        WHERE a.id < b.id AND coalesce(p.hub, false) = false
        RETURN a.id AS a, b.id AS b, p.e164 AS via"""):
        out.add((r["a"], r["b"], r["via"]))
    for r in rows(conn, """
        MATCH (a:Complaint)-[:VISITED]->(:Url)-[:ON_DOMAIN]->(d:Domain)<-[:ON_DOMAIN]-(:Url)<-[:VISITED]-(b:Complaint)
        WHERE a.id < b.id AND coalesce(d.hub, false) = false
        RETURN a.id AS a, b.id AS b, d.name AS via"""):
        out.add((r["a"], r["b"], r["via"]))
    for r in rows(conn, """
        MATCH (a:Complaint)-[:MENTIONS_PERSONA]->(p:Persona)<-[:MENTIONS_PERSONA]-(b:Complaint)
        WHERE a.id < b.id AND coalesce(p.hub, false) = false
        MATCH (a)-[:USED_TACTIC]->(t:Tactic)<-[:USED_TACTIC]-(b)
        RETURN DISTINCT a.id AS a, b.id AS b, 'persona:' + p.name AS via"""):
        out.add((r["a"], r["b"], r["via"]))
    hops = int(max_hops)
    for r in rows(conn, f"""
        MATCH (a:Complaint)-[:PAID_TO]->(x)-[:FORWARDED_TO*0..{hops}]->(k)<-[:FORWARDED_TO*0..{hops}]-(y)<-[:PAID_TO]-(b:Complaint)
        WHERE a.id < b.id AND coalesce(x.hub, false) = false AND coalesce(y.hub, false) = false
          AND coalesce(k.hub, false) = false
        RETURN DISTINCT a.id AS a, b.id AS b, coalesce(k.pan_masked, k.iban) AS via"""):
        out.add((r["a"], r["b"], r["via"]))
    return sorted(out)


# ------------------------------------------------------------------ union-find
class _UF:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            lo, hi = sorted((ra, rb))
            self.p[hi] = lo


def _groups(uf: _UF, ids) -> dict[str, list[str]]:
    g: dict[str, list[str]] = defaultdict(list)
    for x in ids:
        g[uf.find(x)].append(x)
    return {k: sorted(v) for k, v in g.items()}


def _weak_edges(conn: relate.Connection, threshold: float) -> list[tuple[str, str]]:
    return [(r["a"], r["b"]) for r in rows(conn, """
        MATCH (a:Complaint)-[s:SIMILAR_SCRIPT]->(b:Complaint)
        WHERE s.score >= $t
        MATCH (a)-[:USED_TACTIC]->(t:Tactic)<-[:USED_TACTIC]-(b)
        RETURN DISTINCT a.id AS a, b.id AS b""", {"t": threshold})]


# ------------------------------------------------------------------- campaigns
def build_campaigns(conn: relate.Connection, use_vectors: bool = True, use_forwarding: bool = True,
                    use_hub_filter: bool = True, threshold: float = SIMILARITY_THRESHOLD) -> list[Campaign]:
    _clear_hubs(conn)
    if use_hub_filter:
        find_hubs(conn)
    strong = strong_pairs(conn, MAX_FORWARD_HOPS if use_forwarding else 0)

    uf = _UF()
    strong_nodes: set[str] = set()
    for a, b, _via in strong:
        uf.union(a, b)
        strong_nodes.update((a, b))
    groups = {k: v for k, v in _groups(uf, strong_nodes).items() if len(v) >= 2}
    member_of = {cid: root for root, ms in groups.items() for cid in ms}

    weak_joined: set[str] = set()
    if use_vectors:
        weak = _weak_edges(conn, threshold)
        nbrs: dict[str, set[str]] = defaultdict(set)
        for a, b in weak:
            nbrs[a].add(b)
            nbrs[b].add(a)
        # 1) attach loose complaints that echo an existing campaign's script at least twice
        for cid in sorted(nbrs):
            if cid in member_of:
                continue
            votes = Counter(member_of[n] for n in nbrs[cid] if n in member_of)
            if votes:
                root, n = votes.most_common(1)[0]
                if n >= 2:
                    groups[root].append(cid)
                    weak_joined.add(cid)
        for root in groups:
            groups[root].sort()
        member_of = {cid: root for root, ms in groups.items() for cid in ms}
        # 2) script-only campaigns among the remaining loose complaints
        uf2 = _UF()
        loose = [c for c in nbrs if c not in member_of]
        loose_set = set(loose)
        for a, b in _weak_edges(conn, max(threshold, SCRIPT_ONLY_THRESHOLD)):
            if a in loose_set and b in loose_set:
                uf2.union(a, b)
        for root, ms in _groups(uf2, loose).items():
            if len(ms) >= 3:
                groups["S:" + root] = ms
                weak_joined.update(ms)

    campaigns = [_summarize(conn, ms, weak_joined) for ms in groups.values()]
    campaigns.sort(key=lambda c: c.id)
    _write(conn, campaigns)
    _card_roles(conn)
    return campaigns


def _summarize(conn: relate.Connection, members: list[str], weak_joined: set[str]) -> Campaign:
    members = sorted(members)
    info = rows(conn, """
        UNWIND $ids AS id MATCH (c:Complaint {id: id})
        OPTIONAL MATCH (c)-[:USED_TACTIC]->(t:Tactic)
        RETURN c.id AS id, c.region AS region, c.amount_kzt AS amount, toString(c.filed_at) AS d,
               collect(t.code) AS tactics""", {"ids": members})
    tactic_counts = Counter(t for r in info for t in r["tactics"])
    strong_share = sum(1 for m in members if m not in weak_joined) / len(members)
    return Campaign(
        id="CAMP-" + members[0].split("-")[1],
        member_ids=members,
        confidence=round(0.5 + 0.5 * strong_share, 2),
        size=len(members),
        damage_kzt=sum(r["amount"] for r in info),
        regions=sorted({r["region"] for r in info}),
        first_seen=min(r["d"] for r in info),
        last_seen=max(r["d"] for r in info),
        tactics=[t for t, _ in tactic_counts.most_common()],
    )


def _write(conn: relate.Connection, campaigns: list[Campaign]) -> None:
    rows(conn, "MATCH (k:Campaign) DETACH DELETE k")
    if not campaigns:
        return
    rows(conn, """
        UNWIND $rows AS r
        CREATE (k:Campaign {id: r.id, size: r.size, damage_kzt: r.damage, regions: r.regions,
                            first_seen: r.first, last_seen: r.last, confidence: r.conf, tactics: r.tactics,
                            synthetic: true})
        WITH k, r UNWIND r.members AS mid
        MATCH (c:Complaint {id: mid})
        CREATE (c)-[:PART_OF]->(k)
    """, {"rows": [{"id": c.id, "size": c.size, "damage": c.damage_kzt, "regions": c.regions,
                    "first": c.first_seen, "last": c.last_seen, "conf": c.confidence, "tactics": c.tactics,
                    "members": c.member_ids} for c in campaigns]})


def _card_roles(conn: relate.Connection) -> None:
    rows(conn, "MATCH (k:Card) SET k.role_hint = null")
    rows(conn, """
        MATCH (c:Complaint)-[:PAID_TO]->(k:Card) WITH k, count(DISTINCT c) AS n
        WHERE n >= 2 AND coalesce(k.hub, false) = false SET k.role_hint = 'mule'""")
    rows(conn, """
        MATCH (:Card)-[:FORWARDED_TO]->(k:Card) WHERE NOT (k)-[:FORWARDED_TO]->()
        SET k.role_hint = 'cashout'""")
