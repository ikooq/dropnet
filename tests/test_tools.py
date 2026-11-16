import json

import pytest

from dropnet import pipeline, store, tools
from dropnet.synth.generate import generate


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    p = tmp_path_factory.mktemp("tools") / "t.rl"
    pipeline.build(p, seed=1, n=150)
    conn = store.open_store(p, read_only=True)
    yield conn, generate(seed=1, n=150)
    conn.close()


@pytest.mark.parametrize("stmt", ["CREATE (n:X)", "match (n) set n.x = 1", "MATCH (n) DETACH DELETE n",
                                  "MERGE (n:X {a: 1})", "MATCH (n) REMOVE n.a", "CALL db.createLabel('X')",
                                  "LOAD CSV FROM 'x' AS r RETURN r"])
def test_read_cypher_rejects_writes(built, stmt):
    with pytest.raises(ValueError):
        tools.read_cypher(built[0], stmt)


def test_read_cypher_allows_reads_and_vector_call(built):
    conn, _ = built
    r = tools.read_cypher(conn, "MATCH (c:Complaint) RETURN c.id AS id, c.filed_at AS d ORDER BY id LIMIT 3")
    assert r["columns"] == ["id", "d"] and len(r["rows"]) == 3
    json.dumps(r)  # JSON-safe (dates converted)
    r = tools.read_cypher(conn, "MATCH (c:Complaint {id: 'CMP-0001'}) "
                                "CALL db.index.vector.queryNodes('complaint_script', 2, c.script_vec) YIELD node "
                                "RETURN node.id AS id")
    assert r["rows"]


def test_read_cypher_limit(built):
    r = tools.read_cypher(built[0], "MATCH (c:Complaint) RETURN c.id AS id", limit=5)
    assert len(r["rows"]) == 5 and r["truncated"] is True


def test_schema(built):
    s = tools.get_schema(built[0])
    assert s["nodes"]["Complaint"] == 150 and "PAID_TO" in s["relationships"]


def test_find_campaign(built):
    conn, ds = built
    cid = ds.truth["A"][3]
    r = tools.find_campaign(conn, cid)
    assert r["campaign"]["id"] == "CAMP-" + ds.truth["A"][0].split("-")[1]
    assert r["campaign"]["size"] == len(ds.truth["A"])
    noise = next(c.id for c in ds.complaints if all(c.id not in v for v in ds.truth.values()))
    assert tools.find_campaign(conn, noise)["campaign"] is None


def test_explain_link_through_mule_card(built):
    conn, ds = built
    a, b = ds.truth["A"][0], ds.truth["A"][1]
    r = tools.explain_link(conn, a, b)
    assert r["found"] and r["hops"][0]["key"] == a and r["hops"][-1]["key"] == b
    assert any(h["label"] == "Card" for h in r["hops"])
    assert r["quotes"] and all(q["quote"] for q in r["quotes"])


def test_explain_link_chain(built):
    conn, ds = built
    d = ds.truth["D"]
    r = tools.explain_link(conn, d[0], d[-1])
    assert r["found"] and r["rels"]


def test_explain_link_skips_hub(built):
    conn, ds = built
    r = tools.explain_link(conn, ds.truth["A"][0], ds.truth["B"][0])
    assert not any(h["key"] == "+77990000000" for h in r["hops"])


def test_top_mules(built):
    conn, ds = built
    camp = "CAMP-" + ds.truth["A"][0].split("-")[1]
    mules = tools.top_mules(conn, camp)
    # The cash-out card that ultimately receives every victim's money ranks first, then the mule card.
    assert mules[0]["victims"] == len(ds.truth["A"]) and mules[0]["role"] == "cashout"
    assert mules[1]["victims"] == len(ds.truth["A"]) and mules[1]["role"] == "mule"


def test_similar_scripts(built):
    conn, ds = built
    by = {c.id: c for c in ds.complaints}
    hits = tools.similar_scripts(conn, by[ds.truth["E"][0]].text, k=3)
    assert len(hits) == 3 and hits[0]["campaign"] == "CAMP-" + ds.truth["E"][0].split("-")[1]


def test_campaign_graph(built):
    conn, ds = built
    camp = "CAMP-" + ds.truth["D"][0].split("-")[1]
    g = tools.campaign_graph(conn, camp)
    ids = {n["id"] for n in g["nodes"]}
    assert set(ds.truth["D"]) <= ids
    assert any(e["type"] == "FORWARDED_TO" for e in g["edges"])
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])


def test_lists(built):
    conn, _ = built
    camps = tools.list_campaigns(conn)
    assert len(camps) == 7 and camps[0]["size"] >= camps[-1]["size"]
    page = tools.list_complaints(conn, limit=10, offset=5)
    assert len(page["items"]) == 10 and page["total"] == 150
    only = tools.list_complaints(conn, campaign=camps[0]["id"], limit=500)
    assert len(only["items"]) == camps[0]["size"]
    c = tools.get_complaint(conn, "CMP-0001")
    assert c["id"] == "CMP-0001" and "extractions" in c
