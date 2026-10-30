"""
Tool: compare_design_code.py

Compares EA design function specifications with actual C source implementations
and produces a per-function deviation report.

For each C source file associated with a module class, the tool:
  1. Extracts the function list from EA (design).
  2. Parses function definitions from the C source file (code).
  3. Compares design vs. code and categorises each function.

Deviation categories
--------------------
MISSING_IN_CODE   Function defined in design but absent from the C file.
EXTRA_IN_CODE     Function found in C file but absent from the design.
RETURN_TYPE       Return type differs between design and code (normalised).
PARAM_COUNT       Number of parameters differs.
PARAM_TYPE[N]     Parameter N type differs (normalised comparison).
PARAM_NAME[N]     Parameter N name differs (only with --strict-names).\nSTATIC_ATTR      Static/non-static operation attribute differs.

Type normalisation
------------------
Both design and code types are normalised before comparison:
  - FUNC(ret[, memclass]) → ret
  - P2VAR(T, _, _)        → T *
  - P2CONST(T, _, _)      → const T *
  - CONSTP2VAR(T, _, _)   → T * const
  - CONSTP2CONST(T, _, _) → const T * const
  - Pointer spacing        → T*  (no spaces around *)

Requirements
------------
Run with the 32-bit Python that has pywin32 installed:
    .venv32\\Scripts\\python.exe .github/scripts/ea/compare_design_code.py [options]

Usage
-----
Single C file:
    .venv32\\Scripts\\python.exe .github/scripts/ea/compare_design_code.py SwMod_TouchSM touchsm1c1.c
    .venv32\\Scripts\\python.exe .github/scripts/ea/compare_design_code.py SwMod_TouchSM touchsm1c1.c --src-dir input/touchsm/core

Explicit class name (use when EA SourceFile tag has a typo):
    .venv32\\Scripts\\python.exe .github/scripts/ea/compare_design_code.py SwMod_TouchSM touchsm1c1.c --class TouchSM_API

All source files for every class in a module:
    .venv32\\Scripts\\python.exe .github/scripts/ea/compare_design_code.py SwMod_TouchSM --src-dir input/touchsm/core

Save report to file:
    .venv32\\Scripts\\python.exe .github/scripts/ea/compare_design_code.py SwMod_TouchSM touchsm1c1.c --output output/reports/touchsm1c1_deviations.md

Arguments
---------
module              Exact EA package name (e.g. SwMod_TouchSM).
source_file         C filename to compare (e.g. touchsm1c1.c).
                    Omit to compare all source files referenced by the
                    module's classes.
-f / --filter SEG   Path segment to disambiguate the EA module lookup
                    (e.g. Platform).
-c / --class NAME   Exact EA class name to compare against
                    (e.g. TouchSM_API). Use this when the EA SourceFile
                    tag doesn't match the C filename.
-s / --src-dir DIR  Directory containing the C source files.
                    Defaults to <project_root>/input/.
-o / --output FILE  Write the Markdown report to FILE.
                    Defaults to stdout.
--strict-names      Also flag PARAM_NAME deviations (off by default).
--from-doc FILE     Read design from doc markdown instead of EA
                    (no EA connection needed). Pass module name to auto-resolve
                    doc/<module>_Functions.md.

Output
------
Markdown deviation report listing:
    # Canonicalise test-harness STATIC token to standard C static.
    t = re.sub(r"\bSTATIC\b", "static", t)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------
_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_TOOL_DIR)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _TOOL_DIR)

# Load .env if present
try:
    from dotenv import load_dotenv
    env_path = Path(_TOOL_DIR) / '.env'
    load_dotenv(env_path)
except ImportError:
    pass

# EA-specific imports are deferred; only loaded when --from-doc is NOT used.
_EA_PROJECT: str | None = None


def _load_ea_imports() -> tuple:
    """Import win32com and EA helpers lazily to avoid errors on systems
    where pywin32 is not installed (e.g. when using --from-doc mode)."""
    global _EA_PROJECT
    try:
        import win32com.client as _win32  # noqa: PLC0415
    except ImportError:
        print(
            "ERROR: win32com not found.  Run with the 32-bit Python that has "
            "pywin32 installed, or use --from-doc to skip the EA connection.",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        from config.settings import EA_PROJECT as _ep  # noqa: PLC0415
    except ImportError:
        _ep = os.environ.get("EA_PROJECT", r"D:\Temp\S3P-HUD_Test.eap")
    
    import importlib.util as _ilu  # noqa: PLC0415
    _emf_path = os.path.join(_TOOL_DIR, "export_module_functions.py")
    _emf_spec = _ilu.spec_from_file_location("export_module_functions", _emf_path)
    _emf_mod = _ilu.module_from_spec(_emf_spec)
    _emf_spec.loader.exec_module(_emf_mod)
    find_module_package = _emf_mod.find_module_package
    extract_classes = _emf_mod.extract_classes
    _EA_PROJECT = _ep
    return _win32, _ep, find_module_package, extract_classes

_DEFAULT_SRC_DIR = os.path.join(_PROJECT_ROOT, "input")


# ===========================================================================
# C source parser
# ===========================================================================

def _strip_c_comments(text: str) -> str:
    """Remove block /* ... */ and line // comments from C source text."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", " ", text)
    return text


