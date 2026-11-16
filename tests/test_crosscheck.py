import gzip
import json

from dropnet.ftc import campaigns, crosscheck
from tests.test_ftc_campaigns import g  # noqa: F401


def test_blocks_from_fcc_rows():
    rows = [{"caller_id_number": "866-771-0001"}, {"caller_id_number": "(866) 771-0002"},
            {"caller_id_number": "1-415-555-0000"}, {"caller_id_number": ""}, {"caller_id_number": "12345"}]
    assert crosscheck.fcc_blocks(rows) == {"866771": 2, "415555": 1}


def test_crosscheck_pools_vs_random(g):  # noqa: F811
    campaigns.write_campaigns(g, min_numbers=5)
    fcc = {"866771": 3}  # the FTC pool block is confirmed by the other agency
    r = crosscheck.crosscheck(g, fcc, top=50, seeds=3)
    assert r["pools_checked"] == 1 and r["pools_confirmed"] == 1 and r["pool_rate"] == 1.0
    assert 0.0 <= r["random_rate"] <= 1.0
    assert r["confirmed"][0]["block"] == "866771" and r["confirmed"][0]["fcc_complaints"] == 3


def test_load_fcc_rows_from_gz(tmp_path):
    p = tmp_path / "fcc.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump([{"caller_id_number": "866-771-0001"}], f)
    assert crosscheck.read_fcc(p) == [{"caller_id_number": "866-771-0001"}]
