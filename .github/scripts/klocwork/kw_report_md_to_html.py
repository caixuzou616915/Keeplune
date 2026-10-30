#!/usr/bin/env python3
"""
Klocwork Analysis Report - Markdown to HTML Converter
========================================================
Converts a report produced by `kw_report_tool.py report` (title, metadata
bullet list, one summary table with columns Place / Code Snapshot /
Critical? / Evidence-Comment / Proposal) into a single self-contained,
styled HTML file.

This is a small, dedicated converter (not the generic multi-section C/C++
review converter) because it needs exact-match coloring of the "Critical?"
column ("Critical" vs "Not Critical" must not collide), and the report's
table cells already carry pre-escaped HTML (&#124; for literal '|', <br>
for newlines, <pre> for code snapshots) written by kw_report_tool.py.

Usage:
    python kw_report_md_to_html.py <input.md> [output.html]

    Default output: same path as input with .html extension.
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --primary: #2c3e50; --accent: #3498db; --critical: #c0392b; --ok: #27ae60;
    --bg: #ecf0f1; --card: #ffffff; --border: #bdc3c7; --code-bg: #f8f9fa;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background: var(--bg); color: var(--primary); }}
  .container {{ max-width: 98vw; margin: 0 auto; background: var(--card); box-shadow: 0 2px 10px rgba(0,0,0,.1); }}
  header {{ background: linear-gradient(135deg, var(--primary), var(--accent)); color: #fff; padding: 30px 40px; }}
  header h1 {{ margin: 0 0 8px 0; font-size: 1.8em; }}
  header .meta {{ opacity: .9; font-size: .95em; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 15px; padding: 25px 40px; }}
  .stat {{ background: var(--bg); border-left: 4px solid var(--accent); border-radius: 6px; padding: 15px; text-align: center; }}
  .stat .num {{ font-size: 2em; font-weight: bold; display: block; }}
  .stat.critical {{ border-left-color: var(--critical); }}
  .stat.critical .num {{ color: var(--critical); }}
  .stat.ok {{ border-left-color: var(--ok); }}
  .stat.ok .num {{ color: var(--ok); }}
  .content {{ padding: 0 40px 40px 40px; }}
  .table-wrapper {{ overflow-x: auto; box-shadow: 0 2px 4px rgba(0,0,0,.08); border-radius: 6px; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; table-layout: auto; }}
  th {{ background: var(--primary); color: #fff; padding: 12px; text-align: left; position: sticky; top: 0; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; max-width: 380px; word-break: break-word; }}
  td.comment-cell, td.proposal-cell {{ max-width: 640px; min-width: 320px; }}
  tr:hover {{ background: var(--bg); }}
  td pre, td code {{ background: var(--code-bg); border-left: 3px solid var(--accent); padding: 6px 8px; border-radius: 4px; font-size: .82em; white-space: pre-wrap; word-break: break-word; margin: 0; display: block; }}
  .badge {{ display: inline-block; padding: 4px 12px; border-radius: 14px; font-weight: bold; font-size: .85em; color: #fff; white-space: nowrap; }}
  .badge-critical {{ background: var(--critical); }}
  .badge-ok {{ background: var(--ok); }}
  footer {{ text-align: center; padding: 20px; color: #7f8c8d; font-size: .85em; }}

  /* Code snapshot: dark, line-gutter, syntax-colored, flagged-line highlight */
  .code-block {{ background: #1e1e2f; color: #d4d4d4; border-radius: 6px; padding: 6px 0; font-family: 'Consolas', 'Cascadia Code', monospace; font-size: .8em; line-height: 1.5; overflow-x: auto; min-width: 260px; }}
  .code-line {{ display: flex; white-space: pre; padding: 0 10px; }}
  .code-line.marked {{ background: #4a3400; border-left: 3px solid #f1c40f; padding-left: 7px; }}
  .code-line .gutter {{ color: #6c7a89; width: 3.2em; flex-shrink: 0; text-align: right; margin-right: 10px; user-select: none; }}
  .code-line.marked .gutter {{ color: #f1c40f; font-weight: bold; }}
  .code-line .code {{ color: #d4d4d4; }}
  .tok-comment {{ color: #6a9955; font-style: italic; }}
  .tok-string {{ color: #ce9178; }}
  .tok-preproc {{ color: #c586c0; }}
  .tok-number {{ color: #b5cea8; }}
  .tok-keyword {{ color: #569cd6; font-weight: bold; }}

  /* Reviewer controls: 3-way accept/reject/blank + free-text comment */
  .confirm-group {{ display: flex; flex-direction: column; gap: 4px; white-space: nowrap; }}
  .confirm-group label {{ font-size: .85em; cursor: pointer; display: flex; align-items: center; gap: 4px; }}
  .confirm-group input[type=radio] {{ cursor: pointer; }}
  .reviewer-comment {{ width: 100%; min-width: 160px; min-height: 50px; font-family: inherit; font-size: .85em; padding: 4px 6px; border: 1px solid var(--border); border-radius: 4px; resize: vertical; }}
  .row-save-tag {{ display: block; font-size: .75em; color: var(--ok); font-weight: bold; margin-top: 4px; min-height: 1.2em; opacity: 0; transition: opacity .2s ease; }}
  .row-save-tag.visible {{ opacity: 1; }}
  .toolbar {{ padding: 15px 40px 0 40px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
  .export-btn {{ background: var(--accent); color: #fff; border: none; padding: 10px 18px; border-radius: 6px; font-size: .95em; cursor: pointer; font-weight: bold; }}
  .export-btn:hover {{ background: #2980b9; }}
  .export-btn.secondary {{ background: #7f8c8d; }}
  .export-btn.secondary:hover {{ background: #6c7a89; }}
  .export-status {{ font-size: .85em; color: #7f8c8d; }}
  #saveIndicator {{ font-size: .85em; font-weight: bold; color: var(--ok); min-width: 220px; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>{title}</h1>
    <div class="meta">{meta}</div>
  </header>
  <div class="stats">{stats}</div>
  <div class="toolbar">
    <button class="export-btn" onclick="exportReviewedJson()">Export Reviewed JSON</button>
    <button class="export-btn secondary" onclick="clearLocalReviews()">Clear locally saved reviews</button>
    <span id="saveIndicator"></span>
    <span class="export-status">Accept/Reject saves immediately; remarks save when you click away from the box (a "Saved HH:MM:SS" tag appears next to that row's controls). When viewed through serve_reports.py, saves also sync to the server so they survive a refresh and are visible to other users/PCs. Click Export to produce the JSON to feed back into <code>kw_report_tool.py write</code> (that's the permanent save into the workbook).</span>
  </div>
  <div class="content">
    <div class="table-wrapper">
      <table id="reportTable">
        <thead><tr>{head_cells}</tr></thead>
        <tbody>
{body_rows}
        </tbody>
      </table>
    </div>
  </div>
  <footer>Generated by kw_report_md_to_html.py on {timestamp}</footer>
</div>
<script>
const STORAGE_KEY = 'kw_review_state::' + {title_json};
// Basename of this file (e.g. "foo_report.html") - used as the key when
// syncing review state through the report server's /api/confirm endpoint.
// Only resolves to something meaningful when served over http(s); when this
// file is opened directly (file://) the fetch calls below simply fail and
// everything falls back to the localStorage-only behavior.
const REPORT_NAME = location.pathname.split('/').pop();

function loadLocalState() {{
  try {{
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {{}};
  }} catch (e) {{ return {{}}; }}
}}

function saveLocalState(state) {{
  try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }} catch (e) {{ /* storage unavailable/full: ignore */ }}
}}

function setSaveIndicator(text) {{
  const el = document.getElementById('saveIndicator');
  if (el) el.textContent = text;
}}

function markRowSaved(tr) {{
  const now = new Date().toLocaleTimeString();
  tr.querySelectorAll('.row-save-tag').forEach(tag => {{
    tag.textContent = 'Saved ' + now;
    tag.classList.add('visible');
    clearTimeout(tag._fadeTimer);
    tag._fadeTimer = setTimeout(() => tag.classList.remove('visible'), 2500);
  }});
}}

function pushServerState(row, confirmed, userComment) {{
  // Best-effort: if there's no server (e.g. file opened directly) this just
  // fails silently and the localStorage copy remains the only record.
  fetch('/api/confirm', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{report: REPORT_NAME, row: row, confirmed: confirmed, user_comment: userComment}})
  }}).catch(() => {{}});
}}

function fetchServerState() {{
  return fetch('/api/confirm?report=' + encodeURIComponent(REPORT_NAME))
    .then(r => r.ok ? r.json() : {{}})
    .catch(() => null);
}}

function applyState(state) {{
  Object.keys(state).forEach(row => {{
    const tr = document.querySelector('#reportTable tbody tr[data-row="' + row + '"]');
    if (!tr) return;
    const entry = state[row];
    if (entry.confirmed !== undefined) {{
      const radio = tr.querySelector('input[type=radio][value="' + entry.confirmed + '"]');
      if (radio) radio.checked = true;
    }}
    if (entry.user_comment) {{
      const commentBox = tr.querySelector('.reviewer-comment');
      if (commentBox) commentBox.value = entry.user_comment;
    }}
  }});
}}

function currentStateFromDom() {{
  const state = {{}};
  document.querySelectorAll('#reportTable tbody tr[data-row]').forEach(tr => {{
    const row = tr.getAttribute('data-row');
    const checked = tr.querySelector('input[type=radio]:checked');
    const commentBox = tr.querySelector('.reviewer-comment');
    state[row] = {{
      confirmed: checked ? checked.value : '',
      user_comment: commentBox ? commentBox.value : ''
    }};
  }});
  return state;
}}

function autoSaveRow(tr) {{
  const state = loadLocalState();
  const row = tr.getAttribute('data-row');
  const checked = tr.querySelector('input[type=radio]:checked');
  const commentBox = tr.querySelector('.reviewer-comment');
  const confirmed = checked ? checked.value : '';
  const user_comment = commentBox ? commentBox.value : '';
  state[row] = {{ confirmed: confirmed, user_comment: user_comment }};
  saveLocalState(state);
  pushServerState(row, confirmed, user_comment);
  markRowSaved(tr);
}}

function restoreLocalState() {{
  const state = loadLocalState();
  const rowIds = Object.keys(state);
  if (rowIds.length === 0) return;
  rowIds.forEach(row => {{
    const tr = document.querySelector('#reportTable tbody tr[data-row="' + row + '"]');
    if (!tr) return;
    const entry = state[row];
    if (entry.confirmed !== undefined) {{
      const radio = tr.querySelector('input[type=radio][value="' + entry.confirmed + '"]');
      if (radio) radio.checked = true;
    }}
    if (entry.user_comment) {{
      const commentBox = tr.querySelector('.reviewer-comment');
      if (commentBox) commentBox.value = entry.user_comment;
    }}
  }});
  setSaveIndicator('Restored ' + rowIds.length + ' saved review(s) from this browser');
}}

function clearLocalReviews() {{
  if (!confirm('Clear all locally saved Accept/Reject/comment state for this report in this browser?')) return;
  localStorage.removeItem(STORAGE_KEY);
  document.querySelectorAll('#reportTable tbody tr[data-row]').forEach(tr => {{
    const blank = tr.querySelector('input[type=radio][value=""]');
    if (blank) blank.checked = true;
    const commentBox = tr.querySelector('.reviewer-comment');
    if (commentBox) commentBox.value = '';
  }});
  setSaveIndicator('Local reviews cleared');
}}

function htmlDecode(text) {{
  const el = document.createElement('textarea');
  el.innerHTML = text.replace(/<br\s*\/?>/gi, '\\n');
  return el.value;
}}
function exportReviewedJson() {{
  saveLocalState(currentStateFromDom());
  const rows = document.querySelectorAll('#reportTable tbody tr[data-row]');
  const out = [];
  rows.forEach(tr => {{
    const row = parseInt(tr.getAttribute('data-row'), 10);
    if (!row) return;
    const checked = tr.querySelector('input[type=radio]:checked');
    const confirmed = checked ? checked.value : '';
    const commentBox = tr.querySelector('.reviewer-comment');
    const user_comment = commentBox ? commentBox.value : '';
    out.push({{
      row: row,
      verdict: htmlDecode(tr.getAttribute('data-verdict') || ''),
      comment: htmlDecode(tr.getAttribute('data-comment') || ''),
      proposal: htmlDecode(tr.getAttribute('data-proposal') || ''),
      fix_applied: htmlDecode(tr.getAttribute('data-fixapplied') || ''),
      confirmed: confirmed,
      user_comment: user_comment
    }});
  }});
  const blob = new Blob([JSON.stringify(out, null, 1)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'reviewed_analysis.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setSaveIndicator('Exported JSON at ' + new Date().toLocaleTimeString());
}}

document.addEventListener('DOMContentLoaded', () => {{
  restoreLocalState();
  // Push any state already saved locally (e.g. from before server-sync
  // existed on this page) up to the server, so the homepage's Reviewed
  // count picks up past work without needing every row re-clicked.
  const localState = loadLocalState();
  Object.keys(localState).forEach(row => {{
    const entry = localState[row];
    if (entry && (entry.confirmed || entry.user_comment)) {{
      pushServerState(row, entry.confirmed || '', entry.user_comment || '');
    }}
  }});
  fetchServerState().then(serverState => {{
    if (!serverState || Object.keys(serverState).length === 0) return;
    applyState(serverState);
    const merged = loadLocalState();
    Object.keys(serverState).forEach(row => {{ merged[row] = serverState[row]; }});
    saveLocalState(merged);
    setSaveIndicator('Loaded ' + Object.keys(serverState).length + ' review(s) from the shared server');
  }});
  document.querySelectorAll('#reportTable tbody tr[data-row] input[type=radio]').forEach(el => {{
    el.addEventListener('change', () => autoSaveRow(el.closest('tr')));
  }});
  document.querySelectorAll('#reportTable tbody tr[data-row] .reviewer-comment').forEach(el => {{
    el.addEventListener('blur', () => autoSaveRow(el.closest('tr')));
  }});
}});
</script>
</body>
</html>
"""


