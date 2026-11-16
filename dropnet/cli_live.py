"""CLI commands that touch the live store: serve, ingest, mcp."""
from __future__ import annotations

import argparse
import json

from . import config


def cmd_serve(a: argparse.Namespace) -> int:
    import uvicorn

    from .web.app import create_app
    if not config.SNAPSHOT_PATH.exists():
        print(f"No snapshot at {config.SNAPSHOT_PATH}. Run: python -m dropnet build")
        return 2
    print(f"Dropnet → http://{a.host}:{a.port}  (live store: {config.LIVE_PATH}{', reset' if a.reset else ''})")
    uvicorn.run(create_app(reset=a.reset), host=a.host, port=a.port, log_level="warning")
    return 0


def cmd_ingest(a: argparse.Namespace) -> int:
    from . import ingest, store
    from .web.app import prepare_live
    prepare_live(config.SNAPSHOT_PATH, config.LIVE_PATH, reset=False)
    try:
        conn = store.open_store(config.LIVE_PATH)
    except Exception as e:  # the web server is the live store's writer
        print(f"Could not open the live store ({e}). If `dropnet serve` is running, use the web UI or POST /api/ingest.")
        return 2
    try:
        r = ingest.ingest_text(conn, a.text, region=a.region, amount_kzt=a.amount)
    except ValueError as e:
        print(e)
        return 2
    finally:
        conn.close()
    if a.json:
        print(json.dumps(r.to_json(), ensure_ascii=False, indent=2))
        return 0
    print(f"{r.complaint_id}: {r.status.upper()}" + (f" → {r.campaign_id}" if r.campaign_id else ""))
    if r.bridge_to:
        print(f"  also connects to {', '.join(r.bridge_to)}")
    if r.path_text:
        print(f"  evidence: {r.path_text}")
    for q in (r.evidence or {}).get("quotes", []):
        print(f"    «{q['quote']}» ({q['complaint']})")
    if r.status == "unlinked":
        for c in r.candidates[:3]:
            print(f"  closest script: {c['id']} score={c['score']} campaign={c['campaign']}")
    print(f"  extracted: {r.summary_en}")
    return 0


def cmd_mcp(a: argparse.Namespace) -> int:
    from .mcp_server import main
    return main()


def register(sub) -> None:
    s = sub.add_parser("serve", help="run the web UI + API on the live copy of the snapshot")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reset", action="store_true", help="start from a fresh copy of the snapshot")
    s.set_defaults(fn=cmd_serve)

    i = sub.add_parser("ingest", help="add one complaint (Russian text) to the live store and show its links")
    i.add_argument("text")
    i.add_argument("--region")
    i.add_argument("--amount", type=int)
    i.add_argument("--json", action="store_true")
    i.set_defaults(fn=cmd_ingest)

    m = sub.add_parser("mcp", help="MCP server over stdio (proxies to a running `serve`, else reads the snapshot)")
    m.set_defaults(fn=cmd_mcp)
