#!/usr/bin/env python3
"""
generate_trace_data.py

Generates MTS trace_data.xml files from GTF/GTest C++ test annotation comments.
The output matches the GTest_*_pf_trace_data.xml format used by the MTS toolchain.

Annotation fields extracted from CPP comment blocks:
  @Req_ID           -> <Link> elements (split by ' & ')
  @Variant          -> Variants attribute
  @FunctionSafety   -> FSM attribute (yes -> FS, no -> non-FS)
  @Security         -> SPR_sv attribute
  @TechnicalRegulation -> LTR_sv attribute
  @TestMaturity     -> Key_Maturity_sv attribute

Test identity extracted from:
  TEST_F(FixtureName, TestName)  -> TID id="FixtureName__TestName"
  TEST(SuiteName, TestName)      -> TID id="SuiteName__TestName"

Test_Result_sv is populated from the GTF test result XML when available.

Usage:
  python generate_trace_data.py \\
      --tests-dir  <path/to/gtest/tests> \\
      --module-name desctl_pf \\
      --output <path/to/GTest_desctl_pf_trace_data.xml> \\
      [--result-xml <path/to/GT_desctl_pf_test_result.xml>] \\
      [--doc-location <absolute/path/to/reports/desctl_pf>] \\
      [--revision " [abc1234]"]

Auto-detection (when optional args are omitted):
  --result-xml     : looked up at <repo_root>/.gtf/bin/metrics/reports/<module>/GT_<module>_test_result.xml
  --doc-location   : <repo_root>/.gtf/bin/metrics/reports/<module>
  --revision       : git short hash of the tests-dir repository
"""

import re
import os
import sys
import shutil
import argparse
import subprocess
from pathlib import Path