def _strip_preprocessor(text: str) -> str:
    """Remove C preprocessor directive lines (lines starting with #)."""
    return re.sub(r"^[ \t]*#[^\n]*", " ", text, flags=re.MULTILINE)


def _balanced(text: str, start: int) -> tuple[str, int]:
    """
    Given text[start] == '(', find the matching ')' and return
    (content_between_parens, index_after_closing_paren).
    """
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
    return text[start + 1 :], len(text)


def _split_params(params_str: str) -> list[str]:
    """Split a parameter list string by ',' respecting nested parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in params_str:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    last = "".join(current).strip()
    if last:
        parts.append(last)
    return [p for p in parts if p]


# AUTOSAR pointer macros in priority order (longest first to avoid partial matches)
_AUTOSAR_PTR_MACROS: list[tuple[str, str]] = [
    ("CONSTP2CONST", "const {T}*const"),
    ("CONSTP2VAR",   "{T}*const"),
    ("P2CONST",      "const {T}*"),
    ("P2VAR",        "{T}*"),
]


def _norm_type(t: str) -> str:
    """
    Normalise a C type string for comparison:
      - Expand FUNC(ret[, memclass]) macro to ret
      - Expand AUTOSAR pointer macros (P2VAR, P2CONST, etc.)
      - Collapse pointer spacing: 'T *' / 'T * ' → 'T*'
      - Collapse whitespace
    """
    # Expand FUNC(rettype) or FUNC(rettype, memclass) → rettype
    t = re.sub(
        r"\bFUNC\s*\(\s*([^,)]+?)(?:\s*,\s*[^)]+)?\s*\)",
        lambda m: m.group(1).strip(),
        t,
    )
    # Expand AUTOSAR pointer macros
    for macro, fmt in _AUTOSAR_PTR_MACROS:
        pattern = rf"\b{macro}\s*\(\s*([^,)]+?)\s*,\s*[^,)]+?\s*,\s*[^)]+?\s*\)"
        t = re.sub(
            pattern,
            lambda m, f=fmt: f.replace("{T}", m.group(1).strip()),
            t,
        )
    # Canonicalise test-harness STATIC token to standard C static.
    t = re.sub(r"\bSTATIC\b", "static", t)

    # Normalise pointer spacing: T * → T*, T * const → T*const
    t = re.sub(r"\s*\*\s*", "*", t)
    # Collapse remaining whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _parse_c_param(param_str: str) -> dict[str, str]:
    """
    Parse one C parameter declaration into {type, name}.
    AUTOSAR pointer macros are normalised by _norm_type.
    """
    p = _norm_type(param_str.strip())
    if not p or p.lower() == "void":
        return {"type": p, "name": ""}
    # Remove trailing array notation: name[] or name[N]
    p = re.sub(r"(\w+)\s*\[\s*\w*\s*\]$", r"\1", p).rstrip()
    # The last identifier token is the parameter name
    m = re.search(r"\b(\w+)\s*$", p)
    if m:
        name = m.group(1)
        type_part = p[: m.start()].rstrip()
        return {"type": type_part, "name": name}
    return {"type": p, "name": ""}


def _detect_static_from_prefix(prefix: str) -> bool:
    """Detect static/STATIC storage qualifier in function declaration prefix."""
    return re.search(r"\b(?:STATIC|static)\b", prefix or "") is not None


_SKIP_KEYWORDS: frozenset[str] = frozenset(
    {
        "if", "else", "for", "while", "do", "switch", "return",
        "sizeof", "typedef", "struct", "enum", "union", "class",
        "extern", "static", "volatile", "const", "inline", "public",
        "private", "protected", "namespace", "template",
    }
)


def parse_c_functions(file_content: str) -> list[dict]:
    """
    Parse function DEFINITIONS (not declarations) from C source content.

    Returns a list of dicts:
        {
            "name":        str,
            "return_type": str,          # raw return type from source
            "parameters":  list[dict],   # [{type, name}, ...]
        }

    Handles two patterns:
      Pass 1 – FUNC(rettype[, memclass]) funcname(params) { … }
      Pass 2 – plain rettype funcname(params) { … }  (line-start heuristic)
    """
    text = _strip_c_comments(file_content)
    text = _strip_preprocessor(text)

    functions: list[dict] = []
    found_names: set[str] = set()

    # ------------------------------------------------------------------
    # Pass 1: FUNC(...) macro style
    # ------------------------------------------------------------------
    func_macro_re = re.compile(r"\bFUNC\s*\(")
    for m in func_macro_re.finditer(text):
        paren_start = m.end() - 1  # position of '('
        if paren_start >= len(text) or text[paren_start] != "(":
            continue
        try:
            func_args, after_func = _balanced(text, paren_start)
        except Exception:
            continue

        # Return type is the first comma-separated arg of FUNC()
        ret_type = func_args.split(",")[0].strip()
        if not ret_type:
            continue

        # After FUNC(...): optional whitespace, then funcname(
        rest = text[after_func:]
        name_m = re.match(r"\s*(\w+)\s*\(", rest)
        if not name_m:
            continue

        func_name = name_m.group(1)
        if func_name in _SKIP_KEYWORDS or func_name in found_names:
            continue

        # Extract parameter list (balanced parens)
        try:
            paren_idx = rest.index("(", name_m.start())
            params_str, after_params_rel = _balanced(rest, paren_idx)
        except (ValueError, Exception):
            continue

        # Must be a definition: next significant token after params is '{'
        after_params = rest[after_params_rel:].lstrip()
        next_sig = re.search(r"[{;]", after_params)
        if not next_sig or next_sig.group() != "{":
            continue  # declaration, not a definition

        params: list[dict] = []
        ps = params_str.strip()
        if ps and ps.lower() != "void":
            for p in _split_params(ps):
                params.append(_parse_c_param(p))

        line_start = text.rfind("\n", 0, m.start()) + 1
        prefix = text[line_start:m.start()]
        is_static = _detect_static_from_prefix(prefix)

        functions.append(
            {
                "name": func_name,
                "return_type": ret_type,
                "parameters": params,
                "is_static": is_static,
            }
        )
        found_names.add(func_name)

    # ------------------------------------------------------------------
    # Pass 2: plain return-type style (line-start heuristic)
    # ------------------------------------------------------------------
    # Match: RetType funcname( at line start (indentation allowed)
    plain_re = re.compile(
        r"(?:^|\n)[ \t]*"
        r"((?:(?:const|static|inline|unsigned|signed|volatile)\s+)*"
        r"\w[\w\s\*]*?)\s+"
        r"(\w+)\s*\(",
        re.MULTILINE,
    )
    for m in plain_re.finditer(text):
        ret_type_raw = re.sub(r"\s+", " ", m.group(1)).strip()
        func_name = m.group(2)

        if func_name in found_names or func_name in _SKIP_KEYWORDS:
            continue
        if ret_type_raw in _SKIP_KEYWORDS:
            continue
        # Skip if every word in the return type is a keyword
        words = [w for w in ret_type_raw.split() if w]
        if all(w in _SKIP_KEYWORDS for w in words):
            continue

        # m.end() - 1 is position of '('
        paren_start = m.end() - 1
        if paren_start >= len(text) or text[paren_start] != "(":
            continue

        try:
            params_str, after_params_abs = _balanced(text, paren_start)
        except Exception:
            continue

        after_params = text[after_params_abs:].lstrip()
        next_sig = re.search(r"[{;]", after_params)
        if not next_sig or next_sig.group() != "{":
            continue

        params: list[dict] = []
        ps = params_str.strip()
        if ps and ps.lower() != "void":
            for p in _split_params(ps):
                params.append(_parse_c_param(p))

        is_static = _detect_static_from_prefix(ret_type_raw)

        functions.append(
            {
                "name": func_name,
                "return_type": ret_type_raw,
                "parameters": params,
                "is_static": is_static,
            }
        )
        found_names.add(func_name)

    return functions


# ===========================================================================
# Design / Code comparison
# ===========================================================================

def _norm_for_cmp(t: str) -> str:
    """Normalise a type string for equality comparison (lowercase, no spaces)."""
    return _norm_type(t).lower()


def _is_reference_type(t: str) -> bool:
    """Return True when a type is passed by reference (pointer/array)."""
    nt = _norm_type(t)
    return ("*" in nt) or (("[" in nt) and ("]" in nt))


def _is_true_like(value) -> bool:
    """Best-effort bool parsing for EA fixed-value metadata."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value or "").strip().lower()
    return s in {"1", "true", "yes", "y", "on", "const", "fixed"}


