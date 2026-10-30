"""
Generate C source code from EA diagrams (all-in-one orchestration tool).

This unified tool orchestrates the complete EA to C pipeline:
1. Takes a module name (e.g., 'touchsm') as input
2. Optionally exports EA package to XMI format (requires --ea-package)
3. Finds EA XMI and SwDetailedDesignDiagram XML files for that module
4. Generates C code from XMI and enriches with activity diagram bodies
5. Outputs to the appropriate folder (adapt/ or core/)
6. Supports multiple input sources and customizable output paths

All XMI parsing, C code generation, diagram processing, and EA export
are integrated into this single script.

NOTE: xml_to_c.py is still used (imported) for diagram flow parsing.

Usage:
    python ea_diagram_to_code.py <module_name> [options]

    module_name
        Module identifier without 'SwMod_' prefix.
        Examples: 'touchsm', 'TouchSM', 'DesCtl', 'ComMon'

Options:
    --ea-package PACKAGE    Export from EA: package path or GUID
                            Example: "{D94609F2-A53D-4f95-A4DC-8CDB7FAA3AFE}"
                            XMI stored in: ai_output/<module>/SwMod_<Module>_ms.xml
    --xmi FILE              Path to XMI file (overrides auto-detection)
    --diagrams DIR          Directory containing SwDetailedDesignDiagram XML files
    --output DIR            Force output directory (default: ai_output/<module>/generated_c/)
    --input-dir DIR         Base input directory (default: input/)
    --dry-run               Show what would be generated, don't write files
    --force                 Overwrite existing files without prompting
    --verbose               Print detailed step information

Examples:
    # End-to-end: Export from EA and generate C code
    .venv32\Scripts\python.exe .github/scripts/ea/ea_diagram_to_code.py touchsm \\
        --ea-package "{D94609F2-A53D-4f95-A4DC-8CDB7FAA3AFE}" \\
        --output ai_output/generated_c --force --verbose

    # Generate from auto-detected diagrams in input/touchsm/
    python .github/scripts/ea/ea_diagram_to_code.py touchsm

    # Generate from explicit XMI file
    python .github/scripts/ea/ea_diagram_to_code.py touchsm --xmi ai_output/touchsm/SwMod_TouchSM_ms.xml

    # Generate with custom output directory
    python .github/scripts/ea/ea_diagram_to_code.py desctl --output ai_output/desctl/generated_c --force

    # Dry run to preview changes
    python .github/scripts/ea/ea_diagram_to_code.py commond --dry-run --verbose

Exit codes:
    0 - Success
    1 - Invalid module name or missing files
    2 - Configuration error
    3 - File I/O error
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from config.settings import OUTPUT_DIR, EA_PROJECT

# Import xml_to_c utilities (flow graph parsing)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from xml_to_c import (  # noqa: E402
        FlowGraph, Step, CEmitter,
        _parse_function, _emit_step, _collect_traces,
        process_xml_file as _xml_to_c_process_file,
        process_xml_per_class as _xml_to_c_per_class,
    )
except ImportError:
    FlowGraph = Step = CEmitter = None
    _parse_function = _emit_step = _collect_traces = None
    _xml_to_c_process_file = _xml_to_c_per_class = None

# EA COM support (optional, only needed for --ea-package)
try:
    import win32com.client
    HAS_EA_COM = True
except ImportError:
    HAS_EA_COM = False


# ─────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────

DEFAULT_INPUT_DIR = 'input'
DEFAULT_OUTPUT_BASE = 'ai_output'

# Pattern to match SwMod_* package names in XMI
SWMOD_PATTERN = re.compile(r'SwMod_(\w+)', re.IGNORECASE)

# Pattern to match SwDetailedDesignDiagram files
DIAGRAM_PATTERN = re.compile(r'SwDetailedDesignDiagram.*\.xml$', re.IGNORECASE)

# XMI namespace
_UML_NS = 'omg.org/UML1.3'

# EA XMI export type constants
XMI_TYPE_UML13 = 1   # XMI 1.1 / UML 1.3 (matches manual export format)
XMI_TYPE_UML21 = 3   # XMI 2.1 / UML 2.1


# ─────────────────────────────────────────────────────────────────────────
# EA Export Utilities (from ea_xmi_export.py)
# ─────────────────────────────────────────────────────────────────────────

def _normalise_guid(raw: str) -> str:
    """Return GUID in {XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX} form."""
    raw = raw.strip()
    # EA XMI uses EAPK_D94609F2_A53D_4f95_A4DC_8CDB7FAA3AFE form
    if raw.upper().startswith('EAPK_') or raw.upper().startswith('EAID_'):
        raw = raw[5:]                          # strip prefix
        parts = raw.split('_')
        if len(parts) == 5:
            return '{' + '-'.join(parts) + '}'
    # Standard GUID: with or without braces
    raw = raw.strip('{}')
    # Replace underscores (EA style) with dashes
    raw = raw.replace('_', '-')
    # Validate rough GUID shape
    if re.match(r'^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$', raw):
        return '{' + raw.upper() + '}'
    return ''


def _looks_like_guid(s: str) -> bool:
    """Check if string looks like a GUID."""
    return bool(_normalise_guid(s))


def _find_package_by_guid(repo, guid: str):
    """Return the EA Package object for the given GUID, or None."""
    normalised = _normalise_guid(guid)
    if not normalised:
        return None
    try:
        pkg = repo.GetPackageByGuid(normalised)
        return pkg if pkg else None
    except Exception:
        return None


def _find_package_by_path(repo, path: str):
    """
    Walk the package tree by dot-separated name path.
    Skips the first segment if it matches the top model name (EA always has one root model node).
    Case-insensitive matching.
    """
    segments = [s.strip() for s in path.split('.') if s.strip()]
    if not segments:
        return None

    # Collect all root models
    roots = list(repo.Models)
    if not roots:
        return None

    # If the first segment matches a model name, start inside that model;
    # otherwise start from all models and try to match the first segment as a top-level package.
    start_segments = segments
    model_match = next(
        (m for m in roots if m.Name.lower() == segments[0].lower()), None
    )
    if model_match:
        start_segments = segments[1:]
        search_roots = [model_match]
    else:
        search_roots = roots

    def _walk(parent, remaining):
        if not remaining:
            return parent
        target = remaining[0].lower()
        try:
            for pkg in parent.Packages:
                if pkg.Name.lower() == target:
                    result = _walk(pkg, remaining[1:])
                    if result:
                        return result
        except Exception:
            pass
        return None

    for root in search_roots:
        result = _walk(root, start_segments)
        if result:
            return result

    return None


def export_package_xmi(repo, pkg, output_path: str, xmi_type: int = XMI_TYPE_UML13) -> bool:
    """
    Export *pkg* to *output_path* using EA's built-in XMI exporter.

    Parameters
    ----------
    xmi_type : int
        1 = XMI 1.1/UML 1.3 (same as manual "Export Package > XMI 1.1")
        3 = XMI 2.1/UML 2.1
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Convert to absolute path (EA sometimes needs this)
    abs_output_path = os.path.abspath(output_path)

    project = repo.GetProjectInterface()

    # (PackageGUID, XMIType, DiagramXML, DiagramImage, FormatXML, UseDTD, FileName)
    result = project.ExportPackageXMI(
        pkg.PackageGUID,       # package GUID
        xmi_type,              # XMI type: 1 = XMI 1.1
        1,                     # DiagramXML: include diagram markup
        0,                     # DiagramImage: do not embed images
        1,                     # FormatXML: pretty-print
        0,                     # UseDTD
        abs_output_path,       # output filename (use absolute path)
    )
    # EA returns "" on success or an error message string on failure
    if result:
        raise RuntimeError(f"EA export returned error: {result}")
    return True


