"""FastAPI app: the analyst UI and a JSON API over one live Relate store.

The committed snapshot is never written. On start the app copies it to a live store
(data/live/dropnet.rl) and is that copy's only writer; MCP clients read through /api.
"""
from __future__ import annotations

import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import config, ingest, report, store, tools

STATIC = Path(__file__).parent / "static"


class IngestIn(BaseModel):
    text: str
    region: str | None = None
    amount_kzt: int | None = None


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
               reset: bool = False) -> FastAPI:
    snapshot, live = Path(snapshot), Path(live)
    state: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Relate connections are thread-affine: one dedicated thread owns the live store and runs every query.
        # That also makes it the store's only writer.
        prepare_live(snapshot, live, reset)
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="relate")
        state["pool"] = pool
        state["conn"] = pool.submit(store.open_store, live).result()
        try:
            yield
        finally:
            pool.submit(state.pop("conn").close).result()
            pool.shutdown(wait=True)

    app = FastAPI(title="Dropnet", lifespan=lifespan)

    def run(fn, *a, **kw):
        return state["pool"].submit(lambda: fn(state["conn"], *a, **kw)).result()

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

    TOOLS = {
        "get_schema": lambda c, a: tools.get_schema(c),
        "read_cypher": lambda c, a: tools.read_cypher(c, a["statement"], a.get("params")),
        "find_campaign": lambda c, a: tools.find_campaign(c, a["complaint_id"]),
        "explain_link": lambda c, a: {**(r := tools.explain_link(c, a["a"], a["b"])), "path_text": tools.render_path(r)},
        "top_mules": lambda c, a: tools.top_mules(c, a["campaign_id"], int(a.get("n", 5))),
        "similar_scripts": lambda c, a: tools.similar_scripts(c, a["text"], int(a.get("k", 5))),
        "build_case": lambda c, a: report.to_markdown(report.build_case(c, a["campaign_id"])),
        "list_campaigns": lambda c, a: tools.list_campaigns(c),
    }

    @app.post("/api/tools/{name}")
    def tool(name: str, args: dict[str, Any] = Body(default_factory=dict)):
        if name not in TOOLS:
            raise HTTPException(404, f"unknown tool {name}")
        try:
            return run(lambda c: TOOLS[name](c, args))
        except (KeyError, ValueError) as e:
            raise HTTPException(400, f"{type(e).__name__}: {e}")

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app
