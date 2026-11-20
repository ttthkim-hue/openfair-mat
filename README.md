# OpenFAIR-Mat

**Deterministic pre-flight physical-integrity, schema, and reproducibility validator (`RO-Crate 1.1` + `SHA-256`) for federated scientific and materials datasets.**

- **License:** MIT (`100%` OSI-permissive open source; zero GPL/AGPL runtime dependencies)
- **Runtime:** Pure Python standard library (`>=3.10`, zero external AI/LLM APIs, zero GPU dependencies)
- **Live Portfolio:** [https://ttthkim-hue.github.io/openfair-mat/](https://ttthkim-hue.github.io/openfair-mat/)
- **AI Transparency:** See [`AI_DISCLOSURE.md`](./AI_DISCLOSURE.md)
- **Citation:** See [`CITATION.cff`](./CITATION.cff)

---

## Why OpenFAIR-Mat?

Experimental laboratories measure only the observables reachable by instruments during an experiment, while computational simulations construct a complete digital state within configured parameters—enabling post-hoc forensic reanalysis when predictions fail to reproduce perfectly in reality. However, across open materials repositories (`Zenodo`, `NOMAD / FAIRmat`, `Materials Project`), corrupted crystal files, inconsistent unit conventions, and missing provenance manifests still trigger silent downstream errors before physical verification ever starts.

`OpenFAIR-Mat` (`openfair-check`) provides a fast, zero-dependency **pre-flight gate** that runs locally before upload:

1. **CIF Crystallographic Validator:** Enforces positive lattice lengths (`a, b, c > 0`), valid angles (`0 < alpha, beta, gamma < 180`), positive triclinic metric-tensor volume, finite coordinates, and physical site occupancies (`0 <= occ <= 1`).
2. **VASP `POSCAR`/`CONTCAR` Validator:** Verifies positive 3x3 lattice determinant volume (`> 0`), consistent element species/counts, and exact alignment between ion totals and atomic coordinate lines.
3. **CSV/JSON Property Table Validator:** Flags `NaN`/`Inf` (including non-standard JSON constants), unit mixing (`eV` vs `meV`, `K` vs `C`, `A` vs `nm`), negative densities/band gaps/elastic moduli, and sub-zero Kelvin values.
4. **Reproducibility & Repository Readiness:** Emits W3C/ResearchObject-compatible `ro-crate-metadata.json` (`RO-Crate 1.1`) and `SHA-256` digests (`repro-manifest.json`) with automated readiness checks for **Zenodo (CERN)**, **NOMAD (FAIRmat)**, and **Materials Project**.

---

## Quick Installation

```bash
pip install -e ".[dev]"
# or with uv:
# uv pip install -e ".[dev]"
```

Requires Python `>= 3.10` with zero mandatory third-party runtime dependencies (`pytest` and `pytest-cov` are only used for development testing).

---

## Usage & Observed Output

### Validate clean public reference fixtures (`exit 0`)

```bash
openfair-check fixtures/valid -o out_valid
```

Expected output:

```text
Summary: PASS | files=4, passed=4, failed=0, errors=0, warnings=0
Zenodo (CERN): READY | NOMAD (FAIRmat): READY | Materials Project: READY
```

Generates `out_valid/ro-crate-metadata.json` (`RO-Crate 1.1`) and `out_valid/repro-manifest.json` (`SHA-256` manifest).

### Detect corrupted fixtures (`exit 1`)

```bash
openfair-check fixtures/invalid -o out_invalid
```

Flags `20` physical/schema errors and `6` unit/metadata warnings across broken CIF, POSCAR, CSV, and JSON samples and marks all three repository targets as `BLOCKED` with exit code `1` (ideal for GitHub Actions / GitLab CI gates). Use `--strict` to fail on warnings as well, or `--json` for structured machine output.

---

## Tests & Coverage

```bash
pytest --cov=openfair_mat --cov-report=term-missing
```

Verified locally: **`19 passed`**, **`90.65%` coverage** (`fail_under = 85` enforced in CI across Python `3.10`, `3.11`, and `3.12`).

---

## Data & Provenance Policy

All bundled fixtures (`fixtures/valid`, `fixtures/invalid`) are public reference crystal structures (e.g., conventional diamond-cubic silicon, `Fd-3m`) and synthetic edge-case test tables. No proprietary institutional or unpublished experimental data is included.