def export_xmi_from_ea(package_ref: str, module_name: str, output_dir: str = 'ai_output', 
                       verbose: bool = False) -> Optional[str]:
    """
    Export an EA package to XMI format using EA COM.
    
    Parameters
    ----------
    package_ref : str
        Either a dot-separated package path or a GUID
    module_name : str
        Module name (e.g., 'TouchSM') for output filename
    output_dir : str
        Directory to store XMI (default: ai_output/)
    verbose : bool
        Print progress information
    
    Returns
    -------
    str
        Path to exported XMI file, or None if export failed
    """
    if not HAS_EA_COM:
        print(f"ERROR: win32com not available. Cannot export from EA.", file=sys.stderr)
        print(f"  Install: pip install pywin32", file=sys.stderr)
        return None

    if not os.path.exists(EA_PROJECT):
        print(f"ERROR: EA project not found: {EA_PROJECT}", file=sys.stderr)
        return None

    repo = None
    try:
        if verbose:
            print(f"[EA] Connecting to EA: {EA_PROJECT}")

        repo = win32com.client.Dispatch('EA.Repository')
        repo.OpenFile(EA_PROJECT)

        # Locate the package
        if _looks_like_guid(package_ref):
            if verbose:
                print(f"[EA] Locating package by GUID: {package_ref}")
            pkg = _find_package_by_guid(repo, package_ref)
        else:
            if verbose:
                print(f"[EA] Locating package by path: {package_ref}")
            pkg = _find_package_by_path(repo, package_ref)

        if pkg is None:
            print(f"ERROR: Package not found: {package_ref}", file=sys.stderr)
            return None

        if verbose:
            print(f"[OK] Found package: {pkg.Name} (GUID={pkg.PackageGUID})")

        # Resolve output path: ai_output/<module>/SwMod_<Module>_ms.xml
        safe_module = re.sub(r'[\\/:*?"<>|]', '_', module_name)
        module_dir = os.path.join(output_dir, safe_module.lower())
        os.makedirs(module_dir, exist_ok=True)
        xmi_file = os.path.join(module_dir, f'SwMod_{safe_module}_ms.xml')

        if verbose:
            print(f"[IO] Exporting to: {xmi_file}")

        # Export
        try:
            export_package_xmi(repo, pkg, xmi_file)
            
            # Check if file was created
            if not os.path.exists(xmi_file):
                print(f"ERROR: EA export did not create file: {xmi_file}", file=sys.stderr)
                print(f"  Check EA project permissions and package access.", file=sys.stderr)
                return None
            
            size_kb = os.path.getsize(xmi_file) // 1024
            if verbose:
                print(f"[OK] Export successful: {size_kb} KB")
            return xmi_file
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return None
        except Exception as exc:
            print(f"ERROR: Unexpected error during export: {exc}", file=sys.stderr)
            return None

    finally:
        if repo:
            try:
                repo.CloseFile()
                repo.Exit()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────
# XMI Parsing Utilities
# ─────────────────────────────────────────────────────────────────────────

def _tag(local: str) -> str:
    """Create a namespaced tag."""
    return f'{{{_UML_NS}}}{local}'


