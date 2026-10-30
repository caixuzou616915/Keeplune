#!/usr/bin/env python3
"""
Klocwork Excel Report Helper
==============================
Backing utility for the Klocwork Agent (.github/agents/klocwork_agent.agent.md).

Reads a Klocwork issues .xlsx export, summarizes warnings per file, lists the
warnings for one file (with their absolute row number in the source sheet),
and writes AI triage results (verdict/comment/proposal) into a dedicated
"AI_Analysis" sheet in the SAME workbook, without ever modifying the original
data sheet.

Commands:
---------
1. Summary - counts of warnings per file, column names:
   $ python kw_report_tool.py summary <xlsx> [--sheet NAME] [--header-row N]

2. List all warnings for one file (substring match on the detected file column):
   $ python kw_report_tool.py list <xlsx> --file <substring> [--sheet NAME] [--header-row N]

3. Write/upsert AI analysis rows (keyed by source row number, idempotent):
   $ python kw_report_tool.py write <xlsx> --input <analysis.json> [--sheet NAME] [--analysis-sheet AI_Analysis]

   <analysis.json> is a list of objects:
   [
     {"row": 42, "verdict": "Critical", "comment": "...", "proposal": "...", "fix_applied": "Yes"},
     ...
   ]
   "row" MUST be the "_row" value reported by the `list` command for that warning.

   Proposal field convention: when a "Not Critical" verdict is because the
   warning is already covered by an existing inline deviation comment in the
   source (e.g. "[KW_IGNORE][...]..." or an equivalent justification comment
   right above/near the flagged line), "proposal" should quote/paraphrase
   that EXACT existing comment text, not a generic "No change needed;
   existing inline justification is sufficient." placeholder. Verify the
   comment still accurately describes the code before reusing it - if it is
   stale, wrong, or no longer matches the current source, correct the
   proposal text (and, if warranted, correct the comment in the source file
   itself) rather than copying it verbatim.
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from openpyxl import load_workbook


def load_rows(xlsx_path, sheet_name, header_row):
    wb = load_workbook(xlsx_path, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb[wb.sheetnames[0]]
    headers = [str(c.value).strip() if c.value is not None else "" for c in ws[header_row]]
    rows = []
    for r in range(header_row + 1, ws.max_row + 1):
        values = [c.value for c in ws[r]]
        if all(v is None for v in values):
            continue
        row_dict = {headers[i] if i < len(headers) else f"col{i}": values[i] for i in range(len(values))}
        row_dict["_row"] = r
        rows.append(row_dict)
    return wb, ws, headers, rows


def find_file_column(headers):
    for h in headers:
        if h and "file" in h.lower():
            return h
    return headers[0] if headers else None


def cmd_summary(args):
    wb, ws, headers, rows = load_rows(args.xlsx, args.sheet, args.header_row)
    file_col = find_file_column(headers)
    print(f"Sheet: {ws.title}")
    print(f"Columns: {headers}")
    print(f"Total warnings: {len(rows)}")
    if not file_col:
        print("Could not detect a 'file' column.")
        return
    counts = {}
    for r in rows:
        f = r.get(file_col) or "(unknown)"
        counts[f] = counts.get(f, 0) + 1
    print(f"\nGrouped by column '{file_col}' ({len(counts)} files):")
    for f, c in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {c:4d}  {f}")


def cmd_list(args):
    wb, ws, headers, rows = load_rows(args.xlsx, args.sheet, args.header_row)
    file_col = find_file_column(headers)
    matches = [r for r in rows if file_col and args.file.lower() in str(r.get(file_col, "")).lower()]
    print(f"Found {len(matches)} warning(s) matching file filter '{args.file}' in column '{file_col}'\n")
    for r in matches:
        print(f"--- Row {r['_row']} ---")
        for h in headers:
            print(f"  {h}: {r.get(h)}")
        print()


def cmd_write(args):
    with open(args.input, "r", encoding="utf-8") as f:
        analysis_entries = json.load(f)

    wb, ws, headers, rows = load_rows(args.xlsx, args.sheet, args.header_row)
    rows_by_num = {r["_row"]: r for r in rows}

    extra_cols = ["Verdict", "Comment", "Proposal", "FixApplied"]
    out_headers_full = headers + extra_cols + ["_SourceRow"]

    if args.analysis_sheet in wb.sheetnames:
        awb_ws = wb[args.analysis_sheet]
        existing_headers = [c.value for c in awb_ws[1]] if awb_ws.max_row >= 1 else []
        if existing_headers != out_headers_full:
            # Source columns changed since last run - start the analysis sheet over.
            del wb[args.analysis_sheet]
            awb_ws = wb.create_sheet(args.analysis_sheet)
    else:
        awb_ws = wb.create_sheet(args.analysis_sheet)

    existing_index = {}
    if awb_ws.cell(row=1, column=1).value is None:
        for i, h in enumerate(out_headers_full, start=1):
            awb_ws.cell(row=1, column=i, value=h)
    else:
        src_col_idx = len(out_headers_full)
        for r in range(2, awb_ws.max_row + 1):
            src_val = awb_ws.cell(row=r, column=src_col_idx).value
            if src_val is not None:
                existing_index[int(src_val)] = r

    added, updated, skipped = 0, 0, 0
    for entry in analysis_entries:
        src_row_num = int(entry["row"])
        src = rows_by_num.get(src_row_num)
        if src is None:
            print(f"WARNING: source row {src_row_num} not found, skipping")
            skipped += 1
            continue

        values = [src.get(h) for h in headers] + [
            entry.get("verdict", ""),
            entry.get("comment", ""),
            entry.get("proposal", ""),
            entry.get("fix_applied", ""),
        ] + [src_row_num]

        target_row = existing_index.get(src_row_num)
        if target_row is None:
            target_row = awb_ws.max_row + 1
            existing_index[src_row_num] = target_row
            added += 1
        else:
            updated += 1
        for i, v in enumerate(values, start=1):
            awb_ws.cell(row=target_row, column=i, value=v)

    wb.save(args.xlsx)
    print(f"Analysis sheet '{args.analysis_sheet}' updated: {added} added, {updated} updated, {skipped} skipped.")
    print(f"Saved to {args.xlsx}")


def _esc_md_cell(text):
    """Make text safe to embed as one Markdown table cell: escape HTML metachars,
    escape literal '|' (as an HTML entity so it never collides with the table
    delimiter), and turn newlines into <br> so multi-line snippets stay on one
    logical table row."""
    if text is None:
        return ""
    text = str(text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("|", "&#124;")
    text = text.replace("\r\n", "\n").replace("\n", "<br>")
    return text


# A function up to this many lines is shown in full; longer functions are
# condensed to signature + elided "..." + a context window + closing brace.
SMALL_FUNCTION_MAX_LINES = 40

# If the "enclosing function" found by brace-matching is bigger than this,
# it's almost certainly not a real single function (e.g. a whole-file
# '#ifdef ISMD_GTEST class X { ... }' GTest-mocking wrapper, or the warning's
# reported line has drifted into a gap between functions) - fall back to a
# plain context-window snippet instead.
HARD_MAX_FUNCTION_LINES = 300

# How many consecutive non-code lines (blank / comment-only / preprocessor)
# _resolve_stale_line will skip past when looking for the real statement a
# warning's Line marker should point at. Generous enough to clear a stack of
# several project [KW_IGNORE] comments plus a #ifdef/#pragma CTC block, or a
# multi-line '/************' banner/doxygen comment block above a function
# (some of this project's function-header banners run to 15-20 lines).
MAX_STALE_LINE_ADVANCE = 30


def _is_noncode_line(line):
    """True for a line that can never itself be the statement a Klocwork
    warning is about: blank, a whole-line '//' comment, a self-contained
    '/* ... */' comment (this project's stacked '[KW_IGNORE][CODE]...'
    justification comments are always exactly this shape), or a preprocessor/
    pragma directive ('#ifdef', '#pragma CTC SKIP', etc.). Does NOT by itself
    detect multi-line '/* ...' block-comment openers/interiors/closers - see
    _classify_line_for_stale_resolution for that (stateful) case."""
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if stripped.startswith("//"):
        return True
    if stripped.startswith("/*") and stripped.endswith("*/"):
        return True
    return False


def _resolve_stale_line(source_lines, line_no):
    """Auto-correct the classic line-drift bug: a warning's original 'Line'
    lands on a non-code line (most commonly one of this project's stacked
    '[KW_IGNORE][MISRA.XXX]...' comments, or the opening of a multi-line
    '/**********' banner/doxygen comment block above a function) instead of
    the real flagged statement, because a later edit inserted lines above it
    in the same file (e.g. adding KW_IGNORE justification comments, or a
    Critical fix) without the row's Line being shifted to match - or because
    Klocwork itself reported the banner-comment line preceding a function
    definition rather than the definition's own line. When that happens,
    advance forward to the next real code line and use that instead - this
    project's convention always places such comments immediately above the
    statement/function they document, never after it.

    Tracks multi-line '/* ... */' block-comment state explicitly (a bare
    '_is_noncode_line' per-line check cannot tell that a '/******' opener
    line with no closing '*/' on the same line starts a block comment that
    may span many following lines before the real code resumes).

    Returns (resolved_line, was_adjusted: bool).
    """
    if not source_lines or not line_no:
        return line_no, False
    try:
        line_no = int(line_no)
    except (TypeError, ValueError):
        return line_no, False
    if line_no < 1 or line_no > len(source_lines):
        return line_no, False

    def _is_block_comment_open(stripped):
        """True if this line opens a '/* ...' block comment that is not
        closed on the same line (so subsequent lines are still inside it)."""
        if "/*" not in stripped:
            return False
        after_open = stripped[stripped.index("/*") + 2:]
        return "*/" not in after_open

    first_stripped = source_lines[line_no - 1].strip()
    if not (_is_noncode_line(source_lines[line_no - 1]) or _is_block_comment_open(first_stripped)):
        return line_no, False

    idx = line_no - 1
    steps = 0
    in_block_comment = False
    while idx < len(source_lines) and steps < MAX_STALE_LINE_ADVANCE:
        stripped = source_lines[idx].strip()
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            idx += 1
            steps += 1
            continue
        if _is_noncode_line(source_lines[idx]):
            idx += 1
            steps += 1
            continue
        if _is_block_comment_open(stripped):
            in_block_comment = True
            idx += 1
            steps += 1
            continue
        break
    if idx >= len(source_lines) or in_block_comment or _is_noncode_line(source_lines[idx]):
        # Ran off the end of the file, hit the advance cap, or is still
        # inside/at a non-code line - not safe to guess, leave line as-is.
        return line_no, False
    return idx + 1, True


def _format_snapshot_lines(source_lines, lo, hi, marked_line):
    out = []
    for ln in range(lo, hi + 1):
        marker = ">>" if ln == marked_line else "  "
        out.append(f"{marker}{ln}: {source_lines[ln - 1].rstrip()}")
    return out


def _strip_comments(source_lines):
    """Blank out // and /* */ comment content (same line count/positions) so
    brace-counting below isn't confused by braces mentioned inside comments."""
    out = []
    in_block = False
    for line in source_lines:
        result = []
        i, n = 0, len(line)
        while i < n:
            if in_block:
                end = line.find("*/", i)
                if end == -1:
                    result.append(" " * (n - i))
                    i = n
                else:
                    result.append(" " * (end + 2 - i))
                    i = end + 2
                    in_block = False
            elif line[i:i + 2] == "/*":
                end = line.find("*/", i + 2)
                if end == -1:
                    result.append(" " * (n - i))
                    i = n
                    in_block = True
                else:
                    result.append(" " * (end + 2 - i))
                    i = end + 2
            elif line[i:i + 2] == "//":
                result.append(" " * (n - i))
                i = n
            else:
                result.append(line[i])
                i += 1
        out.append("".join(result))
    return out


