"""
Core validation rules for structured financial data.

Each validator is a function that takes a pandas DataFrame and returns
a list of ValidationIssue objects describing any problems found.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
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
# Required columns expected in a financial instrument dataset
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
    "REV",      # Revenue
    "CD",       # Certificate of Deposit
    "BAB",      # Build America
    "IDR",      # Industrial Development Revenue
    "TAN",      # Tax Anticipation Note
    "BAN",      # Anticipation Note
    "RAN",      # Revenue Anticipation Note
    "TRAN",     # Tax & Revenue Anticipation Note
    "COPS",     # Certificates of Participation
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
    """Validate instrument type classifications."""
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
                message=f"Instrument type '{val}' is not a recognized classification. Expected one of: {', '.join(sorted(VALID_BOND_TYPES))}.",
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
# Advanced Validators — CUSIP Deep Validation
# ---------------------------------------------------------------------------

def _cusip_check_digit(cusip_8: str) -> str:
    """
    Calculate the CUSIP check digit (9th character) using the Luhn algorithm
    variant specified by the CUSIP standard (ANNA/ISO 6166).

    Takes the first 8 characters of a CUSIP and returns the expected check digit.
    """
    total = 0
    for i, char in enumerate(cusip_8.upper()):
        if char.isdigit():
            val = int(char)
        elif char.isalpha():
            val = ord(char) - ord('A') + 10
        elif char == '*':
            val = 36
        elif char == '@':
            val = 37
        elif char == '#':
            val = 38
        else:
            val = 0

        # Double every second digit (0-indexed: positions 1, 3, 5, 7)
        if i % 2 == 1:
            val *= 2

        # Sum the digits of the result (e.g., 18 → 1 + 8 = 9)
        total += val // 10 + val % 10

    check = (10 - (total % 10)) % 10
    return str(check)


def check_cusip_check_digit(df: pd.DataFrame) -> list[ValidationIssue]:
    """
    Validate the CUSIP check digit (9th character) using the Luhn algorithm.

    This goes beyond simple format validation — it verifies mathematical
    correctness of the identifier, catching transposition errors and
    fabricated CUSIPs.
    """
    issues: list[ValidationIssue] = []
    if "cusip" not in df.columns:
        return issues

    pattern = re.compile(r"^[A-Za-z0-9]{9}$")
    for idx, val in df["cusip"].items():
        if pd.isna(val) or str(val).strip() == "":
            continue
        val_str = str(val).strip()
        if not pattern.match(val_str):
            continue  # Format errors handled by check_cusip_format

        expected = _cusip_check_digit(val_str[:8])
        actual = val_str[8]
        if actual != expected:
            issues.append(ValidationIssue(
                row=int(idx) + 2, column="cusip", severity=Severity.ERROR,
                rule="CUSIP_CHECK_DIGIT",
                message=f"CUSIP '{val_str}' has an invalid check digit. "
                        f"Expected '{expected}', got '{actual}'. "
                        f"Possible transposition or fabricated identifier.",
            ))

    return issues


def check_cusip_issuer_structure(df: pd.DataFrame) -> list[ValidationIssue]:
    """
    Validate CUSIP issuer code structure (first 6 characters).

    CUSIPs for public-sector issuers typically start with digits (unlike
    corporate CUSIPs which often start with letters). Flags anomalous
    patterns that suggest a data mismatch.
    """
    issues: list[ValidationIssue] = []
    if "cusip" not in df.columns:
        return issues

    pattern = re.compile(r"^[A-Za-z0-9]{9}$")
    for idx, val in df["cusip"].items():
        if pd.isna(val) or str(val).strip() == "":
            continue
        val_str = str(val).strip().upper()
        if not pattern.match(val_str):
            continue

        issuer_code = val_str[:6]
        issue_id = val_str[6:8]

        # Public-sector CUSIPs: first 6 chars are typically numeric
        # or start with a digit. Flag all-alpha issuer codes as unusual.
        if issuer_code.isalpha():
            issues.append(ValidationIssue(
                row=int(idx) + 2, column="cusip", severity=Severity.WARNING,
                rule="CUSIP_ISSUER_ANOMALY",
                message=f"CUSIP '{val_str}': issuer code '{issuer_code}' is all-alphabetic. "
                        f"Public-sector CUSIPs typically have numeric issuer codes. "
                        f"Verify the instrument classification.",
            ))

        # Flag issue identifiers that are all zeros (often placeholder data)
        if issue_id == "00":
            issues.append(ValidationIssue(
                row=int(idx) + 2, column="cusip", severity=Severity.INFO,
                rule="CUSIP_PLACEHOLDER",
                message=f"CUSIP '{val_str}': issue ID '00' may indicate placeholder data.",
            ))

    return issues


# ---------------------------------------------------------------------------
# Advanced Validators — Financial Logic Checks
# ---------------------------------------------------------------------------

# Expected coupon rate ranges by instrument type
_COUPON_RANGES: dict[str, tuple[float, float]] = {
    "GO":   (0.0, 7.0),
    "REV":  (0.0, 8.0),
    "BAB":  (3.0, 10.0),   # Build America instruments have taxable higher rates
    "CD":   (0.0, 6.0),
    "TAN":  (0.0, 5.0),
    "BAN":  (0.0, 5.0),
    "RAN":  (0.0, 5.0),
    "TRAN": (0.0, 5.0),
}

# Maximum typical maturity terms in years by instrument type
_MAX_MATURITY_YEARS: dict[str, int] = {
    "GO":   30,
    "REV":  40,
    "BAB":  35,
    "CD":   5,
    "TAN":  2,
    "BAN":  3,
    "RAN":  2,
    "TRAN": 2,
    "COPs": 30,
    "HFA":  40,
    "IDR":  35,
}

# Typical par value ranges by instrument type
_PAR_RANGES: dict[str, tuple[float, float]] = {
    "GO":   (1_000, 500_000_000),
    "REV":  (1_000, 1_000_000_000),
    "TAN":  (1_000, 100_000_000),
    "BAN":  (1_000, 100_000_000),
    "RAN":  (1_000, 100_000_000),
    "CD":   (1_000, 50_000_000),
}


def check_coupon_bond_type_consistency(df: pd.DataFrame) -> list[ValidationIssue]:
    """
    Cross-validate coupon rates against instrument type expectations.

    Different instrument types have characteristic coupon rate ranges. A GO
    with a 12% coupon or a short-term note with 8% is highly suspicious.
    """
    issues: list[ValidationIssue] = []
    if "coupon_rate" not in df.columns or "bond_type" not in df.columns:
        return issues

    for idx, row in df.iterrows():
        if pd.isna(row.get("coupon_rate")) or pd.isna(row.get("bond_type")):
            continue
        try:
            rate = float(str(row["coupon_rate"]).replace("%", ""))
            bt = str(row["bond_type"]).strip().upper()
        except (ValueError, TypeError):
            continue

        if bt in _COUPON_RANGES:
            min_r, max_r = _COUPON_RANGES[bt]
            if rate > max_r:
                issues.append(ValidationIssue(
                    row=int(idx) + 2, column="coupon_rate",
                    severity=Severity.WARNING,
                    rule="COUPON_TYPE_MISMATCH",
                    message=f"Coupon rate {rate}% is unusually high for {bt} instruments "
                            f"(expected {min_r}–{max_r}%). Verify rate or classification.",
                ))
            elif rate < min_r and rate != 0:
                issues.append(ValidationIssue(
                    row=int(idx) + 2, column="coupon_rate",
                    severity=Severity.INFO,
                    rule="COUPON_TYPE_MISMATCH",
                    message=f"Coupon rate {rate}% is below typical range for {bt} instruments"
                            f"(expected {min_r}–{max_r}%).",
                ))

    return issues


def check_maturity_term_limits(df: pd.DataFrame) -> list[ValidationIssue]:
    """
    Validate maturity terms against instrument type constraints.

    Short-term notes (TAN, BAN, RAN) should not have 30-year maturities.
    GO instruments rarely exceed 30 years. Revenue instruments can go
    longer but 50+ year terms are suspicious.
    """
    issues: list[ValidationIssue] = []
    cols_needed = {"issue_date", "maturity_date", "bond_type"}
    if not cols_needed.issubset(set(df.columns)):
        return issues

    for idx, row in df.iterrows():
        try:
            issue_dt = pd.to_datetime(row["issue_date"])
            mat_dt = pd.to_datetime(row["maturity_date"])
            bt = str(row.get("bond_type", "")).strip().upper()
        except (ValueError, TypeError):
            continue

        if pd.isna(issue_dt) or pd.isna(mat_dt) or not bt:
            continue

        term_years = (mat_dt - issue_dt).days / 365.25

        if term_years <= 0:
            continue  # Handled by MATURITY_BEFORE_ISSUE

        # Check against instrument type limits
        if bt in _MAX_MATURITY_YEARS:
            max_years = _MAX_MATURITY_YEARS[bt]
            if term_years > max_years:
                issues.append(ValidationIssue(
                    row=int(idx) + 2, column="maturity_date",
                    severity=Severity.WARNING,
                    rule="EXCESSIVE_MATURITY_TERM",
                    message=f"{bt} instrument has a {term_years:.1f}-year term, "
                            f"exceeding the typical max of {max_years} years. "
                            f"Verify maturity date or instrument classification.",
                ))

        # Universal cap: flag anything over 50 years
        if term_years > 50:
            issues.append(ValidationIssue(
                row=int(idx) + 2, column="maturity_date",
                severity=Severity.ERROR,
                rule="EXTREME_MATURITY_TERM",
                message=f"Maturity term of {term_years:.1f} years exceeds 50-year maximum. "
                        f"Likely a data entry error.",
            ))

    return issues


def check_par_value_by_bond_type(df: pd.DataFrame) -> list[ValidationIssue]:
    """
    Cross-validate par values against instrument type norms.

    Short-term notes with $500M+ par values or certificates of deposit
    over $50M are red flags for data quality.
    """
    issues: list[ValidationIssue] = []
    if "par_value" not in df.columns or "bond_type" not in df.columns:
        return issues

    for idx, row in df.iterrows():
        if pd.isna(row.get("par_value")) or pd.isna(row.get("bond_type")):
            continue
        try:
            par = float(str(row["par_value"]).replace(",", "").replace("$", ""))
            bt = str(row["bond_type"]).strip().upper()
        except (ValueError, TypeError):
            continue

        if bt in _PAR_RANGES:
            min_p, max_p = _PAR_RANGES[bt]
            if par > max_p:
                issues.append(ValidationIssue(
                    row=int(idx) + 2, column="par_value",
                    severity=Severity.WARNING,
                    rule="PAR_TYPE_MISMATCH",
                    message=f"Par value ${par:,.2f} is unusually high for {bt} instruments"
                            f"(typical max ${max_p:,.0f}). Verify amount or classification.",
                ))
            elif par < min_p:
                issues.append(ValidationIssue(
                    row=int(idx) + 2, column="par_value",
                    severity=Severity.WARNING,
                    rule="PAR_BELOW_MINIMUM",
                    message=f"Par value ${par:,.2f} is below typical minimum for {bt} instruments"
                            f"(${min_p:,.0f}). May indicate incorrect units (thousands vs actual).",
                ))

    return issues


# ---------------------------------------------------------------------------
# Advanced Validators — Data Pattern Detection
# ---------------------------------------------------------------------------

def check_data_patterns(df: pd.DataFrame) -> list[ValidationIssue]:
    """
    Detect data entry patterns that indicate quality problems:
    - Trailing/leading whitespace in text fields
    - Inconsistent casing (mixed upper/lower for same entity)
    - Special characters in issuer names
    - Suspicious repeated values across rows (copy-paste errors)
    """
    issues: list[ValidationIssue] = []
    text_cols = ["issuer_name", "state", "bond_type", "cusip"]

    # --- Whitespace detection ---
    for col in text_cols:
        if col not in df.columns:
            continue
        for idx, val in df[col].items():
            if pd.isna(val):
                continue
            val_str = str(val)
            if val_str != val_str.strip():
                issues.append(ValidationIssue(
                    row=int(idx) + 2, column=col, severity=Severity.INFO,
                    rule="TRAILING_WHITESPACE",
                    message=f"Value in '{col}' has leading/trailing whitespace: '{val_str!r}'.",
                ))

    # --- Special characters in issuer names ---
    if "issuer_name" in df.columns:
        suspicious_chars = re.compile(r'[<>{}\\|~`\[\]^]')
        for idx, val in df["issuer_name"].items():
            if pd.isna(val) or str(val).strip() == "":
                continue
            name = str(val).strip()
            found = suspicious_chars.findall(name)
            if found:
                issues.append(ValidationIssue(
                    row=int(idx) + 2, column="issuer_name",
                    severity=Severity.WARNING, rule="SPECIAL_CHARS_IN_NAME",
                    message=f"Issuer name contains suspicious characters: "
                            f"{''.join(set(found))} in '{name}'.",
                ))

    # --- Inconsistent casing detection ---
    if "issuer_name" in df.columns:
        name_groups: dict[str, list[str]] = {}
        for val in df["issuer_name"].dropna():
            normalized = str(val).strip().lower()
            original = str(val).strip()
            if normalized not in name_groups:
                name_groups[normalized] = []
            if original not in name_groups[normalized]:
                name_groups[normalized].append(original)

        inconsistent = {k: v for k, v in name_groups.items() if len(v) > 1}
        if inconsistent:
            for norm, variants in inconsistent.items():
                issues.append(ValidationIssue(
                    row=None, column="issuer_name",
                    severity=Severity.WARNING, rule="INCONSISTENT_CASING",
                    message=f"Issuer name has inconsistent casing: "
                            f"{', '.join(repr(v) for v in variants)}. Standardize to one form.",
                ))

    return issues


def check_copy_paste_errors(df: pd.DataFrame) -> list[ValidationIssue]:
    """
    Detect copy-paste patterns: when a column has an unusually high
    concentration of identical values, it may indicate bulk-fill errors.

    Also detects fully duplicated rows (all columns identical).
    """
    issues: list[ValidationIssue] = []

    # --- Fully duplicated rows ---
    if len(df) > 1:
        dup_mask = df.duplicated(keep="first")
        for idx in df[dup_mask].index:
            issues.append(ValidationIssue(
                row=int(idx) + 2, column=None,
                severity=Severity.WARNING, rule="DUPLICATE_ROW",
                message=f"Row {int(idx) + 2} is an exact duplicate of a previous row.",
            ))

    # --- Suspicious value concentration (copy-paste detection) ---
    # For text columns, flag when >60% of rows share the same value
    # (but only in datasets with 5+ rows to avoid false positives)
    check_cols = ["issuer_name", "par_value", "coupon_rate"]
    if len(df) >= 5:
        for col in check_cols:
            if col not in df.columns:
                continue
            non_null = df[col].dropna()
            if len(non_null) == 0:
                continue
            mode_count = non_null.astype(str).str.strip().value_counts().iloc[0]
            mode_val = non_null.astype(str).str.strip().value_counts().index[0]
            ratio = mode_count / len(non_null)
            if ratio > 0.6 and mode_count > 3:
                issues.append(ValidationIssue(
                    row=None, column=col,
                    severity=Severity.WARNING, rule="COPY_PASTE_SUSPECTED",
                    message=f"Column '{col}' has {mode_count}/{len(non_null)} rows "
                            f"({ratio:.0%}) with value '{mode_val}'. "
                            f"Possible copy-paste or default-fill error.",
                ))

    return issues


def check_issuer_state_consistency(df: pd.DataFrame) -> list[ValidationIssue]:
    """
    Cross-validate issuer names against stated geographic location.

    If an issuer name contains a state name (e.g., "City of Austin Texas")
    but the state column says "NY", that's a red flag.
    """
    issues: list[ValidationIssue] = []
    if "issuer_name" not in df.columns or "state" not in df.columns:
        return issues

    # State name → abbreviation mapping (common ones)
    _STATE_NAMES: dict[str, str] = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
        "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
        "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
        "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
        "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
        "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
        "new mexico": "NM", "new york": "NY", "north carolina": "NC",
        "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
        "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
        "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
        "vermont": "VT", "virginia": "VA", "washington": "WA",
        "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    }

    for idx, row in df.iterrows():
        if pd.isna(row.get("issuer_name")) or pd.isna(row.get("state")):
            continue

        name_lower = str(row["issuer_name"]).strip().lower()
        stated_code = str(row["state"]).strip().upper()

        for state_name, state_code in _STATE_NAMES.items():
            if state_name in name_lower and state_code != stated_code:
                # Avoid false positives: "New York" shouldn't flag "new" matching "NE"
                # Only flag if the match is a clear state reference
                if len(state_name) >= 4:
                    issues.append(ValidationIssue(
                        row=int(idx) + 2, column="state",
                        severity=Severity.WARNING,
                        rule="ISSUER_STATE_MISMATCH",
                        message=f"Issuer name '{row['issuer_name']}' suggests "
                                f"{state_name.title()} ({state_code}), but state "
                                f"column says '{stated_code}'. Verify geographic data.",
                    ))
                    break  # One mismatch per row is enough

    return issues


# ---------------------------------------------------------------------------
# Validator registry
# ---------------------------------------------------------------------------

ALL_VALIDATORS: list[Callable[[pd.DataFrame], list[ValidationIssue]]] = [
    # Core validators
    check_required_columns,
    check_missing_values,
    check_cusip_format,
    check_duplicate_cusips,
    check_date_validity,
    check_numeric_ranges,
    check_state_codes,
    check_bond_type,
    check_issuer_name_quality,
    # Advanced — CUSIP deep validation
    check_cusip_check_digit,
    check_cusip_issuer_structure,
    # Advanced — Financial logic
    check_coupon_bond_type_consistency,
    check_maturity_term_limits,
    check_par_value_by_bond_type,
    # Advanced — Data pattern detection
    check_data_patterns,
    check_copy_paste_errors,
    check_issuer_state_consistency,
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
