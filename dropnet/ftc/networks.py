"""Pool networks: number ranges that strike the same victims' area codes, on the same days, with the same scam.

Path behind every link (multi-hop, read straight off the graph):
(Pool A)-[:USES_BLOCK]->(Block)<-[:IN_BLOCK]-(Number)<-[:FROM_NUMBER]-(Report)-[:VICTIM_AREA]->(AreaCode)
          <-[:VICTIM_AREA]-(Report)-[:FROM_NUMBER]->(Number)-[:IN_BLOCK]->(Block)<-[:USES_BLOCK]-(Pool B)
with both reports on the same day and about the same subject. Spoofed reports are left out.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations

import relate

from ..store import rows

BUCKET_QUERY = """
    MATCH (c:FtcCampaign {{kind: 'pool'}})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(:Number)<-[:FROM_NUMBER]-(r:Report)
    WHERE r.neighbor = false {extra}
    MATCH (r)-[:VICTIM_AREA]->(a:AreaCode)
    MATCH (r)-[:ABOUT]->(s:Subject)
    RETURN c.id AS pool, r.day AS day, a.npa AS area, s.code AS subject"""


# Tuned on the real data: looser settings glue 127-1,118 pools into one meaningless blob (busy areas, generic subjects).
UNINFORMATIVE = {"OTHER", "NONE", "DROPPED"}


def link_pools(conn: relate.Connection, min_shared: int = 10, max_pools_per_bucket: int = 5) -> dict:
    rows(conn, "MATCH ()-[s:SIBLING]->() DELETE s")
    rows(conn, "MATCH (n:PoolNetwork) DETACH DELETE n")
    buckets: dict[tuple, set[str]] = defaultdict(set)
    for r in rows(conn, BUCKET_QUERY.format(extra="")):
        if r["subject"] not in UNINFORMATIVE:
            buckets[(r["day"], r["area"], r["subject"])].add(r["pool"])
    pairs: Counter = Counter()
    for pools in buckets.values():
        if 2 <= len(pools) <= max_pools_per_bucket:  # a bucket every pool touches says nothing
            pairs.update(combinations(sorted(pools), 2))
    links = [(a, b, n) for (a, b), n in pairs.items() if n >= min_shared]
    if links:
        rows(conn, """UNWIND $l AS l MATCH (a:FtcCampaign {id: l.a}), (b:FtcCampaign {id: l.b})
                      CREATE (a)-[:SIBLING {shared: l.n}]->(b)""",
             {"l": [{"a": a, "b": b, "n": n} for a, b, n in links]})
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, _ in links:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups: dict[str, list[str]] = defaultdict(list)
    for x in list(parent):
        groups[find(x)].append(x)
    nets = [sorted(v) for v in groups.values() if len(v) >= 2]
    if nets:
        rows(conn, """UNWIND $n AS n CREATE (net:PoolNetwork {id: 'NET-' + n.root, pools: size(n.members)})
                      WITH net, n UNWIND n.members AS m MATCH (c:FtcCampaign {id: m}) CREATE (c)-[:IN_NETWORK]->(net)""",
             {"n": [{"root": m[0].replace("POOL-", ""), "members": m} for m in nets]})
        rows(conn, """MATCH (c:FtcCampaign)-[:IN_NETWORK]->(net:PoolNetwork)
                      WITH net, sum(c.reports) AS reps, sum(c.numbers) AS nums
                      SET net.reports = reps, net.numbers = nums""")
    return {"links": len(links), "networks": len(nets), "pools_in_networks": sum(len(n) for n in nets),
            "largest": max((len(n) for n in nets), default=0)}


def explain_siblings(conn: relate.Connection, a: str, b: str, limit: int = 5) -> dict:
    found = rows(conn, BUCKET_QUERY.format(extra="AND c.id IN [$a, $b]"), {"a": a, "b": b})
    by: dict[tuple, set[str]] = defaultdict(set)
    for r in found:
        by[(r["day"], r["area"], r["subject"])].add(r["pool"])
    shared = sorted(k for k, v in by.items() if len(v) == 2)
    return {"a": a, "b": b, "shared": len(shared),
            "examples": [{"day": d, "area": ar, "subject": s} for d, ar, s in shared[:limit]],
            "path": f"({a})-[:USES_BLOCK]->(Block)<-[:IN_BLOCK]-(Number)<-[:FROM_NUMBER]-(Report)-[:VICTIM_AREA]->"
                    f"(AreaCode)<-[:VICTIM_AREA]-(Report)-[:FROM_NUMBER]->(Number)-[:IN_BLOCK]->(Block)<-[:USES_BLOCK]-({b})"}