def parse_report(md_text):
    lines = md_text.splitlines()
    title = "Klocwork Analysis Report"
    meta_lines = []
    table_lines = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and title == "Klocwork Analysis Report":
            title = stripped[2:].strip()
            continue
        if stripped.startswith("- **"):
            meta_lines.append(stripped[2:].strip())
            continue
        if stripped.startswith("|"):
            in_table = True
            table_lines.append(stripped)
            continue
        if in_table and not stripped.startswith("|"):
            in_table = False
    return title, meta_lines, table_lines


def split_row(line):
    # Cells are already HTML-safe (pipes pre-escaped as &#124; by the generator),
    # so a plain split on the literal '|' delimiter is safe here.
    parts = line.strip().strip("|").split("|")
    return [p.strip() for p in parts]


def render_meta(meta_lines):
    def md_bold(text):
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return " &nbsp;|&nbsp; ".join(md_bold(m) for m in meta_lines)


def render_verdict_cell(cell):
    plain = re.sub(r"<[^>]+>", "", cell).strip()
    if plain.lower() == "critical":
        return f'<span class="badge badge-critical">{plain}</span>'
    if plain.lower() == "not critical":
        return f'<span class="badge badge-ok">{plain}</span>'
    return cell


_C_TOKEN_RE = re.compile(
    r"(?P<comment>/\*.*?\*/|//(?:(?!<br>).)*)"
    r"|(?P<string>\"(?:[^\"\\]|\\.)*\")"
    r"|(?P<preproc>#\s*[A-Za-z_]+)"
    r"|(?P<number>\b0[xX][0-9a-fA-F]+[uUlL]*\b|\b\d+\.\d+[fF]?\b|\b\d+[uUlL]*\b)"
    r"|(?P<keyword>\b(?:if|else|for|while|do|switch|case|default|break|continue|return|void|"
    r"const|static|struct|typedef|enum|union|sizeof|volatile|extern|inline|unsigned|signed|"
    r"char|int|short|long|float|double|goto|NULL|TRUE|FALSE)\b)"
)


