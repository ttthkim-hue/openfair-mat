"""Tests for VASP POSCAR/CONTCAR physical cell volume and atom count validator."""

from pathlib import Path

from openfair_mat.poscar_validator import validate_poscar

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_valid_diamond_si_poscar() -> None:
    res = validate_poscar(FIXTURES / "valid" / "si_diamond.poscar")
    assert res.passed
    assert res.status == "PASS"
    assert res.metadata["vasp_format"] == "VASP5"
    assert res.metadata["species"] == ["Si"]
    assert res.metadata["counts"] == [8]
    assert res.metadata["expected_atoms"] == 8
    assert res.metadata["actual_coord_lines"] == 8
    assert res.metadata["coordinate_mode"] == "Direct"
    assert abs(res.metadata["cell_volume_A3"] - 5.43102**3) < 1e-2


def test_invalid_poscar_fixture_detects_zero_volume_and_count_mismatch() -> None:
    res = validate_poscar(FIXTURES / "invalid" / "invalid_si_volume_count.poscar")
    assert not res.passed
    codes = {i.code for i in res.errors}
    assert "POSCAR_NONPOSITIVE_VOLUME" in codes
    assert "POSCAR_ATOM_COUNT_MISMATCH" in codes


def test_poscar_vasp4_and_selective_dynamics(tmp_path: Path) -> None:
    vasp4 = tmp_path / "POSCAR_vasp4"
    vasp4.write_text(
        "\n"
        "1.0\n"
        "4.0 0.0 0.0\n"
        "0.0 4.0 0.0\n"
        "0.0 0.0 4.0\n"
        "2\n"
        "Selective dynamics\n"
        "Cartesian\n"
        "0.0 0.0 0.0 T T F\n"
        "2.0 2.0 2.0 F F T\n",
        encoding="utf-8",
    )
    res = validate_poscar(vasp4)
    assert res.passed
    assert res.status == "WARN"
    w_codes = {w.code for w in res.warnings}
    assert "POSCAR_EMPTY_COMMENT" in w_codes
    assert "POSCAR_VASP4_MISSING_SPECIES" in w_codes
    assert res.metadata["selective_dynamics"] is True
    assert res.metadata["coordinate_mode"] == "Cartesian"


def test_poscar_error_cases(tmp_path: Path) -> None:
    short = tmp_path / "short.poscar"
    short.write_text("Si\n1.0\n", encoding="utf-8")
    assert validate_poscar(short).errors[0].code == "POSCAR_TOO_SHORT"

    bad = tmp_path / "bad.poscar"
    bad.write_text(
        "Bad POSCAR\n"
        "-1.0\n"
        "1.0 0.0 0.0\n"
        "0.0 1.0\n"
        "0.0 0.0 NaN\n"
        "Si O\n"
        "2\n"
        "Selective dynamics\n"
        "InvalidMode\n"
        "0.0 0.0 NaN T X F\n",
        encoding="utf-8",
    )
    res = validate_poscar(bad)
    codes = {i.code for i in res.errors}
    assert "POSCAR_NONPOSITIVE_SCALE" in codes
    assert "POSCAR_INVALID_LATTICE" in codes
    assert "POSCAR_SPECIES_COUNT_MISMATCH" in codes
    assert "POSCAR_INVALID_COORD_MODE" in codes
    assert "POSCAR_INVALID_COORD" in codes
    assert "POSCAR_INVALID_SELECTIVE_FLAGS" in codes
    assert "POSCAR_ATOM_COUNT_MISMATCH" in codes

    neg_det = tmp_path / "left_handed.poscar"
    neg_det.write_text(
        "Left-handed cell\n"
        "1.0\n"
        "0.0 4.0 0.0\n"
        "4.0 0.0 0.0\n"
        "0.0 0.0 4.0\n"
        "Si\n"
        "1\n"
        "Direct\n"
        "0.0 0.0 0.0\n",
        encoding="utf-8",
    )
    lh_res = validate_poscar(neg_det)
    assert any(i.code == "POSCAR_NONPOSITIVE_VOLUME" for i in lh_res.errors)
