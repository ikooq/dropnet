"""The app serves only the FTC graph: no synthetic store, no synthetic endpoints."""
import re
from html.parser import HTMLParser

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
    assert r["ok"] is True and r["synthetic"] is False and r["graph"] == "ftc.rl"
    assert r["loaded"] is False and r["loading"] is False
    assert client.get("/api/ftc/summary").status_code == 200
    r = client.get("/api/health").json()
    assert r["loaded"] is True and r["loading"] is False


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Dropnet" in r.text
    assert "FTC complaint data" in r.text
    assert 'data-tab="ingest"' not in r.text and 'data-tab="inbox"' not in r.text


def test_initial_assets_load_before_graph_boot_script(client):
    class InitialAssets(HTMLParser):
        in_head = False

        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if tag == "head":
                self.in_head = True
            elif tag == "link" and not attrs.get("href", "").startswith("data:"):
                assets.append((tag, self.in_head, attrs))
            elif tag == "script" or "src" in attrs or "srcset" in attrs:
                assets.append((tag, self.in_head, attrs))

        def handle_endtag(self, tag):
            if tag == "head":
                self.in_head = False

    assets = []
    InitialAssets().feed(client.get("/").text)
    # app.js starts the first graph requests as soon as it runs. Its prerequisites
    # must be parser-blocking and the CSS must have no late asset dependencies.
    assert assets == [
        ("link", True, {"rel": "stylesheet", "href": "style.css"}),
        ("script", True, {"src": "cytoscape-3.30.2.min.js"}),
        ("script", False, {"src": "app.js"}),
    ]
    for asset in ("style.css", "cytoscape-3.30.2.min.js", "app.js"):
        assert client.get(f"/{asset}").status_code == 200
    assert not re.search(r"@import\b|url\s*\(", client.get("/style.css").text, re.I)


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
        assert c.get("/api/ftc/summary").status_code == 200
    assert sorted(x.name for x in live.parent.iterdir() if x.suffix == ".rl") == ["ftc.rl"]
