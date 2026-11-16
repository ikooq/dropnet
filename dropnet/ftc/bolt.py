"""Serve the Dropnet graph over Bolt so Neo4j drivers and tools can use it unchanged.

    relate serve --database data/ftc.rl --read-only --bolt 7687 --auth none   # loopback only

and from any Neo4j driver:  GraphDatabase.driver("bolt://127.0.0.1:7687", auth=None)
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

from .build import relate_cli


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def query_via_bolt(store: Path | str, cypher: str, params: dict | None = None, timeout: float = 30) -> list[dict] | None:
    """Start a read-only Relate Bolt server on the store, run one query with the official neo4j driver, stop."""
    cli = relate_cli()
    if not cli:
        return None
    from neo4j import GraphDatabase
    port = _free_port()
    proc = subprocess.Popen([cli, "serve", "--database", str(store), "--read-only", "--host", "127.0.0.1",
                             "--bolt", str(port), "--auth", "none"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env={**os.environ, "RELATE_TELEMETRY": "off"})
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.2)
        with GraphDatabase.driver(f"bolt://127.0.0.1:{port}", auth=None) as driver:
            records, _, _ = driver.execute_query(cypher, params or {})
            return [r.data() for r in records]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
