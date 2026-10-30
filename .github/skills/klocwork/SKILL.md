---
name: klocwork
description: >
  Klocwork server automation via the review/api REST endpoint: export warnings
  (by file/list of files, by severity, by module(s), or by an existing saved
  server-side filter/view), reproduce the UI's cumulative all-builds counts,
  bulk update warning status/comment/owner, and migrate triage state
  (status/comment/owner) for matching warnings from one Klocwork
  server+project to another. Also covers hosting the generated per-file
  triage reports (xlsx AI_Analysis -> Markdown -> HTML) over HTTP for
  multi-user/multi-PC review via serve_reports.py, including its Assigned
  To / Reviewed home-page columns and troubleshooting a stale duplicate
  server process. Use when: exporting Klocwork warnings for a
  given server/project to csv/xml; counting/exporting warnings for a module
  or module group; reproducing the web UI's cumulative (all-builds) warning
  counts; bulk-setting status/comment/owner on a set of warning ids; moving
  triage decisions from an old Klocwork server/project to a new one; hosting
  or reviewing generated Klocwork HTML reports as a team.
  Triggers: "export klocwork warnings", "klocwork module query", "klocwork
  view query", "all builds count", "update klocwork status", "klocwork
  update_status", "migrate klocwork warnings", "move klocwork comments to
  new server", "host klocwork reports", "serve klocwork reports", "klocwork
  home page".
metadata:
  author: "Zhao Jianbo"
  version: "1.9.0"
---

# Klocwork Toolkit (Export / Update / Migrate)

## MANDATORY: never run a full GTest build/execution just to get `compile_commands.json` (no exceptions)

`gen_standard_c.py --execute --clean` only needs a `compile_commands.json` **entry** (the
raw compiler invocation string) for the target `.c` file — it never touches built objects,
mocks, or test results. That means:

- **Never** run a module's full test harness/pipeline (`zz_run_GTest.bat`,
  `*_pf_testrunner.sh`, `run_gtf_menu.sh`, or anything that does conan install + cmake
  configure + build + execute tests) purely to obtain a `compile_commands.json` for
  triage. That pipeline can take a long time, and — for modules whose gtest
  `CMakeLists.txt` doesn't yet list the source file in `MUT_SRC_FILES` (i.e. no test
  infrastructure exists for it yet) — it won't even produce a compile command for the file
  you need, making the run pointless.
- **First choice**: search the repo for an already-generated `compile_commands.json` (a
  production `build/<variant>.Debug/compile_commands.json`, or one from a prior gtest
  build) and pass it to `gen_standard_c.py` via `--build-dir <path>` / `--json <path>`.
  Before relying on it, confirm the target file actually has an entry in it (grep/
  `Select-String` for the basename) — not every variant compiles every module.
- **If no existing `compile_commands.json` covers the file**: stop and ask the user which
  build/variant to use (or whether gtest infrastructure should be set up first via the
  `gtest-mock-creation`/`gtest-testcase-gen` skills) — do not fall back to running the
  full test-build-and-execute pipeline as a workaround just to unblock triage.
- Setting up a gtest harness (mocks, `MUT_SRC_FILES`, test cases) for a module is a
  separate, explicitly-requested unit-testing task (`gtest-mock-creation` /
  `gtest-testcase-gen` / `gtest-run-fix`) — never bundle it silently into a klocwork
  triage pass just to produce a clean file.

## MANDATORY: xlsx/csv triage clean-file rule (no exceptions)

