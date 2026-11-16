"""Parse FTC Do Not Call complaint CSVs (US public data) into Report records."""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

TOLL_FREE = {"800", "833", "844", "855", "866", "877", "888"}

# (keyword regex, code, English label) — FTC's own subject categories
SUBJECTS: list[tuple[str, str, str]] = [
    (r"debt", "DEBT", "Reducing debt (credit cards, mortgage, student loans)"),
    (r"government", "IMPOSTER_GOV", "Pretending to be government, business, family or friends"),
    (r"medical|prescription", "MEDICAL", "Medical & prescriptions"),
    (r"warrant", "WARRANTY", "Warranties & protection plans"),
    (r"home improvement|cleaning", "HOME", "Home improvement & cleaning"),
    (r"dropped call|no message", "DROPPED", "Dropped call or no message"),
    (r"vacation|timeshare", "TRAVEL", "Vacation & timeshares"),
    (r"lotter|prize|sweepstake", "PRIZES", "Lotteries, prizes & sweepstakes"),
    (r"energy|solar|utilit", "ENERGY", "Energy, solar & utilities"),
    (r"computer|technical support", "TECH", "Computer & technical support"),
    (r"work from home|business opportunit", "WORK", "Work from home & business opportunities"),
    (r"no subject", "NONE", "No subject provided"),
]
SUBJECT_LABEL = {code: label for _, code, label in SUBJECTS} | {"OTHER": "Other"}


def subject_code(label: str) -> str:
    low = label.lower()
    for rx, code, _ in SUBJECTS:
        if re.search(rx, low):
            return code
    return "OTHER"


@dataclass
class Report:
    id: str
    number: str
    npa: str
    nxx: str
    created: str
    violation_day: str
    city: str
    state: str
    victim_npa: str
    subject: str
    robocall: bool | None
    neighbor: bool
    toll_free: bool

    @property
    def created_day(self) -> str:
        return self.created[:10]


def _number(raw: str) -> str | None:
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    return d if len(d) == 10 and d[0] not in "01" else None


def parse_row(row: list[str], file_key: str, line_no: int) -> Report | None:
    if len(row) < 8:
        return None
    if len(row) > 8:  # an unquoted subject with commas spills into extra columns
        row = row[:6] + [",".join(row[6:-1]), row[-1]]
    number = _number(row[0])
    if not number:
        return None
    victim_npa = re.sub(r"\D", "", row[5])[:3]
    flag = row[7].strip().upper()
    rid = hashlib.blake2b(f"{file_key}:{line_no}".encode(), digest_size=6).hexdigest()
    return Report(
        id=rid, number=number, npa=number[:3], nxx=number[3:6], created=row[1].strip(),
        violation_day=row[2].strip()[:10], city=row[3].strip().title(), state=row[4].strip(),
        victim_npa=victim_npa, subject=subject_code(row[6]),
        robocall=True if flag == "Y" else False if flag == "N" else None,
        neighbor=bool(victim_npa) and number[:3] == victim_npa, toll_free=number[:3] in TOLL_FREE,
    )


def read_reports(paths: Iterable[Path]) -> Iterator[Report]:
    for path in sorted(Path(p) for p in paths):
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for i, row in enumerate(reader, 1):
                r = parse_row(row, path.name.split(".")[0], i)
                if r:
                    yield r
