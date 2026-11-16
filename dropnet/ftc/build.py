"""Build data/ftc.rl from the FTC files: load -> campaigns -> compact single-file bundle -> evaluation report."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .. import config, store
from . import campaigns, evaluate, load, parse

FTC_RAW = config.DATA_DIR / "ftc" / "raw"
FTC_STORE = config.DATA_DIR / "ftc.rl"
EVAL_JSON = config.DATA_DIR / "ftc" / "eval.json"


def relate_cli() -> str | None:
    for cand in (shutil.which("relate"), str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "relate" / "relate.exe")):
        if cand and Path(cand).exists():
            return cand
    return None


def split_day(days: list[str], train_share: float = 0.7) -> str:
    """First test day: 70 % of the distinct report days are training."""
    days = sorted(set(days))
    return days[int(len(days) * train_share)]


def build(out: Path = FTC_STORE, raw: Path = FTC_RAW, eval_path: Path = EVAL_JSON, log=print) -> dict:
    t0 = time.perf_counter()
    reports = list(parse.read_reports(sorted(Path(raw).glob("*.csv*"))))
    log(f"parsed {len(reports):,} reports")
    work = Path(tempfile.mkdtemp(prefix="dropnet-ftc-")) / "graph"
    conn = store.open_store(work)
    try:
        stats = load.load_reports(conn, reports)
        load.ensure_fulltext(conn)
        log(f"loaded {stats} in {time.perf_counter() - t0:.0f}s")
        n = campaigns.write_campaigns(conn)
        log(f"wrote {n:,} campaigns")
        from . import networks
        log(f"pool networks: {networks.link_pools(conn)}")
        result = evaluate.holdout(conn, split_day([r.created_day for r in reports]))
        result["profile"] = campaigns.spoofing_profile(conn)
    finally:
        conn.close()
    out = Path(out)
    store.reset_store(out)
    cli = relate_cli()
    if cli:  # a compact Parquet bundle: ~40 MB instead of ~150 MB, fits a git repo
        subprocess.run([cli, "clone", str(work), str(out), "--to-snapshot-format", "parquet"], check=True,
                       env={**os.environ, "RELATE_TELEMETRY": "off"}, capture_output=True)
    else:
        out = out.with_suffix("")  # directory mode: same graph, no compaction without the Relate CLI
        log(f"Relate CLI not found: keeping the graph as a directory store at {out} (larger, ~100 MB).")
        shutil.rmtree(out, ignore_errors=True)
        shutil.copytree(work, out)
    shutil.rmtree(work.parent, ignore_errors=True)
    result.update({"stats": stats, "campaigns": n, "seconds": round(time.perf_counter() - t0, 1),
                   "store_mb": round(out.stat().st_size / 1e6, 1) if out.is_file() else None,
                   "first_day": min(r.created_day for r in reports), "last_day": max(r.created_day for r in reports)})
    eval_path = Path(eval_path)
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    eval_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
