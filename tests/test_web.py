import pytest
from fastapi.testclient import TestClient

from dropnet import pipeline
from dropnet.web.app import create_app


@pytest.fixture(scope="module")
def snap(tmp_path_factory):
    p = tmp_path_factory.mktemp("web") / "snap.rl"
    pipeline.build(p, seed=1, n=150)
    return p


@pytest.fixture
def client(snap, tmp_path):
    app = create_app(snapshot=snap, live=tmp_path / "live" / "live.rl", reset=True,
                     ftc_snapshot=tmp_path / "no-ftc.rl")
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health").json()
    assert r["ok"] is True and r["complaints"] == 150 and r["synthetic"] is True


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Dropnet" in r.text
    assert "FTC complaint data" in r.text
    assert 'data-tab="ingest"' not in r.text and 'data-tab="inbox"' not in r.text


def test_campaigns_and_graph(client):
    camps = client.get("/api/campaigns").json()
    assert len(camps) == 7
    g = client.get(f"/api/campaigns/{camps[0]['id']}/graph").json()
    assert g["nodes"] and g["edges"]
    assert client.get("/api/campaigns/CAMP-9999/graph").status_code == 404


def test_complaints_page(client):
    r = client.get("/api/complaints?limit=5&offset=0").json()
    assert r["total"] == 150 and len(r["items"]) == 5
    assert client.get("/api/complaints/CMP-0001").json()["id"] == "CMP-0001"
    assert client.get("/api/complaints/CMP-9999").status_code == 404


def test_case_endpoints(client):
    cid = client.get("/api/campaigns").json()[0]["id"]
    html = client.get(f"/api/campaigns/{cid}/case.html")
    assert html.status_code == 200 and "Evidence paths" in html.text
    md = client.get(f"/api/campaigns/{cid}/case.md")
    assert md.status_code == 200 and md.text.startswith("# Case file")


def test_samples_then_ingest(client):
    samples = client.get("/api/samples").json()
    assert len(samples) >= 3 and all(s["text"] for s in samples)
    statuses = set()
    for s in samples:
        r = client.post("/api/ingest", json={"text": s["text"], "region": "Pavlodar"})
        assert r.status_code == 200
        statuses.add(r.json()["status"])
    assert {"attached", "unlinked"} <= statuses
    assert client.get("/api/health").json()["complaints"] == 150 + len(samples)


def test_samples_use_only_fictional_identifiers(client):
    import re
    for s in client.get("/api/samples").json():
        for m in re.finditer(r"(?<![\d*])(?:\+7|8)[ (]?(\d{3})\)?[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}(?![\d*])", s["text"]):
            assert m.group(1) == "799", s
        for m in re.finditer(r"(?<![\d*])(\d{4})[ -]?(\d{2})[\d*]{2}[ -]?[\d*]{4}[ -]?\d{4}(?![\d*])", s["text"]):
            assert m.group(1) + m.group(2) == "400000", s


def test_ingest_validation(client):
    assert client.post("/api/ingest", json={"text": "  "}).status_code == 400


def test_cypher_read_only(client):
    ok = client.post("/api/cypher", json={"statement": "MATCH (c:Complaint) RETURN count(c) AS n"})
    assert ok.json()["rows"][0]["n"] == 150
    bad = client.post("/api/cypher", json={"statement": "MATCH (n) DETACH DELETE n"})
    assert bad.status_code == 400


def test_tool_dispatch(client):
    r = client.post("/api/tools/find_campaign", json={"complaint_id": "CMP-0001"})
    assert r.status_code == 200 and "campaign" in r.json()
    assert client.post("/api/tools/drop_everything", json={}).status_code == 404


def test_explain(client):
    camps = client.get("/api/campaigns").json()
    members = client.get(f"/api/complaints?campaign={camps[0]['id']}&limit=2").json()["items"]
    r = client.get(f"/api/explain?a={members[0]['id']}&b={members[1]['id']}").json()
    assert r["found"] and r["path_text"]


def test_reset_restores_snapshot(snap, tmp_path):
    live = tmp_path / "l" / "live.rl"
    with TestClient(create_app(snapshot=snap, live=live, reset=True, ftc_snapshot=live.parent / "no-ftc.rl")) as c:
        c.post("/api/ingest", json={"text": "Перевела 10 000 тг на карту 4000 0012 3456 7890."})
    with TestClient(create_app(snapshot=snap, live=live, reset=False, ftc_snapshot=live.parent / "no-ftc.rl")) as c:
        assert c.get("/api/health").json()["complaints"] == 151
    with TestClient(create_app(snapshot=snap, live=live, reset=True, ftc_snapshot=live.parent / "no-ftc.rl")) as c:
        assert c.get("/api/health").json()["complaints"] == 150
