from __future__ import annotations

from typing import Any


def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        if val in (None, "", "NA", "nan", "NaN"):
            return default
        s = str(val).strip()
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        return float(s)
    except (TypeError, ValueError):
        return default


def safe_int(val: Any, default: int = 0) -> int:
    try:
        if val in (None, "", "NA", "nan", "NaN"):
            return default
        return int(float(str(val).replace(",", ".")))
    except (TypeError, ValueError):
        return default