When triaging exported warnings against source (the `klocwork_agent` xlsx/csv
workflow — verdict/comment/proposal/fix per warning), **generating**
`<basename>_clean.tmp` via `.github/scripts/gtest/gen_standard_c.py
<file>.c --execute --clean [--build-dir <path>]` is **not sufficient by
itself** — you must actually **open and read** the relevant section(s) of
that clean file (e.g. via `Select-String`/grep for the function name, macro,
or literal in question) as part of judging *every* warning for that file,
including ones that look "obviously" a false positive or already covered by
an in-source `[KW_IGNORE]` comment. Generating the file and then judging
purely from the raw `.c` source is exactly the mistake this rule exists to
prevent — the whole point is to resolve macro expansions, conflicting
`extern` prototypes (vendor/RTE/generated-header vs. project header vs.
definition), and true operand types, which are frequently invisible in the
raw source.

In this project many modules use an established `/*[KW_IGNORE][<CODE>]...*/`
inline-comment convention immediately before (occasionally immediately
after) the flagged line to record an already-reviewed, dated deviation. When
present, correlating a warning's `Line` to a matching `[KW_IGNORE][<code>]`
comment nearby (same function/statement block) is strong evidence for "Not
Critical / already justified in source" — but for anything that does NOT
have such a marker, or where the marker's checker code doesn't match, still
consult the clean file before deciding (do not rely on the raw source
alone). Only skip the clean-file read when the matched `[KW_IGNORE]` comment
is dated and its checker code is an exact match for the warning being
triaged.

### Known line-drift trap: stacked `[KW_IGNORE]` comments shift subsequent warnings' `Line`
This project's `[KW_IGNORE][CODE][date] reason` comments are always placed **immediately
above** the statement they justify. Whenever a fix or a new justification comment is
inserted above a line, every warning further down in the **same file** whose original
Klocwork `Line` pointed below that insertion point is now stale by exactly the number of
lines inserted — the export's `Line` no longer matches the current source.

`kw_report_tool.py report`'s code-snapshot generator (`_code_snapshot` / `_resolve_stale_line`)
auto-detects this: if a warning's `Line` lands on a comment/pragma/blank line, it
automatically advances to the next real statement and marks that instead (prepending a
`NOTE: ... auto-advanced ...` line to the snapshot so the adjustment is visible, not
silent). You do **not** need to manually pass `--line-shift`/`--line-override` just because
you added a KW_IGNORE comment or a fix above a warning's line earlier in the same
file-processing pass — only use those flags for cases the auto-detection can't resolve
(e.g. the drifted line still happens to land on real code, just the *wrong* code).

Symptom if this ever regresses: a generated report's code snapshot highlights (`>>`) a
`[KW_IGNORE]` comment line or a blank/pragma line instead of the actual flagged statement.
If you see that, re-check `_resolve_stale_line`/`MAX_STALE_LINE_ADVANCE` in
`kw_report_tool.py` rather than hand-waving the mismatch away — this happened in production
for `powmon1c1.c` warning id 708149 (`PowMon_DLTLOG_WarnUv` call): the report highlighted
line 339 (a `[KW_IGNORE]` comment) when the real call was several lines further down.

More generally: whenever a `Line` you're about to judge doesn't match its `Code`/`Message`
in the raw source, check a few lines **forward** (not just backward) for the real
construct before concluding Klocwork's data is wrong — line drift from earlier edits in the
same file is far more likely than a bad export.

## Overview

Three CLI scripts wrap the Klocwork `review/api` REST endpoint (the same API
`kwequery.py` already uses) for the most common warning-management tasks that
go beyond a one-off `search` query:

1. **Export** warnings by file(s), severity, module(s), and/or an existing
   saved view/filter — optionally cumulative across **all builds** —
   `kw_export.py`.
2. **Update** the status/comment/owner of one or more warning ids — the
   scripted equivalent of the Klocwork `update_status` curl call —
   `kw_update.py`.
3. **Migrate** triage state (status/comment/owner) for warnings that exist on
   both an old and a new Klocwork server+project — `kw_migrate.py`.

### Build scope: latest build vs all builds (IMPORTANT)

