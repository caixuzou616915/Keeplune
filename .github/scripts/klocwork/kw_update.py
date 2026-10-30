#!/usr/bin/env python3
"""
Klocwork Warning Update Helper
==============================
Wraps the Klocwork "update_status" REST API action for changing the
status/comment/owner of one or more warnings, e.g. the equivalent of:

  curl --data "action=update_status&user=myself&project=my_project&ids=ids_list \
&status=new_status&comment=new_comment&owner=new_owner" \
      https://<server>:<port>/review/api

Ids can be supplied directly, from a text file (one id per line), from a
CSV/txt export produced by kwequery.py / kw_export.py (any column whose
header contains "id", case-insensitive, e.g. "Id"), or from the JSON sidecar
file kw_export.py always writes alongside its csv/xml/txt output (a JSON
array of the full warning dicts) - the JSON form is preferred when both
exist since it's lossless (no delimiter-splitting ambiguity).

Examples
--------
  # Update a handful of ids directly
  python kw_update.py --url https://server:9898/my_project \\
      --ids 1023 1024 1025 --status "Fix" --comment "Confirmed defect" --owner jdoe

  # Update every id found in a previous export (csv or its .json sidecar)
  python kw_update.py --url https://server:9898/my_project \\
      --ids-file kw_export.json --status "Not a Problem" --comment "False positive"

  # Preview only, without sending the update
  python kw_update.py --url https://server:9898/my_project \\
      --ids-file ids.txt --status Ignore --dry-run

Auth: same as kwequery.py - uses ~/.klocwork/ltoken (or $KLOCWORK_LTOKEN) by
default; for modern Validate servers whose token is in the encrypted
tokens.jks keystore it falls back automatically to the `kwauth
--print-auth-info` CLI (locate kwauth via the KLOCWORK_KWAUTH env var or
PATH). Pass --ltoken/--user to supply one manually.

API note: the underlying Klocwork action is `update_status` (NOT `update`)
and the id parameter is `ids` (plural, comma-separated) - both `action=update`
and `id=<n>` are rejected by the server. Valid statuses: Analyze / Fix /
Defer / Ignore / 'Not a Problem'.
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kwequery  # noqa: E402  (local import, path adjusted above)
import kw_config  # noqa: E402  (local import, path adjusted above)

CONFIG = kw_config.load_config()
DEFAULT_URL = kw_config.get(CONFIG, "url")
DEFAULT_USER = kw_config.get(CONFIG, "user")


def _find_id_key(row):
    for k in row.keys():
        if k.lower() == "id":
            return k
    return None


def load_ids_from_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print("ERROR: %s is not a JSON array of warning objects" % path)
        sys.exit(1)
    ids = []
    for row in data:
        if not isinstance(row, dict):
            continue
        id_key = _find_id_key(row)
        if id_key is None:
            print("ERROR: Could not find an 'id' field in %s entries" % path)
            sys.exit(1)
        if row.get(id_key) not in (None, ""):
            ids.append(str(row[id_key]))
    return ids


def load_ids_from_file(path):
    if path.lower().endswith(".json"):
        return load_ids_from_json(path)
    ids = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        # Detect a delimited export (csv/tab) vs a plain one-id-per-line file.
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        if ";" in first_line:
            delim = ";"
        elif "," in first_line:
            delim = ","
        else:
            delim = None
        if delim:
            reader = csv.reader(f, delimiter=delim)
            rows = list(reader)
            if not rows:
                return ids
            header = [h.strip().lower() for h in rows[0]]
            id_col = next((i for i, h in enumerate(header) if "id" == h or h.endswith("id")), None)
            if id_col is None:
                print("ERROR: Could not find an 'id' column in %s (header: %s)" % (path, rows[0]))
                sys.exit(1)
            for row in rows[1:]:
                if len(row) > id_col and row[id_col].strip():
                    ids.append(row[id_col].strip())
        else:
            for line in f:
                line = line.strip()
                if line:
                    ids.append(line)
    return ids


def main():
    parser = argparse.ArgumentParser(
        prog="kw_update",
        description="Update status/comment/owner of one or more Klocwork warnings")
    parser.add_argument("-u", "--url", required=(DEFAULT_URL is None), default=DEFAULT_URL,
                        metavar="project url",
                        help="(mandatory unless 'url' is set in klocwork_config.json) "
                             "http[s]://<server>:<port>/<project>")
    parser.add_argument("--ids", nargs="+", default=None, metavar="id",
                        help="(one of --ids/--ids-file required) one or more Klocwork issue ids")
    parser.add_argument("--ids-file", nargs="?", default=None, metavar="path",
                        help="(one of --ids/--ids-file required) file with one id per line, "
                             "a kwequery/kw_export csv/txt export containing an 'id' column, "
                             "or a kw_export.py .json sidecar (preferred - lossless)")
    parser.add_argument("--status", required=True, metavar="new_status",
                        help="(mandatory) new status, e.g. Analyze / Fix / 'Not a Problem' / Ignore")
    parser.add_argument("--comment", nargs="?", default=None, metavar="new_comment",
                        help="(optional) new comment text")
    parser.add_argument("--owner", nargs="?", default=None, metavar="new_owner",
                        help="(optional) new owner user name")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="(optional) print what would be sent, without calling the server")
    parser.add_argument("-l", "--ltoken", nargs="?", default=None, metavar="ltoken key",
                        help="(optional, mandatory if --user is specified) Manually define the Klocwork ltoken key")
    parser.add_argument("--user", nargs="?", default=DEFAULT_USER, metavar="user name",
                        help="(optional) Required if manually defining ltoken key. Falls back to "
                             "klocwork_config.json's 'user' if set.")
    args = parser.parse_args()

    if not args.ids and not args.ids_file:
        print("ERROR: Provide --ids or --ids-file")
        sys.exit(1)
    if args.ltoken and not args.user:
        print("ERROR: When defining ltoken key the '--user' option is required")
        sys.exit(1)

    ids = list(args.ids) if args.ids else []
    if args.ids_file:
        ids.extend(load_ids_from_file(args.ids_file))
    # De-dup while preserving order.
    seen = set()
    ids = [i for i in ids if not (i in seen or seen.add(i))]
    if not ids:
        print("ERROR: No ids resolved to update")
        sys.exit(1)

    opts = {"ids": ",".join(ids), "status": args.status}
    if args.comment is not None:
        opts["comment"] = args.comment
    if args.owner is not None:
        opts["owner"] = args.owner

    print("INFO: %d id(s) to update: %s" % (len(ids), ",".join(ids)))
    print("INFO: status=%s comment=%s owner=%s" % (args.status, args.comment, args.owner))
    if args.dry_run:
        print("DRY-RUN: no request sent.")
        return

    kwdb = kwequery.KwConnection(args.url, args.ltoken, args.user)
    result = kwdb.search("update_status", None, opts)
    print("INFO: Server response: %s" % (result.strip() if result else "(empty)"))


if __name__ == "__main__":
    main()
