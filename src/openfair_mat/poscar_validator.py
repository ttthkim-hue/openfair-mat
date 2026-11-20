"""VASP POSCAR/CONTCAR physical cell volume and atom-count validator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openfair_mat.models import FileValidationResult, Severity, ValidationIssue
from openfair_mat.utils import compute_sha256, det3x3, parse_finite_float


def _parse_int_tokens(tokens: list[str]) -> list[int] | None:
    """Parse list of strings as integers, returning None if any token is not an integer."""
    parsed: list[int] = []
    for tok in tokens:
        try:
            if "." in tok or "e" in tok.lower():
                return None
            parsed.append(int(tok))
        except ValueError:
            return None
    return parsed


def validate_poscar(path: Path) -> FileValidationResult:
    """Validate VASP POSCAR/CONTCAR 3x3 determinant volume > 0 and atom coordinate count."""
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    sha256 = compute_sha256(path)
    size_bytes = path.stat().st_size
    issues: list[ValidationIssue] = []

    if len(raw_lines) < 8:
        issues.append(
            ValidationIssue(
                code="POSCAR_TOO_SHORT",
                severity=Severity.ERROR,
                message=f"POSCAR requires at least 8 lines (got {len(raw_lines)}).",
                line=1,
            )
        )
        return FileValidationResult(
            path=str(path),
            file_format="poscar",
            sha256=sha256,
            size_bytes=size_bytes,
            issues=issues,
            metadata={},
        )

    comment = raw_lines[0].strip()
    if not comment:
        issues.append(
            ValidationIssue(
                code="POSCAR_EMPTY_COMMENT",
                severity=Severity.WARNING,
                message="Line 1 comment/title is empty; descriptive title recommended for FAIR metadata.",
                line=1,
            )
        )

    scale = parse_finite_float(raw_lines[1])
    if scale is None:
        issues.append(
            ValidationIssue(
                code="POSCAR_INVALID_SCALE",
                severity=Severity.ERROR,
                message=f"Line 2 universal scaling factor is invalid: '{raw_lines[1].strip()}'.",
                line=2,
            )
        )
    elif scale <= 0.0:
        issues.append(
            ValidationIssue(
                code="POSCAR_NONPOSITIVE_SCALE",
                severity=Severity.ERROR,
                message=f"Line 2 universal scaling factor must be > 0 (got {scale}).",
                line=2,
            )
        )

    lattice: list[list[float]] = []
    for offset in range(3):
        line_no = 3 + offset
        parts = raw_lines[2 + offset].split()
        if len(parts) < 3:
            issues.append(
                ValidationIssue(
                    code="POSCAR_INVALID_LATTICE",
                    severity=Severity.ERROR,
                    message=f"Lattice vector on line {line_no} requires 3 numeric components.",
                    line=line_no,
                )
            )
            continue
        vec = [parse_finite_float(parts[j]) for j in range(3)]
        if any(v is None for v in vec):
            issues.append(
                ValidationIssue(
                    code="POSCAR_INVALID_LATTICE",
                    severity=Severity.ERROR,
                    message=f"Lattice vector on line {line_no} contains non-finite or non-numeric entries.",
                    line=line_no,
                )
            )
            continue
        lattice.append([v for v in vec if v is not None])

    cell_volume: float | None = None
    if len(lattice) == 3 and scale is not None and scale > 0.0:
        det = det3x3(lattice)
        cell_volume = det * (scale ** 3)
        if cell_volume <= 1e-12:
            issues.append(
                ValidationIssue(
                    code="POSCAR_NONPOSITIVE_VOLUME",
                    severity=Severity.ERROR,
                    message=f"3x3 lattice determinant cell volume must be > 0 (got {cell_volume:.6g} A^3).",
                    line=3,
                )
            )

    line6_tokens = raw_lines[5].split()
    if not line6_tokens:
        issues.append(
            ValidationIssue(
                code="POSCAR_MISSING_SPECIES_OR_COUNTS",
                severity=Severity.ERROR,
                message="Line 6 is empty; expected element symbols (VASP5) or ion counts (VASP4).",
                line=6,
            )
        )
        return FileValidationResult(
            path=str(path),
            file_format="poscar",
            sha256=sha256,
            size_bytes=size_bytes,
            issues=issues,
            metadata={"cell_volume_A3": cell_volume},
        )

    line6_ints = _parse_int_tokens(line6_tokens)
    species: list[str] = []
    counts: list[int] = []
    vasp_format = "VASP5"
    idx = 6

    if line6_ints is not None:
        vasp_format = "VASP4"
        counts = line6_ints
        issues.append(
            ValidationIssue(
                code="POSCAR_VASP4_MISSING_SPECIES",
                severity=Severity.WARNING,
                message="VASP4 format detected (no element symbols on line 6); VASP5 recommended for NOMAD/MP.",
                line=6,
            )
        )
    else:
        species = line6_tokens
        for sp in species:
            if not sp.isalpha():
                issues.append(
                    ValidationIssue(
                        code="POSCAR_INVALID_SPECIES",
                        severity=Severity.WARNING,
                        message=f"Unexpected element symbol '{sp}' on line 6.",
                        line=6,
                    )
                )
        line7_tokens = raw_lines[6].split()
        parsed_counts = _parse_int_tokens(line7_tokens)
        if parsed_counts is None or not parsed_counts:
            issues.append(
                ValidationIssue(
                    code="POSCAR_INVALID_COUNTS",
                    severity=Severity.ERROR,
                    message=f"Line 7 ion counts must be space-separated integers (got '{raw_lines[6].strip()}').",
                    line=7,
                )
            )
            counts = []
        else:
            counts = parsed_counts
            if len(species) != len(counts):
                issues.append(
                    ValidationIssue(
                        code="POSCAR_SPECIES_COUNT_MISMATCH",
                        severity=Severity.ERROR,
                        message=(
                            f"Number of species ({len(species)}) does not match number of ion counts ({len(counts)})."
                        ),
                        line=7,
                    )
                )
        idx = 7

    if counts:
        if any(c < 0 for c in counts) or sum(counts) <= 0:
            issues.append(
                ValidationIssue(
                    code="POSCAR_INVALID_COUNTS",
                    severity=Severity.ERROR,
                    message=f"Ion counts must be non-negative with total > 0 (got {counts}).",
                    line=idx,
                )
            )

    expected_atoms = sum(c for c in counts if c > 0)
    if idx >= len(raw_lines):
        issues.append(
            ValidationIssue(
                code="POSCAR_MISSING_COORD_MODE",
                severity=Severity.ERROR,
                message="Missing coordinate mode line ('Direct' or 'Cartesian').",
                line=len(raw_lines),
            )
        )
        return FileValidationResult(
            path=str(path),
            file_format="poscar",
            sha256=sha256,
            size_bytes=size_bytes,
            issues=issues,
            metadata={"cell_volume_A3": cell_volume, "vasp_format": vasp_format},
        )

    selective_dynamics = False
    mode_candidate = raw_lines[idx].strip()
    if mode_candidate.lower().startswith("s"):
        selective_dynamics = True
        idx += 1
        if idx >= len(raw_lines):
            issues.append(
                ValidationIssue(
                    code="POSCAR_MISSING_COORD_MODE",
                    severity=Severity.ERROR,
                    message="Missing coordinate mode line after 'Selective dynamics'.",
                    line=len(raw_lines),
                )
            )
            return FileValidationResult(
                path=str(path),
                file_format="poscar",
                sha256=sha256,
                size_bytes=size_bytes,
                issues=issues,
                metadata={"cell_volume_A3": cell_volume, "vasp_format": vasp_format},
            )
        mode_candidate = raw_lines[idx].strip()

    coord_mode = "Unknown"
    first_char = mode_candidate[:1].lower()
    if first_char == "d":
        coord_mode = "Direct"
    elif first_char in ("c", "k"):
        coord_mode = "Cartesian"
    else:
        issues.append(
            ValidationIssue(
                code="POSCAR_INVALID_COORD_MODE",
                severity=Severity.ERROR,
                message=f"Invalid coordinate mode '{mode_candidate}'; expected 'Direct' or 'Cartesian'.",
                line=idx + 1,
            )
        )

    coord_start = idx + 1
    coord_rows: list[str] = []
    for offset, row_text in enumerate(raw_lines[coord_start:]):
        stripped = row_text.strip()
        if not stripped:
            break
        coord_rows.append(stripped)
        line_no = coord_start + offset + 1
        tokens = stripped.split()
        if len(tokens) < 3:
            issues.append(
                ValidationIssue(
                    code="POSCAR_INVALID_COORD",
                    severity=Severity.ERROR,
                    message=f"Coordinate line {line_no} requires at least 3 numeric values.",
                    line=line_no,
                )
            )
            continue
        coords = [parse_finite_float(tokens[j]) for j in range(3)]
        if any(v is None for v in coords):
            issues.append(
                ValidationIssue(
                    code="POSCAR_INVALID_COORD",
                    severity=Severity.ERROR,
                    message=f"Coordinate line {line_no} contains NaN, Inf, or non-numeric values.",
                    line=line_no,
                )
            )
        if selective_dynamics:
            if len(tokens) < 6 or any(flag.upper() not in {"T", "F"} for flag in tokens[3:6]):
                issues.append(
                    ValidationIssue(
                        code="POSCAR_INVALID_SELECTIVE_FLAGS",
                        severity=Severity.ERROR,
                        message=f"Coordinate line {line_no} requires 3 T/F flags under Selective dynamics.",
                        line=line_no,
                    )
                )

    actual_atoms = len(coord_rows)
    if expected_atoms > 0 and actual_atoms != expected_atoms:
        issues.append(
            ValidationIssue(
                code="POSCAR_ATOM_COUNT_MISMATCH",
                severity=Severity.ERROR,
                message=(
                    f"Sum of ion counts ({expected_atoms}) does not match number of coordinate lines ({actual_atoms})."
                ),
                line=coord_start + 1,
            )
        )

    meta: dict[str, Any] = {
        "comment": comment,
        "vasp_format": vasp_format,
        "species": species,
        "counts": counts,
        "expected_atoms": expected_atoms,
        "actual_coord_lines": actual_atoms,
        "coordinate_mode": coord_mode,
        "selective_dynamics": selective_dynamics,
        "cell_volume_A3": round(cell_volume, 6) if cell_volume is not None else None,
    }

    return FileValidationResult(
        path=str(path),
        file_format="poscar",
        sha256=sha256,
        size_bytes=size_bytes,
        issues=issues,
        metadata=meta,
    )
