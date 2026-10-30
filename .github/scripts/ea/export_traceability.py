"""
Tool: export_traceability.py

Exports complete traceability information for EA design packages to JSON.
Supports three design levels:

  module     — SwMod_*  packages  (software module level, default)
  subsystem  — SwSubSys_* packages (software sub-system level)
  system     — SwSys_* packages   (system design level)

Multiple levels can be combined.  A single named package can also be exported
regardless of its naming prefix.

For every class / interface / component element found inside each package the
tool records:
  - The element's own GUID / Trace ID
  - Incoming links: which other EA elements link *to* this element
  - Outgoing links: which EA elements this element links *to*
  - Per-operation traceability (tagged-value links such as Implements/Trace)

Requirements
------------
Run with the 32-bit Python interpreter that has pywin32 installed:
    .venv32\\Scripts\\python.exe scripts/export_traceability.py [options]

Usage
-----
Single package (exact name, any level):
    .venv32\\Scripts\\python.exe scripts/export_traceability.py SwMod_TouchSM
    .venv32\\Scripts\\python.exe scripts/export_traceability.py SwSubSys_TouchCtl --filter Platform
    .venv32\\Scripts\\python.exe scripts/export_traceability.py SwSys_HUD

All packages at a specific design level:
    .venv32\\Scripts\\python.exe scripts/export_traceability.py --level module
    .venv32\\Scripts\\python.exe scripts/export_traceability.py --level subsystem
    .venv32\\Scripts\\python.exe scripts/export_traceability.py --level system
    .venv32\\Scripts\\python.exe scripts/export_traceability.py --level all

Combine level with scope filter:
    .venv32\\Scripts\\python.exe scripts/export_traceability.py --level subsystem --scope Platform
    .venv32\\Scripts\\python.exe scripts/export_traceability.py --level all --scope Platform

Custom package name prefix (overrides --level):
    .venv32\\Scripts\\python.exe scripts/export_traceability.py --prefix SwIntf_

Custom output directory:
    .venv32\\Scripts\\python.exe scripts/export_traceability.py --level all --output-dir out/trace/

Arguments
---------
package             (positional, optional)
                        Exact EA package name, e.g. SwMod_TouchSM or SwSubSys_TouchCtl.
                        Omit to discover and export packages by --level / --prefix.
-f / --filter SEGMENT
                        Path segment to disambiguate a single-package lookup
                        when the same name exists in multiple places
                        (e.g. --filter Platform).
-s / --scope SEGMENT
                        Restrict multi-package discovery to packages whose EA
                        path contains SEGMENT as a whole dot-separated segment.
                        Ignored when a specific package name is given.
-l / --level LEVEL
                        Design level to export (default: module).
                        Choices:
                          module     — SwMod_* packages
                          subsystem  — SwSubSys_* packages
                          system     — SwSys_* packages
                          all        — SwMod_* + SwSubSys_* + SwSys_*
-p / --prefix PREFIX
                        Custom package name prefix, e.g. SwIntf_.
                        Overrides --level. Can be specified multiple times.
-o / --output-dir DIR
                        Directory where JSON files are written.
                        Defaults to <project_root>/ai_output/traceability/.

Output
------
One JSON file per package:
    ai_output/traceability/<PackageName>_traceability.json

JSON structure:
{
  "module_name": "SwMod_TouchSM",
  "ea_path": "Model.Platform.SwMod_TouchSM",
  "level": "module",
  "classes": [
    {
      "name": "TouchSM_API",
      "guid": "{XXXXXXXX-...}",
      "trace_id": "TouchSM_API|{XXXXXXXX-...}",
      "stereotype": "...",
      "source_file": "touchsm1c1.c",
      "incoming_links": [
        {
          "connector_type": "Dependency",
          "from_name": "SomeOtherClass",
          "from_guid": "{...}",
          "from_package": "SwMod_Other",
          "notes": ""
        }
      ],
      "outgoing_links": [
        {
          "connector_type": "Realization",
          "to_name": "SomeInterface",
          "to_guid": "{...}",
          "to_package": "SwIntf_Something",
          "notes": ""
        }
      ],
      "operations": [
        {
          "name": "TouchSM_vInit",
          "guid": "{...}",
          "trace_id": "TouchSM_vInit|{...}",
          "return_type": "void",
          "incoming_links": [],
          "outgoing_links": []
        }
      ]
    }
  ]
}

Errors
------
Exits with a non-zero code if:
  - The EA project cannot be opened
  - A named package is not found or matches multiple packages (use --filter)
  - No matching packages are found under the given scope / level
"""

