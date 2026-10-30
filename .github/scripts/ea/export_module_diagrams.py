"""
Tool: export_module_diagrams.py

Reads the SwDetailedDesignDiagram XML files produced by src/main.py and:
  1. Renders each function's activity diagram as a numbered flow table in Markdown.
  2. Generates C source code (.h + .c) when a matching <ModuleName>_ms.xml
     XMI file is present in the diagrams directory.

The Markdown output is intended for comparing EA-modelled behaviour with the
actual C implementation to spot differences.

The C output is generated via xmi_to_c.py which produces a full header with
type definitions and a source file with function bodies derived from the
activity diagrams.  Requires a <ModuleName>_ms.xml XMI export alongside the
diagram XML files.  Use --no-code to skip C generation.

Requirements:
    Run src/main.py first to generate the SwDetailedDesignDiagram XML files in
    ai_output/.  This tool does NOT need EA to be running.

Usage
-----
Single module (diagrams + C code):
    python scripts/export_module_diagrams.py SwMod_TouchSM

Single module (diagrams only):
    python scripts/export_module_diagrams.py SwMod_TouchSM --no-code

All modules found in the diagrams directory:
    python scripts/export_module_diagrams.py --all

Custom diagrams directory:
    python scripts/export_module_diagrams.py SwMod_TouchSM --diagrams path/to/xmls/

Custom code output directory:
    python scripts/export_module_diagrams.py SwMod_TouchSM --code-dir path/to/src/

Arguments
---------
module          (positional, optional)
                    Exact module name, e.g. SwMod_TouchSM.
                    Omit when using --all.
--all           Process every module found in the diagrams directory.
--diagrams DIR  Directory containing SwDetailedDesignDiagram*.xml files
                and the <ModuleName>_ms.xml XMI file.
                Defaults to <project_root>/ai_output/.
--code-dir DIR  Directory where generated .h and .c files are written.
                Defaults to <project_root>/ai_output/generated_c/.
--no-code       Skip C source code generation.
output_dir      (positional, optional)
                    Directory where .md files are written.
                    Defaults to <project_root>/doc/.

Output
------
Markdown:  doc/<ModuleName>_diagrams.md
C header:  ai_output/generated_c/<ModuleName>.h
C source:  ai_output/generated_c/<ModuleName>.c

Each Markdown file contains, for every function with an activity diagram:
  - Function name, stereotype, tagged values (Feature/Variant)
  - Numbered flow table: # | Type | Description | Next
    where "Next" references step numbers and shows guards
  - Loop-backs are annotated with *(loop)*
  - A summary table at the end

Errors
------
Exits with a non-zero code if:
  - No SwDetailedDesignDiagram XML files are found for the given module
  - The XML files cannot be parsed
"""

from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Project root on path so sibling modules are importable
# ---------------------------------------------------------------------------
_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_TOOL_DIR)))
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _SRC_DIR)
sys.path.insert(0, _TOOL_DIR)

from config.settings import OUTPUT_DIR  # noqa: E402
from xml_to_c import _parse_function, FlowGraph  # noqa: E402
# `xmi_to_c.py` no longer exists - it was consolidated into
# `ea_diagram_to_code.py` (see that file's `process_xmi_file()`, same
# signature: xmi_path, output_dir, diagrams_dir). This was the actual root
# cause of this tool's `ModuleNotFoundError: xmi_to_c` - not a missing
# dependency, a stale import left over from that consolidation.
from ea_diagram_to_code import process_xmi_file  # noqa: E402

_DEFAULT_DOC_DIR = os.path.join(_PROJECT_ROOT, "doc")
_DEFAULT_DIAGRAMS_DIR = OUTPUT_DIR
_DEFAULT_CODE_DIR = os.path.join(_PROJECT_ROOT, "ai_output", "generated_c")


# ---------------------------------------------------------------------------
# Diagram file discovery
# ---------------------------------------------------------------------------

