from datetime import date

import pytest

from dropnet import link, load, store
from dropnet.extract import rules
from dropnet.models import Complaint, Dataset


def build(tmp_path, ds, name="k.rl"):
    conn = store.open_store(tmp_path / name)
    store.ensure_schema(conn)
    exs = [e for c in ds.complaints for e in rules.extract(c.id, c.text)]
    load.load_dataset(conn, ds, exs)
    return conn


def member_map(camps):
    return {cid: c.id for c in camps for cid in c.member_ids}


@pytest.fixture
def mini(tmp_path, mini_dataset):
    conn = build(tmp_path, mini_dataset)
    link.add_similarity(conn)
    camps = link.build_campaigns(conn)
    yield conn, camps
    conn.close()


def test_shared_card_same_campaign(mini):
    _, camps = mini
    m = member_map(camps)
    assert m["CMP-0001"] == m["CMP-0002"]


def test_forwarding_chain_merges(mini):
    _, camps = mini
    m = member_map(camps)
    assert m["CMP-0003"] == m["CMP-0004"]


def test_domain_merges(mini):
    m = member_map(mini[1])
    assert m["CMP-0005"] == m["CMP-0006"]


def test_unrelated_not_in_campaigns(mini):
    m = member_map(mini[1])
    assert "CMP-0007" not in m and "CMP-0010" not in m
    assert m["CMP-0001"] != m["CMP-0003"]


def test_campaign_id_is_earliest_member(mini):
    conn, camps = mini
    ids = {c.id for c in camps}
    assert {"CAMP-0001", "CAMP-0003", "CAMP-0005"} <= ids
    r = store.rows(conn, "MATCH (c:Complaint)-[:PART_OF]->(k:Campaign {id: 'CAMP-0001'}) RETURN count(c) AS n")
    assert r[0]["n"] == 2


def test_rerun_is_idempotent(mini):
    conn, camps = mini
    again = link.build_campaigns(conn)
    assert sorted((c.id, tuple(c.member_ids)) for c in again) == sorted((c.id, tuple(c.member_ids)) for c in camps)
    assert store.rows(conn, "MATCH (k:Campaign) RETURN count(k) AS n")[0]["n"] == len(camps)


def test_campaign_summary_fields(mini):
    _, camps = mini
    a = next(c for c in camps if c.id == "CAMP-0001")
    assert a.size == 2 and a.damage_kzt == 200000 and a.regions == ["Almaty", "Pavlodar"]
    assert a.first_seen == "2026-01-01" and a.last_seen == "2026-01-02"
    assert 0 < a.confidence <= 1


def test_card_roles(mini):
    conn, _ = mini
    role = {r["k"]: r["role"] for r in store.rows(conn, "MATCH (k:Card) RETURN k.pan_masked AS k, k.role_hint AS role")}
    assert role["4000 00** **** 1111"] == "mule"
    assert role["4000 00** **** 9999"] == "cashout"


def _C(i, text, region, tactic_text=""):
    return Complaint(f"CMP-{i:04d}", date(2026, 3, i), region, "call", 10000 * i, text + tactic_text, "en", "26-40")


def test_hub_does_not_merge(tmp_path):
    hub = " Поддержка 8 799 000 00 00 не помогла."
    texts = [
        ("Следователь угрожал уголовным делом.", "Astana"),
        ("Продавец взял предоплату на карту 4000 0011 1111 1111.", "Almaty"),
        ("Куратор обещал доход 30 %, карта 4000 0022 2222 2222.", "Oral"),
        ("Служба безопасности банка попросила код.", "Aktau"),
        ("SMS о статусе займа, ввела данные.", "Taraz"),
        ("Безопасный счёт KZ00 1111 2222 3333 4444.", "Semey"),
    ]
    ds = Dataset([_C(i + 1, t, r, hub) for i, (t, r) in enumerate(texts)], [], {})
    conn = build(tmp_path, ds)
    hubs = link.find_hubs(conn)
    assert "+77990000000" in hubs
    camps = link.build_campaigns(conn)
    assert camps == []
    camps_nofilter = link.build_campaigns(conn, use_hub_filter=False)
    assert len(camps_nofilter) == 1  # the trap: everything glued together
    conn.close()


def test_single_tactic_hub_across_gangs(tmp_path):
    """A marketplace support line appears in complaints of three different gangs (all MARKETPLACE_PREPAY,
    all in one region). Each gang is linked by its own mule card; the support number must not glue them."""
    hub = " Звонил в поддержку маркетплейса 8 799 000 00 00."
    cs, i = [], 1
    for gang in ("1111", "2222", "3333"):
        for _ in range(3):
            cs.append(_C(i, f"Продавец по объявлению взял предоплату на карту 4000 00{gang[:2]} {gang} {gang}.{hub}",
                         "Almaty"))
            i += 1
    conn = build(tmp_path, Dataset(cs, [], {}))
    camps = link.build_campaigns(conn, use_vectors=False)
    assert len(camps) == 3 and all(c.size == 3 for c in camps)
    assert "+77990000000" in link.find_hubs(conn)
    conn.close()


def test_script_only_trio(tmp_path):
    script = ("Личный куратор платформы «KazOil Invest» обещал гарантированный доход 30 % в месяц от акций "
              "нефтяной компании, первый взнос через карту {card}, потом налог за вывод.")
    cards = ["4000 0011 1111 1111", "4000 0022 2222 2222", "4000 0033 3333 3333"]
    other = "Продавец шин по объявлению взял предоплату на карту 4000 0044 4444 4444 и пропал."
    cs = [_C(i + 1, script.format(card=k), "Almaty") for i, k in enumerate(cards)] + [_C(4, other, "Astana")]
    conn = build(tmp_path, Dataset(cs, [], {}))
    link.add_similarity(conn)
    camps = link.build_campaigns(conn)
    m = member_map(camps)
    assert m.get("CMP-0001") == m.get("CMP-0002") == m.get("CMP-0003") == "CAMP-0001"
    assert "CMP-0004" not in m
    assert link.build_campaigns(conn, use_vectors=False) == []
    conn.close()


def test_shared_persona_and_tactic_links(tmp_path):
    cs = [
        _C(1, "Куратор Алия обещала доход 30 %, карта 4000 0011 1111 1111.", "Almaty"),
        _C(2, "Мне писала куратор Алия про доход, перевела на 4000 0022 2222 2222.", "Oral"),
        _C(3, "Продавец Алия по объявлению взяла предоплату на 4000 0033 3333 3333.", "Astana"),
    ]
    conn = build(tmp_path, Dataset(cs, [], {}))
    m = member_map(link.build_campaigns(conn, use_vectors=False))
    assert m["CMP-0001"] == m["CMP-0002"]
    assert "CMP-0003" not in m  # same name, different tactic: not enough
    assert ("CMP-0001", "CMP-0002", "persona:Алия") in link.strong_pairs(conn)
    conn.close()


def test_strong_pairs_report_via(mini):
    conn, _ = mini
    pairs = link.strong_pairs(conn)
    assert ("CMP-0001", "CMP-0002", "4000 00** **** 1111") in pairs or \
           ("CMP-0001", "CMP-0002", "+77990123456") in pairs
