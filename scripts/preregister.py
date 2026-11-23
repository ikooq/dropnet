"""Pre-registered forward test of Dropnet's range rule.

freeze: learn the number list and the ranges from every FTC file published so far and write them, with hashes,
        to docs/prediction/. The git commit that adds them is the timestamp.
check:  score those frozen lists, unchanged, on FTC files published after the freeze.

    python scripts/preregister.py freeze --out docs/prediction data/ftc/raw data/ftc/fresh-2026-11-18 data/ftc/fresh-2026-11-23
    python scripts/preregister.py check --prediction docs/prediction --test-dir data/ftc/after-freeze
"""
import argparse
import gzip
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

from dropnet.ftc.parse import TOLL_FREE, read_reports
from dropnet.ftc.robustness import _numbers, pools

MIN_NUMBERS = 5   # a range needs at least 5 distinct reported numbers, the same rule as every earlier test
MIN_REPORTS = 2   # the baseline blocks numbers reported at least twice


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_day(path: Path) -> str:
    return path.name.split("_")[-1][:10]


def _reports(paths):
    seen, out = set(), []
    for r in read_reports(paths):
        if r.id not in seen:
            seen.add(r.id)
            out.append(r)
    return out


def freeze(dirs: list[Path], out: Path) -> dict:
    paths = sorted((p for d in dirs for p in d.glob("*.csv.gz")), key=_file_day)
    if len({p.name for p in paths}) != len(paths):
        raise SystemExit("The same FTC file appears in two folders")
    reports = _reports(paths)
    obs = [(r.number, r.number[:6], r.created_day, r.neighbor) for r in reports]
    numbers = _numbers(obs, MIN_REPORTS)
    blocks = pools(obs, MIN_NUMBERS)
    out.mkdir(parents=True, exist_ok=True)
    (out / "numbers.txt").write_text("".join(n + "\n" for n in sorted(numbers)), encoding="utf-8", newline="\n")
    (out / "ranges.txt").write_text(
        "".join(f"{b}\t{'toll-free' if b[:3] in TOLL_FREE else 'geographic'}\n" for b in sorted(blocks)),
        encoding="utf-8", newline="\n")
    seen = "".join(n + "\n" for n in sorted({r.number for r in reports})).encode()
    (out / "seen_numbers.txt.gz").write_bytes(gzip.compress(seen, mtime=0))
    manifest = {
        "frozen_on": date.today().isoformat(),
        "rule": {"min_distinct_numbers_per_range": MIN_NUMBERS, "baseline_min_reports_per_number": MIN_REPORTS,
                 "ranges_built_from": "reports whose caller area code differs from the consumer's"},
        "training": {"files": len(paths), "first_file": _file_day(paths[0]), "last_file": _file_day(paths[-1]),
                     "reports": len(reports), "last_filing_day": max(r.created_day for r in reports),
                     "distinct_numbers": len({r.number for r in reports})},
        "frozen": {"numbers": len(numbers), "ranges": len(blocks),
                   "geographic_ranges": sum(b[:3] not in TOLL_FREE for b in blocks),
                   "numbers_sha256": _sha(out / "numbers.txt"), "ranges_sha256": _sha(out / "ranges.txt"),
                   "seen_numbers_sha256": _sha(out / "seen_numbers.txt.gz")},
        "training_files_sha256": {p.name: hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest() for p in paths},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def _load(pred: Path):
    m = json.loads((pred / "manifest.json").read_text(encoding="utf-8"))
    for name, file in (("numbers", "numbers.txt"), ("ranges", "ranges.txt"), ("seen_numbers", "seen_numbers.txt.gz")):
        if _sha(pred / file) != m["frozen"][f"{name}_sha256"]:
            raise SystemExit(f"{file} changed since it was frozen")
    numbers = set((pred / "numbers.txt").read_text(encoding="utf-8").split())
    seen = set(gzip.decompress((pred / "seen_numbers.txt.gz").read_bytes()).decode().split())
    rows = [line.split("\t") for line in (pred / "ranges.txt").read_text(encoding="utf-8").splitlines()]
    return m, numbers, {b for b, _ in rows}, {b for b, kind in rows if kind == "geographic"}, seen


def score(records, numbers, geo, every, known_numbers=frozenset()):
    def hit(r, blocks):
        return r.number in numbers or r.number[:6] in blocks
    total = len(records)
    hits = {"numbers_only": sum(hit(r, set()) for r in records),
            "numbers_and_geographic_ranges": sum(hit(r, geo) for r in records),
            "numbers_and_all_ranges": sum(hit(r, every) for r in records)}
    unseen = [r for r in records if r.number not in known_numbers]
    return {"complaints": total, "hits": hits,
            "shares": {k: round(v / total, 4) if total else None for k, v in hits.items()},
            "lift_geographic": round(hits["numbers_and_geographic_ranges"] / hits["numbers_only"], 2)
            if hits["numbers_only"] else None,
            "never_seen_numbers": {"complaints": len(unseen),
                                   "in_a_frozen_geographic_range": sum(r.number[:6] in geo for r in unseen)}}


def check(pred: Path, test_dir: Path) -> dict:
    m, numbers, every, geo, known = _load(pred)
    last_file, last_day = m["training"]["last_file"], m["training"]["last_filing_day"]
    paths = sorted((p for p in test_dir.glob("*.csv.gz") if _file_day(p) > last_file), key=_file_day)
    if not paths:
        raise SystemExit(f"No FTC files published after {last_file} in {test_dir}")
    later = [r for r in _reports(paths) if r.created_day > last_day]
    calls = []
    for r in later:
        try:
            filed, called = date.fromisoformat(r.created_day), date.fromisoformat(r.violation_day)
        except ValueError:
            continue
        if called.isoformat() > last_day and called <= filed:
            calls.append(r)
    return {"prediction_frozen_on": m["frozen_on"], "test_files": [p.name for p in paths],
            "test_filing_days": dict(sorted(Counter(r.created_day for r in later).items())),
            "filed_after_freeze": score(later, numbers, geo, every, known),
            "called_after_freeze": score(calls, numbers, geo, every, known),
            "test_files_sha256": {p.name: hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest() for p in paths}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze"); f.add_argument("dirs", nargs="+", type=Path); f.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("check"); c.add_argument("--prediction", type=Path, required=True); c.add_argument("--test-dir", type=Path, required=True)
    a = ap.parse_args()
    result = freeze(a.dirs, a.out) if a.cmd == "freeze" else check(a.prediction, a.test_dir)
    print(json.dumps({k: v for k, v in result.items() if not k.endswith("sha256")}, indent=2))
