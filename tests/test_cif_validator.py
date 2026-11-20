"""Tests for CIF physical and format integrity validator."""

from pathlib import Path

from openfair_mat.cif_validator import validate_cif
from openfair_mat.models import Severity

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_valid_diamond_si_cif() -> None:
    res = validate_cif(FIXTURES / "valid" / "si_diamond.cif")
    assert res.passed
    assert res.status == "PASS"
    assert res.metadata["atom_count"] == 8
    assert res.metadata["has_space_group"] is True
    assert res.metadata["has_fractional_coords"] is True
    assert abs(res.metadata["cell_volume_A3"] - 5.43102**3) < 1e-2


def test_invalid_cif_fixture_detects_angles_lengths_occ_nan() -> None:
    res = validate_cif(FIXTURES / "invalid" / "invalid_si_angles_occ.cif")
    assert not res.passed
    codes = {i.code for i in res.errors}
    assert "CIF_NONPOSITIVE_LENGTH" in codes
    assert "CIF_INVALID_ANGLE" in codes
    assert "CIF_INVALID_OCCUPANCY" in codes
    assert "CIF_INVALID_COORD" in codes


def test_cif_uncertainty_and_cartesian_coords_and_missing_sg(tmp_path: Path) -> None:
    cif = tmp_path / "uncert.cif"
    cif.write_text(
        "data_uncert\n"
        "_cell_length_a 5.4310(2)\n"
        "_cell_length_b 5.4310(2)\n"
        "_cell_length_c 5.4310(2)\n"
        "_cell_angle_alpha 90.0(1)\n"
        "_cell_angle_beta 90.0\n"
        "_cell_angle_gamma 90.0\n"
        ";\n"
        "multi-line comment\n"
        ";\n"
        "_chemical_name_common 'Test Material'\n"
        "loop_\n"
        "_atom_site_label\n"
        "_atom_site_Cartn_x\n"
        "_atom_site_Cartn_y\n"
        "_atom_site_Cartn_z\n"
        "_atom_site_occupancy\n"
        "Si1 0.0 0.0 0.0 0.0\n",
        encoding="utf-8",
    )
    res = validate_cif(cif)
    assert res.passed
    assert res.status == "WARN"
    warn_codes = {w.code for w in res.warnings}
    assert "CIF_MISSING_SPACE_GROUP" in warn_codes
    assert "CIF_ZERO_OCCUPANCY" in warn_codes
    assert res.metadata["has_fractional_coords"] is False


def test_cif_impossible_triclinic_angles_and_edge_cases(tmp_path: Path) -> None:
    impossible = tmp_path / "impossible.cif"
    impossible.write_text(
        "data_impossible\n"
        "_cell_length_a 4.0\n"
        "_cell_length_b 4.0\n"
        "_cell_length_c 4.0\n"
        "_cell_angle_alpha 125.0\n"
        "_cell_angle_beta 125.0\n"
        "_cell_angle_gamma 125.0\n"
        "loop_\n"
        "_atom_site_label\n"
        "_atom_site_fract_x\n"
        "_atom_site_fract_y\n"
        "_atom_site_fract_z\n"
        "_atom_site_occupancy\n"
        "X1 0.0 0.0 0.0 bad_occ\n",
        encoding="utf-8",
    )
    res = validate_cif(impossible)
    codes = {i.code for i in res.errors}
    assert "CIF_IMPOSSIBLE_CELL_ANGLES" in codes
    assert "CIF_INVALID_OCCUPANCY" in codes

    empty_cif = tmp_path / "empty.cif"
    empty_cif.write_text("# comment only\n", encoding="utf-8")
    empty_res = validate_cif(empty_cif)
    assert not empty_res.passed
    assert empty_res.errors[0].code == "CIF_NO_DATA_BLOCK"

    mismatch_cif = tmp_path / "mismatch.cif"
    mismatch_cif.write_text(
        "data_bad\n"
        "_cell_length_a NaN\n"
        "_cell_angle_alpha ?\n"
        "loop_\n"
        "_atom_site_label\n"
        "_atom_site_fract_x\n"
        "Si1 0.1 0.2\n",
        encoding="utf-8",
    )
    mismatch_res = validate_cif(mismatch_cif)
    mcodes = {i.code for i in mismatch_res.errors}
    assert "CIF_INVALID_NUMBER" in mcodes
    assert "CIF_MISSING_CELL_PARAM" in mcodes
    assert "CIF_LOOP_COLUMN_MISMATCH" in mcodes

    no_coords = tmp_path / "no_coords.cif"
    no_coords.write_text(
        "data_nocoord\n"
        "_cell_length_a 5.0\n_cell_length_b 5.0\n_cell_length_c 5.0\n"
        "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
        "loop_\n_atom_site_label\nSi1\n",
        encoding="utf-8",
    )
    nc_res = validate_cif(no_coords)
    assert any(i.code == "CIF_MISSING_COORDINATES" and i.severity == Severity.ERROR for i in nc_res.issues)