def _norm_design_param_type(param: dict) -> str:
    """
    Normalise EA design parameter type for comparison with code.

    EA parameter metadata treated as pass-mode qualifiers:
      - kind out / inout      => pass-by-reference (pointer expected)
      - fixed_value == true   => const-qualified parameter value
    """
    ptype = (param.get("type") or "").strip()
    kind = (param.get("kind") or "").strip().lower()
    fixed_value = _is_true_like(param.get("fixed_value"))

    is_ref_kind = kind in {"out", "inout", "byref", "by-reference", "ref"}

    if is_ref_kind and ptype and not _is_reference_type(ptype):
        # Convert "uint16" + out => "uint16*" for normalized comparison.
        ptype = f"{ptype}*"

    # Fixed value in EA maps to const qualification in code signatures.
    if fixed_value and ptype and not ptype.lstrip().startswith("const "):
        ptype = f"const {ptype}"

    return _norm_for_cmp(ptype)


def _ea_op_is_static(op: dict) -> bool | None:
    """Resolve EA static attribute from explicit field or scope, None when unavailable."""
    if "is_static" in op:
        return _is_true_like(op.get("is_static"))

    scope = (op.get("scope") or "").strip().lower()
    if scope in {"classifier", "static", "class"}:
        return True
    if scope in {"public", "private", "protected", "package"}:
        return False
    return None


