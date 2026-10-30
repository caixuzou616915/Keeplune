#!/usr/bin/env python3
"""
ms_traceability_html.py
=======================
Generate an HTML summary report for MTS traceability.

This script reuses the extraction and tracing logic from ms_traceability.py and
supports either:
  1. Single test file analysis (--cpp), or
  2. Module-wide analysis over all *.cpp files in a tests folder (--tests-dir).
"""

import argparse
import html
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


def load_ms_traceability_module(script_path: Path):
    """Dynamically load ms_traceability.py from the same scripts folder."""
    spec = importlib.util.spec_from_file_location("ms_traceability", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {script_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_html(
    title: str,
    model_path: Path,
    source_desc: str,
    rows: List[Dict],
    untraced: List[Dict],
    unresolved: List[Dict],
    uncovered: List[Tuple[str, str, str]],
    total_tokens: int,
    total_tests: int,
    generated_at: str,
    max_uncovered: int,
) -> str:
    """Render the report into a single self-contained HTML string."""
    covered_count = total_tokens - len(uncovered)
    coverage_pct = (covered_count / total_tokens * 100.0) if total_tokens else 0.0

    rows_html = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['file'])}</td>"
        f"<td>{row['tests']}</td>"
        f"<td>{row['fully']}</td>"
        f"<td>{row['untraced']}</td>"
        f"<td>{row['with_unresolved']}</td>"
        f"<td>{row['unresolved_refs']}</td>"
        "</tr>"
        for row in rows
    )

    untraced_html = "\n".join(
        "<li>"
        f"<span class='file'>{html.escape(entry['file'])}</span>"
        f" :: {html.escape(entry['fixture'])}.{html.escape(entry['test'])}"
        "</li>"
        for entry in untraced
    ) or "<li>None</li>"

    unresolved_html = "\n".join(
        "<li>"
        f"<span class='file'>{html.escape(entry['file'])}</span>"
        f" :: {html.escape(entry['test'])} :: {html.escape(entry['token'])}"
        "</li>"
        for entry in unresolved
    ) or "<li>None</li>"

    uncovered_limited = uncovered[:max_uncovered]
    uncovered_html = "\n".join(
        "<tr>"
        f"<td>{idx}</td>"
        f"<td>{html.escape(token)}</td>"
        f"<td>{html.escape(etype)}</td>"
        "</tr>"
        for idx, (_, token, etype) in enumerate(uncovered_limited, 1)
    ) or "<tr><td colspan='3'>None</td></tr>"

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #f4f7fb;
      --card: #ffffff;
      --ink: #1a2a3a;
      --muted: #5a6b7f;
      --accent: #0d6e6e;
      --warn: #8a5a00;
      --bad: #9a1e1e;
      --good: #1c7c35;
      --line: #d8e1ec;
    }}
    body {{ margin: 0; font-family: "Segoe UI", Tahoma, sans-serif; color: var(--ink); background: linear-gradient(160deg, #eef4fb 0%, #f7fbf9 100%); }}
    .wrap {{ max-width: 1200px; margin: 24px auto; padding: 0 16px 40px; }}
    .hero {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 20px; box-shadow: 0 6px 20px rgba(13, 36, 64, 0.08); }}
    h1 {{ margin: 0 0 8px; font-size: 1.6rem; }}
    .meta {{ color: var(--muted); font-size: 0.92rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin-top: 16px; }}
    .kpi {{ background: #f9fcff; border: 1px solid var(--line); border-radius: 10px; padding: 12px; }}
    .kpi .label {{ color: var(--muted); font-size: 0.86rem; }}
    .kpi .value {{ font-size: 1.35rem; font-weight: 700; margin-top: 4px; }}
    .good {{ color: var(--good); }}
    .bad {{ color: var(--bad); }}
    .warn {{ color: var(--warn); }}
    section {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; margin-top: 16px; padding: 16px; box-shadow: 0 4px 14px rgba(13, 36, 64, 0.06); }}
    h2 {{ margin: 0 0 10px; font-size: 1.15rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f4f8fe; }}
    ul {{ margin: 8px 0 0; padding-left: 18px; }}
    li {{ margin: 3px 0; }}
    .file {{ color: #264a73; font-weight: 600; }}
    details {{ margin-top: 6px; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 600; }}
    .foot {{ margin-top: 16px; color: var(--muted); font-size: 0.85rem; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"hero\">
      <h1>{html.escape(title)}</h1>
      <div class=\"meta\">Generated: {html.escape(generated_at)} | Model: {html.escape(str(model_path))} | Source: {html.escape(source_desc)}</div>
      <div class=\"grid\">
        <div class=\"kpi\"><div class=\"label\">Model tokens</div><div class=\"value\">{total_tokens}</div></div>
        <div class=\"kpi\"><div class=\"label\">Test files</div><div class=\"value\">{len(rows)}</div></div>
        <div class=\"kpi\"><div class=\"label\">Total test cases</div><div class=\"value\">{total_tests}</div></div>
        <div class=\"kpi\"><div class=\"label\">Unresolved token refs</div><div class=\"value good\">{len(unresolved)}</div></div>
        <div class=\"kpi\"><div class=\"label\">Untraced tests</div><div class=\"value bad\">{len(untraced)}</div></div>
        <div class=\"kpi\"><div class=\"label\">Model coverage</div><div class=\"value warn\">{covered_count}/{total_tokens} ({coverage_pct:.1f}%)</div></div>
      </div>
    </div>

    <section>
      <h2>Per-file traceability status</h2>
      <table>
        <thead><tr><th>Test file</th><th>Tests</th><th>Fully traced</th><th>Untraced</th><th>With unresolved</th><th>Unresolved refs</th></tr></thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </section>

    <section>
      <h2>Untraced tests (missing @Req_ID)</h2>
      <details open>
        <summary>Show {len(untraced)} untraced test cases</summary>
        <ul>
          {untraced_html}
        </ul>
      </details>
    </section>

    <section>
      <h2>Unresolved tokens</h2>
      <ul>
        {unresolved_html}
      </ul>
    </section>

    <section>
      <h2>Top uncovered model tokens</h2>
      <p class=\"meta\">Showing first {max_uncovered} uncovered entries from the model token table.</p>
      <table>
        <thead><tr><th>#</th><th>Model token</th><th>Type</th></tr></thead>
        <tbody>
          {uncovered_html}
        </tbody>
      </table>
    </section>

    <div class=\"foot\">Generated via .github/skills/mts-traceability/scripts/ms_traceability.py logic.</div>
  </div>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate HTML summary report for MTS traceability"
    )
    parser.add_argument("--xml", required=True, help="Path to EA XML model file")

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--cpp", help="Single Google Test CPP file")
    source_group.add_argument("--tests-dir", help="Directory containing Google Test CPP files")

    parser.add_argument(
        "--out",
        required=True,
        help="Output HTML file path",
    )
    parser.add_argument(
        "--title",
        default="MTS Traceability Summary",
        help="Custom HTML report title",
    )
    parser.add_argument(
        "--max-uncovered",
        type=int,
        default=40,
        help="Maximum uncovered model tokens to show in table (default: 40)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    xml_path = Path(args.xml)
    out_path = Path(args.out)
    script_dir = Path(__file__).resolve().parent
    trace_script = script_dir / "ms_traceability.py"

    if not xml_path.is_file():
        raise SystemExit(f"ERROR: XML file not found: {xml_path}")
    if not trace_script.is_file():
        raise SystemExit(f"ERROR: Required script not found: {trace_script}")

    mod = load_ms_traceability_module(trace_script)
    mod._verbose = not args.quiet

    guid_table, element_types, class_map = mod.build_guid_table(xml_path)

    cpp_files: List[Path]
    source_desc: str
    if args.cpp:
        cpp_path = Path(args.cpp)
        if not cpp_path.is_file():
            raise SystemExit(f"ERROR: CPP file not found: {cpp_path}")
        cpp_files = [cpp_path]
        source_desc = str(cpp_path)
    else:
        tests_dir = Path(args.tests_dir)
        if not tests_dir.is_dir():
            raise SystemExit(f"ERROR: tests directory not found: {tests_dir}")
        cpp_files = sorted(tests_dir.glob("*.cpp"))
        if not cpp_files:
            raise SystemExit(f"ERROR: No *.cpp files found in tests directory: {tests_dir}")
        source_desc = str(tests_dir)

    rows: List[Dict] = []
    all_untraced: List[Dict] = []
    all_unresolved: List[Dict] = []
    all_covered = set()
    total_tests = 0

    for cpp_file in cpp_files:
        test_cases = mod.parse_test_file(cpp_file)
        report, unresolved_list, covered_names = mod.apply_tracing(
            test_cases, guid_table, element_types, class_map
        )

        untraced = [r for r in report if "[UNTRACED]" in r["notes"]]
        with_unresolved = [
            r for r in report if any(t.startswith("[UNRESOLVED:") for t in r["traced"])
        ]
        fully = len(report) - len(untraced) - len(with_unresolved)

        rows.append(
            {
                "file": cpp_file.name,
                "tests": len(report),
                "fully": fully,
                "untraced": len(untraced),
                "with_unresolved": len(with_unresolved),
                "unresolved_refs": len(unresolved_list),
            }
        )

        total_tests += len(report)
        all_covered.update(covered_names)

        for entry in untraced:
            all_untraced.append(
                {
                    "file": cpp_file.name,
                    "fixture": entry["fixture"],
                    "test": entry["name"],
                }
            )

        for entry in unresolved_list:
            all_unresolved.append(
                {
                    "file": cpp_file.name,
                    "test": entry["test"],
                    "token": entry["token"],
                }
            )

    uncovered = sorted(
        [
            (name, token, element_types.get(name, "?"))
            for name, token in guid_table.items()
            if name not in all_covered
        ],
        key=lambda x: x[0],
    )

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_doc = render_html(
        title=args.title,
        model_path=xml_path,
        source_desc=source_desc,
        rows=rows,
        untraced=all_untraced,
        unresolved=all_unresolved,
        uncovered=uncovered,
        total_tokens=len(guid_table),
        total_tests=total_tests,
        generated_at=generated_at,
        max_uncovered=max(1, args.max_uncovered),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"HTML report created: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
