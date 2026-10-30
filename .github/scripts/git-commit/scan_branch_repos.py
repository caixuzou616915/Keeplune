#!/usr/bin/env python3
"""
Scan a workspace root and its repo-tool sub-repositories to find checkouts on
a given branch name. The workspace root itself is included when it is a Git
repository, which supports standalone mono-repositories as well as meta-repos.

Discovery candidates are reconciled by canonical checkout path and source priority:
project.list (100), XML manifest (50), then filesystem/root candidates (10).

For each discovered checkout, this script:
  1. Discovers local git repositories (both .git/ directories and .git files/symlinks)
  2. Queries the current branch (`git branch --show-current`)
  3. Filters by the target branch name
  4. Reports repository path, current branch, and staged file count for each match

This script is project-agnostic: it infers projects from .repo/project.list and
root-level XML files containing manifest/project elements, and never hardcodes
a project/module name, branch name, or workspace path. Higher-priority sources
replace lower-priority candidate metadata independent of discovery order.

Usage:
    python scan_branch_repos.py --root <workspace-root> --branch <branch-name>

Examples:
    # Find all repos on pt/dgc-4525
    python scan_branch_repos.py --root d:\\Prjs\\vwId1\\vw_id1 --branch pt/dgc-4525

    # Dry-run: list all discovered repos and their current branch
    python scan_branch_repos.py --root d:\\Prjs\\vwId1\\vw_id1 --list-all
"""
import argparse
from dataclasses import dataclass
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Optional

PROJECT_LIST_PRIORITY = 100
MANIFEST_PRIORITY = 50
FILESYSTEM_PRIORITY = 10


@dataclass(frozen=True)
class RepositoryCandidate:
    relative_path: str
    repo_path: Path
    canonical_path: str
    source: str
    priority: int


def run_git(args: List[str], cwd: Path) -> Tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=10
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "git command timed out"
    except Exception as e:
        return 1, "", str(e)


def is_git_repo(repo_path: Path) -> bool:
    """Return whether repo_path is the root of a Git working tree."""
    git_dir_rc, _, _ = run_git(["rev-parse", "--git-dir"], repo_path)
    if git_dir_rc != 0:
        return False

    root_rc, git_root, _ = run_git(["rev-parse", "--show-toplevel"], repo_path)
    if root_rc != 0 or not git_root:
        return False

    try:
        candidate = os.path.normcase(str(repo_path.resolve()))
        actual_root = os.path.normcase(str(Path(git_root).resolve()))
    except (OSError, RuntimeError):
        return False

    return candidate == actual_root


def get_current_branch(repo_path: Path) -> Optional[str]:
    """Get the current branch name via git branch --show-current."""
    rc, out, _ = run_git(["branch", "--show-current"], repo_path)
    return out if rc == 0 and out else None


def get_staged_file_count(repo_path: Path) -> int:
    """Count staged files via git diff --cached --name-only."""
    rc, out, _ = run_git(["diff", "--cached", "--name-only"], repo_path)
    if rc != 0:
        return 0
    return len([line for line in out.splitlines() if line.strip()])


def add_repository_candidate(
    candidates: Dict[str, RepositoryCandidate],
    relative_path: str,
    repo_path: Path,
    source: str,
    priority: int,
) -> None:
    """Keep the highest-priority discovery record for each Git checkout."""
    if not is_git_repo(repo_path):
        return

    try:
        canonical_path = os.path.normcase(str(repo_path.resolve()))
    except (OSError, RuntimeError):
        return

    candidate = RepositoryCandidate(
        relative_path=relative_path,
        repo_path=repo_path,
        canonical_path=canonical_path,
        source=source,
        priority=priority,
    )
    existing = candidates.get(canonical_path)
    if existing is None or candidate.priority > existing.priority:
        candidates[canonical_path] = candidate
    elif candidate.priority == existing.priority and candidate.relative_path < existing.relative_path:
        candidates[canonical_path] = candidate


