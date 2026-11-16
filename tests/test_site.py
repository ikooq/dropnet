import json

from dropnet import site
from tests.test_hook import make


def test_export_site_data(tmp_path):
    out = tmp_path / "graph.json"
    data = site.export(make(tmp_path), out, eval_path=tmp_path / "missing.json", top=10, per_pool=3)
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == data
    assert data["summary"]["reports"] == 31
    p = data["pools"][0]
    assert p["id"] == "POOL-866771" and len(p["nums"]) == 3
    assert p["numbers"] == 6  # the pool's total stays a number (stored as a node property in the browser)
    assert p["block"] == "866771"
    n = p["nums"][0]
    assert set(n) >= {"number", "reports", "states", "subjects"}
    assert data["profile"] and "neighbor_share" in data["profile"][0]
    assert data["eval"] is None


def test_site_files_exist():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "docs"
    html = (root / "index.html").read_text(encoding="utf-8")
    assert "@relate/relate-wasm@1.0.1/relate.js" in (root / "app.js").read_text(encoding="utf-8")
    assert "data/graph.json" in (root / "app.js").read_text(encoding="utf-8")
    assert "<title>" in html
