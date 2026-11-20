"""Public repository schema compatibility evaluation (Zenodo, NOMAD, Materials Project)."""

from __future__ import annotations

from openfair_mat.models import CompatibilityTarget, FileValidationResult


def evaluate_compatibility(results: list[FileValidationResult]) -> list[CompatibilityTarget]:
    """Evaluate dataset readiness for Zenodo, NOMAD (FAIRmat), and Materials Project schemas."""
    if not results:
        return [
            CompatibilityTarget(repo, "EMPTY", False, ["No dataset files provided."])
            for repo in ("Zenodo (CERN)", "NOMAD (FAIRmat)", "Materials Project")
        ]

    total_errors = sum(len(r.errors) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    cifs = [r for r in results if r.file_format == "cif"]
    poscars = [r for r in results if r.file_format == "poscar"]
    tables = [r for r in results if r.file_format in {"csv", "json"}]

    # 1. Zenodo: deposit archive + SHA-256 + RO-Crate metadata + zero hard errors
    zenodo_notes: list[str] = []
    if total_errors == 0:
        zenodo_notes.append(f"All {len(results)} artifacts passed integrity checks with valid SHA-256 digests.")
        zenodo_notes.append("RO-Crate 1.1 (ro-crate-metadata.json) and repro-manifest.json ready for Zenodo deposit.")
        zenodo_status = "READY" if total_warnings == 0 else "READY_WITH_WARNINGS"
        zenodo_ok = True
    else:
        zenodo_notes.append(f"Blocked by {total_errors} integrity error(s); repair before archival deposit.")
        zenodo_status = "BLOCKED"
        zenodo_ok = False
    if total_warnings > 0:
        zenodo_notes.append(f"{total_warnings} metadata/unit warning(s) noted for curator review.")

    # 2. NOMAD (FAIRmat): structural files, CIF space group, VASP5 species, canonical units
    nomad_notes: list[str] = []
    nomad_blockers = 0
    nomad_warns = 0
    for r in cifs + poscars:
        if r.errors:
            nomad_blockers += len(r.errors)
        if r.file_format == "cif" and not r.metadata.get("has_space_group", False):
            nomad_warns += 1
            nomad_notes.append(f"{r.path}: missing CIF space group tag; NOMAD symmetry parser may fall back.")
        if r.file_format == "poscar" and r.metadata.get("vasp_format") == "VASP4":
            nomad_warns += 1
            nomad_notes.append(f"{r.path}: VASP4 lacks element symbol line; VASP5 preferred by NOMAD.")
    for r in tables:
        if r.errors:
            nomad_blockers += len(r.errors)
        if any("MIXED_UNITS" in i.code or "UNIT" in i.code for i in r.warnings):
            nomad_warns += 1
            nomad_notes.append(f"{r.path}: unit mixing/inconsistency detected; normalize to SI/NOMAD units (eV, A, K).")

    if nomad_blockers == 0:
        if not cifs and not poscars:
            nomad_notes.append("No crystal structure files (CIF/POSCAR) in batch; tabular metadata passes base checks.")
        elif not nomad_notes:
            nomad_notes.append("Crystal structures include valid cell geometry, species/space-group tags, and finite sites.")
        nomad_status = "READY" if nomad_warns == 0 else "READY_WITH_WARNINGS"
        nomad_ok = True
    else:
        nomad_notes.insert(0, f"Blocked by {nomad_blockers} structural/data error(s) incompatible with NOMAD parsers.")
        nomad_status = "BLOCKED"
        nomad_ok = False

    # 3. Materials Project (pymatgen Structure / MPContribs): positive volume, [0,1] occupancy, physical tables
    mp_notes: list[str] = []
    mp_blockers = 0
    mp_warns = 0
    for r in results:
        if r.errors:
            mp_blockers += len(r.errors)
        if r.warnings:
            mp_warns += len(r.warnings)
        if r.file_format == "cif" and not r.metadata.get("has_fractional_coords", False) and not r.errors:
            mp_warns += 1
            mp_notes.append(f"{r.path}: Cartesian-only CIF; fractional coordinates preferred for pymatgen/MP ingestion.")

    if mp_blockers == 0:
        if mp_warns == 0:
            mp_notes.append("Positive cell volume, valid occupancies [0, 1], and clean units align with MP/MPContribs.")
            mp_status = "READY"
        else:
            mp_notes.append(f"Structure/table loads without hard errors, but {mp_warns} unit/metadata warning(s) remain.")
            mp_status = "READY_WITH_WARNINGS"
        mp_ok = True
    else:
        mp_notes.insert(0, f"Blocked by {mp_blockers} physical/schema error(s) violating Materials Project constraints.")
        mp_status = "BLOCKED"
        mp_ok = False

    return [
        CompatibilityTarget("Zenodo (CERN)", zenodo_status, zenodo_ok, zenodo_notes),
        CompatibilityTarget("NOMAD (FAIRmat)", nomad_status, nomad_ok, nomad_notes),
        CompatibilityTarget("Materials Project", mp_status, mp_ok, mp_notes),
    ]
