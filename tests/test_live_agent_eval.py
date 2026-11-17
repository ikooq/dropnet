from dropnet.ftc import live_agent_eval as e


def test_sample_is_stratified_and_seeded(tmp_path):
    lk = tmp_path / "lookup.txt"
    lines = ["# dropnet lookup v1 2026-10-09 2026-11-12", "B 866771 7 19"]
    lines += [f"20120000{i:02d} 1 s" for i in range(10)] + [f"86677100{i:02d} 3 p" for i in range(10)]
    lk.write_text("\n".join(lines) + "\n", encoding="utf-8")
    a = e.sample(lk, {"s": 3, "p": 2}, seed=1)
    assert sorted(c for _, c in a) == ["p", "p", "s", "s", "s"]
    assert a == e.sample(lk, {"s": 3, "p": 2}, seed=1)


def test_score_counts_blamed_owners_and_range_blocks():
    rows = [
        {"code": "s", "without": {"answer": {"verdict": "unknown", "owner_likely_innocent": True, "block": "number"}},
         "with": {"answer": {"verdict": "likely_spoofed", "owner_likely_innocent": True, "block": "nothing"}}},
        {"code": "p", "without": {"answer": {"verdict": "unknown", "owner_likely_innocent": False, "block": "number"}},
         "with": {"answer": {"verdict": "rented_range", "owner_likely_innocent": False, "block": "range"}}},
        {"code": "1", "without": {"error": "timeout"}, "with": {"answer": None}},
    ]
    s = e.score(rows)
    off, on = s["without_dropnet"], s["with_dropnet"]
    assert off["spoofed_owner_blamed"] == 1 and on["spoofed_owner_blamed"] == 0  # blocking the number hits the owner
    assert off["pool_range_blocked"] == 0 and on["pool_range_blocked"] == 1
    assert on["verdict_correct"] == 2 and off["verdict_correct"] == 0 and off["said_unknown"] == 2
