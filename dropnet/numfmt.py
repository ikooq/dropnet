"""Percentages printed the way the web pages print them.

The pages use JavaScript's `(100 * x).toFixed(1)`, which rounds the exact binary value half up; Python's format
rounds half to even, so 0.0625 printed as 6.2% in the CLI and 6.3% in the browser. `Decimal(100 * x)` is that same
exact binary value, so ROUND_HALF_UP here matches toFixed digit for digit.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def pct_number(x: float, digits: int = 1) -> str:
    return str(Decimal(100 * x).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def pct(x: float, digits: int = 1) -> str:
    return pct_number(x, digits) + "%"
