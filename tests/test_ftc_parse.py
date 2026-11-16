import gzip

from dropnet.ftc import parse

CSV = (
    "Company_Phone_Number,Created_Date,Violation_Date,Consumer_City,Consumer_State,Consumer_Area_Code,Subject,"
    "Recorded_Message_Or_Robocall\n"
    '7135550101,2026-11-11 00:05:34,2026-11-03 15:07:00,BELLAIRE,Texas,713,'
    '"Reducing your debt (credit cards, mortgage, student loans)",Y\n'
    "7205550199,2026-11-11 00:05:48,2026-11-10 17:34:00,Lakewood,Colorado,303,Other,N\n"
    "1-800-555-0100,2026-11-11 01:00:00,2026-11-10 09:00:00,Austin,Texas,512,Calls pretending to be government, "
    "businesses, or family and friends,\n"
    "12345,2026-11-11 02:00:00,2026-11-10 09:00:00,Austin,Texas,512,Other,Y\n"
)


def write(tmp_path, name="DNC_Complaint_Numbers_2026-11-11.csv.gz", text=CSV):
    p = tmp_path / name
    with gzip.open(p, "wt", encoding="utf-8", newline="") as f:
        f.write(text)
    return p


def test_read_reports_parses_quoted_subject(tmp_path):
    reports = list(parse.read_reports([write(tmp_path)]))
    assert len(reports) == 3  # the 5-digit number is rejected
    r = reports[0]
    assert r.number == "7135550101" and r.npa == "713" and r.nxx == "555"
    assert r.subject == "DEBT" and r.robocall is True
    assert r.state == "Texas" and r.victim_npa == "713" and r.neighbor is True
    assert r.created.startswith("2026-11-11") and r.violation_day == "2026-11-03"


def test_neighbor_flag_false_when_area_codes_differ(tmp_path):
    r = list(parse.read_reports([write(tmp_path)]))[1]
    assert r.neighbor is False and r.robocall is False and r.subject == "OTHER"


def test_unquoted_government_subject_and_toll_free(tmp_path):
    r = list(parse.read_reports([write(tmp_path)]))[2]
    assert r.number == "8005550100" and r.subject == "IMPOSTER_GOV" and r.robocall is None
    assert r.toll_free is True


def test_ids_are_stable_and_unique(tmp_path):
    a = [r.id for r in parse.read_reports([write(tmp_path)])]
    b = [r.id for r in parse.read_reports([write(tmp_path)])]
    assert a == b and len(set(a)) == len(a)


def test_subject_codes_cover_ftc_labels():
    for label, code in [("Medical & prescriptions", "MEDICAL"), ("Warranties & protection plans", "WARRANTY"),
                        ("Home improvement & cleaning", "HOME"), ("Dropped call or no message", "DROPPED"),
                        ("Vacation & timeshares", "TRAVEL"), ("Lotteries, prizes & sweepstakes", "PRIZES"),
                        ("No Subject Provided", "NONE"), ("Energy, solar, & utilities", "ENERGY")]:
        assert parse.subject_code(label) == code, label
