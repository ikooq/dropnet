import math

from dropnet import embed
from dropnet.synth import templates as T


def test_dimension_and_norm():
    v = embed.vectorize("Звонил следователь Нурлан")
    assert len(v) == 256
    assert math.isclose(sum(x * x for x in v), 1.0, rel_tol=1e-6)


def test_deterministic():
    assert embed.vectorize("Куратор Алия") == embed.vectorize("Куратор Алия")


def test_paraphrase_closer_than_unrelated():
    a = T.CAMPAIGN_SCRIPTS["INVESTMENT"][0][0].format(card="4000 00** **** 1111", amount="1 млн ₸",
                                                       phone="8 799 011 11 11")
    b = T.CAMPAIGN_SCRIPTS["INVESTMENT"][1][0].format(card="4000 00** **** 2222", amount="300 тыс. тг",
                                                       phone="8 799 022 22 22")
    c = T.GENERIC["INVESTMENT"][0][0].format(card="4000 00** **** 3333", amount="50 тыс. тг")
    assert embed.cosine(embed.vectorize(a), embed.vectorize(b)) > embed.cosine(embed.vectorize(a), embed.vectorize(c)) + 0.2


def test_digits_ignored():
    assert embed.vectorize("карта 4000 00** **** 1111") == embed.vectorize("карта 4000 00** **** 9999")


def test_empty_text_zero_vector():
    v = embed.vectorize("")
    assert len(v) == 256 and all(x == 0.0 for x in v)
