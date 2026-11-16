"""Download the FTC's daily Do Not Call complaint files (US public data) as gzip."""
from __future__ import annotations

import gzip
import re
import urllib.request
from pathlib import Path
from typing import Callable

INDEX_URL = "https://www.ftc.gov/policy-notices/open-government/data-sets/do-not-call-data"
BASE = "https://www.ftc.gov"
_LINK = re.compile(r"/sites/default/files/DNC_Complaint_Numbers_\d{4}-\d{2}-\d{2}\.csv")


def _http_get(url: str) -> str:
    # ftc.gov answers 404 to requests without an Accept header
    req = urllib.request.Request(url, headers={"User-Agent": "dropnet-research/0.1", "Accept": "text/html,text/csv,*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def csv_links(page_html: str) -> list[str]:
    return sorted({BASE + m.group(0) for m in _LINK.finditer(page_html)})


def fetch(out_dir: Path, days: int | None = None, get: Callable[[str], str] = _http_get) -> list[Path]:
    """Download (once) the most recent `days` daily files listed on the FTC page; return all local paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    links = csv_links(get(INDEX_URL))
    if days:
        links = links[-days:]
    paths = []
    for url in links:
        p = out_dir / (url.rsplit("/", 1)[1] + ".gz")
        if not p.exists():
            with gzip.open(p, "wt", encoding="utf-8", newline="") as f:
                f.write(get(url))
        paths.append(p)
    return paths
