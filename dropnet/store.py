"""Thin helpers around the embedded Relate engine."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import relate

from .config import VECTOR_DIM, VECTOR_INDEX


def open_store(path: str | Path, read_only: bool = False) -> relate.Connection:
    """Open (or create) a single-file Relate store."""
    path = Path(path)
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
        return relate.connect(str(path))
    return relate.connect(str(path), read_only=True)


def reset_store(path: str | Path) -> None:
    """Delete a store file (and its auth token sidecar, if any)."""
    path = Path(path)
    for p in (path, Path(str(path) + ".auth-token")):
        if p.exists():
            os.remove(p)


def rows(conn: relate.Connection, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Run one statement and return its rows as plain dicts.

    relate.Record is a dict subclass whose serialisation only knows the result columns, so keys added later
    (derived fields) would silently vanish from JSON responses. Copy into real dicts.
    """
    return [{k: r[k] for k in r.keys()} for r in conn.execute(cypher, params or {}).data()]


def ensure_schema(conn: relate.Connection, dim: int = VECTOR_DIM) -> None:
    """Create the complaint-script vector index if it does not exist yet."""
    try:
        rows(
            conn,
            f"CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS FOR (c:Complaint) ON (c.script_vec) "
            f"OPTIONS {{indexConfig: {{`vector.dimensions`: {int(dim)}, "
            "`vector.similarity_function`: 'cosine'}}",
        )
    except relate.Error as e:  # older dialects without IF NOT EXISTS
        if "exist" not in str(e).lower():
            raise
