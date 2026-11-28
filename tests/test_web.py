"""The app serves only the FTC graph: no synthetic store, no synthetic endpoints."""
import pytest
from fastapi.testclient import TestClient

from dropnet import store
from dropnet.ftc import campaigns, load
from dropnet.web.app import create_app
from tests.test_ftc_load import R


@pytest.fixture(scope="module")
def ftc(tmp_path_factory):
    p = tmp_path_factory.mktemp("web") / "ftc.rl"
    conn = store.open_store(p)
    load.load_reports(conn, [R(i, f"866771{i % 6:04d}", victim_npa="303") for i in range(30)])
    campaigns.write_campaigns(conn, min_numbers=5)
    conn.close()
    return p


@pytest.fixture
def client(ftc, tmp_path):
    with TestClient(create_app(reset=True, ftc_snapshot=ftc, ftc_live=tmp_path / "live" / "ftc.rl",
                               ftc_eval=tmp_path / "no-eval.json")) as c:
        yield c


def test_health_describes_the_ftc_graph(client):
    r = client.get("/api/health").json()
    assert r["ok"] is True and r["loaded"] is True and r["synthetic"] is False and r["graph"] == "ftc.rl"


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Dropnet" in r.text
    assert "FTC complaint data" in r.text
    assert 'data-tab="ingest"' not in r.text and 'data-tab="inbox"' not in r.text


@pytest.mark.parametrize("method, path", [
    ("get", "/api/campaigns"), ("get", "/api/complaints"), ("get", "/api/samples"), ("get", "/api/explain?a=1&b=2"),
    ("post", "/api/ingest"), ("post", "/api/cypher"), ("post", "/api/tools/find_campaign"),
])
def test_synthetic_endpoints_are_gone(client, method, path):
    r = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
    assert r.status_code in (404, 405)


def test_summary_is_computed_once(client):
    a = client.get("/api/ftc/summary").json()
    client.post("/api/ftc/whatif", json={"blocks": ["866771"]})  # rolled back: the summary cannot change
    assert client.get("/api/ftc/summary").json()["reports"] == a["reports"] == 30


def test_no_synthetic_live_copy(ftc, tmp_path):
    live = tmp_path / "live" / "ftc.rl"
    with TestClient(create_app(reset=True, ftc_snapshot=ftc, ftc_live=live)) as c:
        assert c.get("/api/health").json()["ok"]
    assert sorted(x.name for x in live.parent.iterdir() if x.suffix == ".rl") == ["ftc.rl"]
