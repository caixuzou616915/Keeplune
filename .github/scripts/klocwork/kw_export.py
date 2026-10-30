#!/usr/bin/env python3
"""
Klocwork Warning Export Helper
==============================
Friendly wrapper around kwequery.py's Klocwork REST API client for the
export use-cases requested most often:

  1. Export warnings for one file, or a list of files.
  2. Export warnings by severity (e.g. "1-3" or "1,2,4").
  3. Export warnings using an existing saved server-side filter/view.
  4. Export warnings for one or more modules (Klocwork module: predicate).

Any combination of the above can be ANDed together, plus an optional raw
query fragment for anything not covered by the flags. The Klocwork server
and project are always supplied by the caller via --url (never hardcoded).

Output location
----------------
Unless --out is given explicitly, output is written under the repo's
standard `ai_output/` artifacts folder at the REPOSITORY ROOT
(`<repo_root>/ai_output/klocwork/kw_export.csv`), matching the convention
used by the other agents/scripts in this repo - anchored to the repo root
(found via the nearest `.git` directory) regardless of the current working
directory the script is invoked from. The directory is created
automatically if it doesn't exist yet. Override with "ai_output_dir" in
klocwork_config.json, or with --out for a one-off path.

Configuration
-------------
Non-secret defaults (server --url, --user, ai_output_dir, severity, ruleset)
can be set once in `klocwork_config.json` next to this script, instead of
repeating them on every command line. See kw_config.py's docstring for the
recognised keys. A CLI flag always overrides its config-file default.
Never put an ltoken/password value in that file.

Build scope
-----------
By default a Klocwork `search` only sees the LATEST integration build. To
reproduce the cumulative, all-builds counts shown in the Klocwork web UI
(when the view selector is set to "ALL"), pass --all-builds: it applies the
server's built-in "ALL" view together with your query, so the query filters
within the all-builds scope. This is how UI numbers like "1234 warnings for
the functional-safety modules" are reproduced. --all-builds cannot be
combined with --filter-view (both set the view parameter).

In addition to the requested --format (csv/xml/txt/json), a JSON sidecar
file is ALWAYS written next to --out (same basename, ".json" extension,
skipped only if --format json already targets that same path). This gives
kw_update.py / kw_migrate.py / any other downstream script a lossless,
structured file to consume regardless of which human-readable format was
requested - the csv/xml/txt outputs remain for people to read/review.

Auto-splitting large exports
-----------------------------
If an export returns more warnings than --max-per-file (default 1000,
overridable via klocwork_config.json's "max_warnings_per_file", or per-run
with --max-per-file), the output is automatically split into multiple
numbered files instead of one large one: <basename>_part1.<ext>,
_part2.<ext>, ... each holding at most --max-per-file warnings (plus its
own JSON sidecar). This keeps large views (e.g. a whole module group across
all severities) manageable to open/review in Excel. Pass --max-per-file 0
to force a single file regardless of size.

Examples
--------
  # All severity 1-3 warnings for two files (writes to ai_output/klocwork/)
  python kw_export.py --url https://server:9898/my_project \\
      --files foo.c bar.c --severity 1-3
  # -> ai_output/klocwork/kw_export.csv + ai_output/klocwork/kw_export.json

  # Warnings matching an existing saved view/filter on the server
  python kw_export.py --url https://server:9898/my_project \\
      --filter-view "MyReviewedView" --out review.csv

  # All Analyze warnings for a set of modules, cumulative across ALL builds
  # (reproduces the Klocwork UI number for those modules)
  python kw_export.py --url https://server:9898/my_project \\
      --modules fsv_fsm ismd_fsm --all-builds \\
      --extra-query "status:Analyze" --out fsm_analyze.csv

  # Raw query passthrough (anything kwequery.py's --query would accept)
  python kw_export.py --url https://server:9898/my_project \\
      --extra-query "status:Analyze" --format xml --out out.xml

  # Ask for JSON directly as the primary output
  python kw_export.py --url https://server:9898/my_project \\
      --severity 1-3 --format json --out out.json

  # Warnings matching one or more compliance rulesets/standards (taxonomy:)
  python kw_export.py --url https://server:9898/my_project \\
      --ruleset "MISRA C 2012" "CERT C Rules" --out misra.csv

  # If 'severity'/'ruleset' are set in klocwork_config.json, you can omit
  # them entirely and just supply the scope you want:
  python kw_export.py --url https://server:9898/my_project --modules fsv_fsm

  # A large view split into <=1000-warning chunks (kw_export_part1.csv, ...)
  python kw_export.py --url https://server:9898/my_project \\
      --filter-view "S3P_Modules" --severity 1-4 --max-per-file 1000

Auth: same as kwequery.py - uses ~/.klocwork/ltoken (or $KLOCWORK_LTOKEN) by
default; pass --ltoken/--user to supply one manually.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kwequery  # noqa: E402  (local import, path adjusted above)
import kw_config  # noqa: E402  (local import, path adjusted above)

CONFIG = kw_config.load_config()
DEFAULT_OUT_DIR = kw_config.default_ai_output_dir(CONFIG)
DEFAULT_OUT = os.path.join(DEFAULT_OUT_DIR, "kw_export.csv")
DEFAULT_URL = kw_config.get(CONFIG, "url")
DEFAULT_USER = kw_config.get(CONFIG, "user")
DEFAULT_SEVERITY = kw_config.get(CONFIG, "severity")
DEFAULT_RULESET = kw_config.get_list(CONFIG, "ruleset")
DEFAULT_MAX_PER_FILE = kw_config.get_int(CONFIG, "max_warnings_per_file", 1000)


def build_query(args):
    parts = []
    if args.severity:
        parts.append("severity:%s" % args.severity)
    if args.files:
        # Klocwork query syntax: multiple comma-separated values for one facet = OR.
        parts.append("file:'%s'" % ",".join(args.files))
    if args.modules:
        # module: values must be UNQUOTED comma-separated (module:a,b). Unlike
        # file:'a,b', quoting the module list ('a,b') silently disables the
        # filter and returns every issue - so never quote module values.
        parts.append("module:%s" % ",".join(args.modules))
    if args.ruleset:
        # taxonomy: (compliance ruleset/standard, e.g. "MISRA C 2012") - each
        # value quoted and '+'-prefixed, comma-joined for an OR match.
        parts.append("taxonomy:%s" % ",".join("+'%s'" % r for r in args.ruleset))
    if args.extra_query:
        parts.append(args.extra_query)
    return " ".join(parts)


def json_sidecar_path(out_path):
    return os.path.splitext(out_path)[0] + ".json"


def validate_args(args):
    """Pure validation of parsed args. Returns an error message string if
    invalid, or None if OK. Kept separate from main() so it's unit-testable
    without needing a live server or triggering sys.exit."""
    if args.format not in ("xml", "csv", "txt", "json"):
        return "Invalid format specified (xml/csv/txt/json): %s" % args.format
    if not args.url:
        return ("Provide --url, or set a default 'url' in klocwork_config.json")
    if args.ltoken and not args.user:
        return "When defining ltoken key the '--user' option is required"
    if args.all_builds and args.filter_view:
        return "--all-builds and --filter-view cannot be combined (both set the view parameter)"
    if args.max_per_file < 0:
        return "--max-per-file must be >= 0 (0 disables splitting)"
    if not (args.files or args.severity or args.modules or args.filter_view
            or args.ruleset or args.extra_query or args.all_builds):
        return ("Provide at least one of --files / --severity / --modules / "
                "--ruleset / --filter-view / --extra-query / --all-builds")
    return None


def build_opts(args):
    """Resolve the 'opts' dict (view=...) passed to KwConnection.search()."""
    if args.filter_view:
        return {"view": args.filter_view}
    if args.all_builds:
        # The built-in 'ALL' view supplies all-builds scope; the query filters within it.
        return {"view": "ALL"}
    return None


def ensure_parent_dir(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)


def chunk_list(items, size):
    """Yield successive `size`-sized chunks from `items`. `size` must be > 0."""
    for i in range(0, len(items), size):
        yield items[i:i + size]


def part_path(out_path, part_num):
    """Insert '_partN' before the extension: 'out.csv' -> 'out_part1.csv'."""
    base, ext = os.path.splitext(out_path)
    return "%s_part%d%s" % (base, part_num, ext)


def format_output(result_dict, fmt):
    if fmt == "json":
        return json.dumps(result_dict, indent=2)
    elif fmt == "xml":
        return kwequery.create_xml(result_dict)
    else:
        return kwequery.create_csv(result_dict)


def write_export(result_dict, out_path, fmt, write_json_sidecar):
    """Write one primary output file (+ optional JSON sidecar) for a single
    chunk of warnings. Returns the primary output path."""
    ensure_parent_dir(out_path)
    out_file = kwequery.open_file(out_path, "w")
    out_file.write(format_output(result_dict, fmt))
    out_file.close()
    print("INFO: %d warning(s) written to %s" % (len(result_dict), out_path))

    if write_json_sidecar:
        sidecar = json_sidecar_path(out_path)
        if fmt == "json" and os.path.abspath(sidecar) == os.path.abspath(out_path):
            pass  # primary output already IS the json sidecar - no duplicate write
        else:
            ensure_parent_dir(sidecar)
            sidecar_file = kwequery.open_file(sidecar, "w")
            sidecar_file.write(json.dumps(result_dict, indent=2))
            sidecar_file.close()
            print("INFO: JSON sidecar written to %s (for use by kw_update.py/kw_migrate.py/etc.)" % sidecar)
    return out_path


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="kw_export",
        description="Export Klocwork warnings by file(s), severity, module(s), and/or an existing saved filter/view")
    parser.add_argument("-u", "--url", required=(DEFAULT_URL is None), default=DEFAULT_URL,
                        metavar="project url",
                        help="(mandatory unless 'url' is set in klocwork_config.json) "
                             "http[s]://<server>:<port>/<project>")
    parser.add_argument("--files", nargs="+", default=None, metavar="file",
                        help="(optional) one or more file names/substrings to filter by")
    parser.add_argument("--severity", nargs="?", default=DEFAULT_SEVERITY, metavar="severity",
                        help="(optional) e.g. '1-3' or '1,2,4'. Falls back to klocwork_config.json's "
                             "'severity' if set%s" % (" (default: %s)" % DEFAULT_SEVERITY if DEFAULT_SEVERITY else ""))
    parser.add_argument("--modules", nargs="+", default=None, metavar="module",
                        help="(optional) one or more Klocwork module names to filter by (module: predicate)")
    parser.add_argument("--ruleset", nargs="+", default=DEFAULT_RULESET or None, metavar="ruleset",
                        help="(optional) one or more compliance ruleset/standard names (Klocwork "
                             "'taxonomy:' facet), e.g. --ruleset \"MISRA C 2012\" \"CERT C Rules\". "
                             "Falls back to klocwork_config.json's 'ruleset' if set%s"
                             % (" (default: %s)" % DEFAULT_RULESET if DEFAULT_RULESET else ""))
    parser.add_argument("--filter-view", nargs="?", default=None, metavar="view name",
                        help="(optional) name of an existing saved Klocwork view/filter on the server")
    parser.add_argument("--all-builds", "--cumulative", action="store_true", default=False,
                        dest="all_builds",
                        help="(optional) search cumulatively across ALL builds (via the built-in 'ALL' "
                             "view) instead of only the latest build - reproduces the UI's cumulative "
                             "counts. Cannot be combined with --filter-view.")
    parser.add_argument("--extra-query", nargs="?", default=None, metavar="query",
                        help="(optional) additional raw Klocwork query fragment, ANDed with the rest")
    parser.add_argument("-f", "--format", nargs="?", default="csv", metavar="format",
                        help="(optional) Output format 'xml'/'csv'(default)/'txt'/'json'")
    parser.add_argument("-o", "--out", nargs="?", default=DEFAULT_OUT,
                        metavar="output",
                        help="(optional) output file. Default is %s (created automatically)" % DEFAULT_OUT)
    parser.add_argument("--no-json-sidecar", action="store_true", default=False,
                        help="(optional) skip writing the always-on JSON sidecar file")
    parser.add_argument("--max-per-file", type=int, default=DEFAULT_MAX_PER_FILE, metavar="count",
                        help="(optional) when the export has more than this many warnings, split "
                             "the output into multiple numbered files (<basename>_part1.<ext>, "
                             "_part2, ...) of at most this many warnings each, instead of one large "
                             "file. Falls back to klocwork_config.json's 'max_warnings_per_file' if "
                             "set (default: %d). Use 0 to disable splitting entirely." % DEFAULT_MAX_PER_FILE)
    parser.add_argument("-l", "--ltoken", nargs="?", default=None, metavar="ltoken key",
                        help="(optional, mandatory if --user is specified) Manually define the Klocwork ltoken key")
    parser.add_argument("--user", nargs="?", default=DEFAULT_USER, metavar="user name",
                        help="(optional) Required if manually defining ltoken key. Falls back to "
                             "klocwork_config.json's 'user' if set.")
    return parser


def main():
    args = build_arg_parser().parse_args()

    error = validate_args(args)
    if error:
        print("ERROR: %s" % error)
        sys.exit(1)

    query = build_query(args)
    opts = build_opts(args)

    kwdb = kwequery.KwConnection(args.url, args.ltoken, args.user)
    result = kwdb.search("search", query if query else None, opts)
    result_dict = kwequery.parse_klocwork_ndjson(result)
    if not result_dict:
        print("INFO: No Records Found")
        sys.exit(0)

    total = len(result_dict)
    write_json_sidecar = not args.no_json_sidecar
    if args.max_per_file and total > args.max_per_file:
        chunks = list(chunk_list(result_dict, args.max_per_file))
        print("INFO: %d warning(s) exceed --max-per-file (%d) - splitting into %d file(s)"
              % (total, args.max_per_file, len(chunks)))
        for i, chunk in enumerate(chunks, start=1):
            write_export(chunk, part_path(args.out, i), args.format, write_json_sidecar)
    else:
        write_export(result_dict, args.out, args.format, write_json_sidecar)


if __name__ == "__main__":
    main()
