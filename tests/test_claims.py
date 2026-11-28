import json
import shutil
from pathlib import Path

from dropnet import claims

ROOT = Path(__file__).resolve().parent.parent


def test_published_numbers_match_the_results():
    assert claims.check(ROOT) == []


def copy_project(tmp_path):
    for rel in [*claims.FILES.values(), "data/ftc/eval.json", "docs/data/graph.json", "docs/data/carriers.json"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    return tmp_path


def test_a_changed_number_in_the_text_is_reported(tmp_path):
    root = copy_project(tmp_path)
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace("**14.3%**", "**15.3%**", 1), encoding="utf-8")
    problems = claims.check(root)
    assert any("README.md" in p and "says 15.3, data says 14.3" in p for p in problems)


def test_a_new_result_flags_every_stale_text(tmp_path):
    root = copy_project(tmp_path)
    ev_path = root / "data" / "ftc" / "eval.json"
    ev = json.loads(ev_path.read_text(encoding="utf-8"))
    ev["carrier_prior"]["lift"] = 3.9
    ev_path.write_text(json.dumps(ev), encoding="utf-8")
    stale = {p.split(":")[0] for p in claims.check(root) if "data says 3.9" in p}
    assert stale == {"README.md", "docs/EVIDENCE.md", "docs/devpost.md", "docs/img/architecture.svg"}


def test_a_missing_honest_comparison_is_reported(tmp_path):
    root = copy_project(tmp_path)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    start = text.index("The gain comes from watching ranges")
    readme.write_text(text[:start] + text[text.index("What Dropnet adds is the graph"):], encoding="utf-8")
    assert "README.md: missing 'equal budget (README)'" in claims.check(root)


def test_percentages_round_like_the_browser():
    from dropnet.numfmt import pct
    assert pct(0.0625) == "6.3%"     # JS (6.25).toFixed(1); Python's format gave 6.2%
    assert pct(0.0205) == "2.1%"     # 2.0500000000000003
    assert pct(0.1431) == "14.3%" and pct(0.1452) == "14.5%" and pct(0.0434) == "4.3%"
    assert pct(0.368, 0) == "37%" and pct(0.005, 0) == "1%"


def test_ftc_eval_prints_what_the_browser_shows():
    ev = json.loads((ROOT / "data/ftc/eval.json").read_text(encoding="utf-8"))
    demo = json.loads((ROOT / "docs/data/graph.json").read_text(encoding="utf-8"))
    assert claims.cli_vs_browser(ev, demo) == []
    demo["eval"]["blocklist_all_seen"]["coverage"] = 0.0675
    assert claims.cli_vs_browser(ev, demo) == ["ftc-eval prints 6.3% for blocklist_all_seen; the browser shows 6.8%"]