def _tv(el: ET.Element, key: str) -> str:
    """Return the value of a UML TaggedValue by tag name."""
    for t in el.iter(_tag('TaggedValue')):
        if t.get('tag') == key:
            return (t.get('value') or '').strip()
    return ''


def _unescape(text: str) -> str:
    """Strip HTML tags and unescape HTML entities."""
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def _is_literal(attr: ET.Element) -> bool:
    styleex = _tv(attr, 'styleex')
    return 'IsLiteral=1' in styleex


def _is_static(attr: ET.Element) -> bool:
    return attr.get('ownerScope', '') == 'classifier'


def _is_const(attr: ET.Element) -> bool:
    return attr.get('changeable', '') == 'frozen'


def _is_collection(attr: ET.Element) -> bool:
    return _tv(attr, 'collection').lower() == 'true'


def _upper_bound(attr: ET.Element) -> str:
    return _tv(attr, 'upperBound')


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name)


# ─────────────────────────────────────────────────────────────────────────
# Data Classes (C Model)
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class CParam:
    name: str
    ctype: str
    kind: str = 'in'
    doc: str = ''


@dataclass
class COperation:
    name: str
    return_type: str
    params: List[CParam]
    doc: str
    visibility: str = 'public'
    is_static: bool = False


@dataclass
class CAttribute:
    name: str
    ctype: str
    init_value: str = ''
    doc: str = ''
    visibility: str = 'private'
    is_static: bool = False
    is_const: bool = False
    array_dim: str = ''


@dataclass
class CEnum:
    name: str
    doc: str
    members: List[CAttribute]


@dataclass
class CStruct:
    name: str
    doc: str
    members: List[CAttribute]


@dataclass
class CClass:
    name: str
    doc: str
    operations: List[COperation]
    attributes: List[CAttribute]
    gen_file: str = ''


# ─────────────────────────────────────────────────────────────────────────
# XMI Parsing & Code Generation
# ─────────────────────────────────────────────────────────────────────────

def _parse_attribute(attr_el: ET.Element) -> CAttribute:
    name = attr_el.get('name', '').strip()
    ctype = _tv(attr_el, 'type').strip()
    init = _tv(attr_el, 'initialValue').strip()
    doc = _unescape(_tv(attr_el, 'description') or _tv(attr_el, 'documentation'))
    vis = attr_el.get('visibility', 'private')
    upper = _upper_bound(attr_el)
    array_dim = ''
    if _is_collection(attr_el) and upper and upper != '1' and upper != '-1':
        array_dim = upper
    return CAttribute(
        name=name,
        ctype=ctype,
        init_value=init,
        doc=doc,
        visibility=vis,
        is_static=_is_static(attr_el),
        is_const=_is_const(attr_el),
        array_dim=array_dim,
    )


def _parse_operation(op_el: ET.Element) -> COperation:
    name = op_el.get('name', '').strip()
    vis = op_el.get('visibility', 'public')
    is_static = op_el.get('ownerScope', '') == 'classifier'
    doc = _unescape(_tv(op_el, 'documentation'))
    ret = _tv(op_el, 'type') or 'void'

    params: List[CParam] = []
    for p_el in op_el.iter(_tag('Parameter')):
        kind = p_el.get('kind', 'in')
        pname = p_el.get('name', '').strip()
        ptype = _tv(p_el, 'type').strip() or 'void'
        pdoc = _unescape(_tv(p_el, 'documentation'))
        if kind == 'return':
            ret = ptype
            continue
        params.append(CParam(name=pname, ctype=ptype, kind=kind, doc=pdoc))

    return COperation(
        name=name,
        return_type=ret,
        params=params,
        doc=doc,
        visibility=vis,
        is_static=is_static,
    )


def parse_xmi(xmi_path: str) -> tuple[str, List[CEnum], List[CStruct], List[CClass]]:
    """Parse an EA XMI 1.1 file and extract C entities."""
    tree = ET.parse(xmi_path)
    root = tree.getroot()

    pkg_el = root.find(f'.//{_tag("Package")}')
    module_name = pkg_el.get('name', 'Unknown') if pkg_el is not None else 'Unknown'

    enums: List[CEnum] = []
    structs: List[CStruct] = []
    classes: List[CClass] = []

    for cls_el in root.iter(_tag('Class')):
        cls_name = cls_el.get('name', '').strip()
        if not cls_name or cls_name == 'EARootClass':
            continue

        cls_doc = _unescape(_tv(cls_el, 'documentation'))
        stereo = _tv(cls_el, 'stereotype').lower()
        ea_stype = _tv(cls_el, 'ea_stype').lower()
        xref = _tv(cls_el, '$ea_xref_property')

        attrs = [_parse_attribute(a) for a in cls_el.iter(_tag('Attribute'))]
        has_literals = any('IsLiteral=1' in (_tv(a, 'styleex')) for a in cls_el.iter(_tag('Attribute')))
        is_enum = ('enum' in stereo or ea_stype == 'enumeration' or 'enumeration' in xref.lower() or has_literals)
        is_struct = ('struct' in stereo or ea_stype in ('struct', 'structure'))
        ops = [_parse_operation(o) for o in cls_el.iter(_tag('Operation'))]

        if is_enum:
            enums.append(CEnum(name=cls_name, doc=cls_doc, members=attrs))
        elif is_struct:
            structs.append(CStruct(name=cls_name, doc=cls_doc, members=attrs))
        else:
            gen_file = _tv(cls_el, 'genfile')
            classes.append(CClass(name=cls_name, doc=cls_doc, operations=ops, attributes=attrs, gen_file=gen_file))

    return module_name, enums, structs, classes


