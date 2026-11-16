from dropnet import site, store
from dropnet.ftc import campaigns
from tests.test_ftc_campaigns import g  # noqa: F401


def test_lookup_verdicts_match_assess_number(g, tmp_path):  # noqa: F811
    campaigns.write_campaigns(g)
    path = tmp_path / "c.rl"
    g.close()
    out = tmp_path / "lookup.txt"
    res = site.export_lookup(path, out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# dropnet lookup v1")
    assert "B 866771 7 19" in lines  # the pool block, all of its reports
    conn = store.open_store(path, read_only=True)
    try:
        for line in lines[1:]:
            if line.startswith("B "):
                continue
            number, reports, code = line.split()
            a = campaigns.assess_number(conn, number)
            assert site.CODES[a["verdict"]] == code and a["reports"] == int(reports), line
    finally:
        conn.close()
    assert res["verdicts"]["likely_spoofed"] == 9 and res["pool_blocks"] == 1