def find_diagram_files(module_name: str, diagrams_dir: str) -> list[str]:
    """Return all SwDetailedDesignDiagram XML files that belong to *module_name*."""
    result = []
    try:
        for fname in os.listdir(diagrams_dir):
            if (fname.endswith(".xml")
                    and "SwDetailedDesignDiagram" in fname
                    and module_name in fname):
                result.append(os.path.join(diagrams_dir, fname))
    except OSError as exc:
        print(f"ERROR: Cannot read diagrams directory '{diagrams_dir}': {exc}",
              file=sys.stderr)
        sys.exit(1)
    return sorted(result)


def discover_all_modules(diagrams_dir: str) -> list[str]:
    """Return sorted list of unique module names found in the diagrams directory."""
    names: set[str] = set()
    try:
        for fname in os.listdir(diagrams_dir):
            if not fname.endswith(".xml") or "SwDetailedDesignDiagram" not in fname:
                continue
            # Filename pattern: *SwDetailedDesignDiagram{ModuleName}{GUID}.xml
            m = re.search(r'SwDetailedDesignDiagram(SwMod_\w+?)[0-9A-Fa-f]{30,}\.xml',
                          fname)
            if m:
                names.add(m.group(1))
    except OSError as exc:
        print(f"ERROR: Cannot read diagrams directory '{diagrams_dir}': {exc}",
              file=sys.stderr)
        sys.exit(1)
    return sorted(names)


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def parse_diagram_file(xml_path: str) -> list[dict]:
    """
    Parse a SwDetailedDesignDiagram XML file.

    Returns a list of function dicts:
        {
          "name":       str,
          "guid":       str,
          "stereotype": str,
          "tags":       dict[str, str],   # e.g. Feature, Variant
          "graph":      FlowGraph,
        }
    """
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        print(f"WARNING: Cannot parse '{xml_path}': {exc}", file=sys.stderr)
        return []

    root = tree.getroot()
    functions: list[dict] = []

    for module_el in root.findall("Module"):
        for func_el in module_el.findall("Function"):
            name = (func_el.get("name") or "").strip()
            guid = (func_el.get("guid") or "").strip()
            stereotype = (func_el.get("stereotype") or "").strip()
            tags: dict[str, str] = {}
            for tv in func_el.findall("TaggedValue"):
                k = (tv.get("name") or "").strip()
                v = (tv.get("value") or "").strip()
                if k and v:
                    tags[k] = v
            graph = _parse_function(func_el)
            functions.append({
                "name":       name,
                "guid":       guid,
                "stereotype": stereotype,
                "tags":       tags,
                "graph":      graph,
            })

    return functions


# ---------------------------------------------------------------------------
# Flow graph rendering
# ---------------------------------------------------------------------------

# Step types that represent actual code logic.
# All other types (Requirement, Enumeration, Interface, ActivityParameter,
# InterruptibleActivityRegion, Activity, …) are traceability/model artefacts
# and are excluded from the comparison table.
_CODE_TYPES = frozenset({"StateNode", "Action", "Decision"})


def _assign_step_numbers(graph: FlowGraph) -> dict[str, int]:
    """BFS from the entry node; assign 1-based sequential step numbers
    to *code* steps only (StateNode, Action, Decision)."""
    code_steps = {g: s for g, s in graph.steps.items() if s.type in _CODE_TYPES}

    # Find entry among code steps
    graph.build_in_degrees()
    entry = None
    # Prefer a StateNode with in-degree 0
    for guid, step in code_steps.items():
        if step.type == "StateNode" and graph.in_degree.get(guid, 0) == 0:
            entry = guid
            break
    if entry is None:
        # Fallback: any code step with in-degree 0
        for guid in code_steps:
            if graph.in_degree.get(guid, 0) == 0:
                entry = guid
                break
    if entry is None and code_steps:
        entry = next(iter(code_steps))

    nums: dict[str, int] = {}
    if entry is None:
        return nums

    queue = [entry]
    counter = 1

    while queue:
        guid = queue.pop(0)
        if guid in nums or guid not in code_steps:
            continue
        nums[guid] = counter
        counter += 1
        step = graph.steps.get(guid)
        if step:
            for _, to_guid, _ in step.flows:
                # Follow the flow, skipping non-code hops
                target = _resolve_code_target(graph, to_guid, set())
                if target and target in code_steps and target not in nums:
                    queue.append(target)

    # Any code steps unreachable from entry
    for guid in code_steps:
        if guid not in nums:
            nums[guid] = counter
            counter += 1

    return nums


