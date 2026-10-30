"""
Tool: export_module_functions.py

Searches the EA repository for SwMod_* packages and exports their classes and
operations as Markdown function-list files to doc/<ModuleName>.md.

Requirements:
    Run with the 32-bit Python that has pywin32 installed:
        .venv32\\Scripts\\python.exe scripts/export_module_functions.py [options]

Usage
-----
Single module (exact name):
    .venv32\\Scripts\\python.exe scripts/export_module_functions.py SwMod_TouchSM
    .venv32\\Scripts\\python.exe scripts/export_module_functions.py SwMod_TouchSM --filter Platform

All modules under a subsystem:
    .venv32\\Scripts\\python.exe scripts/export_module_functions.py --scope SwSubSys_TouchCtl

All modules under a platform or project layer:
    .venv32\\Scripts\\python.exe scripts/export_module_functions.py --scope Platform
    .venv32\\Scripts\\python.exe scripts/export_module_functions.py --scope Project

All modules in the entire EA project:
    .venv32\\Scripts\\python.exe scripts/export_module_functions.py

Optional output directory (appended after other args):
    .venv32\\Scripts\\python.exe scripts/export_module_functions.py --scope Platform doc/mydir/

Arguments
---------
module       (positional, optional)
                 Exact EA package name, e.g. SwMod_TouchSM.
                 Omit to discover and export all SwMod_* packages.
-f / --filter SEGMENT
                 Path segment to disambiguate a single-module lookup when the
                 same name exists in multiple places (e.g. --filter Platform).
-s / --scope SEGMENT
                 Restrict multi-module discovery to packages whose EA path
                 contains SEGMENT as a whole dot-separated segment.
                 Examples: SwSubSys_TouchCtl, Platform, Project.
                 Ignored when a specific module name is given.
output_dir   (positional, optional)
                 Directory where .md files are written.
                 Defaults to <project_root>/doc/.

Output
------
One Markdown file per module: doc/<ModuleName>.md
Each file contains:
  - Module header (EA path, feature/variant)
  - Per-class section with class Trace ID and a function table
    (# | Function | Trace ID)
  - Summary table (class, source file, function count)

Errors
------
Exits with a non-zero code if:
  - The EA project cannot be opened
  - A named module is not found or matches multiple packages (use --filter)
  - No SwMod_* packages are found under the given scope
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

_DEFAULT_DOC_DIR = os.path.join(_PROJECT_ROOT, "doc")


# ---------------------------------------------------------------------------
# EA helpers
# ---------------------------------------------------------------------------

def _tagged_value(obj, name: str) -> str:
    """Return the value of a named tagged value on an EA object, or ''."""
    try:
        for tv in obj.TaggedValues:
            if tv.Name == name:
                return (tv.Value or "").strip()
    except Exception:
        pass
    return ""


def _search_package_all(parent, name: str, current_path: str, results: list) -> None:
    """
    Recursively search *parent* (Model or Package) for ALL sub-packages whose
    Name == *name* (case-sensitive).

    Appends (package_object, full_dot_path) tuples to *results*.
    """
    try:
        for pkg in parent.Packages:
            pkg_path = f"{current_path}.{pkg.Name}" if current_path else pkg.Name
            if pkg.Name == name:
                results.append((pkg, pkg_path))
            _search_package_all(pkg, name, pkg_path, results)
    except Exception:
        pass


def find_module_package(
    repo, module_name: str, path_filter: str | None = None
) -> tuple[object, str]:
    """
    Search all EA models for a package named *module_name*.

    If *path_filter* is given (a substring of the full dot-path), only
    matches whose path contains that substring are considered.

    Returns (package_object, full_dot_path).
    Raises SystemExit with an informative error message if:
      - not found
      - multiple packages found (lists all candidates)
    """
    results: list[tuple[object, str]] = []
    for model in repo.Models:
        _search_package_all(model, module_name, model.Name, results)

    # Apply optional path filter â€” must match a complete dot-separated segment
    # (or an exact substring with dots, e.g. "Platform.SwMod").
    if path_filter:
        def _matches_filter(path: str, f: str) -> bool:
            # Accept if the filter contains dots (user gave a multi-segment substring)
            if "." in f:
                return f in path
            # Otherwise require a whole-segment match so "Platform" does NOT
            # match "PlatformConfigs"
            segments = path.split(".")
            return f in segments

        results = [r for r in results if _matches_filter(r[1], path_filter)]

    if not results:
        if path_filter:
            print(
                f"\nERROR: Module '{module_name}' with path containing '{path_filter}'"
                f" was not found in the EA project.\n"
                f"       Project: {EA_PROJECT}\n",
                file=sys.stderr,
            )
        else:
            print(
                f"\nERROR: Module '{module_name}' was not found in the EA project.\n"
                f"       Project: {EA_PROJECT}\n\n"
                "Possible causes:\n"
                "  1. The module name is misspelled (names are case-sensitive).\n"
                "  2. The package exists but is nested inside a package that is\n"
                "     itself not enumerable via COM (access restriction).\n"
                "  3. The EA project file is not the one that contains this module.\n",
                file=sys.stderr,
            )
        sys.exit(1)

    if len(results) > 1:
        # Auto-deduplicate: prefer entries without PlatformConfigs.
        preferred = [r for r in results if "PlatformConfigs" not in r[1]]
        if len(preferred) == 1:
            print(
                f"INFO: Multiple packages named \'SwMod\' found; "
                f"auto-selected non-PlatformConfigs entry: {preferred[0][1]}"
            )
            return preferred[0]

        # Still ambiguous after filtering.
        print(
            f"\nERROR: Multiple packages named '{module_name}' were found.\n"
            f"       Specify a path_filter to disambiguate.\n\n"
            "Candidates:\n",
            file=sys.stderr,
        )
        for i, (_, path) in enumerate(results, start=1):
            print(f"  [{i}] {path}", file=sys.stderr)
        print(
            "\nRe-run with a path_filter substring, e.g.:\n"
            f"  export_module_functions('{module_name}', path_filter='Platform')\n"
            f"  or on the command line:\n"
            f"  python scripts/export_module_functions.py {module_name} --filter Platform\n",
            file=sys.stderr,
        )
        sys.exit(1)

    return results[0]


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------
# Activity Diagram GUID lookup
# ---------------------------------------------------------------------------

def _build_activity_guid_map(module_pkg) -> dict:
    """Return {function_name: ElementGUID} from the Behavior sub-package.

    In EA, function Activity Diagrams live in a sub-package named 'Behavior'.
    The element's ElementGUID matches the xmi.id of the Collaboration element
    in the MS_*.xml export, which is what ms_traceability.py validates against.
    MethodGUID is a DIFFERENT identifier (Operation element GUID) and must NOT
    be used as the trace GUID.
    """
    result: dict = {}

    def _scan_element(el):
        """Recursively scan an element and its embedded child elements."""
        name = (el.Name or "").strip()
        guid = (el.ElementGUID or "").strip()
        if name and guid:
            result[name] = guid
        try:
            for child in el.Elements:
                _scan_element(child)
        except Exception:
            pass

    def _scan(pkg):
        try:
            for el in pkg.Elements:
                _scan_element(el)
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


def _build_functions_json(module_name: str, module_path: str, classes: list, activity_guid_map=None) -> dict:
    """Build the SwMod_<Module>_Functions.json structure consumed by gtest_traceability.py."""
    covered_names = set()
    out_classes = []
    for cls in classes:
        cls_guid = cls.get("guid", "")
        functions = []
        for op in cls.get("operations", []):
            trace_label = op["name"] if op.get("ea_guid", "") != cls_guid else cls["name"]
            tid = _trace_id(trace_label, op["ea_guid"])
            if tid:
                functions.append({"name": op["name"], "trace_id": tid})
                covered_names.add(op["name"])
        out_classes.append({
            "class_name":  cls["name"],
            "trace_id":    f"{cls['name']}|{cls_guid}" if cls_guid else "",
            "source_file": cls.get("source_file") or "",
            "functions":   functions,
        })
    if activity_guid_map:
        orphan_fns = []
        for name, guid in sorted(activity_guid_map.items()):
            if name not in covered_names:
                tid = _trace_id(name, guid)
                if tid:
                    orphan_fns.append({"name": name, "trace_id": tid})
        if orphan_fns:
            mod_short = module_name.replace("SwMod_", "")
            out_classes.append({
                "class_name":  f"{mod_short}_Behavior",
                "trace_id":    "",
                "source_file": "",
                "functions":   orphan_fns,
            })
    return {
        "module":   module_name.replace("SwMod_", ""),
        "ea_path":  module_path,
        "classes":  out_classes,
    }
# ---------------------------------------------------------------------------

# Tagged value names that appear as extra property rows on operations
_EXTRA_OP_TAGS: tuple[str, ...] = (
    "CycleTime (ms)",
    "TaskContext",
    "Type",
    "ResourceStates",
    "Runtime",
)

# Human-readable labels for the extra tags
_EXTRA_OP_TAG_LABELS: dict[str, str] = {
    "CycleTime (ms)": "Cycle Time (ms)",
    "TaskContext":    "Task Context",
    "Type":           "Type",
    "ResourceStates": "Resource States",
    "Runtime":        "Runtime",
}


def _to_bool(value) -> bool:
    """Best-effort conversion of EA COM values to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value or "").strip().lower()
    return s in {"1", "true", "yes", "y", "on", "const", "fixed"}


