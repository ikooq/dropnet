"""Check that the headline numbers in the README, EVIDENCE, the submission text and the diagram match the results.

Every number is derived from data/ftc/eval.json (the evaluation output); `check(graph=True)` also recounts reports in
data/ftc.rl. A claim is a regex whose groups capture numbers in the text: each capture must equal the value computed
from the data, and the headline claims must appear in every file that is listed for them.

    python -m dropnet check-claims [--graph]
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config
from .numfmt import pct_number

FILES = {"README": "README.md", "EVIDENCE": "docs/EVIDENCE.md", "devpost": "docs/devpost.md",
         "index": "docs/index.html", "diagram": "docs/img/architecture.svg"}
WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine"}

# (name, regex, value names for its groups, files where it must appear)
CLAIMS: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = [
    ("reports", r"\b(29\d,\d{3})\b", ("reports",), ("README", "EVIDENCE", "devpost", "diagram")),
    ("numbers", r"\b(24\d,\d{3}) (?:phone )?numbers\b", ("numbers",), ("README", "devpost")),
    ("test reports", r"\b(10\d,\d{3}) (?:later )?complaints\b", ("test_reports",), ("README", "EVIDENCE", "devpost")),
    # hold-out: numbers only -> numbers + ranges
    ("hold-out (README)", r"\*\*(\d+\.\d)%\*\* of the [\d,]+ later complaints.*?\*\*(\d+\.\d)%\*\*",
     ("base", "geo"), ("README",)),
    ("hold-out (EVIDENCE)", r"Hold-out: (\d+\.\d)% → (\d+\.\d)% \((\d+\.\d)% with toll-free\)",
     ("base", "geo", "all"), ("EVIDENCE",)),
    ("hold-out (devpost table)", r"complaints filed after \| (\d+\.\d)% \| \*\*(\d+\.\d)%\*\*", ("base", "geo"),
     ("devpost",)),
    ("hold-out (diagram)", r"hold-out: (\d+\.\d) % numbers → (\d+\.\d) % with ranges", ("base", "geo"), ("diagram",)),
    # equal budget: Dropnet's ranking vs ranking by distinct numbers
    ("equal budget (EVIDENCE)", r"Dropnet (\d+\.\d\d)%, naive (\d+\.\d\d)%", ("geo2", "naive2"), ("EVIDENCE",)),
    ("equal budget (EVIDENCE table)", r"naive geographic prefixes \| [\d,]+ \| (\d+\.\d\d)%", ("naive2",),
     ("EVIDENCE",)),
    ("equal budget (devpost)", r"reported matched (\d+\.\d\d)%, against Dropnet's (\d+\.\d\d)%", ("naive2", "geo2"),
     ("devpost",)),
    ("equal budget (README)", r"matched \*\*(\d+\.\d)%\*\* and ours \*\*(\d+\.\d)%\*\*", ("naive", "geo"),
     ("README",)),
    ("equal budget (diagram)", r"naive range ranking: (\d+\.\d) %", ("naive",), ("diagram",)),
    # holders
    ("holders 20+ per 100", r"\b(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|one|two|three|four|five|six|seven|"
     r"eight|nine) of the 15 (?:holders|largest holders)", ("holders_20",), ("README", "devpost")),
    ("holders (diagram)", r"holders: (\d) of top 15 at ≥20 flagged per 100", ("holders_20_int",), ("diagram",)),
    ("holder prior", r"flagged later (\d+\.\d)% (?:of the time, against|vs) (\d+\.\d)%[^(]{0,40}\((\d+\.\d)×",
     ("prior_leader", "prior_other", "prior_lift"), ("EVIDENCE", "devpost")),
    ("holder prior (prose)", r"(\d+\.\d)% of those become flagged again[^.]*?(\d+\.\d)% of the other",
     ("prior_leader", "prior_other"), ()),
    ("holder prior (README)", r"flagged later (\d+\.\d) times as often", ("prior_lift",), ("README",)),
    ("holder prior (diagram)", r"flagged later: (\d+\.\d)×", ("prior_lift",), ("diagram",)),
    # FCC
    ("FCC", r"\b(\d+) of (?:the )?(\d+) (?:largest|top) ranges", ("fcc_confirmed", "fcc_checked"),
     ("EVIDENCE", "diagram")),
]


def pct(x: float, digits: int = 1) -> str:
    return pct_number(x, digits)


def expected(ev: dict) -> dict[str, str]:
    cp, carriers = ev["carrier_prior"], ev["carriers"]
    n20 = sum(1 for c in carriers[:15] if c["flagged_per_100_ranges"] >= 20)
    return {
        "reports": f"{ev['stats']['reports']:,}", "numbers": f"{ev['stats']['numbers']:,}",
        "test_reports": f"{ev['test_reports']:,}",
        "base": pct(ev["baseline"]["coverage"]), "geo": pct(ev["dropnet_geographic"]["coverage"]),
        "all": pct(ev["dropnet"]["coverage"]),
        "geo2": pct(ev["dropnet_geographic"]["coverage"], 2), "naive2": pct(ev["naive_geographic"]["coverage"], 2),
        "naive": pct(ev["naive_geographic"]["coverage"]),
        "holders_20": WORDS[n20], "holders_20_int": str(n20),
        "prior_leader": pct(cp["leader_flagged_later"]), "prior_other": pct(cp["other_flagged_later"]),
        "prior_lift": f"{cp['lift']:.1f}",
        "fcc_confirmed": str(ev["fcc_crosscheck"]["pools_confirmed"]),
        "fcc_checked": str(ev["fcc_crosscheck"]["pools_checked"]),
    }


# rows of the `ftc-eval` table, in print order, and the result each row prints
CLI_ROWS = ("blocklist_all_seen", "baseline", "dropnet_geographic", "naive_geographic", "dropnet")


def cli_vs_browser(ev: dict, demo: dict) -> list[str]:
    """`python -m dropnet ftc-eval` must print the shares the browser shows from docs/data/graph.json."""
    import contextlib
    import io
    from .cli_live import _print_eval
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        _print_eval(ev)
    printed = re.findall(r"^\|[^|\n]+\|[^|\n]+\| (\d+\.\d)% \|$", out.getvalue(), re.M)
    if len(printed) != len(CLI_ROWS):
        return [f"ftc-eval printed {len(printed)} share rows, expected {len(CLI_ROWS)}"]
    problems = []
    for part, cli in zip(CLI_ROWS, printed):
        browser = pct(demo["eval"][part]["coverage"])  # what the page's toFixed(1) shows
        if cli != browser:
            problems.append(f"ftc-eval prints {cli}% for {part}; the browser shows {browser}%")
    return problems


def check(root: Path | str = config.ROOT, graph: bool = False) -> list[str]:
    """Return a list of problems; empty means every claim matches the data."""
    root = Path(root)
    ev = json.loads((root / "data" / "ftc" / "eval.json").read_text(encoding="utf-8"))
    want = expected(ev)
    texts = {k: (root / f).read_text(encoding="utf-8") for k, f in FILES.items()}
    problems = []
    for name, rx, groups, required in CLAIMS:
        pattern = re.compile(rx, re.S)
        for key, text in texts.items():
            hits = list(pattern.finditer(text.replace("\n", " ")))  # same offsets; wrapped lines still match
            if key in required and not hits:
                problems.append(f"{FILES[key]}: missing '{name}'")
            for m in hits:
                for g, value in zip(groups, m.groups()):
                    if value.capitalize() != want[g].capitalize():
                        line = text.count("\n", 0, m.start()) + 1
                        problems.append(f"{FILES[key]}:{line}: '{name}' says {value}, data says {want[g]}")
    # the browser demo reads its own copies of the results
    demo = json.loads((root / "docs" / "data" / "graph.json").read_text(encoding="utf-8"))
    if demo["summary"]["reports"] != ev["stats"]["reports"]:
        problems.append(f"docs/data/graph.json: {demo['summary']['reports']} reports, eval.json "
                        f"{ev['stats']['reports']}")
    for part in ("baseline", "dropnet_geographic", "naive_geographic", "dropnet"):
        if demo["eval"].get(part, {}).get("coverage") != ev[part]["coverage"]:
            problems.append(f"docs/data/graph.json: eval.{part}.coverage differs from data/ftc/eval.json")
    problems += cli_vs_browser(ev, demo)
    # EVIDENCE's holder table, one row per start day and number of leaders
    splits = {(s["split_day"], str(s["top"])): (pct(s["leader_flagged_later"]), pct(s["other_flagged_later"]),
                                                 f"{s['lift']:.1f}") for s in ev.get("carrier_prior_splits", [])}
    rows_seen = 0
    for m in re.finditer(r"^\| (2026-\d\d-\d\d) \| (\d+) \| (\d+\.\d)% \| (\d+\.\d)% \| (\d+\.\d)× \|$",
                         texts["EVIDENCE"], re.M):
        rows_seen += 1
        want_row = splits.get((m[1], m[2]))
        if want_row != (m[3], m[4], m[5]):
            line = texts["EVIDENCE"].count("\n", 0, m.start()) + 1
            problems.append(f"docs/EVIDENCE.md:{line}: holder split {m[1]}/{m[2]} says {m[3]}%, {m[4]}%, {m[5]}×; "
                            f"data says {want_row}")
    if rows_seen != len(splits):
        problems.append(f"docs/EVIDENCE.md: holder table has {rows_seen} rows, eval.json {len(splits)} splits")
    demo_carriers = json.loads((root / "docs" / "data" / "carriers.json").read_text(encoding="utf-8"))["carriers"]
    if demo_carriers[:15] != ev["carriers"][:15]:
        problems.append("docs/data/carriers.json: top 15 holders differ from data/ftc/eval.json")
    if graph:
        from . import store
        conn = store.open_store(root / "data" / "ftc.rl", read_only=True)
        try:
            n = store.rows(conn, "MATCH (r:Report) RETURN count(r) AS n")[0]["n"]
        finally:
            conn.close()
        if n != ev["stats"]["reports"]:
            problems.append(f"data/ftc.rl: {n:,} reports, eval.json {ev['stats']['reports']:,}")
    return problems


def main(graph: bool = False) -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    problems = check(graph=graph)
    for p in problems:
        print(p)
    print("claims: OK" if not problems else f"claims: {len(problems)} problem(s)")
    return 1 if problems else 0
