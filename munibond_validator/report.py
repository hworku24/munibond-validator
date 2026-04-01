"""
Report generators for validation results.

Supports:
  - Rich console output (terminal)
  - HTML report
  - JSON report
"""

import json
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from .validators import ValidationResult, Severity


# ---------------------------------------------------------------------------
# Console report (using Rich)
# ---------------------------------------------------------------------------

def print_console_report(result: ValidationResult) -> None:
    """Pretty-print the validation report to the terminal using Rich."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    console = Console()

    # Header
    status_color = "green" if result.is_clean else ("red" if result.error_count > 0 else "yellow")
    status_text = "PASS" if result.is_clean else "FAIL"

    console.print()
    console.print(Panel(
        f"[bold]{result.file_name}[/bold]\n"
        f"Rows: {result.total_rows}  |  Columns: {result.total_columns}  |  "
        f"Validators: {result.validators_run}\n"
        f"Status: [{status_color} bold]{status_text}[/{status_color} bold]  |  "
        f"Pass Rate: [{status_color}]{result.pass_rate}%[/{status_color}]",
        title="[bold blue]MuniBond Data Validation Report[/bold blue]",
        border_style="blue",
    ))

    # Summary bar
    console.print(
        f"  [red]Errors: {result.error_count}[/red]  |  "
        f"[yellow]Warnings: {result.warning_count}[/yellow]  |  "
        f"[cyan]Info: {result.info_count}[/cyan]"
    )
    console.print()

    if not result.issues:
        console.print("[green bold]  ✔ No issues found — data looks clean![/green bold]\n")
        return

    # Issues table
    table = Table(show_header=True, header_style="bold", show_lines=False, pad_edge=True)
    table.add_column("Row", style="dim", width=5, justify="right")
    table.add_column("Column", width=16)
    table.add_column("Severity", width=9, justify="center")
    table.add_column("Rule", width=22)
    table.add_column("Message", min_width=40)

    severity_styles = {
        Severity.ERROR: "[red bold]ERROR[/red bold]",
        Severity.WARNING: "[yellow]WARN[/yellow]",
        Severity.INFO: "[cyan]INFO[/cyan]",
    }

    for issue in result.issues:
        table.add_row(
            str(issue.row) if issue.row else "—",
            issue.column or "—",
            severity_styles.get(issue.severity, str(issue.severity.value)),
            issue.rule,
            issue.message,
        )

    console.print(table)
    console.print()

    # Per-rule summary
    rule_counts: dict[str, int] = {}
    for issue in result.issues:
        rule_counts[issue.rule] = rule_counts.get(issue.rule, 0) + 1

    console.print("[bold]Issue Breakdown by Rule:[/bold]")
    for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        console.print(f"  {rule:<28} {count}")
    console.print()


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MuniBond Validation Report — {{ result.file_name }}</title>
<style>
  :root { --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --accent: #3b82f6;
          --red: #ef4444; --yellow: #eab308; --green: #22c55e; --cyan: #06b6d4; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg);
         color: var(--text); padding: 2rem; line-height: 1.6; }
  .container { max-width: 1100px; margin: 0 auto; }
  h1 { color: var(--accent); margin-bottom: 0.5rem; font-size: 1.8rem; }
  .meta { color: #94a3b8; margin-bottom: 1.5rem; }
  .summary { display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }
  .stat { background: var(--card); border-radius: 10px; padding: 1.2rem 1.6rem;
          flex: 1; min-width: 140px; text-align: center; }
  .stat .num { font-size: 2rem; font-weight: 700; }
  .stat .label { font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; }
  .stat.errors .num { color: var(--red); }
  .stat.warnings .num { color: var(--yellow); }
  .stat.pass .num { color: var(--green); }
  .stat.rows .num { color: var(--cyan); }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 6px;
           font-size: 0.78rem; font-weight: 600; text-transform: uppercase; }
  .badge.error { background: rgba(239,68,68,0.2); color: var(--red); }
  .badge.warning { background: rgba(234,179,8,0.2); color: var(--yellow); }
  .badge.info { background: rgba(6,182,212,0.2); color: var(--cyan); }
  table { width: 100%; border-collapse: collapse; background: var(--card);
          border-radius: 10px; overflow: hidden; margin-bottom: 2rem; }
  th { background: #334155; padding: 12px 14px; text-align: left;
       font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; }
  td { padding: 10px 14px; border-top: 1px solid #334155; font-size: 0.9rem; }
  tr:hover td { background: rgba(59,130,246,0.06); }
  .clean { text-align: center; padding: 3rem; color: var(--green); font-size: 1.2rem; }
  footer { color: #475569; text-align: center; margin-top: 2rem; font-size: 0.8rem; }
</style>
</head>
<body>
<div class="container">
  <h1>MuniBond Validation Report</h1>
  <p class="meta">File: <strong>{{ result.file_name }}</strong> &nbsp;|&nbsp;
     Generated: {{ timestamp }}</p>

  <div class="summary">
    <div class="stat rows"><div class="num">{{ result.total_rows }}</div><div class="label">Rows</div></div>
    <div class="stat errors"><div class="num">{{ result.error_count }}</div><div class="label">Errors</div></div>
    <div class="stat warnings"><div class="num">{{ result.warning_count }}</div><div class="label">Warnings</div></div>
    <div class="stat pass"><div class="num">{{ result.pass_rate }}%</div><div class="label">Pass Rate</div></div>
  </div>

  {% if result.issues %}
  <table>
    <thead>
      <tr><th>Row</th><th>Column</th><th>Severity</th><th>Rule</th><th>Message</th></tr>
    </thead>
    <tbody>
    {% for issue in result.issues %}
      <tr>
        <td>{{ issue.row if issue.row else '—' }}</td>
        <td>{{ issue.column if issue.column else '—' }}</td>
        <td><span class="badge {{ issue.severity.value }}">{{ issue.severity.value }}</span></td>
        <td>{{ issue.rule }}</td>
        <td>{{ issue.message }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="clean">✔ No issues found — data looks clean!</div>
  {% endif %}

  <footer>Generated by MuniBond Validator v1.0.0</footer>
</div>
</body>
</html>"""


def generate_html_report(result: ValidationResult, output_path: str | Path) -> Path:
    """Render the validation result as an HTML file."""
    template = Template(HTML_TEMPLATE)
    html = template.render(result=result, timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    path = Path(output_path)
    path.write_text(html, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def generate_json_report(result: ValidationResult, output_path: str | Path) -> Path:
    """Export validation results as structured JSON."""
    data = {
        "file_name": result.file_name,
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_rows": result.total_rows,
            "total_columns": result.total_columns,
            "validators_run": result.validators_run,
            "errors": result.error_count,
            "warnings": result.warning_count,
            "info": result.info_count,
            "pass_rate": result.pass_rate,
        },
        "issues": [
            {
                "row": i.row,
                "column": i.column,
                "severity": i.severity.value,
                "rule": i.rule,
                "message": i.message,
            }
            for i in result.issues
        ],
    }
    path = Path(output_path)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