def load_activity_diagrams(diagrams_dir: str, module_name: str) -> Dict[str, ET.Element]:
    """Load activity diagram XML elements for functions."""
    func_map: Dict[str, ET.Element] = {}
    if not os.path.isdir(diagrams_dir):
        return func_map

    safe = re.escape(module_name)
    pattern = re.compile(rf'SwDetailedDesign.*{safe}.*\.xml$', re.I)

    for fname in os.listdir(diagrams_dir):
        if not pattern.search(fname):
            continue
        fpath = os.path.join(diagrams_dir, fname)
        try:
            tree = ET.parse(fpath)
        except ET.ParseError:
            continue

        root = tree.getroot()
        module_el = root.find('Module') or root
        for func_el in module_el.findall('Function'):
            name = func_el.get('name', '').strip()
            if name and name not in func_map:
                func_map[name] = func_el

    return func_map


# ─────────────────────────────────────────────────────────────────────────
# C Code Emission
# ─────────────────────────────────────────────────────────────────────────

_GUARD_RE = re.compile(r'[^A-Z0-9_]')


def _header_guard(name: str) -> str:
    return _GUARD_RE.sub('_', name.upper()) + '_H'


def _doc_comment(text: str, indent: str = '') -> List[str]:
    if not text:
        return []
    lines = text.splitlines()
    if len(lines) == 1:
        return [f'{indent}/** {lines[0]} */']
    result = [f'{indent}/**']
    for line in lines:
        result.append(f'{indent} * {line}' if line else f'{indent} *')
    result.append(f'{indent} */')
    return result


def _format_param_list(params: List[CParam]) -> str:
    if not params:
        return 'void'
    parts = []
    for p in params:
        pointer = '*' if p.kind in ('inout', 'out') else ''
        parts.append(f'{p.ctype} {pointer}{p.name}'.strip())
    return ', '.join(parts)


def _emit_enum(e: CEnum) -> List[str]:
    lines: List[str] = []
    lines += _doc_comment(e.doc)
    lines.append('typedef enum')
    lines.append('{')
    for i, m in enumerate(e.members):
        comma = ',' if i < len(e.members) - 1 else ''
        if m.doc:
            lines.append(f'    {m.name}{comma}  /**< {m.doc} */')
        else:
            lines.append(f'    {m.name}{comma}')
    lines.append(f'}} {e.name};')
    lines.append('')
    return lines


def _emit_struct(s: CStruct) -> List[str]:
    lines: List[str] = []
    lines += _doc_comment(s.doc)
    lines.append('typedef struct')
    lines.append('{')
    for m in s.members:
        ctype = m.ctype or 'uint8'
        if m.array_dim:
            decl = f'    {ctype} {m.name}[{m.array_dim}];'
        else:
            decl = f'    {ctype} {m.name};'
        if m.doc:
            lines.append(f'{decl}  /**< {m.doc} */')
        else:
            lines.append(decl)
    lines.append(f'}} {s.name};')
    lines.append('')
    return lines


def _emit_variable_decl(a: CAttribute, extern: bool = False, force_static: bool = False) -> str:
    ctype = a.ctype or 'uint8'
    prefix = ''
    if extern:
        prefix = 'extern '
    elif a.is_static or force_static:
        prefix = 'static '
    const = 'const ' if a.is_const else ''
    if a.array_dim:
        decl = f'{prefix}{const}{ctype} {a.name}[{a.array_dim}]'
    else:
        decl = f'{prefix}{const}{ctype} {a.name}'
    if not extern and a.init_value:
        decl += f' = {a.init_value}'
    decl += ';'
    return decl


def _emit_prototype(op: COperation, static: bool = False) -> str:
    prefix = 'static ' if static or op.is_static else ''
    params = _format_param_list(op.params)
    return f'{prefix}{op.return_type} {op.name}({params});'


