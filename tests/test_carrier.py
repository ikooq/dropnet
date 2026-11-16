import csv

from dropnet.ftc import carrier, networks
from tests.test_vault import make


def test_carrier_csv(tmp_path):
    c = make(tmp_path)
    out = tmp_path / "ranges.csv"
    n = carrier.export_csv(c, out, fcc={"866771": 4})
    c.close()
    assert n == 2
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    r = {x["block"]: x for x in rows}
    assert r["866-771"]["fcc_complaints"] == "4" and r["877-578"]["fcc_complaints"] == "0"
    assert r["866-771"]["toll_free"] == "yes" and r["866-771"]["network"] == "NET-866771"
    assert r["866-771"]["reported_numbers"] == "3" and int(r["866-771"]["reports"]) == 9
    assert set(rows[0]) >= {"block", "reports", "states", "first_day", "last_day", "subjects", "spoofed_share",
                            "fcc_complaints", "network", "note"}
    assert "10,000 numbers" in rows[0]["note"]
