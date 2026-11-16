"""MCP server (stdio) that lets any agent investigate the Dropnet graph.

If `python -m dropnet serve` is running it proxies to its API, so the agent sees complaints
ingested a moment ago and never fights the web app for Relate's single-writer lock.
Otherwise it opens the committed snapshot read-only.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import config, store, tools

TOOL_NAMES = tools.TOOL_NAMES
INSTRUCTIONS = """Dropnet: a Relate graph of (synthetic) Kazakh fraud complaints.
Nodes: Complaint (Russian text + English gloss), Phone, Card (masked), Account (IBAN), Url, Domain, Persona (alias),
Tactic, Region, Bank, Campaign, Extraction (provenance: the quote each link comes from).
Relationships: CONTACTED_BY, PAID_TO, FORWARDED_TO (money moving between cards), VISITED, ON_DOMAIN, MENTIONS_PERSONA,
USED_TACTIC, FILED_IN, SIMILAR_SCRIPT {score}, PART_OF (Campaign), FROM/FOUND (Extraction).
Rules: every claim must cite node ids, a path (use explain_link) and a victim quote. Nodes with hub=true are
legitimate shared numbers (e.g. marketplace support) and are NOT evidence. All data is synthetic."""


class Backend:
    def __init__(self, web_url: str | None = None, snapshot: str | Path | None = None):
        self.web_url = (web_url or os.environ.get("DROPNET_WEB_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.snapshot = Path(snapshot or os.environ.get("DROPNET_SNAPSHOT") or config.SNAPSHOT_PATH)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="relate-mcp")
        self._conn = None

    def mode(self) -> str:
        try:
            with urllib.request.urlopen(self.web_url + "/api/health", timeout=0.5) as r:
                return "proxy" if json.loads(r.read()).get("ok") else "snapshot"
        except (OSError, ValueError, urllib.error.URLError):
            return "snapshot"

    def _local(self, name: str, args: dict) -> Any:
        if self._conn is None:
            self._conn = store.open_store(self.snapshot, read_only=True)
        return tools.dispatch(self._conn, name, args)

    def call(self, name: str, args: dict) -> Any:
        if name not in TOOL_NAMES:
            raise LookupError(name)
        if name == "read_cypher":
            tools.check_read_only(args.get("statement", ""))
        if self.mode() == "proxy":
            req = urllib.request.Request(f"{self.web_url}/api/tools/{name}", data=json.dumps(args).encode(),
                                         headers={"content-type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                detail = json.loads(e.read() or b"{}").get("detail", str(e))
                raise ValueError(detail) from None
        return self._pool.submit(self._local, name, args).result()

    def close(self) -> None:
        if self._conn is not None:
            self._pool.submit(self._conn.close).result()
            self._conn = None
        self._pool.shutdown(wait=True)


def build_server(backend: Backend):
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("dropnet", instructions=INSTRUCTIONS, version="0.1.0")

    @mcp.tool()
    def get_schema() -> dict:
        """Node labels and relationship types with counts, and the key property of each label."""
        return backend.call("get_schema", {})

    @mcp.tool()
    def read_cypher(statement: str, params: dict | None = None) -> dict:
        """Run ONE read-only Cypher statement against the Relate graph (writes are rejected).
        Vector search: CALL db.index.vector.queryNodes('complaint_script', k, vector)."""
        return backend.call("read_cypher", {"statement": statement, "params": params or {}})

    @mcp.tool()
    def list_campaigns() -> list:
        """All detected campaigns, largest first, with size, damage, regions, period, tactics and confidence."""
        return backend.call("list_campaigns", {})

    @mcp.tool()
    def find_campaign(complaint_id: str) -> dict:
        """The campaign a complaint (e.g. CMP-0042) belongs to, or campaign=null if it is not linked."""
        return backend.call("find_campaign", {"complaint_id": complaint_id})

    @mcp.tool()
    def explain_link(a: str, b: str) -> dict:
        """Shortest evidence path between two complaints through phones, cards, money transfers, domains or aliases
        (never through hub nodes), with the victims' own quotes. Falls back to script similarity."""
        return backend.call("explain_link", {"a": a, "b": b})

    @mcp.tool()
    def top_mules(campaign_id: str, n: int = 5) -> list:
        """Accounts that received money in a campaign: cash-out sinks first, then mule cards, with victim counts."""
        return backend.call("top_mules", {"campaign_id": campaign_id, "n": n})

    @mcp.tool()
    def similar_scripts(text: str, k: int = 5) -> list:
        """Complaints whose scam script is closest to `text` (Relate vector index), with their campaigns."""
        return backend.call("similar_scripts", {"text": text, "k": k})

    @mcp.tool()
    def build_case(campaign_id: str) -> str:
        """A full markdown case file for a campaign: summary, accounts to freeze, evidence paths, quotes, actions."""
        return backend.call("build_case", {"campaign_id": campaign_id})

    return mcp


def main() -> int:
    backend = Backend()
    try:
        build_server(backend).run("stdio")
    finally:
        backend.close()
    return 0