def _emit_function_def(op: COperation, static: bool = False, func_el: Optional[ET.Element] = None) -> List[str]:
    """Emit a full C function definition with Doxygen block.

    When *func_el* is provided (a <Function> element from a
    SwDetailedDesignDiagram XML written by export_activity_diagrams.py),
    the following diagram-sourced metadata is used in preference over
    XMI-only data:

    * func_el[notes]         - EA operation notes  -> @brief / @details
    * func_el/<Param>        - per-parameter notes  -> @param
    * <Step type=Interface>  - traceability links   -> @Trace
    * step flow graph        - full activity flow   -> function body
    """
    lines: List[str] = []

    # -- Collect diagram-sourced metadata ----------------------------------
    # EA operation notes stored by export_activity_diagrams._get_operation_metadata
    notes: str = ''
    if func_el is not None:
        notes = (func_el.get('notes') or '').strip()
    if not notes:
        notes = op.doc or ''

    # Per-parameter notes written by steps_to_xml_element as <Param notes=...>
    diag_param_notes: Dict[str, str] = {}
    if func_el is not None:
        for p_el in func_el.findall('Param'):
            pname = (p_el.get('name') or '').strip()
            pnote = (p_el.get('notes') or '').strip()
            if pname and pnote:
                diag_param_notes[pname] = pnote

    # Traceability links from <Step type="Interface"> nodes
    traces: List[Tuple[str, str]] = []
    if func_el is not None and _collect_traces is not None:
        traces = _collect_traces(func_el)

    # -- Doxygen comment block ---------------------------------------------
    lines.append('/**')
    if notes:
        brief, _, rest = notes.partition('.')
        lines.append(f' * @brief  {brief.strip()}.')
        if rest.strip():
            lines.append(f' * @details {rest.strip()}')
    else:
        lines.append(f' * @brief  {op.name}')

    if op.params:
        lines.append(' *')
        for p in op.params:
            direction = f'[{p.kind}]' if p.kind else ''
            # Prefer diagram param notes; fall back to XMI p.doc
            pdoc = diag_param_notes.get(p.name, '') or p.doc or ''
            pdoc_str = f'  {pdoc}' if pdoc else ''
            lines.append(f' * @param  {direction} {p.name}{pdoc_str}'.rstrip())

    if op.return_type and op.return_type not in ('void', 'Void'):
        lines.append(f' * @return {op.return_type}')

    if traces:
        lines.append(' *')
        for doc_type, traced_id in traces:
            lines.append(f' * @Trace  {doc_type}: {traced_id}')

    lines.append(' *')
    lines.append(' * @note   AUTO-GENERATED SKELETON -- review and complete all TODO items.')
    lines.append(' */')

    # -- Function signature ------------------------------------------------
    prefix = 'static ' if static or op.is_static else ''
    params = _format_param_list(op.params)
    lines.append(f'{prefix}{op.return_type} {op.name}({params})')
    lines.append('{')

    # -- Function body from activity diagram --------------------------------
    if func_el is not None and FlowGraph is not None:
        graph = _parse_function(func_el)
        entry = graph.find_entry()
        emitter = CEmitter()
        if entry is None:
            emitter.emit('    /* TODO: no entry point found in activity diagram */')
        else:
            if op.return_type and op.return_type not in ('void', 'Void'):
                emitter.emit(f'    {op.return_type} retVal = ({op.return_type})0;')
            _emit_step(entry, graph, emitter, '    ', set(), set(), [], None)
            if op.return_type and op.return_type not in ('void', 'Void'):
                emitter.emit('    return retVal;')
        lines.extend(emitter.lines())
    else:
        if op.return_type and op.return_type not in ('void', 'Void'):
            lines.append(f'    {op.return_type} retVal = ({op.return_type})0;')
            lines.append('    /* TODO: implement */')
            lines.append('    return retVal;')
        else:
            lines.append('    /* TODO: implement */')

    lines.append('}')
    lines.append('')
    return lines


def generate_header(module_name: str, enums: List[CEnum], structs: List[CStruct], classes: List[CClass]) -> List[str]:
    guard = _header_guard(module_name)
    lines: List[str] = []

    lines += [
        f'/**',
        f' * @file    {module_name}.h',
        f' * @brief   Auto-generated header for {module_name}',
        f' *',
        f' * AUTO-GENERATED from EA XMI export.',
        f' * Review and complete before use.',
        f' */',
        '',
        f'#ifndef {guard}',
        f'#define {guard}',
        '',
        '/* TODO: include required headers */',
        '#include "stdtypes.h"',
        '',
    ]

    if enums:
        lines += ['/* ============================================================ */',
                  '/* Enumerations                                                   */',
                  '/* ============================================================ */',
                  '']
        for e in enums:
            lines += _emit_enum(e)

    if structs:
        lines += ['/* ============================================================ */',
                  '/* Structures                                                     */',
                  '/* ============================================================ */',
                  '']
        for s in structs:
            lines += _emit_struct(s)

    pub_vars = [a for c in classes for a in c.attributes if a.visibility == 'public']
    pub_ops = [o for c in classes for o in c.operations if o.visibility == 'public']
    priv_ops = [o for c in classes for o in c.operations if o.visibility == 'private']

    if pub_vars:
        lines += ['/* ============================================================ */',
                  '/* Public variable declarations                                   */',
                  '/* ============================================================ */',
                  '']
        for a in pub_vars:
            lines += _doc_comment(a.doc)
            lines.append(_emit_variable_decl(a, extern=True))
            lines.append('')

    if pub_ops:
        lines += ['/* ============================================================ */',
                  '/* Public function prototypes                                     */',
                  '/* ============================================================ */',
                  '']
        for op in pub_ops:
            lines += _doc_comment(op.doc)
            lines.append(_emit_prototype(op, static=False))
            lines.append('')

    if priv_ops:
        lines += ['/* ============================================================ */',
                  '/* Private function prototypes (module-internal)                  */',
                  '/* ============================================================ */',
                  '']
        for op in priv_ops:
            lines += _doc_comment(op.doc)
            lines.append(_emit_prototype(op, static=True))
            lines.append('')

    lines += [f'#endif /* {guard} */', '']
    return lines


def generate_source(module_name: str, classes: List[CClass], activity_funcs: Optional[Dict[str, ET.Element]] = None) -> List[str]:
    lines: List[str] = []

    lines += [
        f'/**',
        f' * @file    {module_name}.c',
        f' * @brief   Auto-generated source for {module_name}',
        f' *',
        f' * AUTO-GENERATED from EA XMI export.',
        f' * Review and complete before use.',
        f' */',
        '',
        f'#include "{module_name}.h"',
        '',
    ]

    priv_vars = [a for c in classes for a in c.attributes if a.visibility == 'private']
    static_class_vars = [a for c in classes for a in c.attributes if a.is_static]
    all_defs = list({a.name: a for a in priv_vars + static_class_vars}.values())

    if all_defs:
        lines += ['/* ============================================================ */',
                  '/* Module-private variable definitions                            */',
                  '/* ============================================================ */',
                  '']
        for a in all_defs:
            if a.doc:
                lines += _doc_comment(a.doc)
            lines.append(_emit_variable_decl(a, extern=False, force_static=True))
            lines.append('')

    all_ops = [o for c in classes for o in c.operations]
    if all_ops:
        lines += ['/* ============================================================ */',
                  '/* Function definitions                                           */',
                  '/* ============================================================ */',
                  '']
        for op in all_ops:
            is_priv = op.visibility == 'private' or op.is_static
            func_el = (activity_funcs or {}).get(op.name)
            lines += _emit_function_def(op, static=is_priv, func_el=func_el)

    return lines


