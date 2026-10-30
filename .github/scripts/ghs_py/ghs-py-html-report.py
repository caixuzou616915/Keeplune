"""ghs-py-html-report — Canonical, fixed-structure HTML report for a flash/debug session.

Task 5 requires a *single canonical template* whose sections, ordering, headings and styling never
change between runs — only the data content varies. To enforce that, this module renders the report
from ONE constant skeleton (:data:`_TEMPLATE`) plus a fixed, ordered list of section renderers
(:data:`_SECTIONS`). The AI does not (and must not) improvise a per-run layout: callers only supply
the session ``dict`` produced by ``ghs-py-output``.

Mandatory sections, always in this order:
    1. Session metadata (target, date/time, method/device)
    2. Summary / overview (overall PASS/FAIL, totals)
    3. Step-by-step timeline (per-step timing)
    4. Breakpoint table (file, function, line, hit status, values)
    5. Inspected register/memory/variable values
    6. Errors & handling
    7. Total time taken (prompt -> solved: per-step + overall elapsed)
    8. Raw environment / config footer

Pure standard library (``html`` for escaping). No external CSS/JS — the report is a single,
self-contained file.
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Dict, List


TEMPLATE_VERSION = "1.0.0"


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _badge(status: str) -> str:
    cls = {
        "PASS": "b-pass", "FAIL": "b-fail", "SKIP": "b-skip", "RUNNING": "b-run",
    }.get(str(status).upper(), "b-run")
    return f'<span class="badge {cls}">{_esc(status)}</span>'


# --------------------------------------------------------------------------------------------------
# Section renderers — fixed order, fixed headings. Each returns an HTML string.
# --------------------------------------------------------------------------------------------------
def _sec_metadata(d: Dict) -> str:
    m = d["metadata"]
    h = m.get("host", {})
    rows = [
        ("Task", m.get("task") or "(debug session)"),
        ("Method", m.get("method")),
        ("Debugger device", m.get("device")),
        ("Target variant", m.get("target_variant")),
        ("Bench / chip / core", f"{m.get('bench')} / {m.get('chip')} / {m.get('app_core')}"),
        ("Mode", "SIMULATE" if m.get("simulate") else "LIVE"),
        ("Started", m.get("started")),
        ("Ended", m.get("ended")),
        ("Host", f"{h.get('hostname','?')} — {h.get('os','?')} (py{h.get('python','?')})"),
    ]
    body = "".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows)
    return _section("1. Session Metadata", f'<table class="kv">{body}</table>')


def _sec_summary(d: Dict) -> str:
    s = d["summary"]
    cards = [
        ("Overall", _badge(s["overall"]), ""),
        ("Total time", f"{s['total_elapsed_s']:.3f}s", ""),
        ("Steps passed", f"{s['steps_passed']}/{s['steps_total']}",
         f"{s['steps_failed']} failed, {s['steps_skipped']} skipped"),
        ("Breakpoints hit", f"{s['breakpoints_hit']}/{s['breakpoints_total']}", ""),
        ("Errors", f"{s['errors_total']}", f"{s['errors_handled']} handled"),
    ]
    cells = "".join(
        f'<div class="card"><div class="card-h">{_esc(t)}</div>'
        f'<div class="card-v">{v}</div><div class="card-s">{_esc(sub)}</div></div>'
        for t, v, sub in cards
    )
    return _section("2. Summary / Overview", f'<div class="cards">{cells}</div>')


def _sec_timeline(d: Dict) -> str:
    head = "<tr><th>#</th><th>Step</th><th>Status</th><th>Elapsed (s)</th><th>Detail</th></tr>"
    rows = []
    for i, s in enumerate(d["steps"], 1):
        err = f'<div class="err">! {_esc(s["error"])}</div>' if s.get("error") else ""
        rows.append(
            f"<tr><td>{i}</td><td>{_esc(s['name'])}</td><td>{_badge(s['status'])}</td>"
            f"<td class='num'>{s['elapsed_s']:.3f}</td><td>{_esc(s['detail'])}{err}</td></tr>"
        )
    return _section("3. Step-by-Step Timeline",
                    f'<table class="grid"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table>')


def _sec_breakpoints(d: Dict) -> str:
    bps = d.get("breakpoints", [])
    if not bps:
        return _section("4. Breakpoints", '<p class="muted">No breakpoints set in this session.</p>')
    head = ("<tr><th>Function</th><th>File</th><th>Line</th><th>Address</th>"
            "<th>Kind</th><th>Hit</th><th>Count</th><th>Values</th></tr>")
    rows = []
    for b in bps:
        vals = ", ".join(f"{_esc(k)}={_esc(v)}" for k, v in b.get("values", {}).items())
        hit = _badge("PASS") if b.get("hit") else _badge("SKIP")
        rows.append(
            f"<tr><td>{_esc(b['function'])}</td><td>{_esc(b.get('file') or '-')}</td>"
            f"<td class='num'>{_esc(b.get('line') if b.get('line') is not None else '-')}</td>"
            f"<td class='mono'>{_esc(b.get('address') or '-')}</td>"
            f"<td>{_esc(b.get('kind'))}</td><td>{hit}</td>"
            f"<td class='num'>{_esc(b.get('hit_count', 0))}</td><td class='mono'>{vals}</td></tr>"
        )
    return _section("4. Breakpoints",
                    f'<table class="grid"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table>')


def _sec_inspections(d: Dict) -> str:
    items = d.get("inspections", [])
    if not items:
        return _section("5. Inspected Values",
                        '<p class="muted">No register/memory/variable values inspected.</p>')
    head = "<tr><th>Name</th><th>Scope</th><th>Expression</th><th>Value</th><th>Step</th><th>Time</th></tr>"
    rows = [
        f"<tr><td>{_esc(i['name'])}</td><td>{_esc(i['scope'])}</td>"
        f"<td class='mono'>{_esc(i['expr'])}</td><td class='mono'>{_esc(i['value'])}</td>"
        f"<td>{_esc(i['step'])}</td><td>{_esc(i['ts'])}</td></tr>"
        for i in items
    ]
    return _section("5. Inspected Register / Memory / Variable Values",
                    f'<table class="grid"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table>')


def _sec_errors(d: Dict) -> str:
    errs = d.get("errors", [])
    if not errs:
        return _section("6. Errors & Handling",
                        '<p class="muted ok">No errors encountered.</p>')
    head = "<tr><th>Step</th><th>Message</th><th>Marker</th><th>Handled</th><th>Action taken</th></tr>"
    rows = [
        f"<tr><td>{_esc(e['step'])}</td><td>{_esc(e['message'])}</td>"
        f"<td class='mono'>{_esc(e.get('marker') or '-')}</td>"
        f"<td>{_badge('PASS') if e.get('handled') else _badge('FAIL')}</td>"
        f"<td>{_esc(e.get('action') or '-')}</td></tr>"
        for e in errs
    ]
    return _section("6. Errors & Handling",
                    f'<table class="grid"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table>')


def _sec_total_time(d: Dict) -> str:
    m, s = d["metadata"], d["summary"]
    steps = d.get("steps", [])
    kv = (
        f"<tr><th>Started</th><td>{_esc(m.get('started'))}</td></tr>"
        f"<tr><th>Ended</th><td>{_esc(m.get('ended'))}</td></tr>"
        f"<tr><th>Total time (prompt &rarr; solved)</th>"
        f"<td class='num'>{s['total_elapsed_s']:.3f}s</td></tr>"
    )
    head = "<tr><th>Step</th><th>Elapsed (s)</th></tr>"
    rows = "".join(
        f"<tr><td>{_esc(st['name'])}</td><td class='num'>{st['elapsed_s']:.3f}</td></tr>"
        for st in steps
    )
    total_row = f"<tr class='total'><td>TOTAL</td><td class='num'>{s['total_elapsed_s']:.3f}</td></tr>"
    note = ('<p class="muted">Wall-clock time for this session, covering all debug/processing '
            'steps from start to completion.</p>')
    return _section("7. Total Time Taken",
                    f'<table class="kv">{kv}</table>'
                    f'<table class="grid"><thead>{head}</thead>'
                    f'<tbody>{rows}{total_row}</tbody></table>{note}')


def _sec_footer(d: Dict) -> str:
    cfg = d.get("config", {})
    keys = ["project_root", "variant", "git_bash", "ghs_path_prefix", "skip_verify",
            "multi_rc", "debug_rc", "verify_py"]
    rows = "".join(
        f"<tr><th>{_esc(k)}</th><td class='mono'>{_esc(cfg.get(k))}</td></tr>"
        for k in keys if k in cfg
    )
    return _section("8. Environment / Configuration", f'<table class="kv">{rows}</table>')


# Fixed, ordered section pipeline — the canonical structure the AI must always follow.
_SECTIONS = [
    _sec_metadata,
    _sec_summary,
    _sec_timeline,
    _sec_breakpoints,
    _sec_inspections,
    _sec_errors,
    _sec_total_time,
    _sec_footer,
]


def _section(title: str, body_html: str) -> str:
    anchor = title.split(".")[0].strip()
    return (f'<section id="s{anchor}"><h2>{_esc(title)}</h2>{body_html}</section>')


def render(session_dict: Dict) -> str:
    """Render the full canonical HTML document from a session ``dict``."""
    m = session_dict["metadata"]
    s = session_dict["summary"]
    nav = "".join(
        f'<a href="#s{i}">{lbl}</a>'
        for i, lbl in enumerate(
            ["Metadata", "Summary", "Timeline", "Breakpoints", "Values",
             "Errors", "Total Time", "Config"], 1)
    )
    sections = "\n".join(fn(session_dict) for fn in _SECTIONS)
    title = f"Traveo Flash/Debug Report — {m.get('target_variant','')}"
    subtitle = (f"{m.get('method','')} · {m.get('device','')} · "
                f"{'SIMULATE' if m.get('simulate') else 'LIVE'} · {m.get('started','')}")
    return _TEMPLATE.format(
        title=_esc(title),
        subtitle=_esc(subtitle),
        overall_badge=_badge(s["overall"]),
        nav=nav,
        sections=sections,
        template_version=TEMPLATE_VERSION,
        generated=_esc(datetime.now().isoformat(timespec="seconds")),
    )


def write(session_dict: Dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(session_dict), encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------------------
# The ONE canonical skeleton. Do not fork per-run — only the {placeholders} change.
# --------------------------------------------------------------------------------------------------
_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --primary:#2c3e50; --accent:#3498db; --ok:#27ae60; --fail:#e74c3c;
    --warn:#f39c12; --bg:#eef1f4; --card:#fff; --border:#d5dbe0; --mono:#f4f6f8;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:'Segoe UI',Tahoma,sans-serif; background:var(--bg); color:var(--primary);
          line-height:1.55; padding:24px; }}
  .wrap {{ max-width:1200px; margin:0 auto; background:var(--card); border-radius:10px;
           box-shadow:0 2px 12px rgba(0,0,0,.08); overflow:hidden; }}
  header {{ background:linear-gradient(135deg,var(--primary),var(--accent)); color:#fff;
            padding:28px 36px; }}
  header h1 {{ font-size:1.7em; }}
  header .sub {{ opacity:.9; margin-top:6px; font-size:.95em; }}
  header .ov {{ margin-top:12px; font-size:1.05em; }}
  nav {{ background:var(--primary); padding:10px 36px; position:sticky; top:0; z-index:5; }}
  nav a {{ color:#fff; text-decoration:none; margin-right:16px; font-size:.9em; }}
  nav a:hover {{ text-decoration:underline; }}
  main {{ padding:24px 36px 40px; }}
  section {{ margin:26px 0; }}
  section h2 {{ font-size:1.2em; color:var(--primary); border-left:4px solid var(--accent);
                padding-left:10px; margin-bottom:12px; }}
  table {{ width:100%; border-collapse:collapse; font-size:.9em; }}
  table.kv th {{ text-align:left; width:220px; background:var(--mono); padding:7px 10px;
                 border:1px solid var(--border); }}
  table.kv td {{ padding:7px 10px; border:1px solid var(--border); }}
  table.grid th {{ background:var(--primary); color:#fff; text-align:left; padding:8px 10px; }}
  table.grid td {{ padding:7px 10px; border:1px solid var(--border); vertical-align:top; }}
  table.grid tbody tr:nth-child(even) {{ background:#f7f9fb; }}
  tr.total td {{ font-weight:700; background:#eaf3fb; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .mono {{ font-family:Consolas,'Courier New',monospace; background:var(--mono); }}
  .cards {{ display:flex; flex-wrap:wrap; gap:14px; }}
  .card {{ flex:1 1 160px; border:1px solid var(--border); border-radius:8px; padding:14px 16px;
           background:#fbfdff; }}
  .card-h {{ font-size:.8em; text-transform:uppercase; color:#7a8791; letter-spacing:.04em; }}
  .card-v {{ font-size:1.5em; font-weight:700; margin:4px 0; }}
  .card-s {{ font-size:.8em; color:#7a8791; }}
  .badge {{ display:inline-block; padding:2px 10px; border-radius:12px; font-size:.8em;
            font-weight:700; color:#fff; }}
  .b-pass {{ background:var(--ok); }} .b-fail {{ background:var(--fail); }}
  .b-skip {{ background:var(--warn); }} .b-run {{ background:var(--accent); }}
  .muted {{ color:#7a8791; font-style:italic; }} .muted.ok {{ color:var(--ok); }}
  .err {{ color:var(--fail); font-family:Consolas,monospace; font-size:.85em; margin-top:4px; }}
  footer {{ padding:14px 36px; background:var(--mono); color:#7a8791; font-size:.8em;
            border-top:1px solid var(--border); }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{title}</h1>
    <div class="sub">{subtitle}</div>
    <div class="ov">Overall result: {overall_badge}</div>
  </header>
  <nav>{nav}</nav>
  <main>
{sections}
  </main>
  <footer>
    Generated by ghs-py-html-report (canonical template v{template_version}) · {generated}
  </footer>
</div>
</body>
</html>
"""