A Klocwork `search` **only sees the LATEST integration build by default** —
so a raw query typically returns far fewer warnings than the web UI shows.
The UI's large "cumulative" numbers come from its view selector being set to
**ALL** (all builds). To reproduce those numbers from the toolkit, pass
`--all-builds` (alias `--cumulative`) to `kw_export.py`: it applies the
server's built-in `ALL` view together with your query, so the query filters
*within* the all-builds scope.

| Search | Scope | Typical result |
|--------|-------|----------------|
| `--modules fsv_fsm ...` (no flag) | latest build | small |
| `--modules fsv_fsm ... --all-builds` | all builds | matches the UI |
| `--filter-view NAME` | all builds (views are always cumulative) | matches the UI |

Notes:
- `module:` values must be **unquoted** comma-separated (the script handles
  this) — quoting a module list silently disables the filter and returns
  every issue.
- `--all-builds` and `--filter-view` are mutually exclusive (both set the
  `view` parameter).
- The `Unexpected` severity appears only in the cumulative/all-builds scope,
  never in the latest build.

All three are thin wrappers around `kwequery.py`'s `KwConnection` class and
`parse_klocwork_ndjson()` response parser — they import `kwequery.py`
directly (no code duplication), so any auth/query-parsing fix made there
benefits all three scripts automatically.

The Klocwork server (and project) is **always supplied by the caller**
via `--url` / `--src-url` / `--dst-url` — never hardcoded in the scripts.

**`kw_export.py` always writes a JSON sidecar file** (same basename as
`--out`, `.json` extension) in addition to whatever `--format` was
requested for human review (csv/xml/txt). This is the recommended
machine-readable hand-off format for chaining into `kw_update.py`
(`--ids-file <name>.json`) or any other downstream script — it is lossless
(full field types/values), unlike parsing the `;`-delimited csv. Pass
`--no-json-sidecar` to `kw_export.py` to skip it if truly not needed.

**Default output location**: unless `--out` is given explicitly,
`kw_export.py` writes into `<repo_root>/ai_output/klocwork/kw_export.csv` —
anchored to the repository root (found via the nearest `.git` directory),
regardless of the current working directory the script is run from —
matching this repo's standard `ai_output/` artifacts convention used by the
other agents/scripts. The directory is created automatically if it doesn't
exist. Override with `"ai_output_dir"` in `klocwork_config.json` (see
"Configuration" below), or with `--out` for a one-off path.

**Auto-splitting large exports**: broad queries (e.g. a whole module-group
view across several severities) can return tens of thousands of warnings —
too many for one comfortable Excel/csv file. If the result has more rows
than `--max-per-file` (default **1000**, overridable via
`klocwork_config.json`'s `"max_warnings_per_file"`, or per-run with
`--max-per-file`), `kw_export.py` automatically splits the output into
numbered files instead of one giant one: `<basename>_part1.<ext>`,
`_part2.<ext>`, ... each holding at most `--max-per-file` warnings, each
with its own `.json` sidecar. Pass `--max-per-file 0` to force a single
file regardless of size. When the result fits within the limit, behaviour
is unchanged (a single `--out` file, no `_partN` suffix).

## Configuration

Non-secret defaults can be set once in
`.github/scripts/klocwork/klocwork_config.json` instead of repeating them on
every command line:

```json
{
  "url": "https://<server>:<port>/<project>",
  "user": "",
  "ai_output_dir": "",
  "severity": "",
  "ruleset": [],
  "max_warnings_per_file": 1000
}
```

Example, filled in:

```json
{
  "url": "https://kwserver01:8096/S3P_HUD_Project",
  "user": "uidc1098",
  "ai_output_dir": "ai_output/klocwork",
  "severity": "1-3",
  "ruleset": ["MISRA C 2012", "CERT C Rules"],
  "max_warnings_per_file": 1000
}
```

- `url` — default `--url` for `kw_export.py`/`kw_update.py` (leave `""` to
  keep requiring `--url` on the command line).
- `user` — default `--user` (only meaningful together with a manually
  supplied `--ltoken`).