def process_xmi_file(xmi_path: str, output_dir: str, diagrams_dir: str = '', verbose: bool = False) -> bool:
    """Process XMI file and generate C code. Returns True on success."""
    try:
        module_name, enums, structs, classes = parse_xmi(xmi_path)

        if not diagrams_dir:
            diagrams_dir = os.path.dirname(xmi_path)

        activity_funcs = load_activity_diagrams(diagrams_dir, module_name)
        
        # Diagnostic: Show which diagrams are being used
        if verbose:
            print(f"\n  [DATA] Diagrams loaded:")
            if activity_funcs:
                for fname, count in {f.get('name', '?'): len([o for c in classes for o in c.operations if o.name == f.get('name', '?')]) for f in [activity_funcs.get(k) for k in activity_funcs]}.items():
                    print(f"    - {fname} (used for function bodies)")
            else:
                print(f"    • No diagrams with function bodies found")
        
        matched = len([o for c in classes for o in c.operations if o.name in activity_funcs])
        total_ops = sum(len(c.operations) for c in classes)

        safe_name = _sanitize_filename(module_name)
        os.makedirs(output_dir, exist_ok=True)

        h_path = os.path.join(output_dir, safe_name + '.h')
        c_path = os.path.join(output_dir, safe_name + '.c')

        h_lines = generate_header(module_name, enums, structs, classes)
        c_lines = generate_source(module_name, classes, activity_funcs)

        with open(h_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(h_lines))
        with open(c_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(c_lines))

        print(f'\n[OK] Generated: {h_path}')
        print(f'[OK] Generated: {c_path}')
        print(f'\n[STATS] Code Statistics:')
        print(f'   Enums  : {len(enums)}')
        print(f'   Structs: {len(structs)}')
        print(f'   Classes: {len(classes)}  ({total_ops} ops, {sum(len(c.attributes) for c in classes)} attrs)')
        print(f'   Bodies from diagrams: {matched}/{total_ops} functions ({100*matched//total_ops if total_ops > 0 else 0}%)')
        
        # Show source information
        print(f'\n[INFO] Generation Sources:')
        print(f'   XMI file: {xmi_path}')
        print(f'   Diagrams: {diagrams_dir}')
        
        return True
    except Exception as e:
        print(f"ERROR: Failed to process XMI: {e}", file=sys.stderr)
        return False

def normalize_module_name(name: str) -> str:
    """Normalize module name to SwMod_<Name> format."""
    name = name.strip()
    # Remove SwMod_ prefix if present
    if name.lower().startswith('swmod_'):
        name = name[6:]
    # Capitalize first letter, keep rest as-is (preserve case)
    if name:
        name = name[0].upper() + name[1:]
    return f'SwMod_{name}'


def find_xmi_files(module_name: str, input_dir: str, xmi_override: Optional[str] = None) -> List[str]:
    """
    Find XMI files for the given module.
    
    Search order:
    1. Use xmi_override if provided
    2. Look in input/<module_name>/ for *_ms.xml files
    3. Look in ai_output/ for SwMod_<Name>*_ms.xml files
    """
    if xmi_override:
        if os.path.isfile(xmi_override):
            return [os.path.abspath(xmi_override)]
        print(f"WARNING: XMI override file not found: {xmi_override}", file=sys.stderr)
        return []

    xmi_files = []
    swmod_name = normalize_module_name(module_name)
    base_name = swmod_name.replace('SwMod_', '')

    # Search in input/<module_name>/
    input_module_dir = os.path.join(input_dir, base_name.lower())
    if os.path.isdir(input_module_dir):
        for fname in os.listdir(input_module_dir):
            if fname.endswith('_ms.xml'):
                xmi_files.append(os.path.abspath(os.path.join(input_module_dir, fname)))

    # Search in ai_output/
    if os.path.isdir(OUTPUT_DIR):
        for fname in os.listdir(OUTPUT_DIR):
            if swmod_name.lower() in fname.lower() and fname.endswith('_ms.xml'):
                xmi_files.append(os.path.abspath(os.path.join(OUTPUT_DIR, fname)))

    return list(set(xmi_files))  # Remove duplicates