def _extract_operation_static(op, scope: str) -> bool:
    """Extract EA operation static/classifier attribute in a robust way."""
    # Primary EA COM attribute for operation static-ness.
    for attr in ("IsStatic", "Static", "Classifier"):
        try:
            if hasattr(op, attr):
                raw = getattr(op, attr)
                if str(raw).strip() != "":
                    return _to_bool(raw)
        except Exception:
            pass

    # Fallback from scope naming used by some EA repositories.
    scope_l = (scope or "").strip().lower()
    return scope_l in {"classifier", "static", "class"}


def _extract_parameter(param) -> dict:
    """Extract one EA Parameter as a dict with keys name/type/kind/fixed_value."""
    fixed_value = False

    # EA repositories can expose this metadata under different COM attributes.
    for attr in ("IsConst", "Const", "Fixed", "FixedValue", "IsFixed"):
        try:
            if hasattr(param, attr):
                raw = getattr(param, attr)
                if str(raw).strip() != "":
                    fixed_value = _to_bool(raw)
                    break
        except Exception:
            pass

    return {
        "name": (param.Name or "").strip(),
        "type": (param.Type or "").strip(),
        "kind": (param.Kind or "").strip(),
        "fixed_value": fixed_value,
    }


def extract_classes(module_pkg, repo, activity_guid_map=None) -> list[dict]:
    """
    Return a list of class-info dicts for every Class element found directly
    inside *module_pkg* (non-recursive â€” classes live at the top level of the
    module package).

    Each class dict:
        {
            "name":        str,
            "stereotype":  str,
            "guid":        str,
            "source_file": str,
            "feature":     str,
            "variant":     str,
            "connectors":  list[dict],   # outgoing class-level connectors
            "operations":  list[dict],
        }

    Each connector dict:  {"type": str, "target_name": str, "target_desc": str}

    Each operation dict:
        {
            "name":            str,
            "return_type":     str,
            "scope":           str,
            "parameters":      list[dict],   # {name, type, kind}
            "ea_guid":         str,
            "implements":      str,
            "implements_guid": str,
            "extra_tags":      dict[str, str],
            "notes":           str,
        }
    """
    classes = []
    try:
        for el in module_pkg.Elements:
            if el.Type != "Class":
                continue

            source_file = _tagged_value(el, "SourceFile")
            if source_file and not source_file.endswith(".c"):
                source_file += ".c"

            # --- Outgoing class-level connectors ---
            connectors: list[dict] = []
            try:
                for conn in el.Connectors:
                    if conn.ClientID != el.ElementID:
                        continue
                    try:
                        target = repo.GetElementByID(conn.SupplierID)
                        t_type = (target.Type or "").strip()
                        t_stereo = (target.Stereotype or "").strip()
                        target_desc = f"{t_type} ({t_stereo})" if t_stereo else t_type
                        connectors.append({
                            "type":        (conn.Type or "").strip(),
                            "target_name": (target.Name or "").strip(),
                            "target_desc": target_desc,
                        })
                    except Exception:
                        pass
            except Exception:
                pass

            el_guid = (el.ElementGUID or "").strip()  # SW Unit Class GUID
            ops = []
            try:
                for op in el.Methods:
                    # Skip Macro operations
                    if (getattr(op, "Stereotype", "") or "").strip() == "Macro":
                        continue

                    params: list[dict] = []
                    try:
                        for p in op.Parameters:
                            params.append(_extract_parameter(p))
                    except Exception:
                        pass

                    # Primary: Activity Diagram ElementGUID from Behavior sub-package.
                    # Fallback: SW Unit (Class) ElementGUID — never use MethodGUID
                    # (action state GUID) as it is not a valid trace target.
                    ea_guid = (activity_guid_map or {}).get(op.Name or "", "") or el_guid

                    extra_tags: dict[str, str] = {}
                    try:
                        for tv in op.TaggedValues:
                            n = tv.Name
                            v = (tv.Value or "").strip()
                            if n in _EXTRA_OP_TAGS and v:
                                extra_tags[n] = v
                    except Exception:
                        pass

                    _scope = (getattr(op, "Scope", None) or "Public").strip()
                    ops.append({
                        "name":       op.Name or "",
                        "return_type": (op.ReturnType or "void").strip(),
                        "scope":      _scope,
                        "is_static":  _extract_operation_static(op, _scope),
                        "parameters": params,
                        "ea_guid":    ea_guid,
                        "extra_tags": extra_tags,
                        "notes":      (op.Notes or "")
                                      .replace("\r\n", " ")
                                      .replace("\n", " ")
                                      .strip(),
                    })
            except Exception:
                pass

            # Also include operations from realized Interfaces
            # (SW unit Class -> Realization -> Interface -> Methods)
            try:
                for conn in el.Connectors:
                    if (conn.Type or "").strip() not in ("Realization", "Realisation"):
                        continue
                    if conn.ClientID != el.ElementID:
                        continue
                    try:
                        iface = repo.GetElementByID(conn.SupplierID)
                        for op in iface.Methods:
                            if (getattr(op, "Stereotype", "") or "").strip() == "Macro":
                                continue
                            ea_guid = (activity_guid_map or {}).get(op.Name or "", "") or el_guid
                            params = []
                            try:
                                for p in op.Parameters:
                                    params.append(_extract_parameter(p))
                            except Exception:
                                pass
                            if (op.Name or "") in set(o["name"] for o in ops):
                                continue  # skip duplicate (already in class Methods)
                            _scope = (getattr(op, "Scope", None) or "Public").strip()
                            ops.append({
                                "name":        op.Name or "",
                                "return_type": (op.ReturnType or "void").strip(),
                                "scope":       _scope,
                                "is_static":   _extract_operation_static(op, _scope),
                                "parameters":  params,
                                "ea_guid":     ea_guid,
                                "extra_tags":  {},
                                "notes":       "",
                            })
                    except Exception:
                        pass
            except Exception:
                pass

            classes.append({
                "name":        el.Name or "",
                "stereotype":  (el.Stereotype or "").strip(),
                "guid":        (el.ElementGUID or "").strip(),
                "source_file": source_file,
                "feature":     _tagged_value(el, "Feature"),
                "variant":     _tagged_value(el, "Variant"),
                "connectors":  connectors,
                "operations":  ops,
            })
    except Exception as exc:
        print(f"WARNING: Could not iterate elements in module package: {exc}", file=sys.stderr)

    return classes


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def _md_cell(text: str) -> str:
    """Escape pipe characters in markdown table cells."""
    return text.replace("|", "\\|")


