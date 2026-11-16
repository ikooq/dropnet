import gzip
import json
import os
import subprocess

import pytest

from dropnet import relate_ext, store
from dropnet.ftc import build

HEADER = ("Company_Phone_Number,Created_Date,Violation_Date,Consumer_City,Consumer_State,Consumer_Area_Code,Subject,"
          "Recorded_Message_Or_Robocall\n")


def fixture(tmp_path, filler=0):
    raw = tmp_path / "raw"
    raw.mkdir()
    lines = [f"866771{k:04d},2026-11-0{d} 10:00:00,2026-11-0{d},Denver,Colorado,303,Other,Y"
             for d in range(1, 4) for k in range(6)]
    # one report per block: never a pool, but pushes the run past Relate's 1,000-rows-per-statement cap
    lines += [f"2{k:05d}0000,2026-11-02 10:00:00,2026-11-02,Austin,Texas,512,Other,Y" for k in range(filler)]
    # 7 numbers from 713-555 but every report is from the victim's own area code: spoofed, never a pool
    lines += [f"713555{k:04d},2026-11-01 10:00:00,2026-11-01,Houston,Texas,713,Other,Y" for k in range(7)]
    with gzip.open(raw / "DNC_Complaint_Numbers_2026-11-03.csv.gz", "wt", encoding="utf-8") as f:
        f.write(HEADER + "\n".join(lines) + "\n")
    return raw


def test_package_is_one_executable_plus_manifest(tmp_path):
    for windows, exe in ((True, "dropnet-ftc.cmd"), (False, "dropnet_ftc.py")):
        out = relate_ext.package(tmp_path / str(windows), windows=windows)
        m = json.loads((out / "extension.json").read_text(encoding="utf-8"))
        assert m["executable"] == exe and m["kind"] == "command"
        assert sorted(p.name for p in out.iterdir()) == sorted(["extension.json", exe])
        assert {f["name"] for f in m["flags"]} == {"path", "min_numbers"}


def test_child_parser_matches_dropnet_parser(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("child", relate_ext.CHILD)
    child = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(child)
    raw = fixture(tmp_path)
    from dropnet.ftc import parse
    ours = [(r.number, r.neighbor) for r in parse.read_reports(raw.glob("*.csv.gz"))]
    theirs = [(r["number"], r["neighbor"]) for r in child.read_reports(str(raw))]
    assert ours == theirs and len(ours) == 25


@pytest.mark.skipif(not build.relate_cli(), reason="Relate CLI not installed")
def test_relate_run_finds_pools(tmp_path):
    cli = build.relate_cli()
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "RELATE_TELEMETRY": "off"}
    relate_ext.install(cli, env=env)
    db = tmp_path / "graph"
    r = subprocess.run([cli, "run", "dropnet-ftc", "--path", str(fixture(tmp_path, filler=1500)), "-d", str(db)],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "1,525 FTC reports -> 1 rented number ranges" in r.stdout
    conn = store.open_store(db, read_only=True)
    pools = store.rows(conn, "MATCH (c:FtcCampaign) RETURN c.id AS id, c.numbers AS n")
    conn.close()
    assert pools == [{"id": "POOL-866771", "n": 6}]
