"""Dropnet command line: python -m dropnet <command>."""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import config


def _utf8_stdout() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def cmd_build(a: argparse.Namespace) -> int:
    from .pipeline import build
    rep = build(a.out, seed=a.seed, n=a.n, hard=a.hard, raw_dir=config.RAW_DIR if a.out == str(config.SNAPSHOT_PATH) else None)
    print(f"Built {rep.path} in {rep.seconds:.1f}s")
    print("Nodes: " + ", ".join(f"{k}={v}" for k, v in sorted(rep.counts.items())))
    print(f"Campaigns: {len(rep.campaigns)}  (similar-script edges: {rep.similar_edges})")
    for c in rep.campaigns:
        print(f"  {c.id}: {c.size} complaints, {len(c.regions)} regions, {c.damage_kzt:,} KZT, "
              f"{', '.join(c.tactics[:2])}, confidence {c.confidence}")
    print(f"Pairwise vs ground truth: P={rep.scores['precision']:.3f} R={rep.scores['recall']:.3f} "
          f"F1={rep.scores['f1']:.3f}")
    return 0


def cmd_eval(a: argparse.Namespace) -> int:
    from .pipeline import build
    variants = [("default", {})]
    if a.hard:
        variants.append(("hard", {"hard": True}))
    if a.ablations:
        variants += [("no vectors", {"use_vectors": False}), ("no forwarding", {"use_forwarding": False}),
                     ("no hub filter", {"use_hub_filter": False})]
    print("| seed | variant | campaigns | precision | recall | F1 |")
    print("|---:|---|---:|---:|---:|---:|")
    totals: dict[str, list[float]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for seed in a.seeds:
            for name, kw in variants:
                rep = build(Path(tmp) / f"e{seed}-{name.replace(' ', '_')}.rl", seed=seed, n=a.n, **kw)
                s = rep.scores
                totals.setdefault(name, []).append(s["f1"])
                print(f"| {seed} | {name} | {len(rep.campaigns)} | {s['precision']:.3f} | {s['recall']:.3f} "
                      f"| {s['f1']:.3f} |")
    for name, f1s in totals.items():
        print(f"\nMean F1 ({name}): {sum(f1s) / len(f1s):.3f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    p = argparse.ArgumentParser(prog="dropnet", description="Scattered fraud complaints -> one connected case.")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="generate synthetic data and (re)build the Relate snapshot")
    b.add_argument("--seed", type=int, default=1)
    b.add_argument("--n", type=int, default=250)
    b.add_argument("--hard", action="store_true")
    b.add_argument("--out", default=str(config.SNAPSHOT_PATH))
    b.set_defaults(fn=cmd_build)

    e = sub.add_parser("eval", help="linking quality vs ground truth on held-out seeds")
    e.add_argument("--seeds", type=int, nargs="+", default=[2, 3, 4, 5])
    e.add_argument("--n", type=int, default=250)
    e.add_argument("--hard", action="store_true")
    e.add_argument("--ablations", action="store_true")
    e.set_defaults(fn=cmd_eval)

    _register_more(sub)
    a = p.parse_args(argv)
    return a.fn(a)


def _register_more(sub) -> None:
    """Commands added by later modules (serve, ingest, case, investigate, mcp)."""
    try:
        from .cli_more import register
    except ImportError:
        return
    register(sub)


if __name__ == "__main__":
    raise SystemExit(main())
