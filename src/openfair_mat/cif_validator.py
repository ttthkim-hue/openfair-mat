"""CIF (Crystallographic Information File) physical and structural validator."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openfair_mat.models import FileValidationResult, Severity, ValidationIssue
from openfair_mat.utils import compute_sha256, parse_finite_float

_CELL_LENGTH_TAGS = ("_cell_length_a", "_cell_length_b", "_cell_length_c")
_CELL_ANGLE_TAGS = ("_cell_angle_alpha", "_cell_angle_beta", "_cell_angle_gamma")
_SPACE_GROUP_TAGS = (
    "_symmetry_space_group_name_h-m",
    "_space_group_name_h-m_alt",
    "_symmetry_int_tables_number",
    "_space_group_it_number",
)
_FRACT_COORD_TAGS = ("_atom_site_fract_x", "_atom_site_fract_y", "_atom_site_fract_z")
_CARTN_COORD_TAGS = ("_atom_site_cartn_x", "_atom_site_cartn_y", "_atom_site_cartn_z")


@dataclass
class _CifToken:
    value: str
    line: int
    is_quoted: bool = False


@dataclass
class _CifLoop:
    headers: list[str]
    values: list[_CifToken]
    start_line: int


@dataclass
class _CifBlock:
    name: str
    start_line: int
    tags: dict[str, _CifToken] = field(default_factory=dict)
    loops: list[_CifLoop] = field(default_factory=list)


def _tokenize_cif(text: str) -> list[_CifToken]:
    """Tokenize CIF text into tokens while preserving line numbers and quoted/semicolon strings."""
    lines = text.splitlines()
    tokens: list[_CifToken] = []
    idx = 0
    n_lines = len(lines)

    while idx < n_lines:
        raw_line = lines[idx]
        line_no = idx + 1

        if raw_line.startswith(";"):
            block_lines = [raw_line[1:]]
            idx += 1
            while idx < n_lines and not lines[idx].startswith(";"):
                block_lines.append(lines[idx])
                idx += 1
            tokens.append(_CifToken("\n".join(block_lines).strip(), line_no, is_quoted=True))
            idx += 1
            continue

        pos = 0
        length = len(raw_line)
        while pos < length:
            ch = raw_line[pos]
            if ch.isspace():
                pos += 1
                continue
            if ch == "#":
                break
            if ch in ("'", '"'):
                quote = ch
                pos += 1
                start = pos
                while pos < length:
                    if raw_line[pos] == quote and (pos + 1 == length or raw_line[pos + 1].isspace()):
                        break
                    pos += 1
                tokens.append(_CifToken(raw_line[start:pos], line_no, is_quoted=True))
                if pos < length and raw_line[pos] == quote:
                    pos += 1
                continue

            start = pos
            while pos < length and not raw_line[pos].isspace():
                pos += 1
            tokens.append(_CifToken(raw_line[start:pos], line_no, is_quoted=False))
        idx += 1

    return tokens


def _parse_cif_blocks(tokens: list[_CifToken]) -> list[_CifBlock]:
    """Group CIF tokens into data_ blocks with tag-value pairs and loop_ tables."""
    blocks: list[_CifBlock] = []
    current: _CifBlock | None = None
    i = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]
        lower = tok.value.lower() if not tok.is_quoted else ""
        if not tok.is_quoted and lower.startswith("data_"):
            current = _CifBlock(name=tok.value[5:] or "unnamed", start_line=tok.line)
            blocks.append(current)
            i += 1
            continue

        if current is None:
            i += 1
            continue

        if not tok.is_quoted and lower == "loop_":
            loop_line = tok.line
            i += 1
            headers: list[str] = []
            while i < n and not tokens[i].is_quoted and tokens[i].value.startswith("_"):
                headers.append(tokens[i].value.lower())
                i += 1

            values: list[_CifToken] = []
            while i < n:
                nxt = tokens[i]
                nxt_lower = nxt.value.lower() if not nxt.is_quoted else ""
                if not nxt.is_quoted and (
                    nxt_lower.startswith("data_")
                    or nxt_lower == "loop_"
                    or nxt_lower.startswith("_")
                    or nxt_lower.startswith("save_")
                    or nxt_lower == "global_"
                ):
                    break
                values.append(nxt)
                i += 1

            current.loops.append(_CifLoop(headers=headers, values=values, start_line=loop_line))
            continue

        if not tok.is_quoted and tok.value.startswith("_"):
            tag_name = lower
            if i + 1 < n:
                nxt = tokens[i + 1]
                nxt_lower = nxt.value.lower() if not nxt.is_quoted else ""
                if nxt.is_quoted or (
                    not nxt_lower.startswith("_")
                    and not nxt_lower.startswith("data_")
                    and nxt_lower != "loop_"
                ):
                    current.tags[tag_name] = nxt
                    i += 2
                    continue
            current.tags[tag_name] = _CifToken("", tok.line)
            i += 1
            continue

        i += 1

    return blocks


def _validate_cell_geometry(
    block: _CifBlock,
    issues: list[ValidationIssue],
) -> tuple[float | None, dict[str, float]]:
    """Validate CIF lattice parameters (a,b,c > 0 and angles in (0,180)) and compute volume."""
    lengths: dict[str, float] = {}
    angles: dict[str, float] = {}

    for tag in _CELL_LENGTH_TAGS:
        tok = block.tags.get(tag)
        if tok is None or not tok.value:
            issues.append(
                ValidationIssue(
                    code="CIF_MISSING_CELL_PARAM",
                    severity=Severity.ERROR,
                    message=f"Block '{block.name}' missing required lattice length '{tag}'.",
                    line=block.start_line,
                    field=tag,
                )
            )
            continue
        val = parse_finite_float(tok.value, allow_cif_uncertainty=True)
        if val is None:
            issues.append(
                ValidationIssue(
                    code="CIF_INVALID_NUMBER",
                    severity=Severity.ERROR,
                    message=f"Block '{block.name}' has non-numeric/non-finite '{tag}': '{tok.value}'.",
                    line=tok.line,
                    field=tag,
                )
            )
        elif val <= 0.0:
            issues.append(
                ValidationIssue(
                    code="CIF_NONPOSITIVE_LENGTH",
                    severity=Severity.ERROR,
                    message=f"Block '{block.name}' lattice length '{tag}' must be > 0 (got {val}).",
                    line=tok.line,
                    field=tag,
                )
            )
        else:
            lengths[tag] = val

    for tag in _CELL_ANGLE_TAGS:
        tok = block.tags.get(tag)
        if tok is None or not tok.value:
            issues.append(
                ValidationIssue(
                    code="CIF_MISSING_CELL_PARAM",
                    severity=Severity.ERROR,
                    message=f"Block '{block.name}' missing required lattice angle '{tag}'.",
                    line=block.start_line,
                    field=tag,
                )
            )
            continue
        val = parse_finite_float(tok.value, allow_cif_uncertainty=True)
        if val is None:
            issues.append(
                ValidationIssue(
                    code="CIF_INVALID_NUMBER",
                    severity=Severity.ERROR,
                    message=f"Block '{block.name}' has non-numeric/non-finite '{tag}': '{tok.value}'.",
                    line=tok.line,
                    field=tag,
                )
            )
        elif not (0.0 < val < 180.0):
            issues.append(
                ValidationIssue(
                    code="CIF_INVALID_ANGLE",
                    severity=Severity.ERROR,
                    message=f"Block '{block.name}' angle '{tag}' must be strictly in (0, 180) deg (got {val}).",
                    line=tok.line,
                    field=tag,
                )
            )
        else:
            angles[tag] = val

    if len(lengths) == 3 and len(angles) == 3:
        alpha = math.radians(angles["_cell_angle_alpha"])
        beta = math.radians(angles["_cell_angle_beta"])
        gamma = math.radians(angles["_cell_angle_gamma"])
        ca, cb, cg = math.cos(alpha), math.cos(beta), math.cos(gamma)
        metric_disc = 1.0 - ca * ca - cb * cb - cg * cg + 2.0 * ca * cb * cg
        if metric_disc <= 1e-12:
            issues.append(
                ValidationIssue(
                    code="CIF_IMPOSSIBLE_CELL_ANGLES",
                    severity=Severity.ERROR,
                    message=(
                        f"Block '{block.name}' cell angles ({angles['_cell_angle_alpha']}, "
                        f"{angles['_cell_angle_beta']}, {angles['_cell_angle_gamma']}) produce non-positive cell volume."
                    ),
                    line=block.start_line,
                    field="_cell_angle",
                )
            )
            return None, {**lengths, **angles}
        volume = (
            lengths["_cell_length_a"]
            * lengths["_cell_length_b"]
            * lengths["_cell_length_c"]
            * math.sqrt(metric_disc)
        )
        return volume, {**lengths, **angles}

    return None, {**lengths, **angles}


def _validate_atom_sites(block: _CifBlock, issues: list[ValidationIssue]) -> dict[str, Any]:
    """Validate _atom_site loop coordinates and occupancies (0 <= occ <= 1)."""
    atom_loops = [lp for lp in block.loops if any(h.startswith("_atom_site_") for h in lp.headers)]
    if not atom_loops:
        issues.append(
            ValidationIssue(
                code="CIF_NO_ATOM_SITES",
                severity=Severity.ERROR,
                message=f"Block '{block.name}' does not define an '_atom_site_*' loop.",
                line=block.start_line,
                field="_atom_site",
            )
        )
        return {"atom_count": 0, "has_fractional_coords": False}

    total_atoms = 0
    has_fract_any = False

    for loop in atom_loops:
        n_cols = len(loop.headers)
        if n_cols == 0:
            issues.append(
                ValidationIssue(
                    code="CIF_EMPTY_LOOP_HEADER",
                    severity=Severity.ERROR,
                    message=f"Block '{block.name}' has loop_ with no header tags.",
                    line=loop.start_line,
                )
            )
            continue

        if len(loop.values) == 0:
            issues.append(
                ValidationIssue(
                    code="CIF_EMPTY_ATOM_LOOP",
                    severity=Severity.ERROR,
                    message=f"Block '{block.name}' '_atom_site' loop contains zero data rows.",
                    line=loop.start_line,
                )
            )
            continue

        if len(loop.values) % n_cols != 0:
            issues.append(
                ValidationIssue(
                    code="CIF_LOOP_COLUMN_MISMATCH",
                    severity=Severity.ERROR,
                    message=(
                        f"Block '{block.name}' '_atom_site' loop has {len(loop.values)} values, "
                        f"not divisible by {n_cols} headers."
                    ),
                    line=loop.start_line,
                )
            )
            continue

        has_fract = all(tag in loop.headers for tag in _FRACT_COORD_TAGS)
        has_cartn = all(tag in loop.headers for tag in _CARTN_COORD_TAGS)
        has_fract_any = has_fract_any or has_fract
        if not has_fract and not has_cartn:
            issues.append(
                ValidationIssue(
                    code="CIF_MISSING_COORDINATES",
                    severity=Severity.ERROR,
                    message=f"Block '{block.name}' '_atom_site' loop lacks complete x/y/z coordinate columns.",
                    line=loop.start_line,
                )
            )

        coord_tags = _FRACT_COORD_TAGS if has_fract else (_CARTN_COORD_TAGS if has_cartn else ())
        coord_indices = [loop.headers.index(tag) for tag in coord_tags]
        occ_idx = loop.headers.index("_atom_site_occupancy") if "_atom_site_occupancy" in loop.headers else None

        n_rows = len(loop.values) // n_cols
        total_atoms += n_rows
        for row_idx in range(n_rows):
            row = loop.values[row_idx * n_cols : (row_idx + 1) * n_cols]
            for c_idx, c_tag in zip(coord_indices, coord_tags):
                tok = row[c_idx]
                if parse_finite_float(tok.value, allow_cif_uncertainty=True) is None:
                    issues.append(
                        ValidationIssue(
                            code="CIF_INVALID_COORD",
                            severity=Severity.ERROR,
                            message=(
                                f"Block '{block.name}' row {row_idx + 1} has invalid coordinate "
                                f"'{c_tag}'='{tok.value}'."
                            ),
                            line=tok.line,
                            field=c_tag,
                        )
                    )
            if occ_idx is not None:
                occ_tok = row[occ_idx]
                occ = parse_finite_float(occ_tok.value, allow_cif_uncertainty=True)
                if occ is None:
                    issues.append(
                        ValidationIssue(
                            code="CIF_INVALID_OCCUPANCY",
                            severity=Severity.ERROR,
                            message=(
                                f"Block '{block.name}' row {row_idx + 1} has non-numeric occupancy "
                                f"'{occ_tok.value}'."
                            ),
                            line=occ_tok.line,
                            field="_atom_site_occupancy",
                        )
                    )
                elif not (0.0 <= occ <= 1.0):
                    issues.append(
                        ValidationIssue(
                            code="CIF_INVALID_OCCUPANCY",
                            severity=Severity.ERROR,
                            message=(
                                f"Block '{block.name}' row {row_idx + 1} occupancy must satisfy "
                                f"0 <= occ <= 1 (got {occ})."
                            ),
                            line=occ_tok.line,
                            field="_atom_site_occupancy",
                        )
                    )
                elif occ == 0.0:
                    issues.append(
                        ValidationIssue(
                            code="CIF_ZERO_OCCUPANCY",
                            severity=Severity.WARNING,
                            message=f"Block '{block.name}' row {row_idx + 1} has occupancy == 0.0.",
                            line=occ_tok.line,
                            field="_atom_site_occupancy",
                        )
                    )

    return {"atom_count": total_atoms, "has_fractional_coords": has_fract_any}


def validate_cif(path: Path) -> FileValidationResult:
    """Validate crystallographic and format integrity of a CIF file."""
    raw_text = path.read_text(encoding="utf-8", errors="replace")
    sha256 = compute_sha256(path)
    size_bytes = path.stat().st_size
    issues: list[ValidationIssue] = []

    tokens = _tokenize_cif(raw_text)
    blocks = _parse_cif_blocks(tokens)
    if not blocks:
        issues.append(
            ValidationIssue(
                code="CIF_NO_DATA_BLOCK",
                severity=Severity.ERROR,
                message="No 'data_<name>' block found in CIF file.",
                line=1,
            )
        )
        return FileValidationResult(
            path=str(path),
            file_format="cif",
            sha256=sha256,
            size_bytes=size_bytes,
            issues=issues,
            metadata={"data_blocks": []},
        )

    block_summaries: list[dict[str, Any]] = []
    total_atoms = 0
    has_space_group_all = True
    has_fract_all = True
    primary_volume: float | None = None

    for block in blocks:
        volume, cell_params = _validate_cell_geometry(block, issues)
        if primary_volume is None and volume is not None:
            primary_volume = volume

        sg_value = None
        for sg_tag in _SPACE_GROUP_TAGS:
            if sg_tag in block.tags and block.tags[sg_tag].value not in ("", ".", "?"):
                sg_value = block.tags[sg_tag].value
                break
        if sg_value is None:
            has_space_group_all = False
            issues.append(
                ValidationIssue(
                    code="CIF_MISSING_SPACE_GROUP",
                    severity=Severity.WARNING,
                    message=f"Block '{block.name}' lacks space group metadata (_symmetry_space_group_name_H-M / IT number).",
                    line=block.start_line,
                    field="_symmetry_space_group",
                )
            )

        site_info = _validate_atom_sites(block, issues)
        total_atoms += site_info["atom_count"]
        has_fract_all = has_fract_all and site_info["has_fractional_coords"]

        block_summaries.append(
            {
                "name": block.name,
                "cell_volume_A3": round(volume, 6) if volume is not None else None,
                "space_group": sg_value,
                "atom_count": site_info["atom_count"],
                "cell_params": cell_params,
            }
        )

    return FileValidationResult(
        path=str(path),
        file_format="cif",
        sha256=sha256,
        size_bytes=size_bytes,
        issues=issues,
        metadata={
            "data_blocks": block_summaries,
            "cell_volume_A3": round(primary_volume, 6) if primary_volume is not None else None,
            "atom_count": total_atoms,
            "has_space_group": has_space_group_all,
            "has_fractional_coords": has_fract_all,
        },
    )
