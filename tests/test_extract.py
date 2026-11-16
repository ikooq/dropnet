import pytest

from dropnet.extract import normalize, rules
from dropnet.synth.generate import generate


@pytest.mark.parametrize("raw", ["8 799 012 34 56", "+7(799)0123456", "87990123456", "+7 799 012-34-56",
                                 "+7 799 012 34 56"])
def test_phone_shapes(raw):
    assert normalize.phone(raw) == "+77990123456"


def test_phone_rejects_short():
    assert normalize.phone("8 799 01") is None


@pytest.mark.parametrize("raw", ["4000 0012 3456 1234", "4000001234561234", "4000 00** **** 1234"])
def test_card_shapes(raw):
    assert normalize.card(raw) == "4000 00** **** 1234"


@pytest.mark.parametrize("raw,val", [("50 тыс. тг", 50000), ("120 000 тг", 120000), ("1,5 млн ₸", 1500000),
                                     ("85 000 тенге", 85000)])
def test_amount(raw, val):
    assert normalize.amount_kzt(raw) == val


def test_domain():
    assert normalize.domain("https://loan-status-check.example/verify?id=1") == "loan-status-check.example"


def test_iban():
    assert normalize.iban("KZ00 1234 5678 9012 3456") == "KZ0012345678901234 56".replace(" ", "")


def kinds(exs, kind):
    return [e.value for e in exs if e.kind == kind]


def test_extract_phone_card_amount():
    text = "Звонили с +7(799)0123456, я перевела 120 000 тг на карту 4000 0012 3456 1234."
    exs = rules.extract("CMP-0001", text)
    assert kinds(exs, "phone") == ["+77990123456"]
    assert kinds(exs, "card") == ["4000 00** **** 1234"]
    assert 120000 in [int(v) for v in kinds(exs, "amount")]


def test_tactic_lexicon():
    exs = rules.extract("CMP-0002", "Мне звонили из службы безопасности банка и попросили код.")
    assert kinds(exs, "tactic") == ["BANK_SECURITY"]


def test_every_campaign_script_has_a_tactic():
    from dropnet.synth import templates as T
    for tactic, scripts in T.CAMPAIGN_SCRIPTS.items():
        for ru, _en in scripts:
            text = ru.format(phone="8 799 011 11 11", phone2="8 799 022 22 22", card="4000 00** **** 1111",
                             iban="KZ001111222233334444", url="https://a.example/x", amount="50 тыс. тг")
            assert tactic in kinds(rules.extract("CMP-0009", text), "tactic"), (tactic, ru[:60])


@pytest.mark.parametrize("text,name", [
    ("Представились Ерланом из отдела финансового мониторинга.", "Ерлан"),
    ("Написал куратор Алия с платформы.", "Алия"),
    ("Продавец Санжар (8 799 012 34 56) взял предоплату.", "Санжар"),
    ("Женщина по имени Динара, «Нацбанк».", "Динара"),
    ("Позвонил «следователь Нурлан» и угрожал.", "Нурлан"),
])
def test_persona(text, name):
    assert kinds(rules.extract("CMP-0011", text), "persona") == [name]


def test_no_persona_without_known_name():
    assert kinds(rules.extract("CMP-0012", "Мама пожилая, звонил Мужчина из банка."), "persona") == []


def test_hub_sentence_is_not_marketplace_tactic():
    exs = rules.extract("CMP-0003", "Поддержка маркетплейса по номеру 8 799 000 00 00 не помогла.")
    assert kinds(exs, "tactic") == []


def test_spans_quote():
    text = "Сначала было тихо. Потом звонок с 8 799 012 34 56 и угрозы следователя. Конец."
    for e in rules.extract("CMP-0004", text):
        assert text[e.span_start:e.span_end] in e.quote
        assert len(e.quote) <= 240
        assert e.extractor == "rules"


def test_quote_not_cut_at_abbreviation():
    text = "Мне позвонили. Я перевела 50 тыс. тг на карту 4000 0012 3456 1234, как он сказал. Конец."
    card = next(e for e in rules.extract("CMP-0013", text) if e.kind == "card")
    assert card.quote.startswith("Я перевела 50 тыс. тг")


def test_no_entities():
    assert rules.extract("CMP-0005", "Мне просто нагрубили") == []


def test_url_trailing_punct():
    exs = rules.extract("CMP-0006", "Ссылка: https://a-b-c.example/verify?id=12345.")
    assert kinds(exs, "url") == ["https://a-b-c.example/verify?id=12345"]


def test_generated_campaign_texts_yield_identifiers():
    ds = generate(seed=1)
    by_id = {c.id: c for c in ds.complaints}
    for cid in ds.truth["A"]:
        assert kinds(rules.extract(cid, by_id[cid].text), "card"), by_id[cid].text
    for cid in ds.truth["C"]:
        assert kinds(rules.extract(cid, by_id[cid].text), "url")
    for cid in ds.truth["B"]:
        assert kinds(rules.extract(cid, by_id[cid].text), "phone")
