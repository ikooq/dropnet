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
    assert set(n) >= {"number", "reports", "states", "subjects", "verdict"}
    spoofed = [x for x in data["pools"][0]["nums"] if x["number"] == "3035550001"]
    assert not spoofed or spoofed[0]["verdict"] == "likely_spoofed"


def test_export_marks_spoofed_numbers(tmp_path):
    from dropnet import store
    from dropnet.ftc import campaigns, load
    from tests.test_ftc_load import R
    p = tmp_path / "s.rl"
    c = store.open_store(p)
    load.load_reports(c, [R(i, f"866771{i % 6:04d}", victim_npa="303") for i in range(30)]
                      + [R(99, "8667719999", victim_npa="866")])  # one spoofed-local call inside the pool block
    campaigns.write_campaigns(c, min_numbers=5)
    c.close()
    data = site.export(p, tmp_path / "g.json", eval_path=tmp_path / "x.json")
    v = {n["number"]: n["verdict"] for n in data["pools"][0]["nums"]}
    assert v["8667719999"] == "likely_spoofed" and v["8667710001"] == "pool"
    assert data["profile"] and "neighbor_share" in data["profile"][0]
    assert data["eval"] is None
    assert data["networks"] == []  # no pool network in this tiny fixture, but the key is always there


def test_site_files_exist():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "docs"
    html = (root / "index.html").read_text(encoding="utf-8")
    assert "@relate/relate-wasm@1.0.1/relate.js" in (root / "app.js").read_text(encoding="utf-8")
    assert "data/graph.json" in (root / "app.js").read_text(encoding="utf-8")
    assert "<title>" in html
