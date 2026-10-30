#!/usr/bin/env python3
"""
Klocwork Warning Migration Helper
=================================
Migrates warning triage state (status / comment / owner) from one Klocwork
server+project to another, for warnings that represent the "same" underlying
issue on both sides (e.g. moving a project between two Klocwork servers, or
re-triaging after a project was re-created/renamed on a new server).

Since issue ids are assigned per-server and are NOT stable across servers,
warnings are matched between source and destination by a composite key built
from a configurable set of fields (default: file, method, code - i.e. the
file path, enclosing function/method, and checker id). Only source warnings
whose key matches exactly one destination warning are migrated; ambiguous
(matches > 1) or unmatched warnings are reported, never guessed at.

This never touches ids/warnings that don't have a match, and --dry-run lets
you review the full match/unmatched report before sending any update_status
calls to the destination server.

Example
-------
  python kw_migrate.py \\
      --src-url https://old-server:9898/my_project \\
      --dst-url https://new-server:9898/my_project \\
      --query "status:Analyze,Fix,'Not a Problem',Ignore" \\
      --dry-run

  # after reviewing the dry-run report, re-run without --dry-run to apply
  python kw_migrate.py \\
      --src-url https://old-server:9898/my_project \\
      --dst-url https://new-server:9898/my_project

Auth: each server can have its own ltoken entry in ~/.klocwork/ltoken (this is
the normal case - kwauth keys entries by server:port). Use --src-ltoken/--src-user
and --dst-ltoken/--dst-user only if you need to override that for either side.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kwequery  # noqa: E402  (local import, path adjusted above)

DEFAULT_MATCH_FIELDS = ["file", "method", "code"]


def find_field(row, wanted):
    """Case-insensitive lookup of a field name in one issue's dict (server
    field naming/casing can vary between 'file'/'File', 'method'/'Method')."""
    wanted_l = wanted.lower()
    for k in row.keys():
        if k.lower() == wanted_l:
            return row.get(k)
    return None


def find_id(row):
    for candidate in ("id", "Id", "ID"):
        if candidate in row:
            return row[candidate]
    for k in row.keys():
        if k.lower() == "id":
            return row[k]
    return None


def build_key(row, match_fields):
    return tuple(str(find_field(row, f) or "").strip() for f in match_fields)


def fetch_issues(url, ltoken, user, query):
    kwdb = kwequery.KwConnection(url, ltoken, user)
    result = kwdb.search("search", query if query else None, None)
    return kwdb, kwequery.parse_klocwork_ndjson(result)


def main():
    parser = argparse.ArgumentParser(
        prog="kw_migrate",
        description="Migrate Klocwork warning status/comment/owner from one server+project to another")
    parser.add_argument("--src-url", required=True, metavar="src project url",
                        help="(mandatory) http[s]://<server>:<port>/<project> to migrate FROM")
    parser.add_argument("--dst-url", required=True, metavar="dst project url",
                        help="(mandatory) http[s]://<server>:<port>/<project> to migrate TO")
    parser.add_argument("--query", nargs="?", default=None, metavar="query",
                        help="(optional) Klocwork query to limit which source warnings are considered, "
                             "e.g. \"status:Analyze,Fix,'Not a Problem',Ignore\"")
    parser.add_argument("--match-fields", nargs="?", default=",".join(DEFAULT_MATCH_FIELDS), metavar="f1,f2,...",
                        help="(optional) comma-separated field names used to match a warning between "
                             "servers. Default: %s" % ",".join(DEFAULT_MATCH_FIELDS))
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="(optional) report matches/unmatched/ambiguous only, do not call update_status")
    parser.add_argument("--src-ltoken", nargs="?", default=None, metavar="ltoken key")
    parser.add_argument("--src-user", nargs="?", default=None, metavar="user name")
    parser.add_argument("--dst-ltoken", nargs="?", default=None, metavar="ltoken key")
    parser.add_argument("--dst-user", nargs="?", default=None, metavar="user name")
    args = parser.parse_args()

    if (args.src_ltoken and not args.src_user) or (args.dst_ltoken and not args.dst_user):
        print("ERROR: When defining ltoken key the matching '--src-user'/'--dst-user' option is required")
        sys.exit(1)

    match_fields = [f.strip() for f in args.match_fields.split(",") if f.strip()]
    if not match_fields:
        print("ERROR: --match-fields resolved to an empty field list")
        sys.exit(1)

    print("INFO: Fetching source warnings from %s ..." % args.src_url)
    _, src_issues = fetch_issues(args.src_url, args.src_ltoken, args.src_user, args.query)
    print("INFO: %d source warning(s) fetched" % len(src_issues))

    print("INFO: Fetching destination warnings from %s ..." % args.dst_url)
    dst_kwdb, dst_issues = fetch_issues(args.dst_url, args.dst_ltoken, args.dst_user, None)
    print("INFO: %d destination warning(s) fetched" % len(dst_issues))

    dst_index = {}
    for row in dst_issues:
        key = build_key(row, match_fields)
        dst_index.setdefault(key, []).append(row)

    matched, unmatched, ambiguous, skipped_no_state = [], [], [], []
    for src in src_issues:
        status = find_field(src, "status")
        comment = find_field(src, "comment")
        owner = find_field(src, "owner")
        if not status and not comment and not owner:
            skipped_no_state.append(src)
            continue
        key = build_key(src, match_fields)
        candidates = dst_index.get(key, [])
        if len(candidates) == 1:
            matched.append((src, candidates[0], status, comment, owner))
        elif len(candidates) == 0:
            unmatched.append(src)
        else:
            ambiguous.append((src, candidates))

    print("\n=== Migration Plan ===")
    print("Match fields: %s" % ",".join(match_fields))
    print("To migrate (matched 1:1): %d" % len(matched))
    print("No triage state on source (skipped): %d" % len(skipped_no_state))
    print("No destination match found: %d" % len(unmatched))
    print("Ambiguous (>1 destination match): %d" % len(ambiguous))

    if unmatched:
        print("\n-- Unmatched source warnings (no equivalent found on destination) --")
        for src in unmatched:
            print("  src_id=%s key=%s" % (find_id(src), build_key(src, match_fields)))
    if ambiguous:
        print("\n-- Ambiguous source warnings (skipped, need a narrower --match-fields) --")
        for src, candidates in ambiguous:
            dst_ids = [find_id(c) for c in candidates]
            print("  src_id=%s key=%s -> dst_ids=%s" % (find_id(src), build_key(src, match_fields), dst_ids))

    if not matched:
        print("\nINFO: Nothing to migrate.")
        return

    print("\n-- Matched warnings to migrate --")
    for src, dst, status, comment, owner in matched:
        print("  src_id=%s -> dst_id=%s  status=%s comment=%s owner=%s"
              % (find_id(src), find_id(dst), status, comment, owner))

    if args.dry_run:
        print("\nDRY-RUN: no update_status request sent.")
        return

    print("\nINFO: Applying %d update(s) to %s ..." % (len(matched), args.dst_url))
    ok, failed = 0, 0
    for src, dst, status, comment, owner in matched:
        opts = {"ids": str(find_id(dst)), "status": status}
        if comment:
            opts["comment"] = comment
        if owner:
            opts["owner"] = owner
        try:
            dst_kwdb.search("update_status", None, opts)
            ok += 1
        except SystemExit:
            failed += 1
            print("  ERROR: failed to update dst_id=%s (src_id=%s)" % (find_id(dst), find_id(src)))
    print("\nINFO: Migration complete: %d updated, %d failed." % (ok, failed))


if __name__ == "__main__":
    main()
