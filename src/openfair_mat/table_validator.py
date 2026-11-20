"""CSV and JSON materials property table physical, NaN/Inf, and unit-consistency validator."""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any

from openfair_mat.models import FileValidationResult, Severity, ValidationIssue
from openfair_mat.utils import compute_sha256, parse_finite_float

_NONFINITE_STRINGS = {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}
_INLINE_VALUE_UNIT_RE = re.compile(
    r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z°Åµμ/]+)\s*$"
)

# Canonical unit mapping: raw lowercase token -> (dimension, canonical_symbol)
_UNIT_CANONICAL: dict[str, tuple[str, str]] = {
    "ev": ("energy", "eV"),
    "mev": ("energy", "meV"),
    "kj/mol": ("energy", "kJ/mol"),
    "ha": ("energy", "Ha"),
    "hartree": ("energy", "Ha"),
    "ry": ("energy", "Ry"),
    "k": ("temperature", "K"),
    "kelvin": ("temperature", "K"),
    "c": ("temperature", "C"),
    "°c": ("temperature", "C"),
    "degc": ("temperature", "C"),
    "celsius": ("temperature", "C"),
    "a": ("length", "Å"),
    "å": ("length", "Å"),
    "ang": ("length", "Å"),
    "angstrom": ("length", "Å"),
    "angstroms": ("length", "Å"),
    "nm": ("length", "nm"),
    "nanometer": ("length", "nm"),
    "nanometers": ("length", "nm"),
    "pm": ("length", "pm"),
    "g/cm3": ("density", "g/cm3"),
    "g/cm^3": ("density", "g/cm3"),
    "kg/m3": ("density", "kg/m3"),
    "gpa": ("pressure", "GPa"),
    "mpa": ("pressure", "MPa"),
}

_HEADER_UNIT_SUFFIXES: list[tuple[str, str, str, bool]] = [
    ("_mev", "energy", "meV", False),
    ("_ev", "energy", "eV", False),
    ("_K", "temperature", "K", True),
    ("_C", "temperature", "C", True),
    ("_degc", "temperature", "C", False),
    ("_nm", "length", "nm", False),
    ("_A", "length", "Å", True),
    ("_ang", "length", "Å", False),
    ("_angstrom", "length", "Å", False),
    ("_g_cm3", "density", "g/cm3", False),
    ("_kg_m3", "density", "kg/m3", False),
    ("_gpa", "pressure", "GPa", False),
]


def _canonicalize_unit(raw: object) -> tuple[str, str] | None:
    """Normalize a raw unit string into (dimension, canonical_unit)."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    return _UNIT_CANONICAL.get(text)


def _header_unit_hint(col_name: str) -> tuple[str, str] | None:
    """Extract expected (dimension, canonical_unit) from a column header suffix."""
    stripped = col_name.strip()
    lower = stripped.lower()
    for suffix, dim, unit, case_sensitive in _HEADER_UNIT_SUFFIXES:
        if case_sensitive:
            if stripped.endswith(suffix):
                return dim, unit
        elif lower.endswith(suffix):
            return dim, unit
    return None


def _is_unit_column(col_name: str) -> bool:
    """Return True if column name represents a unit annotation field."""
    lower = col_name.strip().lower()
    return lower in {"unit", "units"} or lower.endswith("_unit") or lower.endswith("_units")


def _extract_numeric_and_inline_unit(raw: object) -> tuple[float | None, tuple[str, str] | None, bool]:
    """Parse cell into (numeric_value, inline_unit, is_explicit_nonfinite)."""
    if raw is None or isinstance(raw, bool):
        return None, None, False
    if isinstance(raw, (int, float)):
        val = float(raw)
        if not math.isfinite(val):
            return None, None, True
        return val, None, False

    text = str(raw).strip()
    if not text:
        return None, None, False
    if text.lower() in _NONFINITE_STRINGS:
        return None, None, True

    val = parse_finite_float(text)
    if val is not None:
        return val, None, False

    match = _INLINE_VALUE_UNIT_RE.match(text)
    if match:
        num = parse_finite_float(match.group(1))
        unit_info = _canonicalize_unit(match.group(2))
        if num is not None and unit_info is not None:
            return num, unit_info, False
    return None, None, False


def _load_csv_rows(path: Path, issues: list[ValidationIssue]) -> tuple[list[str], list[tuple[int, dict[str, Any]]]]:
    """Load CSV records with 1-based line numbers."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            issues.append(
                ValidationIssue(
                    code="TABLE_EMPTY_FILE",
                    severity=Severity.ERROR,
                    message="CSV file has no header row.",
                    line=1,
                )
            )
            return [], []
        headers = [h.strip() for h in reader.fieldnames]
        rows: list[tuple[int, dict[str, Any]]] = []
        for row_idx, row in enumerate(reader, start=2):
            if None in row:
                issues.append(
                    ValidationIssue(
                        code="TABLE_MALFORMED_ROW",
                        severity=Severity.ERROR,
                        message=f"Row {row_idx} has extra columns beyond CSV header.",
                        line=row_idx,
                    )
                )
            cleaned = {k.strip(): v for k, v in row.items() if k is not None}
            rows.append((row_idx, cleaned))
        return headers, rows


