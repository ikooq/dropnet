import json
import re

from dropnet.synth.generate import generate, write_dataset

PHONE_ANY = re.compile(r"(?:\+7|8)[\s(]*7\s*9\s*9[\s)-]*\d[\d\s-]{6,12}\d")
CARD_ANY = re.compile(r"\b4\s?0\s?0\s?0[\s*\d]{11,20}\d{4}\b")


def test_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_dataset(generate(seed=1), a)
    write_dataset(generate(seed=1), b)
    for name in ("complaints.jsonl", "bank_transfers.jsonl", "ground_truth.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_different_seed_differs():
    assert generate(seed=1).complaints[0].text != generate(seed=2).complaints[0].text


def test_counts():
    ds = generate(seed=1, n=250)
    assert len(ds.complaints) == 250
    assert len(ds.truth) == 7
    in_campaign = {cid for ids in ds.truth.values() for cid in ids}
    noise = 250 - len(in_campaign)
    assert 0.20 * 250 <= noise <= 0.30 * 250
    assert len({c.id for c in ds.complaints}) == 250


def test_ids_are_chronological():
    ds = generate(seed=1)
    dates = [c.filed_at for c in ds.complaints]
    assert dates == sorted(dates)
    assert ds.complaints[0].id == "CMP-0001"


def test_safe_identifiers():
    ds = generate(seed=1)
    text = "\n".join(c.text for c in ds.complaints)
    phone_shape = r"(?<![\d*])(?:\+7|8)[ (]?(\d{3})\)?[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}(?![\d*])"
    found = list(re.finditer(phone_shape, text))
    assert len(found) > 100
    for m in found:
        assert m.group(1) == "799", m.group(0)
    for iban in re.findall(r"\bKZ\d{2}", text):
        assert iban == "KZ00"
    for dom in re.findall(r"https?://([a-z0-9.-]+)", text):
        assert dom.endswith(".example") or dom.endswith(".test"), dom
    for t in ds.transfers:
        for acct in (t.src, t.dst):
            assert acct.startswith("4000 00") or acct.startswith("KZ00"), acct


def test_formats_vary():
    ds = generate(seed=1)
    text = "\n".join(c.text for c in ds.complaints)
    shapes = set()
    if re.search(r"\b8 799 \d{3} \d{2} \d{2}\b", text): shapes.add("8 spaced")
    if re.search(r"\+7\(799\)\d{7}", text): shapes.add("+7(799)")
    if re.search(r"\b87990\d{6}\b", text): shapes.add("8 compact")
    if re.search(r"\+7 799 \d{3}-\d{2}-\d{2}", text): shapes.add("+7 dashed")
    assert len(shapes) >= 3, shapes


def test_hub_present():
    ds = generate(seed=1)
    hub_texts = [c for c in ds.complaints if re.search(r"799[\s)-]*000[\s-]*00[\s-]*00", c.text)]
    assert len(hub_texts) >= 10
    assert len({c.region for c in hub_texts}) >= 4


def test_complaint_fields():
    c = generate(seed=1).complaints[0]
    assert c.text and c.text_en and c.region and c.channel
    assert c.amount_kzt > 0
    assert re.search("[а-яА-Я]", c.text)


def test_written_raw_files_have_no_full_card_numbers(tmp_path):
    write_dataset(generate(seed=1), tmp_path)
    pan = re.compile(r"(?<![\dA-Z*])\d{4}[ -]?\d{2}\d{2}[ -]?\d{4}[ -]?\d{4}(?![\d*])")
    assert not pan.search((tmp_path / "complaints.jsonl").read_text(encoding="utf-8"))


def test_ground_truth_json(tmp_path):
    write_dataset(generate(seed=1), tmp_path)
    truth = json.loads((tmp_path / "ground_truth.json").read_text(encoding="utf-8"))
    assert all(len(v) >= 3 for v in truth.values())


def test_noise_is_diverse():
    from itertools import combinations
    from dropnet import embed
    ds = generate(seed=1)
    in_campaign = {cid for ids in ds.truth.values() for cid in ids}
    noise = [c for c in ds.complaints if c.id not in in_campaign]
    from dropnet.extract import rules
    vecs = [embed.vectorize(c.text) for c in noise]
    tactics = [{e.value for e in rules.extract(c.id, c.text) if e.kind == "tactic"} for c in noise]
    # Only same-tactic pairs can become weak links (see dropnet.link), so only they matter.
    pairs = [(i, j) for i, j in combinations(range(len(noise)), 2) if tactics[i] & tactics[j]]
    # New script-only groups need SCRIPT_ONLY_THRESHOLD (0.90), so that is the bar noise must stay under.
    close = sum(1 for i, j in pairs if (embed.cosine(vecs[i], vecs[j]) + 1) / 2 >= 0.90)
    assert close / len(pairs) < 0.02, (close, len(pairs))


def test_phone_pool_numbers_co_mentioned():
    ds = generate(seed=1)
    by = {c.id: c for c in ds.complaints}
    two = [cid for cid in ds.truth["B"] if len(re.findall(r"799[ )-]*0\d\d", by[cid].text)) >= 2]
    assert len(two) >= 0.25 * len(ds.truth["B"])


def test_hard_variant_has_extra_script_campaign():
    assert len(generate(seed=1, hard=True).truth) == 8
