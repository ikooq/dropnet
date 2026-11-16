"""Deterministic generator of synthetic Kazakh fraud complaints.

Everything here is fictional: phones live in +7 799 0xx xx xx, cards use the
test BIN 400000, IBANs start with KZ00, domains end with .example/.test.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import REGIONS
from ..models import Complaint, Dataset, Transfer
from . import templates as T

HUB_E164 = "+77990000000"
YEAR_START = date(2026, 1, 1)
YEAR_DAYS = 181  # Jan..Jun 2026
AGE_BANDS = ["18-25", "26-40", "41-60", "60+"]

# label, tactic, weight, mechanic
CAMPAIGNS = [
    ("A", "BANK_SECURITY", 9, "shared_card"),
    ("B", "SAFE_ACCOUNT", 7, "phone_pool"),
    ("C", "LOAN_STATUS_SMS", 6, "domain"),
    ("D", "POLICE_THREAT", 6, "chain"),
    ("E", "INVESTMENT", 5, "script_only"),
    ("F", "MARKETPLACE_PREPAY", 6, "two_mules"),
    ("G", "ATM_DROP_HELP", 2, "shared_card"),
]
HARD_EXTRA = ("H", "MARKETPLACE_PREPAY", 4, "script_only")


# ---------------------------------------------------------------- identifiers
class Ids:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.phones: set[str] = {HUB_E164}
        self.last4: set[str] = set()
        self.ibans: set[str] = set()
        self.domains: set[str] = set()

    def phone(self) -> str:
        while True:
            p = "+77990" + "".join(self.rng.choice("0123456789") for _ in range(6))
            if p not in self.phones:
                self.phones.add(p)
                return p

    def card(self) -> str:
        """Full 16-digit PAN on test BIN 400000 with a dataset-unique last 4."""
        while True:
            last4 = "".join(self.rng.choice("0123456789") for _ in range(4))
            if last4 not in self.last4:
                self.last4.add(last4)
                mid = "".join(self.rng.choice("0123456789") for _ in range(6))
                return "400000" + mid + last4

    def iban(self) -> str:
        while True:
            i = "KZ00" + "".join(self.rng.choice("0123456789") for _ in range(16))
            if i not in self.ibans:
                self.ibans.add(i)
                return i

    def domain(self, suffix: str = ".test") -> str:
        words = ["loan", "status", "credit", "check", "secure", "verify", "online", "kz", "pay", "portal"]
        while True:
            d = "-".join(self.rng.sample(words, 3)) + suffix
            if d not in self.domains:
                self.domains.add(d)
                return d


def mask(pan: str) -> str:
    return f"{pan[:4]} {pan[4:6]}** **** {pan[-4:]}"


def fmt_phone(e164: str, rng: random.Random) -> str:
    d = e164[2:]  # 10 digits, e.g. 7990123456
    a, b, c, e = d[0:3], d[3:6], d[6:8], d[8:10]
    style = rng.randrange(5)
    return [
        f"8 {a} {b} {c} {e}",
        f"+7({a}){b}{c}{e}",
        f"8{a}{b}{c}{e}",
        f"+7 {a} {b}-{c}-{e}",
        f"+7 {a} {b} {c} {e}",
    ][style]


def fmt_card(pan: str, rng: random.Random) -> str:
    style = rng.randrange(3)
    if style == 0:
        return f"{pan[0:4]} {pan[4:8]} {pan[8:12]} {pan[12:16]}"
    if style == 1:
        return pan
    return mask(pan)


def fmt_amount(v: int, rng: random.Random) -> tuple[str, str]:
    en = f"{v:,} KZT"
    style = rng.randrange(4)
    if style == 0 and v % 1000 == 0:
        ru = f"{v // 1000} тыс. тг"
    elif style == 1 and v >= 1_000_000 and v % 100_000 == 0:
        ru = f"{v / 1_000_000:.1f}".replace(".", ",").replace(",0", "") + " млн ₸"
    elif style == 2:
        ru = f"{v:,}".replace(",", " ") + " тенге"
    else:
        ru = f"{v:,}".replace(",", " ") + " тг"
    return ru, en


def rand_amount(rng: random.Random) -> int:
    return rng.choice([rng.randrange(15, 200) * 1000, rng.randrange(200, 1500) * 1000, rng.randrange(10, 40) * 100_000])


# ----------------------------------------------------------------- drafting
@dataclass
class Draft:
    label: str | None
    tactic: str
    filed_at: date
    region: str
    amount: int
    text: str
    text_en: str
    order: float = 0.0
    age: str = "26-40"


@dataclass
class _Ctx:
    rng: random.Random
    ids: Ids
    hard: bool
    transfers: list[Transfer] = field(default_factory=list)


def _paraphrase(rng: random.Random, text: str, p: float) -> str:
    """Swap whole words for synonyms with probability p each (templates only, before ids are filled)."""
    def swap(m):
        w = m.group(0)
        opts = T.SYNONYMS.get(w)
        return rng.choice(opts) if opts and rng.random() < p else w
    import re as _re
    return _re.sub(r"[А-Яа-яЁё]+", swap, text)


def _fill(ctx: _Ctx, tpl: T.Template, values: dict[str, str], amount: int, paraphrase: float = 0.0) -> tuple[str, str]:
    rng = ctx.rng
    if paraphrase:
        tpl = (_paraphrase(rng, tpl[0], paraphrase), tpl[1])
    ru_amt, en_amt = fmt_amount(amount, rng)
    ru_vals, en_vals = dict(values), dict(values)
    for k in ("phone", "phone2", "hub"):
        if k in values:
            ru_vals[k] = fmt_phone(values[k], rng)
            en_vals[k] = ru_vals[k]
    for k in ("card", "card2"):
        if k in values:
            ru_vals[k] = fmt_card(values[k], rng)
            en_vals[k] = mask(values[k])
    ru_vals["amount"], en_vals["amount"] = ru_amt, en_amt
    ru, en = tpl
    ru, en = ru.format(**ru_vals), en.format(**en_vals)
    if ctx.hard and rng.random() < 0.35:
        for good, bad in T.TYPOS.items():
            if good in ru and rng.random() < 0.5:
                ru = ru.replace(good, bad, 1)
    return ru, en


def _transfer(ctx: _Ctx, src: str, dst: str, when: date) -> None:
    amt = ctx.rng.randrange(300, 3000) * 1000
    at = datetime(when.year, when.month, when.day, ctx.rng.randrange(8, 23), ctx.rng.randrange(60))
    ctx.transfers.append(Transfer(src=src, dst=dst, amount_kzt=amt, at=at))


def _campaign(ctx: _Ctx, label: str, tactic: str, mechanic: str, size: int) -> list[Draft]:
    rng, ids = ctx.rng, ctx.ids
    start = YEAR_START + timedelta(days=rng.randrange(0, YEAR_DAYS - 60))
    span = rng.randrange(30, 60)
    regions = rng.sample(REGIONS, rng.randrange(3, 7))
    scripts = T.HARD_EXTRA_SCRIPT if label == "H" else T.CAMPAIGN_SCRIPTS[tactic]
    end = start + timedelta(days=span)

    shared_card = ids.card()
    cashout = ids.card()
    pool = [ids.phone() for _ in range(4)]
    domain = ids.domain(".example")
    chain_cards = [ids.card() for _ in range(4)]
    mid_cards = [ids.card(), ids.card()]
    mules = [ids.card(), ids.card()]

    if mechanic in ("shared_card",):
        _transfer(ctx, mask(shared_card), mask(cashout), end)
    if mechanic == "chain":
        _transfer(ctx, mask(chain_cards[0]), mask(mid_cards[0]), end)
        _transfer(ctx, mask(chain_cards[1]), mask(mid_cards[0]), end)
        _transfer(ctx, mask(chain_cards[2]), mask(mid_cards[1]), end)
        _transfer(ctx, mask(chain_cards[3]), mask(mid_cards[1]), end)
        _transfer(ctx, mask(mid_cards[0]), mask(cashout), end)
        _transfer(ctx, mask(mid_cards[1]), mask(cashout), end)
    if mechanic == "two_mules":
        _transfer(ctx, mask(mules[0]), mask(cashout), end)
        _transfer(ctx, mask(mules[1]), mask(cashout), end)

    out = []
    for i in range(size):
        values: dict[str, str] = {"phone": ids.phone(), "card": ids.card(), "iban": ids.iban()}
        if mechanic == "shared_card":
            values["card"] = shared_card
        elif mechanic == "phone_pool":
            values["phone"] = pool[i % len(pool)]
            values["phone2"] = pool[(i + 1) % len(pool)]
        elif mechanic == "domain":
            path = rng.choice(["verify", "status", "check", "loan"]) + "?id=" + str(rng.randrange(10000, 99999))
            values["url"] = f"https://{domain}/{path}"
        elif mechanic == "chain":
            values["card"] = chain_cards[i % 4]
        elif mechanic == "two_mules":
            values["card"] = mules[i % 2]
        amount = rand_amount(rng)
        tpl = rng.choice(scripts)
        if ctx.hard and rng.random() < 0.15:  # the victim lost the number / card: only the script remains
            tpl = (tpl[0].replace("{phone}", "(номер не определился)").replace("{card}", "(номер карты не сохранился)")
                   .replace("{iban}", "(реквизиты не сохранились)"),
                   tpl[1].replace("{phone}", "(number not shown)").replace("{card}", "(card number not kept)")
                   .replace("{iban}", "(details not kept)"))
        ru, en = _fill(ctx, tpl, values, amount, paraphrase=0.3 if ctx.hard else 0.0)
        out.append(Draft(label, tactic, start + timedelta(days=rng.randrange(span)), rng.choice(regions),
                         amount, ru, en, rng.random(), rng.choice(AGE_BANDS)))
    return out


def _noise(ctx: _Ctx, count: int) -> list[Draft]:
    rng, ids = ctx.rng, ctx.ids
    out = []
    tactics = list(T.GENERIC)
    for _ in range(count):
        tactic = rng.choice(tactics)
        body = rng.choice(T.VAGUE) if rng.random() < 0.15 else \
            rng.choice(T.GENERIC[tactic] + T.GENERIC_EXTRA[tactic])
        parts = [rng.choice(T.OPENINGS)] + rng.sample(T.DETAILS, 2)
        rng.shuffle(parts)
        parts.insert(rng.randrange(len(parts) + 1), body)
        parts.append(rng.choice(T.ENDINGS))
        tpl = (" ".join(p[0] for p in parts if p[0]), " ".join(p[1] for p in parts if p[1]))
        values = {"phone": ids.phone(), "card": ids.card(), "iban": ids.iban(),
                  "url": f"https://{ids.domain('.test')}/{rng.choice(['login', 'pay', 'form'])}"}
        amount = rand_amount(rng)
        ru, en = _fill(ctx, tpl, values, amount, paraphrase=0.6)
        out.append(Draft(None, tactic, YEAR_START + timedelta(days=rng.randrange(YEAR_DAYS)),
                         rng.choice(REGIONS), amount, ru, en, rng.random(), rng.choice(AGE_BANDS)))
    return out


def _add_hub_mentions(ctx: _Ctx, drafts: list[Draft], k: int = 14) -> None:
    rng = ctx.rng
    by_tactic: dict[str, list[Draft]] = {}
    for d in drafts:
        by_tactic.setdefault(d.tactic, []).append(d)
    chosen: list[Draft] = []
    tactics = sorted(by_tactic)
    i = 0
    while len(chosen) < k:
        pool = [d for d in by_tactic[tactics[i % len(tactics)]] if d not in chosen]
        if pool:
            chosen.append(rng.choice(pool))
        i += 1
    for d in chosen:
        ru, en = rng.choice(T.HUB_SENTENCES)
        hub = fmt_phone(HUB_E164, rng)
        d.text += ru.format(hub=hub)
        d.text_en += en.format(hub=hub)


def generate(seed: int = 1, n: int = 250, hard: bool = False) -> Dataset:
    rng = random.Random(seed)
    ctx = _Ctx(rng=rng, ids=Ids(rng), hard=hard)
    specs = list(CAMPAIGNS) + ([HARD_EXTRA] if hard else [])
    noise_n = round(0.25 * n)
    budget = n - noise_n
    total_w = sum(s[2] for s in specs)
    sizes = [max(3, budget * s[2] // total_w) for s in specs]
    sizes[0] += budget - sum(sizes)

    drafts: list[Draft] = []
    for (label, tactic, _w, mechanic), size in zip(specs, sizes):
        drafts += _campaign(ctx, label, tactic, mechanic, size)
    drafts += _noise(ctx, noise_n)
    _add_hub_mentions(ctx, drafts)

    drafts.sort(key=lambda d: (d.filed_at, d.order))
    complaints: list[Complaint] = []
    truth: dict[str, list[str]] = {}
    for i, d in enumerate(drafts, 1):
        cid = f"CMP-{i:04d}"
        complaints.append(Complaint(cid, d.filed_at, d.region, T.CHANNEL[d.tactic], d.amount,
                                    d.text, d.text_en, d.age))
        if d.label:
            truth.setdefault(d.label, []).append(cid)
    ctx.transfers.sort(key=lambda t: (t.at, t.src))
    return Dataset(complaints=complaints, transfers=ctx.transfers, truth=dict(sorted(truth.items())))


def write_dataset(ds: Dataset, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    from ..privacy import redact
    with open(out_dir / "complaints.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for c in ds.complaints:
            d = c.to_json()
            d["text"] = redact(d["text"])
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open(out_dir / "bank_transfers.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for t in ds.transfers:
            f.write(json.dumps(t.to_json(), ensure_ascii=False) + "\n")
    with open(out_dir / "ground_truth.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(ds.truth, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_dataset(raw_dir: Path) -> Dataset:
    raw_dir = Path(raw_dir)
    complaints = []
    with open(raw_dir / "complaints.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            d["filed_at"] = date.fromisoformat(d["filed_at"])
            complaints.append(Complaint(**d))
    transfers = []
    with open(raw_dir / "bank_transfers.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            d["at"] = datetime.fromisoformat(d["at"])
            transfers.append(Transfer(**d))
    truth = json.loads((raw_dir / "ground_truth.json").read_text(encoding="utf-8"))
    return Dataset(complaints, transfers, truth)