from __future__ import annotations

import json
import os
import sys

import win32com.client

# ---------------------------------------------------------------------------
# Project root on path so settings is importable
# ---------------------------------------------------------------------------
_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_TOOL_DIR)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _TOOL_DIR)

from config.settings import EA_PROJECT  # noqa: E402

_DEFAULT_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "ai_output", "traceability")


# ---------------------------------------------------------------------------
# Design-level prefix maps
# ---------------------------------------------------------------------------

_LEVEL_PREFIXES: dict[str, list[str]] = {
    "module":    ["SwMod_"],
    "subsystem": ["SwSubSys_"],
    "system":    ["SwSys_"],
    "all":       ["SwMod_", "SwSubSys_", "SwSys_"],
}


def _level_label(pkg_name: str) -> str:
    """Return a human-readable level label for a package name."""
    if pkg_name.startswith("SwMod_"):
        return "module"
    if pkg_name.startswith("SwSubSys_"):
        return "subsystem"
    if pkg_name.startswith("SwSys_"):
        return "system"
    return "unknown"


# ---------------------------------------------------------------------------
# EA path / package helpers  (same logic as export_module_functions.py)
# ---------------------------------------------------------------------------

def _search_package_all(parent, name: str, current_path: str, results: list) -> None:
    try:
        for pkg in parent.Packages:
            pkg_path = f"{current_path}.{pkg.Name}" if current_path else pkg.Name
            if pkg.Name == name:
                results.append((pkg, pkg_path))
            _search_package_all(pkg, name, pkg_path, results)
    except Exception:
        pass


def _path_filter_matches(path: str, f: str) -> bool:
    if "." in f:
        return f in path
    return f in path.split(".")


def find_module_package(
    repo, module_name: str, path_filter: str | None = None
) -> tuple[object, str]:
    results: list[tuple[object, str]] = []
    for model in repo.Models:
        _search_package_all(model, module_name, model.Name, results)

    if path_filter:
        results = [r for r in results if _path_filter_matches(r[1], path_filter)]

    if not results:
        msg = (
            f"\nERROR: Module '{module_name}'"
            + (f" with path containing '{path_filter}'" if path_filter else "")
            + f" was not found.\n       Project: {EA_PROJECT}\n"
        )
        print(msg, file=sys.stderr)
        sys.exit(1)

    if len(results) > 1:
        print(
            f"\nERROR: Multiple packages named '{module_name}' found.\n"
            "Candidates:\n",
            file=sys.stderr,
        )
        for i, (_, p) in enumerate(results, 1):
            print(f"  [{i}] {p}", file=sys.stderr)
        print(
            f"\nRe-run with --filter, e.g.:\n"
            f"  export_traceability.py {module_name} --filter Platform\n",
            file=sys.stderr,
        )
        sys.exit(1)

    return results[0]


def _collect_packages_by_prefix(
    parent,
    current_path: str,
    results: list,
    prefixes: list[str],
) -> None:
    """Recursively collect packages whose name starts with any of *prefixes*."""
    try:
        for pkg in parent.Packages:
            pkg_path = f"{current_path}.{pkg.Name}" if current_path else pkg.Name
            if any(pkg.Name.startswith(p) for p in prefixes):
                results.append((pkg, pkg_path))
            else:
                _collect_packages_by_prefix(pkg, pkg_path, results, prefixes)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Connector extraction helpers
# ---------------------------------------------------------------------------

def _safe_str(val) -> str:
    try:
        return (val or "").strip()
    except Exception:
        return ""


def _element_package_name(repo, element_id: int) -> str:
    """Return the parent package Name for a given element ID, or ''."""
    try:
        el = repo.GetElementByID(element_id)
        pkg = repo.GetPackageByID(el.PackageID)
        return _safe_str(pkg.Name)
    except Exception:
        return ""