def _resolve_code_target(graph: FlowGraph, guid: str,
                         visited: set[str]) -> str | None:
    """Follow non-code hops until we reach a code step or exhaust the graph."""
    if guid in visited:
        return None
    visited.add(guid)
    step = graph.steps.get(guid)
    if step is None:
        return None
    if step.type in _CODE_TYPES:
        return guid
    # Hop through non-code step: follow its first outgoing flow
    for _, next_guid, _ in step.flows:
        result = _resolve_code_target(graph, next_guid, visited)
        if result:
            return result
    return None


def _md_safe(text: str) -> str:
    """Escape characters that would break a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", "")


def _render_function(func: dict) -> list[str]:
    """Render one function's activity diagram as Markdown lines."""
    name = func["name"]
    stereotype = func["stereotype"]
    tags = func["tags"]
    graph: FlowGraph = func["graph"]

    lines: list[str] = []
    lines.append(f"### `{_md_safe(name)}`")

    meta: list[str] = []
    if stereotype:
        meta.append(f"**Stereotype:** {stereotype}")
    for k, v in tags.items():
        meta.append(f"**{k}:** `{v}`")
    if meta:
        lines.append(" | ".join(meta))
    lines.append("")

    if not graph.steps:
        lines.append("*(no diagram steps found)*")
        lines.append("")
        return lines

    nums = _assign_step_numbers(graph)
    if not nums:
        lines.append("*(no executable steps found)*")
        lines.append("")
        return lines

    # Render only code steps, sorted by assigned number
    code_steps = [
        graph.steps[g] for g in sorted(nums, key=lambda g: nums[g])
    ]

    lines.append("| # | Type | Description | Next |")
    lines.append("|---|------|-------------|------|")

    for step in code_steps:
        n = nums[step.guid]
        stype = step.type

        # Human-readable description
        if step.name:
            desc = step.name
        elif stype == "StateNode":
            desc = "*(start)*" if step.flows else "*(end)*"
        else:
            desc = ""

        # Build "Next" cell — resolve flows through non-code hops
        if not step.flows:
            next_cell = "*(end)*"
        else:
            parts: list[str] = []
            for _, to_guid, guard in step.flows:
                # Skip hops over non-code steps
                resolved = _resolve_code_target(graph, to_guid, set())
                if resolved is None:
                    continue          # external / dead-end — skip
                to_num = nums.get(resolved)
                if to_num is None:
                    continue          # resolved to a step without a number
                is_loop = to_num <= n
                suffix = " *(loop)*" if is_loop else ""
                if guard:
                    parts.append(f"[{_md_safe(guard)}] → {to_num}{suffix}")
                else:
                    parts.append(f"→ {to_num}{suffix}")
            next_cell = ", ".join(parts) if parts else "*(end)*"

        lines.append(
            f"| {n} | {stype} | {_md_safe(desc)} | {_md_safe(next_cell)} |"
        )

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Markdown document generation
# ---------------------------------------------------------------------------

