import pytest

from dropnet import load, store
from dropnet.extract import rules


@pytest.fixture
def loaded(tmp_path, mini_dataset):
    conn = store.open_store(tmp_path / "l.rl")
    store.ensure_schema(conn)
    exs = [e for c in mini_dataset.complaints for e in rules.extract(c.id, c.text)]
    counts = load.load_dataset(conn, mini_dataset, exs)
    yield conn, counts
    conn.close()


def one(conn, q, **p):
    return store.rows(conn, q, p)[0]


def test_counts(loaded):
    conn, counts = loaded
    assert counts["Complaint"] == 10
    assert one(conn, "MATCH (c:Complaint) RETURN count(c) AS n")["n"] == 10


def test_same_phone_two_formats_is_one_node(loaded):
    conn, _ = loaded
    r = one(conn, "MATCH (p:Phone {e164: '+77990123456'})<-[:CONTACTED_BY]-(c:Complaint) RETURN count(c) AS n")
    assert r["n"] == 2
    assert one(conn, "MATCH (p:Phone {e164: '+77990123456'}) RETURN count(p) AS n")["n"] == 1


def test_masked_and_full_card_merge(loaded):
    conn, _ = loaded
    r = one(conn, "MATCH (:Complaint)-[:PAID_TO]->(k:Card {pan_masked: '4000 00** **** 1111'}) RETURN count(*) AS n")
    assert r["n"] == 2


def test_forwarding_edges(loaded):
    conn, _ = loaded
    r = one(conn, "MATCH (:Card)-[f:FORWARDED_TO]->(:Card {pan_masked: '4000 00** **** 9999'}) RETURN count(f) AS n")
    assert r["n"] == 2


def test_iban_account_and_domain(loaded):
    conn, _ = loaded
    assert one(conn, "MATCH (:Complaint)-[:PAID_TO]->(a:Account) RETURN count(a) AS n")["n"] == 1
    r = one(conn, "MATCH (:Complaint)-[:VISITED]->(:Url)-[:ON_DOMAIN]->(d:Domain {name: 'loan-x.example'}) "
                  "RETURN count(*) AS n")
    assert r["n"] == 2


def test_tactics_and_regions(loaded):
    conn, _ = loaded
    r = one(conn, "MATCH (c:Complaint {id: 'CMP-0003'})-[:USED_TACTIC]->(t:Tactic) RETURN t.code AS code")
    assert r["code"] == "POLICE_THREAT"
    assert one(conn, "MATCH (c:Complaint {id:'CMP-0002'})-[:FILED_IN]->(r:Region) RETURN r.name AS n")["n"] == "Pavlodar"


def test_every_extraction_has_provenance(loaded):
    conn, _ = loaded
    total = one(conn, "MATCH (e:Extraction) RETURN count(e) AS n")["n"]
    assert total > 10
    linked = one(conn, "MATCH (c:Complaint)<-[:FROM]-(e:Extraction)-[:FOUND]->() RETURN count(DISTINCT e) AS n")["n"]
    assert linked == total


def test_script_vectors_and_synthetic_flag(loaded):
    conn, _ = loaded
    r = one(conn, "MATCH (c:Complaint {id:'CMP-0001'}) RETURN size(c.script_vec) AS d, c.synthetic AS s")
    assert r == {"d": 256, "s": True}
    assert one(conn, "MATCH (n) WHERE n.synthetic IS NULL RETURN count(n) AS n")["n"] == 0


def test_vector_index_query(loaded):
    conn, _ = loaded
    from dropnet import embed
    v = embed.vectorize("Куратор Алия, доход 30 % в месяц")
    r = store.rows(conn, "CALL db.index.vector.queryNodes('complaint_script', 1, $v) YIELD node RETURN node.id AS id",
                   {"v": v})
    assert r[0]["id"] == "CMP-0010"