def _extract_element_links(repo, el) -> tuple[list[dict], list[dict]]:
    """
    Return (incoming_links, outgoing_links) for *el*.

    incoming_links: connector where el is the Supplier  (someone else → el)
    outgoing_links: connector where el is the Client    (el → someone else)
    """
    incoming: list[dict] = []
    outgoing: list[dict] = []

    try:
        for conn in el.Connectors:
            conn_type = _safe_str(conn.Type)
            notes = _safe_str(conn.Notes)

            is_outgoing = (conn.ClientID == el.ElementID)
            is_incoming = (conn.SupplierID == el.ElementID)

            if not is_outgoing and not is_incoming:
                continue

            if is_outgoing:
                try:
                    target = repo.GetElementByID(conn.SupplierID)
                    outgoing.append({
                        "connector_type": conn_type,
                        "to_name":        _safe_str(target.Name),
                        "to_guid":        _safe_str(target.ElementGUID),
                        "to_package":     _element_package_name(repo, conn.SupplierID),
                        "notes":          notes,
                    })
                except Exception:
                    pass
            else:  # incoming
                try:
                    source = repo.GetElementByID(conn.ClientID)
                    incoming.append({
                        "connector_type": conn_type,
                        "from_name":      _safe_str(source.Name),
                        "from_guid":      _safe_str(source.ElementGUID),
                        "from_package":   _element_package_name(repo, conn.ClientID),
                        "notes":          notes,
                    })
                except Exception:
                    pass
    except Exception:
        pass

    return incoming, outgoing


def _extract_operation_links(repo, op) -> tuple[list[dict], list[dict]]:
    """
    Return (incoming_links, outgoing_links) for an EA Method/Operation.

    EA stores operation-level traceability in two ways:
      1. Via tagged values — e.g. "Implements" pointing to an operation GUID.
      2. Via the operation's parent element connectors filtered by stereotype.

    We capture both sources so nothing is missed.
    """
    incoming: list[dict] = []
    outgoing: list[dict] = []

    # --- Tagged values that represent explicit trace links ---
    _TRACE_TV_NAMES = {
        "Implements", "Realizes", "DerivedFrom", "Trace", "Refine",
    }
    try:
        for tv in op.TaggedValues:
            if tv.Name in _TRACE_TV_NAMES:
                val = _safe_str(tv.Value)
                if val:
                    outgoing.append({
                        "connector_type": tv.Name,
                        "to_name":        "",     # GUID only — name not resolvable cheaply
                        "to_guid":        val,
                        "to_package":     "",
                        "notes":          "",
                    })
    except Exception:
        pass

    return incoming, outgoing


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------



def _build_activity_guid_map(module_pkg) -> dict:
    """Return {function_name: ElementGUID} from the Behavior sub-package.

    In EA, function Activity Diagrams live in a sub-package named 'Behavior'.
    The element ElementGUID matches the xmi.id of the Collaboration element
    in MS_*.xml exports. MethodGUID is the Operation element GUID and is
    NOT the same value -- do not use it for @Req_ID trace tokens.
    """
    result: dict = {}

    def _scan(pkg):
        try:
            for el in pkg.Elements:
                name = (el.Name or "").strip()
                guid = (el.ElementGUID or "").strip()
                if name and guid:
                    result[name] = guid
        except Exception:
            pass
        try:
            for sp in pkg.Packages:
                _scan(sp)
        except Exception:
            pass

    try:
        for sp in module_pkg.Packages:
            if sp.Name == "Behavior":
                _scan(sp)
                break
    except Exception:
        pass

    return result

def extract_traceability(module_pkg, repo) -> list[dict]:
    """
    Return a list of class-info dicts containing full traceability data.
    """
    # Build activity guid map and store on the function object so operation
    # processing can access it without threading an extra argument everywhere.
    extract_traceability._act_map_cache = _build_activity_guid_map(module_pkg)
    classes: list[dict] = []
    try:
        for el in module_pkg.Elements:
            if el.Type not in ("Class", "Interface", "Component"):
                continue

            el_guid = _safe_str(el.ElementGUID)
            el_name = _safe_str(el.Name)
            source_file = ""
            try:
                for tv in el.TaggedValues:
                    if tv.Name == "SourceFile":
                        source_file = _safe_str(tv.Value)
                        if source_file and not source_file.endswith(".c"):
                            source_file += ".c"
                        break
            except Exception:
                pass

            incoming_links, outgoing_links = _extract_element_links(repo, el)

            # --- Operations ---
            operations: list[dict] = []
            try:
                for op in el.Methods:
                    # Skip Macro stereotype
                    if _safe_str(getattr(op, "Stereotype", "")) == "Macro":
                        continue

                    # Use Activity Diagram ElementGUID (matches @Req_ID token GUIDs).
                    _act_map = getattr(extract_traceability, '_act_map_cache', None)
                    op_guid = _act_map.get(op.Name or "", "") if _act_map else ""
                    if not op_guid:
                        op_guid = _safe_str(getattr(op, "MethodGUID", None) or "")
                    op_name = _safe_str(op.Name)
                    op_in, op_out = _extract_operation_links(repo, op)

                    operations.append({
                        "name":           op_name,
                        "guid":           op_guid,
                        "trace_id":       f"{op_name}|{op_guid}" if op_guid else "",
                        "return_type":    _safe_str(op.ReturnType or "void"),
                        "incoming_links": op_in,
                        "outgoing_links": op_out,
                    })
            except Exception as exc:
                print(f"  WARNING: could not read operations for '{el_name}': {exc}", file=sys.stderr)

            classes.append({
                "name":           el_name,
                "guid":           el_guid,
                "trace_id":       f"{el_name}|{el_guid}" if el_guid else "",
                "stereotype":     _safe_str(el.Stereotype),
                "source_file":    source_file,
                "incoming_links": incoming_links,
                "outgoing_links": outgoing_links,
                "operations":     operations,
            })
    except Exception as exc:
        print(f"WARNING: Could not iterate elements: {exc}", file=sys.stderr)

    return classes


