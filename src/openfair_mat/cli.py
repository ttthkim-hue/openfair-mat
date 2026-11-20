"""Command-line interface for openfair-check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from openfair_mat import __version__
from openfair_mat.manifest import write_manifests
from openfair_mat.models import SuiteReport
from openfair_mat.runner import run_validation_suite


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openfair-check",
        description=(
            "Validate CIF, POSCAR/VASP, and CSV/JSON materials datasets, emit RO-Crate 1.1 "
            "and SHA-256 manifests, and report Zenodo/NOMAD/Materials Project compatibility."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Input file(s) or directory/directories to validate.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory where ro-crate-metadata.json and repro-manifest.json are written (default: .).",
    )
    parser.add_argument(
        "--title",
        default="OpenFAIR-Mat Validated Research Dataset",
        help="Dataset title written into ro-crate-metadata.json.",
    )
    parser.add_argument(
        "--license",
        dest="license_url",
        default="https://opensource.org/licenses/MIT",
        help="License URI recorded in ro-crate-metadata.json.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat validation WARNINGs as failures (exit code 1).",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print machine-readable JSON validation report to stdout.",
    )
    parser.add_argument(
        "--no-manifest",
        action="store_true",
        help="Skip writing ro-crate-metadata.json and repro-manifest.json.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _format_human_report(
    report: SuiteReport,
    *,
    strict: bool,
    ro_crate_path: Path | None,
    repro_path: Path | None,
) -> str:
    """Format concise human-readable terminal report."""
    lines: list[str] = [
        f"OpenFAIR-Mat v{report.tool_version} — Validation Report",
        "=" * 64,
    ]
    for res in report.results:
        lines.append(
            f"[{res.status}] {res.path} ({res.file_format.upper()}, "
            f"sha256={res.sha256[:12]}..., errors={len(res.errors)}, warnings={len(res.warnings)})"
        )
        for issue in res.issues:
            loc = f"line {issue.line}" if issue.line is not None else "file"
            lines.append(f"  - {issue.severity.value} [{issue.code}] ({loc}): {issue.message}")

    lines.append("")
    lines.append("Public Repository Schema Compatibility Summary:")
    for target in report.compatibility:
        lines.append(f"  - {target.repository}: {target.status}")
        for note in target.notes:
            lines.append(f"      * {note}")

    lines.append("")
    overall = "PASS" if report.overall_passed(strict=strict) else "FAIL"
    lines.append(
        f"Summary: {overall} | files={report.total_files}, "
        f"passed={report.passed_count(strict=strict)}, failed={report.failed_count(strict=strict)}, "
        f"errors={report.total_errors}, warnings={report.total_warnings}"
    )
    if ro_crate_path is not None and repro_path is not None:
        lines.append(f"Generated RO-Crate : {ro_crate_path.resolve()}")
        lines.append(f"Generated Manifest : {repro_path.resolve()}")
    return "\n".join(lines)


def _common_parent(paths: list[Path]) -> Path:
    """Compute deepest common parent directory across resolved paths."""
    dirs = [p.resolve() if p.is_dir() else p.resolve().parent for p in paths]
    common = dirs[0]
    for candidate in dirs[1:]:
        while common != candidate and common not in candidate.parents:
            if common.parent == common:
                return Path.cwd()
            common = common.parent
    return common


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on pass, 1 on validation error, 2 on usage/input error."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        report = run_validation_suite(args.paths, tool_version=__version__)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if report.total_files == 0:
        print("Error: No supported dataset files (.cif, POSCAR/.vasp, .csv, .json) found.", file=sys.stderr)
        return 2

    base_dir = _common_parent(args.paths)
    ro_crate_path: Path | None = None
    repro_path: Path | None = None
    if not args.no_manifest:
        ro_crate_path, repro_path = write_manifests(
            report,
            args.output_dir,
            base_dir,
            title=args.title,
            license_url=args.license_url,
            strict=args.strict,
        )

    if args.json_output:
        payload = report.to_dict(strict=args.strict)
        if ro_crate_path is not None and repro_path is not None:
            payload["generated_files"] = {
                "ro_crate": str(ro_crate_path.resolve()),
                "repro_manifest": str(repro_path.resolve()),
            }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(
            _format_human_report(
                report,
                strict=args.strict,
                ro_crate_path=ro_crate_path,
                repro_path=repro_path,
            )
        )

    return 0 if report.overall_passed(strict=args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
