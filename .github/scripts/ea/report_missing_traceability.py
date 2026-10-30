"""
Tool: report_missing_traceability.py

Generates a missing-traceability report from the JSON files produced by
export_arch_design.py.  Supports five scope modes:

  platform                        All packages under the Platform model branch
                                  (default when no argument is given)
  project                         All packages under the Project model branch
  platform:<PackageName>          A single named package under Platform
  project:<PackageName>           A single named package under Project
  all                             Every package regardless of model branch

Output (saved to ai_output/reports/ by default)
--------------------------------------------
  <scope>_missing_traceability.json   — Detailed JSON report
  <scope>_missing_traceability.md     — Markdown summary + detail table

Usage
-----
    # Platform scope (default)
    .venv32\\Scripts\\python.exe scripts/report_missing_traceability.py

    # Project scope
    .venv32\\Scripts\\python.exe scripts/report_missing_traceability.py project

    # All packages
    .venv32\\Scripts\\python.exe scripts/report_missing_traceability.py all

    # Single subsystem under Platform
    .venv32\\Scripts\\python.exe scripts/report_missing_traceability.py platform:SwSubSys_AmbientSense

    # Single subsystem under Project
    .venv32\\Scripts\\python.exe scripts/report_missing_traceability.py project:SwSubSys_TouchCtl

    # Re-export from EA before reporting (requires 32-bit Python + pywin32)
    .venv32\\Scripts\\python.exe scripts/report_missing_traceability.py platform --refresh

    # Full audit (include elements WITH traceability)
    .venv32\\Scripts\\python.exe scripts/report_missing_traceability.py all --all-elements

Arguments
---------
scope                   Scope selector (see above). Default: platform.
-i / --input-dir DIR    Folder containing *_arch_design.json files.
                        Default: ai_output/arch_design/
-o / --output-dir DIR   Folder for the JSON/MD report files.
                        Default: ai_output/reports/
--refresh               Re-export arch_design JSON files before reporting.
--all-elements          Include ALL elements (not only missing). Full audit table.
--include-structural    Include structural element types (ProxyConnector,
                        UMLDiagram, Synchronization, UseCase, etc.) which
                        are excluded by default.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from glob import glob

_TOOL_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_TOOL_DIR)))

_DEFAULT_INPUT_DIR  = os.path.join(_PROJECT_ROOT, "ai_output", "arch_design")
_DEFAULT_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "ai_output", "reports")

# Element types that are structural artifacts and do NOT require traceability links.
_STRUCTURAL_TYPES = {
    "ProxyConnector",
    "UMLDiagram",
    "Synchronization",
    "UseCase",       # Dyn_SwSubSys_* wrapper elements
    "SwSubsystem",   # top-level subsystem wrapper
    "Document",
    "pkg",
    "Package",
    "Boundary",
    "Note",
    "Text",
}


# ---------------------------------------------------------------------------
# Scope parsing
# ---------------------------------------------------------------------------

def _parse_scope(raw: str) -> tuple[str, str | None, str | None]:
    """
    Return (scope_label, branch_filter, package_filter).

    branch_filter : 'Platform' | 'Project' | None
    package_filter: exact package name | None
    """
    raw = raw.strip()
    low = raw.lower()

    if low == "all":
        return "all", None, None
    if low == "platform":
        return "platform", "Platform", None
    if low == "project":
        return "project", "Project", None

    for prefix in ("platform:", "project:"):
        if low.startswith(prefix):
            branch   = prefix.rstrip(":").capitalize()
            pkg_name = raw[len(prefix):]
            label    = f"{prefix.rstrip(':')}_{pkg_name.replace(' ', '_')}"
            return label, branch, pkg_name

    # Bare package name → default to platform scope
    return f"platform_{raw.replace(' ', '_')}", "Platform", raw


def _doc_matches(doc: dict, branch_filter: str | None, package_filter: str | None) -> bool:
    ea_path  = doc.get("eaPath", "")
    pkg_name = doc.get("packageName", "")
    if branch_filter:
        if f".{branch_filter}." not in ea_path and not ea_path.startswith(branch_filter + "."):
            return False
    if package_filter and pkg_name != package_filter:
        return False
    return True


# ---------------------------------------------------------------------------
# Load and filter JSON files
# ---------------------------------------------------------------------------

def load_all_docs(input_dir: str) -> list[dict]:
    """Load all *_arch_design.json files from branch subdirs and flat dir."""
    docs: list[dict] = []
    seen_ids: set[str] = set()  # de-duplicate by (packageName, eaPath)

    # Search order: branch subdirs first, then flat dir for backward compat
    search_dirs = [
        os.path.join(input_dir, "platform"),
        os.path.join(input_dir, "project"),
        input_dir,  # legacy flat files
    ]
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for fpath in sorted(glob(os.path.join(search_dir, "*_arch_design.json"))):
            try:
                with open(fpath, encoding="utf-8") as fh:
                    doc = json.load(fh)
                # Skip flat-dir files that are now superseded by a subdir version
                key = (doc.get("packageName", ""), doc.get("eaPath", ""))
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                docs.append(doc)
            except Exception as exc:
                print(f"WARNING: Could not read '{fpath}': {exc}", file=sys.stderr)

    if not docs:
        print(f"ERROR: No *_arch_design.json files in '{input_dir}' or its subdirs.", file=sys.stderr)
        print("       Run export_arch_design.py first, or use --refresh.", file=sys.stderr)
        sys.exit(1)
    return docs


def filter_docs(
    docs: list[dict],
    branch_filter: str | None,
    package_filter: str | None,
) -> list[dict]:
    if branch_filter is None and package_filter is None:
        return docs
    return [d for d in docs if _doc_matches(d, branch_filter, package_filter)]


# ---------------------------------------------------------------------------
# Collect element rows
# ---------------------------------------------------------------------------

def collect_rows(
    docs: list[dict],
    all_elements: bool = False,
    include_structural: bool = False,
) -> list[dict]:
    rows: list[dict] = []
    for doc in docs:
        pkg_name = doc.get("packageName", "")
        ea_path  = doc.get("eaPath", "")
        level    = doc.get("level", "")
        for el in doc.get("elements", []):
            ea_req_type = el.get("eaReqType", "")
            if not include_structural and ea_req_type in _STRUCTURAL_TYPES:
                continue
            traced_to = el.get("tracedTo", [])
            if all_elements or not traced_to:
                rows.append({
                    "packageName":       pkg_name,
                    "eaPath":            ea_path,
                    "level":             level,
                    "elementName":       el.get("name", ""),
                    "elementId":         el.get("id", ""),
                    "eaReqType":         ea_req_type,
                    "status":            el.get("status", ""),
                    "safetyLevel":       el.get("safetyLevel", ""),
                    "securityOrPrivacy": el.get("securityOrPrivacy", ""),
                    "tsh":               el.get("tsh", ""),
                    "reqType":           el.get("reqType", ""),
                    "variants":          el.get("variants", ""),
                    "ltr":               el.get("ltr", ""),
                    "traceabilityCount": len(traced_to),
                })
    return rows


# ---------------------------------------------------------------------------
# Per-package statistics
# ---------------------------------------------------------------------------

def build_stats(docs: list[dict], include_structural: bool) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for doc in docs:
        pname   = doc.get("packageName", "")
        ea_path = doc.get("eaPath", "")
        level   = doc.get("level", "")
        total   = 0
        missing = 0
        for el in doc.get("elements", []):
            if not include_structural and el.get("eaReqType", "") in _STRUCTURAL_TYPES:
                continue
            total += 1
            if not el.get("tracedTo"):
                missing += 1
        stats[pname] = {
            "total":   total,
            "missing": missing,
            "eaPath":  ea_path,
            "level":   level,
        }
    return dict(sorted(stats.items()))


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def write_json(
    rows: list[dict],
    stats: dict[str, dict],
    scope_label: str,
    all_elements: bool,
    out_path: str,
) -> None:
    total_el   = sum(s["total"]   for s in stats.values())
    total_miss = sum(s["missing"] for s in stats.values())
    pct        = round((1 - total_miss / total_el) * 100, 2) if total_el else 0.0

    report = {
        "reportType":     "FullTraceabilityAudit" if all_elements else "MissingTraceability",
        "scope":          scope_label,
        "generatedDate":  date.today().isoformat(),
        "totalElements":  total_el,
        "missingCount":   total_miss,
        "coveragePct":    pct,
        "packageSummary": [
            {
                "packageName": pname,
                "eaPath":      s["eaPath"],
                "level":       s["level"],
                "total":       s["total"],
                "missing":     s["missing"],
                "coveragePct": round((1 - s["missing"] / s["total"]) * 100, 2) if s["total"] else 0.0,
            }
            for pname, s in stats.items()
        ],
        "elements": rows,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"JSON report  -> {out_path}")


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _status_badge(pct: float, missing: int) -> str:
    if missing == 0:
        return "✅"
    if pct >= 90.0:
        return "⚠️"
    return "❌"


def write_md(
    rows: list[dict],
    stats: dict[str, dict],
    scope_label: str,
    all_elements: bool,
    out_path: str,
) -> None:
    total_el   = sum(s["total"]   for s in stats.values())
    total_miss = sum(s["missing"] for s in stats.values())
    pct_cov    = (1 - total_miss / total_el) * 100 if total_el else 0.0
    today      = date.today().isoformat()
    title      = "Full Traceability Audit" if all_elements else "Missing Traceability Report"
    scope_disp = scope_label.replace("_", " ").title()

    L: list[str] = []

    # ── Header ──────────────────────────────────────────────────────────────
    L.append(f"# {title} — {scope_disp}")
    L.append("")
    L.append("| Field | Value |")
    L.append("|-------|-------|")
    L.append(f"| Generated | {today} |")
    L.append(f"| Scope | `{scope_label}` |")
    L.append(f"| Total design elements | {total_el} |")
    if not all_elements:
        L.append(f"| Missing traceability | {total_miss} ({100 - pct_cov:.1f}%) |")
        L.append(f"| Overall coverage | {pct_cov:.1f}% |")
    L.append("")

    # ── Summary table ────────────────────────────────────────────────────────
    L.append("## Summary by Package")
    L.append("")
    L.append("| Package | Missing | Total | Coverage | Status |")
    L.append("|---------|--------:|------:|---------:|:------:|")
    for pname, s in stats.items():
        t     = s["total"]
        m     = s["missing"]
        pct   = (1 - m / t) * 100 if t else 0.0
        badge = _status_badge(pct, m)
        L.append(f"| `{pname}` | {m} | {t} | {pct:.1f}% | {badge} |")
    L.append("")

    # ── Detail: elements without links ───────────────────────────────────────
    if not all_elements:
        missing_rows = [r for r in rows if r["traceabilityCount"] == 0]
        if missing_rows:
            L.append("## Elements Without Traceability Links")
            L.append("")

            by_pkg: dict[str, list[dict]] = {}
            for row in missing_rows:
                by_pkg.setdefault(row["packageName"], []).append(row)

            for pname in sorted(by_pkg):
                L.append(f"### {pname}")
                L.append("")
                L.append("| Element | Type | Status | Safety Level | Sec/Privacy |")
                L.append("|---------|------|--------|:------------:|:-----------:|")
                for r in by_pkg[pname]:
                    L.append(
                        f"| `{r['elementName']}` | {r['eaReqType']} "
                        f"| {r['status'] or '—'} "
                        f"| {r['safetyLevel'] or '—'} "
                        f"| {r['securityOrPrivacy'] or '—'} |"
                    )
                L.append("")
        else:
            L.append("## Elements Without Traceability Links")
            L.append("")
            L.append("_No elements with missing traceability found in this scope._")
            L.append("")

    # ── Full audit detail ────────────────────────────────────────────────────
    else:
        L.append("## All Design Elements")
        L.append("")
        by_pkg_all: dict[str, list[dict]] = {}
        for row in rows:
            by_pkg_all.setdefault(row["packageName"], []).append(row)

        for pname in sorted(by_pkg_all):
            L.append(f"### {pname}")
            L.append("")
            L.append("| Element | Type | TracedTo | Status | Safety Level |")
            L.append("|---------|------|:--------:|--------|:------------:|")
            for r in by_pkg_all[pname]:
                cnt     = r["traceabilityCount"]
                cnt_str = str(cnt) if cnt > 0 else "**0** ❌"
                L.append(
                    f"| `{r['elementName']}` | {r['eaReqType']} "
                    f"| {cnt_str} "
                    f"| {r['status'] or '—'} "
                    f"| {r['safetyLevel'] or '—'} |"
                )
            L.append("")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
        fh.write("\n")
    print(f"Markdown     -> {out_path}")


# ---------------------------------------------------------------------------
# Optional refresh (re-export from EA)
# ---------------------------------------------------------------------------

def run_export(branch_filter: str | None, package_filter: str | None, input_dir: str) -> None:
    """Invoke export_arch_design.py to refresh the JSON source files."""
    script = os.path.join(_TOOL_DIR, "export_arch_design.py")
    python = sys.executable

    # Always pass the parent arch_design dir; the export tool creates branch subdirs
    cmd = [python, script, "--level", "subsystem", "--recurse",
           "--output-dir", input_dir]

    if package_filter:
        # For a specific package, use --scope instead of positional + --filter
        # to avoid the "multiple packages found" error from same-named packages
        # in both branches. Pass scope as the branch name.
        if branch_filter:
            cmd += ["--scope", branch_filter]
        # We still need the specific package — use positional arg with explicit filter
        # But since --scope already restricts the search, we must also pass the name.
        # Reset and use positional + scope-based filter via path_filter argument.
        cmd = [python, script, "--level", "subsystem", "--recurse",
               "--output-dir", input_dir,
               package_filter]
        if branch_filter:
            # Use a more specific path segment to disambiguate (e.g. Project.SwMod)
            cmd += ["--filter", f"{branch_filter}.SwMod"]
    elif branch_filter:
        cmd += ["--scope", branch_filter]

    print(f"Re-exporting: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("WARNING: export_arch_design.py returned non-zero exit code.", file=sys.stderr)
    print()


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def print_summary(stats: dict[str, dict], scope_label: str, all_elements: bool) -> None:
    total_el   = sum(s["total"]   for s in stats.values())
    total_miss = sum(s["missing"] for s in stats.values())
    pct_cov    = (1 - total_miss / total_el) * 100 if total_el else 0.0
    title      = "Full Audit" if all_elements else "Missing Traceability"

    print(
        f"=== {title} — {scope_label}  "
        f"({total_miss}/{total_el} missing, {pct_cov:.1f}% coverage) ==="
    )
    print()

    pkg_w = max((len(p) for p in stats), default=20) + 2
    print(f"  {'Package':<{pkg_w}}  {'Missing':>8}  {'Total':>8}  {'Coverage':>10}")
    print(f"  {'-'*pkg_w}  {'-'*8}  {'-'*8}  {'-'*10}")
    for pname, s in stats.items():
        pct  = (1 - s["missing"] / s["total"]) * 100 if s["total"] else 0.0
        flag = " !" if s["missing"] > 0 else ""
        print(
            f"  {pname:<{pkg_w}}  {s['missing']:>8}  {s['total']:>8}"
            f"  {pct:>9.1f}%{flag}"
        )
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="report_missing_traceability",
        description=(
            "Generate missing-traceability reports from arch_design JSON files.\n\n"
            "Scope modes:\n"
            "  platform                  All Platform packages (default)\n"
            "  project                   All Project packages\n"
            "  all                       All packages\n"
            "  platform:<PackageName>    Single package under Platform\n"
            "  project:<PackageName>     Single package under Project\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "scope",
        nargs="?",
        default="platform",
        metavar="SCOPE",
        help="Scope selector (default: platform). See description above.",
    )
    parser.add_argument(
        "-i", "--input-dir",
        dest="input_dir",
        default=_DEFAULT_INPUT_DIR,
        metavar="DIR",
        help=f"Folder with *_arch_design.json files (default: {_DEFAULT_INPUT_DIR}).",
    )
    parser.add_argument(
        "-o", "--output-dir",
        dest="output_dir",
        default=_DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Output folder for reports (default: {_DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-export arch_design JSON files from EA before generating the report.",
    )
    parser.add_argument(
        "--all-elements",
        dest="all_elements",
        action="store_true",
        help="Include ALL elements (not only missing). Generates a full audit table.",
    )
    parser.add_argument(
        "--include-structural",
        dest="include_structural",
        action="store_true",
        help=(
            "Include structural element types (ProxyConnector, UMLDiagram, "
            "UseCase, SwSubsystem, etc.) which are excluded by default."
        ),
    )

    args = parser.parse_args(argv)

    scope_label, branch_filter, package_filter = _parse_scope(args.scope)
    os.makedirs(args.output_dir, exist_ok=True)

    # ── Optional re-export ───────────────────────────────────────────────────
    if args.refresh:
        run_export(branch_filter, package_filter, args.input_dir)

    # ── Load and filter ──────────────────────────────────────────────────────
    print(f"Loading arch_design files from: {args.input_dir}")
    all_docs = load_all_docs(args.input_dir)
    print(f"Loaded {len(all_docs)} file(s) total.")

    docs = filter_docs(all_docs, branch_filter, package_filter)
    if not docs:
        print(
            f"\nERROR: No packages matched scope '{args.scope}'.\n"
            f"  branch_filter  = {branch_filter!r}\n"
            f"  package_filter = {package_filter!r}\n"
            f"\nTip: run with --refresh to re-export from EA first.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Scope '{scope_label}': {len(docs)} package(s) matched.")
    print()

    # ── Compute ──────────────────────────────────────────────────────────────
    rows  = collect_rows(docs, args.all_elements, args.include_structural)
    stats = build_stats(docs, args.include_structural)

    print_summary(stats, scope_label, args.all_elements)

    # ── Write outputs ────────────────────────────────────────────────────────
    safe      = scope_label.replace(":", "_")
    json_path = os.path.join(args.output_dir, f"{safe}_missing_traceability.json")
    md_path   = os.path.join(args.output_dir, f"{safe}_missing_traceability.md")

    write_json(rows, stats, scope_label, args.all_elements, json_path)
    write_md(rows, stats, scope_label, args.all_elements, md_path)
    print()
    print("Done.")


if __name__ == "__main__":
    main(sys.argv[1:])

