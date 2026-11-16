import json
import subprocess
import sys

from dropnet import evaluate, pipeline, store


def test_pairwise_perfect():
    truth = {"A": ["1", "2", "3"], "B": ["4", "5"]}
    assert evaluate.pairwise(truth, truth) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_pairwise_singletons_zero_recall():
    r = evaluate.pairwise({}, {"A": ["1", "2"]})
    assert r["recall"] == 0.0 and r["f1"] == 0.0


def test_pairwise_partial():
    r = evaluate.pairwise({"x": ["1", "2", "3", "4"]}, {"A": ["1", "2"], "B": ["3", "4"]})
    assert r["recall"] == 1.0 and abs(r["precision"] - 2 / 6) < 1e-9


def test_build_small(tmp_path):
    rep = pipeline.build(tmp_path / "b.rl", seed=3, n=120, raw_dir=tmp_path / "raw")
    assert rep.counts["Complaint"] == 120
    assert 5 <= len(rep.campaigns) <= 9
    assert rep.scores["f1"] > 0.8
    conn = store.open_store(tmp_path / "b.rl", read_only=True)
    assert store.rows(conn, "MATCH (k:Campaign) RETURN count(k) AS n")[0]["n"] == len(rep.campaigns)
    conn.close()
    assert json.loads((tmp_path / "raw" / "ground_truth.json").read_text(encoding="utf-8"))


def test_ablation_without_vectors_loses_script_campaign(tmp_path):
    full = pipeline.build(tmp_path / "f.rl", seed=3, n=120)
    novec = pipeline.build(tmp_path / "n.rl", seed=3, n=120, use_vectors=False)
    assert novec.scores["recall"] < full.scores["recall"]


def test_console_script_and_mcp_json():
    import json as _json
    import tomllib
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["dropnet"] == "dropnet.__main__:main"
    cfg = _json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["dropnet"]
    assert cfg["command"] == "dropnet" and cfg["args"] == ["mcp"]


def test_cli_eval_prints_table(tmp_path):
    out = subprocess.run([sys.executable, "-m", "dropnet", "eval", "--seeds", "2", "--n", "100"],
                         capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert out.returncode == 0, out.stderr
    assert "| seed |" in out.stdout and "F1" in out.stdout
