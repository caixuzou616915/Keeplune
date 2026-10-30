#!/usr/bin/env python3
"""
generate_test_report.py

Renders a white-box use-case test report (paired .md + .html) from a JSON spec,
following the canonical structure documented in
.github/skills/whitebox-test-report/SKILL.md.

Usage:
    python generate_test_report.py --spec my_module_report.json \
        --out-md ai_output/MyModule_UseCaseTesting.md \
        --out-html ai_output/MyModule_UseCaseTesting.html

See references/example_spec.json (sibling to this skill's SKILL.md) for the full
JSON schema.
"""
import argparse
import html
import json
import sys
from pathlib import Path

PENDING = "\u23f3 pending"  # hourglass

STATUS_CLASS_BY_PREFIX = [
    ("\u2705", "pass"),      # ✅
    ("\u26a0\ufe0f", "partial"),  # ⚠️
    ("\u274c", "blocked"),   # ❌
    ("\u2139\ufe0f", "info"),  # ℹ️
    ("\u23f3", "info"),      # ⏳ pending
]


def status_class(result_text: str) -> str:
    text = (result_text or "").strip()
    for prefix, css_class in STATUS_CLASS_BY_PREFIX:
        if text.startswith(prefix):
            return css_class
    return ""


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def render_md(spec: dict) -> str:
    module = spec["module"]
    lines = []
    lines.append(f"# {module['name']} White-Box Use Case Testing")
    lines.append("")
    lines.append(f"**Module**: {module['description']}")
    lines.append(f"**Method**: {module.get('method', 'White-box, on-target (GHS Multi / Lauterbach TRACE32 debugger).')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| # | Test Case | Result / Status |")
    lines.append("|---|-----------|------------------|")
    for tc in spec["test_cases"]:
        lines.append(f"| {tc['id']} | {tc['title']} | {tc.get('status', PENDING)} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Detailed Test Cases")
    lines.append("")

    for tc in spec["test_cases"]:
        lines.append(f"### {tc['id']} — {tc['title']}")
        lines.append("")
        lines.append(f"**Description / Purpose**: {tc['description']}")
        lines.append("")
        lines.append(f"**Traceability**: {tc['traceability']}")
        lines.append("")
        lines.append(f"**Test Script(s)**: {tc['scripts']}")
        lines.append("")
        lines.append("| # | What to do | How to do exactly | Expectation | Result |")
        lines.append("|---|-----------|--------------------|--------------|--------|")
        for step in tc["steps"]:
            result = step.get("result") or PENDING
            expectation = step.get("expectation") or "None"
            lines.append(
                f"| {step['step']} | {step['what']} | {step['how']} | {expectation} | {result} |"
            )
        lines.append("")
        summary = tc.get("summary") or "Not yet executed."
        lines.append(f"**Summary**: {summary}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(
        "*Full execution logs and RC/Python scripts are archived under the build "
        "output folder; file names for each step are listed under each use case's "
        '"Test Script(s)" line.*'
    )
    return "\n".join(lines) + "\n"


CSS = """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary-color: #2c3e50;
            --secondary-color: #3498db;
            --success-color: #27ae60;
            --warning-color: #f39c12;
            --danger-color: #e74c3c;
            --bg-color: #ecf0f1;
            --card-bg: #ffffff;
            --text-color: #2c3e50;
            --border-color: #bdc3c7;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6; color: var(--text-color); background: var(--bg-color); padding: 20px;
        }
        .container {
            max-width: 1300px; margin: 0 auto; background: var(--card-bg);
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden;
        }
        header {
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
            color: white; padding: 30px 40px; text-align: center;
        }
        header h1 { font-size: 1.9em; margin-bottom: 6px; }
        header .subtitle { opacity: 0.9; font-size: 0.95em; }
        section { padding: 30px 40px; }
        h2 { color: var(--primary-color); border-bottom: 2px solid var(--secondary-color); padding-bottom: 8px; margin-bottom: 16px; }
        h3 { color: var(--primary-color); margin: 30px 0 8px; }
        p.meta { margin: 4px 0; font-size: 0.95em; }
        p.meta b { color: var(--primary-color); }
        table { width: 100%; border-collapse: collapse; margin: 10px 0 18px; }
        th, td { border: 1px solid var(--border-color); padding: 8px 12px; text-align: left; vertical-align: top; font-size: 0.93em; }
        th { background: var(--primary-color); color: white; }
        tr:nth-child(even) { background: #f8f9fa; }
        table.summary td:nth-child(1), table.summary th:nth-child(1) { width: 60px; }
        table.steps td:nth-child(1), table.steps th:nth-child(1) { width: 40px; text-align: center; }
        .pass { color: var(--success-color); font-weight: 700; }
        .partial { color: var(--warning-color); font-weight: 700; }
        .blocked { color: var(--danger-color); font-weight: 700; }
        .info { color: #7f8c8d; font-weight: 600; }
        code { background: #f4f6f7; padding: 1px 5px; border-radius: 4px; font-family: Consolas, monospace; font-size: 0.9em; }
        .test-summary { background: #f4f6f7; border-left: 4px solid var(--secondary-color); padding: 10px 16px; margin-bottom: 10px; }
        footer { text-align: center; padding: 18px; color: #7f8c8d; font-size: 0.85em; border-top: 1px solid var(--border-color); }
"""


