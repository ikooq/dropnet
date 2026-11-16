"""CLI commands that read or extend a built store: case, investigate, ingest, serve, mcp."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config


def _db_arg(p: argparse.ArgumentParser, default: Path = config.SNAPSHOT_PATH) -> None:
    p.add_argument("--db", default=str(default), help=f"Relate store (default: {default})")


def cmd_case(a: argparse.Namespace) -> int:
    from . import report, store
    conn = store.open_store(a.db, read_only=True)
    try:
        case = report.build_case(conn, a.campaign)
    except KeyError:
        print(f"Unknown campaign {a.campaign}")
        return 2
    finally:
        conn.close()
    text = report.to_html(case) if a.html else report.to_markdown(case)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"Wrote {a.out}")
    else:
        print(text)
    return 0


def cmd_investigate(a: argparse.Namespace) -> int:
    from . import report, store, tools
    conn = store.open_store(a.db, read_only=True)
    try:
        try:
            found = tools.find_campaign(conn, a.complaint)
        except KeyError:
            print(f"Unknown complaint {a.complaint}")
            return 2
        comp = found["complaint"]
        print(f"{comp['id']} · {comp['region']} · {comp['filed_at']} · {comp['amount_kzt']:,} KZT")
        print(f"  {comp['text_en']}\n")
        if not found["campaign"]:
            print("Not linked to any campaign. Closest scripts:")
            full = tools.get_complaint(conn, a.complaint)
            for h in tools.similar_scripts(conn, full["text"], k=4)[1:]:
                print(f"  {h['id']} score={h['score']} campaign={h['campaign']}")
            return 0
        print(f"Part of {found['campaign']['id']}:\n")
        print(report.to_markdown(report.build_case(conn, found["campaign"]["id"])))
    finally:
        conn.close()
    return 0


def register(sub) -> None:
    c = sub.add_parser("case", help="print the case file for a campaign")
    c.add_argument("campaign")
    c.add_argument("--html", action="store_true")
    c.add_argument("--out")
    _db_arg(c)
    c.set_defaults(fn=cmd_case)

    i = sub.add_parser("investigate", help="find the campaign behind a complaint and print its case file")
    i.add_argument("complaint")
    _db_arg(i)
    i.set_defaults(fn=cmd_investigate)

    try:
        from .cli_live import register as reg_live
    except ImportError:
        return
    reg_live(sub)