def discover_repos(root: Path) -> Dict[str, Path]:
    """
    Discover the root checkout and repositories listed by project.list or XML manifests.
    Returns a dict mapping relative path -> Path to repo root.
    """
    candidates: Dict[str, RepositoryCandidate] = {}

    # Include a standalone mono-repo or the meta-repo root itself.
    add_repository_candidate(
        candidates, ".", root, "workspace_root", FILESYSTEM_PRIORITY
    )

    # project.list is authoritative for synchronized checkouts; manifests supplement it.
    project_list = root / ".repo" / "project.list"
    if project_list.exists():
        try:
            with open(project_list, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        repo_path = root / line
                        add_repository_candidate(
                            candidates,
                            line,
                            repo_path,
                            "project.list",
                            PROJECT_LIST_PRIORITY,
                        )
        except Exception as e:
            print(f"Warning: Could not read {project_list}: {e}", file=sys.stderr)

    # Identify root-level XML manifests by their contents, not their filenames.
    for manifest_path in sorted(root.glob("*.xml")):
        try:
            manifest_root = ET.parse(manifest_path).getroot()
            elements = list(manifest_root.iter())
            local_names = [element.tag.rsplit("}", 1)[-1] for element in elements]
            if "manifest" not in local_names and "project" not in local_names:
                continue

            for element in elements:
                if element.tag.rsplit("}", 1)[-1] != "project":
                    continue

                relative_path = element.attrib.get("path")
                if relative_path:
                    add_repository_candidate(
                        candidates,
                        relative_path,
                        root / relative_path,
                        "manifest",
                        MANIFEST_PRIORITY,
                    )
        except (ET.ParseError, OSError) as e:
            print(f"Warning: Could not parse {manifest_path}: {e}", file=sys.stderr)

    return {
        candidate.relative_path: candidate.repo_path
        for candidate in candidates.values()
    }


def filter_by_branch(repos: Dict[str, Path], target_branch: str) -> Dict[str, Tuple[Path, int]]:
    """
    Filter repositories by target branch.
    Returns dict: relative_path -> (Path, staged_file_count)
    """
    matched = {}
    for rel_path, repo_path in repos.items():
        if not is_git_repo(repo_path):
            continue

        current_branch = get_current_branch(repo_path)
        if current_branch == target_branch:
            staged_count = get_staged_file_count(repo_path)
            matched[rel_path] = (repo_path, staged_count)

    return matched


def main():
    parser = argparse.ArgumentParser(
        description="Scan workspace and manifest-listed repositories for a branch"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Workspace root (default: current directory)"
    )
    parser.add_argument(
        "--branch",
        type=str,
        help="Target branch name to filter by (e.g., pt/dgc-4525)"
    )
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="List all discovered repos and their current branch (ignore --branch)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    root = args.root.resolve()
    if not root.exists():
        print(f"Error: Root path does not exist: {root}", file=sys.stderr)
        sys.exit(1)

    # Discover all repos
    all_repos = discover_repos(root)

    if not all_repos:
        print(f"Error: No repositories found under {root}", file=sys.stderr)
        sys.exit(1)

    if args.list_all:
        # List all discovered repos with their current branch
        results = {}
        for rel_path, repo_path in sorted(all_repos.items()):
            current_branch = get_current_branch(repo_path)
            staged_count = get_staged_file_count(repo_path)
            results[rel_path] = {
                "path": str(repo_path),
                "branch": current_branch,
                "staged_files": staged_count
            }

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Discovered {len(results)} repositories:")
            print()
            for rel_path, info in results.items():
                print(f"  {rel_path}")
                print(f"    Path: {info['path']}")
                print(f"    Branch: {info['branch']}")
                print(f"    Staged files: {info['staged_files']}")
                print()
        return

    if not args.branch:
        print("Error: --branch is required (or use --list-all)", file=sys.stderr)
        sys.exit(1)

    # Filter by branch
    matched = filter_by_branch(all_repos, args.branch)

    if args.json:
        results = {
            rel_path: {
                "path": str(repo_path),
                "branch": args.branch,
                "staged_files": staged_count
            }
            for rel_path, (repo_path, staged_count) in matched.items()
        }
        print(json.dumps(results, indent=2))
    else:
        if not matched:
            print(f"No repositories found on branch '{args.branch}'", file=sys.stderr)
            sys.exit(0)

        print(f"Repositories on branch '{args.branch}':")
        print()
        for rel_path in sorted(matched.keys()):
            repo_path, staged_count = matched[rel_path]
            print(f"  {rel_path}")
            print(f"    Path: {repo_path}")
            print(f"    Staged files: {staged_count}")
            print()


if __name__ == "__main__":
    main()