# Default upload destination (UNC share)
DEFAULT_UPLOAD_DIR = r"\\automotive-wan.com\smt\did36169\20_Disciplines\40_SW\80_SW_Tool\MDD_TVII\03_XML_From_GTest"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def get_git_revision(search_path):
    """Return ' [<short-hash>]' of the HEAD commit containing search_path, or ''."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(search_path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return f" [{result.stdout.strip()}]"
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Repository root detection
# ---------------------------------------------------------------------------

def find_repo_root(start_path):
    """
    Walk up from start_path to find the root that contains the .gtf directory.
    Specifically looks for .gtf/bin/metrics/reports (the GTF metrics tree) to
    avoid confusing nested git sub-modules with the top-level project root.
    Falls back to the outermost ancestor that has a plain .gtf folder.
    """
    p = Path(start_path).resolve()
    best_gtf_root = None
    q = p
    while True:
        # Prefer the root that owns the GTF metrics tree (most specific match)
        if (q / ".gtf" / "bin" / "metrics" / "reports").exists():
            return q
        if (q / ".gtf").exists():
            best_gtf_root = q   # record but keep walking up
        parent = q.parent
        if parent == q:
            break
        q = parent
    if best_gtf_root is not None:
        return best_gtf_root
    # Last resort: walk up and find the outermost .git
    q = p
    last_git = p
    while True:
        if (q / ".git").exists():
            last_git = q
        parent = q.parent
        if parent == q:
            break
        q = parent
    return last_git


# ---------------------------------------------------------------------------
# CPP comment-block parser
# ---------------------------------------------------------------------------

def _parse_comment_fields(block_text):
    """
    Parse a Doxygen-style /** ... */ comment block and return a dict of fields.
    Handles multi-line field values (the continuation lines start with '* ').
    """
    # Strip leading '* ' / ' * ' from each line
    lines = re.sub(r"^\s*\*[ \t]?", "", block_text, flags=re.MULTILINE).splitlines()

    fields = {}
    current_key = None
    current_val_lines = []

    for line in lines:
        m = re.match(r"@(\w+):\s*(.*)", line)
        if m:
            # Save the previous field
            if current_key is not None:
                fields[current_key] = "\n".join(current_val_lines).strip()
            current_key = m.group(1)
            current_val_lines = [m.group(2)]
        elif current_key is not None:
            current_val_lines.append(line)

    if current_key is not None:
        fields[current_key] = "\n".join(current_val_lines).strip()

    return fields


def parse_test_file(filepath):
    """
    Parse a single CPP test file and return a list of test-entry dicts.

    Each entry contains:
        tid_id, req_ids, variant, fsm, security, ltr, maturity
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError as e:
        print(f"Warning: cannot read {filepath}: {e}", file=sys.stderr)
        return []

    # Match /** ... */ blocks immediately followed by TEST_F, TEST_P, or TEST(...)
    combo = re.compile(
        r"/\*\*(.*?)\*/"          # Doxygen block
        r"\s*"
        r"TEST(_F|_P)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)",   # TEST, TEST_F or TEST_P
        re.DOTALL,
    )

    entries = []
    for m in combo.finditer(content):
        block_text = m.group(1)
        fixture_or_suite = m.group(3)
        test_name = m.group(4)

        fields = _parse_comment_fields(block_text)

        # Skip group comment blocks (they contain @GroupName / @Order but no @Req_ID)
        if "Req_ID" not in fields:
            continue

        # --- FSM mapping ---
        fs_raw = fields.get("FunctionSafety", "no").strip().lower()
        fsm = "FS" if fs_raw == "yes" else "non-FS"

        # --- TestMaturity capitalisation ---
        maturity_raw = fields.get("TestMaturity", "Draft").strip()
        maturity = (maturity_raw[0].upper() + maturity_raw[1:]) if maturity_raw else "Draft"

        # --- Req_ID: split by ' & ', collapse internal whitespace ---
        req_id_raw = re.sub(r"\s+", " ", fields.get("Req_ID", "")).strip()
        req_ids = [t.strip() for t in re.split(r"\s*&\s*", req_id_raw) if t.strip()]

        # --- Variant: use first line only (strip <br> annotations etc.) ---
        variant_raw = fields.get("Variant", "").strip()
        # Take only the first non-empty line and strip HTML tags
        variant_first_line = re.split(r"[\r\n]", variant_raw)[0].strip()
        variant = re.sub(r"<[^>]+>", "", variant_first_line).strip()

        entries.append(
            {
                "tid_id": f"{fixture_or_suite}__{test_name}",
                "fixture": fixture_or_suite,
                "name": test_name,
                "req_ids": req_ids,
                "variant": variant,
                "fsm": fsm,
                "security": fields.get("Security", "non-SPR").strip(),
                "ltr": fields.get("TechnicalRegulation", "non-LTR").strip(),
                "maturity": maturity,
            }
        )

    return entries


# ---------------------------------------------------------------------------
# Test-result XML parser
# ---------------------------------------------------------------------------

