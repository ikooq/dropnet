from dropnet.ftc import campaigns, semantic
from tests.test_ftc_campaigns import g  # noqa: F401


def fake_embed(texts):
    """Deterministic 384-d vectors: a 'debt' axis and a 'medical' axis, so the test needs no model."""
    out = []
    for t in texts:
        low = t.lower()
        v = [0.0] * semantic.DIM
        v[0] = 1.0 if any(w in low for w in ("debt", "loan", "credit")) else 0.0
        v[1] = 1.0 if any(w in low for w in ("medic", "brace", "pharmac")) else 0.0
        v[2] = 0.1
        out.append(v)
    return out


def test_profiles_read_like_complaints(g):  # noqa: F811
    campaigns.write_campaigns(g)
    p = semantic.profiles(g)
    assert [x["id"] for x in p] == ["POOL-866771"]
    assert "Toll-free phone number range 866-771-xxxx" in p[0]["text"] and "Colorado" in p[0]["text"]
    assert "student loans" in p[0]["text"]  # DEBT is described in people's words


def test_hybrid_fulltext_vector_and_state_filter(g, monkeypatch):  # noqa: F811
    campaigns.write_campaigns(g)
    monkeypatch.setattr(semantic, "embed", fake_embed)
    semantic.write_profiles(g, log=lambda *_: None)
    # no literal word in common with the profile, found by meaning (here: the fake 'debt' axis)
    v = semantic.search(g, "help with my loans", mode="vector")
    assert [r["id"] for r in v["results"]] == ["POOL-866771"]
    h = semantic.search(g, "Colorado", mode="hybrid")
    assert h["mode"] == "hybrid" and h["results"][0]["id"] == "POOL-866771"
    assert semantic.search(g, "loans", mode="hybrid", state="California")["results"] == []  # graph filter: never called CA
    assert semantic.search(g, "loans", mode="hybrid", state="Colorado")["results"]


def test_falls_back_to_fulltext_without_a_model(g, monkeypatch):  # noqa: F811
    campaigns.write_campaigns(g)
    monkeypatch.setattr(semantic, "embed", lambda texts: None)
    semantic.write_profiles(g, log=lambda *_: None)
    r = semantic.search(g, "toll-free range", mode="hybrid")
    assert r["mode"] == "fulltext (no model)" and r["results"]
