import re
import subprocess
import sys

import pytest

from dropnet import pipeline, report, store, tools
from dropnet.synth.generate import generate


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    p = tmp_path_factory.mktemp("rep") / "r.rl"
    pipeline.build(p, seed=1, n=150)
    conn = store.open_store(p, read_only=True)
    yield conn, generate(seed=1, n=150), p
    conn.close()


def camp(ds, label):
    return "CAMP-" + ds.truth[label][0].split("-")[1]


def test_explain_link_reports_direction(built):
    conn, ds, _ = built
    r = tools.explain_link(conn, ds.truth["A"][0], ds.truth["A"][1])
    assert r["forward"] == [True, False]  # complaint -PAID_TO-> card <-PAID_TO- complaint


def test_markdown_sections(built):
    conn, ds, _ = built
    md = report.to_markdown(report.build_case(conn, camp(ds, "A")))
    for h in ("## Summary", "## Tactics", "## Mule & cash-out accounts", "## Evidence paths",
              "## Phones, domains & aliases", "## Recommended actions"):
        assert h in md
    assert len(re.findall(r"—PAID_TO→|—CONTACTED_BY→", md)) >= 3
    assert "Synthetic data" in md
    assert "> " in md  # quotes from complaints


def test_no_full_card_numbers_in_output(built):
    conn, ds, _ = built
    for label in ("A", "D", "F"):
        case = report.build_case(conn, camp(ds, label))
        for text in (report.to_markdown(case), report.to_html(case)):
            assert not re.search(r"\b4000\s?00\d{2}\s?\d{4}\s?\d{4}\b", text)


def test_redact():
    assert tools.redact("карта 4000 0012 3456 1234 и 4000001234561234") == \
        "карта 4000 00** **** 1234 и 4000 00** **** 1234"


def test_chain_case_shows_money_flow(built):
    conn, ds, _ = built
    md = report.to_markdown(report.build_case(conn, camp(ds, "D")))
    assert "—FORWARDED_TO→" in md or "←FORWARDED_TO—" in md


def test_script_only_case_uses_similarity(built):
    conn, ds, _ = built
    md = report.to_markdown(report.build_case(conn, camp(ds, "E")))
    assert "same script" in md


def test_html_is_self_contained(built):
    conn, ds, _ = built
    html = report.to_html(report.build_case(conn, camp(ds, "A")))
    assert html.startswith("<!doctype html>")
    assert not re.search(r"(src|href)=\"https?://", html)
    assert "<h2>Evidence paths</h2>" in html


def test_unknown_campaign(built):
    with pytest.raises(KeyError):
        report.build_case(built[0], "CAMP-9999")


def test_cli_case_and_investigate(built):
    _, ds, path = built
    out = subprocess.run([sys.executable, "-m", "dropnet", "case", camp(ds, "A"), "--db", str(path)],
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert out.returncode == 0, out.stderr
    assert "## Evidence paths" in out.stdout
    out = subprocess.run([sys.executable, "-m", "dropnet", "investigate", ds.truth["B"][2], "--db", str(path)],
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert out.returncode == 0 and camp(ds, "B") in out.stdout