def _load_json_rows(path: Path, issues: list[ValidationIssue]) -> tuple[list[str], list[tuple[int, dict[str, Any]]]]:
    """Load JSON property records while detecting non-standard NaN/Infinity constants."""
    nonfinite_hits: list[str] = []

    def _capture_constant(token: str) -> float:
        nonfinite_hits.append(token)
        return float("nan") if "nan" in token.lower() else float("inf")

    raw_text = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        payload = json.loads(raw_text, parse_constant=_capture_constant)
    except json.JSONDecodeError as exc:
        issues.append(
            ValidationIssue(
                code="TABLE_PARSE_ERROR",
                severity=Severity.ERROR,
                message=f"Invalid JSON syntax: {exc.msg} (line {exc.lineno}).",
                line=exc.lineno,
            )
        )
        return [], []

    if nonfinite_hits:
        issues.append(
            ValidationIssue(
                code="TABLE_NONFINITE_VALUE",
                severity=Severity.ERROR,
                message=f"JSON contains non-finite numeric constants: {', '.join(sorted(set(nonfinite_hits)))}.",
                line=1,
            )
        )

    records: list[Any]
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        extracted = None
        for key in ("records", "data", "items", "entries", "materials"):
            if isinstance(payload.get(key), list):
                extracted = payload[key]
                break
        records = extracted if extracted is not None else [payload]
    else:
        issues.append(
            ValidationIssue(
                code="TABLE_UNSUPPORTED_JSON",
                severity=Severity.ERROR,
                message="JSON root must be an object or array of property objects.",
                line=1,
            )
        )
        return [], []

    rows: list[tuple[int, dict[str, Any]]] = []
    headers_seen: list[str] = []
    for idx, item in enumerate(records, start=1):
        if not isinstance(item, dict):
            issues.append(
                ValidationIssue(
                    code="TABLE_MALFORMED_ROW",
                    severity=Severity.ERROR,
                    message=f"Record {idx} in JSON array is not an object.",
                    line=idx,
                )
            )
            continue
        for key in item:
            if key not in headers_seen:
                headers_seen.append(key)
        rows.append((idx, item))

    return headers_seen, rows


def _row_unit_for_dimension(row: dict[str, Any], dimension: str) -> str | None:
    """Resolve an explicit unit annotation in the same row matching a physical dimension."""
    for col, raw_val in row.items():
        if not _is_unit_column(col):
            continue
        parsed = _canonicalize_unit(raw_val)
        if parsed and parsed[0] == dimension:
            return parsed[1]
    return None


