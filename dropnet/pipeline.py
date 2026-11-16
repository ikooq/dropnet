"""generate -> extract -> embed -> load -> link, into one single-file Relate store."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from . import evaluate, link, load, store
from .extract import rules
from .models import Campaign
from .synth.generate import generate, write_dataset


@dataclass
class BuildReport:
    path: Path
    counts: dict[str, int]
    campaigns: list[Campaign]
    scores: dict[str, float]
    seconds: float
    similar_edges: int


def build(path: str | Path, seed: int = 1, n: int = 250, hard: bool = False, raw_dir: str | Path | None = None,
          use_vectors: bool = True, use_forwarding: bool = True, use_hub_filter: bool = True) -> BuildReport:
    t0 = time.perf_counter()
    path = Path(path)
    ds = generate(seed=seed, n=n, hard=hard)
    if raw_dir is not None:
        write_dataset(ds, Path(raw_dir))
    store.reset_store(path)
    conn = store.open_store(path)
    try:
        store.ensure_schema(conn)
        extractions = [e for c in ds.complaints for e in rules.extract(c.id, c.text)]
        counts = load.load_dataset(conn, ds, extractions)
        sim = link.add_similarity(conn) if use_vectors else 0
        campaigns = link.build_campaigns(conn, use_vectors=use_vectors, use_forwarding=use_forwarding,
                                         use_hub_filter=use_hub_filter)
        rows = store.rows(conn, "MATCH (n) RETURN labels(n)[0] AS l, count(n) AS c")
        counts = {r["l"]: r["c"] for r in rows}
    finally:
        conn.close()
    scores = evaluate.pairwise({c.id: c.member_ids for c in campaigns}, ds.truth)
    return BuildReport(path, counts, campaigns, scores, time.perf_counter() - t0, sim)
