import gzip
import json

from dropnet import store
from dropnet.ftc import build

HEADER = ("Company_Phone_Number,Created_Date,Violation_Date,Consumer_City,Consumer_State,Consumer_Area_Code,Subject,"
          "Recorded_Message_Or_Robocall\n")


def test_split_day():
    assert build.split_day(["2026-11-%02d" % i for i in range(1, 11)][::-1]) == "2026-11-08"


def test_build_end_to_end(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    lines = []
    for day in range(1, 10):
        for k in range(6):
            lines.append(f"866771{k:04d},2026-11-0{day} 10:00:00,2026-11-0{day} 09:00:00,Denver,Colorado,303,Other,Y")
    with gzip.open(raw / "DNC_Complaint_Numbers_2026-11-09.csv.gz", "wt", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(lines) + "\n")
    out = tmp_path / "ftc.rl"
    (tmp_path / "eval.json").write_text(json.dumps({"live_agent": {"kept": True}, "test_reports": -1}), encoding="utf-8")
    r = build.build(out=out, raw=raw, eval_path=tmp_path / "eval.json", log=lambda *_: None)
    assert r["stats"]["reports"] == 54 and r["campaigns"] >= 1
    assert r["dropnet"]["coverage"] >= r["baseline"]["coverage"]
    saved = json.loads((tmp_path / "eval.json").read_text(encoding="utf-8"))
    assert saved["test_reports"] == r["test_reports"]  # a fresh result wins
    assert saved["live_agent"] == {"kept": True}  # sections other commands wrote survive a rebuild
    target = out if out.exists() else out.with_suffix("")
    conn = store.open_store(target, read_only=True)
    assert store.rows(conn, "MATCH (c:FtcCampaign {id: 'POOL-866771'}) RETURN c.numbers AS n")[0]["n"] == 6
    conn.close()