def _check_physical_bounds(
    col: str,
    val: float,
    row_line: int,
    row: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    """Check physical plausibility rules for density, band gap, temperature, moduli, and geometry."""
    lower = col.strip().lower()

    if "density" in lower:
        if val < 0.0:
            issues.append(
                ValidationIssue(
                    code="TABLE_IMPOSSIBLE_NEGATIVE_DENSITY",
                    severity=Severity.ERROR,
                    message=f"Row {row_line} '{col}' cannot be negative (got {val}).",
                    line=row_line,
                    field=col,
                )
            )
        elif val == 0.0:
            issues.append(
                ValidationIssue(
                    code="TABLE_ZERO_DENSITY",
                    severity=Severity.WARNING,
                    message=f"Row {row_line} '{col}' is 0.0; verify whether empty structure was intended.",
                    line=row_line,
                    field=col,
                )
            )
        return

    if "band_gap" in lower or "bandgap" in lower or lower in {"eg", "e_g"}:
        if val < 0.0:
            issues.append(
                ValidationIssue(
                    code="TABLE_IMPOSSIBLE_NEGATIVE_BANDGAP",
                    severity=Severity.ERROR,
                    message=f"Row {row_line} '{col}' electronic band gap cannot be negative (got {val}).",
                    line=row_line,
                    field=col,
                )
            )
        return

    if any(tok in lower for tok in ("bulk_modulus", "shear_modulus", "youngs_modulus", "young_modulus")):
        if val < 0.0:
            issues.append(
                ValidationIssue(
                    code="TABLE_IMPOSSIBLE_NEGATIVE_MODULUS",
                    severity=Severity.ERROR,
                    message=f"Row {row_line} '{col}' elastic modulus cannot be negative (got {val}).",
                    line=row_line,
                    field=col,
                )
            )
        return

    if "occupancy" in lower:
        if not (0.0 <= val <= 1.0):
            issues.append(
                ValidationIssue(
                    code="TABLE_IMPOSSIBLE_OCCUPANCY",
                    severity=Severity.ERROR,
                    message=f"Row {row_line} '{col}' occupancy must be in [0, 1] (got {val}).",
                    line=row_line,
                    field=col,
                )
            )
        return

    if any(tok in lower for tok in ("lattice_a", "lattice_b", "lattice_c", "cell_volume", "volume")):
        if val <= 0.0:
            issues.append(
                ValidationIssue(
                    code="TABLE_IMPOSSIBLE_NONPOSITIVE_GEOMETRY",
                    severity=Severity.ERROR,
                    message=f"Row {row_line} '{col}' geometric length/volume must be > 0 (got {val}).",
                    line=row_line,
                    field=col,
                )
            )
        return

    if "temp" in lower:
        hint = _header_unit_hint(col)
        unit = hint[1] if hint and hint[0] == "temperature" else _row_unit_for_dimension(row, "temperature")
        if unit == "K" and val < 0.0:
            issues.append(
                ValidationIssue(
                    code="TABLE_IMPOSSIBLE_SUBZERO_KELVIN",
                    severity=Severity.ERROR,
                    message=f"Row {row_line} '{col}' temperature in Kelvin cannot be < 0 K (got {val}).",
                    line=row_line,
                    field=col,
                )
            )
        elif unit == "C" and val < -273.15:
            issues.append(
                ValidationIssue(
                    code="TABLE_IMPOSSIBLE_BELOW_ABSOLUTE_ZERO",
                    severity=Severity.ERROR,
                    message=f"Row {row_line} '{col}' temperature in Celsius is below -273.15 C (got {val}).",
                    line=row_line,
                    field=col,
                )
            )


def _check_unit_consistency(
    headers: list[str],
    rows: list[tuple[int, dict[str, Any]]],
    inline_units_by_col: dict[str, set[str]],
    issues: list[ValidationIssue],
) -> dict[str, list[str]]:
    """Detect mixed or conflicting units (eV vs meV, K vs C, Å vs nm) across columns and rows."""
    observed_units: dict[str, set[str]] = {}

    for col in headers:
        if not _is_unit_column(col):
            continue
        units_seen: set[str] = set()
        raw_seen: set[str] = set()
        for _, row in rows:
            raw_val = row.get(col)
            if raw_val is None or str(raw_val).strip() == "":
                continue
            raw_text = str(raw_val).strip()
            raw_seen.add(raw_text)
            canon = _canonicalize_unit(raw_text)
            units_seen.add(canon[1] if canon else raw_text)
        if units_seen:
            observed_units[col] = units_seen
        if len(units_seen) > 1:
            issues.append(
                ValidationIssue(
                    code="TABLE_MIXED_UNITS",
                    severity=Severity.WARNING,
                    message=(
                        f"Mixed units detected in column '{col}': {', '.join(sorted(units_seen))}. "
                        "Normalize to a single canonical unit before deposit."
                    ),
                    line=1,
                    field=col,
                )
            )

    for col, units in inline_units_by_col.items():
        if len(units) > 1:
            issues.append(
                ValidationIssue(
                    code="TABLE_MIXED_UNITS",
                    severity=Severity.WARNING,
                    message=(
                        f"Mixed inline units detected in values of '{col}': {', '.join(sorted(units))}."
                    ),
                    line=1,
                    field=col,
                )
            )

    # Detect header unit suffix vs row unit column mismatches (e.g. band_gap_eV + energy_unit='meV')
    for col in headers:
        hint = _header_unit_hint(col)
        if hint is None:
            continue
        dim, expected_unit = hint
        for row_line, row in rows:
            val = row.get(col)
            if val is None or str(val).strip() == "":
                continue
            row_unit = _row_unit_for_dimension(row, dim)
            if row_unit is not None and row_unit != expected_unit:
                issues.append(
                    ValidationIssue(
                        code="TABLE_UNIT_HEADER_MISMATCH",
                        severity=Severity.WARNING,
                        message=(
                            f"Row {row_line} column '{col}' header implies '{expected_unit}', "
                            f"but row unit column declares '{row_unit}'."
                        ),
                        line=row_line,
                        field=col,
                    )
                )

    # Detect same-property parallel columns with conflicting unit suffixes
    by_base_dim: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for col in headers:
        hint = _header_unit_hint(col)
        if hint is None:
            continue
        dim, unit = hint
        lower = col.strip().lower()
        base = re.sub(r"_(mev|ev|k|c|degc|nm|a|ang|angstrom|g_cm3|kg_m3|gpa)$", "", lower)
        by_base_dim.setdefault((base, dim), []).append((col, unit))
    for (base, dim), cols in by_base_dim.items():
        if len({u for _, u in cols}) > 1:
            col_names = ", ".join(c for c, _ in cols)
            issues.append(
                ValidationIssue(
                    code="TABLE_INCONSISTENT_UNIT_COLUMNS",
                    severity=Severity.WARNING,
                    message=f"Parallel {dim} columns for '{base}' use mixed units: {col_names}.",
                    line=1,
                    field=base,
                )
            )

    return {k: sorted(v) for k, v in observed_units.items()}


def validate_table(path: Path) -> FileValidationResult:
    """Validate a CSV or JSON materials property table."""
    ext = path.suffix.lower()
    file_format = "json" if ext == ".json" else "csv"
    sha256 = compute_sha256(path)
    size_bytes = path.stat().st_size
    issues: list[ValidationIssue] = []

    if file_format == "csv":
        headers, rows = _load_csv_rows(path, issues)
    else:
        headers, rows = _load_json_rows(path, issues)

    if not rows and not any(i.severity == Severity.ERROR for i in issues):
        issues.append(
            ValidationIssue(
                code="TABLE_NO_RECORDS",
                severity=Severity.ERROR,
                message=f"No property rows found in {file_format.upper()} file.",
                line=1,
            )
        )

    inline_units_by_col: dict[str, set[str]] = {}
    for row_line, row in rows:
        for col in headers:
            if _is_unit_column(col):
                continue
            raw_val = row.get(col)
            num_val, inline_unit, is_nonfinite = _extract_numeric_and_inline_unit(raw_val)
            if is_nonfinite:
                issues.append(
                    ValidationIssue(
                        code="TABLE_NONFINITE_VALUE",
                        severity=Severity.ERROR,
                        message=f"Row {row_line} '{col}' contains NaN/Inf value '{raw_val}'.",
                        line=row_line,
                        field=col,
                    )
                )
                continue
            if inline_unit is not None:
                inline_units_by_col.setdefault(col, set()).add(inline_unit[1])
            if num_val is not None:
                _check_physical_bounds(col, num_val, row_line, row, issues)

    observed_units = _check_unit_consistency(headers, rows, inline_units_by_col, issues)

    return FileValidationResult(
        path=str(path),
        file_format=file_format,
        sha256=sha256,
        size_bytes=size_bytes,
        issues=issues,
        metadata={
            "row_count": len(rows),
            "columns": headers,
            "observed_units": observed_units,
        },
    )
