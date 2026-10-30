#!/usr/bin/env python3
"""Extract selected function-fix rows from a PMS HTML audit report."""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path


SKIP_COMMENTS = {
    "matlab generated code, can be ignored.": "Generated MATLAB code is intentionally excluded from auto-fix selection.",
    "not used by s3p baseline.": "Rows marked as unused by the S3P baseline are excluded from auto-fix selection.",
}

AUTO_FIX_STRATEGIES = (
    ("number of return statements", "single-exit refactor"),
    ("number of goto statements", "replace goto with structured flow"),
    ("number of function parameters", "parameter-object or context bundling"),
    ("inactive\\total loc ratio", "remove inactive branches or extract variant"),
    ("comment\\total loc ratio", "add targeted documentation"),
    ("maximal level of nesting", "guard-clause and helper extraction"),
    ("cyclomatic", "branch decomposition into helpers"),
    ("number of executed statements", "extract repeated statement groups"),
    ("lines of code", "split large function into helpers"),
    ("maintainability metric", "multi-step structural simplification"),
    ("static path count", "collapse duplicated decision paths"),
    ("fanin", "architectural review required"),
    ("fanout", "dependency reduction review required"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a PMS red-metric HTML report, keep only rows selected in the last column, "
            "and emit structured fix targets for the agent."
        )
    )
    parser.add_argument("html_report", type=Path, help="Path to the saved HTML report")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. Defaults to <report>_selected_fix_targets.json",
    )
    return parser.parse_args()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def default_output_path(html_report: Path) -> Path:
    return html_report.with_name(f"{html_report.stem}_selected_fix_targets.json")


def parse_metric_lines(metric_text: str) -> list[dict[str, str]]:
    metrics: list[dict[str, str]] = []
    for raw_line in [line.strip() for line in metric_text.splitlines() if line.strip()]:
        match = re.match(r"^(?P<name>.*?):\s*(?P<value>[^()]+?)(?:\s*\((?P<threshold>.*)\))?$", raw_line)
        if match is None:
            metrics.append({"name": raw_line, "value": "", "threshold": ""})
            continue
        metrics.append(
            {
                "name": match.group("name").strip(),
                "value": match.group("value").strip(),
                "threshold": (match.group("threshold") or "").strip(),
            }
        )
    return metrics


def derive_strategies(metrics: list[dict[str, str]]) -> list[str]:
    strategies: list[str] = []
    for metric in metrics:
        metric_name = normalize(metric["name"])
        for token, strategy in AUTO_FIX_STRATEGIES:
            if token in metric_name and strategy not in strategies:
                strategies.append(strategy)
    if not strategies:
        strategies.append("manual review required")
    return strategies


def skip_reason(repo_location: str, comment: str) -> str | None:
    if normalize(repo_location) == "not found in repository":
        return "Repository match is missing, so the agent has no safe source anchor for edits."

    normalized_comment = normalize(comment)
    for marker, reason in SKIP_COMMENTS.items():
        if normalized_comment == marker:
            return reason
    return None


class AuditReportSelectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_audit_table = False
        self.table_depth = 0
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.capture_selection_json = False
        self.current_cells: list[str] = []
        self.current_cell_text: list[str] = []
        self.current_checkbox_attrs: dict[str, str | None] | None = None
        self.rows: list[dict] = []
        self.selection_state_json: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "table" and attr_map.get("id") == "audit-table":
            self.in_audit_table = True
            self.table_depth = 1
            return

        if self.in_audit_table and tag == "table":
            self.table_depth += 1

        if tag == "script" and attr_map.get("id") == "pms-audit-selected-rows":
            self.capture_selection_json = True
            return

        if not self.in_audit_table:
            return

        if tag == "tbody":
            self.in_tbody = True
            return

        if self.in_tbody and tag == "tr":
            self.in_tr = True
            self.current_cells = []
            self.current_checkbox_attrs = None
            return

        if self.in_tr and tag == "td":
            self.in_td = True
            self.current_cell_text = []
            return

        if self.in_td and tag == "br":
            self.current_cell_text.append("\n")
            return

        if self.in_tr and tag == "input" and attr_map.get("type") == "checkbox":
            self.current_checkbox_attrs = attr_map

    def handle_endtag(self, tag: str) -> None:
        if self.capture_selection_json and tag == "script":
            self.capture_selection_json = False
            return

        if not self.in_audit_table:
            return

        if tag == "td" and self.in_td:
            self.in_td = False
            cell_text = re.sub(r"\n{3,}", "\n\n", "".join(self.current_cell_text)).strip()
            self.current_cells.append(cell_text)
            self.current_cell_text = []
            return

        if tag == "tr" and self.in_tr:
            self.in_tr = False
            if self.current_cells:
                self.rows.append(
                    {
                        "cells": list(self.current_cells),
                        "checkbox": dict(self.current_checkbox_attrs or {}),
                    }
                )
            self.current_cells = []
            self.current_checkbox_attrs = None
            return

        if tag == "tbody":
            self.in_tbody = False
            return

        if tag == "table":
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.in_audit_table = False

    def handle_data(self, data: str) -> None:
        if self.capture_selection_json:
            self.selection_state_json.append(data)
            return
        if self.in_td:
            self.current_cell_text.append(data)

    def selected_row_keys(self) -> set[str]:
        joined = "".join(self.selection_state_json).strip()
        if not joined:
            return set()
        try:
            payload = json.loads(joined)
        except json.JSONDecodeError:
            return set()
        if not isinstance(payload, dict):
            return set()
        return {str(key) for key, value in payload.items() if value}


def extract_selected_findings(html_report: Path) -> list[dict]:
    parser = AuditReportSelectionParser()
    parser.feed(html_report.read_text(encoding="utf-8", errors="ignore"))
    embedded_selected_keys = parser.selected_row_keys()

    findings: list[dict] = []
    for row in parser.rows:
        cells = row["cells"]
        if len(cells) < 6:
            continue

        checkbox = row["checkbox"]
        row_key = str(checkbox.get("data-row-key") or "")
        selected = False
        if row_key and row_key in embedded_selected_keys:
            selected = True
        elif "checked" in checkbox:
            selected = True
        elif normalize(str(checkbox.get("data-selected") or "")) in {"true", "1", "yes"}:
            selected = True

        if not selected:
            continue

        metrics = parse_metric_lines(cells[3])
        reason = skip_reason(cells[4], cells[5])
        findings.append(
            {
                "row_key": row_key,
                "line_no": cells[0],
                "file_name": cells[1],
                "function_name": cells[2],
                "metrics": metrics,
                "repo_location": cells[4],
                "comment": cells[5],
                "fix_strategies": derive_strategies(metrics),
                "eligible_for_fix": reason is None,
                "skip_reason": reason,
            }
        )

    return findings


def print_summary(html_report: Path, output_path: Path, findings: list[dict]) -> None:
    selected_count = len(findings)
    eligible_count = sum(1 for item in findings if item["eligible_for_fix"])
    skipped_count = selected_count - eligible_count

    print(f"HTML report: {html_report}")
    print(f"Selected rows found: {selected_count}")
    print(f"Eligible fix targets: {eligible_count}")
    print(f"Skipped selections: {skipped_count}")
    print(f"JSON output: {output_path}")

    for item in findings:
        metric_names = ", ".join(metric["name"] for metric in item["metrics"])
        status = "eligible" if item["eligible_for_fix"] else f"skipped ({item['skip_reason']})"
        print(
            f"- {item['function_name']} [{item['file_name']}] -> {metric_names} :: {status}"
        )


def main() -> int:
    args = parse_args()
    if not args.html_report.exists():
        raise FileNotFoundError(f"HTML report not found: {args.html_report}")

    findings = extract_selected_findings(args.html_report)
    output_path = args.output or default_output_path(args.html_report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    print_summary(args.html_report, output_path, findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())