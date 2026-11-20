"""CLI end-to-end tests for openfair-check."""

import json
import subprocess
import sys
from pathlib import Path

from openfair_mat.cli import main

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_cli_valid_fixtures_exit_zero_and_creates_manifests(tmp_path: Path) -> None:
    code = main([str(FIXTURES / "valid"), "-o", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "ro-crate-metadata.json").is_file()
    assert (tmp_path / "repro-manifest.json").is_file()


def test_cli_invalid_fixtures_exit_nonzero(tmp_path: Path) -> None:
    code = main([str(FIXTURES / "invalid"), "-o", str(tmp_path), "--json"])
    assert code == 1
    repro = json.loads((tmp_path / "repro-manifest.json").read_text(encoding="utf-8"))
    assert repro["validation_summary"]["overall_passed"] is False


def test_cli_strict_mode_fails_on_warnings(tmp_path: Path) -> None:
    warn_csv = tmp_path / "warn_units.csv"
    warn_csv.write_text("formula,band_gap,energy_unit\nSi,1.12,eV\nMgO,7800,meV\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    assert main([str(warn_csv), "-o", str(out_dir)]) == 0
    assert main([str(warn_csv), "-o", str(out_dir), "--strict"]) == 1


def test_cli_missing_path_returns_exit_two(tmp_path: Path) -> None:
    assert main([str(tmp_path / "does_not_exist.cif")]) == 2


def test_module_subprocess_execution(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "openfair_mat",
            str(FIXTURES / "valid" / "si_diamond.cif"),
            "-o",
            str(tmp_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["summary"]["overall_passed"] is True
    assert payload["summary"]["total_files"] == 1