# ---------------------------------------------------------------------------
# JSON generation
# ---------------------------------------------------------------------------

def build_traceability_json(
    module_name: str,
    module_path: str,
    classes: list[dict],
    level: str = "",
) -> dict:
    return {
        "module_name": module_name,
        "ea_path":     module_path,
        "level":       level or _level_label(module_name),
        "classes":     classes,
    }


# ---------------------------------------------------------------------------
# Single-module export
# ---------------------------------------------------------------------------

def export_module_traceability(
    module_name: str,
    output_dir: str | None = None,
    path_filter: str | None = None,
    level: str = "",
) -> str:
    """
    Export traceability for a single named package (any design level).

    Returns the path of the generated JSON file.
    """
    if output_dir is None:
        output_dir = _DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    print(f"Opening EA project: {EA_PROJECT}")
    repo = win32com.client.Dispatch("EA.Repository")
    try:
        repo.OpenFile(EA_PROJECT)
    except Exception as exc:
        print(f"ERROR: Could not open EA project: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        print(f"Searching for module '{module_name}'...")
        module_pkg, module_path = find_module_package(repo, module_name, path_filter)
        print(f"Found: {module_path}")

        classes = extract_traceability(module_pkg, repo)
        if not classes:
            print(
                f"\nWARNING: No Class/Interface/Component elements found in '{module_name}'.\n",
                file=sys.stderr,
            )

        data = build_traceability_json(module_name, module_path, classes, level)
        out_path = os.path.join(output_dir, f"{module_name}_traceability.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

        total_ops = sum(len(c["operations"]) for c in classes)
        total_links = sum(
            len(c["incoming_links"]) + len(c["outgoing_links"])
            + sum(len(o["incoming_links"]) + len(o["outgoing_links"]) for o in c["operations"])
            for c in classes
        )
        print(
            f"Extracted {len(classes)} class(es), {total_ops} operation(s), "
            f"{total_links} traceability link(s)."
        )
        print(f"Written: {out_path}")
        return out_path

    finally:
        try:
            repo.CloseFile()
            repo.Exit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Multi-module export
# ---------------------------------------------------------------------------

def export_all_traceability(
    scope_filter: str | None = None,
    output_dir: str | None = None,
    prefixes: list[str] | None = None,
) -> list[str]:
    """
    Discover packages whose names start with any of *prefixes* (optionally
    filtered to paths containing *scope_filter*) and generate one traceability
    JSON per package.

    Parameters
    ----------
    scope_filter : str, optional
        Whole-segment EA path filter (e.g. 'Platform', 'SwSubSys_TouchCtl').
    output_dir : str, optional
        Output directory. Defaults to <project_root>/ai_output/traceability/.
    prefixes : list[str], optional
        Package name prefixes to collect. Defaults to ['SwMod_'].

    Returns
    -------
    list[str]
        Paths of all generated JSON files.
    """
    if prefixes is None:
        prefixes = ["SwMod_"]
    if output_dir is None:
        output_dir = _DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    print(f"Opening EA project: {EA_PROJECT}")
    repo = win32com.client.Dispatch("EA.Repository")
    try:
        repo.OpenFile(EA_PROJECT)
    except Exception as exc:
        print(f"ERROR: Could not open EA project: {exc}", file=sys.stderr)
        sys.exit(1)

    generated: list[str] = []
    try:
        all_packages: list[tuple[object, str]] = []
        for model in repo.Models:
            _collect_packages_by_prefix(model, model.Name, all_packages, prefixes)

        if scope_filter:
            all_packages = [
                (pkg, path) for pkg, path in all_packages
                if _path_filter_matches(path, scope_filter)
            ]

        if not all_packages:
            prefix_str = ", ".join(f"'{p}*'" for p in prefixes)
            print(
                f"No packages matching {prefix_str} found"
                + (f" under scope '{scope_filter}'" if scope_filter else "")
                + ".",
                file=sys.stderr,
            )
            sys.exit(1)

        # Deduplicate: prefer non-PlatformConfigs paths when a package appears twice
        by_name: dict[str, list[tuple[object, str]]] = {}
        for pkg, path in all_packages:
            by_name.setdefault(pkg.Name, []).append((pkg, path))

        deduped: list[tuple[object, str]] = []
        for name, candidates in by_name.items():
            if len(candidates) == 1:
                deduped.append(candidates[0])
            else:
                preferred = [c for c in candidates if "PlatformConfigs" not in c[1]]
                deduped.extend(preferred if preferred else candidates)

        deduped.sort(key=lambda x: x[1])

        print(f"Found {len(deduped)} package(s):")
        for _, path in deduped:
            print(f"  {path}")
        print()

        for module_pkg, module_path in deduped:
            module_name = module_pkg.Name
            lbl = _level_label(module_name)
            print(f"Processing {module_name} [{lbl}] ...")
            try:
                classes = extract_traceability(module_pkg, repo)
                total_ops = sum(len(c["operations"]) for c in classes)
                total_links = sum(
                    len(c["incoming_links"]) + len(c["outgoing_links"])
                    + sum(
                        len(o["incoming_links"]) + len(o["outgoing_links"])
                        for o in c["operations"]
                    )
                    for c in classes
                )
                print(
                    f"  {len(classes)} class(es), {total_ops} op(s), "
                    f"{total_links} link(s)"
                )
                data = build_traceability_json(module_name, module_path, classes, lbl)
                out_path = os.path.join(output_dir, f"{module_name}_traceability.json")
                with open(out_path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2, ensure_ascii=False)
                print(f"  Written: {out_path}")
                generated.append(out_path)
            except Exception as exc:
                print(f"  ERROR processing {module_name}: {exc}", file=sys.stderr)

        print(f"\nDone. {len(generated)} file(s) generated.")
    finally:
        try:
            repo.CloseFile()
            repo.Exit()
        except Exception:
            pass

    return generated


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="export_traceability",
        description=(
            "Export EA traceability links for design packages to JSON.\n"
            "Supports module (SwMod_*), subsystem (SwSubSys_*), and system (SwSys_*) levels.\n"
            "Pass a package name to export a single package, or use --level / --scope\n"
            "to discover and export all matching packages."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "package",
        nargs="?",
        default=None,
        help=(
            "Exact EA package name (e.g. SwMod_TouchSM, SwSubSys_TouchCtl). "
            "Omit to discover by --level / --prefix."
        ),
    )
    parser.add_argument(
        "-f", "--filter",
        dest="path_filter",
        metavar="SEGMENT",
        help="Path segment to disambiguate a single-package lookup (e.g. Platform).",
    )
    parser.add_argument(
        "-s", "--scope",
        dest="scope",
        metavar="SEGMENT",
        help=(
            "Limit discovery to packages under this path segment "
            "(e.g. SwSubSys_TouchCtl, Platform). Ignored when a package name is given."
        ),
    )
    parser.add_argument(
        "-l", "--level",
        dest="level",
        metavar="LEVEL",
        default="module",
        choices=list(_LEVEL_PREFIXES.keys()),
        help=(
            "Design level to export (default: module). "
            "Choices: module (SwMod_*), subsystem (SwSubSys_*), "
            "system (SwSys_*), all. "
            "Ignored when a package name is given or --prefix is used."
        ),
    )
    parser.add_argument(
        "-p", "--prefix",
        dest="prefixes",
        metavar="PREFIX",
        action="append",
        default=None,
        help=(
            "Custom package name prefix (e.g. SwIntf_). "
            "Can be specified multiple times. Overrides --level."
        ),
    )
    parser.add_argument(
        "-o", "--output-dir",
        dest="output_dir",
        metavar="DIR",
        default=None,
        help="Directory where JSON files are written (default: ai_output/traceability/).",
    )

    args = parser.parse_args(argv[1:])

    if args.package:
        export_module_traceability(
            args.package, args.output_dir, args.path_filter
        )
    else:
        # Resolve prefixes: --prefix overrides --level
        if args.prefixes:
            prefixes = args.prefixes
        else:
            prefixes = _LEVEL_PREFIXES.get(args.level, ["SwMod_"])
        export_all_traceability(args.scope, args.output_dir, prefixes)


if __name__ == "__main__":
    main(sys.argv)

