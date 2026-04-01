# Data Integrity Validator

A data quality validation project for structured datasets. Point it at a CSV, get back a detailed report of every issue, row by row, column by column, ranked by severity.

I built this after spending too many hours debugging analytics pipelines that broke because of data issues that upstream: truncated identifiers, formatting, downstream and semantic validation. 

The architecture is extensible: each validator is a standalone function that takes a DataFrame and returns a list of typed issues. Adding a new check is just writing a function and dropping it into the registry.

## What it catches

The engine runs 17 checks across three layers:

**Structural validation** — missing columns, blank fields, malformed identifiers, unparseable dates, invalid reference codes. The baseline stuff that should never make it past ingestion.

**Identifier verification** — goes beyond format checks. Validates check digits using the Luhn algorithm (same math behind credit card validation), flags issuer codes that don't match expected patterns, and catches placeholder identifiers that suggest incomplete data.

**Cross-field logic** — this is where it gets interesting. The engine understands relationships between fields: rates that don't make sense for a given instrument type, terms that exceed typical limits, face values that are orders of magnitude off for their category. It also cross-references geographic data in text fields against coded fields to catch mismatches.

**Pattern detection** — catches the human side of data quality: trailing whitespace, inconsistent casing of the same entity name, special characters from bad exports, fully duplicated rows, and suspicious value concentrations that suggest copy-paste errors. These are the issues that automated pipelines miss because each individual value looks valid.

## Quick start

```bash
git clone https://github.com/YOUR_USERNAME/munibond-validator.git
cd munibond-validator
pip install -r requirements.txt

# Clean dataset — should pass all 17 validators
python -m munibond_validator.main sample_data/sample_clean.csv

# Messy dataset — demonstrates every kind of issue
python -m munibond_validator.main sample_data/sample_messy.csv
```

## Output formats

```bash
# Terminal — Rich-formatted tables with color-coded severity
python -m munibond_validator.main data.csv

# HTML — interactive dashboard with search, filter, and sort
python -m munibond_validator.main data.csv --format html

# JSON — structured output for piping into other tools
python -m munibond_validator.main data.csv --format json

# Excel — styled .xlsx report with summary charts
python -m munibond_validator.main data.csv --format xlsx

# Everything at once
python -m munibond_validator.main data.csv --format all
```

The HTML report is a dark-themed dashboard with live search, severity filters, sortable columns, and bar charts — designed to be shared with a team or dropped into a wiki.

## Filtering

When you're working with large datasets, you don't want to see every INFO-level whitespace issue:

```bash
# Only errors
python -m munibond_validator.main data.csv --severity error

# Only identifier-related rules
python -m munibond_validator.main data.csv --rule CUSIP

# Cap the output
python -m munibond_validator.main data.csv --limit 20
```

## Validation rules

| Rule | What it catches | Severity |
|---|---|---|
| `MISSING_COLUMN` | Required column not in dataset | Error |
| `MISSING_VALUE` | Blank/null in a required field | Error |
| `CUSIP_FORMAT` | Identifier not 9 alphanumeric characters | Error |
| `CUSIP_CHECK_DIGIT` | Luhn algorithm check digit mismatch | Error |
| `CUSIP_ISSUER_ANOMALY` | Issuer code pattern doesn't match expected type | Warning |
| `CUSIP_PLACEHOLDER` | Identifier segment suggests placeholder data | Info |
| `DUPLICATE_CUSIP` | Same identifier appears more than once | Warning |
| `INVALID_DATE` | Date value can't be parsed | Error |
| `FUTURE_ISSUE_DATE` | Date is in the future | Warning |
| `MATURITY_BEFORE_ISSUE` | End date on or before start date | Error |
| `COUPON_TYPE_MISMATCH` | Rate outside expected range for instrument type | Warning |
| `EXCESSIVE_MATURITY_TERM` | Term exceeds typical max for instrument type | Warning |
| `EXTREME_MATURITY_TERM` | Term exceeds 50 years (likely data error) | Error |
| `PAR_TYPE_MISMATCH` | Face value unusual for instrument type | Warning |
| `ISSUER_STATE_MISMATCH` | Text field suggests different geography than coded field | Warning |
| `DUPLICATE_ROW` | Entire row is identical to another | Warning |
| `COPY_PASTE_SUSPECTED` | >60% of a column shares one value | Warning |
| `TRAILING_WHITESPACE` | Leading/trailing spaces in text fields | Info |

Plus range checks for negative values, unusually large amounts, invalid reference codes, and short/numeric entity names.

## Expected input

CSV or Excel with these columns (case-insensitive):

| Column | Type | Example |
|---|---|---|
| `cusip` | 9-char identifier | `912828ZT0` |
| `issuer_name` | String | `City of Austin Texas` |
| `state` | 2-letter code | `TX` |
| `issue_date` | Date | `2023-01-15` |
| `maturity_date` | Date | `2033-01-15` |
| `par_value` | Numeric (USD) | `5000000` |
| `coupon_rate` | Numeric (%) | `4.25` |
| `bond_type` | Classification | `GO` |

## Tests

```bash
pytest tests/ -v
```

162 unit tests covering all 17 validators, including edge cases for the Luhn algorithm, cross-field logic, and pattern detection.

## Project structure

```
munibond-validator/
├── munibond_validator/
│   ├── __init__.py
│   ├── main.py            # CLI entry point (argparse)
│   ├── validators.py      # 17 validation rules + registry
│   └── report.py          # Terminal, HTML, JSON, Excel generators
├── tests/
│   └── test_validators.py
├── sample_data/
│   ├── sample_clean.csv
│   └── sample_messy.csv
├── reports/
├── requirements.txt
├── setup.py
└── README.md
```

## Built with

Python 3.9+ / Pandas / Rich / Jinja2 / openpyxl / Pytest

## License

MIT