def parse_test_results(result_xml_path):
    """
    Parse a GTF/GTest result XML (JUnit format) and return:
        dict  tid_id -> "passed" | "failed" | ""
    Tests not present in the result file (compiled-out) map to "" when looked up.
    """
    results = {}
    if not result_xml_path:
        return results

    path = Path(result_xml_path)
    if not path.exists():
        print(f"Info: test result file not found: {path}", file=sys.stderr)
        return results

    try:
        import xml.etree.ElementTree as ET

        tree = ET.parse(str(path))
        root = tree.getroot()

        for testsuite in root.iter("testsuite"):
            suite_name = testsuite.get("name", "")
            for testcase in testsuite.iter("testcase"):
                classname = testcase.get("classname", suite_name)
                name = testcase.get("name", "")
                status = testcase.get("status", "")
                tid_id = f"{classname}__{name}"

                has_failure = testcase.find("failure") is not None
                if has_failure:
                    results[tid_id] = "failed"
                elif status == "run":
                    results[tid_id] = "passed"
                else:
                    results[tid_id] = ""

        # Build a secondary lookup for parameterized tests.
        #
        # INSTANTIATE_TEST_SUITE_P causes two transformations in the result XML:
        #   1. classname  = "InstantiationName/FixtureName"
        #   2. name       = "TestName/instance_index"
        #
        # The CPP TID is just "FixtureName__TestName" so we must strip both
        # the instantiation prefix from classname and the index suffix from name.
        param_results: dict = {}
        for tid_id, result in results.items():
            classname_part, _, name_part = tid_id.partition("__")
            # Strip instantiation prefix: "Prefix/Fixture" → "Fixture"
            if "/" in classname_part:
                classname_part = classname_part.split("/", 1)[1]
            # Strip instance index suffix: "TestName/0" → "TestName"
            name_part_clean = re.sub(r"/\d+$", "", name_part)
            base_tid = f"{classname_part}__{name_part_clean}"
            # Only update if this key was changed and "passed" wins over ""
            if base_tid != tid_id:
                if result == "passed" or base_tid not in param_results:
                    param_results[base_tid] = result
        results.update(param_results)

    except Exception as exc:
        print(f"Warning: could not parse test results from {path}: {exc}", file=sys.stderr)

    return results


# ---------------------------------------------------------------------------
# XML builder
# ---------------------------------------------------------------------------

