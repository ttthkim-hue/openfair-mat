"""Shared deterministic helpers for hashing, parsing, and crystallographic math."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

_CIF_UNCERTAINTY_RE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\(\d+\)$")
_NONFINITE_TOKENS = {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}


def compute_sha256(path: Path) -> str:
    """Compute lowercase hexadecimal SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_cif_uncertainty(token: str) -> str:
    """Strip standard CIF parenthesized uncertainty suffix such as '5.4310(2)'."""
    text = token.strip()
    match = _CIF_UNCERTAINTY_RE.match(text)
    if match:
        return match.group(1)
    return text


def parse_finite_float(raw: object, *, allow_cif_uncertainty: bool = False) -> float | None:
    """Parse a finite floating-point number, returning None on NaN, Inf, or invalid text."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if math.isfinite(val) else None

    text = str(raw).strip()
    if not text or text.lower() in _NONFINITE_TOKENS or text in {".", "?"}:
        return None
    if allow_cif_uncertainty:
        text = strip_cif_uncertainty(text)
    try:
        val = float(text)
    except ValueError:
        return None
    return val if math.isfinite(val) else None


def det3x3(matrix: list[list[float]]) -> float:
    """Compute exact determinant of a 3x3 real matrix."""
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
