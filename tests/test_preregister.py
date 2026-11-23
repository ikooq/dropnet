import gzip
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("preregister", Path(__file__).parents[1] / "scripts" / "preregister.py")
pre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre)

HEADER = ("Company_Phone_Number,Created_Date,Violation_Date,Consumer_City,Consumer_State,Consumer_Area_Code,Subject,"
          "Recorded_Message_Or_Robocall\n")


def write(folder: Path, day: str, rows: list[str]):
    folder.mkdir(parents=True, exist_ok=True)
    with gzip.open(folder / f"DNC_Complaint_Numbers_{day}.csv.gz", "wt", encoding="utf-8", newline="") as f:
        f.write(HEADER + "".join(r + "\n" for r in rows))


def row(number: str, day: str, consumer_npa: str = "212") -> str:
    return f"{number},{day} 10:00:00,{day} 09:00:00,Denver,Colorado,{consumer_npa},Other,Y"


def test_freeze_then_check_scores_only_later_files(tmp_path):
    train = tmp_path / "train"
    write(train, "2026-11-10", [row(f"303555{k:04d}", "2026-11-09") for k in range(6)])  # one range, 6 numbers
    write(train, "2026-11-11", [row("7205550000", "2026-11-10")] * 2)                  # one repeat number
    pred = tmp_path / "pred"
    m = pre.freeze([train], pred)
    assert m["training"]["last_file"] == "2026-11-11" and m["training"]["last_filing_day"] == "2026-11-10"
    assert m["frozen"]["geographic_ranges"] == 1 and m["frozen"]["numbers"] == 1

    test = tmp_path / "test"
    write(test, "2026-11-11", [row("3035559999", "2026-11-12")])  # not after the last training file: ignored
    write(test, "2026-11-13", [row("3035559998", "2026-11-12"), row("7205550000", "2026-11-12"),
                               row("4155550000", "2026-11-12"), row("3035550001", "2026-11-09")])
    r = pre.check(pred, test)
    assert r["test_files"] == ["DNC_Complaint_Numbers_2026-11-13.csv.gz"]
    s = r["filed_after_freeze"]
    assert s["complaints"] == 3  # the complaint filed on 2026-11-09 is not after the freeze
    assert s["hits"] == {"numbers_only": 1, "numbers_and_geographic_ranges": 2, "numbers_and_all_ranges": 2}
    assert s["never_seen_numbers"] == {"complaints": 2, "in_a_frozen_geographic_range": 1}


def test_check_refuses_changed_lists(tmp_path):
    write(tmp_path / "train", "2026-11-10", [row(f"303555{k:04d}", "2026-11-09") for k in range(6)])
    pred = tmp_path / "pred"
    pre.freeze([tmp_path / "train"], pred)
    with (pred / "ranges.txt").open("a", encoding="utf-8") as f:
        f.write("415555\tgeographic\n")
    with pytest.raises(SystemExit, match="changed"):
        pre.check(pred, tmp_path / "train")
