"""Data models for OpenFAIR-Mat validation results and reproducibility reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Severity levels for validation diagnostics."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class ValidationIssue:
    """Single validation diagnostic emitted for a checked dataset file."""

    code: str
    severity: Severity
    message: str
    line: int | None = None
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize diagnostic to a JSON-compatible dictionary."""
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "line": self.line,
            "field": self.field,
        }


@dataclass
class FileValidationResult:
    """Validation outcome and extracted metadata for a single file."""

    path: str
    file_format: str
    sha256: str
    size_bytes: int
    issues: list[ValidationIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Return all ERROR-level issues."""
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Return all WARNING-level issues."""
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def passed(self) -> bool:
        """Return True when zero ERROR issues were found."""
        return len(self.errors) == 0

    def passed_mode(self, strict: bool = False) -> bool:
        """Return pass status under normal or strict (warnings fail) mode."""
        if strict:
            return len(self.errors) == 0 and len(self.warnings) == 0
        return self.passed

    @property
    def status(self) -> str:
        """Human-readable status label."""
        if self.errors:
            return "FAIL"
        if self.warnings:
            return "WARN"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        """Serialize file validation result to a JSON-compatible dictionary."""
        return {
            "path": self.path,
            "file_format": self.file_format,
            "status": self.status,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "metadata": self.metadata,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class CompatibilityTarget:
    """Public repository schema compatibility evaluation summary."""

    repository: str
    status: str
    compatible: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize compatibility target summary."""
        return {
            "repository": self.repository,
            "status": self.status,
            "compatible": self.compatible,
            "notes": self.notes,
        }


@dataclass
class SuiteReport:
    """Aggregate report across all checked files in a validation run."""

    tool_name: str
    tool_version: str
    generated_at_utc: str
    results: list[FileValidationResult] = field(default_factory=list)
    compatibility: list[CompatibilityTarget] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        """Total number of validated files."""
        return len(self.results)

    @property
    def total_errors(self) -> int:
        """Total ERROR count across all files."""
        return sum(len(r.errors) for r in self.results)

    @property
    def total_warnings(self) -> int:
        """Total WARNING count across all files."""
        return sum(len(r.warnings) for r in self.results)

    def passed_count(self, strict: bool = False) -> int:
        """Count of files passing under normal or strict mode."""
        return sum(1 for r in self.results if r.passed_mode(strict=strict))

    def failed_count(self, strict: bool = False) -> int:
        """Count of files failing under normal or strict mode."""
        return self.total_files - self.passed_count(strict=strict)

    def overall_passed(self, strict: bool = False) -> bool:
        """Return True iff every file passed under the requested strictness."""
        return self.total_files > 0 and self.failed_count(strict=strict) == 0

    def to_dict(self, strict: bool = False) -> dict[str, Any]:
        """Serialize aggregate suite report."""
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "generated_at_utc": self.generated_at_utc,
            "summary": {
                "total_files": self.total_files,
                "passed_files": self.passed_count(strict=strict),
                "failed_files": self.failed_count(strict=strict),
                "total_errors": self.total_errors,
                "total_warnings": self.total_warnings,
                "overall_passed": self.overall_passed(strict=strict),
                "strict_mode": strict,
            },
            "compatibility": [c.to_dict() for c in self.compatibility],
            "files": [r.to_dict() for r in self.results],
        }
