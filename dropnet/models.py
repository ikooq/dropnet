"""Plain data records passed between pipeline stages."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Literal

ExtractionKind = Literal["phone", "card", "iban", "url", "amount", "tactic", "persona"]


@dataclass
class Complaint:
    id: str
    filed_at: date
    region: str
    channel: str
    amount_kzt: int
    text: str
    text_en: str
    victim_age_band: str

    def to_json(self) -> dict:
        d = asdict(self)
        d["filed_at"] = self.filed_at.isoformat()
        return d


@dataclass
class Transfer:
    src: str
    dst: str
    amount_kzt: int
    at: datetime

    def to_json(self) -> dict:
        d = asdict(self)
        d["at"] = self.at.isoformat()
        return d


@dataclass
class Dataset:
    complaints: list[Complaint]
    transfers: list[Transfer]
    truth: dict[str, list[str]]  # hidden campaign label -> complaint ids


@dataclass
class Extraction:
    complaint_id: str
    kind: ExtractionKind
    value: str
    span_start: int
    span_end: int
    quote: str
    extractor: str = "rules"

    @property
    def id(self) -> str:
        return f"{self.complaint_id}:{self.kind}:{self.span_start}"


@dataclass
class Campaign:
    id: str
    member_ids: list[str]
    confidence: float = 1.0
    size: int = 0
    damage_kzt: int = 0
    regions: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    tactics: list[str] = field(default_factory=list)
