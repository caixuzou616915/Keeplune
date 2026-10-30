#!/usr/bin/env python3
"""
Sync repo-tool manifest revision pins (default.xml, platform.xml, ...) to the
actual current HEAD commit of each project's local git checkout.

For every <project name="..." path="..." remote="..." revision="..."/> entry in
the given manifest file(s), this script:
  1. Resolves the project's clone URL (remote fetch url + project name) and
     matches it against the local checkout at <root>/<path>, so entries that
     merely share the same `path` (e.g. overlaid/unused manifest fragments)
     are never touched.
  2. Skips projects with no matching local checkout.
  3. Reads the local HEAD commit and compares it to the pinned `revision`.
  4. Verifies the local HEAD has been pushed (matches the upstream tracking
     branch) before rewriting the pin - unless --allow-unpushed is given.
  5. Warns (but does not block) if the working tree has uncommitted changes,
     since those are never part of the pinned commit.
  6. Rewrites only the `revision="..."` attribute value in place, leaving all
     other manifest formatting/comments untouched (manifests are hand-parsed
     by other tooling and must not be reformatted).

This script is project-agnostic: it only relies on the standard repo-tool
manifest XML shape (<remote>, <default>, <project>) and never hardcodes a
project/module name, branch name, or workspace path.

Usage:
    python manifest_sync.py [--dry-run] [--allow-unpushed]
                             [--root ROOT] [--manifest FILE ...]
                             [--path REL_PATH ...]

Examples:
    # Preview what would change across default.xml / platform.xml
    python manifest_sync.py --dry-run

    # Apply, but restrict to specific project paths
    python manifest_sync.py --path app --path pkg/some_module
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_MANIFESTS = ["default.xml", "platform.xml", "platform_removal.xml"]

PROJECT_RE = re.compile(r"<project\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</project>)", re.DOTALL)
REMOTE_RE = re.compile(r"<remote\b(?P<attrs>[^>]*?)/>")
DEFAULT_RE = re.compile(r"<default\b(?P<attrs>[^>]*?)/>")
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')


def parse_attrs(attr_text):
    return dict(ATTR_RE.findall(attr_text))


def run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def normalize_url(url):
    return url.strip().rstrip("/").removesuffix(".git").lower()


def local_remote_urls(repo_dir):
    rc, out, _ = run_git(["remote", "-v"], repo_dir)
    if rc != 0:
        return set()
    urls = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            urls.add(normalize_url(parts[1]))
    return urls


def find_local_head(repo_dir):
    rc, out, _ = run_git(["rev-parse", "HEAD"], repo_dir)
    return out if rc == 0 else None


def is_dirty(repo_dir):
    rc, out, _ = run_git(["status", "--porcelain"], repo_dir)
    return rc == 0 and bool(out)


def upstream_pushed(repo_dir, head):
    rc, upstream, _ = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], repo_dir)
    if rc != 0 or not upstream:
        return None  # no upstream configured, can't verify
    rc, upstream_head, _ = run_git(["rev-parse", upstream], repo_dir)
    if rc != 0:
        return None
    return upstream_head == head


class ManifestProject:
    def __init__(self, match, name, path, remote, revision):
        self.match = match
        self.name = name
        self.path = path
        self.remote = remote
        self.revision = revision


def collect_projects(text):
    remotes = {}
    for m in REMOTE_RE.finditer(text):
        attrs = parse_attrs(m.group("attrs"))
        if "name" in attrs and "fetch" in attrs:
            remotes[attrs["name"]] = attrs["fetch"]

    default_remote = None
    m = DEFAULT_RE.search(text)
    if m:
        default_remote = parse_attrs(m.group("attrs")).get("remote")

    projects = []
    for m in PROJECT_RE.finditer(text):
        attrs = parse_attrs(m.group("attrs"))
        name = attrs.get("name")
        path = attrs.get("path", name)
        revision = attrs.get("revision")
        remote = attrs.get("remote", default_remote)
        if not name or not revision or not remote or remote not in remotes:
            continue
        clone_url = normalize_url(f"{remotes[remote]}/{name}")
        projects.append((ManifestProject(m, name, path, remote, revision), clone_url))
    return projects


def process_manifest(manifest_path, root, path_filter, dry_run, allow_unpushed):
    text = manifest_path.read_text(encoding="utf-8")
    changed = False
    report = []

    for project, clone_url in collect_projects(text):
        if path_filter and project.path not in path_filter:
            continue

        repo_dir = root / project.path
        if not (repo_dir / ".git").exists():
            continue  # not checked out locally, nothing to sync

        if clone_url not in local_remote_urls(repo_dir):
            continue  # this manifest entry doesn't correspond to this checkout

        head = find_local_head(repo_dir)
        if not head or head == project.revision:
            continue  # already in sync (or HEAD unreadable)

        pushed = upstream_pushed(repo_dir, head)
        dirty = is_dirty(repo_dir)

        if pushed is False:
            report.append(f"  SKIP  {project.path} ({project.name}): local HEAD {head[:12]} "
                           f"is ahead of/differs from upstream - not pushed yet")
            if not allow_unpushed:
                continue
        elif pushed is None:
            report.append(f"  WARN  {project.path} ({project.name}): no upstream tracking branch, "
                           f"could not verify HEAD {head[:12]} was pushed")
            if not allow_unpushed:
                report.append(f"  SKIP  {project.path}: use --allow-unpushed to pin anyway")
                continue

        if dirty:
            report.append(f"  WARN  {project.path} ({project.name}): working tree has uncommitted "
                           f"changes not reflected in HEAD {head[:12]}")

        old_attrs = project.match.group("attrs")
        new_attrs = re.sub(r'(revision\s*=\s*")[^"]*(")', rf"\g<1>{head}\g<2>", old_attrs, count=1)
        old_span = project.match.group(0)
        new_span = old_span.replace(old_attrs, new_attrs, 1)

        report.append(f"  {'WOULD UPDATE' if dry_run else 'UPDATE'}  {project.path} ({project.name}): "
                       f"{project.revision[:12]} -> {head[:12]}")

        if not dry_run:
            text = text.replace(old_span, new_span, 1)
            changed = True

    if changed and not dry_run:
        manifest_path.write_text(text, encoding="utf-8")

    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="Workspace root containing the manifests and checkouts (default: cwd)")
    parser.add_argument("--manifest", action="append", help="Manifest file(s) to update (default: default.xml, platform.xml, platform_removal.xml)")
    parser.add_argument("--path", action="append", help="Restrict to this project checkout path (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would change, don't write files")
    parser.add_argument("--allow-unpushed", action="store_true", help="Pin revisions even if HEAD wasn't verified as pushed")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifests = args.manifest or DEFAULT_MANIFESTS
    path_filter = set(args.path) if args.path else None

    any_report = False
    for manifest_name in manifests:
        manifest_path = root / manifest_name
        if not manifest_path.exists():
            continue
        report = process_manifest(manifest_path, root, path_filter, args.dry_run, args.allow_unpushed)
        if report:
            any_report = True
            print(f"{manifest_name}:")
            print("\n".join(report))

    if not any_report:
        print("Nothing to sync - all matched project pins already match local HEAD.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