def _find_enclosing_function(source_lines, line_no, max_sig_lookback=12):
    """Best-effort brace-matching scan (comments stripped) to find the
    (signature_start, open_brace, close_brace) 1-based line numbers of the
    *innermost* function enclosing line_no. Returns None if line_no sits at
    file scope (e.g. a macro/typedef finding, not inside any brace block)."""
    stripped = _strip_comments(source_lines)
    n = len(stripped)
    if not (1 <= line_no <= n):
        return None

    # Stack of open-brace line numbers; top of stack = innermost enclosing
    # scope at line_no (correctly handles files that wrap every function in
    # an outer '#ifdef ISMD_GTEST class X { ... }' GTest-mocking wrapper).
    stack = []
    for i in range(line_no):
        for ch in stripped[i]:
            if ch == "{":
                stack.append(i + 1)
            elif ch == "}":
                if stack:
                    stack.pop()
    if not stack:
        return None
    open_brace = stack[-1]

    depth2 = 0
    close_brace = None
    for i in range(open_brace - 1, n):
        for ch in stripped[i]:
            if ch == "{":
                depth2 += 1
            elif ch == "}":
                depth2 -= 1
                if depth2 == 0:
                    close_brace = i + 1
                    break
        if close_brace:
            break
    if close_brace is None:
        return None
    if (close_brace - open_brace) > HARD_MAX_FUNCTION_LINES:
        # Implausibly large "function": we've actually landed on a
        # whole-file/class wrapper (e.g. a #ifdef ISMD_GTEST class X { ... }
        # GTest-mocking shell, or stale line-number drift landed in a gap
        # between functions), not a real single function body.
        return None

    sig_start = open_brace
    k = open_brace - 2
    steps = 0
    while k >= 0 and steps < max_sig_lookback:
        stripped_text = source_lines[k].strip()
        if stripped_text == "" or stripped_text.endswith("*/") or stripped_text == "}":
            break
        sig_start = k + 1
        k -= 1
        steps += 1
    return (sig_start, open_brace, close_brace)