def _trace_id(func_name: str, ea_guid: str) -> str:
    """Return 'FunctionName|{GUID}' or empty string when no GUID."""
    if not ea_guid:
        return ""
    return f"{func_name}|{ea_guid}"


def _format_signature(return_type: str, params: list[dict]) -> str:
    """Merge return type and parameters into a single markdown table cell."""
    ret = f"`{_md_cell(return_type)}`" if return_type else "`void`"
    if not params:
        return ret
    parts = []
    for p in params:
        kind  = f"[{p['kind']}] " if p["kind"] else ""
        ptype = p["type"]
        pname = p["name"]
        parts.append(_md_cell(f"{kind}{ptype} {pname}".strip()))
    return ret + "<br>" + "<br>".join(parts)


def generate_markdown(module_name: str, module_path: str, classes: list[dict]) -> str:
    """Render the flat-table format matching SwMod_TouchSM_Functions.md."""
    lines: list[str] = []

    feature = next((c["feature"] for c in classes if c.get("feature")), "")
    variant = next((c["variant"] for c in classes if c.get("variant")), "")

    feature_line = ""
    if feature or variant:
        parts = []
        if feature:
            parts.append(f"**Feature:** `{feature}`")
        if variant:
            parts.append(f"**Variant:** `{variant}`")
        feature_line = " | ".join(parts)

    lines.append(f"# {module_name} â€“ Function List\n")
    lines.append(f"**Module:** `{module_name}`  ")
    lines.append(f"**EA Path:** `{module_path}`  ")
    if feature_line:
        lines.append(feature_line)
    lines.append("")
    lines.append("---")
    lines.append("")

    all_summary: list[tuple[str, str, int]] = []

    for cls in classes:
        cls_name = cls["name"]
        src      = cls["source_file"] or "â€”"
        ops      = cls["operations"]
        count    = len(ops)
        all_summary.append((cls_name, src, count))

        if count == 0:
            continue

        cls_guid      = cls.get("guid", "")
        cls_trace_id  = f"{cls_name}|{cls_guid}" if cls_guid else ""

        lines.append(f"## {cls_name} Â· `{src}`")
        if cls_trace_id:
            lines.append(f"**Trace:** `{cls_trace_id}`")
        lines.append("")
        lines.append("| # | Function | Trace ID |")
        lines.append("|---|---|---|")

        for i, op in enumerate(ops, start=1):
            trace_label = op["name"] if op.get("ea_guid", "") != cls_guid else cls_name
            tid        = _trace_id(trace_label, op["ea_guid"])
            trace_cell = tid if tid else "â€”"
            lines.append(
                f"| {i} "
                f"| `{_md_cell(op['name'])}` "
                f"| {trace_cell} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Class | Source File | Function Count |")
    lines.append("|---|---|---|")
    total = 0
    for cls_name, src, count in all_summary:
        lines.append(f"| `{cls_name}` | `{src}` | {count} |")
        total += count
    lines.append(f"| **Total** | | **{total}** |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def export_module_functions(
    module_name: str,
    output_dir: str | None = None,
    path_filter: str | None = None,
) -> str:
    """
    Core reusable function.

    Parameters
    ----------
    module_name : str
        Exact EA package name to search for.
    output_dir : str, optional
        Directory where the .md file is written.  Defaults to
        <project_root>/doc/.
    path_filter : str, optional
        Substring that must appear in the full EA path.  Use this to
        disambiguate when multiple packages share the same name.
        Example: path_filter="Platform"

    Returns
    -------
    str
        Absolute path of the generated markdown file.
    """
    if output_dir is None:
        output_dir = _DEFAULT_DOC_DIR

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

        activity_map = _build_activity_guid_map(module_pkg)
        classes = extract_classes(module_pkg, repo, activity_map)
        if not classes:
            print(
                f"\nERROR: No Class elements found inside module '{module_name}'.\n"
                f"       EA path: {module_path}\n",
                file=sys.stderr,
            )
            sys.exit(1)

        total_ops = sum(len(c["operations"]) for c in classes)
        print(
            f"Extracted {len(classes)} class(es), {total_ops} operation(s) total."
        )

        md_content = generate_markdown(module_name, module_path, classes)

        out_path = os.path.join(output_dir, f"{module_name}.md")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(md_content)

        print(f"Written: {out_path}")

        # Write Functions JSON for gtest_traceability.py
        json_dir = os.path.join(_PROJECT_ROOT, "ai_output", "doc")
        os.makedirs(json_dir, exist_ok=True)
        json_out = os.path.join(json_dir, f"{module_name}_Functions.json")
        json_data = _build_functions_json(module_name, module_path, classes, activity_map)
        with open(json_out, "w", encoding="utf-8") as fh:
            import json as _json
            _json.dump(json_data, fh, indent=2, ensure_ascii=False)
        print(f"Written: {json_out}")

        return out_path

    finally:
        try:
            repo.CloseFile()
            repo.Exit()
        except Exception:
            pass