def render_html(spec: dict) -> str:
    module = spec["module"]
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('    <meta charset="UTF-8">')
    parts.append('    <meta name="viewport" content="width=device-width, initial-scale=1.0">')
    parts.append(f"    <title>{esc(module['name'])} White-Box Use Case Testing</title>")
    parts.append(f"    <style>{CSS}    </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append('<div class="container">')
    parts.append("    <header>")
    parts.append(f"        <h1>{esc(module['name'])} White-Box Use Case Testing</h1>")
    parts.append(
        f"        <div class=\"subtitle\">{esc(module['description'])}<br>"
        f"{esc(module.get('method', 'White-box, on-target (GHS Multi / Lauterbach TRACE32 debugger)'))}</div>"
    )
    parts.append("    </header>")

    parts.append("    <section>")
    parts.append("        <h2>Summary</h2>")
    parts.append('        <table class="summary">')
    parts.append("            <thead><tr><th>#</th><th>Test Case</th><th>Result / Status</th></tr></thead>")
    parts.append("            <tbody>")
    for tc in spec["test_cases"]:
        status = tc.get("status", PENDING)
        parts.append(
            f"                <tr><td>{esc(tc['id'])}</td><td>{esc(tc['title'])}</td>"
            f'<td class="{status_class(status)}">{esc(status)}</td></tr>'
        )
    parts.append("            </tbody>")
    parts.append("        </table>")
    parts.append("    </section>")

    parts.append("    <section>")
    parts.append("        <h2>Detailed Test Cases</h2>")
    for tc in spec["test_cases"]:
        parts.append(f"        <h3>{esc(tc['id'])} \u2014 {esc(tc['title'])}</h3>")
        parts.append(f'        <p class="meta"><b>Description / Purpose:</b> {esc(tc["description"])}</p>')
        parts.append(f'        <p class="meta"><b>Traceability:</b> {esc(tc["traceability"])}</p>')
        parts.append(f'        <p class="meta"><b>Test Script(s):</b> {esc(tc["scripts"])}</p>')
        parts.append('        <table class="steps">')
        parts.append("            <thead><tr><th>#</th><th>What to do</th><th>How to do exactly</th><th>Expectation</th><th>Result</th></tr></thead>")
        parts.append("            <tbody>")
        for step in tc["steps"]:
            result = step.get("result") or PENDING
            expectation = step.get("expectation") or "None"
            parts.append(
                f"                <tr><td>{esc(str(step['step']))}</td><td>{esc(step['what'])}</td>"
                f"<td>{esc(step['how'])}</td><td>{esc(expectation)}</td>"
                f'<td class="{status_class(result)}">{esc(result)}</td></tr>'
            )
        parts.append("            </tbody>")
        parts.append("        </table>")
        summary = tc.get("summary") or "Not yet executed."
        parts.append(f'        <div class="test-summary"><b>Summary:</b> {esc(summary)}</div>')
    parts.append("    </section>")

    parts.append("    <footer>")
    parts.append(
        "        Full execution logs and RC/Python scripts are archived under the build output "
        'folder; file names for each step are listed under each use case\'s "Test Script(s)" line.'
    )
    parts.append("    </footer>")
    parts.append("</div>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, help="Path to the JSON spec file")
    parser.add_argument("--out-md", required=True, help="Output path for the .md report")
    parser.add_argument("--out-html", required=True, help="Output path for the .html report")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    for key in ("module", "test_cases"):
        if key not in spec:
            print(f"error: spec is missing required key '{key}'", file=sys.stderr)
            sys.exit(1)

    md_out = Path(args.out_md)
    html_out = Path(args.out_html)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    html_out.parent.mkdir(parents=True, exist_ok=True)

    md_out.write_text(render_md(spec), encoding="utf-8")
    html_out.write_text(render_html(spec), encoding="utf-8")

    print(f"Wrote {md_out}")
    print(f"Wrote {html_out}")


if __name__ == "__main__":
    main()