def _code_snapshot(source_lines, line_no, context):
    if not source_lines or not line_no:
        return "N/A", line_no, False
    try:
        line_no = int(line_no)
    except (TypeError, ValueError):
        return "N/A", line_no, False
    if line_no < 1 or line_no > len(source_lines):
        return "N/A", line_no, False

    resolved_line, was_adjusted = _resolve_stale_line(source_lines, line_no)
    note = []
    if was_adjusted:
        note.append(
            f"    NOTE: original Line {line_no} is a comment/pragma (stale - likely shifted by an "
            f"earlier edit); auto-advanced to the next real statement at line {resolved_line}."
        )
    line_no = resolved_line

    func = _find_enclosing_function(source_lines, line_no)
    if func is None:
        lo = max(1, line_no - context)
        hi = min(len(source_lines), line_no + context)
        return "\n".join(note + _format_snapshot_lines(source_lines, lo, hi, line_no)), line_no, was_adjusted

    sig_start, open_brace, close_brace = func
    if (close_brace - sig_start + 1) <= SMALL_FUNCTION_MAX_LINES:
        return "\n".join(note + _format_snapshot_lines(source_lines, sig_start, close_brace, line_no)), line_no, was_adjusted

    # Function is too long to show in full: signature, elided "...", a context
    # window around the flagged line, elided "...", then the closing brace.
    out = note + list(_format_snapshot_lines(source_lines, sig_start, open_brace, line_no))
    ctx_lo = max(open_brace + 1, line_no - context)
    ctx_hi = min(close_brace - 1, line_no + context)
    if ctx_lo > open_brace + 1:
        out.append("    ...")
    if ctx_hi >= ctx_lo:
        out.extend(_format_snapshot_lines(source_lines, ctx_lo, ctx_hi, line_no))
    if ctx_hi < close_brace - 1:
        out.append("    ...")
    out.extend(_format_snapshot_lines(source_lines, close_brace, close_brace, line_no))
    return "\n".join(out), line_no, was_adjusted


