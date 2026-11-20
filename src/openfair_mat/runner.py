"""File discovery and validation orchestration for OpenFAIR-Mat."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from openfair_mat.cif_validator import validate_cif
from openfair_mat.compatibility import evaluate_compatibility
from openfair_mat.models import FileValidationResult, SuiteReport
from openfair_mat.poscar_validator import validate_poscar
from openfair_mat.table_validator import validate_table

_SKIP_FILENAMES = {"ro-crate-metadata.json", "repro-manifest.json"}
_SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "node_modules"}


def detect_file_format(path: Path) -> str | None:
    """Detect supported scientific dataset format from extension or VASP naming."""
    name_lower = path.name.lower()
    suffix_lower = path.suffix.lower()

    if name_lower in _SKIP_FILENAMES:
        return None
    if suffix_lower == ".cif":
        return "cif"
    if suffix_lower in {".poscar", ".vasp"} or name_lower.startswith(("poscar", "contcar")):
        return "poscar"
    if suffix_lower == ".csv":
        return "csv"
    if suffix_lower == ".json":
        return "json"
    return None


def collect_target_files(paths: list[Path]) -> list[Path]:
    """Collect and deterministically sort supported dataset files from input files/directories."""
    collected: dict[Path, Path] = {}
    for target in paths:
        if not target.exists():
            raise FileNotFoundError(f"Input path does not exist: {target}")
        if target.is_file():
            resolved = target.resolve()
            if detect_file_format(resolved) is None:
                raise ValueError(f"Unsupported file format for '{target}'. Expected CIF, POSCAR/VASP, CSV, or JSON.")
            collected[resolved] = resolved
            continue

        for candidate in sorted(target.rglob("*")):
            if any(part in _SKIP_DIRS for part in candidate.parts):
                continue
            if candidate.is_file() and detect_file_format(candidate) is not None:
                resolved = candidate.resolve()
                collected[resolved] = resolved

    return sorted(collected.values(), key=lambda p: p.as_posix())


def validate_single_file(path: Path) -> FileValidationResult:
    """Dispatch single file to the matching OpenFAIR-Mat format validator."""
    fmt = detect_file_format(path)
    if fmt == "cif":
        return validate_cif(path)
    if fmt == "poscar":
        return validate_poscar(path)
    if fmt in {"csv", "json"}:
        return validate_table(path)
    raise ValueError(f"Unsupported file format: {path}")


def run_validation_suite(paths: list[Path], *, tool_version: str = "0.1.0") -> SuiteReport:
    """Validate all discovered files and compute repository compatibility summaries."""
    target_files = collect_target_files(paths)
    results = [validate_single_file(file_path) for file_path in target_files]
    compatibility = evaluate_compatibility(results)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return SuiteReport(
        tool_name="openfair-mat",
        tool_version=tool_version,
        generated_at_utc=timestamp,
        results=results,
        compatibility=compatibility,
    )
