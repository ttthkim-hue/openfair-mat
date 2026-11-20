"""Core package exports for OpenFAIR-Mat."""

from openfair_mat.models import (
    CompatibilityTarget,
    FileValidationResult,
    Severity,
    SuiteReport,
    ValidationIssue,
)
from openfair_mat.runner import run_validation_suite

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "CompatibilityTarget",
    "FileValidationResult",
    "Severity",
    "SuiteReport",
    "ValidationIssue",
    "run_validation_suite",
]
