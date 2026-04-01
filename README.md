# MuniBond Validator

A data quality validation tool purpose-built for municipal bond records. Upload a CSV or Excel file of bond data and get an instant quality report — flagging format errors, missing fields, logical inconsistencies, and suspicious values.

Built with Python, Pandas, and Rich for beautiful terminal output. Generates HTML and JSON reports for sharing with teams.

---

## Why This Exists

Municipal bond data flows through multiple systems — from issuers to underwriters to data vendors to end users. At every handoff, errors creep in: truncated CUSIPs, flipped dates, negative par values, invalid state codes. This tool catches those issues before they become expensive problems downstream.

---

## Features

| Validation Rule | What It Catches | Severity |
|---|---|---|
| **Required Columns** | Missing columns in the dataset | Error |
| **Missing Values** | Blank or null fields in required columns | Error |
| **CUSIP Format** | CUSIPs that aren't 9 alphanumeric characters | Error |
| **Duplicate CUSIPs** | Repeated CUSIP identifiers | Warning |
| **Date Validity** | Unparseable dates, future issue dates | Error/Warning |
| **Maturity Logic** | Maturity date on or before issue date | Error |
| **Numeric Ranges** | Negative par values, impossible coupon rates | Error |
| **Unusual Values** | Extremely large par values, high coupon rates | Warning |
| **State Codes** | Invalid US state/territory abbreviations | Error |
| **Bond Type** | Unrecognized bond classifications | Warning |
| **Issuer Name Quality** | Suspiciously short or numeric issuer names | Warning |

---

## Quick Start

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/munibond-validator.git
cd munibond-validator
pip install -r requirements.txt
```

### Run Against Sample Data

```bash
# Clean data — should pass with 0 issues
python -m munibond_validator.main sample_data/bonds_clean.csv

# Messy data — demonstrates all validation rules
python -m munibond_validator.main sample_data/bonds_messy.csv
```

### Generate Reports

```bash
# HTML report (great for sharing)
python -m munibond_validator.main sample_data/bonds_messy.csv --format html

# JSON report (for programmatic use)
python -m munibond_validator.main sample_data/bonds_messy.csv --format json

# All formats at once
python -m munibond_validator.main sample_data/bonds_messy.csv --format all
```

---

## Example Output

### Terminal (Rich)

```
╭──────────── MuniBond Data Validation Report ────────────╮
│ bonds_messy.csv                                         │
│ Rows: 15  |  Columns: 8  |  Validators: 9              │
│ Status: FAIL  |  Pass Rate: 40.0%                       │
╰─────────────────────────────────────────────────────────╯
  Errors: 12  |  Warnings: 7  |  Info: 0

  Row  Column          Severity  Rule                    Message
   3   cusip           ERROR     CUSIP_FORMAT            Invalid CUSIP format: 'INVALID99'...
   6   issuer_name     ERROR     MISSING_VALUE           Required field 'issuer_name' is empty.
   7   state           ERROR     INVALID_STATE           'XX' is not a valid state code.
   ...
```

### HTML Report

The HTML report features a dark-themed dashboard with summary statistics, color-coded severity badges, and a searchable issues table. Generate one with `--format html` and open it in your browser.

---

## Expected Data Format

Your CSV or Excel file should include these columns (case-insensitive):

| Column | Type | Description | Example |
|---|---|---|---|
| `cusip` | String | 9-character CUSIP identifier | `912828ZT6` |
| `issuer_name` | String | Name of the bond issuer | `City of Austin Texas` |
| `state` | String | 2-letter US state/territory code | `TX` |
| `issue_date` | Date | Bond issuance date | `2023-01-15` |
| `maturity_date` | Date | Bond maturity date | `2033-01-15` |
| `par_value` | Numeric | Face value in USD | `5000000` |
| `coupon_rate` | Numeric | Annual coupon rate (%) | `4.25` |
| `bond_type` | String | Bond classification code | `GO` |

### Recognized Bond Types

`GO` (General Obligation), `REV` (Revenue), `BAB` (Build America), `CD` (Certificate of Deposit), `IDR` (Industrial Development Revenue), `TAN` (Tax Anticipation Note), `BAN` (Bond Anticipation Note), `RAN` (Revenue Anticipation Note), `TRAN` (Tax & Revenue Anticipation Note), `COPs` (Certificates of Participation), `HFA` (Housing Finance Authority), `OTHER`

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Project Structure

```
munibond-validator/
├── munibond_validator/
│   ├── __init__.py
│   ├── main.py            # CLI entry point
│   ├── validators.py      # Core validation rules
│   └── report.py          # Console, HTML, and JSON report generators
├── tests/
│   └── test_validators.py # Unit tests for all validation rules
├── sample_data/
│   ├── bonds_clean.csv    # Sample clean dataset
│   └── bonds_messy.csv    # Sample dataset with intentional errors
├── reports/               # Generated reports go here
├── requirements.txt
├── setup.py
└── README.md
```

---

## Tech Stack

- **Python 3.9+**
- **Pandas** — data loading and manipulation
- **Rich** — beautiful terminal output
- **Jinja2** — HTML report templating
- **Pytest** — test framework

---

## License

MIT
