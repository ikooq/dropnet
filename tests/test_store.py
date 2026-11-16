from dropnet import store


def test_open_write_reopen(tmp_path):
    db = tmp_path / "t.rl"
    conn = store.open_store(db)
    store.rows(conn, "CREATE (:Probe {name: $n})", {"n": "x"})
    conn.close()
    ro = store.open_store(db, read_only=True)
    assert store.rows(ro, "MATCH (p:Probe) RETURN count(p) AS c")[0]["c"] == 1
    ro.close()


def test_ensure_schema_idempotent(tmp_path):
    conn = store.open_store(tmp_path / "s.rl")
    store.ensure_schema(conn)
    store.ensure_schema(conn)
    conn.close()


def test_reset_store_removes_file(tmp_path):
    db = tmp_path / "r.rl"
    store.open_store(db).close()
    store.reset_store(db)
    assert not db.exists()
