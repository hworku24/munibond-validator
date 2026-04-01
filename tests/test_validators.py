"""Unit tests for the MuniBond validation engine."""

import pytest
import pandas as pd

from munibond_validator.validators import (
    check_required_columns,
    check_missing_values,
    check_cusip_format,
    check_duplicate_cusips,
    check_date_validity,
    check_numeric_ranges,
    check_state_codes,
    check_bond_type,
    check_issuer_name_quality,
    run_all_validators,
    Severity,
    REQUIRED_COLUMNS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(overrides: dict | None = None, rows: int = 1) -> pd.DataFrame:
    """Build a minimal valid DataFrame, optionally overriding column values."""
    base = {
        "cusip": ["912828ZT6"] * rows,
        "issuer_name": ["City of Austin Texas"] * rows,
        "state": ["TX"] * rows,
        "issue_date": ["2023-01-15"] * rows,
        "maturity_date": ["2033-01-15"] * rows,
        "par_value": ["5000000"] * rows,
        "coupon_rate": ["4.25"] * rows,
        "bond_type": ["GO"] * rows,
    }
    if overrides:
        for k, v in overrides.items():
            if isinstance(v, list):
                base[k] = v
            else:
                base[k] = [v] * rows
    return pd.DataFrame(base)


# ---------------------------------------------------------------------------
# check_required_columns
# ---------------------------------------------------------------------------

class TestRequiredColumns:
    def test_all_present(self):
        df = _make_df()
        assert check_required_columns(df) == []

    def test_missing_column(self):
        df = _make_df()
        df = df.drop(columns=["cusip"])
        issues = check_required_columns(df)
        assert len(issues) == 1
        assert issues[0].rule == "MISSING_COLUMN"
        assert issues[0].severity == Severity.ERROR

    def test_multiple_missing(self):
        df = _make_df()
        df = df.drop(columns=["cusip", "state", "par_value"])
        issues = check_required_columns(df)
        assert len(issues) == 3


# ---------------------------------------------------------------------------
# check_missing_values
# ---------------------------------------------------------------------------

class TestMissingValues:
    def test_no_missing(self):
        df = _make_df()
        assert check_missing_values(df) == []

    def test_empty_string(self):
        df = _make_df({"cusip": ""})
        issues = check_missing_values(df)
        assert any(i.rule == "MISSING_VALUE" and i.column == "cusip" for i in issues)

    def test_nan_value(self):
        df = _make_df({"issuer_name": None})
        issues = check_missing_values(df)
        assert any(i.rule == "MISSING_VALUE" and i.column == "issuer_name" for i in issues)


# ---------------------------------------------------------------------------
# check_cusip_format
# ---------------------------------------------------------------------------

class TestCusipFormat:
    def test_valid_cusip(self):
        df = _make_df({"cusip": "912828ZT6"})
        assert check_cusip_format(df) == []

    def test_too_short(self):
        df = _make_df({"cusip": "12345"})
        issues = check_cusip_format(df)
        assert len(issues) == 1
        assert issues[0].rule == "CUSIP_FORMAT"

    def test_too_long(self):
        df = _make_df({"cusip": "1234567890"})
        issues = check_cusip_format(df)
        assert len(issues) == 1

    def test_special_characters(self):
        df = _make_df({"cusip": "912828-T6"})
        issues = check_cusip_format(df)
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# check_duplicate_cusips
# ---------------------------------------------------------------------------

class TestDuplicateCusips:
    def test_no_duplicates(self):
        df = _make_df({"cusip": ["912828ZT6", "912828ZU3"]}, rows=2)
        assert check_duplicate_cusips(df) == []

    def test_has_duplicates(self):
        df = _make_df({"cusip": ["912828ZT6", "912828ZT6"]}, rows=2)
        issues = check_duplicate_cusips(df)
        assert len(issues) == 1
        assert issues[0].rule == "DUPLICATE_CUSIP"
        assert issues[0].severity == Severity.WARNING


# ---------------------------------------------------------------------------
# check_date_validity
# ---------------------------------------------------------------------------

class TestDateValidity:
    def test_valid_dates(self):
        df = _make_df()
        assert check_date_validity(df) == []

    def test_unparseable_date(self):
        df = _make_df({"issue_date": "not-a-date"})
        issues = check_date_validity(df)
        assert any(i.rule == "INVALID_DATE" for i in issues)

    def test_maturity_before_issue(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2020-01-01"})
        issues = check_date_validity(df)
        assert any(i.rule == "MATURITY_BEFORE_ISSUE" for i in issues)

    def test_future_issue_date(self):
        df = _make_df({"issue_date": "2099-01-01", "maturity_date": "2100-01-01"})
        issues = check_date_validity(df)
        assert any(i.rule == "FUTURE_ISSUE_DATE" for i in issues)


# ---------------------------------------------------------------------------
# check_numeric_ranges
# ---------------------------------------------------------------------------

class TestNumericRanges:
    def test_valid_values(self):
        df = _make_df()
        assert check_numeric_ranges(df) == []

    def test_negative_par_value(self):
        df = _make_df({"par_value": "-500000"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "NEGATIVE_PAR_VALUE" for i in issues)

    def test_non_numeric_par(self):
        df = _make_df({"par_value": "abc"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "NON_NUMERIC_PAR" for i in issues)

    def test_negative_coupon(self):
        df = _make_df({"coupon_rate": "-2.5"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "NEGATIVE_COUPON" for i in issues)

    def test_high_coupon_warning(self):
        df = _make_df({"coupon_rate": "22.5"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "HIGH_COUPON" and i.severity == Severity.WARNING for i in issues)

    def test_unusually_large_par(self):
        df = _make_df({"par_value": "5000000000"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "UNUSUAL_PAR_VALUE" for i in issues)


# ---------------------------------------------------------------------------
# check_state_codes
# ---------------------------------------------------------------------------

class TestStateCodes:
    def test_valid_state(self):
        df = _make_df({"state": "CA"})
        assert check_state_codes(df) == []

    def test_invalid_state(self):
        df = _make_df({"state": "XX"})
        issues = check_state_codes(df)
        assert len(issues) == 1
        assert issues[0].rule == "INVALID_STATE"

    def test_territory_valid(self):
        df = _make_df({"state": "PR"})
        assert check_state_codes(df) == []


# ---------------------------------------------------------------------------
# check_bond_type
# ---------------------------------------------------------------------------

class TestBondType:
    def test_valid_types(self):
        for bt in ["GO", "REV", "BAB", "TAN"]:
            df = _make_df({"bond_type": bt})
            assert check_bond_type(df) == [], f"Failed for bond type {bt}"

    def test_unknown_type(self):
        df = _make_df({"bond_type": "XYZ"})
        issues = check_bond_type(df)
        assert len(issues) == 1
        assert issues[0].rule == "UNKNOWN_BOND_TYPE"


# ---------------------------------------------------------------------------
# check_issuer_name_quality
# ---------------------------------------------------------------------------

class TestIssuerNameQuality:
    def test_normal_name(self):
        df = _make_df({"issuer_name": "City of Austin Texas"})
        assert check_issuer_name_quality(df) == []

    def test_short_name(self):
        df = _make_df({"issuer_name": "AB"})
        issues = check_issuer_name_quality(df)
        assert any(i.rule == "SHORT_ISSUER_NAME" for i in issues)

    def test_numeric_name(self):
        df = _make_df({"issuer_name": "12345"})
        issues = check_issuer_name_quality(df)
        assert any(i.rule == "NUMERIC_ISSUER_NAME" for i in issues)


# ---------------------------------------------------------------------------
# Integration: run_all_validators
# ---------------------------------------------------------------------------

class TestRunAllValidators:
    def test_clean_data(self):
        df = _make_df()
        result = run_all_validators(df, "test.csv")
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.pass_rate == 100.0
        assert result.is_clean

    def test_messy_data(self):
        df = pd.DataFrame({
            "cusip": ["912828ZT6", "INVALID", "", "912828ZT6"],
            "issuer_name": ["Austin", "AB", "City of LA", "Austin"],
            "state": ["TX", "XX", "CA", "TX"],
            "issue_date": ["2023-01-15", "not-a-date", "2023-06-01", "2023-01-15"],
            "maturity_date": ["2033-01-15", "2033-01-15", "2043-06-01", "2033-01-15"],
            "par_value": ["5000000", "-100", "7000000", "5000000"],
            "coupon_rate": ["4.25", "25.0", "3.80", "4.25"],
            "bond_type": ["GO", "XYZ", "REV", "GO"],
        })
        result = run_all_validators(df, "messy.csv")
        assert result.error_count > 0
        assert result.warning_count > 0
        assert not result.is_clean
        assert result.validators_run == 9

    def test_pass_rate_calculation(self):
        df = pd.DataFrame({
            "cusip": ["912828ZT6", "SHORT"],
            "issuer_name": ["City A", "City B"],
            "state": ["TX", "CA"],
            "issue_date": ["2023-01-15", "2023-01-15"],
            "maturity_date": ["2033-01-15", "2033-01-15"],
            "par_value": ["5000000", "5000000"],
            "coupon_rate": ["4.25", "4.25"],
            "bond_type": ["GO", "GO"],
        })
        result = run_all_validators(df, "test.csv")
        # 1 of 2 rows has an error (invalid CUSIP) → 50% pass rate
        assert result.pass_rate == 50.0
