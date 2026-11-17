import json

import pytest
from fastapi.testclient import TestClient

from dropnet import pipeline, store
from dropnet.ftc import campaigns, load
from dropnet.web.app import create_app
from tests.test_ftc_load import R


@pytest.fixture(scope="module")
def stores(tmp_path_factory):
    d = tmp_path_factory.mktemp("wf")
    pipeline.build(d / "snap.rl", seed=1, n=60)
    reports = [R(i, f"866771{i % 6:04d}", victim_npa="303", state="Colorado") for i in range(30)]
    reports += [R(100 + i, f"303555{i:04d}", victim_npa="303", subject="MEDICAL") for i in range(5)]
    conn = store.open_store(d / "ftc.rl")
    load.load_reports(conn, reports)
    campaigns.write_campaigns(conn, min_numbers=5)
    conn.close()
    (d / "eval.json").write_text(json.dumps({"baseline": {"coverage": 0.043}}), encoding="utf-8")
    return d


@pytest.fixture
def client(stores, tmp_path):
    app = create_app(snapshot=stores / "snap.rl", live=tmp_path / "live.rl", reset=True,
                     ftc_snapshot=stores / "ftc.rl", ftc_live=tmp_path / "ftc-live.rl", ftc_eval=stores / "eval.json")
    with TestClient(app) as c:
        yield c


def test_ftc_summary(client):
    s = client.get("/api/ftc/summary").json()
    assert s["reports"] == 35 and s["eval"]["baseline"]["coverage"] == 0.043
    assert {p["subject"] for p in s["profile"]} >= {"DEBT", "MEDICAL"}
    assert all("neighbor_share" in p and "label" in p for p in s["profile"])  # derived fields survive JSON
    st = client.get("/api/ftc/states").json()
    assert all("neighbor_share" in x for x in st)


def test_ftc_campaigns_graph_assess(client):
    camps = client.get("/api/ftc/campaigns").json()
    assert camps[0]["id"] == "POOL-866771"
    g = client.get("/api/ftc/campaigns/POOL-866771/graph").json()
    assert g["nodes"] and g["edges"]
    assert client.get("/api/ftc/campaigns/POOL-000000/graph").status_code == 404
    a = client.get("/api/ftc/number/(303) 555-0001").json()
    assert a["verdict"] == "likely_spoofed" and "not proof" in a["caution"]


def test_ftc_whatif_and_export(client):
    r = client.post("/api/ftc/whatif", json={"blocks": ["866771"]}).json()
    assert r["reports_stopped"] == 30 and r["campaigns_touched"] == ["POOL-866771"]
    assert client.post("/api/ftc/whatif", json={"blocks": ["8"]}).status_code == 400
    assert client.post("/api/ftc/whatif", json={"blocks": ["866771"]}).json()["reports_stopped"] == 30  # rolled back
    ex = client.get("/api/ftc/campaigns/POOL-866771/export")
    assert ex.status_code == 200 and len(ex.content) > 1000
    assert "attachment" in ex.headers["content-disposition"]
    import tempfile
    from pathlib import Path
    assert not list(Path(tempfile.gettempdir()).glob("dropnet-case-*/*.rl"))  # no leftovers after download
    assert client.get("/api/ftc/campaigns/POOL-000000/export").status_code == 404
    assert not list(Path(tempfile.gettempdir()).glob("dropnet-case-*"))


def test_ftc_tools_dispatch(client):
    r = client.post("/api/tools/assess_number", json={"number": "8667710001"})
    assert r.status_code == 200 and r.json()["verdict"] == "pool"
    r = client.post("/api/tools/ftc_campaigns", json={"limit": 1})
    assert r.json()[0]["id"] == "POOL-866771"


def test_ftc_absent_is_graceful(stores, tmp_path):
    app = create_app(snapshot=stores / "snap.rl", live=tmp_path / "l.rl", reset=True,
                     ftc_snapshot=tmp_path / "missing.rl", ftc_live=tmp_path / "fl.rl")
    with TestClient(app) as c:
        assert c.get("/api/ftc/summary").status_code == 404
        assert c.get("/api/health").json()["ok"] is True


def test_number_input_validation_and_unreported_range_context(client):
    assert client.get("/api/ftc/number/998667710002").status_code == 400
    result = client.get("/api/ftc/number/8667714444").json()
    assert result["reports"] == 0 and result["in_pool_range"]
