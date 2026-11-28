"""FastAPI app: the analyst UI and a JSON API over the FTC complaint graph.

The committed data/ftc.rl is never written. On start the app copies it to data/live/ftc.rl (again only when the
committed file is newer, or with --reset) and is that copy's only writer; what-ifs roll back. MCP clients read
through /api.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import relate

from .. import config, store, tools

STATIC = Path(__file__).parent / "static"


class WhatIfIn(BaseModel):
    blocks: list[str] | None = None
    numbers: list[str] | None = None
    since_day: str | None = None


class CypherIn(BaseModel):
    statement: str
    params: dict[str, Any] | None = None


def prepare_live(snapshot: Path, live: Path, reset: bool) -> None:
    live.parent.mkdir(parents=True, exist_ok=True)
    if reset or not live.exists():
        store.reset_store(live)
        shutil.copy(snapshot, live)


def _summary(conn) -> dict:
    from ..ftc import api as ftc_api, campaigns as ftc_campaigns
    return {**ftc_api.summary(conn), "profile": ftc_campaigns.spoofing_profile(conn)}


def create_app(reset: bool = False, ftc_snapshot: Path | str = config.DATA_DIR / "ftc.rl",
               ftc_live: Path | str = config.DATA_DIR / "live" / "ftc.rl",
               ftc_eval: Path | str = config.DATA_DIR / "ftc" / "eval.json", ready_message: str | None = None) -> FastAPI:
    ftc_snapshot, ftc_live, ftc_eval = Path(ftc_snapshot), Path(ftc_live), Path(ftc_eval)
    state: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Relate connections are thread-affine: one dedicated thread owns the live store and runs every query.
        # That also makes it the store's only writer.
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="relate")
        state["pool"] = pool
        if ftc_snapshot.exists():
            # FTC what-if writes roll back. This copy can be refreshed when the checked-in data changes.
            stale_ftc = ftc_live.exists() and ftc_live.stat().st_mtime_ns < ftc_snapshot.stat().st_mtime_ns
            prepare_live(ftc_snapshot, ftc_live, reset or stale_ftc)
            state["ftc"] = pool.submit(store.open_store, ftc_live).result()
            state["summary"] = pool.submit(_summary, state["ftc"])  # warm the first page while the browser opens
        if ready_message:
            print(ready_message, flush=True)
        try:
            yield
        finally:
            for key in ("ftc",):
                if key in state:
                    pool.submit(state.pop(key).close).result()
            pool.shutdown(wait=True)

    app = FastAPI(title="Dropnet", lifespan=lifespan)

    def run_ftc(fn, *a, **kw):
        if "ftc" not in state:
            raise HTTPException(404, "FTC data not built: run `python -m dropnet ftc-build`")
        return state["pool"].submit(lambda: fn(state["ftc"], *a, **kw)).result()

    from ..ftc import api as ftc_api, campaigns as ftc_campaigns, whatif as ftc_whatif

    @app.get("/api/ftc/summary")
    def ftc_summary():
        if "ftc" not in state:
            raise HTTPException(404, "FTC data not built: run `python -m dropnet ftc-build`")
        s = dict(state["summary"].result())  # computed once: what-ifs always roll back, so it cannot change
        s["eval"] = json.loads(ftc_eval.read_text(encoding="utf-8")) if ftc_eval.exists() else None
        return s

    @app.get("/api/ftc/schema")
    def ftc_schema():
        return run_ftc(tools.get_schema)

    @app.post("/api/ftc/cypher")
    def ftc_cypher(body: CypherIn):
        try:
            return run_ftc(tools.read_cypher, body.statement, body.params)
        except (ValueError, relate.Error) as e:
            raise HTTPException(400, str(e))

    @app.get("/api/ftc/campaigns")
    def ftc_campaign_list(limit: int = 60, kind: str | None = None):
        return run_ftc(ftc_api.campaign_list, min(limit, 500), kind)

    @app.get("/api/ftc/campaigns/{cid}/graph")
    def ftc_graph(cid: str):
        g = run_ftc(ftc_api.campaign_graph, cid)
        if g is None:
            raise HTTPException(404, "unknown campaign")
        return g

    @app.get("/api/ftc/campaigns/{cid}/export")
    def ftc_export(cid: str):
        tmp = Path(tempfile.mkdtemp(prefix="dropnet-case-")) / f"{re.sub(r'[^A-Z0-9-]', '', cid)}.rl"
        try:
            run_ftc(ftc_whatif.export_case, cid, tmp)
        except KeyError:
            shutil.rmtree(tmp.parent, ignore_errors=True)
            raise HTTPException(404, "unknown campaign")
        except Exception:
            shutil.rmtree(tmp.parent, ignore_errors=True)
            raise
        data = tmp.read_bytes()  # small (~1 MB): serve from memory so nothing is left on disk
        shutil.rmtree(tmp.parent, ignore_errors=True)
        return Response(data, media_type="application/octet-stream",
                        headers={"content-disposition": f'attachment; filename="{tmp.name}"'})

    @app.get("/api/ftc/search")
    def ftc_search(q: str = "", mode: str = "hybrid", state: str | None = None, limit: int = 10):
        from ..ftc import semantic
        if mode == "subjects":  # the original scam-type lookup through the Subject full-text index
            return run_ftc(ftc_api.search_pools, q[:200])
        if mode not in ("hybrid", "fulltext", "vector"):
            raise HTTPException(400, "mode must be hybrid, fulltext, vector or subjects")
        return run_ftc(lambda c: semantic.search(c, q[:200], limit=max(1, min(int(limit), 50)), mode=mode, state=state))

    @app.get("/api/ftc/networks")
    def ftc_networks():
        return run_ftc(ftc_api.networks)

    @app.get("/api/ftc/carriers")
    def ftc_carriers(limit: int = 25):
        return run_ftc(ftc_api.dispatch_ftc, "carriers", {"limit": max(1, min(int(limit), 200))})

    @app.get("/api/ftc/carriers/{name}")
    def ftc_carrier(name: str):
        return run_ftc(ftc_api.dispatch_ftc, "carrier_detail", {"carrier": name})

    @app.get("/api/ftc/states")
    def ftc_states():
        return run_ftc(ftc_api.states)

    @app.get("/api/ftc/number/{number}")
    def ftc_number(number: str):
        try:
            return run_ftc(ftc_campaigns.assess_number, number)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/ftc/whatif")
    def ftc_whatif_route(body: WhatIfIn):
        try:
            return run_ftc(ftc_whatif.whatif, blocks=body.blocks, numbers=body.numbers, since_day=body.since_day)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/health")
    def health():
        return {"ok": True, "graph": ftc_snapshot.name, "loaded": "ftc" in state, "data": "FTC Do Not Call reports",
                "synthetic": False}

    @app.post("/api/tools/{name}")
    def tool(name: str, args: dict[str, Any] = Body(default_factory=dict)):
        if name not in ftc_api.FTC_TOOL_NAMES:
            raise HTTPException(404, f"unknown tool {name}")
        try:
            return run_ftc(ftc_api.dispatch_ftc, name, args)
        except (KeyError, ValueError) as e:
            raise HTTPException(400, f"{type(e).__name__}: {e}")
        except Exception as e:  # Relate errors explain how to fix the query
            raise HTTPException(400, f"{type(e).__name__}: {e}")

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app
