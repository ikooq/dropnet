"""FastAPI app: the analyst UI and a JSON API over one live Relate store.

The committed snapshot is never written. On start the app copies it to a live store
(data/live/dropnet.rl) and is that copy's only writer; MCP clients read through /api.
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
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import config, ingest, report, store, tools

STATIC = Path(__file__).parent / "static"


class IngestIn(BaseModel):
    text: str
    region: str | None = None
    amount_kzt: int | None = None


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


def _with_fresh_identifiers(text: str, extractions: list[dict]) -> str:
    """Same words, brand-new (still fictional, +7 799 0… / 4000 00…) phone and card numbers."""
    import random

    from ..synth.generate import Ids, fmt_phone, mask
    rng = random.Random(len(text))
    ids = Ids(rng)
    for x in sorted(extractions, key=lambda x: -x["start"]):
        if x["kind"] == "phone":
            new = fmt_phone(ids.phone(), rng)
        elif x["kind"] == "card":
            new = mask(ids.card())
        else:
            continue
        text = text[:x["start"]] + new + text[x["end"]:]
    return text


def _samples(conn) -> list[dict]:
    camps = tools.list_campaigns(conn)
    out: list[dict] = []
    by_conf = sorted(camps, key=lambda c: (-c["confidence"], -c["size"]))
    strong = [c for c in by_conf if c["confidence"] == 1.0]
    mule = None
    for c in strong:
        accts = [a for a in tools.top_mules(conn, c["id"]) if a["role"] == "mule" and a["kind"] == "Card"]
        if accts:
            mule = (c, accts[0]["account"])
            break
    if mule:
        out.append({"label": "Known mule card", "expect": "attached",
                    "text": "Мне позвонили, представились службой безопасности банка, сказали, что на меня "
                            "оформляют кредит, и велели срочно перевести 120 000 тг на резервную карту "
                            f"{mule[1]}. Я перевела."})
    phone_camp = next((c for c in strong if mule and c["id"] != mule[0]["id"] and
                       tools.read_cypher(conn, "MATCH (:Complaint)-[:PART_OF]->(:Campaign {id: $id}) "
                                               "MATCH (x:Complaint)-[:PART_OF]->(:Campaign {id: $id}) "
                                               "MATCH (x)-[:CONTACTED_BY]->(p:Phone) WHERE NOT coalesce(p.hub,false) "
                                               "WITH p, count(DISTINCT x) AS n WHERE n > 1 RETURN p.e164 AS p LIMIT 1",
                                         {"id": c["id"]})["rows"]), None)
    if mule and phone_camp:
        phone = tools.read_cypher(conn, "MATCH (x:Complaint)-[:PART_OF]->(:Campaign {id: $id}) "
                                        "MATCH (x)-[:CONTACTED_BY]->(p:Phone) WHERE NOT coalesce(p.hub,false) "
                                        "WITH p, count(DISTINCT x) AS n WHERE n > 1 RETURN p.e164 AS p LIMIT 1",
                                  {"id": phone_camp["id"]})["rows"][0]["p"]
        out.append({"label": "Two gangs, one victim", "expect": "bridge",
                    "text": f"Сначала звонили с номера {phone}, потом прислали реквизиты и попросили перевести "
                            f"300 000 тг на карту {mule[1]}. Я перевёл."})
    script = next((c for c in camps if c["confidence"] < 1.0), None)
    if script:
        member = tools.list_complaints(conn, campaign=script["id"], limit=1)["items"][0]
        comp = tools.get_complaint(conn, member["id"])
        text = _with_fresh_identifiers(comp["text"], comp["extractions"])
        out.append({"label": "Same script, new numbers", "expect": "attached",
                    "text": text})
    out.append({"label": "Unrelated story", "expect": "unlinked",
                "text": "Написали в WhatsApp от имени дочери, попросили срочно помочь с оплатой, "
                        "я отправила 45 000 тенге через терминал."})
    return out


def create_app(snapshot: Path | str = config.SNAPSHOT_PATH, live: Path | str = config.LIVE_PATH,
               reset: bool = False, ftc_snapshot: Path | str = config.DATA_DIR / "ftc.rl",
               ftc_live: Path | str = config.DATA_DIR / "live" / "ftc.rl",
               ftc_eval: Path | str = config.DATA_DIR / "ftc" / "eval.json") -> FastAPI:
    snapshot, live = Path(snapshot), Path(live)
    ftc_snapshot, ftc_live, ftc_eval = Path(ftc_snapshot), Path(ftc_live), Path(ftc_eval)
    state: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Relate connections are thread-affine: one dedicated thread owns the live stores and runs every query.
        # That also makes it the stores' only writer.
        prepare_live(snapshot, live, reset)
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="relate")
        state["pool"] = pool
        state["conn"] = pool.submit(store.open_store, live).result()
        if ftc_snapshot.exists():
            prepare_live(ftc_snapshot, ftc_live, reset)
            state["ftc"] = pool.submit(store.open_store, ftc_live).result()
        try:
            yield
        finally:
            for key in ("conn", "ftc"):
                if key in state:
                    pool.submit(state.pop(key).close).result()
            pool.shutdown(wait=True)

    app = FastAPI(title="Dropnet", lifespan=lifespan)

    def run(fn, *a, **kw):
        return state["pool"].submit(lambda: fn(state["conn"], *a, **kw)).result()

    def run_ftc(fn, *a, **kw):
        if "ftc" not in state:
            raise HTTPException(404, "FTC data not built: run `python -m dropnet ftc-build`")
        return state["pool"].submit(lambda: fn(state["ftc"], *a, **kw)).result()

    from ..ftc import api as ftc_api, campaigns as ftc_campaigns, whatif as ftc_whatif

    @app.get("/api/ftc/summary")
    def ftc_summary():
        s = run_ftc(ftc_api.summary)
        s["profile"] = run_ftc(ftc_campaigns.spoofing_profile)
        s["eval"] = json.loads(ftc_eval.read_text(encoding="utf-8")) if ftc_eval.exists() else None
        return s

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
    def ftc_search(q: str = ""):
        return run_ftc(ftc_api.search_pools, q[:200])

    @app.get("/api/ftc/networks")
    def ftc_networks():
        return run_ftc(ftc_api.networks)

    @app.get("/api/ftc/states")
    def ftc_states():
        return run_ftc(ftc_api.states)

    @app.get("/api/ftc/number/{number}")
    def ftc_number(number: str):
        return run_ftc(ftc_campaigns.assess_number, number)

    @app.post("/api/ftc/whatif")
    def ftc_whatif_route(body: WhatIfIn):
        try:
            return run_ftc(ftc_whatif.whatif, blocks=body.blocks, numbers=body.numbers, since_day=body.since_day)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/health")
    def health():
        n = run(lambda c: store.rows(c, "MATCH (x:Complaint) RETURN count(x) AS n")[0]["n"])
        k = run(lambda c: store.rows(c, "MATCH (x:Campaign) RETURN count(x) AS n, sum(x.damage_kzt) AS d")[0])
        return {"ok": True, "complaints": n, "campaigns": k["n"], "damage_kzt": k["d"] or 0,
                "synthetic": True, "store": str(live.name), "mode": "single file"}

    @app.get("/api/schema")
    def schema():
        return run(tools.get_schema)

    @app.get("/api/campaigns")
    def campaigns():
        return run(tools.list_campaigns)

    @app.get("/api/campaigns/{cid}/graph")
    def graph(cid: str):
        g = run(tools.campaign_graph, cid)
        if g["campaign"] is None:
            raise HTTPException(404, "unknown campaign")
        return g

    def _case(cid: str):
        try:
            return run(report.build_case, cid)
        except KeyError:
            raise HTTPException(404, "unknown campaign")

    @app.get("/api/campaigns/{cid}/case.html", response_class=HTMLResponse)
    def case_html(cid: str):
        return report.to_html(_case(cid))

    @app.get("/api/campaigns/{cid}/case.md", response_class=PlainTextResponse)
    def case_md(cid: str):
        return PlainTextResponse(report.to_markdown(_case(cid)), media_type="text/markdown; charset=utf-8")

    @app.get("/api/complaints")
    def complaints(limit: int = 50, offset: int = 0, campaign: str | None = None):
        return run(tools.list_complaints, limit=min(limit, 500), offset=offset, campaign=campaign)

    @app.get("/api/complaints/{cid}")
    def complaint(cid: str):
        c = run(tools.get_complaint, cid)
        if c is None:
            raise HTTPException(404, "unknown complaint")
        return c

    @app.get("/api/explain")
    def explain(a: str, b: str):
        r = run(tools.explain_link, a, b)
        r["path_text"] = tools.render_path(r)
        return r

    @app.get("/api/samples")
    def samples():
        return run(_samples)

    @app.post("/api/ingest")
    def do_ingest(body: IngestIn):
        try:
            return run(ingest.ingest_text, body.text, region=body.region, amount_kzt=body.amount_kzt).to_json()
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/cypher")
    def cypher(body: CypherIn):
        try:
            return run(tools.read_cypher, body.statement, body.params)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # Relate compile/runtime errors explain how to fix the query
            raise HTTPException(400, f"{type(e).__name__}: {e}")

    @app.post("/api/tools/{name}")
    def tool(name: str, args: dict[str, Any] = Body(default_factory=dict)):
        if name not in tools.TOOL_NAMES and name not in ftc_api.FTC_TOOL_NAMES:
            raise HTTPException(404, f"unknown tool {name}")
        try:
            if name in ftc_api.FTC_TOOL_NAMES:
                return run_ftc(ftc_api.dispatch_ftc, name, args)
            return run(tools.dispatch, name, args)
        except (KeyError, ValueError) as e:
            raise HTTPException(400, f"{type(e).__name__}: {e}")
        except Exception as e:  # Relate errors explain how to fix the query
            raise HTTPException(400, f"{type(e).__name__}: {e}")

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app
