#!/usr/bin/env python3
"""
Klocwork report server
=======================
Serves the generated Klocwork HTML/Markdown reports (ai_output/klocwork/reports
by default) over plain HTTP so multiple users on other PCs can browse them
from a single running instance, instead of everyone needing their own copy
of the files.

Binds to 0.0.0.0 (all interfaces) by default so it is reachable from other
machines on the same network - only run this on a trusted network, since it
serves the directory with no authentication.

Usage:
    python serve_reports.py                    # serve default reports dir on port 8000
    python serve_reports.py --port 8080
    python serve_reports.py --dir <path>       # serve a different directory
    python serve_reports.py --host 127.0.0.1   # localhost-only instead of LAN-wide

Press Ctrl+C to stop the server.
"""
import argparse
import html
import json
import os
import re
import socket
import sys
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from http.server import HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from kw_config import find_repo_root

INDEX_FILENAME = "index.html"
ASSIGNMENTS_FILENAME = ".assignments.json"
CONFIRMATIONS_FILENAME = ".confirmations.json"
_assignments_lock = threading.Lock()
_confirmations_lock = threading.Lock()


def load_assignments(reports_dir):
    """Load the {report_filename: assignee_name} map, tolerating a missing
    or corrupt file (first run, or a write raced with a crash)."""
    path = os.path.join(reports_dir, ASSIGNMENTS_FILENAME)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_assignments(reports_dir, data):
    """Atomic write (tmp file + os.replace) so a concurrent reader from
    another thread/user never sees a half-written file."""
    path = os.path.join(reports_dir, ASSIGNMENTS_FILENAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def load_confirmations(reports_dir):
    """Load the {report_filename: {row_id: {confirmed, user_comment}}} store
    of per-warning reviewer decisions, tolerating a missing/corrupt file."""
    path = os.path.join(reports_dir, CONFIRMATIONS_FILENAME)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_confirmations(reports_dir, data):
    """Atomic write (tmp file + os.replace), same as save_assignments."""
    path = os.path.join(reports_dir, CONFIRMATIONS_FILENAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def default_reports_dir():
    return os.path.join(find_repo_root(), "ai_output", "klocwork", "reports")


def find_xlsx(reports_dir):
    """Best-effort locate the Klocwork issues workbook sitting alongside the
    generated reports (most recently modified one, if there happens to be
    more than one), so the index page can show per-file stats."""
    candidates = [
        f for f in os.listdir(reports_dir)
        if f.lower().endswith(".xlsx") and not f.startswith("~$")
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda f: os.path.getmtime(os.path.join(reports_dir, f)), reverse=True)
    return os.path.join(reports_dir, candidates[0])


def load_warning_totals(xlsx_path):
    """Load the raw Klocwork data rows (main sheet) once, so a per-report
    'Total warnings found' count can be computed without re-reading the
    workbook for every report. Returns None if openpyxl isn't installed or
    the workbook can't be read right now (e.g. locked by another process)
    so the index page can degrade gracefully instead of failing to render."""
    try:
        from kw_report_tool import load_rows, find_file_column
    except ImportError:
        return None
    try:
        _, _, headers, rows = load_rows(xlsx_path, None, 1)
        file_col = find_file_column(headers)
    except Exception:
        return None
    return rows, file_col


def total_for_basename(basename, warning_totals):
    """Total raw warnings Klocwork found for this file (main sheet), matched
    by substring on the file column - same matching convention as
    kw_report_tool.py's list/report --file."""
    if warning_totals is None:
        return None
    rows, file_col = warning_totals
    return sum(1 for r in rows if file_col and basename.lower() in str(r.get(file_col, "")).lower())


_REPORT_ROW_RE = re.compile(r'<tr\s+data-row="(\d+)"\s+data-verdict="([^"]*)"[^>]*>(.*?)</tr>', re.DOTALL)
_CONFIRM_RADIO_RE = re.compile(r'value="([^"]*)"\s*(checked)?\s*>')


def page_stats_for_report(report_path, report_name, confirmations):
    """Parse a generated <basename>_report.html directly (the single source
    of truth a human actually looks at) for Critical/Not Critical counts
    and a Reviewed count. A row counts as Reviewed only if its Confirmed
    control was actually set to Accept/Reject by a reviewer - the default
    'Blank (to be checked)' radio option does NOT count as reviewed.
    Server-persisted confirmations (saved via /api/confirm, e.g. clicked
    from another PC since this file was last generated) take priority over
    whatever confirmed state happens to be baked into the static HTML."""
    try:
        with open(report_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    row_confirmations = confirmations.get(report_name, {}) if confirmations else {}
    critical = not_critical = reviewed = 0
    for row_id, verdict, row_html in _REPORT_ROW_RE.findall(text):
        if verdict.strip().lower() == "critical":
            critical += 1
        else:
            not_critical += 1
        if row_id in row_confirmations:
            confirmed_value = row_confirmations[row_id].get("confirmed", "")
        else:
            confirmed_value = ""
            for value, checked in _CONFIRM_RADIO_RE.findall(row_html):
                if checked:
                    confirmed_value = value
                    break
        if confirmed_value:  # non-blank i.e. Accept/Reject, not the blank "to be checked" option
            reviewed += 1
    return {"critical": critical, "not_critical": not_critical, "reviewed": reviewed}


def _report_basename(report_name):
    suffix = "_report.html"
    if report_name.endswith(suffix):
        return report_name[: -len(suffix)]
    return Path(report_name).stem


def build_index(reports_dir):
    """(Re)generate index.html listing every .html file in reports_dir
    (except index.html itself), so users get a clickable overview instead
    of relying on directory listing alone. Called fresh on every request,
    so newly generated reports show up without restarting the server.
    Also merges in per-report stats (Total from the Klocwork xlsx sitting
    alongside the reports, if any; Critical/Not Critical/Reviewed parsed
    straight from each report page) and the "who is working on it" name
    saved via the /api/assign endpoint."""
    assignments = load_assignments(reports_dir)
    confirmations = load_confirmations(reports_dir)
    xlsx_path = find_xlsx(reports_dir)
    warning_totals = load_warning_totals(xlsx_path) if xlsx_path else None
    if xlsx_path is None:
        xlsx_note = "No Klocwork xlsx found alongside reports - Total column unavailable"
    elif warning_totals is None:
        xlsx_note = "Found %s but could not read it right now - Total column unavailable" % os.path.basename(xlsx_path)
    else:
        xlsx_note = "Total from " + os.path.basename(xlsx_path)

    entries = []
    for name in sorted(os.listdir(reports_dir)):
        if name == INDEX_FILENAME or not name.lower().endswith(".html"):
            continue
        path = os.path.join(reports_dir, name)
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
        size_kb = os.path.getsize(path) / 1024.0
        total = total_for_basename(_report_basename(name), warning_totals)
        page_stats = page_stats_for_report(path, name, confirmations)
        entries.append((name, mtime, size_kb, total, page_stats))

    def _fmt(value):
        return str(value) if value is not None else "N/A"

    row_tpl = (
        '<tr><td>%d</td><td><a href="%s">%s</a></td>'
        '<td><input type="text" class="assignee" data-report="%s" value="%s" placeholder="unassigned" maxlength="100"></td>'
        '<td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
        '<td>%s</td><td>%.1f KB</td></tr>'
    )
    rows = "\n".join(
        row_tpl % (
            i, html.escape(name), html.escape(name),
            html.escape(name), html.escape(assignments.get(name, "")),
            _fmt(total),
            _fmt(page_stats["critical"] if page_stats else None),
            _fmt(page_stats["not_critical"] if page_stats else None),
            _fmt(page_stats["reviewed"] if page_stats else None),
            mtime, size_kb,
        )
        for i, (name, mtime, size_kb, total, page_stats) in enumerate(entries, start=1)
    )
    if not rows:
        rows = '<tr><td colspan="9"><em>No reports found yet.</em></td></tr>'

    page = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Klocwork Reports</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 2em; background: #f7f7f9; }}
h1 {{ color: #2b2b2b; }}
table {{ border-collapse: collapse; width: 100%; max-width: 1300px; background: #fff; }}
th, td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; }}
th {{ background: #2b579a; color: #fff; }}
tr:nth-child(even) {{ background: #f2f2f2; }}
a {{ color: #2b579a; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.meta {{ color: #666; font-size: 0.9em; margin-bottom: 1em; }}
input.assignee {{ width: 100%; box-sizing: border-box; border: 1px solid #ccc; padding: 4px 6px; border-radius: 3px; font: inherit; }}
input.assignee:focus {{ outline: 2px solid #2b579a; }}
</style>
</head>
<body>
<h1>Klocwork Analysis Reports</h1>
<div class="meta">Generated {generated} | {xlsx_note} | Reviewed = Confirmed as Accept/Reject on the report page (blank "to be checked" does not count)</div>
<table>
<tr><th>No.</th><th>Report</th><th>Assigned To</th><th>Total</th><th>Critical</th><th>Not Critical</th><th>Reviewed</th><th>Last updated</th><th>Size</th></tr>
{rows}
</table>
<script>
document.querySelectorAll('input.assignee').forEach(function(inp) {{
  function save() {{
    fetch('/api/assign', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{report: inp.dataset.report, assignee: inp.value}})
    }}).then(function(r) {{
      inp.style.background = r.ok ? '#e6ffe6' : '#ffe6e6';
      setTimeout(function() {{ inp.style.background = ''; }}, 1000);
    }}).catch(function() {{ inp.style.background = '#ffe6e6'; }});
  }}
  inp.addEventListener('change', save);
  inp.addEventListener('keydown', function(e) {{ if (e.key === 'Enter') {{ inp.blur(); }} }});
}});
</script>
</body>
</html>
""".format(generated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), xlsx_note=html.escape(xlsx_note), rows=rows)

    with open(os.path.join(reports_dir, INDEX_FILENAME), "w", encoding="utf-8") as f:
        f.write(page)


def local_ips():
    """Best-effort list of this machine's LAN IPv4 addresses, so the user
    can share a reachable URL with other PCs."""
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except socket.gaierror:
        pass
    return sorted(ips)


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class QuietHandler(SimpleHTTPRequestHandler):
    refresh_index = True

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/confirm":
            self._handle_get_confirm(parse_qs(parsed.query))
            return
        if self.refresh_index and self.path in ("/", "/" + INDEX_FILENAME):
            build_index(self.directory)
        super().do_GET()

    def _valid_reports(self):
        return {
            f for f in os.listdir(self.directory)
            if f.lower().endswith(".html") and f != INDEX_FILENAME
        }

    def _read_json_body(self, max_len=4096):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0 or length > max_len:
            self.send_error(400, "Bad request")
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, AttributeError):
            self.send_error(400, "Invalid JSON body")
            return None

    def _send_json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_get_confirm(self, query):
        report = (query.get("report") or [""])[0]
        if report not in self._valid_reports():
            self.send_error(404, "Unknown report")
            return
        with _confirmations_lock:
            data = load_confirmations(self.directory).get(report, {})
        self._send_json(data)

    def do_POST(self):
        if self.path == "/api/assign":
            self._handle_post_assign()
        elif self.path == "/api/confirm":
            self._handle_post_confirm()
        else:
            self.send_error(404, "Not found")

    def _handle_post_assign(self):
        payload = self._read_json_body()
        if payload is None:
            return
        report = str(payload.get("report", ""))
        assignee = str(payload.get("assignee", "")).strip()[:100]

        # Only accept report names that actually exist in the served directory,
        # so /api/assign can't be used to stuff arbitrary keys into the store.
        if report not in self._valid_reports():
            self.send_error(404, "Unknown report")
            return

        with _assignments_lock:
            data = load_assignments(self.directory)
            if assignee:
                data[report] = assignee
            else:
                data.pop(report, None)
            save_assignments(self.directory, data)

        self._send_json({"ok": True, "report": report, "assignee": assignee})

    def _handle_post_confirm(self):
        payload = self._read_json_body()
        if payload is None:
            return
        report = str(payload.get("report", ""))
        row = str(payload.get("row", "")).strip()
        confirmed = str(payload.get("confirmed", "")).strip()
        user_comment = str(payload.get("user_comment", ""))[:2000]

        if not row.isdigit() or confirmed not in ("", "Yes", "No"):
            self.send_error(400, "Invalid row/confirmed value")
            return
        if report not in self._valid_reports():
            self.send_error(404, "Unknown report")
            return

        with _confirmations_lock:
            data = load_confirmations(self.directory)
            report_data = data.setdefault(report, {})
            if confirmed or user_comment:
                report_data[row] = {"confirmed": confirmed, "user_comment": user_comment}
            else:
                report_data.pop(row, None)
            save_confirmations(self.directory, data)

        self._send_json({"ok": True, "report": report, "row": row, "confirmed": confirmed})


def main():
    parser = argparse.ArgumentParser(description="Serve Klocwork HTML/Markdown reports over HTTP for multi-user access.")
    parser.add_argument("--dir", default=None, help="Directory to serve (default: <repo_root>/ai_output/klocwork/reports)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="Host/interface to bind (default: 0.0.0.0, all interfaces)")
    parser.add_argument("--no-index", action="store_true", help="Do not (re)generate index.html before serving")
    args = parser.parse_args()

    reports_dir = os.path.abspath(args.dir or default_reports_dir())
    if not os.path.isdir(reports_dir):
        print("ERROR: reports directory does not exist: %s" % reports_dir)
        sys.exit(1)

    if not args.no_index:
        build_index(reports_dir)
    QuietHandler.refresh_index = not args.no_index

    handler = lambda *a, **kw: QuietHandler(*a, directory=reports_dir, **kw)
    server = ThreadingHTTPServer((args.host, args.port), handler)

    print("Serving Klocwork reports from: %s" % reports_dir)
    print("Listening on %s:%d" % (args.host, args.port))
    urls = ["http://%s:%d/" % (ip, args.port) for ip in local_ips()] or ["http://<this-machine-ip>:%d/" % args.port]
    print("Share one of these URLs with other users on the network:")
    for url in urls:
        print("  %s" % url)
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