def _collect_modules(parent, current_path: str, results: list) -> None:
    """
    Recursively walk *parent* and collect every package whose name starts
    with 'SwMod_'.  Appends (pkg, full_dot_path) to *results*.
    """
    try:
        for pkg in parent.Packages:
            pkg_path = f"{current_path}.{pkg.Name}" if current_path else pkg.Name
            if pkg.Name.startswith("SwMod_"):
                results.append((pkg, pkg_path))
            else:
                _collect_modules(pkg, pkg_path, results)
    except Exception:
        pass


def _path_filter_matches(path: str, f: str) -> bool:
    """Return True when *f* matches a complete dot-separated segment of *path*."""
    if "." in f:
        return f in path
    return f in path.split(".")


def export_all_modules(
    scope_filter: str | None = None,
    output_dir: str | None = None,
) -> list[str]:
    """
    Discover every SwMod_* package in the EA project (optionally restricted to
    paths that contain *scope_filter* as a whole path segment) and generate one
    .md file per module.

    Parameters
    ----------
    scope_filter : str, optional
        Whole-segment path filter, e.g. 'Platform', 'SwSubSys_TouchCtl'.
        When given, only modules whose EA path contains that segment are
        exported.  Deduplication: if the same module name appears in both a
        'Platform' and a 'PlatformConfigs' path and *scope_filter* is
        'Platform', only the 'Platform' occurrence is included.
    output_dir : str, optional
        Output directory.  Defaults to <project_root>/doc/.

    Returns
    -------
    list[str]
        Paths of all generated markdown files.
    """
    if output_dir is None:
        output_dir = _DEFAULT_DOC_DIR
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
        # Collect all SwMod_* packages across all models
        all_modules: list[tuple[object, str]] = []
        for model in repo.Models:
            _collect_modules(model, model.Name, all_modules)

        # Apply scope filter
        if scope_filter:
            all_modules = [
                (pkg, path) for pkg, path in all_modules
                if _path_filter_matches(path, scope_filter)
            ]

        if not all_modules:
            print(
                f"No SwMod_* packages found"
                + (f" under scope '{scope_filter}'" if scope_filter else "")
                + ".",
                file=sys.stderr,
            )
            sys.exit(1)

        # Deduplicate: prefer entries whose path does NOT contain 'PlatformConfigs'
        # when a non-PlatformConfigs match exists for the same module name.
        by_name: dict[str, list[tuple[object, str]]] = {}
        for pkg, path in all_modules:
            by_name.setdefault(pkg.Name, []).append((pkg, path))

        deduped: list[tuple[object, str]] = []
        for name, candidates in by_name.items():
            if len(candidates) == 1:
                deduped.append(candidates[0])
            else:
                preferred = [c for c in candidates if "PlatformConfigs" not in c[1]]
                deduped.extend(preferred if preferred else candidates)

        deduped.sort(key=lambda x: x[1])  # stable alphabetical order

        print(f"Found {len(deduped)} module(s):")
        for _, path in deduped:
            print(f"  {path}")
        print()

        for module_pkg, module_path in deduped:
            module_name = module_pkg.Name
            print(f"Processing {module_name} ...")
            try:
                activity_map = _build_activity_guid_map(module_pkg)
                classes = extract_classes(module_pkg, repo, activity_map)
                if not classes:
                    print(f"  WARNING: no Class elements found, skipping.")
                    continue
                total_ops = sum(len(c["operations"]) for c in classes)
                print(f"  {len(classes)} class(es), {total_ops} operation(s)")
                md_content = generate_markdown(module_name, module_path, classes)
                out_path = os.path.join(output_dir, f"{module_name}.md")
                with open(out_path, "w", encoding="utf-8") as fh:
                    fh.write(md_content)
                print(f"  Written: {out_path}")
                json_dir = os.path.join(_PROJECT_ROOT, "ai_output", "doc")
                os.makedirs(json_dir, exist_ok=True)
                json_out = os.path.join(json_dir, f"{module_name}_Functions.json")
                json_data = _build_functions_json(module_name, module_path, classes, activity_map)
                with open(json_out, "w", encoding="utf-8") as fh:
                    import json as _json
                    _json.dump(json_data, fh, indent=2, ensure_ascii=False)
                print(f"  Written: {json_out}")
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