def generate_markdown(module_name: str, functions: list[dict]) -> str:
    """Build the full Markdown document for a module's activity diagrams."""
    lines: list[str] = []

    lines.append(f"# {module_name} – Activity Diagrams\n")
    lines.append(f"**Module:** `{module_name}`  ")
    lines.append(f"**Total diagrams:** {len(functions)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for func in functions:
        lines.extend(_render_function(func))
        lines.append("---")
        lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Function | Stereotype | Steps | Decisions |")
    lines.append("|----------|------------|-------|-----------|")
    for func in functions:
        g: FlowGraph = func["graph"]
        code = [s for s in g.steps.values() if s.type in _CODE_TYPES]
        n_steps = len(code)
        n_decisions = sum(1 for s in code if s.type == "Decision")
        stereo = func["stereotype"] or "—"
        lines.append(
            f"| `{_md_safe(func['name'])}` | {stereo} | {n_steps} | {n_decisions} |"
        )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# C source code generation
# ---------------------------------------------------------------------------

def generate_source_code(
    module_name: str,
    output_dir: str | None = None,
    diagrams_dir: str | None = None,
) -> tuple[str, str] | None:
    """
    Generate C source code (.h + .c) for *module_name*.

    Looks for ``<module_name>_ms.xml`` in *diagrams_dir* (the output folder).
    If the XMI file is found, calls ``xmi_to_c.process_xmi_file`` which
    produces a full .h + .c with enums, structs, variable declarations and
    function bodies from the activity diagrams.

    Parameters
    ----------
    module_name : str
        Exact module name, e.g. 'SwMod_TouchSM'.
    output_dir : str, optional
        Directory where .h and .c are written. Defaults to ai_output/generated_c/.
    diagrams_dir : str, optional
        Directory that contains both the XMI file and the diagram XMLs.
        Defaults to ai_output/.

    Returns
    -------
    tuple[str, str]  – (h_path, c_path) on success
    None             – when the XMI file is not found (warning printed)
    """
    if output_dir is None:
        output_dir = _DEFAULT_CODE_DIR
    if diagrams_dir is None:
        diagrams_dir = _DEFAULT_DIAGRAMS_DIR

    xmi_path = os.path.join(diagrams_dir, f"{module_name}_ms.xml")
    if not os.path.isfile(xmi_path):
        print(
            f"WARNING: XMI file not found for '{module_name}': {xmi_path}\n"
            "         Skipping C code generation.\n"
            "         Export the XMI from EA (File → Export Package as XMI) "
            f"and save as '{module_name}_ms.xml' in {diagrams_dir}.",
            file=sys.stderr,
        )
        return None

    print(f"\nGenerating C source from: {os.path.basename(xmi_path)}")
    os.makedirs(output_dir, exist_ok=True)
    process_xmi_file(xmi_path, output_dir, diagrams_dir)

    safe = module_name  # xmi_to_c uses module_name directly as filename base
    h_path = os.path.join(output_dir, f"{safe}.h")
    c_path = os.path.join(output_dir, f"{safe}.c")
    return h_path, c_path


# ---------------------------------------------------------------------------
# Core export function
# ---------------------------------------------------------------------------

def export_module_diagrams(
    module_name: str,
    output_dir: str | None = None,
    diagrams_dir: str | None = None,
    code_dir: str | None = None,
    generate_code: bool = True,
) -> str:
    """
    Export activity diagrams for *module_name* to a Markdown file and,
    optionally, generate the C source code (.h + .c).

    Parameters
    ----------
    module_name : str
        Exact module name, e.g. 'SwMod_TouchSM'.
    output_dir : str, optional
        Directory where the .md file is written.  Defaults to doc/.
    diagrams_dir : str, optional
        Directory containing SwDetailedDesignDiagram XML files.
        Defaults to ai_output/.
    code_dir : str, optional
        Directory where .h and .c are written. Defaults to ai_output/generated_c/.
    generate_code : bool
        When True (default), also generate the C source code.

    Returns
    -------
    str
        Absolute path of the generated Markdown file.
    """
    if output_dir is None:
        output_dir = _DEFAULT_DOC_DIR
    if diagrams_dir is None:
        diagrams_dir = _DEFAULT_DIAGRAMS_DIR

    os.makedirs(output_dir, exist_ok=True)

    xml_files = find_diagram_files(module_name, diagrams_dir)
    if not xml_files:
        print(
            f"\nERROR: No SwDetailedDesignDiagram XML files found for '{module_name}'.\n"
            f"       Searched in: {diagrams_dir}\n\n"
            "       Run 'python src/main.py' first to export diagram XMLs.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found {len(xml_files)} diagram file(s) for '{module_name}':")
    for f in xml_files:
        print(f"  {os.path.basename(f)}")

    all_functions: list[dict] = []
    for xml_path in xml_files:
        funcs = parse_diagram_file(xml_path)
        all_functions.extend(funcs)

    # Deduplicate by function name (same function may appear in multiple files
    # as different variants — keep all but mark the source file)
    all_functions.sort(key=lambda f: f["name"].lower())

    print(f"Loaded {len(all_functions)} function diagram(s).")

    md_content = generate_markdown(module_name, all_functions)

    out_path = os.path.join(output_dir, f"{module_name}_diagrams.md")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md_content)

    print(f"Written: {out_path}")

    if generate_code:
        generate_source_code(module_name, code_dir, diagrams_dir)

    return out_path


