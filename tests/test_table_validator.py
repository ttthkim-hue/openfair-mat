"""Tests for CSV/JSON materials property table validator."""

from pathlib import Path

from openfair_mat.table_validator import validate_table

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_valid_csv_and_json_tables() -> None:
    csv_res = validate_table(FIXTURES / "valid" / "public_materials_props.csv")
    assert csv_res.passed
    assert csv_res.status == "PASS"
    assert csv_res.metadata["row_count"] == 5

    json_res = validate_table(FIXTURES / "valid" / "public_materials_props.json")
    assert json_res.passed
    assert json_res.status == "PASS"
    assert json_res.metadata["row_count"] == 3


def test_invalid_csv_detects_nan_inf_impossible_values_and_mixed_units() -> None:
    res = validate_table(FIXTURES / "invalid" / "invalid_props_mixed_units.csv")
    assert not res.passed
    err_codes = {i.code for i in res.errors}
    warn_codes = {i.code for i in res.warnings}
    assert "TABLE_NONFINITE_VALUE" in err_codes
    assert "TABLE_IMPOSSIBLE_NEGATIVE_DENSITY" in err_codes
    assert "TABLE_IMPOSSIBLE_NEGATIVE_BANDGAP" in err_codes
    assert "TABLE_IMPOSSIBLE_SUBZERO_KELVIN" in err_codes
    assert "TABLE_MIXED_UNITS" in warn_codes
    mixed_messages = " ".join(w.message for w in res.warnings if w.code == "TABLE_MIXED_UNITS")
    assert "eV" in mixed_messages and "meV" in mixed_messages
    assert "K" in mixed_messages and "C" in mixed_messages
    assert "Å" in mixed_messages and "nm" in mixed_messages


def test_invalid_json_detects_nan_infinity_and_negative_physics() -> None:
    res = validate_table(FIXTURES / "invalid" / "invalid_props.json")
    assert not res.passed
    err_codes = {i.code for i in res.errors}
    warn_codes = {i.code for i in res.warnings}
    assert "TABLE_NONFINITE_VALUE" in err_codes
    assert "TABLE_IMPOSSIBLE_NEGATIVE_DENSITY" in err_codes
    assert "TABLE_IMPOSSIBLE_SUBZERO_KELVIN" in err_codes
    assert "TABLE_IMPOSSIBLE_NEGATIVE_MODULUS" in err_codes
    assert "TABLE_MIXED_UNITS" in warn_codes


def test_table_header_mismatch_parallel_columns_and_bounds(tmp_path: Path) -> None:
    csv_file = tmp_path / "conflicts.csv"
    csv_file.write_text(
        "formula,band_gap_eV,band_gap_meV,energy_unit,temperature_C,occupancy,cell_volume,density\n"
        "Si,1.12,1120,meV,-280.0,1.2,0.0,0.0\n",
        encoding="utf-8",
    )
    res = validate_table(csv_file)
    err_codes = {i.code for i in res.errors}
    warn_codes = {i.code for i in res.warnings}
    assert "TABLE_IMPOSSIBLE_BELOW_ABSOLUTE_ZERO" in err_codes
    assert "TABLE_IMPOSSIBLE_OCCUPANCY" in err_codes
    assert "TABLE_IMPOSSIBLE_NONPOSITIVE_GEOMETRY" in err_codes
    assert "TABLE_ZERO_DENSITY" in warn_codes
    assert "TABLE_UNIT_HEADER_MISMATCH" in warn_codes
    assert "TABLE_INCONSISTENT_UNIT_COLUMNS" in warn_codes

    inline_csv = tmp_path / "inline.csv"
    inline_csv.write_text("formula,band_gap\nSi,1.12 eV\nMgO,7800 meV\n", encoding="utf-8")
    inline_res = validate_table(inline_csv)
    assert inline_res.passed
    assert any(w.code == "TABLE_MIXED_UNITS" for w in inline_res.warnings)

    bad_json = tmp_path / "broken.json"
    bad_json.write_text("{broken json", encoding="utf-8")
    assert validate_table(bad_json).errors[0].code == "TABLE_PARSE_ERROR"

    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")
    assert validate_table(empty_csv).errors[0].code == "TABLE_EMPTY_FILE"

    # Lowercase lattice_a (axis name) should not collide with _A (Angstrom) suffix
    nm_csv = tmp_path / "nm_valid.csv"
    nm_csv.write_text("formula,lattice_a,length_unit\nSi,0.5431,nm\n", encoding="utf-8")
    nm_res = validate_table(nm_csv)
    assert nm_res.passed
    assert len(nm_res.warnings) == 0