def main(argv: list[str]) -> None:
    """
    Usage
    -----
    Single module:
        python scripts/export_module_functions.py SwMod_TouchSM [--filter Platform] [output_dir]

    All modules under a subsystem or platform:
        python scripts/export_module_functions.py --scope SwSubSys_TouchCtl [output_dir]
        python scripts/export_module_functions.py --scope Platform [output_dir]

    All modules (no filter):
        python scripts/export_module_functions.py [output_dir]
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="export_module_functions",
        description=(
            "Export EA module function lists to Markdown.\n"
            "Pass a module name to export a single module, or use --scope / no args "
            "to discover and export all SwMod_* packages."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "module",
        nargs="?",
        default=None,
        help="Exact module name (e.g. SwMod_TouchSM). Omit to export all modules.",
    )
    parser.add_argument(
        "-f", "--filter",
        dest="path_filter",
        metavar="SEGMENT",
        help="Path segment to disambiguate a single-module lookup (e.g. Platform).",
    )
    parser.add_argument(
        "-s", "--scope",
        dest="scope",
        metavar="SEGMENT",
        help=(
            "Limit multi-module discovery to packages under this path segment "
            "(e.g. SwSubSys_TouchCtl, Platform). Ignored when a module name is given."
        ),
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help="Directory where .md files are written (default: doc/).",
    )

    args = parser.parse_args(argv[1:])

    if args.module:
        # Single-module mode (existing behaviour)
        export_module_functions(args.module, args.output_dir, args.path_filter)
    else:
        # Multi-module discovery mode
        export_all_modules(args.scope, args.output_dir)


if __name__ == "__main__":
    main(sys.argv)


