"""
Tool: export_arch_design.py

Single entry point for both architecture-design exports that read the
`SwSys_/SwSubSys_/SwMod_` package tree in the EA repository:

  markdown   Human-readable Markdown docs (one .md per package): breadcrumb
             path, notes, sub-packages, elements, diagrams. Whole-tree walk,
             optionally narrowed with --scope (breadcrumb substring).
  json       Software Architecture Design traceability JSON, mirroring the
             SwArchDesignExpToTraceIt XML format produced by the MDD/TraceIT
             export plugin (GUID, tagged values, TableTracedTo connectors).
             Single-package lookup or --level/--prefix + --scope discovery.

Usage
-----
    .venv32\\Scripts\\python.exe export_arch_design.py markdown [--output DIR] [--scope NAME]
    .venv32\\Scripts\\python.exe export_arch_design.py json [package] [options]

Examples
--------
    # Markdown: whole model / one subsystem (+ its modules) / one platform
    .venv32\\Scripts\\python.exe export_arch_design.py markdown
    .venv32\\Scripts\\python.exe export_arch_design.py markdown --scope SwSubSys_TouchCtl
    .venv32\\Scripts\\python.exe export_arch_design.py markdown --scope Platform

    # JSON: single package, or discover by level under a scope
    .venv32\\Scripts\\python.exe export_arch_design.py json SwSubSys_AmbientSense
    .venv32\\Scripts\\python.exe export_arch_design.py json SwSubSys_AmbientSense --filter Platform
    .venv32\\Scripts\\python.exe export_arch_design.py json --level subsystem --scope Platform
    .venv32\\Scripts\\python.exe export_arch_design.py json --level all --scope Platform

JSON output
-----------
One JSON file per package: `ai_output/arch_design/<platform|project>/<PackageName>_arch_design.json`
{
  "document": "SwSubSys_AmbientSense{GUID}|EA_file.eap",
  "documentType": "SwArchDesign",
  "documentLocationLocal": "...",
  "packageName": "SwSubSys_AmbientSense",
  "eaPath": "...",
  "level": "subsystem",
  "elements": [
    {
      "id": "{GUID}", "name": "AmbSTemp", "status": "released",
      "safetyLevel": "QM", "securityOrPrivacy": "No", "tsh": "Yes",
      "reqType": "Functional", "priority": "Medium",
      "variants": "DNGA2_COMMON_DS", "packageName": "SwSubSys_AmbientSense",
      "eaReqType": "SwModule",
      "features": [{"featureName": "EnBlLedPcbTmp", "featureVariant": "STD_ON"}],
      "ltr": "non-LTR",
      "tracedTo": [{"reqDocType": "SwReqSpec", "tracedToId": "SRSC_AmbientSenseAndInput_196", "tracedToName": ""}]
    }
  ]
}

Markdown output
----------------
`ai_output/arch_design/<PackageName>.md` (or `<PackageName>__<PackageID>.md`
on a name collision) - see build_markdown() for the exact structure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ea_connect as ea
import export_sequence_diagrams as seq

DEFAULT_MARKDOWN_OUTPUT = os.path.join(ea.REPO_ROOT, "ai_output", "arch_design")
DEFAULT_DIAGRAMS_DIR = seq.DEFAULT_OUTPUT
_DEFAULT_JSON_OUTPUT_DIR = os.path.join(ea.REPO_ROOT, "ai_output", "arch_design")

INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*]')

_LEVEL_PREFIXES: dict[str, list[str]] = {
    "module":    ["SwMod_"],
    "subsystem": ["SwSubSys_"],
    "system":    ["SwSys_"],
    "all":       ["SwMod_", "SwSubSys_", "SwSys_"],
}


def _level_label(pkg_name: str) -> str:
    if pkg_name.startswith("SwMod_"):
        return "module"
    if pkg_name.startswith("SwSubSys_"):
        return "subsystem"
    if pkg_name.startswith("SwSys_"):
        return "system"
    return "unknown"


# ===========================================================================
# Shared helpers
# ===========================================================================

def sanitize_filename(name):
    cleaned = INVALID_FS_CHARS.sub("_", name).strip()
    return cleaned or "unnamed"


def is_template_placeholder(name):
    return "<" in name or ">" in name


def safe_notes(elem_or_pkg):
    try:
        return (elem_or_pkg.Notes or "").strip()
    except Exception:
        return ""


# ===========================================================================
# Markdown export
# ===========================================================================

def describe_elements(package):
    lines = []
    elements = list(ea.iter_elements(package))
    if not elements:
        return lines
    lines.append("| # | Name | Type | Stereotype | Notes |")
    lines.append("|---|------|------|------------|-------|")
    for i, elem in enumerate(elements, 1):
        notes = safe_notes(elem).replace("\n", " ").replace("|", "\\|")
        if len(notes) > 120:
            notes = notes[:117] + "..."
        stereotype = elem.Stereotype or "-"
        lines.append(f"| {i} | {elem.Name} | {elem.Type} | {stereotype} | {notes or '-'} |")
    return lines


def describe_diagrams(package):
    lines = []
    diagrams = list(ea.iter_diagrams(package))
    if not diagrams:
        return lines
    lines.append("| # | Name | Type |")
    lines.append("|---|------|------|")
    for i, d in enumerate(diagrams, 1):
        lines.append(f"| {i} | {d.Name or '(unnamed)'} | {d.Type} |")
    return lines


def describe_subpackages(package):
    lines = []
    children = list(ea.iter_subpackages(package))
    if not children:
        return lines
    for c in children:
        marker = " (template placeholder, skipped)" if is_template_placeholder(c.Name) else ""
        lines.append(f"- **{c.Name}**{marker} ({c.Elements.Count} elements, {c.Diagrams.Count} diagrams)")
    return lines


def describe_sequence_diagrams(seq_diagrams, seq_manifest, md_output_dir, diagrams_dir):
    """Cross-reference Type=='Sequence' diagrams belonging to this package (as
    discovered by export_sequence_diagrams.find_sequence_diagrams(), which
    finds Element-owned sequence diagrams that never show up in
    describe_diagrams()/Package.Diagrams - see that function's docstring).
    Links to the .puml file if export_sequence_diagrams.py has already
    exported it (per its resume manifest), otherwise says so."""
    lines = []
    if not seq_diagrams:
        return lines
    try:
        rel_dir = os.path.relpath(diagrams_dir, md_output_dir).replace(os.sep, "/")
    except ValueError:
        rel_dir = diagrams_dir.replace(os.sep, "/")  # e.g. different drives on Windows
    lines.append("| # | Name | File |")
    lines.append("|---|------|------|")
    for i, d in enumerate(seq_diagrams, 1):
        name = d.Name or f"diagram_{d.DiagramID}"
        entry = seq_manifest.get(str(d.DiagramID))
        if entry:
            link = f"{rel_dir}/{entry['fname']}.puml"
            lines.append(f"| {i} | {name} | [{entry['fname']}.puml]({link}) |")
        else:
            lines.append(f"| {i} | {name} | _not yet exported - run export_sequence_diagrams.py_ |")
    return lines


def build_markdown(package, breadcrumb, seq_diagrams, seq_manifest, output_dir, diagrams_dir):
    notes = safe_notes(package)
    md = []
    md.append(f"# {package.Name}")
    md.append("")
    md.append(f"**Package path:** `{' / '.join(breadcrumb)}`  ")
    md.append(f"**PackageID:** {package.PackageID}")
    md.append("")
    md.append("## Purpose / Notes")
    md.append("")
    md.append(notes if notes else "_No notes recorded in EA for this package._")
    md.append("")
    md.append("## Sub-packages")
    md.append("")
    sub_lines = describe_subpackages(package)
    md.extend(sub_lines if sub_lines else ["_None._"])
    md.append("")
    md.append("## Elements")
    md.append("")
    elem_lines = describe_elements(package)
    md.extend(elem_lines if elem_lines else ["_None directly in this package._"])
    md.append("")
    md.append("## Diagrams")
    md.append("")
    diag_lines = describe_diagrams(package)
    md.extend(diag_lines if diag_lines else ["_None directly in this package._"])
    md.append("")
    md.append("## Sequence Diagrams")
    md.append("")
    seq_lines = describe_sequence_diagrams(seq_diagrams, seq_manifest, output_dir, diagrams_dir)
    md.extend(seq_lines if seq_lines else [
        "_None found for this package. (Sequence diagrams are Element-owned in this "
        "model, not Package-owned, so they are cross-referenced here separately from "
        "the 'Diagrams' section above - see export_sequence_diagrams.py.)_"
    ])
    md.append("")
    return "\n".join(md)


def run_markdown_export(args) -> None:
    os.makedirs(args.output, exist_ok=True)

    project = ea.resolve_project_path()
    print(f"[info] Opening: {project}")
    repo = ea.connect(project)

    exported = []
    skipped_templates = []
    used_names = {}

    try:
        print("[info] Discovering sequence diagrams for cross-referencing...")
        diagrams_by_pkg_id = {}
        for d, _bc in seq.find_sequence_diagrams(repo):
            diagrams_by_pkg_id.setdefault(d.PackageID, []).append(d)
        seq_manifest = seq.load_manifest(args.diagrams_dir)
        print(f"[info] Found {sum(len(v) for v in diagrams_by_pkg_id.values())} sequence "
              f"diagram(s) across {len(diagrams_by_pkg_id)} package(s) for cross-referencing "
              f"({len(seq_manifest)} already exported to {args.diagrams_dir}).")

        for root in ea.iter_root_packages(repo):
            def walk(pkg, breadcrumb):
                here = breadcrumb + [pkg.Name]
                if pkg.Name == args.skip_templates_branch:
                    return  # entire branch is generic templates, not real design content
                if ea.matches_design_prefix(pkg.Name):
                    if is_template_placeholder(pkg.Name):
                        skipped_templates.append(" / ".join(here))
                    elif args.scope is None or any(args.scope in part for part in here):
                        base = sanitize_filename(pkg.Name)
                        used_names[base] = used_names.get(base, 0) + 1
                        fname = base if used_names[base] == 1 else f"{base}__{pkg.PackageID}"
                        out_path = os.path.join(args.output, f"{fname}.md")
                        seq_diagrams_here = diagrams_by_pkg_id.get(pkg.PackageID, [])
                        content = build_markdown(
                            pkg, here, seq_diagrams_here, seq_manifest, args.output, args.diagrams_dir
                        )
                        with open(out_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        exported.append(out_path)
                        print(f"[export] {' / '.join(here)}  ->  {out_path}")
                for child in ea.iter_subpackages(pkg):
                    walk(child, here)

            walk(root, [])
    finally:
        ea.disconnect(repo)

    print(f"\n[summary] Exported {len(exported)} Markdown design documents to {args.output}")
    if skipped_templates:
        print(f"[summary] Skipped {len(skipped_templates)} template-placeholder packages:")
        for t in skipped_templates:
            print(f"  - {t}")


# ===========================================================================
# JSON traceability export
# ===========================================================================

# Tagged-value names as they appear in EA
# (the tool tries each alias in order and uses the first non-empty match)
_TV_STATUS          = ("Status",)
_TV_SAFETY          = ("SafetyLevel", "Safety Level", "ASIL")
_TV_SECURITY        = ("SecurityOrPrivacy", "Security", "SecurityAndPrivacy")
_TV_TSH             = ("TSH",)
_TV_REQ_TYPE        = ("Req_Type_sv", "Req_Type", "Type", "RequirementType")
_TV_PRIORITY        = ("priority", "Priority")
_TV_VARIANTS        = ("Variants_sv", "Variants", "Variant")
_TV_LTR             = ("LTR_sv", "LTR", "TechnicalRegulation")
_TV_FEATURES        = ("Features", "Feature")

# Tagged values on connectors that carry the reqDocType
_TV_CONN_DOC_TYPE   = ("reqDocType", "DocumentType", "DocType")

# Connector types considered as traceability links
_TRACE_CONN_TYPES   = {"Trace", "Dependency", "Realization", "Abstraction", "Refine"}


def _safe_str(val) -> str:
    try:
        return (val or "").strip()
    except Exception:
        return ""


def _all_tvs(obj) -> dict[str, str]:
    """Return all tagged values on *obj* as a dict."""
    result: dict[str, str] = {}
    try:
        for tv in obj.TaggedValues:
            result[tv.Name] = _safe_str(tv.Value)
    except Exception:
        pass
    return result


def _parse_features(raw: str) -> list[dict]:
    """
    Try to parse a Features tagged-value string into
    [{featureName, featureVariant}, ...].

    EA often stores this as a comma/semicolon-separated list like:
        EnBlLedPcbTmp=STD_ON;EnBlPcbTmp=STD_OFF
    or simply a feature name.
    """
    features: list[dict] = []
    if not raw:
        return features
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            fname, fvar = part.split("=", 1)
            features.append({"featureName": fname.strip(), "featureVariant": fvar.strip()})
        else:
            features.append({"featureName": part, "featureVariant": ""})
    return features


def _infer_req_doc_type(target_pkg_name: str) -> str:
    """
    Infer the reqDocType from the name of the target element's package.
    Mirrors common project naming conventions.
    """
    name = target_pkg_name.lower()
    if "swreqspec" in name or "srsc" in name or "reqspec" in name:
        return "SwReqSpec"
    if "sysreq" in name or "srs" in name or "systemreq" in name:
        return "SysReqSpec"
    if "safetyreg" in name or "ltr" in name:
        return "SafetyReq"
    return "SwReqSpec"  # default


def _element_package_name(repo, element_id: int) -> str:
    try:
        el = repo.GetElementByID(element_id)
        pkg = repo.GetPackageByID(el.PackageID)
        return _safe_str(pkg.Name)
    except Exception:
        return ""


def _extract_traced_to(repo, el) -> list[dict]:
    """
    Return TracedTo entries for outgoing Trace/Dependency/Realization
    connectors from *el*.
    """
    traced: list[dict] = []
    try:
        for conn in el.Connectors:
            if conn.ClientID != el.ElementID:
                continue  # only outgoing (el -> target)
            conn_type = _safe_str(conn.Type)
            if conn_type not in _TRACE_CONN_TYPES:
                continue
            try:
                target = repo.GetElementByID(conn.SupplierID)
                target_name = _safe_str(target.Name)
                target_alias = _safe_str(getattr(target, "Alias", None) or "")

                # Prefer Alias as TracedToId if it looks like a requirement ID,
                # otherwise fall back to Name
                traced_to_id = target_alias if target_alias else target_name
                traced_to_name = target_name if target_alias else ""

                # reqDocType: try connector tagged values first, then infer
                conn_tvs = _all_tvs(conn)
                req_doc_type = ""
                for tv_name in _TV_CONN_DOC_TYPE:
                    if tv_name in conn_tvs and conn_tvs[tv_name]:
                        req_doc_type = conn_tvs[tv_name]
                        break
                if not req_doc_type:
                    target_pkg_name = _element_package_name(repo, conn.SupplierID)
                    req_doc_type = _infer_req_doc_type(target_pkg_name)

                traced.append({
                    "reqDocType":    req_doc_type,
                    "tracedToId":    traced_to_id,
                    "tracedToName":  traced_to_name,
                    "connectorType": conn_type,
                })
            except Exception:
                pass
    except Exception:
        pass
    return traced


def _extract_element(repo, el, pkg_name: str) -> dict:
    """Extract one EA element as a SwArchDesignReq-compatible dict."""
    el_guid  = _safe_str(el.ElementGUID)
    el_name  = _safe_str(el.Name)
    stereo   = _safe_str(el.Stereotype) or el.Type or ""

    tvs = _all_tvs(el)

    def tv_pick(*names: str) -> str:
        for n in names:
            if n in tvs and tvs[n]:
                return tvs[n]
        return ""

    features_raw = tv_pick(*_TV_FEATURES)
    features = _parse_features(features_raw)

    traced_to = _extract_traced_to(repo, el)

    return {
        "id":                el_guid,
        "name":              el_name,
        "status":            tv_pick(*_TV_STATUS),
        "safetyLevel":       tv_pick(*_TV_SAFETY),
        "securityOrPrivacy": tv_pick(*_TV_SECURITY),
        "tsh":               tv_pick(*_TV_TSH),
        "reqType":           tv_pick(*_TV_REQ_TYPE),
        "priority":          tv_pick(*_TV_PRIORITY),
        "variants":          tv_pick(*_TV_VARIANTS),
        "packageName":       pkg_name,
        "eaReqType":         stereo,
        "features":          features,
        "ltr":               tv_pick(*_TV_LTR),
        "tracedTo":          traced_to,
    }


def extract_arch_design(
    pkg,
    repo,
    pkg_name: str,
    recurse: bool = False,
) -> list[dict]:
    """
    Extract SwArchDesignReq entries from *pkg*.

    Parameters
    ----------
    recurse : bool
        When True, also scans sub-packages recursively.  When False (default)
        only the direct child elements of *pkg* are included - matching the
        SwArchDesign convention where each package represents one design unit.
    """
    elements: list[dict] = []

    def _scan(p):
        try:
            for el in p.Elements:
                # Skip diagram placeholder elements; keep Activity only if it
                # has at least one outgoing trace/dependency connector
                if el.Type in ("Text", "Note", "Boundary"):
                    continue
                if el.Type == "Activity":
                    has_trace = any(
                        c.ClientID == el.ElementID
                        and c.Type in _TRACE_CONN_TYPES
                        for c in el.Connectors
                    )
                    if not has_trace:
                        continue
                elements.append(_extract_element(repo, el, pkg_name))
        except Exception as exc:
            print(f"  WARNING: could not scan elements: {exc}", file=sys.stderr)

        if recurse:
            try:
                for sub in p.Packages:
                    _scan(sub)
            except Exception:
                pass

    _scan(pkg)
    return elements


def build_arch_design_json(
    pkg_name: str,
    pkg_path: str,
    pkg_guid: str,
    level: str,
    elements: list[dict],
    ea_project: str,
    document_location_local: str,
) -> dict:
    ea_file = os.path.basename(ea_project)
    return {
        "document":             f"{pkg_name}{pkg_guid}|{ea_file}",
        "documentType":         "SwArchDesign",
        "documentLocationLocal": document_location_local,
        "packageName":          pkg_name,
        "eaPath":               pkg_path,
        "level":                level,
        "elements":             elements,
    }


# ---------------------------------------------------------------------------
# Package discovery (mirrors export_traceability.py helpers)
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


def find_package(
    repo, pkg_name: str, ea_project: str, path_filter: str | None = None
) -> tuple[object, str]:
    results: list[tuple[object, str]] = []
    for model in repo.Models:
        _search_package_all(model, pkg_name, model.Name, results)

    if path_filter:
        results = [r for r in results if _path_filter_matches(r[1], path_filter)]

    if not results:
        print(
            f"\nERROR: Package '{pkg_name}'"
            + (f" with path containing '{path_filter}'" if path_filter else "")
            + f" was not found.\n       Project: {ea_project}\n",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(results) > 1:
        print(
            f"\nERROR: Multiple packages named '{pkg_name}' found.\n"
            "Candidates:\n",
            file=sys.stderr,
        )
        for i, (_, p) in enumerate(results, 1):
            print(f"  [{i}] {p}", file=sys.stderr)
        print(
            f"\nRe-run with --filter, e.g.:\n"
            f"  export_arch_design.py json {pkg_name} --filter Platform\n",
            file=sys.stderr,
        )
        sys.exit(1)

    return results[0]


def _collect_packages_by_prefix(
    parent, current_path: str, results: list, prefixes: list[str]
) -> None:
    try:
        for pkg in parent.Packages:
            pkg_path = f"{current_path}.{pkg.Name}" if current_path else pkg.Name
            if any(pkg.Name.startswith(p) for p in prefixes):
                results.append((pkg, pkg_path))
            else:
                _collect_packages_by_prefix(pkg, pkg_path, results, prefixes)
    except Exception:
        pass


def _pkg_guid(pkg) -> str:
    try:
        # Packages expose their GUID via .PackageGUID or through the Element
        return _safe_str(getattr(pkg, "PackageGUID", None) or "")
    except Exception:
        return ""


def _branch_from_path(ea_path: str) -> str:
    """Return 'platform' or 'project' based on the EA package path."""
    if ".Platform." in ea_path:
        return "platform"
    if ".Project." in ea_path:
        return "project"
    return "platform"  # safe default


def export_package_arch_design(
    repo,
    ea_project: str,
    document_location_local: str,
    pkg_name: str,
    output_dir: str | None = None,
    path_filter: str | None = None,
    recurse: bool = False,
) -> str:
    if output_dir is None:
        output_dir = _DEFAULT_JSON_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    print(f"Searching for package '{pkg_name}'...")
    pkg, pkg_path = find_package(repo, pkg_name, ea_project, path_filter)
    print(f"Found: {pkg_path}")

    level = _level_label(pkg_name)
    guid  = _pkg_guid(pkg)
    elements = extract_arch_design(pkg, repo, pkg_name, recurse)

    total_traced = sum(len(e["tracedTo"]) for e in elements)
    print(f"Extracted {len(elements)} element(s), {total_traced} traced-to link(s).")

    data = build_arch_design_json(
        pkg_name, pkg_path, guid, level, elements, ea_project, document_location_local
    )
    branch    = _branch_from_path(pkg_path)
    branch_dir = os.path.join(output_dir, branch)
    os.makedirs(branch_dir, exist_ok=True)
    out_path = os.path.join(branch_dir, f"{pkg_name}_arch_design.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"Written: {out_path}")
    return out_path


def export_all_arch_design(
    repo,
    ea_project: str,
    document_location_local: str,
    scope_filter: str | None = None,
    output_dir: str | None = None,
    prefixes: list[str] | None = None,
    recurse: bool = False,
) -> list[str]:
    if prefixes is None:
        prefixes = ["SwSubSys_"]
    if output_dir is None:
        output_dir = _DEFAULT_JSON_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    generated: list[str] = []

    all_pkgs: list[tuple[object, str]] = []
    for model in repo.Models:
        _collect_packages_by_prefix(model, model.Name, all_pkgs, prefixes)

    if scope_filter:
        all_pkgs = [
            (pkg, path) for pkg, path in all_pkgs
            if _path_filter_matches(path, scope_filter)
        ]

    if not all_pkgs:
        prefix_str = ", ".join(f"'{p}*'" for p in prefixes)
        print(
            f"No packages matching {prefix_str} found"
            + (f" under scope '{scope_filter}'" if scope_filter else "")
            + ".",
            file=sys.stderr,
        )
        sys.exit(1)

    # Deduplicate: keep one copy per package name.
    #
    # This model has duplicate-named "container" packages (e.g. an empty
    # SwSubSys_AmbientSense shell living under a mismatched ".SwMod." tree
    # segment, alongside the real, populated SwSubSys_AmbientSense living
    # under its own ".SwSubSys." segment - see repo memory / regression
    # test notes). The original heuristic here picked purely on path
    # substrings (any ".SwMod." segment ranked highest, regardless of
    # whether it actually contained anything), which could pick the empty
    # shell over the real package. "Real" element count (excluding
    # Text/Note/Boundary placeholder elements - a PlatformConfigs template
    # branch is typically padded with instructional Notes, which would
    # otherwise make it look more "populated" than it really is) is a far
    # more reliable signal of "which copy is the real one" than a path guess,
    # so it is now the primary criterion; the original path-based heuristic
    # is kept only as a tiebreaker for genuine ties.
    #
    # Priority (highest first):
    #   1. More non-Text/Note/Boundary elements directly in the package
    #   2. Non-PlatformConfigs path (PlatformConfigs is a template/config
    #      scaffold branch, not real design content)
    #   3. Non-PlatformConfigs AND SwMod in path  (original heuristic)
    #   4. Non-PlatformConfigs AND SwSubSys in path
    #   5. PlatformConfigs copies (fallback)
    by_name: dict[str, list[tuple[object, str]]] = {}
    for pkg, path in all_pkgs:
        by_name.setdefault(pkg.Name, []).append((pkg, path))

    def _count_real_elements(pkg) -> int:
        try:
            return sum(1 for el in pkg.Elements if el.Type not in ("Text", "Note", "Boundary"))
        except Exception:
            return 0

    def _pick_priority(pkg, path: str) -> tuple[int, int]:
        n_elements = _count_real_elements(pkg)
        no_platform_cfg = "PlatformConfigs" not in path
        is_swmod_path   = ".SwMod." in path
        if no_platform_cfg and is_swmod_path:
            path_rank = 0
        elif no_platform_cfg:
            path_rank = 1
        else:
            path_rank = 2
        return (-n_elements, path_rank)

    deduped: list[tuple[object, str]] = []
    for name, candidates in by_name.items():
        if len(candidates) == 1:
            deduped.append(candidates[0])
        else:
            best_priority = min(_pick_priority(c[0], c[1]) for c in candidates)
            preferred = [c for c in candidates if _pick_priority(c[0], c[1]) == best_priority]
            deduped.append(preferred[0])

    deduped.sort(key=lambda x: x[1])

    print(f"Found {len(deduped)} package(s):")
    for _, path in deduped:
        print(f"  {path}")
    print()

    for pkg, pkg_path in deduped:
        pkg_name = pkg.Name
        lbl  = _level_label(pkg_name)
        guid = _pkg_guid(pkg)
        print(f"Processing {pkg_name} [{lbl}] ...")
        try:
            elements = extract_arch_design(pkg, repo, pkg_name, recurse)
            total_traced = sum(len(e["tracedTo"]) for e in elements)
            print(f"  {len(elements)} element(s), {total_traced} traced-to link(s)")
            data = build_arch_design_json(
                pkg_name, pkg_path, guid, lbl, elements, ea_project, document_location_local
            )
            branch     = _branch_from_path(pkg_path)
            branch_dir = os.path.join(output_dir, branch)
            os.makedirs(branch_dir, exist_ok=True)
            out_path = os.path.join(branch_dir, f"{pkg_name}_arch_design.json")
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            print(f"  Written: {out_path}")
            generated.append(out_path)
        except Exception as exc:
            print(f"  ERROR processing {pkg_name}: {exc}", file=sys.stderr)

    print(f"\nDone. {len(generated)} file(s) generated.")
    return generated


def run_json_export(args) -> None:
    project = ea.resolve_project_path()
    document_location_local = os.environ.get("EA_DOCUMENT_LOCATION_LOCAL", "") or project

    print(f"Opening EA project: {project}")
    repo = ea.connect(project)
    try:
        if args.package:
            export_package_arch_design(
                repo, project, document_location_local,
                args.package, args.output_dir, args.path_filter, args.recurse,
            )
        else:
            prefixes = args.prefixes or _LEVEL_PREFIXES.get(args.level, ["SwSubSys_"])
            export_all_arch_design(
                repo, project, document_location_local,
                args.scope, args.output_dir, prefixes, args.recurse,
            )
    finally:
        ea.disconnect(repo)


# ===========================================================================
# CLI
# ===========================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_arch_design",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="format", required=True)

    md = sub.add_parser(
        "markdown",
        help="Export human-readable Markdown design docs (one .md per package)",
    )
    md.add_argument("--output", default=DEFAULT_MARKDOWN_OUTPUT,
                     help="Output directory for Markdown files")
    md.add_argument("--scope", default=None,
                     help="Only export packages whose breadcrumb path (this package or any "
                          "ancestor) contains this substring, e.g. 'SwSubSys_TouchCtl' "
                          "(one subsystem + its modules) or 'Platform' (whole platform "
                          "subtree). Omit to export every design package in the model.")
    md.add_argument("--skip-templates-branch", default="ModelStructureTemplates",
                     help="Package name marking a templates-only branch to skip entirely")
    md.add_argument("--diagrams-dir", default=DEFAULT_DIAGRAMS_DIR,
                     help="Directory of .puml files + manifest produced by "
                          "export_sequence_diagrams.py, used to cross-reference each "
                          "package's sequence diagrams (default: ai_output/arch_design/diagrams).")

    js = sub.add_parser(
        "json",
        help="Export architecture-design traceability info to JSON",
    )
    js.add_argument(
        "package",
        nargs="?",
        default=None,
        help=(
            "Exact EA package name (e.g. SwSubSys_AmbientSense). "
            "Omit to discover by --level / --prefix."
        ),
    )
    js.add_argument(
        "-f", "--filter",
        dest="path_filter",
        metavar="SEGMENT",
        help="Path segment to disambiguate a single-package lookup (e.g. Platform).",
    )
    js.add_argument(
        "-s", "--scope",
        dest="scope",
        metavar="SEGMENT",
        help=(
            "Limit discovery to packages under this path segment "
            "(e.g. Platform, SwSubSys_TouchCtl). "
            "Ignored when a package name is given."
        ),
    )
    js.add_argument(
        "-l", "--level",
        dest="level",
        metavar="LEVEL",
        default="subsystem",
        choices=list(_LEVEL_PREFIXES.keys()),
        help=(
            "Design level (default: subsystem). "
            "Choices: module (SwMod_*), subsystem (SwSubSys_*), "
            "system (SwSys_*), all. "
            "Ignored when a package name or --prefix is given."
        ),
    )
    js.add_argument(
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
    js.add_argument(
        "-o", "--output-dir",
        dest="output_dir",
        metavar="DIR",
        default=None,
        help="Directory for JSON files (default: ai_output/arch_design/).",
    )
    js.add_argument(
        "--recurse",
        action="store_true",
        default=False,
        help=(
            "Scan sub-packages recursively for elements. "
            "By default only direct child elements are included."
        ),
    )

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.format == "markdown":
        run_markdown_export(args)
    else:
        run_json_export(args)


if __name__ == "__main__":
    main()
