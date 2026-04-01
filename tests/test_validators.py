"""
Comprehensive unit tests for the data quality validation engine.

Covers all 17 validators with edge cases, boundary conditions,
and integration scenarios.
"""

import pytest
import pandas as pd
import numpy as np

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
    check_cusip_check_digit,
    check_cusip_issuer_structure,
    check_coupon_bond_type_consistency,
    check_maturity_term_limits,
    check_par_value_by_bond_type,
    check_data_patterns,
    check_copy_paste_errors,
    check_issuer_state_consistency,
    _cusip_check_digit,
    run_all_validators,
    Severity,
    ValidationResult,
    REQUIRED_COLUMNS,
    VALID_STATES,
    VALID_BOND_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(overrides: dict | None = None, rows: int = 1) -> pd.DataFrame:
    """Build a minimal valid DataFrame, optionally overriding column values."""
    base = {
        "cusip": ["912828ZT0"] * rows,
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


# ===========================================================================
# 1. check_required_columns
# ===========================================================================

class TestRequiredColumns:
    def test_all_present(self):
        df = _make_df()
        assert check_required_columns(df) == []

    def test_single_missing_column(self):
        df = _make_df().drop(columns=["cusip"])
        issues = check_required_columns(df)
        assert len(issues) == 1
        assert issues[0].rule == "MISSING_COLUMN"
        assert issues[0].severity == Severity.ERROR
        assert issues[0].column == "cusip"
        assert issues[0].row is None  # file-level issue

    def test_multiple_missing_columns(self):
        df = _make_df().drop(columns=["cusip", "state", "par_value"])
        issues = check_required_columns(df)
        assert len(issues) == 3
        missing_cols = {i.column for i in issues}
        assert missing_cols == {"cusip", "state", "par_value"}

    def test_all_columns_missing(self):
        df = pd.DataFrame({"random_col": [1, 2, 3]})
        issues = check_required_columns(df)
        assert len(issues) == len(REQUIRED_COLUMNS)

    def test_case_insensitive_columns(self):
        df = _make_df()
        df.columns = [c.upper() for c in df.columns]
        # Validator lowercases — should still detect missing if case differs
        issues = check_required_columns(df)
        assert len(issues) == 0  # columns are uppercased but set comparison is lowercase

    def test_extra_columns_ignored(self):
        df = _make_df()
        df["extra_column"] = "test"
        assert check_required_columns(df) == []


# ===========================================================================
# 2. check_missing_values
# ===========================================================================

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

    def test_whitespace_only_treated_as_missing(self):
        df = _make_df({"state": "   "})
        issues = check_missing_values(df)
        assert any(i.rule == "MISSING_VALUE" and i.column == "state" for i in issues)

    def test_multiple_missing_in_one_row(self):
        df = _make_df({"cusip": "", "state": "", "par_value": ""})
        issues = check_missing_values(df)
        missing_cols = {i.column for i in issues if i.rule == "MISSING_VALUE"}
        assert "cusip" in missing_cols
        assert "state" in missing_cols
        assert "par_value" in missing_cols

    def test_multiple_rows_missing(self):
        df = _make_df({"cusip": ["912828ZT0", "", ""]}, rows=3)
        issues = [i for i in check_missing_values(df) if i.column == "cusip"]
        assert len(issues) == 2

    def test_row_numbers_are_correct(self):
        df = _make_df({"cusip": ["912828ZT0", "", "912828ZT0"]}, rows=3)
        issues = [i for i in check_missing_values(df) if i.column == "cusip"]
        assert len(issues) == 1
        assert issues[0].row == 3  # 0-indexed row 1, +2 for header = row 3

    def test_missing_column_skipped(self):
        df = _make_df().drop(columns=["cusip"])
        # Should not crash — just skips the missing column
        issues = check_missing_values(df)
        assert not any(i.column == "cusip" for i in issues)


# ===========================================================================
# 3. check_cusip_format
# ===========================================================================

class TestCusipFormat:
    def test_valid_cusip(self):
        df = _make_df({"cusip": "912828ZT0"})
        assert check_cusip_format(df) == []

    def test_valid_all_numeric(self):
        df = _make_df({"cusip": "123456789"})
        assert check_cusip_format(df) == []

    def test_valid_all_alpha(self):
        df = _make_df({"cusip": "ABCDEFGHI"})
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

    def test_spaces_in_cusip(self):
        df = _make_df({"cusip": "912 28ZT0"})
        issues = check_cusip_format(df)
        assert len(issues) == 1

    def test_empty_cusip_skipped(self):
        df = _make_df({"cusip": ""})
        assert check_cusip_format(df) == []  # handled by missing value check

    def test_nan_cusip_skipped(self):
        df = _make_df({"cusip": None})
        assert check_cusip_format(df) == []

    def test_multiple_invalid(self):
        df = _make_df({"cusip": ["ABC", "TOOLONGCUSIP", "912828ZT0"]}, rows=3)
        issues = check_cusip_format(df)
        assert len(issues) == 2

    def test_no_cusip_column(self):
        df = _make_df().drop(columns=["cusip"])
        assert check_cusip_format(df) == []


# ===========================================================================
# 4. check_duplicate_cusips
# ===========================================================================

class TestDuplicateCusips:
    def test_no_duplicates(self):
        df = _make_df({"cusip": ["912828ZT0", "912828ZU7"]}, rows=2)
        assert check_duplicate_cusips(df) == []

    def test_has_duplicates(self):
        df = _make_df({"cusip": ["912828ZT0", "912828ZT0"]}, rows=2)
        issues = check_duplicate_cusips(df)
        assert len(issues) == 1
        assert issues[0].rule == "DUPLICATE_CUSIP"
        assert issues[0].severity == Severity.WARNING

    def test_triple_duplicate(self):
        df = _make_df({"cusip": ["912828ZT0"] * 3}, rows=3)
        issues = check_duplicate_cusips(df)
        assert len(issues) == 2  # second and third are flagged

    def test_multiple_duplicate_groups(self):
        df = _make_df({
            "cusip": ["AAA111111", "BBB222222", "AAA111111", "BBB222222"]
        }, rows=4)
        issues = check_duplicate_cusips(df)
        assert len(issues) == 2

    def test_nan_not_flagged_as_duplicate(self):
        df = _make_df({"cusip": [None, None, "912828ZT0"]}, rows=3)
        issues = check_duplicate_cusips(df)
        assert len(issues) == 0

    def test_single_row_no_duplicates(self):
        df = _make_df()
        assert check_duplicate_cusips(df) == []


# ===========================================================================
# 5. check_date_validity
# ===========================================================================

class TestDateValidity:
    def test_valid_dates(self):
        df = _make_df()
        assert check_date_validity(df) == []

    def test_unparseable_issue_date(self):
        df = _make_df({"issue_date": "not-a-date"})
        issues = check_date_validity(df)
        assert any(i.rule == "INVALID_DATE" and i.column == "issue_date" for i in issues)

    def test_unparseable_maturity_date(self):
        df = _make_df({"maturity_date": "garbage"})
        issues = check_date_validity(df)
        assert any(i.rule == "INVALID_DATE" and i.column == "maturity_date" for i in issues)

    def test_maturity_before_issue(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2020-01-01"})
        issues = check_date_validity(df)
        assert any(i.rule == "MATURITY_BEFORE_ISSUE" for i in issues)

    def test_maturity_equals_issue(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2023-01-15"})
        issues = check_date_validity(df)
        assert any(i.rule == "MATURITY_BEFORE_ISSUE" for i in issues)

    def test_future_issue_date(self):
        df = _make_df({"issue_date": "2099-01-01", "maturity_date": "2100-01-01"})
        issues = check_date_validity(df)
        assert any(i.rule == "FUTURE_ISSUE_DATE" for i in issues)

    def test_various_date_formats(self):
        # Should parse multiple date formats
        df = _make_df({"issue_date": "01/15/2023", "maturity_date": "2033-01-15"})
        issues = check_date_validity(df)
        assert not any(i.rule == "INVALID_DATE" for i in issues)

    def test_empty_date_skipped(self):
        df = _make_df({"issue_date": ""})
        issues = check_date_validity(df)
        assert not any(i.rule == "INVALID_DATE" and i.column == "issue_date" for i in issues)

    def test_multiple_date_errors(self):
        df = _make_df({
            "issue_date": ["2023-01-15", "xyz", "abc"],
            "maturity_date": ["2033-01-15", "2033-01-15", "2033-01-15"],
        }, rows=3)
        issues = [i for i in check_date_validity(df) if i.rule == "INVALID_DATE"]
        assert len(issues) == 2


# ===========================================================================
# 6. check_numeric_ranges
# ===========================================================================

class TestNumericRanges:
    def test_valid_values(self):
        df = _make_df()
        assert check_numeric_ranges(df) == []

    def test_negative_par_value(self):
        df = _make_df({"par_value": "-500000"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "NEGATIVE_PAR_VALUE" for i in issues)

    def test_zero_par_value(self):
        df = _make_df({"par_value": "0"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "NEGATIVE_PAR_VALUE" for i in issues)

    def test_non_numeric_par(self):
        df = _make_df({"par_value": "abc"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "NON_NUMERIC_PAR" for i in issues)

    def test_par_with_dollar_sign(self):
        df = _make_df({"par_value": "$5,000,000"})
        issues = check_numeric_ranges(df)
        assert not any(i.rule == "NON_NUMERIC_PAR" for i in issues)

    def test_negative_coupon(self):
        df = _make_df({"coupon_rate": "-2.5"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "NEGATIVE_COUPON" for i in issues)

    def test_zero_coupon_valid(self):
        df = _make_df({"coupon_rate": "0"})
        issues = check_numeric_ranges(df)
        assert not any(i.rule == "NEGATIVE_COUPON" for i in issues)

    def test_high_coupon_warning(self):
        df = _make_df({"coupon_rate": "22.5"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "HIGH_COUPON" and i.severity == Severity.WARNING for i in issues)

    def test_coupon_at_15_boundary(self):
        df = _make_df({"coupon_rate": "15.0"})
        issues = check_numeric_ranges(df)
        assert not any(i.rule == "HIGH_COUPON" for i in issues)

    def test_coupon_just_over_15(self):
        df = _make_df({"coupon_rate": "15.1"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "HIGH_COUPON" for i in issues)

    def test_unusually_large_par(self):
        df = _make_df({"par_value": "5000000000"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "UNUSUAL_PAR_VALUE" for i in issues)

    def test_non_numeric_coupon(self):
        df = _make_df({"coupon_rate": "N/A"})
        issues = check_numeric_ranges(df)
        assert any(i.rule == "NON_NUMERIC_COUPON" for i in issues)

    def test_coupon_with_percent_sign(self):
        df = _make_df({"coupon_rate": "4.25%"})
        issues = check_numeric_ranges(df)
        assert not any(i.rule == "NON_NUMERIC_COUPON" for i in issues)

    def test_empty_values_skipped(self):
        df = _make_df({"par_value": "", "coupon_rate": ""})
        issues = check_numeric_ranges(df)
        assert len(issues) == 0


# ===========================================================================
# 7. check_state_codes
# ===========================================================================

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
        for terr in ["PR", "GU", "VI", "DC", "AS"]:
            df = _make_df({"state": terr})
            assert check_state_codes(df) == [], f"Failed for territory {terr}"

    def test_all_50_states_valid(self):
        for state in VALID_STATES:
            df = _make_df({"state": state})
            assert check_state_codes(df) == [], f"Failed for state {state}"

    def test_lowercase_state_still_valid(self):
        df = _make_df({"state": "ca"})
        assert check_state_codes(df) == []  # validator uppercases

    def test_three_letter_code_invalid(self):
        df = _make_df({"state": "CAL"})
        issues = check_state_codes(df)
        assert len(issues) == 1

    def test_empty_skipped(self):
        df = _make_df({"state": ""})
        assert check_state_codes(df) == []

    def test_multiple_invalid_states(self):
        df = _make_df({"state": ["XX", "YY", "TX"]}, rows=3)
        issues = check_state_codes(df)
        assert len(issues) == 2


# ===========================================================================
# 8. check_bond_type (instrument type)
# ===========================================================================

class TestBondType:
    def test_all_valid_types(self):
        for bt in VALID_BOND_TYPES:
            df = _make_df({"bond_type": bt})
            assert check_bond_type(df) == [], f"Failed for type {bt}"

    def test_unknown_type(self):
        df = _make_df({"bond_type": "XYZ"})
        issues = check_bond_type(df)
        assert len(issues) == 1
        assert issues[0].rule == "UNKNOWN_BOND_TYPE"

    def test_case_insensitive(self):
        df = _make_df({"bond_type": "go"})
        assert check_bond_type(df) == []

    def test_empty_skipped(self):
        df = _make_df({"bond_type": ""})
        assert check_bond_type(df) == []

    def test_multiple_unknown(self):
        df = _make_df({"bond_type": ["GO", "XYZ", "ABC", "REV"]}, rows=4)
        issues = check_bond_type(df)
        assert len(issues) == 2


# ===========================================================================
# 9. check_issuer_name_quality
# ===========================================================================

class TestIssuerNameQuality:
    def test_normal_name(self):
        df = _make_df({"issuer_name": "City of Austin Texas"})
        assert check_issuer_name_quality(df) == []

    def test_short_name_2_chars(self):
        df = _make_df({"issuer_name": "AB"})
        issues = check_issuer_name_quality(df)
        assert any(i.rule == "SHORT_ISSUER_NAME" for i in issues)

    def test_short_name_1_char(self):
        df = _make_df({"issuer_name": "X"})
        issues = check_issuer_name_quality(df)
        assert any(i.rule == "SHORT_ISSUER_NAME" for i in issues)

    def test_three_char_name_passes(self):
        df = _make_df({"issuer_name": "NYC"})
        assert check_issuer_name_quality(df) == []

    def test_numeric_name(self):
        df = _make_df({"issuer_name": "12345"})
        issues = check_issuer_name_quality(df)
        assert any(i.rule == "NUMERIC_ISSUER_NAME" for i in issues)

    def test_alphanumeric_name_passes(self):
        df = _make_df({"issuer_name": "District 5 Water"})
        issues = check_issuer_name_quality(df)
        assert not any(i.rule == "NUMERIC_ISSUER_NAME" for i in issues)

    def test_empty_skipped(self):
        df = _make_df({"issuer_name": ""})
        assert check_issuer_name_quality(df) == []

    def test_short_and_numeric_both_flagged(self):
        df = _make_df({"issuer_name": "99"})
        issues = check_issuer_name_quality(df)
        rules = {i.rule for i in issues}
        assert "SHORT_ISSUER_NAME" in rules
        assert "NUMERIC_ISSUER_NAME" in rules


# ===========================================================================
# 10. check_cusip_check_digit (Luhn algorithm)
# ===========================================================================

class TestCusipCheckDigit:
    def test_luhn_helper_known_values(self):
        assert _cusip_check_digit("912828ZT") == "0"
        assert _cusip_check_digit("03783310") == "0"  # Apple CUSIP

    def test_luhn_all_zeros(self):
        assert _cusip_check_digit("00000000") == "0"

    def test_luhn_all_nines(self):
        # Verify deterministic output
        result = _cusip_check_digit("99999999")
        assert result.isdigit()
        assert len(result) == 1

    def test_valid_check_digit_passes(self):
        df = _make_df({"cusip": "912828ZT0"})
        assert check_cusip_check_digit(df) == []

    def test_invalid_check_digit_error(self):
        df = _make_df({"cusip": "912828ZT9"})
        issues = check_cusip_check_digit(df)
        assert len(issues) == 1
        assert issues[0].rule == "CUSIP_CHECK_DIGIT"
        assert issues[0].severity == Severity.ERROR
        assert "Expected '0'" in issues[0].message

    def test_every_wrong_digit_caught(self):
        # The correct digit is 0, so digits 1-9 should all fail
        for d in "123456789":
            df = _make_df({"cusip": f"912828ZT{d}"})
            issues = check_cusip_check_digit(df)
            assert len(issues) == 1, f"Failed to catch wrong digit {d}"

    def test_skips_malformed_cusips(self):
        df = _make_df({"cusip": "12345"})
        assert check_cusip_check_digit(df) == []

    def test_skips_empty(self):
        df = _make_df({"cusip": ""})
        assert check_cusip_check_digit(df) == []

    def test_skips_nan(self):
        df = _make_df({"cusip": None})
        assert check_cusip_check_digit(df) == []

    def test_multiple_rows_mixed(self):
        df = _make_df({
            "cusip": ["912828ZT0", "912828ZT9", "912828ZT0"],
        }, rows=3)
        issues = check_cusip_check_digit(df)
        assert len(issues) == 1
        assert issues[0].row == 3  # second row (0-indexed 1) → +2 = row 3


# ===========================================================================
# 11. check_cusip_issuer_structure
# ===========================================================================

class TestCusipIssuerStructure:
    def test_numeric_issuer_code_passes(self):
        df = _make_df({"cusip": "912828ZT0"})
        issues = check_cusip_issuer_structure(df)
        assert not any(i.rule == "CUSIP_ISSUER_ANOMALY" for i in issues)

    def test_all_alpha_issuer_code_flagged(self):
        df = _make_df({"cusip": "ABCDEF123"})
        issues = check_cusip_issuer_structure(df)
        assert any(i.rule == "CUSIP_ISSUER_ANOMALY" for i in issues)
        assert any(i.severity == Severity.WARNING for i in issues)

    def test_mixed_issuer_code_not_flagged(self):
        df = _make_df({"cusip": "A12345678"})
        issues = check_cusip_issuer_structure(df)
        assert not any(i.rule == "CUSIP_ISSUER_ANOMALY" for i in issues)

    def test_placeholder_issue_id_00(self):
        df = _make_df({"cusip": "912828004"})
        issues = check_cusip_issuer_structure(df)
        assert any(i.rule == "CUSIP_PLACEHOLDER" for i in issues)
        assert any(i.severity == Severity.INFO for i in issues)

    def test_non_placeholder_issue_id(self):
        df = _make_df({"cusip": "912828ZT0"})
        issues = check_cusip_issuer_structure(df)
        assert not any(i.rule == "CUSIP_PLACEHOLDER" for i in issues)

    def test_skips_malformed(self):
        df = _make_df({"cusip": "SHORT"})
        assert check_cusip_issuer_structure(df) == []

    def test_both_anomaly_and_placeholder(self):
        # All-alpha issuer + "00" issue ID
        df = _make_df({"cusip": "ABCDEF005"})
        issues = check_cusip_issuer_structure(df)
        rules = {i.rule for i in issues}
        assert "CUSIP_ISSUER_ANOMALY" in rules
        assert "CUSIP_PLACEHOLDER" in rules


# ===========================================================================
# 12. check_coupon_bond_type_consistency
# ===========================================================================

class TestCouponTypeConsistency:
    def test_normal_go_coupon(self):
        df = _make_df({"coupon_rate": "4.25", "bond_type": "GO"})
        assert check_coupon_bond_type_consistency(df) == []

    def test_high_coupon_for_go(self):
        df = _make_df({"coupon_rate": "9.5", "bond_type": "GO"})
        issues = check_coupon_bond_type_consistency(df)
        assert any(i.rule == "COUPON_TYPE_MISMATCH" for i in issues)

    def test_high_coupon_for_tan(self):
        df = _make_df({"coupon_rate": "7.0", "bond_type": "TAN"})
        issues = check_coupon_bond_type_consistency(df)
        assert any(i.rule == "COUPON_TYPE_MISMATCH" for i in issues)

    def test_bab_high_coupon_normal(self):
        df = _make_df({"coupon_rate": "6.0", "bond_type": "BAB"})
        assert check_coupon_bond_type_consistency(df) == []

    def test_bab_too_high(self):
        df = _make_df({"coupon_rate": "12.0", "bond_type": "BAB"})
        issues = check_coupon_bond_type_consistency(df)
        assert any(i.rule == "COUPON_TYPE_MISMATCH" for i in issues)

    def test_zero_coupon_no_issue(self):
        df = _make_df({"coupon_rate": "0", "bond_type": "GO"})
        assert check_coupon_bond_type_consistency(df) == []

    def test_rev_at_boundary(self):
        df = _make_df({"coupon_rate": "8.0", "bond_type": "REV"})
        assert check_coupon_bond_type_consistency(df) == []

    def test_rev_over_boundary(self):
        df = _make_df({"coupon_rate": "8.5", "bond_type": "REV"})
        issues = check_coupon_bond_type_consistency(df)
        assert any(i.rule == "COUPON_TYPE_MISMATCH" for i in issues)

    def test_unknown_type_skipped(self):
        # Types not in the lookup table should be silently skipped
        df = _make_df({"coupon_rate": "50.0", "bond_type": "OTHER"})
        assert check_coupon_bond_type_consistency(df) == []

    def test_missing_columns_skipped(self):
        df = _make_df().drop(columns=["coupon_rate"])
        assert check_coupon_bond_type_consistency(df) == []

    def test_nan_values_skipped(self):
        df = _make_df({"coupon_rate": None, "bond_type": "GO"})
        assert check_coupon_bond_type_consistency(df) == []


# ===========================================================================
# 13. check_maturity_term_limits
# ===========================================================================

class TestMaturityTermLimits:
    def test_normal_go_20_year_term(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2043-01-15", "bond_type": "GO"})
        assert check_maturity_term_limits(df) == []

    def test_go_exceeds_30_years(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2058-01-15", "bond_type": "GO"})
        issues = check_maturity_term_limits(df)
        assert any(i.rule == "EXCESSIVE_MATURITY_TERM" for i in issues)

    def test_go_at_29_years(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2052-01-15", "bond_type": "GO"})
        issues = check_maturity_term_limits(df)
        # 29 years is under the 30-year limit
        assert not any(i.rule == "EXCESSIVE_MATURITY_TERM" for i in issues)

    def test_tan_over_2_years(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2028-01-15", "bond_type": "TAN"})
        issues = check_maturity_term_limits(df)
        assert any(i.rule == "EXCESSIVE_MATURITY_TERM" for i in issues)

    def test_tan_under_2_years(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2024-06-15", "bond_type": "TAN"})
        assert check_maturity_term_limits(df) == []

    def test_rev_40_years_ok(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2063-01-15", "bond_type": "REV"})
        assert check_maturity_term_limits(df) == []

    def test_extreme_term_over_50_years(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2080-01-15", "bond_type": "REV"})
        issues = check_maturity_term_limits(df)
        assert any(i.rule == "EXTREME_MATURITY_TERM" for i in issues)
        assert any(i.severity == Severity.ERROR for i in issues)

    def test_negative_term_skipped(self):
        # Maturity before issue — handled by date validator, not this one
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2020-01-15", "bond_type": "GO"})
        issues = check_maturity_term_limits(df)
        assert not any(i.rule == "EXCESSIVE_MATURITY_TERM" for i in issues)

    def test_unparseable_dates_skipped(self):
        df = _make_df({"issue_date": "bad", "maturity_date": "2033-01-15", "bond_type": "GO"})
        assert check_maturity_term_limits(df) == []

    def test_unknown_type_no_limit(self):
        df = _make_df({"issue_date": "2023-01-15", "maturity_date": "2060-01-15", "bond_type": "OTHER"})
        issues = check_maturity_term_limits(df)
        # OTHER is not in the limits table, but 37 years < 50 → no extreme flag
        assert not any(i.rule == "EXCESSIVE_MATURITY_TERM" for i in issues)


# ===========================================================================
# 14. check_par_value_by_bond_type
# ===========================================================================

class TestParValueByType:
    def test_normal_go_par(self):
        df = _make_df({"par_value": "5000000", "bond_type": "GO"})
        assert check_par_value_by_bond_type(df) == []

    def test_go_par_at_max(self):
        df = _make_df({"par_value": "500000000", "bond_type": "GO"})
        assert check_par_value_by_bond_type(df) == []

    def test_go_par_over_max(self):
        df = _make_df({"par_value": "600000000", "bond_type": "GO"})
        issues = check_par_value_by_bond_type(df)
        assert any(i.rule == "PAR_TYPE_MISMATCH" for i in issues)

    def test_tan_excessive_par(self):
        df = _make_df({"par_value": "300000000", "bond_type": "TAN"})
        issues = check_par_value_by_bond_type(df)
        assert any(i.rule == "PAR_TYPE_MISMATCH" for i in issues)

    def test_par_below_minimum(self):
        df = _make_df({"par_value": "500", "bond_type": "GO"})
        issues = check_par_value_by_bond_type(df)
        assert any(i.rule == "PAR_BELOW_MINIMUM" for i in issues)

    def test_par_at_minimum(self):
        df = _make_df({"par_value": "1000", "bond_type": "GO"})
        assert check_par_value_by_bond_type(df) == []

    def test_unknown_type_skipped(self):
        df = _make_df({"par_value": "999999999", "bond_type": "OTHER"})
        assert check_par_value_by_bond_type(df) == []

    def test_nan_values_skipped(self):
        df = _make_df({"par_value": None, "bond_type": "GO"})
        assert check_par_value_by_bond_type(df) == []

    def test_missing_column_skipped(self):
        df = _make_df().drop(columns=["par_value"])
        assert check_par_value_by_bond_type(df) == []


# ===========================================================================
# 15. check_data_patterns
# ===========================================================================

class TestDataPatterns:
    def test_clean_data_no_issues(self):
        df = _make_df()
        issues = check_data_patterns(df)
        assert not any(i.rule == "TRAILING_WHITESPACE" for i in issues)
        assert not any(i.rule == "SPECIAL_CHARS_IN_NAME" for i in issues)

    def test_trailing_whitespace(self):
        df = _make_df({"issuer_name": "City of Austin  "})
        issues = check_data_patterns(df)
        assert any(i.rule == "TRAILING_WHITESPACE" for i in issues)

    def test_leading_whitespace(self):
        df = _make_df({"issuer_name": "  City of Austin"})
        issues = check_data_patterns(df)
        assert any(i.rule == "TRAILING_WHITESPACE" for i in issues)

    def test_whitespace_in_state(self):
        df = _make_df({"state": " TX"})
        issues = check_data_patterns(df)
        assert any(i.rule == "TRAILING_WHITESPACE" and i.column == "state" for i in issues)

    def test_special_characters_angle_brackets(self):
        df = _make_df({"issuer_name": "Cook County <Illinois>"})
        issues = check_data_patterns(df)
        assert any(i.rule == "SPECIAL_CHARS_IN_NAME" for i in issues)

    def test_special_characters_backslash(self):
        df = _make_df({"issuer_name": "Cook County\\Illinois"})
        issues = check_data_patterns(df)
        assert any(i.rule == "SPECIAL_CHARS_IN_NAME" for i in issues)

    def test_special_characters_pipe(self):
        df = _make_df({"issuer_name": "Cook County | Illinois"})
        issues = check_data_patterns(df)
        assert any(i.rule == "SPECIAL_CHARS_IN_NAME" for i in issues)

    def test_normal_punctuation_ok(self):
        df = _make_df({"issuer_name": "Port Authority of NY & NJ"})
        issues = check_data_patterns(df)
        assert not any(i.rule == "SPECIAL_CHARS_IN_NAME" for i in issues)

    def test_inconsistent_casing(self):
        df = _make_df({
            "issuer_name": ["City of Austin", "city of austin", "CITY OF AUSTIN"],
        }, rows=3)
        issues = check_data_patterns(df)
        assert any(i.rule == "INCONSISTENT_CASING" for i in issues)

    def test_consistent_casing_no_flag(self):
        df = _make_df({
            "issuer_name": ["City of Austin", "City of Dallas"],
        }, rows=2)
        issues = check_data_patterns(df)
        assert not any(i.rule == "INCONSISTENT_CASING" for i in issues)

    def test_nan_values_skipped(self):
        df = _make_df({"issuer_name": None})
        issues = check_data_patterns(df)
        assert not any(i.rule == "SPECIAL_CHARS_IN_NAME" for i in issues)


# ===========================================================================
# 16. check_copy_paste_errors
# ===========================================================================

class TestCopyPasteErrors:
    def test_single_row_no_issues(self):
        df = _make_df()
        issues = check_copy_paste_errors(df)
        assert not any(i.rule == "DUPLICATE_ROW" for i in issues)

    def test_duplicate_row_detected(self):
        df = _make_df(rows=2)  # Two identical rows
        issues = check_copy_paste_errors(df)
        assert any(i.rule == "DUPLICATE_ROW" for i in issues)

    def test_three_identical_rows(self):
        df = _make_df(rows=3)
        issues = [i for i in check_copy_paste_errors(df) if i.rule == "DUPLICATE_ROW"]
        assert len(issues) == 2  # rows 2 and 3 flagged

    def test_no_duplicate_when_different(self):
        df = _make_df({
            "cusip": ["912828ZT0", "912828ZU7"],
            "issuer_name": ["City A", "City B"],
        }, rows=2)
        issues = check_copy_paste_errors(df)
        assert not any(i.rule == "DUPLICATE_ROW" for i in issues)

    def test_copy_paste_suspected_issuer(self):
        df = _make_df({
            "cusip": [f"91282800{i}" for i in range(6)],
            "issuer_name": ["City of Austin"] * 5 + ["City of Dallas"],
        }, rows=6)
        issues = check_copy_paste_errors(df)
        assert any(i.rule == "COPY_PASTE_SUSPECTED" for i in issues)

    def test_copy_paste_not_triggered_under_5_rows(self):
        df = _make_df({
            "cusip": ["912828ZT0", "912828ZU7", "912828ZW3"],
            "issuer_name": ["Same Name"] * 3,
        }, rows=3)
        issues = check_copy_paste_errors(df)
        assert not any(i.rule == "COPY_PASTE_SUSPECTED" for i in issues)

    def test_copy_paste_under_60_percent(self):
        df = _make_df({
            "cusip": [f"91282800{i}" for i in range(10)],
            "issuer_name": ["City of Austin"] * 5 + [f"City {i}" for i in range(5)],
        }, rows=10)
        issues = check_copy_paste_errors(df)
        # 50% concentration — should NOT trigger (threshold is >60%)
        assert not any(i.rule == "COPY_PASTE_SUSPECTED" and i.column == "issuer_name" for i in issues)

    def test_copy_paste_par_value(self):
        df = _make_df({
            "cusip": [f"91282800{i}" for i in range(6)],
            "par_value": ["5000000"] * 5 + ["10000000"],
            "issuer_name": [f"Issuer {i}" for i in range(6)],
        }, rows=6)
        issues = check_copy_paste_errors(df)
        assert any(i.rule == "COPY_PASTE_SUSPECTED" and i.column == "par_value" for i in issues)


# ===========================================================================
# 17. check_issuer_state_consistency
# ===========================================================================

class TestIssuerStateConsistency:
    def test_consistent_state(self):
        df = _make_df({"issuer_name": "City of Austin Texas", "state": "TX"})
        assert check_issuer_state_consistency(df) == []

    def test_mismatched_state(self):
        df = _make_df({"issuer_name": "City of Houston Texas", "state": "CA"})
        issues = check_issuer_state_consistency(df)
        assert any(i.rule == "ISSUER_STATE_MISMATCH" for i in issues)

    def test_no_state_in_name(self):
        df = _make_df({"issuer_name": "Metro Transit Authority", "state": "NY"})
        assert check_issuer_state_consistency(df) == []

    def test_california_mismatch(self):
        df = _make_df({"issuer_name": "State of California", "state": "TX"})
        issues = check_issuer_state_consistency(df)
        assert any(i.rule == "ISSUER_STATE_MISMATCH" for i in issues)

    def test_california_match(self):
        df = _make_df({"issuer_name": "State of California", "state": "CA"})
        assert check_issuer_state_consistency(df) == []

    def test_massachusetts_mismatch(self):
        df = _make_df({"issuer_name": "Commonwealth of Massachusetts", "state": "NY"})
        issues = check_issuer_state_consistency(df)
        assert any(i.rule == "ISSUER_STATE_MISMATCH" for i in issues)

    def test_short_state_names_not_false_positive(self):
        # "New" is only 3 chars — should not match "NE" (Nebraska)
        df = _make_df({"issuer_name": "New York City Authority", "state": "NY"})
        issues = check_issuer_state_consistency(df)
        assert not any(i.rule == "ISSUER_STATE_MISMATCH" for i in issues)

    def test_nan_values_skipped(self):
        df = _make_df({"issuer_name": None, "state": "TX"})
        assert check_issuer_state_consistency(df) == []

    def test_multiple_rows_mixed(self):
        df = _make_df({
            "issuer_name": ["City of Austin Texas", "State of Florida", "Some Entity"],
            "state": ["TX", "NY", "CA"],
        }, rows=3)
        issues = check_issuer_state_consistency(df)
        # Row 2: Florida vs NY → mismatch
        assert len(issues) == 1
        assert issues[0].row == 3  # 0-indexed row 1 → +2 = row 3


# ===========================================================================
# Integration: run_all_validators
# ===========================================================================

class TestRunAllValidators:
    def test_clean_data(self):
        df = _make_df()
        result = run_all_validators(df, "test.csv")
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.pass_rate == 100.0
        assert result.is_clean
        assert result.validators_run == 17

    def test_messy_data_has_issues(self):
        df = pd.DataFrame({
            "cusip": ["912828ZT0", "INVALID", "", "912828ZT0"],
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
        assert result.validators_run == 17

    def test_pass_rate_calculation(self):
        df = pd.DataFrame({
            "cusip": ["912828ZT0", "SHORT"],
            "issuer_name": ["City A", "City B"],
            "state": ["TX", "CA"],
            "issue_date": ["2023-01-15", "2023-01-15"],
            "maturity_date": ["2033-01-15", "2033-01-15"],
            "par_value": ["5000000", "5000000"],
            "coupon_rate": ["4.25", "4.25"],
            "bond_type": ["GO", "GO"],
        })
        result = run_all_validators(df, "test.csv")
        assert result.pass_rate == 50.0

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=REQUIRED_COLUMNS)
        result = run_all_validators(df, "empty.csv")
        assert result.total_rows == 0
        assert result.pass_rate == 0.0

    def test_result_properties(self):
        df = _make_df()
        result = run_all_validators(df, "test.csv")
        assert isinstance(result, ValidationResult)
        assert result.file_name == "test.csv"
        assert result.total_rows == 1
        assert result.total_columns == 8

    def test_issues_sorted_by_row_then_severity(self):
        df = pd.DataFrame({
            "cusip": ["SHORT", "912828ZT9"],
            "issuer_name": ["AB", "Good Name Here"],
            "state": ["XX", "TX"],
            "issue_date": ["2023-01-15", "2023-01-15"],
            "maturity_date": ["2033-01-15", "2033-01-15"],
            "par_value": ["5000000", "5000000"],
            "coupon_rate": ["4.25", "4.25"],
            "bond_type": ["GO", "GO"],
        })
        result = run_all_validators(df, "test.csv")
        # Verify issues are sorted: row 2 issues before row 3
        rows = [i.row for i in result.issues if i.row is not None]
        assert rows == sorted(rows)

    def test_column_normalization(self):
        df = _make_df()
        df.columns = [c.upper() for c in df.columns]
        result = run_all_validators(df, "test.csv")
        # Should still work — columns get lowercased
        assert result.validators_run == 17


# ===========================================================================
# Validator result model
# ===========================================================================

class TestValidationResult:
    def test_error_count(self):
        result = ValidationResult(file_name="test.csv", total_rows=10, total_columns=8)
        result.issues.append(
            _make_issue(Severity.ERROR)
        )
        result.issues.append(
            _make_issue(Severity.WARNING)
        )
        assert result.error_count == 1
        assert result.warning_count == 1

    def test_info_count(self):
        result = ValidationResult(file_name="test.csv", total_rows=10, total_columns=8)
        result.issues.append(_make_issue(Severity.INFO))
        result.issues.append(_make_issue(Severity.INFO))
        assert result.info_count == 2

    def test_is_clean(self):
        result = ValidationResult(file_name="test.csv", total_rows=10, total_columns=8)
        assert result.is_clean
        result.issues.append(_make_issue(Severity.INFO))
        assert result.is_clean  # info doesn't break "clean"
        result.issues.append(_make_issue(Severity.WARNING))
        assert not result.is_clean

    def test_pass_rate_all_clean(self):
        result = ValidationResult(file_name="test.csv", total_rows=5, total_columns=8)
        assert result.pass_rate == 100.0  # no issues

    def test_pass_rate_zero_rows(self):
        result = ValidationResult(file_name="test.csv", total_rows=0, total_columns=8)
        assert result.pass_rate == 0.0


def _make_issue(severity, row=1, column="cusip", rule="TEST"):
    from munibond_validator.validators import ValidationIssue
    return ValidationIssue(row=row, column=column, severity=severity, rule=rule, message="test")