def export_all_diagrams(
    output_dir: str | None = None,
    diagrams_dir: str | None = None,
    code_dir: str | None = None,
    generate_code: bool = True,
) -> list[str]:
    """Export activity diagrams for every module found in *diagrams_dir*."""
    if diagrams_dir is None:
        diagrams_dir = _DEFAULT_DIAGRAMS_DIR

    modules = discover_all_modules(diagrams_dir)
    if not modules:
        print(
            f"ERROR: No SwDetailedDesignDiagram XML files found in '{diagrams_dir}'.\n"
            "       Run 'python src/main.py' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found {len(modules)} module(s): {', '.join(modules)}")
    generated: list[str] = []
    for module_name in modules:
        print(f"\n--- {module_name} ---")
        try:
            path = export_module_diagrams(
                module_name, output_dir, diagrams_dir, code_dir, generate_code
            )
            generated.append(path)
        except SystemExit:
            pass  # already printed error; continue with next module

    print(f"\nDone. {len(generated)} file(s) generated.")
    return generated


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="export_module_diagrams",
        description=(
            "Render EA activity diagrams from SwDetailedDesignDiagram XML files\n"
            "as numbered flow tables in Markdown for comparison with C code."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "module",
        nargs="?",
        default=None,
        help="Module name (e.g. SwMod_TouchSM). Omit when using --all.",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        dest="all_modules",
        help="Process every module found in the diagrams directory.",
    )
    parser.add_argument(
        "--diagrams", "-d",
        dest="diagrams_dir",
        metavar="DIR",
        default=None,
        help=(
            "Directory containing SwDetailedDesignDiagram XML files "
            f"(default: {_DEFAULT_DIAGRAMS_DIR})."
        ),
    )
    parser.add_argument(
        "--code-dir",
        dest="code_dir",
        metavar="DIR",
        default=None,
        help=(
            "Directory where generated .h and .c files are written "
            f"(default: {_DEFAULT_CODE_DIR})."
        ),
    )
    parser.add_argument(
        "--no-code",
        action="store_false",
        dest="generate_code",
        help=(
            "Skip C source code generation. "
            "By default the tool generates .h + .c when a matching "
            "<ModuleName>_ms.xml XMI file is found."
        ),
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help=f"Output directory for .md files (default: {_DEFAULT_DOC_DIR}).",
    )

    args = parser.parse_args(argv[1:])

    if args.all_modules:
        export_all_diagrams(args.output_dir, args.diagrams_dir,
                            args.code_dir, args.generate_code)
    elif args.module:
        export_module_diagrams(args.module, args.output_dir, args.diagrams_dir,
                               args.code_dir, args.generate_code)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)