def find_diagram_files(module_name: str, diagrams_override: Optional[str] = None) -> List[str]:
    """
    Find SwDetailedDesignDiagram XML files for the given module.
    
    Search order:
    1. Use diagrams_override if provided
    2. Look in input/<module_name>/
    3. Look in ai_output/
    """
    if diagrams_override and os.path.isdir(diagrams_override):
        diagram_files = []
        for fname in os.listdir(diagrams_override):
            if DIAGRAM_PATTERN.search(fname):
                diagram_files.append(os.path.abspath(os.path.join(diagrams_override, fname)))
        if diagram_files:
            return diagram_files

    diagram_files = []
    base_name = normalize_module_name(module_name).replace('SwMod_', '')

    # Search in input/<module_name>/
    input_module_dir = os.path.join('input', base_name.lower())
    if os.path.isdir(input_module_dir):
        for fname in os.listdir(input_module_dir):
            if DIAGRAM_PATTERN.search(fname):
                diagram_files.append(os.path.abspath(os.path.join(input_module_dir, fname)))

    # Search in ai_output/
    if os.path.isdir(OUTPUT_DIR):
        for fname in os.listdir(OUTPUT_DIR):
            if DIAGRAM_PATTERN.search(fname) and base_name.lower() in fname.lower():
                diagram_files.append(os.path.abspath(os.path.join(OUTPUT_DIR, fname)))

    return list(set(diagram_files))  # Remove duplicates


def determine_target_folder(xmi_file: str, diagrams_dir: str, args_target: Optional[str],
                            module_name: str, input_dir: str) -> tuple[str, str]:
    """
    Determine the output folder path.
    
    Output structure: ai_output/<module>/generated_c/
    
    Returns:
        (target_type: str, output_path: str)
        target_type: 'generated_c' (for informational purposes)
        output_path: ai_output/<module>/generated_c
    """
    # Normalize module name
    base_name = normalize_module_name(module_name).replace('SwMod_', '')
    
    # Output path is always ai_output/<module>/generated_c/
    output_path = os.path.join(DEFAULT_OUTPUT_BASE, base_name.lower(), 'generated_c')
    target_type = 'generated_c'

    return target_type, output_path


def collect_functions(xmi_file: str) -> List[str]:
    """
    Extract function names from an XMI file (for documentation).
    This is a simple extraction for display purposes.
    """
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(xmi_file)
        root = tree.getroot()
        functions = []
        # Simple namespace-agnostic search
        for elem in root.iter():
            if 'Operation' in elem.tag:
                name = elem.get('name', '')
                if name and name not in functions:
                    functions.append(name)
        return functions
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────
# Main generation logic
# ─────────────────────────────────────────────────────────────────────────

