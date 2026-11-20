"""Tests for RO-Crate 1.1, SHA-256 repro manifest, and repository compatibility."""

import hashlib
import json
from pathlib import Path

from openfair_mat.manifest import write_manifests
from openfair_mat.runner import run_validation_suite

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_manifests_and_compatibility_for_valid_suite(tmp_path: Path) -> None:
    report = run_validation_suite([FIXTURES / "valid"])
    assert report.overall_passed()
    assert report.total_files == 4
    assert all(target.compatible for target in report.compatibility)
    assert [t.repository for t in report.compatibility] == [
        "Zenodo (CERN)",
        "NOMAD (FAIRmat)",
        "Materials Project",
    ]

    ro_path, repro_path = write_manifests(
        report,
        tmp_path,
        FIXTURES / "valid",
        title="Diamond Si & Public Reference Set",
    )
    assert ro_path.exists()
    assert repro_path.exists()

    ro_data = json.loads(ro_path.read_text(encoding="utf-8"))
    assert ro_data["@context"] == "https://w3id.org/ro/crate/1.1/context"
    graph_ids = {node["@id"] for node in ro_data["@graph"]}
    assert "./" in graph_ids
    assert "ro-crate-metadata.json" in graph_ids
    assert "repro-manifest.json" in graph_ids
    assert "si_diamond.cif" in graph_ids
    assert "si_diamond.poscar" in graph_ids

    repro_data = json.loads(repro_path.read_text(encoding="utf-8"))
    assert repro_data["validation_summary"]["overall_passed"] is True
    assert repro_data["runtime_environment"]["external_llm_used_at_runtime"] is False

    cif_bytes = (FIXTURES / "valid" / "si_diamond.cif").read_bytes()
    expected_sha = hashlib.sha256(cif_bytes).hexdigest()
    cif_entry = next(a for a in repro_data["artifacts"] if a["relative_path"] == "si_diamond.cif")
    assert cif_entry["sha256"] == expected_sha


def test_compatibility_blocked_for_invalid_suite(tmp_path: Path) -> None:
    report = run_validation_suite([FIXTURES / "invalid"])
    assert not report.overall_passed()
    assert all(not target.compatible for target in report.compatibility)
    assert all(target.status == "BLOCKED" for target in report.compatibility)

    _, repro_path = write_manifests(report, tmp_path, FIXTURES / "invalid")
    repro_data = json.loads(repro_path.read_text(encoding="utf-8"))
    assert repro_data["validation_summary"]["overall_passed"] is False
    assert repro_data["validation_summary"]["failed_files"] == 4
