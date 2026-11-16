"""Scam-script vectors without downloading a model: hashed character n-grams.

Character 3-5-grams survive Russian inflection and typos, so two complaints that
retell the same gang's script land close together.
"""
from __future__ import annotations

import hashlib
import math
import re

from .config import VECTOR_DIM

_NON_WORD = re.compile(r"[^a-zа-я ]+")
_SPACES = re.compile(r"\s+")


def _normalize(text: str) -> str:
    t = text.lower().replace("ё", "е")
    t = _NON_WORD.sub(" ", t)
    return _SPACES.sub(" ", t).strip()


def vectorize(text: str, dim: int = VECTOR_DIM) -> list[float]:
    v = [0.0] * dim
    t = _normalize(text)
    if not t:
        return v
    padded = f" {t} "
    for n in (3, 4, 5):
        for i in range(len(padded) - n + 1):
            h = hashlib.blake2b(padded[i:i + n].encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % dim
            v[idx] += 1.0 if h[4] & 1 else -1.0
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v] if norm else v


def cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)