def _norm_design_return_type(op: dict) -> str:
    """Normalise design return type including static modifier from EA operation attributes."""
    rtype = (op.get("return_type") or "").strip()
    is_static = _ea_op_is_static(op)
    if is_static and not re.search(r"^\s*static\b", rtype, flags=re.IGNORECASE):
        rtype = f"static {rtype}".strip()
    return _norm_for_cmp(rtype)


def _norm_code_return_type(code_fn: dict) -> str:
    """Normalise code return type including parsed static/STATIC modifier."""
    rtype = (code_fn.get("return_type") or "").strip()
    if code_fn.get("is_static", False) and not re.search(r"^\s*static\b", rtype, flags=re.IGNORECASE):
        rtype = f"static {rtype}".strip()
    return _norm_for_cmp(rtype)


def compare_functions(
    design_ops: list[dict],
    code_funcs: list[dict],
    strict_names: bool = False,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Compare design operations against code function definitions.

    Parameters
    ----------
    design_ops   : extracted from EA via extract_classes()
    code_funcs   : parsed from C source via parse_c_functions()
    strict_names : when True, also flag PARAM_NAME deviations

    Returns
    -------
    (deviations, clean_funcs, extra_in_code)

    Each deviation dict has keys:
        func_name, category, detail, design_value, code_value

    Each clean dict has key:
        func_name

    extra_in_code is a list of deviation dicts with category='EXTRA_IN_CODE'.
    """
    code_by_name: dict[str, dict] = {f["name"]: f for f in code_funcs}
    design_names: set[str] = {op["name"] for op in design_ops}

    deviations: list[dict] = []
    clean_funcs: list[dict] = []

    for op in design_ops:
        fname = op["name"]

        if fname not in code_by_name:
            deviations.append(
                {
                    "func_name":    fname,
                    "category":     "MISSING_IN_CODE",
                    "detail":       "Function specified in design but not found in C source.",
                    "design_value": f'`{op["return_type"]}` ({len(op["parameters"])} param(s))',
                    "code_value":   "—",
                }
            )
            continue

        code_fn = code_by_name[fname]
        func_devs: list[dict] = []

        # ---- Return type ----
        d_ret = _norm_design_return_type(op)
        c_ret = _norm_code_return_type(code_fn)
        if d_ret != c_ret:
            d_display = (op.get("return_type") or "").strip()
            if _ea_op_is_static(op) and not re.search(r"^\s*static\b", d_display, flags=re.IGNORECASE):
                d_display = f"static {d_display}".strip()

            c_display = (code_fn.get("return_type") or "").strip()
            if code_fn.get("is_static", False) and not re.search(r"^\s*static\b", c_display, flags=re.IGNORECASE):
                c_display = f"static {c_display}".strip()

            func_devs.append(
                {
                    "func_name":    fname,
                    "category":     "RETURN_TYPE",
                    "detail":       "Return type differs.",
                    "design_value": f'`{d_display}`',
                    "code_value":   f'`{c_display}`',
                }
            )

        # ---- Parameter count ----
        d_params = op["parameters"]
        c_params = code_fn["parameters"]
        if len(d_params) != len(c_params):
            func_devs.append(
                {
                    "func_name":    fname,
                    "category":     "PARAM_COUNT",
                    "detail":       (
                        f"Design has {len(d_params)} parameter(s), "
                        f"code has {len(c_params)}."
                    ),
                    "design_value": str(len(d_params)),
                    "code_value":   str(len(c_params)),
                }
            )
        else:
            # ---- Parameter types (and optionally names) ----
            for i, (dp, cp) in enumerate(zip(d_params, c_params), start=1):
                d_ptype = _norm_design_param_type(dp)
                c_ptype = _norm_for_cmp(cp["type"])
                param_label = dp["name"] or cp["name"] or str(i)
                if d_ptype != c_ptype:
                    d_kind = (dp.get("kind") or "").strip()
                    d_fixed = _is_true_like(dp.get("fixed_value"))
                    d_type_display = dp.get("type", "")
                    qualifiers = []
                    if d_kind:
                        qualifiers.append(d_kind)
                    if d_fixed:
                        qualifiers.append("fixed")
                    if qualifiers:
                        d_type_display = f"[{', '.join(qualifiers)}] {d_type_display}".strip()
                    func_devs.append(
                        {
                            "func_name":    fname,
                            "category":     f"PARAM_TYPE[{i}]",
                            "detail":       f"Parameter {i} `{param_label}` type differs.",
                            "design_value": f'`{d_type_display}`',
                            "code_value":   f'`{cp["type"]}`',
                        }
                    )
                elif (
                    strict_names
                    and dp["name"]
                    and cp["name"]
                    and dp["name"] != cp["name"]
                ):
                    func_devs.append(
                        {
                            "func_name":    fname,
                            "category":     f"PARAM_NAME[{i}]",
                            "detail":       f"Parameter {i} name differs.",
                            "design_value": f'`{dp["name"]}`',
                            "code_value":   f'`{cp["name"]}`',
                        }
                    )

        if func_devs:
            deviations.extend(func_devs)
        else:
            clean_funcs.append({"func_name": fname})

    # Functions in code but not in design
    extra_in_code: list[dict] = [
        {
            "func_name":    f["name"],
            "category":     "EXTRA_IN_CODE",
            "detail":       "Function found in C source but not specified in design.",
            "design_value": "—",
            "code_value":   (
                f'`{f["return_type"]}` ({len(f["parameters"])} param(s))'
            ),
        }
        for f in code_funcs
        if f["name"] not in design_names
    ]

    deviations.extend(extra_in_code)
    return deviations, clean_funcs, extra_in_code


# ===========================================================================
# Markdown formatting
# ===========================================================================

def _md_cell(text: str) -> str:
    """Escape pipe characters for markdown table cells."""
    return text.replace("|", "\\|")


def format_report(
    source_file: str,
    all_deviations: list[dict],
    clean_by_class: dict[str, list[dict]],
    deviations_by_class: dict[str, list[dict]],
) -> str:
    """Generate a per-class Markdown deviation report."""
    lines: list[str] = []

    lines.append(f"# Design vs. Code Comparison Report")
    lines.append(f"**Source file:** `{source_file}`")
    lines.append(f"**Report generated:** {__import__('datetime').datetime.now().isoformat()}")
    lines.append("")

    # Global summary
    total_clean = sum(len(v) for v in clean_by_class.values())
    total_devs  = len(all_deviations)
    lines.append(f"## Summary")
    lines.append(f"- **Clean functions:** {total_clean}")
    lines.append(f"- **Deviations found:** {total_devs}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Per-class tables
    for class_name in sorted(set(list(clean_by_class.keys()) + list(deviations_by_class.keys()))):
        lines.append(f"### Class: `{class_name}`")
        lines.append("")

        class_devs  = deviations_by_class.get(class_name, [])
        class_clean = clean_by_class.get(class_name, [])

        if class_devs:
            lines.append(f"#### Deviations ({len(class_devs)})")
            lines.append("")
            lines.append("| Function | Category | Detail | Design | Code |")
            lines.append("|----------|----------|--------|--------|------|")
            for dev in class_devs:
                lines.append(
                    f"| `{_md_cell(dev['func_name'])}` "
                    f"| `{_md_cell(dev['category'])}` "
                    f"| {_md_cell(dev['detail'])} "
                    f"| {_md_cell(dev['design_value'])} "
                    f"| {_md_cell(dev['code_value'])} |"
                )
            lines.append("")

        if class_clean:
            lines.append(f"#### Clean Functions ({len(class_clean)})")
            lines.append("")
            for item in class_clean:
                lines.append(f"- `{_md_cell(item['func_name'])}`")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ===========================================================================
# Load design from Markdown doc file
# ===========================================================================

def load_design_from_doc(doc_path: str, module_name: str = "") -> dict[str, list[dict]]:
    """
    Load the design function list from a Markdown file created by
    export_module_functions.py.

    Returns a dict mapping class_name → list of operation dicts.
    """
    if not os.path.isfile(doc_path):
        print(f"ERROR: Design doc file not found: {doc_path}", file=sys.stderr)
        sys.exit(1)

    with open(doc_path, encoding="utf-8") as fh:
        content = fh.read()

    classes_ops: dict[str, list[dict]] = {}
    current_class: str | None = None

    # Markdown format: ### Class_Name (from export_module_functions.py)
    # Each class section has a table with: | # | Function | Return Type | Parameters | Trace ID | ...
    for line in content.split("\n"):
        line = line.strip()

        # Detect "### ClassName" section header
        if line.startswith("### "):
            current_class = line[4:].strip("`").strip()
            classes_ops[current_class] = []
            continue

        # Skip non-table-data lines
        if not line.startswith("|") or line.startswith("| ---"):
            continue

        # Parse table row: | # | Function | Return Type | ... |
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) < 4:
            continue

        # Skip header row
        if parts[0].lower() in ("function", "#"):
            continue

        func_name = parts[1].strip("`").strip()
        return_type = parts[2].strip("`").strip() if len(parts) > 2 else "void"
        params_str = parts[3].strip() if len(parts) > 3 else ""

        # Parse parameters (simple split on comma, preserving [kind]/[fixed] qualifiers)
        params: list[dict] = []
        if params_str and params_str.lower() != "void":
            # Remove <br> markers and split
            params_str = params_str.replace("<br>", ",")
            for p in _split_params(params_str):
                raw = p.strip()
                kind = ""
                fixed_value = False

                # Markdown format allows multiple leading qualifiers like:
                #   [inout][fixed] Type name
                while raw.startswith("[") and "]" in raw:
                    end = raw.find("]")
                    token = raw[1:end].strip()
                    raw = raw[end + 1:].strip()

                    token_l = token.lower()
                    if token_l in {"in", "out", "inout", "ref", "byref", "by-reference"}:
                        kind = token
                    elif token_l in {"fixed", "const"}:
                        fixed_value = True

                p_parts = raw.split()
                if not p_parts:
                    continue

                # Reconstruct type and name
                if len(p_parts) >= 2:
                    pname = p_parts[-1]
                    ptype = " ".join(p_parts[:-1])
                else:
                    pname = ""
                    ptype = p_parts[0]

                params.append({
                    "type": ptype,
                    "name": pname,
                    "kind": kind,
                    "fixed_value": fixed_value,
                })

        # Optional qualifier in return type for docs: [static] ReturnType
        is_static = False
        rt = return_type
        if rt.startswith("[") and "]" in rt:
            end = rt.find("]")
            q = rt[1:end].strip().lower()
            if q in {"static", "classifier", "class"}:
                is_static = True
            rt = rt[end + 1:].strip()

        if current_class:
            classes_ops[current_class].append({
                "name": func_name,
                "return_type": rt,
                "parameters": params,
                "is_static": is_static,
            })

    return classes_ops


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="compare_design_code",
        description="Compare EA design function specs with C source code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("module", help="EA module name (e.g. SwMod_TouchSM)")
    parser.add_argument(
        "source_file", nargs="?", default=None,
        help="C source filename (e.g. touchsm1c1.c). Omit to compare all."
    )
    parser.add_argument(
        "-f", "--filter",
        dest="path_filter",
        help="Path filter for EA module lookup (e.g. Platform)"
    )
    parser.add_argument(
        "-c", "--class",
        dest="class_name",
        help="EA class name (e.g. TouchSM_API)"
    )
    parser.add_argument(
        "-s", "--src-dir",
        dest="src_dir",
        default=_DEFAULT_SRC_DIR,
        help=f"Source directory (default: {_DEFAULT_SRC_DIR})"
    )
    parser.add_argument(
        "-o", "--output",
        dest="output",
        help="Output file (default: stdout)"
    )
    parser.add_argument(
        "--strict-names",
        action="store_true",
        help="Also flag parameter name differences"
    )
    parser.add_argument(
        "--from-doc",
        dest="from_doc",
        help="Read design from doc markdown (pass module name to auto-resolve path)"
    )

    args = parser.parse_args()

    # ── Load design ──────────────────────────────────────────────────────────
    if args.from_doc:
        # Auto-resolve doc/<module>_Functions.md
        module_for_doc = args.from_doc if args.from_doc != "True" else args.module
        doc_path = os.path.join(_PROJECT_ROOT, "doc", f"{module_for_doc}_Functions.md")
        print(f"Loading design from: {doc_path}")
        classes_ops = load_design_from_doc(doc_path, module_for_doc)
    else:
        # Load from EA
        _win32, ea_proj, find_module_package, extract_classes = _load_ea_imports()
        repo = _win32.Dispatch("EA.Repository")
        try:
            repo.OpenFile(ea_proj)
        except Exception as exc:
            print(f"ERROR: Cannot open EA project {ea_proj}: {exc}", file=sys.stderr)
            sys.exit(1)

        try:
            print(f"Searching for module '{args.module}'...")
            module_pkg, module_path = find_module_package(repo, args.module, args.path_filter)
            print(f"Found: {module_path}")
            classes = extract_classes(module_pkg, repo)
            classes_ops = {c["name"]: c["operations"] for c in classes}
            classes_src_files = {c["name"]: c.get("source_file") or "" for c in classes}
        finally:
            try:
                repo.CloseFile()
                repo.Exit()
            except Exception:
                pass

    # ── Parse code and compare ───────────────────────────────────────────────
    deviations_by_class: dict[str, list[dict]] = {}
    clean_by_class: dict[str, list[dict]] = {}
    all_deviations: list[dict] = []

    for class_name, design_ops in classes_ops.items():
        # Determine which C file to compare
        if args.source_file:
            c_files = [args.source_file]
        elif args.class_name and class_name != args.class_name:
            continue
        else:
            src_fname = classes_src_files.get(class_name, "")
            c_files = []
            if src_fname:
                try:
                    for root, _dirs, fnames in os.walk(args.src_dir):
                        for fname in fnames:
                            if fname.lower() == src_fname.lower():
                                c_files.append(os.path.join(root, fname))
                except OSError as exc:
                    print(f"ERROR: Cannot search source directory: {exc}", file=sys.stderr)
                    sys.exit(1)
                if not c_files:
                    print(f"  WARNING: Source file '{src_fname}' for {class_name} not found in {args.src_dir}", file=sys.stderr)
            else:
                try:
                    for root, _dirs, fnames in os.walk(args.src_dir):
                        for fname in fnames:
                            if fname.endswith(".c"):
                                c_files.append(os.path.join(root, fname))
                except OSError as exc:
                    print(f"ERROR: Cannot search source directory: {exc}", file=sys.stderr)
                    sys.exit(1)

        if not c_files:
            print(
                f"WARNING: No C files found for class {class_name}",
                file=sys.stderr
            )
            continue

        for c_file in c_files:
            print(f"  Comparing: {class_name} vs. {c_file}")
            try:
                with open(c_file, encoding="utf-8", errors="replace") as fh:
                    c_content = fh.read()
            except OSError as exc:
                print(f"  ERROR: Cannot read {c_file}: {exc}", file=sys.stderr)
                continue

            code_funcs = parse_c_functions(c_content)
            devs, clean, extra = compare_functions(
                design_ops, code_funcs, args.strict_names
            )

            if class_name not in deviations_by_class:
                deviations_by_class[class_name] = []
                clean_by_class[class_name] = []
            deviations_by_class[class_name].extend(devs)
            clean_by_class[class_name].extend(clean)
            all_deviations.extend(devs)

    # ── Generate report ─────────────────────────────────────────────────────
    source_label = args.source_file or "all"
    report_text = format_report(source_label, all_deviations, clean_by_class, deviations_by_class)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(report_text)
        print(f"\nReport written to: {args.output}")
    else:
        print("\n" + report_text)


if __name__ == "__main__":
    main()