def generate_from_xmi(xmi_file: str, output_dir: str, diagrams_dir: str,
                      dry_run: bool = False, verbose: bool = False) -> bool:
    """
    Generate C files from XMI (now integrated, no subprocess needed).
    Returns True if successful.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        if verbose:
            print(f"\n[PROC] Generation Process:")
            print(f"  - XMI input: {xmi_file}")
            print(f"  - Output directory: {output_dir}")
            if diagrams_dir:
                print(f"  - Diagrams directory: {diagrams_dir}")

        if dry_run:
            print(f"\n[DRY RUN] Would generate C from: {xmi_file}")
            print(f"[DRY RUN] Output to: {output_dir}")
            return True

        return process_xmi_file(xmi_file, output_dir, diagrams_dir, verbose)

    except Exception as e:
        print(f"ERROR: Failed to generate from XMI: {e}", file=sys.stderr)
        return False


def generate_from_diagrams(diagrams_dir, output_dir,
                           json_mapping=None,
                           dry_run=False, verbose=False):
    try:
        os.makedirs(output_dir, exist_ok=True)
        if verbose:
            print('  Generating C from diagrams: ' + diagrams_dir)
            print('  Output directory: ' + output_dir)
            if json_mapping:
                print('  JSON class mapping: ' + json_mapping)
        if dry_run:
            print('  [DRY RUN] Would generate C from diagrams in: ' + diagrams_dir)
            print('  [DRY RUN] Output to: ' + output_dir)
            return True
        xml_files = sorted(
            os.path.join(diagrams_dir, f)
            for f in os.listdir(diagrams_dir)
            if f.lower().endswith('.xml') and 'SwDetailedDesign' in f
        )
        if not xml_files:
            print('ERROR: No SwDetailedDesign XML files found in ' + diagrams_dir, file=sys.stderr)
            return False
        if json_mapping and os.path.isfile(json_mapping) and _xml_to_c_per_class is not None:
            success = True
            for xml_path in xml_files:
                try:
                    generated = _xml_to_c_per_class(xml_path, json_mapping, output_dir)
                    for out in generated:
                        print('Generated: ' + out)
                except Exception as exc:
                    print('ERROR processing ' + xml_path + ': ' + str(exc), file=sys.stderr)
                    success = False
            return success
        if _xml_to_c_process_file is not None:
            success = True
            for xml_path in xml_files:
                try:
                    out = _xml_to_c_process_file(xml_path, output_dir)
                    print('Generated: ' + out)
                except Exception as exc:
                    print('ERROR processing ' + xml_path + ': ' + str(exc), file=sys.stderr)
                    success = False
            return success
        import subprocess
        xml_to_c_script = os.path.join(os.path.dirname(__file__), 'xml_to_c.py')
        for xml_path in xml_files:
            cmd = [sys.executable, xml_to_c_script, xml_path, output_dir]
            if json_mapping and os.path.isfile(json_mapping):
                cmd += ['--per-class', '--json-mapping', json_mapping]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                print('ERROR: xml_to_c.py failed (code ' + str(result.returncode) + ')', file=sys.stderr)
                if result.stderr:
                    print(result.stderr, file=sys.stderr)
                return False
            if verbose and result.stdout:
                print(result.stdout)
        return True
    except Exception as e:
        print('ERROR: Failed to generate from diagrams: ' + str(e), file=sys.stderr)
        return False

def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description='Generate C source code from EA diagrams for a given module.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument('module', metavar='MODULE_NAME',
                        help='Module name (e.g., touchsm, desctl, common)')
    parser.add_argument('--ea-package', dest='ea_package',
                        help='Export from EA: package path or GUID (e.g., "{D94609F2-A53D-4f95-A4DC-8CDB7FAA3AFE}")')
    parser.add_argument('--xmi', dest='xmi_file',
                        help='Path to XMI file (overrides auto-detection)')
    parser.add_argument('--diagrams', dest='diagrams_dir',
                        help='Directory containing SwDetailedDesignDiagram XML files')
    parser.add_argument('--output', dest='output_dir',
                        help='Force output directory (default: ai_output/<module>/generated_c/)')
    parser.add_argument('--input-dir', default=DEFAULT_INPUT_DIR,
                        help='Base input directory (default: input/)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be generated, don\'t write files')
    parser.add_argument('--force', action='store_true',
                        help='Overwrite existing files without prompting')
    parser.add_argument('--json-mapping', dest='json_mapping', default=None,
                        help='Path to SwMod_*_Functions.json for per-class generation')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print detailed step information')

    args = parser.parse_args(argv[1:])

    # ── Normalize and validate module name ────────────────────────────────
    swmod_name = normalize_module_name(args.module)
    base_name = swmod_name.replace('SwMod_', '')

    if args.verbose:
        print(f"Module: {swmod_name}")
        print(f"Base name: {base_name}")

    # ── Export from EA if --ea-package specified ──────────────────────────
    if args.ea_package:
        if args.verbose:
            print(f"\n[EA] EA Export Phase:")
        xmi_from_ea = export_xmi_from_ea(
            args.ea_package, 
            base_name,
            output_dir='ai_output',
            verbose=args.verbose
        )
        if xmi_from_ea:
            if args.verbose:
                print(f"[OK] Using exported XMI: {xmi_from_ea}")
            args.xmi_file = xmi_from_ea
        else:
            print(f"ERROR: Failed to export XMI from EA", file=sys.stderr)
            return 2

    # ── Find input files ─────────────────────────────────────────────────
    xmi_files = find_xmi_files(base_name, args.input_dir, args.xmi_file)
    diagram_files = find_diagram_files(base_name, args.diagrams_dir)

    if not xmi_files and not diagram_files:
        print(f"ERROR: No XMI or diagram files found for module '{swmod_name}'", file=sys.stderr)
        print(f"  Searched in:")
        print(f"    - {os.path.join(args.input_dir, base_name.lower())}/")
        print(f"    - {OUTPUT_DIR}/")
        return 1

    if args.verbose:
        if xmi_files:
            print(f"\n[FILES] Found {len(xmi_files)} XMI file(s):")
            for f in xmi_files:
                print(f"     {f}")
        if diagram_files:
            print(f"[DIAG] Found {len(diagram_files)} diagram file(s):")
            for f in diagram_files:
                print(f"     {f}")

    # ── Determine output folder ────────────────────────────────────────────
    primary_input = xmi_files[0] if xmi_files else (diagram_files[0] if diagram_files else '')
    diagrams_dir_to_use = args.diagrams_dir or (os.path.dirname(diagram_files[0]) if diagram_files else '')

    target_type, output_dir = determine_target_folder(
        primary_input, diagrams_dir_to_use, None, base_name, args.input_dir
    )

    # Override if --output is specified
    if args.output_dir:
        output_dir = args.output_dir
        if args.verbose:
            print(f"[CFG] Output override: --output {output_dir}")

    if args.verbose:
        print(f"\n[TARGET] Target Information:")
        print(f"   Target type: {target_type}")
        print(f"   Output directory: {output_dir}")

    # ── Check for existing files ───────────────────────────────────────────
    if os.path.isdir(output_dir) and os.listdir(output_dir) and not args.force and not args.dry_run:
        print(f"Output directory already exists with files: {output_dir}")
        response = input("Overwrite? (y/N): ").strip().lower()
        if response != 'y':
            print("Cancelled.")
            return 0

    # ── Generate C files ──────────────────────────────────────────────────
    success = True

    if xmi_files:
        diagrams_for_xmi = diagrams_dir_to_use or os.path.dirname(xmi_files[0])
        for xmi_file in xmi_files:
            if not generate_from_xmi(xmi_file, output_dir, diagrams_for_xmi, args.dry_run, args.verbose):
                success = False

    if diagram_files and not xmi_files:
        # Auto-detect JSON class mapping: ai_output/doc/{swmod_name}_Functions.json
        json_map = args.json_mapping or os.path.join(OUTPUT_DIR, 'doc', swmod_name + '_Functions.json')
        if not os.path.isfile(json_map):
            json_map = None
        if args.verbose:
            if json_map:
                print('[JSON] Per-class mapping: ' + json_map)
            else:
                print('[JSON] No class mapping found - using single-file mode')
        if not generate_from_diagrams(diagrams_dir_to_use, output_dir, json_map, args.dry_run, args.verbose):
            success = False

    if success:
        if args.dry_run:
            print(f"\n[DRY RUN] Generation would complete successfully.")
            print(f"  Target: {target_type}")
            print(f"  Output: {output_dir}")
        else:
            print(f"\nGeneration completed successfully.")
            print(f"  Target: {target_type}")
            print(f"  Output: {output_dir}")
            if os.path.isdir(output_dir):
                files = os.listdir(output_dir)
                print(f"  Generated files: {', '.join(sorted(files))}")
        return 0
    else:
        print(f"\nGeneration failed.", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
