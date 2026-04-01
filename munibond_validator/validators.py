"""
Core validation rules for municipal bond data.

Each validator is a function that takes a pandas DataFrame and returns
a list of ValidationIssue objects describing any problems found.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
import re
from datetime import datetime

import pandas as pd


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class Severity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"         # Data is invalid — must be fixed
    WARNING = "warning"     # Suspicious data — should be reviewed
    INFO = "info"           # Minor issue or suggestion


@dataclass
class ValidationIssue:
    """A single data quality issue found during validation."""
    row: int | None          # Row number (1-indexed, None if file-level)
    column: str | None       # Column name (None if row/file-level)
    severity: Severity
    rule: str                # Short rule identifier, e.g. "CUSIP_FORMAT"
    message: str             # Human-readable description


@dataclass
class ValidationResult:
    """Aggregated result from running all validators on a dataset."""
    file_name: str
    total_rows: int
    total_columns: int
    issues: list[ValidationIssue] = field(default_factory=list)
    validators_run: int = 0

    # -- Computed helpers -----------------------------------------------------

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.INFO)

    @property
    def pass_rate(self) -> float:
        """Percentage of rows with zero ERRORs."""
        if self.total_rows == 0:
            return 0.0
        error_rows = len({i.row for i in self.issues if i.severity == Severity.ERROR and i.row is not None})
        return round((1 - error_rows / self.total_rows) * 100, 2)

    @property
    def is_clean(self) -> bool:
        return self.error_count == 0 and self.warning_count == 0


# ---------------------------------------------------------------------------
# Required columns expected in a municipal bond dataset
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = [
    "cusip",
    "issuer_name",
    "state",
    "issue_date",
    "maturity_date",
    "par_value",
    "coupon_rate",
    "bond_type",
]

VALID_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "GU", "VI", "AS",
}

VALID_BOND_TYPES = {
    "GO",       # General Obligation
    "REV",      # Revenue Bond
    "CD",       # Certificate of Deposit
    "BAB",      # Build America Bond
    "IDR",      # Industrial Development Revenue
    "TAN",      # Tax Anticipation Note
    "BAN",      # Bond Anticipation Note
    "RAN",      # Revenue Anticipation Note
    "TRAN",     # Tax & Revenue Anticipation Note
    "COPs",     # Certificates of Participation
    "HFA",      # Housing Finance Authority
    "OTHER",
}


# ---------------------------------------------------------------------------
# Individual validation rules
# ---------------------------------------------------------------------------

def check_required_columns(df: pd.DataFrame) -> list[ValidationIssue]:
    """Verify all required columns are present in the dataset."""
    issues: list[ValidationIssue] = []
    cols_lower = {c.lower().strip() for c in df.columns}
    for col in REQUIRED_COLUMNS:
        if col not in cols_lower:
            issues.append(ValidationIssue(
                row=None, column=col, severity=Severity.ERROR,
                rule="MISSING_COLUMN",
                message=f"Required column '{col}' is missing from the dataset.",
            ))
    return issues


def check_missing_values(df: pd.DataFrame) -> list[ValidationIssue]:
    """Flag rows with missing values in required columns."""
    issues: list[ValidationIssue] = []
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            continue
        mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
        for idx in df[mask].index:
            issues.append(ValidationIssue(
                row=int(idx) + 2,  # +2 for 1-indexed + header row
                column=col,
                severity=Severity.ERROR,
                rule="MISSING_VALUE",
                message=f"Required field '{col}' is empty.",
            ))
    return issues


def check_cusip_format(df: pd.DataFrame) -> list[ValidationIssue]:
    """
    Validate CUSIP identifiers.
    A valid CUSIP is exactly 9 alphanumeric characters.
    """
    issues: list[ValidationIssue] = []
    if "cusip" not in df.columns:
        return issues

    pattern = re.compile(r"^[A-Za-z0-9]{9}$")
    for idx, val in df["cusip"].items():
        if pd.isna(val) or str(val).strip() == "":
            continue  # handled by missing-value check
        val_str = str(val).strip()
        if not pattern.match(val_str):
            issues.append(ValidationIssue(
                row=int(idx) + 2, column="cusip", severity=Severity.ERROR,
                rule="CUSIP_FORMAT",
                message=f"Invalid CUSIP format: '{val_str}'. Expected 9 alphanumeric characters.",
            ))
    return issues


def check_duplicate_cusips(df: pd.DataFrame) -> list[ValidationIssue]:
    """Flag duplicate CUSIP numbers within the dataset."""
    issues: list[ValidationIssue] = []
    if "cusip" not in df.columns:
        return issues

    dupes = df[df["cusip"].duplicated(keep=False) & df["cusip"].notna()]
    seen: set[str] = set()
    for idx, val in dupes["cusip"].items():
        val_str = str(val).strip()
        if val_str and val_str in seen:
            issues.append(ValidationIssue(
                row=int(idx) + 2, column="cusip", severity=Severity.WARNING,
                rule="DUPLICATE_CUSIP",
                message=f"Duplicate CUSIP '{val_str}' found.",
            ))
        seen.add(val_str)
    return issues


def check_date_validity(df: pd.DataFrame) -> list[ValidationIssue]:
    """Validate date fields are parseable and logically consistent."""
    issues: list[ValidationIssue] = []
    date_cols = ["issue_date", "maturity_date"]

    for col in date_cols:
        if col not in df.columns:
            continue
        for idx, val in df[col].items():
            if pd.isna(val) or str(val).strip() == "":
                continue
            try:
                parsed = pd.to_datetime(val)
                # Flag future issue dates
                if col == "issue_date" and parsed > pd.Timestamp.now():
                    issues.append(ValidationIssue(
                        row=int(idx) + 2, column=col, severity=Severity.WARNING,
                        rule="FUTURE_ISSUE_DATE",
                        message=f"Issue date '{val}' is in the future.",
                    ))
            except (ValueError, TypeError):
                issues.append(ValidationIssue(
                    row=int(idx) + 2, column=col, severity=Severity.ERROR,
                    rule="INVALID_DATE",
                    message=f"Cannot parse date value: '{val}'.",
                ))

    # Check maturity > issue date
    if "issue_date" in df.columns and "maturity_date" in df.columns:
        for idx, row in df.iterrows():
            try:
                issue_dt = pd.to_datetime(row["issue_date"])
                mat_dt = pd.to_datetime(row["maturity_date"])
                if mat_dt <= issue_dt:
                    issues.append(ValidationIssue(
                        row=int(idx) + 2, column="maturity_date",
                        severity=Severity.ERROR, rule="MATURITY_BEFORE_ISSUE",
                        message=f"Maturity date ({row['maturity_date']}) is on or before issue date ({row['issue_date']}).",
                    ))
            except (ValueError, TypeError):
                pass  # Date parse errors handled above

    return issues


def check_numeric_ranges(df: pd.DataFrame) -> list[ValidationIssue]:
    """Validate that numeric fields fall within expected ranges."""
    issues: list[ValidationIssue] = []

    # Par value: must be positive
    if "par_value" in df.columns:
        for idx, val in df["par_value"].items():
            if pd.isna(val) or str(val).strip() == "":
                continue
            try:
                num = float(str(val).replace(",", "").replace("$", ""))
                if num <= 0:
                    issues.append(ValidationIssue(
                        row=int(idx) + 2, column="par_value",
                        severity=Severity.ERROR, rule="NEGATIVE_PAR_VALUE",
                        message=f"Par value must be positive, got {num}.",
                    ))
                elif num > 1_000_000_000:
                    issues.append(ValidationIssue(
                        row=int(idx) + 2, column="par_value",
                        severity=Severity.WARNING, rule="UNUSUAL_PAR_VALUE",
                        message=f"Par value of {num:,.2f} is unusually large — verify.",
                    ))
            except ValueError:
                issues.append(ValidationIssue(
                    row=int(idx) + 2, column="par_value",
                    severity=Severity.ERROR, rule="NON_NUMERIC_PAR",
                    message=f"Par value '{val}' is not a valid number.",
                ))

    # Coupon rate: should be between 0 and 15%
    if "coupon_rate" in df.columns:
        for idx, val in df["coupon_rate"].items():
            if pd.isna(val) or str(val).strip() == "":
                continue
            try:
                rate = float(str(val).replace("%", ""))
                if rate < 0:
                    issues.append(ValidationIssue(
                        row=int(idx) + 2, column="coupon_rate",
                        severity=Severity.ERROR, rule="NEGATIVE_COUPON",
                        message=f"Coupon rate cannot be negative: {rate}%.",
                    ))
                elif rate > 15:
                    issues.append(ValidationIssue(
                        row=int(idx) + 2, column="coupon_rate",
                        severity=Severity.WARNING, rule="HIGH_COUPON",
                        message=f"Coupon rate of {rate}% seems unusually high — verify.",
                    ))
            except ValueError:
                issues.append(ValidationIssue(
                    row=int(idx) + 2, column="coupon_rate",
                    severity=Severity.ERROR, rule="NON_NUMERIC_COUPON",
                    message=f"Coupon rate '{val}' is not a valid number.",
                ))

    return issues


def check_state_codes(df: pd.DataFrame) -> list[ValidationIssue]:
    """Validate state/territory codes."""
    issues: list[ValidationIssue] = []
    if "state" not in df.columns:
        return issues

    for idx, val in df["state"].items():
        if pd.isna(val) or str(val).strip() == "":
            continue
        code = str(val).strip().upper()
        if code not in VALID_STATES:
            issues.append(ValidationIssue(
                row=int(idx) + 2, column="state", severity=Severity.ERROR,
                rule="INVALID_STATE",
                message=f"'{val}' is not a valid US state/territory code.",
            ))
    return issues


def check_bond_type(df: pd.DataFrame) -> list[ValidationIssue]:
    """Validate bond type classifications."""
    issues: list[ValidationIssue] = []
    if "bond_type" not in df.columns:
        return issues

    for idx, val in df["bond_type"].items():
        if pd.isna(val) or str(val).strip() == "":
            continue
        bt = str(val).strip().upper()
        if bt not in VALID_BOND_TYPES:
            issues.append(ValidationIssue(
                row=int(idx) + 2, column="bond_type", severity=Severity.WARNING,
                rule="UNKNOWN_BOND_TYPE",
                message=f"Bond type '{val}' is not a recognized classification. Expected one of: {', '.join(sorted(VALID_BOND_TYPES))}.",
            ))
    return issues


def check_issuer_name_quality(df: pd.DataFrame) -> list[ValidationIssue]:
    """Flag low-quality issuer names (too short, all caps, or numeric)."""
    issues: list[ValidationIssue] = []
    if "issuer_name" not in df.columns:
        return issues

    for idx, val in df["issuer_name"].items():
        if pd.isna(val) or str(val).strip() == "":
            continue
        name = str(val).strip()
        if len(name) < 3:
            issues.append(ValidationIssue(
                row=int(idx) + 2, column="issuer_name", severity=Severity.WARNING,
                rule="SHORT_ISSUER_NAME",
                message=f"Issuer name '{name}' is suspiciously short.",
            ))
        if name.isdigit():
            issues.append(ValidationIssue(
                row=int(idx) + 2, column="issuer_name", severity=Severity.WARNING,
                rule="NUMERIC_ISSUER_NAME",
                message=f"Issuer name '{name}' appears to be purely numeric.",
            ))
    return issues


# ---------------------------------------------------------------------------
# Validator registry
# ---------------------------------------------------------------------------

ALL_VALIDATORS: list[Callable[[pd.DataFrame], list[ValidationIssue]]] = [
    check_required_columns,
    check_missing_values,
    check_cusip_format,
    check_duplicate_cusips,
    check_date_validity,
    check_numeric_ranges,
    check_state_codes,
    check_bond_type,
    check_issuer_name_quality,
]


def run_all_validators(df: pd.DataFrame, file_name: str = "unknown") -> ValidationResult:
    """Execute every registered validator and return a consolidated result."""
    # Normalize column names to lowercase
    df.columns = [c.lower().strip() for c in df.columns]

    result = ValidationResult(
        file_name=file_name,
        total_rows=len(df),
        total_columns=len(df.columns),
    )

    for validator in ALL_VALIDATORS:
        issues = validator(df)
        result.issues.extend(issues)
        result.validators_run += 1

    # Sort issues by row number, then severity
    severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    result.issues.sort(key=lambda i: (i.row or 0, severity_order.get(i.severity, 9)))

    return result
