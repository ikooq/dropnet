import re
import shutil

import pytest

from dropnet import ingest, pipeline, store, tools
from dropnet.synth.generate import generate


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    d = tmp_path_factory.mktemp("ing")
    pipeline.build(d / "base.rl", seed=1, n=150)
    return d / "base.rl", generate(seed=1, n=150)


@pytest.fixture
def live(base, tmp_path):
    p = tmp_path / "live.rl"
    shutil.copy(base[0], p)
    conn = store.open_store(p)
    yield conn, base[1]
    conn.close()


def camp(ds, label):
    return "CAMP-" + ds.truth[label][0].split("-")[1]


def entity(conn, ds, label, kind):
    cid = ds.truth[label][0]
    return next(x["value"] for x in tools.get_complaint(conn, cid)["extractions"] if x["kind"] == kind)


def test_attach_by_mule_card(live):
    conn, ds = live
    card = entity(conn, ds, "A", "card")
    r = ingest.ingest_text(conn, f"Мне позвонили из банка и велели перевести 90 000 тг на карту {card}.",
                           region="Pavlodar")
    assert r.status == "attached" and r.campaign_id == camp(ds, "A")
    assert r.evidence and r.evidence["found"] and card in tools.render_path(r.evidence)
    k = tools.find_campaign(conn, r.complaint_id)["campaign"]
    assert k["size"] == len(ds.truth["A"]) + 1 and "Pavlodar" in k["regions"]


def test_new_id_continues_numbering(live):
    conn, _ = live
    r = ingest.ingest_text(conn, "Просто обман без деталей, потеряла 10 000 тг.")
    assert r.complaint_id == "CMP-0151"


def test_bridge_between_campaigns(live):
    conn, ds = live
    card = entity(conn, ds, "A", "card")
    phone = entity(conn, ds, "B", "phone")
    r = ingest.ingest_text(conn, f"Звонили с {phone}, сказали перевести на карту {card}. Перевела 50 000 тг.")
    assert r.status == "bridge"
    assert {r.campaign_id, *r.bridge_to} == {camp(ds, "A"), camp(ds, "B")}


def test_attach_by_script_only(live):
    conn, ds = live
    by = {c.id: c for c in ds.complaints}
    text = re.sub(r"\d", "5", by[ds.truth["E"][0]].text)  # same script, unknown numbers
    r = ingest.ingest_text(conn, text)
    assert r.status == "attached" and r.campaign_id == camp(ds, "E") and r.via == "script"


def test_new_campaign_from_loose_complaint(live):
    conn, ds = live
    in_c = {c for v in ds.truth.values() for c in v}
    loose = next(c for c in ds.complaints if c.id not in in_c and re.search(r"4000[\d *]{10,}", c.text))
    card = next(x["value"] for x in tools.get_complaint(conn, loose.id)["extractions"] if x["kind"] == "card")
    r = ingest.ingest_text(conn, f"Перевела 70 000 тг на карту {card} по просьбе незнакомца.")
    assert r.status == "new_campaign" and r.campaign_id == "CAMP-" + loose.id.split("-")[1]


def test_unlinked_has_candidates(live):
    conn, _ = live
    r = ingest.ingest_text(conn, "Позвонили якобы из службы безопасности банка, попросили код из SMS, списали 40 000 тг.")
    assert r.status == "unlinked" and r.campaign_id is None
    assert r.candidates and all("score" in c for c in r.candidates)


def test_empty_rejected(live):
    with pytest.raises(ValueError, match="empty complaint"):
        ingest.ingest_text(live[0], "   \n ")


def test_long_text_truncated(live):
    r = ingest.ingest_text(live[0], "мошенники " * 5000)
    c = tools.get_complaint(live[0], r.complaint_id)
    assert len(c["text"]) <= 20000


def test_hub_number_alone_does_not_attach(live):
    conn, _ = live
    r = ingest.ingest_text(conn, "Звонила в поддержку по номеру 8 799 000 00 00, ничего не решили, потеряла 5 000 тг.")
    assert r.status == "unlinked"


def test_snapshot_untouched(base, tmp_path):
    before = base[0].read_bytes()
    p = tmp_path / "copy.rl"
    shutil.copy(base[0], p)
    conn = store.open_store(p)
    ingest.ingest_text(conn, "Перевела 10 000 тг на карту 4000 0012 3456 7890.")
    conn.close()
    assert base[0].read_bytes() == before


def test_result_json(live):
    r = ingest.ingest_text(live[0], "Перевела 10 000 тг на карту 4000 0012 3456 7890.")
    d = r.to_json()
    assert set(d) >= {"complaint_id", "status", "campaign_id", "bridge_to", "evidence", "candidates", "via",
                      "summary_en", "path_text"}
