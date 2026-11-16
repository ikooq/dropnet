"""Paths and domain constants shared by every Dropnet module."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "dropnet.rl"
LIVE_PATH = DATA_DIR / "live" / "dropnet.rl"
RAW_DIR = DATA_DIR / "raw"

VECTOR_DIM = 256
VECTOR_INDEX = "complaint_script"

# code -> (label_ru, label_en)
TACTICS: dict[str, tuple[str, str]] = {
    "BANK_SECURITY": ("Служба безопасности банка", "Fake bank security call"),
    "SAFE_ACCOUNT": ("Безопасный счёт", "'Safe account' transfer"),
    "LOAN_STATUS_SMS": ("SMS о статусе займа", "Phishing SMS about a loan"),
    "MARKETPLACE_PREPAY": ("Предоплата на маркетплейсе", "Marketplace prepayment"),
    "POLICE_THREAT": ("Угрозы от имени полиции", "Fake police threat"),
    "INVESTMENT": ("Инвестиции с гарантией дохода", "Fake investment platform"),
    "ATM_DROP_HELP": ("Помощь с переводом у банкомата", "Money-mule request at an ATM"),
}

REGIONS: list[str] = [
    "Astana", "Almaty", "Shymkent", "Pavlodar", "Karaganda", "Aktobe", "Atyrau",
    "Kostanay", "Oskemen", "Semey", "Taraz", "Kyzylorda", "Aktau", "Petropavl",
    "Oral", "Turkistan", "Taldykorgan",
]

BANKS: list[str] = ["Demo Bank A", "Demo Bank B", "Demo Bank C", "Demo Bank D"]

# Linking thresholds (tuned on seed 1 only; see dropnet.evaluate).
SIMILARITY_K = 15  # top-5 was filled by near-verbatim copies, hiding links between script variants
SIMILARITY_THRESHOLD = 0.80        # attach a loose complaint to an existing campaign (needs 2 votes)
SCRIPT_ONLY_THRESHOLD = 0.90       # form a brand-new campaign from script similarity alone
MAX_FORWARD_HOPS = 3
HUB_MIN_TACTICS = 3
HUB_MIN_REGIONS = 4
