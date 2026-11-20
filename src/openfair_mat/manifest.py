"""RO-Crate 1.1 and SHA-256 reproducibility manifest generators."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Any

from openfair_mat.models import FileValidationResult, SuiteReport

_MEDIA_TYPES = {
    "cif": "chemical/x-cif",
    "poscar": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
}


def _relative_posix(file_path: str, base_dir: Path) -> str:
    """Resolve stable POSIX relative path from base_dir where possible."""
    resolved_file = Path(file_path).resolve()
    resolved_base = base_dir.resolve()
    try:
        return resolved_file.relative_to(resolved_base).as_posix()
    except ValueError:
        return resolved_file.name


def _file_entity(result: FileValidationResult, rel_path: str) -> dict[str, Any]:
    """Build an RO-Crate File entity dictionary for a validated file."""
    return {
        "@id": rel_path,
        "@type": "File",
        "name": Path(result.path).name,
        "encodingFormat": _MEDIA_TYPES.get(result.file_format, "application/octet-stream"),
        "contentSize": str(result.size_bytes),
        "sha256": result.sha256,
        "description": (
            f"Validated {result.file_format.upper()} artifact "
            f"(status={result.status}, errors={len(result.errors)}, warnings={len(result.warnings)})."
        ),
    }


def build_ro_crate(
    report: SuiteReport,
    base_dir: Path,
    *,
    title: str = "OpenFAIR-Mat Validated Research Dataset",
    license_url: str = "https://opensource.org/licenses/MIT",
) -> dict[str, Any]:
    """Build an RO-Crate 1.1 JSON-LD metadata document."""
    part_ids: list[dict[str, str]] = []
    file_entities: list[dict[str, Any]] = []

    for res in report.results:
        rel_id = _relative_posix(res.path, base_dir)
        part_ids.append({"@id": rel_id})
        file_entities.append(_file_entity(res, rel_id))

    part_ids.append({"@id": "repro-manifest.json"})

    graph: list[dict[str, Any]] = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": title,
            "datePublished": report.generated_at_utc,
            "license": {"@id": license_url},
            "hasPart": part_ids,
            "description": (
                f"Validated by {report.tool_name} v{report.tool_version}: "
                f"{report.total_files} files, {report.total_errors} errors, {report.total_warnings} warnings."
            ),
        },
        {
            "@id": license_url,
            "@type": "CreativeWork",
            "name": "MIT License",
        },
        {
            "@id": "repro-manifest.json",
            "@type": "File",
            "name": "repro-manifest.json",
            "encodingFormat": "application/json",
            "description": "SHA-256 reproducibility and repository compatibility manifest.",
        },
        *file_entities,
    ]

    return {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": graph,
    }


def build_repro_manifest(
    report: SuiteReport,
    base_dir: Path,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Build deterministic SHA-256 reproducibility and schema compatibility manifest."""
    artifacts: list[dict[str, Any]] = []
    for res in report.results:
        rel_path = _relative_posix(res.path, base_dir)
        artifacts.append(
            {
                "relative_path": rel_path,
                "file_format": res.file_format,
                "sha256": res.sha256,
                "size_bytes": res.size_bytes,
                "status": res.status,
                "error_count": len(res.errors),
                "warning_count": len(res.warnings),
                "metadata": res.metadata,
                "issues": [i.to_dict() for i in res.issues],
            }
        )

    return {
        "schema": "openfair-mat/repro-manifest/v0.1",
        "tool": {
            "name": report.tool_name,
            "version": report.tool_version,
        },
        "generated_at_utc": report.generated_at_utc,
        "runtime_environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.system(),
            "machine": platform.machine(),
            "deterministic_mode": True,
            "external_llm_used_at_runtime": False,
        },
        "validation_summary": {
            "total_files": report.total_files,
            "passed_files": report.passed_count(strict=strict),
            "failed_files": report.failed_count(strict=strict),
            "total_errors": report.total_errors,
            "total_warnings": report.total_warnings,
            "strict_mode": strict,
            "overall_passed": report.overall_passed(strict=strict),
        },
        "compatibility_summary": [c.to_dict() for c in report.compatibility],
        "artifacts": artifacts,
    }


def write_manifests(
    report: SuiteReport,
    output_dir: Path,
    base_dir: Path,
    *,
    title: str = "OpenFAIR-Mat Validated Research Dataset",
    license_url: str = "https://opensource.org/licenses/MIT",
    strict: bool = False,
) -> tuple[Path, Path]:
    """Write ro-crate-metadata.json and repro-manifest.json to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ro_crate_path = output_dir / "ro-crate-metadata.json"
    repro_path = output_dir / "repro-manifest.json"

    ro_crate_payload = build_ro_crate(report, base_dir, title=title, license_url=license_url)
    repro_payload = build_repro_manifest(report, base_dir, strict=strict)

    ro_crate_path.write_text(json.dumps(ro_crate_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    repro_path.write_text(json.dumps(repro_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ro_crate_path, repro_path
