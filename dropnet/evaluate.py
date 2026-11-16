"""Pairwise clustering quality: did we put the same pairs of complaints together as the ground truth?"""
from __future__ import annotations

from itertools import combinations


def _pairs(groups: dict[str, list[str]]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for members in groups.values():
        out.update(combinations(sorted(set(members)), 2))
    return out


def pairwise(pred: dict[str, list[str]], truth: dict[str, list[str]]) -> dict[str, float]:
    p, t = _pairs(pred), _pairs(truth)
    tp = len(p & t)
    precision = tp / len(p) if p else (1.0 if not t else 0.0)
    recall = tp / len(t) if t else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}