def _highlight_c_tokens(code_text):
    """Lightweight, dependency-free C token colorizer for an already
    HTML-escaped line of code (no external highlighter/CDN needed to keep
    the report a single self-contained file)."""
    def repl(m):
        return f'<span class="tok-{m.lastgroup}">{m.group()}</span>'
    return _C_TOKEN_RE.sub(repl, code_text)


_SNAPSHOT_LINE_RE = re.compile(r"^(\s*(?:&gt;&gt;)?\d+:)(.*)$")


def render_code_snapshot(cell):
    """Render a kw_report_tool.py code-snapshot cell (a <pre>...</pre> block
    with <br>-joined '  NNN: <code>' / '>>NNN: <code>' lines) as a dark,
    line-numbered, syntax-colored code block with the flagged line
    highlighted, instead of a flat monospace blob."""
    inner = re.sub(r"^\s*<pre>|</pre>\s*$", "", cell.strip())
    if inner.strip().lower() in ("n/a", ""):
        return cell
    lines_html = []
    for line in inner.split("<br>"):
        marked = line.lstrip().startswith("&gt;&gt;")
        m = _SNAPSHOT_LINE_RE.match(line)
        gutter, code = (m.group(1), m.group(2)) if m else ("", line)
        code_html = _highlight_c_tokens(code)
        row_class = "code-line marked" if marked else "code-line"
        lines_html.append(
            f'<div class="{row_class}"><span class="gutter">{gutter}</span><span class="code">{code_html}</span></div>'
        )
    return '<div class="code-block">' + "".join(lines_html) + "</div>"