- `ai_output_dir` — override where `kw_export.py` writes its default output
  (absolute, or relative to the repo root). Leave `""` for the default
  `<repo_root>/ai_output/klocwork`.
- `severity` — default `--severity` for `kw_export.py`, e.g. `"1-3"` (leave
  `""` to require `--severity` explicitly, or to omit it as a filter).
- `ruleset` — default `--ruleset` for `kw_export.py`: a JSON list of
  compliance ruleset/standard names (e.g. `["MISRA C 2012", "CERT C
  Rules"]`), or a single comma-separated string. Maps to the Klocwork
  `taxonomy:` query facet. Leave `[]`/`""` to omit it as a filter.
- `max_warnings_per_file` — default `--max-per-file` for `kw_export.py`:
  the row-count threshold above which the export is automatically split
  into numbered `_part1`/`_part2`/... files (see "Auto-splitting large
  exports" above). Leave `0`/unset to fall back to the script's built-in
  default (1000).

Any of these three, `--severity`/`--ruleset`/`--max-per-file`, given on the
command line always overrides the config-file default — so if a user's
prompt doesn't mention a severity, ruleset, or split threshold, the
config-file default (if set) is used automatically; if the user does
specify one, that takes precedence.

A CLI flag always overrides the config file value. **Never put an ltoken or
password in this file** — it is a plain, repo-committed JSON file; keep
using `~/.klocwork/ltoken` / `$KLOCWORK_LTOKEN` / `--ltoken` for
authentication. `kw_migrate.py` deliberately has no config-file defaults
since it always operates on two distinct servers (`--src-url`/`--dst-url`
must be given explicitly).

## Implementation Files

- `.github/scripts/klocwork/kwequery.py` — shared `KwConnection` client +
  `parse_klocwork_ndjson()` / `create_csv()` / `create_xml()` helpers, and the
  original general-purpose `search`/`metrics` query CLI.
- `.github/scripts/klocwork/kw_config.py` — shared config-file loader
  (`klocwork_config.json`) and repo-root resolution used by `kw_export.py`/
  `kw_update.py` to anchor `ai_output/` and resolve `--url`/`--user` defaults.
- `.github/scripts/klocwork/klocwork_config.json` — the user-editable settings
  file (see "Configuration" above).
- `.github/scripts/klocwork/kw_export.py` — export by file(s)/severity/module(s)/ruleset/filter, with optional `--all-builds` cumulative scope. Defaults `--out` to `<repo_root>/ai_output/klocwork/kw_export.csv`; `--severity`/`--ruleset`/`--max-per-file` can default from `klocwork_config.json`. Auto-splits into `_part1`/`_part2`/... files when the result exceeds `--max-per-file` (default 1000).
- `.github/scripts/klocwork/kw_update.py` — bulk status/comment/owner update.
- `.github/scripts/klocwork/kw_migrate.py` — cross-server/project migration.
- `.github/scripts/klocwork/test/test_kw_export.py` — offline `unittest` suite for
  `kw_export.py`'s query-building/validation/default-output-path logic and
  `kw_config.py`'s config-loading/repo-root logic (no live server needed).
  Run with `python -m unittest test_kw_export -v` from
  `.github/scripts/klocwork/test` after touching `kw_export.py`/`kw_config.py`.
- `.github/scripts/klocwork/kw_report_tool.py` — xlsx `AI_Analysis` sheet reader/writer + per-file Markdown report generator (`summary`/`list`/`write`/`report` subcommands), used by the `klocwork_agent` triage workflow.
- `.github/scripts/klocwork/kw_report_md_to_html.py` — converts one `kw_report_tool.py report` Markdown file into a single self-contained, styled HTML report with interactive Accept/Reject/comment controls per warning.
- `.github/scripts/klocwork/serve_reports.py` — hosts every generated `<basename>_report.html` in a directory over HTTP for the whole team (see "Hosting reports" below).
- `.github/scripts/klocwork/README.md` — quick-reference index of all
  the files in this folder, setup, and how to run the tests.
- `.github/scripts/klocwork/requirements.txt` — third-party Python
  packages needed by this toolkit (currently just `openpyxl`, used only by
  `kw_report_tool.py`). Install with `pip install -r requirements.txt`.

## Hosting reports (serve_reports.py)

Once `kw_report_tool.py report` + `kw_report_md_to_html.py` have produced one
`<basename>_report.html` per source file in a directory (typically
`ai_output/klocwork`), `serve_reports.py` hosts ALL of them from one running
instance so the whole team can browse/review them, instead of everyone
needing their own copy of the files:

```bash
python .github/scripts/klocwork/serve_reports.py \
    --dir ai_output/klocwork --port 9000
```

- `--dir` — directory to serve (default: `<repo_root>/ai_output/klocwork/reports`;
  pass the actual directory the reports live in if it's different, e.g. the
  flat `ai_output/klocwork` layout most of this repo's reports use).
- `--port` — default `8000`. Pick a port your team has agreed on and isn't
  already in use (see "Troubleshooting: stale duplicate server" below).
- `--host` — default `0.0.0.0` (all interfaces, reachable from other PCs on
  the network). Use `127.0.0.1` for a localhost-only instance.

It binds with `ThreadingHTTPServer` (concurrent requests from multiple
users/PCs at once) and has **no authentication** — only run it on a
trusted network.

### Home page (`index.html`)

Regenerated fresh on every request to `/`, so new/changed reports always
show up without restarting the server. Columns:

| Column | Source |
|---|---|
| No. | Row position (1-based), not persisted |
| Report | The `<basename>_report.html` filename, links to the report |
| Assigned To | Free-text, editable inline, saved via `/api/assign` |
| Total | Raw warning count for that file from the newest `*.xlsx` sitting in the same directory (main sheet, matched by substring on the file column) — `N/A` if no xlsx is found or it can't be read right now (locked/corrupt/openpyxl missing) |
| Critical / Not Critical | Parsed directly from that report's own HTML (`data-verdict` attributes) — does NOT need the xlsx |
| Reviewed | Count of rows where the Confirmed control was actually set to Accept/Reject — NOT the default "Blank (to be checked)" state. Server-persisted confirmations (`.confirmations.json`) take priority over whatever is baked into the static HTML |
| Last updated / Size | File mtime/size |

### Server-side persistence (survives refresh, restart, and is shared across every PC hitting this server)

- `.assignments.json` — `{report_filename: assignee_name}`, written by
  `POST /api/assign` `{report, assignee}` (empty `assignee` removes the key).
- `.confirmations.json` — `{report_filename: {row_id: {confirmed, user_comment}}}`,
  written by `POST /api/confirm` `{report, row, confirmed, user_comment}`
  (`confirmed` must be `""`/`"Yes"`/`"No"`). `GET /api/confirm?report=<name>`
  returns the saved map for one report (used by the report page's JS to
  restore state on load). Both endpoints validate `report` against the
  actual `.html` files in the served directory before writing, and both
  files are written atomically (tmp file + `os.replace`).

Both stores live as plain JSON files next to the reports themselves — back
them up / commit them if you want a durable audit trail beyond the xlsx.

### Report pages must have the sync JS to be reflected on the home page

A `<basename>_report.html` only pushes Accept/Reject/comment state to
`/api/confirm` if it was generated by a `kw_report_md_to_html.py` that
includes the `REPORT_NAME`/`pushServerState`/`fetchServerState` JS (added
after the initial report-hosting feature). If a report predates that change,
its reviewer clicks only ever land in that one browser's `localStorage` —
the home page's Reviewed count for it will stay stuck at 0 no matter how
many rows get reviewed. Fix: regenerate it —
`python kw_report_md_to_html.py <basename>_report.md` — the DOMContentLoaded
handler auto-pushes any pre-existing `localStorage` state to the server the
next time that page loads, so past review work isn't lost. When bulk-fixing
an old set of reports, regenerate every `*_report.md` → `.html` in one pass
rather than one at a time.

### Troubleshooting: stale duplicate server process (Windows)

`HTTPServer.allow_reuse_address` is on, and Windows will happily let a
second `serve_reports.py` bind the same port without erroring even while an
older one is still alive — but only ONE of them actually receives traffic,
and it's not necessarily the newest. Symptom: you restart the server after
an edit, it prints "Listening on 0.0.0.0:<port>" with no error, but
behavior still matches the OLD code (e.g. a new endpoint 404s, or data never
persists) — because requests are actually still going to a leftover process
from a previous session that was never truly killed (only its terminal
wrapper was).

Diagnose and fix:

```powershell
# Find every python process, not just the one you think is running
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Select-Object ProcessId, CreationDate, CommandLine

# Which PID is the OS actually routing <port> traffic to right now
Get-NetTCPConnection -LocalPort <port> -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess

# Kill every serve_reports.py process (not just one), then relaunch a single fresh instance
Stop-Process -Id <id1>,<id2>,... -Force
```

Always cross-check `Get-NetTCPConnection`'s `OwningProcess` against every
`serve_reports.py` PID from `Win32_Process` before trusting that a restart
actually took effect — a clean "Listening on ..." printout is NOT proof the
newest process is the one serving requests.

## Prerequisites

- Python 3. Every script except `kw_report_tool.py` is stdlib only
  (`argparse`, `csv`, `json`, `urllib`, `re`). `kw_report_tool.py` (the xlsx
  reader/writer) additionally needs `openpyxl` — install via
  `pip install -r .github/scripts/klocwork/requirements.txt`.
- A valid Klocwork ltoken for each server involved. By default this is read
  from `~/.klocwork/ltoken` (or `$KLOCWORK_LTOKEN`), keyed per `server;port`
  line — the same file `kwauth --url <server>` populates. Pass `--ltoken`
  (with `--user`) to override manually for a single-server script, or
  `--src-ltoken`/`--src-user` + `--dst-ltoken`/`--dst-user` for `kw_migrate.py`.
- **Modern Validate servers (auth keystore fallback):** newer
  Validate/Klocwork servers store the token in an encrypted `tokens.jks`
  keystore (referenced by `~/.klocwork/credentials`) instead of the
  plain-text `~/.klocwork/ltoken` file, so the plain-file scan finds nothing
  and you'd otherwise get `ERROR: No Klocwork token found`. In that case the
  toolkit now **automatically falls back to the `kwauth` CLI**
  (`kwauth --url <server> --print-auth-info`) to read the token from the
  keystore — no manual token extraction needed. `kwauth` is located via the
  `KLOCWORK_KWAUTH` env var (set it to the full path of `kwauth`/`kwauth.exe`,
  e.g. `D:\tool\...\Server_24.4\bin\kwauth.exe`), otherwise plain `kwauth`
  must be on `PATH`. You still run `kwauth --url <server>` (entering your
  password) once to populate the keystore; after that the scripts reuse it
  non-interactively. Passing `--ltoken` explicitly always skips this fallback.

## Usage

### 1. Export warnings

```bash
# By one or more files (writes to <repo_root>/ai_output/klocwork/kw_export.csv by default)
python kw_export.py --url https://<server>:<port>/<project> \
    --files foo.c bar.c

# By severity, explicit output path
python kw_export.py --url https://<server>:<port>/<project> \
    --severity 1-3 --out sev1-3.csv

# By one or more modules (latest build)
python kw_export.py --url https://<server>:<port>/<project> \
    --modules fsv_fsm ismd_fsm --out fsm.csv

# Module group, cumulative across ALL builds (reproduces the UI count)
python kw_export.py --url https://<server>:<port>/<project> \
    --modules fsv_fsm ismd_fsm vsgen_fsm --all-builds \
    --extra-query "status:+'Analyze'" --out fsm_analyze.csv

# By an existing saved view/filter on the server (always cumulative)
python kw_export.py --url https://<server>:<port>/<project> \
    --filter-view "MyReviewedView" --out review.csv

# By one or more compliance rulesets/standards (taxonomy: facet)
python kw_export.py --url https://<server>:<port>/<project> \
    --ruleset "MISRA C 2012" "CERT C Rules" --out misra.csv

# Combine + raw passthrough query fragment, xml output
python kw_export.py --url https://<server>:<port>/<project> \
    --files foo.c --severity 1-3 --extra-query "status:Analyze" \
    --format xml --out out.xml
# -> also writes out.json (same records, structured, for downstream scripts)

# If 'severity'/'ruleset' are set in klocwork_config.json, they're used
# automatically when not passed on the command line:
python kw_export.py --url https://<server>:<port>/<project> --modules fsv_fsm

# A large view/severity range, auto-split into <=1000-warning files
# (s3p_modules_sev1-4_part1.csv, _part2.csv, ...) - matches the web UI's
# "S3P_Modules" view filtered to severity 1 (Critical) through 4
# (Recommendation)
python kw_export.py --url https://<server>:<port>/<project> \
    --filter-view "S3P_Modules" --severity 1-4 \
    --out s3p_modules_sev1-4.csv --max-per-file 1000
```

`--files` values are ORed together (`file:'a.c,b.c'`); `--modules` values are
ORed together (`module:a,b` — unquoted); `--ruleset` values are ORed
together (`taxonomy:+'a',+'b'`); combining `--files`, `--severity`,
`--modules`, `--ruleset`, `--filter-view`, `--extra-query` ANDs each piece
together. At least one of these (or `--all-builds`) must be given — or a
default `severity`/`ruleset` from `klocwork_config.json`. Add `--all-builds`
(alias `--cumulative`) to search across all builds instead of only the
latest — this reproduces the web UI's cumulative counts (mutually exclusive
with `--filter-view`, which is already cumulative). Every run also writes a
`.json` sidecar next to `--out` unless `--no-json-sidecar` is passed.

### 2. Update status / comment / owner

Equivalent of:
```
curl --data "action=update_status&user=myself&project=my_project&ids=ids_list&status=new_status&comment=new_comment&owner=new_owner" https://<server>:<port>/review/api
```

```bash
# Explicit ids
python kw_update.py --url https://<server>:<port>/<project> \
    --ids 1023 1024 1025 --status "Fix" --comment "Confirmed defect" --owner jdoe

# Ids sourced from a file (one per line), a prior kwequery.py csv (any "id" column),
# or (preferred - lossless) the .json sidecar kw_export.py always writes
python kw_update.py --url https://<server>:<port>/<project> \
    --ids-file kw_export.json --status "Not a Problem" --comment "False positive"

# Dry run - print what would be sent, no request made
python kw_update.py --url https://<server>:<port>/<project> \
    --ids-file ids.txt --status Ignore --dry-run
```

`--status` is mandatory; `--comment`/`--owner` are optional. Always run with
`--dry-run` first when applying to a large id set to confirm scope.

> **API note:** the Klocwork action is `update_status` (not `update`), and the
> id parameter is `ids` (plural, comma-separated) — `id=<n>` is rejected with
> `400 Required parameter 'ids' not specified`, and `action=update` is rejected
> with `400 ... no such action`. A successful call returns
> `{"status_message":"N issue(s) successfully updated."}`. `kw_update.py`
> handles all of this for you. Valid `--status` values: `Analyze`, `Fix`,
> `Defer`, `Ignore`, `Not a Problem`.

### 3. Migrate warnings between servers

```bash
python kw_migrate.py \
    --src-url https://old-server:9898/my_project \
    --dst-url https://new-server:9898/my_project \
    --query "status:Analyze,Fix,'Not a Problem',Ignore" \
    --dry-run
```

Review the printed match/unmatched/ambiguous report, then re-run without
`--dry-run` to actually push the `update_status` calls to the destination
server.

## Workflow

### Step 1 -- Confirm target server(s) and scope with the user

Never assume a Klocwork server/project — always get `--url` (or
`--src-url`/`--dst-url`) explicitly from the user. For export, confirm which
of file(s)/severity/module(s)/filter-view the user wants (or a combination),
and whether they need the latest build only (default) or `--all-builds` for
cumulative UI-matching counts.

### Step 2 -- Export or update, always dry-run destructive changes first

For `kw_update.py` and `kw_migrate.py`, run with `--dry-run` first, show the
user the exact ids/warnings and new status/comment/owner that will be
applied, and only re-run without `--dry-run` after the user confirms — status
changes and comments on a shared Klocwork server are visible to the whole
team and are not easily reversible.

### Step 3 -- Migration matching strategy

`kw_migrate.py` matches warnings between servers by a composite key (default
`file,method,code` — file path, enclosing function/method, checker id), NOT
by id (ids are never stable across servers/projects). If the match report
shows many "ambiguous" or "unmatched" entries, narrow or widen
`--match-fields` (comma-separated field names, case-insensitive) rather than
guessing — e.g. add `line` if two warnings in the same function collide, or
drop `method` if the destination server didn't compute it identically.

### Step 4 -- Report back

Summarize: how many warnings were exported / how many ids updated / how many
matched-migrated vs skipped (no source state) vs unmatched vs ambiguous, and
the output file path(s).

## Outputs

- `kw_export.py`: a csv/xml/txt/json file at `--out` (default
  `<repo_root>/ai_output/klocwork/kw_export.csv`, directory created automatically),
  one row/element per warning with whatever fields the server returned, PLUS
  a `.json` sidecar file (same basename, always written unless
  `--no-json-sidecar`) for lossless consumption by other scripts.
- `kw_update.py`: prints the ids updated and the raw server response; exits
  non-zero on auth/HTTP errors (same behaviour as `kwequery.py`).
- `kw_migrate.py`: prints a migration plan (matched/unmatched/ambiguous
  counts + per-warning detail) and, unless `--dry-run`, applies
  `update_status` to each matched destination warning, then prints an
  updated/failed count.

## Resources

- `.github/scripts/klocwork/kwequery.py`
- `.github/scripts/klocwork/kw_config.py` (shared config loader)
- `.github/scripts/klocwork/klocwork_config.json` (user-editable settings)
- `.github/scripts/klocwork/kw_export.py`
- `.github/scripts/klocwork/kw_update.py`
- `.github/scripts/klocwork/kw_migrate.py`
- `.github/scripts/klocwork/test/test_kw_export.py` (offline unit tests, no server needed)
- `.github/scripts/klocwork/kw_report_tool.py` / `kw_report_md_to_html.py`
  (separate xlsx-triage workflow used by the `klocwork_agent`)
- `.github/scripts/klocwork/serve_reports.py` (hosts the generated
  reports; see "Hosting reports" above)

### Proposal field convention (xlsx triage `AI_Analysis` sheet)

When `kw_report_tool.py write` records a "Not Critical" verdict because the
warning is already covered by an existing inline deviation comment in the
source (a `[KW_IGNORE][...]` tag or equivalent justification right
above/near the flagged line), the `proposal` field should quote or
paraphrase that EXACT existing comment rather than a generic "No change
needed; existing inline justification is sufficient." placeholder — the
report should show the reviewer *why* it's justified, not just that it is.
Always re-verify the comment still accurately describes the current code
before reusing it: if it's stale, incorrect, or no longer matches the
source (e.g. after a refactor), correct the proposal text and, if
warranted, fix the comment in the source file itself rather than copying
a wrong justification forward.