def _parse_line_adjustments(shift_args, override_args):
    """Parse --line-shift START:DELTA and --line-override ORIG:NEW into a
    resolver function. Overrides win over range shifts for an exact original
    line number; otherwise all shifts whose START <= original line are
    summed (cumulative), so multiple edits to the same file compose
    correctly. This lets `report` show/snapshot the CURRENT source location
    of a still-valid warning even after a prior Critical fix inserted or
    removed lines above it in the same file."""
    shifts = []
    for s in shift_args or []:
        start_s, delta_s = s.split(":")
        shifts.append((int(start_s), int(delta_s)))
    shifts.sort(key=lambda x: x[0])
    overrides = {}
    for s in override_args or []:
        orig_s, new_s = s.split(":")
        overrides[int(orig_s)] = int(new_s)

    def resolve(orig_line):
        try:
            orig_line = int(orig_line)
        except (TypeError, ValueError):
            return orig_line
        if orig_line in overrides:
            return overrides[orig_line]
        delta = sum(d for start, d in shifts if orig_line >= start)
        return orig_line + delta

    return resolve


def cmd_report(args):
    wb = load_workbook(args.xlsx, data_only=True)
    if args.analysis_sheet not in wb.sheetnames:
        print(f"Analysis sheet '{args.analysis_sheet}' not found in {args.xlsx}. Run 'write' first.")
        return
    ws = wb[args.analysis_sheet]
    headers = [c.value for c in ws[1]]
    file_col = next((h for h in headers if h and "file" in str(h).lower()), None)
    # Source 'Warnings' sheet columns are titlecased as written by kw_export.py
    # (e.g. "Id", not "ID") - match case-insensitively so the issue number
    # actually gets picked up instead of silently resolving to "".
    id_col = next((h for h in headers if h and str(h).strip().lower() == "id"), None)
    resolve_line = _parse_line_adjustments(args.line_shift, args.line_override)

    rows = []
    for r in range(2, ws.max_row + 1):
        values = [c.value for c in ws[r]]
        if all(v is None for v in values):
            continue
        rows.append({headers[i]: values[i] for i in range(len(values)) if i < len(headers)})

    matches = [r for r in rows if file_col and args.file.lower() in str(r.get(file_col, "")).lower()]
    if not matches:
        print(f"No AI_Analysis rows found for file filter '{args.file}'.")
        return

    def _line_key(r):
        try:
            return int(r.get("Line") or 0)
        except (TypeError, ValueError):
            return 0
    matches.sort(key=_line_key)

    source_lines = []
    if args.source and os.path.isfile(args.source):
        with open(args.source, "r", encoding="utf-8", errors="replace") as f:
            source_lines = f.readlines()

    total = len(matches)
    critical = sum(1 for r in matches if str(r.get("Verdict", "")).strip().lower() == "critical")
    not_critical = total - critical
    fixed = sum(1 for r in matches if str(r.get("FixApplied", "")).strip().lower() == "yes")

    out = []
    out.append(f"# Klocwork Analysis Report - {args.file}")
    out.append("")
    out.append(f"- **Source workbook:** `{args.xlsx}`")
    out.append(f"- **Generated:** {datetime.now().isoformat(timespec='seconds')}")
    out.append(f"- **Total warnings:** {total}")
    out.append(f"- **Critical:** {critical}")
    out.append(f"- **Not Critical:** {not_critical}")
    out.append(f"- **Fixes applied:** {fixed}")
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append("| # | Issue No | Place | Code Snapshot | Critical? | Evidence / Comment | Proposal | Fixed | Confirmed | Reviewer Comment | Src Row |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")

    for i, r in enumerate(matches, start=1):
        orig_line = r.get("Line")
        line_no = resolve_line(orig_line)
        method = r.get("Method") or ""
        code = r.get("Code") or ""
        issue_no = (r.get(id_col) if id_col else None) or ""
        snap, resolved_line, was_adjusted = _code_snapshot(source_lines, line_no, args.context)
        place_line = resolved_line if was_adjusted else line_no
        place = f"{args.file}:{place_line} ({method}) [{code}]"
        verdict = str(r.get("Verdict") or "").strip()
        comment = r.get("Comment") or ""
        proposal = r.get("Proposal") or ""
        fix_applied = r.get("FixApplied") or ""
        confirmed = r.get("Confirmed") or ""
        reviewer_comment = r.get("ReviewerComment") or ""
        src_row = r.get("_SourceRow") or ""
        out.append(
            "| " + str(i) + " | " + _esc_md_cell(issue_no) + " | " + _esc_md_cell(place) + " | <pre>" + _esc_md_cell(snap) +
            "</pre> | " + _esc_md_cell(verdict) + " | " + _esc_md_cell(comment) + " | " +
            _esc_md_cell(proposal) + " | " + _esc_md_cell(fix_applied) + " | " + _esc_md_cell(confirmed) + " | " + _esc_md_cell(reviewer_comment) +
            " | " + _esc_md_cell(src_row) + " |"
        )


    md_text = "\n".join(out) + "\n"
    out_path = args.output or f"{Path(args.file).stem}_report.md"
    Path(out_path).write_text(md_text, encoding="utf-8")
    print(f"Report written to {out_path} ({total} warnings, {critical} critical, {not_critical} not critical, {fixed} fixed)")