def render_confirmed_cell(cell, row_id):
    """3-way Accept/Reject/blank radio group replacing the old checkbox;
    'blank' means not yet reviewed. Maps to the Confirmed column's existing
    Yes/No/'' convention used by kw_report_tool.py write."""
    plain = re.sub(r"<[^>]+>", "", cell).strip().lower()
    name = f"confirmed_{row_id}"
    accept_checked = "checked" if plain == "yes" else ""
    reject_checked = "checked" if plain == "no" else ""
    blank_checked = "checked" if plain not in ("yes", "no") else ""
    return (
        f'<div class="confirm-group">'
        f'<label><input type="radio" name="{name}" value="Yes" {accept_checked}> Accept</label>'
        f'<label><input type="radio" name="{name}" value="No" {reject_checked}> Reject</label>'
        f'<label><input type="radio" name="{name}" value="" {blank_checked}> Blank (to be checked)</label>'
        f'<span class="row-save-tag"></span>'
        f'</div>'
    )


def render_reviewer_comment_cell(cell):
    plain = re.sub(r"<br\s*/?>", "\n", cell)
    plain = re.sub(r"<[^>]+>", "", plain)
    plain = (plain.replace("&amp;", "&").replace("&lt;", "<")
             .replace("&gt;", ">").replace("&#124;", "|"))
    return (f'<textarea class="reviewer-comment" placeholder="Reviewer remarks...">{plain}</textarea>'
            f'<span class="row-save-tag"></span>')


