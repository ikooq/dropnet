"""MCP server (stdio) that gives any agent the evidence in the FTC complaint graph before it answers.

If `python -m dropnet serve` is running it proxies to its API, so the agent never fights the web app for Relate's
single-writer lock. Otherwise it opens data/ftc.rl read-only (what-if runs on a throw-away copy).
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
from .ftc.api import FTC_TOOL_NAMES, dispatch_ftc

TOOL_NAMES = list(FTC_TOOL_NAMES)
INSTRUCTIONS = """Dropnet: real FTC Do Not Call complaints (US public data) in a Relate graph, joined to NANPA numbering data.
(:Report)-[:FROM_NUMBER]->(:Number)-[:IN_BLOCK]->(:Block {npa_nxx})-[:IN_AREA]->(:AreaCode)
(:Report)-[:ABOUT]->(:Subject), -[:VICTIM_IN]->(:State), -[:VICTIM_AREA]->(:AreaCode)
(:FtcCampaign {kind: pool|repeat})-[:USES_BLOCK|USES_NUMBER]->(...)
(:Block)-[:HELD_BY]->(:Carrier {ocn})-[:PART_OF]->(:CarrierGroup), (:Block)-[:IN_RATE_CENTER]->(:RateCenter)
(:Number)-[:IN_SUBBLOCK]->(:SubBlock)-[:ASSIGNED_TO]->(:Carrier)
Rules: complaints are unverified and caller ID can be faked. A carrier holds or was assigned numbers; it is not the
caller. Never call a number's owner or a carrier a scammer, and always relay the `caution` field."""


class Backend:
    def __init__(self, web_url: str | None = None, ftc_snapshot: str | Path | None = None):
        self.web_url = (web_url or os.environ.get("DROPNET_WEB_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.ftc_snapshot = Path(ftc_snapshot or os.environ.get("DROPNET_FTC_SNAPSHOT") or config.DATA_DIR / "ftc.rl")
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="relate-mcp")
        self._ftc = None
        self._ftc_rw = None
        self._tmp = None

    def _local(self, name: str, args: dict) -> Any:
        import shutil
        import tempfile
        if name == "whatif_block":  # needs a writable store: a throw-away copy keeps the snapshot untouched
            if self._ftc_rw is None:
                self._tmp = Path(tempfile.mkdtemp(prefix="dropnet-mcp-"))
                shutil.copy(self.ftc_snapshot, self._tmp / "ftc.rl")
                self._ftc_rw = store.open_store(self._tmp / "ftc.rl")
            return dispatch_ftc(self._ftc_rw, name, args)
        if self._ftc is None:
            self._ftc = store.open_store(self.ftc_snapshot, read_only=True)
        return dispatch_ftc(self._ftc, name, args)

    def mode(self) -> str:
        try:
            with urllib.request.urlopen(self.web_url + "/api/health", timeout=0.5) as r:
                return "proxy" if json.loads(r.read()).get("ok") else "snapshot"
        except (OSError, ValueError, urllib.error.URLError):
            return "snapshot"

    def call(self, name: str, args: dict) -> Any:
        if name not in TOOL_NAMES:
            raise LookupError(name)
        if name == "ftc_read_cypher":
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
        for attr in ("_ftc", "_ftc_rw"):
            c = getattr(self, attr)
            if c is not None:
                self._pool.submit(c.close).result()
                setattr(self, attr, None)
        self._pool.shutdown(wait=True)
        if self._tmp is not None:
            import shutil
            shutil.rmtree(self._tmp, ignore_errors=True)


def build_server(backend: Backend):
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("dropnet", instructions=INSTRUCTIONS, version="0.2.0")

    @mcp.tool()
    def get_schema() -> dict:
        """Node labels and relationship types of the FTC graph, with counts."""
        return backend.call("ftc_schema", {})

    @mcp.tool()
    def read_cypher(statement: str, params: dict | None = None) -> dict:
        """Run ONE read-only Cypher statement against the FTC graph (writes are rejected). Use $parameters."""
        return backend.call("ftc_read_cypher", {"statement": statement, "params": params or {}})

    @mcp.tool()
    def ftc_summary() -> dict:
        """Totals of the FTC Do Not Call reports graph and, per scam type, the share of reports with matching caller
        and consumer area codes. This is not proof of spoofing."""
        return backend.call("ftc_summary", {})

    @mcp.tool()
    def ftc_campaigns(limit: int = 20, kind: str | None = None) -> list:
        """Number pools (many numbers from one NPA-NXX range) and repeat numbers, by report volume."""
        return backend.call("ftc_campaigns", {"limit": limit, "kind": kind})

    @mcp.tool()
    def assess_number(number: str) -> dict:
        """Evidence about a phone number reported to the FTC: reports, states, scam types, its range's pool, the
        NANPA holder of its range, and a verdict (likely_spoofed / pool / repeat / single / unknown).
        ALWAYS relay the `caution` field. Area-code matches are indicators, not proof of spoofing or ownership."""
        return backend.call("assess_number", {"number": number})

    @mcp.tool()
    def search_ranges(text: str, state: str | None = None, limit: int = 10) -> dict:
        """Search complaint-range profiles, optionally filtered to one US state.
        Search uses full-text and adds vector ranking when the optional semantic dependencies are installed."""
        return backend.call("search_ranges", {"text": text, "state": state, "limit": limit})

    @mcp.tool()
    def whatif_block(blocks: list[str] | None = None, numbers: list[str] | None = None,
                     since_day: str | None = None) -> dict:
        """Count reports matching hypothetical NPA-NXX ranges or numbers. This does not measure prevented calls or
        legitimate-call impact. The transaction is rolled back."""
        return backend.call("whatif_block", {"blocks": blocks, "numbers": numbers, "since_day": since_day})

    @mcp.tool()
    def carriers(limit: int = 25) -> dict:
        """Carriers (NANPA range holders) ranked by how many flagged ranges they hold, with flagged ranges per 100
        ranges held. A holder issued the numbers; it is not the caller. ALWAYS relay the `caution` field."""
        return backend.call("carriers", {"limit": limit})

    @mcp.tool()
    def carrier_detail(carrier: str, limit: int = 40) -> dict:
        """One carrier's flagged ranges with rate centers, states and complaint categories."""
        return backend.call("carrier_detail", {"carrier": carrier, "limit": limit})

    return mcp


def main() -> int:
    backend = Backend()
    try:
        build_server(backend).run("stdio")
    finally:
        backend.close()
    return 0
