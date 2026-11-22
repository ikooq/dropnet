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


def cmd_ftc_build(a: argparse.Namespace) -> int:
    from .ftc import build, fetch
    if a.fetch:
        paths = fetch.fetch(build.FTC_RAW)
        print(f"{len(paths)} FTC daily files in {build.FTC_RAW}")
    r = build.build()
    _print_eval(r)
    return 0


def _print_eval(r: dict) -> None:
    b, d, allseen = r["baseline"], r["dropnet"], r["blocklist_all_seen"]
    print(f"\nReal FTC reports: train before {r['split_day']} ({r['train_reports']:,}) · test after "
          f"({r['test_reports']:,})")
    print(f"| rules | count | later-filed reports matched |\n|---|---:|---:|")
    print(f"| every number ever reported | {allseen['rules']:,} | {allseen['coverage']:.1%} |")
    print(f"| blocklist: numbers with ≥2 reports | {b['rules']:,} | {b['coverage']:.1%} |")
    g = r.get("dropnet_geographic")
    if g:
        print(f"| Dropnet: + {g['block_rules']:,} geographic pool blocks | {g['rules']:,} | {g['coverage']:.1%} |")
    print(f"| Dropnet: + {d['block_rules']:,} pool blocks incl. toll-free | {d['rules']:,} | {d['coverage']:.1%} |")
    print(f"\n{d['new_numbers_caught']:,} matching reports involved numbers not previously reported. Potential scope: rules cover up to "
          f"{d.get('numbers_blocked', 0) / 1e6:.1f} M numbers (blocklist: {b.get('numbers_blocked', b['rules']):,}); "
          f"risk: {d['spoofed_caught']:,} matching reports had matching caller and consumer area codes; this is not proof of spoofing.")


def cmd_ftc_eval(a: argparse.Namespace) -> int:
    from . import store
    from .ftc import build, evaluate
    conn = store.open_store(build.FTC_STORE, read_only=True)
    try:
        days = [r["d"] for r in store.rows(conn, "MATCH (r:Report) RETURN DISTINCT r.day AS d")]
        _print_eval(evaluate.holdout(conn, a.split or build.split_day(days)))
    finally:
        conn.close()
    return 0


def cmd_hook(a: argparse.Namespace) -> int:
    from . import hook
    return hook.main(ftc_store=a.ftc)


def cmd_site(a: argparse.Namespace) -> int:
    from . import site
    d = site.export(top=a.top)
    print(f"Wrote {site.SITE_DATA} ({len(d['pools'])} pools). Serve docs/ (GitHub Pages: branch, /docs).")
    print(f"Wrote {site.LOOKUP}: {site.export_lookup()}")
    print(f"Wrote date-quality index: {site.export_date_quality()}")
    return 0


def cmd_agent_eval(a: argparse.Namespace) -> int:
    from . import store
    from .ftc import agent_eval, build
    conn = store.open_store(build.FTC_STORE, read_only=True)
    try:
        r = agent_eval.run(conn, n=a.n, seed=a.seed)
    finally:
        conn.close()
    k = r["sampled"]
    print(f"{k:,} sampled reported numbers: {r['naive_blames_likely_spoofed']:,} meet the area-code-match "
          f"heuristic; {r['naive_dismisses_pool_members']:,} are single-report numbers in a pool. "
          f"These categories are heuristics, not verified spoofing or ownership. Verdicts: {r['verdicts']}")
    return 0


def cmd_vault(a: argparse.Namespace) -> int:
    from . import config, store
    from .ftc import build, vault
    conn = store.open_store(build.FTC_STORE, read_only=True)
    try:
        r = vault.export(conn, a.out or config.DATA_DIR / "vault", top=a.top)
    finally:
        conn.close()
    print(f"{r['pools']} pools, {r['networks']} networks -> {r['path']}  "
          f"(open: relate --snapshot-format markdown --markdown-body-properties text --database {r['path']})")
    return 0


def cmd_carrier(a: argparse.Namespace) -> int:
    from . import config, store
    from .ftc import build, carrier, crosscheck
    fcc_files = sorted((config.DATA_DIR / "fcc").glob("*.json.gz"))
    fcc = crosscheck.fcc_blocks([r for p in fcc_files for r in crosscheck.read_fcc(p)])
    conn = store.open_store(build.FTC_STORE, read_only=True)
    try:
        n = carrier.export_csv(conn, a.out, fcc=fcc, top=a.top)
    finally:
        conn.close()
    print(f"{n:,} ranges -> {a.out}" + (f" (FCC cross-check from {len(fcc_files)} file(s))" if fcc_files else ""))
    return 0