def _plain_text(cell):
    """Undo the pre-escaping kw_report_tool.py applies to a cell (<br> for
    newlines, &#124; for literal '|', HTML entities) to get raw text
    suitable for embedding in an HTML attribute (still attribute-escaped
    afterwards by the caller)."""
    text = re.sub(r"<br\s*/?>", "\n", cell)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&#124;", "|").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return text


def _attr_escape(text):
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def convert(md_text):
    title, meta_lines, table_lines = parse_report(md_text)
    meta_html = render_meta(meta_lines)

    stats_html = ""
    stat_map = {}
    for m in meta_lines:
        match = re.match(r"\*\*(.+?):\*\*\s*(.+)", m)
        if match:
            stat_map[match.group(1).strip()] = match.group(2).strip()
    stat_order = [("Total warnings", ""), ("Critical", "critical"), ("Not Critical", "ok"), ("Fixes applied", "ok")]
    for label, css_class in stat_order:
        if label in stat_map:
            cls = f" {css_class}" if css_class else ""
            stats_html += f'<div class="stat{cls}"><span class="num">{stat_map[label]}</span>{label}</div>'

    head_cells = ""
    body_rows = ""
    if len(table_lines) >= 2:
        header_cells = split_row(table_lines[0])
        head_cells = "".join(f"<th>{c}</th>" for c in header_cells)
        header_lower = [h.strip().lower() for h in header_cells]

        def _col(name_prefix):
            for i, h in enumerate(header_lower):
                if h.startswith(name_prefix):
                    return i
            return None

        idx_srcrow = _col("src row")
        idx_comment = _col("evidence")
        idx_proposal = _col("proposal")
        idx_fixed = _col("fixed")
        idx_verdict = _col("critical")

        for row_line in table_lines[2:]:
            cells = split_row(row_line)
            if len(cells) != len(header_cells):
                continue
            src_row = _plain_text(cells[idx_srcrow]).strip() if idx_srcrow is not None else ""
            tr_attrs = f' data-row="{_attr_escape(src_row)}"'
            for attr_name, idx in (("data-verdict", idx_verdict), ("data-comment", idx_comment),
                                    ("data-proposal", idx_proposal), ("data-fixapplied", idx_fixed)):
                if idx is not None:
                    tr_attrs += f' {attr_name}="{_attr_escape(_plain_text(cells[idx]))}"'

            tds = []
            for idx, cell in enumerate(cells):
                header = header_lower[idx]
                if header.startswith("critical"):
                    tds.append(f"<td>{render_verdict_cell(cell)}</td>")
                elif header.startswith("code snapshot"):
                    tds.append(f"<td>{render_code_snapshot(cell)}</td>")
                elif header.startswith("confirmed"):
                    tds.append(f"<td>{render_confirmed_cell(cell, src_row or str(idx))}</td>")
                elif header.startswith("reviewer comment"):
                    tds.append(f"<td>{render_reviewer_comment_cell(cell)}</td>")
                elif header.startswith("evidence"):
                    tds.append(f'<td class="comment-cell">{cell}</td>')
                elif header.startswith("proposal"):
                    tds.append(f'<td class="proposal-cell">{cell}</td>')
                else:
                    tds.append(f"<td>{cell}</td>")
            body_rows += f"          <tr{tr_attrs}>" + "".join(tds) + "</tr>\n"

    return HTML_TEMPLATE.format(
        title=title,
        title_json=json.dumps(title),
        meta=meta_html,
        stats=stats_html,
        head_cells=head_cells,
        body_rows=body_rows,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: python kw_report_md_to_html.py <input.md> [output.html]")
        sys.exit(1)
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_suffix(".html")
    md_text = input_path.read_text(encoding="utf-8")
    html = convert(md_text)
    output_path.write_text(html, encoding="utf-8")
    print(f"HTML report written to {output_path}")


if __name__ == "__main__":
    main()
