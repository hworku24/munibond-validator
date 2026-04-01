"""
CLI entry point for MuniBond Validator.

Usage:
    python -m munibond_validator.main data.csv
    python -m munibond_validator.main data.xlsx --format html --output report.html
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from .validators import run_all_validators
from .report import print_console_report, generate_html_report, generate_json_report


def load_data(file_path: str) -> pd.DataFrame:
    """Load a CSV or Excel file into a DataFrame."""
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str)
    elif suffix in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str, engine="openpyxl")
    else:
        print(f"Error: Unsupported file format '{suffix}'. Use .csv or .xlsx.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="munibond-validate",
        description="Validate municipal bond data files for quality and consistency.",
    )
    parser.add_argument("file", help="Path to the CSV or Excel file to validate.")
    parser.add_argument(
        "--format", "-f",
        choices=["console", "html", "json", "all"],
        default="console",
        help="Output format (default: console).",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path for html/json reports (default: reports/<filename>.<ext>).",
    )

    args = parser.parse_args()

    # Load and validate
    df = load_data(args.file)
    result = run_all_validators(df, file_name=Path(args.file).name)

    # Determine output directory
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    stem = Path(args.file).stem

    # Generate reports
    if args.format in ("console", "all"):
        print_console_report(result)

    if args.format in ("html", "all"):
        out = args.output or str(reports_dir / f"{stem}_report.html")
        path = generate_html_report(result, out)
        print(f"HTML report saved to: {path}")

    if args.format in ("json", "all"):
        out = args.output if args.format == "json" else str(reports_dir / f"{stem}_report.json")
        path = generate_json_report(result, out)
        print(f"JSON report saved to: {path}")

    # Exit code: 1 if errors found, 0 otherwise
    sys.exit(1 if result.error_count > 0 else 0)


if __name__ == "__main__":
    main()
