import json
import os
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from dropnet import store
from dropnet.ftc import campaigns, load, numbering
from dropnet.web.app import create_app
from tests.test_ftc_load import R


@pytest.fixture(scope="module")
def stores(tmp_path_factory):
    d = tmp_path_factory.mktemp("wf")
    reports = [R(i, f"866771{i % 6:04d}", victim_npa="303", state="Colorado") for i in range(30)]
    reports += [R(100 + i, f"303555{i:04d}", victim_npa="303", subject="MEDICAL") for i in range(5)]
    conn = store.open_store(d / "ftc.rl")
    load.load_reports(conn, reports)
    campaigns.write_campaigns(conn, min_numbers=5)
    store.rows(conn, """
        MATCH (b:Block {npa_nxx: '866771'})
        SET b.state = 'IL'
        CREATE (b)-[:HELD_BY]->(:Carrier {ocn: '0001'})-[:PART_OF]->
               (:CarrierGroup {name: 'Example & Telecom', codes_held: 8})
        CREATE (b)-[:IN_RATE_CENTER]->(:RateCenter {id: 'IL:EXAMPLE', name: 'EXAMPLE'})
    """)
    conn.close()
    (d / "eval.json").write_text(json.dumps({"baseline": {"coverage": 0.043}}), encoding="utf-8")
    return d


@pytest.fixture
def client(stores, tmp_path):
    app = create_app(reset=True,
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


def test_ftc_carrier_ranking_and_detail(client):
    assert "Who holds flagged ranges" in client.get("/").text
    ranking = client.get("/api/ftc/carriers", params={"limit": 15})
    assert ranking.status_code == 200
    result = ranking.json()
    assert result == {
        "carriers": [{"carrier": "Example & Telecom", "ranges_held": 8, "flagged": 1, "reports": 30,
                      "numbers": 6, "ocns": 1, "states": 1, "flagged_per_100_ranges": 12.5}],
        "caution": numbering.CAUTION,
    }
    name = quote(result["carriers"][0]["carrier"], safe="")
    detail = client.get(f"/api/ftc/carriers/{name}")
    assert detail.status_code == 200
    details = detail.json()
    assert details["caution"] == result["caution"]
    assert details["carrier"] == "Example & Telecom"
    assert details["subjects"] == [{"subject": "DEBT", "reports": 30}]
    top = details["ranges"][0]
    assert (top["block"], top["rate_center"], top["state"]) == ("866771", "EXAMPLE", "IL")


def test_ftc_cypher_queries_the_ftc_store(client):
    response = client.post("/api/ftc/cypher", json={"statement": "MATCH (r:Report) RETURN count(r) AS reports"})
    assert response.status_code == 200
    assert response.json()["rows"] == [{"reports": 35}]
    assert client.get("/api/ftc/schema").status_code == 200


def test_ftc_snapshot_refreshes_an_older_live_copy(stores, tmp_path):
    old = tmp_path / "ftc-live.rl"
    with store.open_store(old) as conn:
        store.rows(conn, "CREATE (:Report {id: 'old'})")
    os.utime(old, (1_000_000_000, 1_000_000_000))
    app = create_app(ftc_snapshot=stores / "ftc.rl", ftc_live=old, ftc_eval=stores / "eval.json")
    with TestClient(app) as c:
        assert c.get("/api/ftc/summary").json()["reports"] == 35


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
    app = create_app(reset=True,
                     ftc_snapshot=tmp_path / "missing.rl", ftc_live=tmp_path / "fl.rl")
    with TestClient(app) as c:
        assert c.get("/api/ftc/summary").status_code == 404
        assert c.get("/api/health").json()["ok"] is True


def test_number_input_validation_and_unreported_range_context(client):
    assert client.get("/api/ftc/number/998667710002").status_code == 400
    result = client.get("/api/ftc/number/8667714444").json()
    assert result["reports"] == 0 and result["in_pool_range"]


def test_whatif_rejects_invalid_filing_date(client):
    response = client.post("/api/ftc/whatif", json={"blocks": ["866771"], "since_day": "2026-02-30"})
    assert response.status_code == 400
    assert "YYYY-MM-DD" in response.json()["detail"]