def _xml_escape(text):
    """Escape XML special characters in element text content."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text


def _xml_attr(value):
    """Escape a value for use in an XML attribute (double-quoted)."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def build_xml(module_name, entries, test_results, doc_location, revision):
    """
    Produce the trace-data XML string matching the GT_*_trace_data.xml format.
    """
    filename = f"GT_{module_name}_test_spec.html"
    doc_loc_escaped = _xml_attr(doc_location)
    rev_escaped = _xml_attr(revision)

    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        (
            f'<FILE filename="{filename}" revision="{rev_escaped}"'
            f' xmlschema="MTS_XML_DEF" documentType="Module Test"'
            f' DocumentLocation="{doc_loc_escaped}">'
        ),
    ]

    for entry in entries:
        tid_id = _xml_attr(entry["tid_id"])
        fsm = _xml_attr(entry["fsm"])
        variant_attr = _xml_attr(entry["variant"])
        security = _xml_attr(entry["security"])
        ltr = _xml_attr(entry["ltr"])
        maturity = _xml_attr(entry["maturity"])
        req_ids = entry["req_ids"]

        test_result = test_results.get(entry["tid_id"], "")

        lines.append(
            f'  <TID id="{tid_id}" FSM="{fsm}" NFT="No"'
            f' Req_Type_sv="Functional Requirement"'
            f' Test_Result_sv="{test_result}"'
            f' SPR_sv="{security}" LTR_sv="{ltr}"'
            f' Key_Maturity_sv="{maturity}" Variants="{variant_attr}"'
            f' Req_Satisfier_sv="" Test_Discipline_sv="">'
        )
        lines.append("    <C>")

        for req_id in req_ids:
            link_text = _xml_escape(req_id)
            lines.append(
                f'      <Link reqDocType="Module Specification" linkType="Functional"'
                f' fulfillment="Yes" reasonForDeviation="" Variants="{variant_attr}"'
                f' comment="">{link_text}</Link>'
            )

        lines.append("    </C>")
        lines.append("  </TID>")

    lines.append("</FILE>")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate MTS trace_data.xml from GTF/GTest C++ test annotation comments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--tests-dir",
        required=True,
        help="Path to the gtest/tests folder containing the CPP test files.",
    )
    parser.add_argument(
        "--module-name",
        required=True,
        help='Full module name used in GTF reports, e.g. "desctl_pf" or "warpalgo_pf".',
    )
    parser.add_argument(
        "--output",
        required=False,
        default=None,
        help="Output XML file path. Defaults to GTest_<module-name>_trace_data.xml in the current directory.",
    )
    parser.add_argument(
        "--result-xml",
        default=None,
        help=(
            "Path to the GTF test result XML (JUnit format). "
            "Auto-detected under <repo>/.gtf/bin/metrics/reports/<module>/ if not set."
        ),
    )
    parser.add_argument(
        "--doc-location",
        default=None,
        help=(
            "Absolute path written into DocumentLocation attribute. "
            "Defaults to <repo>/.gtf/bin/metrics/reports/<module>."
        ),
    )
    parser.add_argument(
        "--revision",
        default=None,
        help=(
            'Revision string e.g. " [abc1234]". '
            "Auto-detected from git HEAD if not set."
        ),
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        default=False,
        help=(
            f"Copy the generated XML to the MTS network share: {DEFAULT_UPLOAD_DIR}. "
            "Use --upload-dir to override the destination."
        ),
    )
    parser.add_argument(
        "--upload-dir",
        default=None,
        help=(
            "Override the upload destination directory "
            f"(default: {DEFAULT_UPLOAD_DIR})."
        ),
    )

    args = parser.parse_args()

    tests_dir = Path(args.tests_dir).resolve()
    if not tests_dir.exists():
        print(f"Error: tests directory not found: {tests_dir}", file=sys.stderr)
        sys.exit(1)

    repo_root = find_repo_root(tests_dir)
    module_name = args.module_name

    # --- Revision ---
    revision = args.revision if args.revision is not None else get_git_revision(tests_dir)

    # --- DocumentLocation ---
    if args.doc_location:
        doc_location = args.doc_location
    else:
        doc_location = str(repo_root / ".gtf" / "bin" / "metrics" / "reports" / module_name)

    # --- Auto-detect result XML ---
    result_xml = args.result_xml
    if result_xml is None:
        candidate = (
            repo_root / ".gtf" / "bin" / "metrics" / "reports"
            / module_name / f"GT_{module_name}_test_result.xml"
        )
        if candidate.exists():
            result_xml = str(candidate)
            print(f"Auto-detected result XML: {result_xml}")

    # --- Collect CPP files ---
    cpp_files = sorted(tests_dir.glob("*.cpp"))
    if not cpp_files:
        print(f"Warning: no CPP files found in {tests_dir}", file=sys.stderr)

    # --- Parse tests ---
    all_entries = []
    for cpp_file in cpp_files:
        entries = parse_test_file(cpp_file)
        print(f"  {cpp_file.name}: {len(entries)} test(s)")
        all_entries.extend(entries)

    print(f"Total: {len(all_entries)} test(s) from {len(cpp_files)} file(s).")

    # --- Parse test results ---
    test_results = parse_test_results(result_xml)
    if test_results:
        passed = sum(1 for v in test_results.values() if v == "passed")
        failed = sum(1 for v in test_results.values() if v == "failed")
        print(f"Test results: {passed} passed, {failed} failed, "
              f"{len(test_results) - passed - failed} other.")

    # --- Build and write XML ---
    xml_content = build_xml(module_name, all_entries, test_results, doc_location, revision)

    output_path = Path(args.output).resolve() if args.output else Path.cwd() / f"GTest_{module_name}_trace_data.xml"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(xml_content)

    print(f"Generated: {output_path}")

    # --- Optional upload ---
    if args.upload:
        upload_dir = Path(args.upload_dir) if args.upload_dir else Path(DEFAULT_UPLOAD_DIR)
        _upload_file(output_path, upload_dir)


def _upload_file(source: Path, dest_dir: Path) -> None:
    """Copy *source* to *dest_dir*, creating the directory if necessary."""
    if not dest_dir.exists():
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(
                f"Error: upload destination does not exist and could not be created: "
                f"{dest_dir}\n  {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

    dest_file = dest_dir / source.name
    try:
        shutil.copy2(str(source), str(dest_file))
        print(f"Uploaded: {dest_file}")
    except OSError as exc:
        print(
            f"Error: could not copy {source.name} to {dest_dir}\n  {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
