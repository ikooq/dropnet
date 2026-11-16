import gzip

from dropnet.ftc import fetch

PAGE = ('<a href="/sites/default/files/DNC_Complaint_Numbers_2026-11-13.csv">x</a>'
        '<a href="/sites/default/files/DNC_Complaint_Numbers_2026-11-12.csv">y</a>'
        '<a href="/sites/default/files/DNC_Complaint_Numbers_2026-11-13.csv">dup</a>')


def test_csv_links_sorted_unique():
    assert fetch.csv_links(PAGE) == [
        "https://www.ftc.gov/sites/default/files/DNC_Complaint_Numbers_2026-11-12.csv",
        "https://www.ftc.gov/sites/default/files/DNC_Complaint_Numbers_2026-11-13.csv"]


def test_fetch_downloads_gzips_and_skips_existing(tmp_path):
    calls = []

    def get(url):
        calls.append(url)
        return PAGE if url == fetch.INDEX_URL else "Company_Phone_Number\n7135550101\n"

    paths = fetch.fetch(tmp_path, get=get)
    assert [p.name for p in paths] == ["DNC_Complaint_Numbers_2026-11-12.csv.gz",
                                       "DNC_Complaint_Numbers_2026-11-13.csv.gz"]
    assert gzip.open(paths[0], "rt").read().startswith("Company_Phone_Number")
    n = len(calls)
    fetch.fetch(tmp_path, get=get)
    assert len(calls) == n + 1  # only the index page again


def test_fetch_limits_days(tmp_path):
    get = lambda url: PAGE if url == fetch.INDEX_URL else "h\n"
    assert len(fetch.fetch(tmp_path, days=1, get=get)) == 1