def cmd_relate_ext(a) -> int:
    from . import relate_ext
    from .ftc import build
    cli = build.relate_cli()
    if not cli:
        print("Relate CLI not found — install it first (see README).")
        return 1
    print(relate_ext.install(cli))
    print("now: relate run dropnet-ftc --path data/ftc/raw -d ./ftc-graph")
    return 0


def cmd_robustness(a) -> int:
    import json
    from . import store
    from .ftc import build, robustness
    ev = json.loads(build.EVAL_JSON.read_text(encoding="utf-8"))
    conn = store.open_store(build.FTC_STORE, read_only=True)
    try:
        ev["robustness"] = robustness.run(conn, ev["split_day"])
    finally:
        conn.close()
    build.EVAL_JSON.write_text(json.dumps(ev, indent=2), encoding="utf-8")
    r = ev["robustness"]
    print(json.dumps({k: r[k] for k in ("rolling_summary", "bootstrap", "ablations")}, indent=2))
    for t in r["thresholds"]:
        print(t)
    return 0


def cmd_live_agent(a) -> int:
    import json
    from .ftc import live_agent_eval
    r = live_agent_eval.run(model=a.model, seed=a.seed)
    print(json.dumps(r["score"], indent=2))
    return 0


def cmd_early_warning(a) -> int:
    import json
    from . import store
    from .ftc import build, early_warning, robustness
    conn = store.open_store(build.FTC_STORE, read_only=True)
    try:
        reports = robustness.load(conn)
    finally:
        conn.close()
    res = early_warning.replay(reports)
    ev = json.loads(build.EVAL_JSON.read_text(encoding="utf-8"))
    ev["early_warning"] = res
    build.EVAL_JSON.write_text(json.dumps(ev, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


def register(sub) -> None:
    ew = sub.add_parser("ftc-early-warning", help="replay complaints day by day: how early do range rules fire?")
    ew.set_defaults(fn=cmd_early_warning)
    la = sub.add_parser("ftc-live-agent-eval", help="a real Claude Code agent, with and without Dropnet's MCP tool")
    la.add_argument("--model", default="haiku")
    la.add_argument("--seed", type=int, default=0)
    la.set_defaults(fn=cmd_live_agent)
    rb = sub.add_parser("ftc-robustness", help="rolling splits, bootstrap intervals, threshold sweep, ablations")
    rb.set_defaults(fn=cmd_robustness)
    rx = sub.add_parser("relate-ext", help="install Dropnet as a Relate extension: `relate run dropnet-ftc`")
    rx.set_defaults(fn=cmd_relate_ext)
    cc = sub.add_parser("carrier-csv", help="carrier-ready CSV of number ranges with evidence and the FCC cross-check")
    cc.add_argument("--out", default="data/ftc/ranges.csv")
    cc.add_argument("--top", type=int, default=None)
    cc.set_defaults(fn=cmd_carrier)
    vt = sub.add_parser("vault", help="export the top pools as a markdown vault Relate opens as a graph")
    vt.add_argument("--out")
    vt.add_argument("--top", type=int, default=50)
    vt.set_defaults(fn=cmd_vault)
    ae = sub.add_parser("ftc-agent-eval", help="naive agent vs Dropnet verdicts on random reported numbers")
    ae.add_argument("--n", type=int, default=1000)
    ae.add_argument("--seed", type=int, default=0)
    ae.set_defaults(fn=cmd_agent_eval)
    st = sub.add_parser("site", help="export the browser demo data (docs/data/graph.json) from data/ftc.rl")
    st.add_argument("--top", type=int, default=200)
    st.set_defaults(fn=cmd_site)
    hk = sub.add_parser("hook", help="Claude Code UserPromptSubmit hook: evidence + caution for phone numbers")
    hk.add_argument("--ftc", default=None, help="FTC store (default data/ftc.rl)")
    hk.set_defaults(fn=cmd_hook)
    fb = sub.add_parser("ftc-build", help="build data/ftc.rl from real FTC Do Not Call reports")
    fb.add_argument("--fetch", action="store_true", help="download the latest daily files from ftc.gov first")
    fb.set_defaults(fn=cmd_ftc_build)
    fe = sub.add_parser("ftc-eval", help="temporal hold-out: blocklist vs Dropnet pool rules on real reports")
    fe.add_argument("--split", help="first test day, YYYY-MM-DD (default: 70%% of the days)")
    fe.set_defaults(fn=cmd_ftc_eval)

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