def main():
    parser = argparse.ArgumentParser(description="Klocwork Excel report helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_summary = sub.add_parser("summary", help="Show columns and per-file warning counts")
    p_summary.add_argument("xlsx")
    p_summary.add_argument("--sheet", default=None)
    p_summary.add_argument("--header-row", type=int, default=1)
    p_summary.set_defaults(func=cmd_summary)

    p_list = sub.add_parser("list", help="List all warnings for one file")
    p_list.add_argument("xlsx")
    p_list.add_argument("--file", required=True)
    p_list.add_argument("--sheet", default=None)
    p_list.add_argument("--header-row", type=int, default=1)
    p_list.set_defaults(func=cmd_list)

    p_write = sub.add_parser("write", help="Upsert AI analysis rows into the AI_Analysis sheet")
    p_write.add_argument("xlsx")
    p_write.add_argument("--input", required=True, help="JSON file with a list of analysis entries")
    p_write.add_argument("--sheet", default=None)
    p_write.add_argument("--analysis-sheet", default="AI_Analysis")
    p_write.add_argument("--header-row", type=int, default=1)
    p_write.set_defaults(func=cmd_write)

    p_report = sub.add_parser("report", help="Generate a Markdown summary report for one file from AI_Analysis")
    p_report.add_argument("xlsx")
    p_report.add_argument("--file", required=True)
    p_report.add_argument("--source", default=None, help="Path to the real source file, to embed code snapshots")
    p_report.add_argument("--context", type=int, default=4, help="Lines of context around the reported Line (used as-is for file-scope findings; used as the elided context window for large functions)")
    p_report.add_argument("--analysis-sheet", default="AI_Analysis")
    p_report.add_argument("--output", default=None, help="Output .md path (default: <file>_report.md)")
    p_report.add_argument("--line-shift", action="append", metavar="START:DELTA",
                           help="Correct stale Line numbers after a source edit changed line count: "
                                "any original Line >= START is adjusted by DELTA before snapshot/display. "
                                "Repeatable; deltas are cumulative for edits at different points in the same file.")
    p_report.add_argument("--line-override", action="append", metavar="ORIG:NEW",
                           help="Force an exact original Line to map to a specific current Line (takes "
                                "precedence over --line-shift); use for non-uniform edits like a reordered block.")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
