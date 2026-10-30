"""
Tool: ea_import_diagrams_from_xml.py  (internal — called by import_code_to_diagrams.py)

Imports C-parsed activity flow graphs into Enterprise Architect via COM.

For each function found in the SwDetailedDesignDiagram XML files (produced by
import_code_to_diagrams.py or the original src/main.py), this tool:

  1. Locates the target SwMod_* package in EA (requires EA to be running).
  2. Finds (or creates) the Behavior sub-package.
  3. For each function:
       a) If an Activity element with that name already exists:
            - Reconciles sub-elements (Action / Decision / StateNode) against
              the XML steps:  add missing, update changed names, remove deleted.
            - Reconciles ControlFlow connectors against the XML flows.
       b) If no Activity element exists yet:
            - Creates a new Activity element.
            - Creates all steps as sub-elements.
            - Creates ControlFlow connectors between them.
            - Creates an Activity diagram and places all elements on it.
  4. Writes a change report describing every EA object created/updated/deleted.

Requirements
------------
- Enterprise Architect must be running with the project open.
- Run with the 32-bit Python interpreter (.venv32) that has pywin32 installed.
- The SwDetailedDesignDiagram XML files must already exist (run
  import_code_to_diagrams.py or src/main.py first).

Usage
-----
This tool is normally invoked automatically by import_code_to_diagrams.py
via the --push-to-ea flag.  It can also be run standalone:

Single module:
    .venv32\\Scripts\\python.exe scripts/ea_import_diagrams_from_xml.py SwMod_TouchSM

Single module, specific XML dir:
    .venv32\\Scripts\\python.exe scripts/ea_import_diagrams_from_xml.py SwMod_TouchSM --diagrams ai_output/

Dry run (parse + diff, no EA writes):
    .venv32\\Scripts\\python.exe scripts/ea_import_diagrams_from_xml.py SwMod_TouchSM --dry-run

Save report:
    .venv32\\Scripts\\python.exe scripts/ea_import_diagrams_from_xml.py SwMod_TouchSM --report out/report.txt

Restrict to specific functions:
    .venv32\\Scripts\\python.exe scripts/ea_import_diagrams_from_xml.py SwMod_TouchSM --functions TouchSM_vInit,TouchSM_vMainFunction
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import win32com.client

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
_TOOL_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_TOOL_DIR)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _TOOL_DIR)

from config.settings import EA_PROJECT, OUTPUT_DIR  # noqa: E402

_DEFAULT_DIAGRAMS_DIR = OUTPUT_DIR

# ---------------------------------------------------------------------------
# Layout constants  (EA uses integer pixel coordinates)
# In EA DiagramObject coordinates:
#   less-negative Y = higher on screen  (top of diagram)
#   more-negative Y = lower  on screen  (bottom of diagram)
# Calibrated against the reference template:
#   TouchSM__vConsolidateErrorAdapt (ID=137612)
# ---------------------------------------------------------------------------
_STEP_W    = 240   # Action / Decision element width  (px)
_STEP_H    = 70    # Action / Decision element height (px)
_NODE_W    = 30    # StateNode circle diameter         (px)
_NODE_H    = 30
_COL_X     = 360   # left edge of Action/Decision elements (main / TRUE-down branch)
               #  FALSE branch is placed to the LEFT at (_COL_X - _STEP_W - _BRANCH_GAP)
_GAP       = 30    # vertical gap between consecutive elements  (px)
_BRANCH_GAP = 40   # horizontal gap between branch columns
_ORIGIN_Y  = -180  # top-edge Y of the first element (entry StateNode)
                   # Must be negative enough so container top (_ORIGIN_Y + _PAD_TOP)
                   # stays negative — positive y falls in the swimlane header region.
                   # Template TouchSM__vConsolidateErrorAdapt has entry StateNode at -180.

# Activity container DiagramObject padding  (px around the element group)
_PAD_LEFT   = 80   # extra space left of leftmost element
_PAD_RIGHT  = 80   # extra space right of rightmost element
_PAD_TOP    = 40   # extra space above first element (swimlane header area)
_PAD_BOTTOM = 40   # extra space below last element

# Diagram StyleEx — matches template TouchSM__vConsolidateErrorAdapt
_DIAG_STYLE_EX = (
    'ExcludeRTF=0;DocAll=0;HideQuals=0;AttPkg=1;ShowTests=0;ShowMaint=0;'
    'SuppressFOC=1;MatrixActive=0;SwimlanesActive=1;KanbanActive=0;'
    'MatrixLineWidth=1;MatrixLineClr=0;MatrixLocked=0;'
    'TConnectorNotation=UML 2.1;TExplicitNavigability=0;'
    'AdvancedElementProps=1;AdvancedFeatureProps=1;AdvancedConnectorProps=1;'
    'm_bElementClassifier=1;ProfileData=;MDGDgm=;STBLDgm=;ShowNotes=0;'
    'VisibleAttributeDetail=0;ShowOpRetType=1;SuppressBrackets=0;'
    'SuppConnectorLabels=0;PrintPageHeadFoot=0;ShowAsList=0;'
    'SuppressedCompartments=;Theme=:119;'
)

# Style applied to the Activity container DiagramObject (matches template)
_ACTIVITY_CONTAINER_STYLE = (
    'BCol=-1;BFol=-1;LCol=-1;LWth=-1;NSL=0;'
    'black=0;bold=0;charset=0;fontsz=0;italic=0;pitch=0;ul=0;'
)


# ===========================================================================
# XML loading helpers
# ===========================================================================

@dataclass
class XmlStep:
    name:  str
    type:  str   # StateNode | Action | Decision
    guid:  str
    flows: List[Tuple[str, str, str]]  # (toName, toGuid, guard)
    ea_id: int = 0                      # EA ElementID (stored back into XML after creation)


@dataclass
class XmlFunction:
    name:        str
    guid:        str
    stereotype:  str
    diagram_guid: str
    steps:       Dict[str, XmlStep]   # guid → XmlStep
    return_type: str = ''   # from returnType attr in XML
    raw_params:  str = ''   # from rawParams attr in XML


def load_xml_functions(diagrams_dir: str, module_name: str) -> Dict[str, XmlFunction]:
    """Return all <Function> elements from diagram XMLs for *module_name*."""
    funcs: Dict[str, XmlFunction] = {}
    try:
        for fname in sorted(os.listdir(diagrams_dir)):
            if ('SwDetailedDesignDiagram' not in fname
                    or module_name not in fname
                    or not fname.endswith('.xml')):
                continue
            fpath = os.path.join(diagrams_dir, fname)
            try:
                tree = ET.parse(fpath)
            except ET.ParseError as exc:
                print(f'  WARNING: cannot parse {fname}: {exc}', file=sys.stderr)
                continue
            root = tree.getroot()
            for mod_el in root.findall('Module'):
                for func_el in mod_el.findall('Function'):
                    fname2 = (func_el.get('name') or '').strip()
                    if not fname2:
                        continue
                    steps: Dict[str, XmlStep] = {}
                    for s in func_el.findall('Step'):
                        g = (s.get('guid') or '').strip()
                        n = (s.get('name') or '').strip()
                        t = (s.get('type') or '').strip()
                        flows = [
                            (
                                (f.get('toName') or '').strip(),
                                (f.get('toGuid') or '').strip(),
                                (f.get('guard')  or '').strip(),
                            )
                            for f in s.findall('Flow')
                        ]
                        ea_id = int(s.get('eaId') or 0)
                        if g:
                            steps[g] = XmlStep(name=n, type=t, guid=g, flows=flows, ea_id=ea_id)
                    funcs[fname2] = XmlFunction(
                        name=fname2,
                        guid=(func_el.get('guid') or '').strip(),
                        stereotype=(func_el.get('stereotype') or '').strip(),
                        diagram_guid=(func_el.get('diagramGuid') or '').strip(),
                        steps=steps,
                        return_type=(func_el.get('returnType') or '').strip(),
                        raw_params=(func_el.get('rawParams') or '').strip(),
                    )
    except OSError as exc:
        print(f'ERROR: cannot read diagrams directory: {exc}', file=sys.stderr)
        sys.exit(1)
    return funcs


# ===========================================================================
# EA navigation helpers
# ===========================================================================

def _safe(obj, prop: str, default='') -> str:
    try:
        v = getattr(obj, prop)
        return str(v) if v is not None else default
    except Exception:
        return default


def _find_package_all(root_pkg, name, max_depth=10, _path=''):
    results = []
    cur_path = (_path + '/' + root_pkg.Name) if _path else root_pkg.Name
    if root_pkg.Name == name:
        results.append((root_pkg, cur_path))
        return results
    if max_depth <= 0:
        return results
    try:
        for sp in root_pkg.Packages:
            results.extend(_find_package_all(sp, name, max_depth - 1, cur_path))
    except Exception:
        pass
    return results


def find_package(root_pkg, name: str, max_depth: int = 10):
    results = _find_package_all(root_pkg, name, max_depth)
    if not results:
        return None
    if len(results) == 1:
        return results[0][0]
    preferred = [r for r in results if 'PlatformConfigs' not in r[1]]
    if len(preferred) == 1:
        pkg, path = preferred[0]
        print(f'INFO: Multiple packages named {name!r}; auto-selected non-PlatformConfigs: {path}')
        return pkg
    return results[0][0]
def _collect_source_file_matches(
    pkg, stem: str, path: str, results: list, max_depth: int = 12
) -> None:
    """Walk the package tree and collect (swmod_pkg, ea_path, tv_val, el_name)
    for every element whose 'SourceFile' tagged value closely matches *stem*.
    Uses fuzzy matching (ratio >= 0.80) to handle typos in EA data."""
    import difflib
    if max_depth <= 0:
        return
    full_path = path + '/' + pkg.Name
    for el in pkg.Elements:
        try:
            for tv in el.TaggedValues:
                if tv.Name.lower() == 'sourcefile':
                    tv_val = (tv.Value or '').lower().strip()
                    if not tv_val:
                        continue
                    # Exact match or fuzzy match (handles EA typos like
                    # 'toushsm1c1' instead of 'touchsm1c1')
                    ratio = difflib.SequenceMatcher(
                        None, stem, tv_val).ratio()
                    if ratio >= 0.80:
                        results.append((pkg, full_path, tv_val, el.Name, ratio, el))
                        return   # one match per package is enough
        except Exception:
            pass
    for sp in pkg.Packages:
        _collect_source_file_matches(sp, stem, full_path, results, max_depth - 1)


def find_module_by_source_file(
    repo, source_filepath: str
) -> Optional[Tuple[object, str]]:
    """
    Locate the exact SwMod_* package in EA that owns the given source file.

    EA elements carry a 'SourceFile' tagged value (e.g. 'touchsm1c1') that
    corresponds to the C source file stem.  By matching on that value we can
    distinguish between the Project-layer and Platform-layer instances of the
    same module package.

    Returns (package, full_ea_path) or None if no match is found.
    """
    stem = os.path.splitext(os.path.basename(source_filepath))[0].lower()
    results: list = []
    for model in repo.Models:
        _collect_source_file_matches(model, stem, '', results)

    if not results:
        return None

    # Sort by match ratio descending, then prefer Project layer over Platform
    results.sort(key=lambda r: (r[4], '/Project/' in r[1]), reverse=True)

    for pkg, path, tv_val, el_name, ratio, class_el in results:
        if '/Project/' in path:
            print(f'  Source file {stem!r} matched element {el_name!r} '
                  f'(TV SourceFile={tv_val!r}, similarity={ratio:.0%}) in Project layer')
            return pkg, path, class_el

    pkg, path, tv_val, el_name, ratio, class_el = results[0]
    print(f'  Source file {stem!r} matched element {el_name!r} '
          f'(TV SourceFile={tv_val!r}, similarity={ratio:.0%})')
    return pkg, path, class_el


def find_or_create_package(parent_pkg, name: str):
    """Return the child package named *name*, creating it if absent."""
    for sp in parent_pkg.Packages:
        if sp.Name == name:
            return sp
    new_pkg = parent_pkg.Packages.AddNew(name, '')
    new_pkg.Update()
    parent_pkg.Packages.Refresh()
    return new_pkg


def get_activity_elements(behavior_pkg) -> Dict[str, object]:
    """Return mapping func_name → EA Activity element from a Behavior package."""
    result: Dict[str, object] = {}
    for el in behavior_pkg.Elements:
        if _safe(el, 'Type') == 'Activity' and el.Name:
            result[el.Name] = el
    return result


def get_sub_elements(activity_el) -> Dict[str, object]:
    """Return mapping element_name_or_guid → EA sub-element."""
    result: Dict[str, object] = {}
    for sub in activity_el.Elements:
        result[sub.Name] = sub
    return result


def get_activity_diagram(activity_el) -> Optional[object]:
    """Return the first Activity-type diagram of an element, or None."""
    for diag in activity_el.Diagrams:
        if _safe(diag, 'Type') == 'Activity':
            return diag
    return None


# ===========================================================================
# EA element type mapping
# ===========================================================================

_XML_TYPE_TO_EA: Dict[str, str] = {
    'Action':    'Action',
    'Decision':  'Decision',
    'StateNode': 'StateNode',   # EA uses 'StateNode' for Initial/Final nodes
}

_EA_TYPE_FROM_XML = {
    'Action':    'Action',
    'Decision':  'Decision',
    'StateNode': 'StateNode',
}


# ===========================================================================
# Change report structures
# ===========================================================================

@dataclass
class EaChange:
    kind:    str    # created | updated | deleted | unchanged
    object:  str    # what was changed (element/connector name)
    detail:  str = ''


@dataclass
class FuncReport:
    func_name: str
    status:    str   # created | updated | unchanged | skipped
    changes:   List[EaChange] = field(default_factory=list)

    def has_changes(self) -> bool:
        return bool(self.changes) or self.status in ('created',)


# ===========================================================================
# Version-control helpers
# ===========================================================================

def _vc_checkout(pkg, repo) -> Tuple[bool, str]:
    """
    Try to check out *pkg* from version control, or unlock its underlying
    element if it is locked.  Returns (success, message).
    """
    # Always try SCC checkout first — IsVersionControlled is not reliable in
    # EA 13 (may return False even for SCC-controlled packages).
    try:
        pkg.VersionControlCheckOut()
        return True, 'SCC checked out'
    except AttributeError:
        pass  # method absent in this EA version
    except Exception as exc:
        err = str(exc).lower()
        if 'checked out' in err or 'exclusive' in err or 'already' in err:
            return True, 'SCC already checked out'
        # Not an SCC package or checkout not applicable — fall through.

    # Fallback: repo-level checkout (EA 13 COM: Repository.VersionControlCheckOut)
    try:
        ok = repo.VersionControlCheckOut(pkg.PackageID)
        if ok:
            return True, 'repo-level SCC checked out'
    except AttributeError:
        pass
    except Exception as exc:
        err = str(exc).lower()
        if 'checked out' in err or 'exclusive' in err or 'already' in err:
            return True, 'repo-level SCC already checked out'

    # EA Element lock  (Package.Element.Locked)
    # This is the most common cause of "locked by Version Control" errors
    # when the package is not SCC-controlled but has been manually locked.
    try:
        el = pkg.Element
        if getattr(el, 'Locked', False):
            el.Locked = False
            el.Update()
            return True, f'unlocked Element (was Locked=True, Status={el.Status!r})'
    except Exception as exc:
        return False, f'unlock failed: {exc}'

    return True, 'not locked'


# ===========================================================================
# Layout helper
# ===========================================================================

def _layout_positions(steps: List[XmlStep]) -> Dict[str, Tuple[int, int, int, int]]:
    """
    Compute DiagramObject coordinates for every step in *steps*.

    Layout rules
    ============
    * Sequential nodes are stacked vertically in a single column.
    * At each Decision with two outgoing branches the arms are placed
      side-by-side horizontally:
        - left  branch (TRUE): same column as the decision
        - right branch (FALSE): shifted right by (_STEP_W + _BRANCH_GAP)
      Both arms are drawn downward until they reach the same merge node
      (the first node reachable from both branch tails).  After the merge
      node the single-column layout resumes.
    * Branches may themselves contain nested decisions (recursive).

    Coordinate convention (EA DiagramObject):
      top    = upper edge  (less negative = higher on screen)
      bottom = lower edge  (more negative = lower  on screen)
      top - bottom = element height  (always positive)
    """
    if not steps:
        return {}

    guid_to_step: Dict[str, XmlStep] = {s.guid: s for s in steps}

    def _elem_h(step: XmlStep) -> int:
        return _NODE_H if step.type == 'StateNode' else _STEP_H

    def _reachable(start: str) -> List[str]:
        seen, order, q = set(), [], [start]
        while q:
            g = q.pop(0)
            if g in seen or g not in guid_to_step:
                continue
            seen.add(g)
            order.append(g)
            for _, tg, _ in guid_to_step[g].flows:
                if tg not in seen:
                    q.append(tg)
        return order

    def _find_merge(a: str, b: str) -> Optional[str]:
        ra = _reachable(a)
        rb_set = set(_reachable(b))
        for g in ra:
            if g in rb_set:
                return g
        return None

    def _next(guid: Optional[str]) -> Optional[str]:
        if not guid or guid not in guid_to_step:
            return None
        flows = guid_to_step[guid].flows
        return flows[0][1] if flows else None

    pos: Dict[str, Tuple[int, int, int, int]] = {}

    def _place_node(guid: str, col_left: int, y: int) -> int:
        """Place one node at (col_left, y) and return the y below it."""
        if guid not in guid_to_step or guid in pos:
            return y
        step = guid_to_step[guid]
        h = _elem_h(step)
        cx = col_left + _STEP_W // 2
        if step.type == 'StateNode':
            pos[guid] = (cx - _NODE_W // 2, y, cx + _NODE_W // 2, y - h)
        else:
            pos[guid] = (col_left, y, col_left + _STEP_W, y - h)
        return y - h - _GAP

    def _place_chain(guid: str, col_left: int, y: int,
                     stop_guid: Optional[str] = None) -> int:
        """
        Place guid and its successors in column col_left starting at y.
        Stops when stop_guid is reached (without placing it) or the chain ends.
        Returns the y cursor after the last placed node.
        """
        visited: set = set()
        while guid and guid != stop_guid and guid in guid_to_step and guid not in pos:
            if guid in visited:
                break
            visited.add(guid)
            step = guid_to_step[guid]

            # --- branching Decision (2 branches: if/else) ---
            if step.type == 'Decision' and len(step.flows) == 2:
                y_decision_top = y              # top edge of diamond before placement
                y = _place_node(guid, col_left, y)
                flows = step.flows
                true_tgt  = next((f[1] for f in flows if f[2].upper() == 'TRUE'),  flows[0][1])
                false_tgt = next((f[1] for f in flows if f[2].upper() == 'FALSE'), flows[1][1])

                merge = _find_merge(true_tgt, false_tgt)
                # don't let inner merge go past outer stop
                inner_stop = merge if merge != stop_guid else None

                # Determine FALSE branch column and start-Y.
                # If FALSE branch has multiple steps, place it to the RIGHT
                # below the decision (same y as TRUE) so it doesn't overlap.
                # If FALSE branch is empty (direct to merge), keep left-exit.
                false_branch_len = len(_reachable(false_tgt)) if false_tgt != inner_stop else 0
                if false_branch_len > 1:
                    # Multi-step FALSE branch: place right of TRUE, starting below decision
                    false_col = col_left + (_STEP_W + _BRANCH_GAP)
                    false_start_y = y
                else:
                    # Empty/single-step FALSE branch: exit left at diamond level
                    false_col = col_left - (_STEP_W + _BRANCH_GAP)
                    false_start_y = y_decision_top

                y_t = _place_chain(true_tgt,  col_left,  y,             inner_stop or stop_guid)
                y_f = _place_chain(false_tgt, false_col, false_start_y, inner_stop or stop_guid)
                y = min(y_t, y_f)

                if inner_stop and inner_stop in guid_to_step and inner_stop not in pos:
                    merge_col = false_col if false_tgt == inner_stop else col_left
                    y = _place_node(inner_stop, merge_col, y)
                    guid = _next(inner_stop)
                else:
                    guid = _next(merge) if merge else None
                continue

            # --- branching Decision (N branches: switch/case) ---
            if step.type == 'Decision' and len(step.flows) > 2:
                y_decision_top = y
                y = _place_node(guid, col_left, y)
                flows = step.flows

                # Find the merge node reachable from ALL branch tails
                branch_tgts = [f[1] for f in flows]
                merge: Optional[str] = None
                for candidate in _reachable(branch_tgts[0]):
                    if all(candidate in set(_reachable(tgt)) for tgt in branch_tgts[1:]):
                        merge = candidate
                        break
                inner_stop = merge if merge != stop_guid else None

                # Place each branch in its own column, all starting at y
                # (below the decision diamond).
                # Branch 0 stays in col_left; branches 1..N go rightward.
                y_branches: List[int] = []
                for idx, (_, tgt, _) in enumerate(flows):
                    branch_col = col_left + idx * (_STEP_W + _BRANCH_GAP)
                    y_br = _place_chain(tgt, branch_col, y,
                                        inner_stop or stop_guid)
                    y_branches.append(y_br)
                y = min(y_branches)

                if inner_stop and inner_stop in guid_to_step and inner_stop not in pos:
                    y = _place_node(inner_stop, col_left, y)
                    guid = _next(inner_stop)
                else:
                    guid = _next(merge) if merge else None
                continue

            # --- sequential node ---
            y = _place_node(guid, col_left, y)
            guid = _next(guid)

        return y

    # Find entry StateNode (no incoming edges)
    incoming: Dict[str, int] = {s.guid: 0 for s in steps}
    for s in steps:
        for _, tg, _ in s.flows:
            if tg in incoming:
                incoming[tg] += 1
    entry = next((g for g, cnt in incoming.items()
                  if cnt == 0 and guid_to_step[g].type == 'StateNode'), None)
    if entry is None:
        entry = next((g for g, cnt in incoming.items() if cnt == 0), None)
    if entry is None:
        entry = steps[0].guid

    _place_chain(entry, _COL_X, _ORIGIN_Y)

    # Append any unreachable nodes below
    y_extra = min((c[3] for c in pos.values()), default=_ORIGIN_Y) - _GAP
    for step in steps:
        if step.guid not in pos:
            y_extra = _place_node(step.guid, _COL_X, y_extra)

    return pos


def _calc_container_bounds(
    layout: Dict[str, Tuple[int, int, int, int]]
) -> Tuple[int, int, int, int]:
    """
    Calculate the Activity container bounds from the element layout.
    Returns (left, top, right, bottom) with padding applied.
    The container is guaranteed to enclose every element in *layout*.
    """
    coords = list(layout.values())
    return (
        min(c[0] for c in coords) - _PAD_LEFT,    # left
        max(c[1] for c in coords) + _PAD_TOP,      # top  (less-negative = higher)
        max(c[2] for c in coords) + _PAD_RIGHT,    # right
        min(c[3] for c in coords) - _PAD_BOTTOM,   # bottom (more-negative = lower)
    )


# ===========================================================================
# Core EA write operations
# ===========================================================================

def _create_sub_element(activity_el, name: str, ea_type: str, repo) -> object:
    """Create a sub-element (Action/Decision/StateNode) inside an Activity."""
    sub = activity_el.Elements.AddNew(name, ea_type)
    sub.Update()
    activity_el.Elements.Refresh()
    return sub


def _find_or_create_connector(src_el, tgt_el, guard: str,
                               existing_conns: Dict[Tuple[int, int], object],
                               repo) -> Tuple[object, bool]:
    """
    Return (connector, was_created).  Reuses existing ControlFlow if found.
    """
    key = (src_el.ElementID, tgt_el.ElementID)
    if key in existing_conns:
        conn = existing_conns[key]
        changed = False
        if _safe(conn, 'TransitionGuard') != guard:
            conn.TransitionGuard = guard
            conn.Update()
            changed = True
        return conn, changed

    conn = src_el.Connectors.AddNew('', 'ControlFlow')
    conn.SupplierID = tgt_el.ElementID
    conn.TransitionGuard = guard
    conn.Update()
    src_el.Connectors.Refresh()
    return conn, True


def _add_to_diagram(diag, element_id: int,
                    left: int, top: int, right: int, bottom: int,
                    style: str = '') -> object:
    """Place an element on the diagram at the given coordinates.

    Returns the created DiagramObject.
    """
    dobj = diag.DiagramObjects.AddNew('', '')
    dobj.ElementID = element_id
    dobj.left   = left
    dobj.top    = top
    dobj.right  = right
    dobj.bottom = bottom
    if style:
        dobj.Style = style
    dobj.Update()
    return dobj


def _add_activity_container(diag, activity_id: int,
                             layout: Dict[str, Tuple[int, int, int, int]]) -> None:
    """
    Add the Activity element itself as a container DiagramObject that
    visually wraps all sub-elements.  Uses _calc_container_bounds so the
    container always fits the current layout with padding.
    """
    if not layout:
        return
    cl, ct, cr, cb = _calc_container_bounds(layout)
    _add_to_diagram(diag, activity_id, cl, ct, cr, cb,
                    style=_ACTIVITY_CONTAINER_STYLE)


def _delete_all_controlflows(activity_el) -> int:
    """
    Delete every ControlFlow connector owned by any sub-element of activity_el.
    Returns the count of deleted connectors.
    """
    deleted = 0
    for sub in activity_el.Elements:
        to_delete = []
        for i in range(sub.Connectors.Count):
            conn = sub.Connectors.GetAt(i)
            if conn.ClientID == sub.ElementID and _safe(conn, 'Type') == 'ControlFlow':
                to_delete.append(i)
        # Delete in reverse order so indices stay valid
        for i in reversed(to_delete):
            try:
                sub.Connectors.DeleteAt(i, False)
                deleted += 1
            except Exception:
                pass
        if to_delete:
            sub.Connectors.Refresh()
    return deleted


def _set_decision_exit_geometry(
    diag, layout: Dict[str, Tuple[int, int, int, int]],
    step_list: List['XmlStep'], guid_to_ea: Dict[str, object],
    repo=None,
) -> None:
    """
    Set connector waypoints via COM DiagramLink objects so that
    Decision diamond arrows exit from the correct side:

      TRUE  guard → exits BOTTOM of the diamond (straight down)
      FALSE guard → exits LEFT  of the diamond (horizontal left)

    Must be called AFTER repo.ReloadDiagram() so that diag.DiagramLinks
    is fully populated.  t_diagramlinks rows are empty for newly-created
    diagrams, so SQL UPDATE cannot be used here.
    """
    # Build connector_id → DiagramLink map (requires prior ReloadDiagram call)
    try:
        diag.DiagramLinks.Refresh()
        link_map: Dict[int, object] = {}
        for i in range(diag.DiagramLinks.Count):
            lnk = diag.DiagramLinks.GetAt(i)
            link_map[lnk.ConnectorID] = lnk
    except Exception:
        return

    if not link_map:
        return

    # Build reverse map: EA ElementID → guid, so we can look up target coords.
    eid_to_guid: Dict[int, str] = {
        ea_el.ElementID: g for g, ea_el in guid_to_ea.items()
    }

    for step in step_list:
        if step.type != 'Decision':
            continue
        src_el = guid_to_ea.get(step.guid)
        if src_el is None:
            continue
        src_coords = layout.get(step.guid)
        if not src_coords:
            continue
        s_left, s_top, s_right, s_bottom = src_coords
        s_center_x = (s_left + s_right) // 2
        s_center_y = (s_top + s_bottom) // 2

        try:
            for i in range(src_el.Connectors.Count):
                conn = src_el.Connectors.GetAt(i)
                if (conn.ClientID == src_el.ElementID
                        and _safe(conn, 'Type') == 'ControlFlow'):
                    guard = (conn.TransitionGuard or '').upper().strip()
                    lnk = link_map.get(conn.ConnectorID)
                    if lnk is None:
                        continue
                    if guard == 'TRUE':
                        # Exit bottom: waypoint just below bottom tip.
                        # EDGE=3 forces EA to use the bottom connection point.
                        wx, wy = s_center_x, s_bottom - 5
                        lnk.Geometry = f'N=1;WX={wx};WY={wy};EDGE=3;'
                    elif guard == 'FALSE':
                        # Exit LEFT side and route to target with an L-shape.
                        # Waypoint at (target_center_x, diamond_center_y) is
                        # the *bend corner* of the L: horizontal first, then
                        # vertical.  Without this the waypoint is at s_left-5
                        # which is only 5px from the source and EA draws a
                        # diagonal instead of two orthogonal segments.
                        # EDGE=4 forces the LEFT connection point on the source.
                        tgt_center_x = s_left - 30  # safe fallback
                        try:
                            tgt_guid = eid_to_guid.get(conn.SupplierID)
                            if tgt_guid:
                                tgt_coords = layout.get(tgt_guid)
                                if tgt_coords:
                                    tgt_center_x = (tgt_coords[0] + tgt_coords[2]) // 2
                        except Exception:
                            pass
                        wx, wy = tgt_center_x, s_center_y
                        lnk.Geometry = f'N=1;WX={wx};WY={wy};EDGE=4;'
                    else:
                        continue
                    lnk.Update()
        except Exception:
            pass


# ===========================================================================
# Function-level import
# ===========================================================================

def _import_function(
    xml_func: XmlFunction,
    write_pkg,
    existing_activities: Dict[str, object],
    repo,
    dry_run: bool,
) -> FuncReport:
    """
    Create or update the EA Activity element for one function.
    New elements are added to *write_pkg* (Behavior or module package).
    Returns a FuncReport.
    """
    report = FuncReport(func_name=xml_func.name, status='unchanged')

    # Only import functions that have meaningful steps (skip pure-TODO stubs)
    code_steps = [s for s in xml_func.steps.values()
                  if s.type in ('Action', 'Decision', 'StateNode')]
    non_todo_steps = [s for s in code_steps
                      if s.name not in ('', '/* TODO: implement */')]
    if not non_todo_steps:
        report.status = 'skipped'
        report.changes.append(EaChange('unchanged', xml_func.name,
                                        'only TODO stubs â€“ skipped'))
        return report

    # â”€â”€ Ordered list of XML steps (preserving BFS order) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Build ordered step list: entry StateNode first, then reachable steps
    guid_to_step = xml_func.steps
    step_list: List[XmlStep] = []
    visited: set = set()

    def _bfs(start_guid: str) -> None:
        queue = [start_guid]
        while queue:
            g = queue.pop(0)
            if g in visited or g not in guid_to_step:
                continue
            visited.add(g)
            step_list.append(guid_to_step[g])
            for _, to_g, _ in guid_to_step[g].flows:
                if to_g not in visited and to_g in guid_to_step:
                    queue.append(to_g)

    # Find entry StateNode (one with no incoming flows)
    incoming: Dict[str, int] = {g: 0 for g in guid_to_step}
    for s in guid_to_step.values():
        for _, to_g, _ in s.flows:
            if to_g in incoming:
                incoming[to_g] += 1
    entry_candidates = [g for g, cnt in incoming.items()
                        if cnt == 0 and guid_to_step[g].type == 'StateNode']
    entry_guid = entry_candidates[0] if entry_candidates else (
        next((g for g, s in guid_to_step.items() if s.type == 'StateNode'), None)
        or next(iter(guid_to_step), None)
    )
    if entry_guid:
        _bfs(entry_guid)
    for g in guid_to_step:
        if g not in visited:
            step_list.append(guid_to_step[g])

    # Exit StateNode: has no outgoing flows (used to set Subtype=101)
    exit_state_guid = next(
        (s.guid for s in step_list
         if s.type == 'StateNode' and not s.flows and s.guid != entry_guid),
        None
    )

    # â”€â”€ Get or create the Activity element â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    activity_el = existing_activities.get(xml_func.name)
    is_new = activity_el is None

    if is_new:
        report.status = 'created'
        report.changes.append(EaChange('created', xml_func.name,
                                        'new Activity element'))
        if dry_run:
            return report
        activity_el = write_pkg.Elements.AddNew(xml_func.name, 'Activity')
        activity_el.Stereotype = xml_func.stereotype or ''
        activity_el.Update()
        write_pkg.Elements.Refresh()
    else:
        report.status = 'updated'

    # â”€â”€ Reconcile sub-elements â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Matching strategy (most reliable to least):
    #   1. Named elements (Action/Decision): matched by name
    #   2. StateNodes: matched by ea_id stored in XML (set at creation time)
    #      Fallback for first import (ea_id=0): Subtype=100→entry, else→exit/merge
    existing_subs: Dict[str, object] = {}       # name → EA element
    existing_by_id: Dict[int, object] = {}      # ElementID → EA element
    if not dry_run:
        for sub in activity_el.Elements:
            existing_by_id[sub.ElementID] = sub
            if sub.Type != 'StateNode':
                existing_subs[sub.Name] = sub

    # Map xml_step_guid → EA sub-element (created or found)
    guid_to_ea: Dict[str, object] = {}

    for step in step_list:
        ea_type = _EA_TYPE_FROM_XML.get(step.type, 'Action')

        # Find existing EA element for this step
        existing_el = None
        if step.type == 'StateNode':
            if step.ea_id and step.ea_id in existing_by_id:
                existing_el = existing_by_id[step.ea_id]
        else:
            existing_el = existing_subs.get(step.name)

        if existing_el is None:
            if step.type in ('Action', 'Decision', 'StateNode'):
                report.changes.append(EaChange('created', step.name or f'({step.type})',
                                                f'new {ea_type}'))
                if not dry_run:
                    new_el = _create_sub_element(activity_el, step.name, ea_type, repo)
                    if step.type == 'StateNode':
                        new_el.Subtype = 100 if step.guid == entry_guid else 101
                        new_el.Update()
                    # Capture ElementID immediately — the next _create_sub_element
                    # call triggers Elements.Refresh() which can invalidate COM object
                    # references stored in guid_to_ea, causing stale objects to return
                    # ElementID=0 later.  Storing the ID now guarantees the persist
                    # loop and the guid_to_ea rebuild both use the correct value.
                    step.ea_id = new_el.ElementID
                    guid_to_ea[step.guid] = new_el
        else:
            guid_to_ea[step.guid] = existing_el
            existing_type = _safe(existing_el, 'Type')
            if existing_type != ea_type:
                report.changes.append(EaChange('updated', step.name,
                                                f'type {existing_type} -> {ea_type}'))

    # Remove sub-elements not in XML (by name for named types only)
    xml_names = {s.name for s in step_list if s.type != 'StateNode'}
    for sub_name, sub_el in list(existing_subs.items()):
        if sub_name not in xml_names and _safe(sub_el, 'Type') in ('Action', 'Decision'):
            report.changes.append(EaChange('deleted', sub_name, 'step removed from XML'))
            if not dry_run:
                try:
                    target_id = sub_el.ElementID
                    for i in range(activity_el.Elements.Count):
                        if activity_el.Elements.GetAt(i).ElementID == target_id:
                            activity_el.Elements.DeleteAt(i, True)
                            break
                except Exception:
                    pass

    if dry_run:
        return report

    # Persist EA ElementIDs back to the XML step objects so they are saved
    # to the XML file after this import — enables reliable re-matching on
    # subsequent imports without depending on name or Subtype.
    # Use `not step.ea_id` to cover both None (brand-new step) and 0.
    for step in step_list:
        sub = guid_to_ea.get(step.guid)
        if sub and not step.ea_id:
            step.ea_id = sub.ElementID

    activity_el.Elements.Refresh()
    # Rebuild guid_to_ea and fresh_by_name after refresh
    fresh_by_name: Dict[str, object] = {}
    fresh_by_id:   Dict[int,  object] = {}
    for sub in activity_el.Elements:
        fresh_by_id[sub.ElementID] = sub
        if sub.Name:
            fresh_by_name[sub.Name] = sub

    guid_to_ea = {}
    for step in step_list:
        if step.ea_id and step.ea_id in fresh_by_id:
            guid_to_ea[step.guid] = fresh_by_id[step.ea_id]
        elif step.type != 'StateNode':
            sub = fresh_by_name.get(step.name)
            if sub:
                guid_to_ea[step.guid] = sub
                step.ea_id = sub.ElementID

    # Fix StateNode Subtypes
    for step in step_list:
        if step.type != 'StateNode':
            continue
        sub = guid_to_ea.get(step.guid)
        if sub is None:
            continue
        expected = 100 if step.guid == entry_guid else 101
        try:
            if int(getattr(sub, 'Subtype', -1)) != expected:
                sub.Subtype = expected
                sub.Update()
        except Exception:
            pass

    # â”€â”€ Recreate all ControlFlow connectors â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Delete all existing connectors first — this is the only reliable way
    # to avoid duplicates (same src→tgt pair can exist multiple times when
    # guards differ) and stale routing after layout changes.
    _delete_all_controlflows(activity_el)
    activity_el.Elements.Refresh()

    seen_flows: set = set()   # (src_eid, tgt_eid, guard) — deduplicate
    for step in step_list:
        src_el = guid_to_ea.get(step.guid)
        if not src_el:
            continue
        for to_name, to_guid, guard in step.flows:
            tgt_el = guid_to_ea.get(to_guid)
            if tgt_el is None:
                tgt_el = fresh_by_name.get(to_name)
            if tgt_el is None:
                continue
            key = (src_el.ElementID, tgt_el.ElementID, guard)
            if key in seen_flows:
                continue
            seen_flows.add(key)
            conn = src_el.Connectors.AddNew('', 'ControlFlow')
            conn.SupplierID = tgt_el.ElementID
            conn.TransitionGuard = guard
            # RouteStyle=0 → use diagram default (orthogonal for Activity).
            # RouteStyle=3 = Direct/Straight which ignores custom waypoints.
            try:
                conn.RouteStyle = 0
            except Exception:
                pass
            conn.Update()
            src_el.Connectors.Refresh()
            report.changes.append(EaChange('created',
                                            f'{step.name or step.type} -> {to_name or to_guid[:8]}',
                                            f'ControlFlow guard={guard!r}'))

    # â”€â”€ Create/refresh the Activity diagram â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    diag = get_activity_diagram(activity_el)
    if diag is None:
        diag = activity_el.Diagrams.AddNew(xml_func.name, 'Activity')
        diag.StyleEx = _DIAG_STYLE_EX   # swimlanes, UML 2.1 connectors, theme
        diag.Update()
        activity_el.Diagrams.Refresh()
        report.changes.append(EaChange('created', f'Diagram:{xml_func.name}',
                                        'new Activity diagram'))
    else:
        # Update StyleEx on existing diagram if it doesn't match template
        current_sx = _safe(diag, 'StyleEx')
        if 'SwimlanesActive=1' not in current_sx:
            diag.StyleEx = _DIAG_STYLE_EX
            diag.Update()

    # â”€â”€ Place / reposition all elements on the diagram â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Every import recalculates the full layout and updates DiagramObject
    # positions, ensuring the diagram is always self-consistent regardless
    # of what previous imports may have placed.
    layout = _layout_positions(step_list)
    cl, ct, cr, cb = _calc_container_bounds(layout)

    # Build elementID → existing DiagramObject map for fast look-up
    existing_dobjs: Dict[int, object] = {
        dobj.ElementID: dobj for dobj in diag.DiagramObjects
    }

    # â”€â”€ Sub-elements FIRST so they get lower Sequence numbers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # In EA, DiagramObjects with LOWER Sequence are drawn ON TOP.
    # The Activity container must have the HIGHEST Sequence so it renders
    # behind all sub-elements.
    for step in step_list:
        sub_el = guid_to_ea.get(step.guid)
        if sub_el is None:
            continue
        coords = layout.get(step.guid)
        if not coords:
            continue
        left, top, right, bottom = coords
        dobj = existing_dobjs.get(sub_el.ElementID)
        if dobj is None:
            # New element — add to diagram
            _add_to_diagram(diag, sub_el.ElementID, left, top, right, bottom)
            report.changes.append(EaChange(
                'created',
                f'DiagramObject:{step.name or step.type}',
                f'placed at ({left},{top})'))
        elif (dobj.left != left or dobj.top != top
              or dobj.right != right or dobj.bottom != bottom):
            dobj.left   = left
            dobj.top    = top
            dobj.right  = right
            dobj.bottom = bottom
            dobj.Update()
            report.changes.append(EaChange(
                'updated',
                f'DiagramObject:{step.name or step.type}',
                f'repositioned to ({left},{top})'))

    diag.DiagramObjects.Refresh()

    # â”€â”€ Activity container: placed after sub-elements, then Sequence forced to 1 â”€
    # EA assigns Sequence=999999 to ALL newly-created DiagramObjects.
    # When elements share the same Sequence EA renders them in CREATION order
    # (last-added = on top / foreground).  The container must render BEHIND all
    # sub-elements (background), so we:
    #   1. Add/update the container DiagramObject (gets Seq=999999 like others)
    #   2. Commit via diag.Update() so the row exists in t_diagramobjects
    #   3. Use SQL to set its Sequence=1 — lower than 999999 means it renders first = background
    container_dobj = existing_dobjs.get(activity_el.ElementID)
    if container_dobj is None:
        container_dobj = _add_to_diagram(diag, activity_el.ElementID, cl, ct, cr, cb,
                                         style=_ACTIVITY_CONTAINER_STYLE)
        report.changes.append(EaChange(
            'created',
            f'DiagramObject:{xml_func.name}',
            f'container created  l={cl} t={ct} r={cr} b={cb}  '
            f'({cr - cl}w x {ct - cb}h)'))
    else:
        container_dobj.left   = cl
        container_dobj.top    = ct
        container_dobj.right  = cr
        container_dobj.bottom = cb
        container_dobj.Style  = _ACTIVITY_CONTAINER_STYLE
        container_dobj.Update()
        report.changes.append(EaChange(
            'updated',
            f'DiagramObject:{xml_func.name}',
            f'container resized  l={cl} t={ct} r={cr} b={cb}  '
            f'({cr - cl}w x {ct - cb}h) padding={_PAD_LEFT}/{_PAD_TOP}px'))

    # Commit positions to the .eap file BEFORE the SQL UPDATE so the row exists.
    diag.DiagramObjects.Refresh()
    diag.Update()

    # Force container Sequence higher than all sub-elements so it renders behind them.
    # In EA: higher Sequence = drawn first = background (further back in z-order).
    # Sub-elements have Sequence=999999 (EA default), so container must be > 999999.
    try:
        repo.Execute(
            f"UPDATE t_diagramobjects SET Sequence=9999999 "
            f"WHERE Object_ID={activity_el.ElementID} "
            f"AND Diagram_ID={diag.DiagramID}"
        )
    except Exception:
        pass

    repo.ReloadDiagram(diag.DiagramID)   # tell EA to redraw the diagram

    # Set exit-side geometry for Decision connectors (TRUE→bottom, FALSE→left).
    # DiagramLinks are only accessible AFTER ReloadDiagram, so this call must
    # come here rather than before the layout is committed.
    _set_decision_exit_geometry(diag, layout, step_list, guid_to_ea)
    diag.Update()
    repo.ReloadDiagram(diag.DiagramID)   # redraw with updated connector geometry

    if not report.changes:
        report.status = 'unchanged'

    return report


# ===========================================================================
# Class operation sync helpers
# ===========================================================================

def _parse_params(raw_params: str) -> List[Tuple[str, str]]:
    """Parse a raw C param string into [(type, name), ...] pairs."""
    params: List[Tuple[str, str]] = []
    if not raw_params or raw_params.strip() in ('void', ''):
        return params
    for part in raw_params.split(','):
        part = part.strip()
        if not part:
            continue
        # Remove 'const', normalise spaces
        clean = re.sub(r'\bconst\b', '', part).strip()
        # Last word is the variable name; everything before is the type
        m = re.match(r'^(.+?)\s+(\w+)\s*$', clean)
        if m:
            params.append((m.group(1).strip(), m.group(2).strip()))
    return params


def _sync_class_operation(
    class_el,
    xml_func: 'XmlFunction',
    dry_run: bool,
) -> List['EaChange']:
    """Add or update the Operation on an EA Class element to match a C function."""
    changes: List[EaChange] = []
    func_name = xml_func.name
    return_type = xml_func.return_type or 'void'
    params = _parse_params(xml_func.raw_params)

    # --- find existing operation by name ---
    existing_op = None
    try:
        for i in range(class_el.Methods.Count):
            op = class_el.Methods.GetAt(i)
            if op.Name == func_name:
                existing_op = op
                break
    except Exception as exc:
        changes.append(EaChange('error', f'Operation:{func_name}',
                                f'cannot read Methods: {exc}'))
        return changes

    if existing_op is None:
        # --- create new operation ---
        if not dry_run:
            try:
                new_op = class_el.Methods.AddNew(func_name, 'Method')
                new_op.ReturnType = return_type
                new_op.Update()
                for ptype, pname in params:
                    p = new_op.Parameters.AddNew(pname, 'Parameter')
                    p.Type = ptype
                    p.Kind = 'in'
                    p.Update()
                new_op.Parameters.Refresh()
                class_el.Methods.Refresh()
                class_el.Update()
            except Exception as exc:
                changes.append(EaChange('error', f'Operation:{func_name}',
                                        f'cannot add: {exc}'))
                return changes
        param_str = ', '.join(f'{t} {n}' for t, n in params)
        changes.append(EaChange('created', f'Operation:{func_name}',
                                f'{return_type} {func_name}({param_str})'))
    else:
        # --- check for differences ---
        diffs = []
        if (existing_op.ReturnType or '').strip() != return_type:
            diffs.append(f'return_type {existing_op.ReturnType!r} -> {return_type!r}')
        try:
            n_existing = existing_op.Parameters.Count
        except Exception:
            n_existing = -1
        if n_existing != len(params):
            diffs.append(f'param count {n_existing} -> {len(params)}')
        if diffs:
            if not dry_run:
                try:
                    existing_op.ReturnType = return_type
                    existing_op.Update()
                except Exception as exc:
                    changes.append(EaChange('error', f'Operation:{func_name}',
                                            f'cannot update: {exc}'))
                    return changes
            changes.append(EaChange('updated', f'Operation:{func_name}',
                                    '; '.join(diffs)))
        else:
            changes.append(EaChange('unchanged', f'Operation:{func_name}',
                                    'already up-to-date'))
    return changes


# ===========================================================================
# Module-level import
# ===========================================================================

def import_module(
    module_name: str,
    repo,
    diagrams_dir: str = _DEFAULT_DIAGRAMS_DIR,
    dry_run: bool = False,
    function_filter: Optional[List[str]] = None,
    source_file: Optional[str] = None,
) -> List[FuncReport]:
    """
    Import all functions for *module_name* from diagram XMLs into EA.

    Parameters
    ----------
    module_name     : e.g. 'SwMod_TouchSM'
    repo            : connected EA.Repository COM object
    diagrams_dir    : directory with SwDetailedDesignDiagram XML files
    dry_run         : if True, parse and diff but do not write to EA
    function_filter : if given, only import these function names
    source_file     : path to the C source file (e.g. 'touchsm1c1.c').
                      When provided, the exact EA package is located via the
                      'SourceFile' tagged value on its elements, avoiding
                      ambiguity when the same module name exists in both the
                      Project and Platform layers.

    Returns a list of FuncReport.
    """
    print(f'\nLoading diagram XMLs for {module_name} ...')
    xml_funcs = load_xml_functions(diagrams_dir, module_name)
    if not xml_funcs:
        print(f'  ERROR: No diagram XMLs found for {module_name} in {diagrams_dir}',
              file=sys.stderr)
        return []
    print(f'  {len(xml_funcs)} functions loaded from XML.')

    if function_filter:
        xml_funcs = {k: v for k, v in xml_funcs.items() if k in function_filter}
        print(f'  Filter applied: {len(xml_funcs)} functions to process.')

    # Locate the exact module package in EA
    module_pkg = None
    class_el = None  # EA Class element with SourceFile TV (e.g. TouchSM_API)

    if source_file and not dry_run:
        # Use the SourceFile tagged value to find the right package unambiguously
        result = find_module_by_source_file(repo, source_file)
        if result:
            module_pkg, ea_path, class_el = result
            print(f'  Located via SourceFile tag: {ea_path} (ID={module_pkg.PackageID})')
        else:
            print(f'  WARNING: No SourceFile TV match for {source_file!r}; '
                  f'falling back to name search.', file=sys.stderr)

    if module_pkg is None:
        for model in repo.Models:
            module_pkg = find_package(model, module_name)
            if module_pkg:
                break

    if module_pkg is None:
        print(f'  ERROR: Package "{module_name}" not found in EA model.', file=sys.stderr)
        return []
    print(f'  Using EA package: {module_pkg.Name} (ID={module_pkg.PackageID})')

    # Get or create Behavior sub-package
    behavior_pkg = find_or_create_package(module_pkg, 'Behavior')
    if behavior_pkg is None:
        print(f'  ERROR: Could not get/create Behavior package.', file=sys.stderr)
        return []
    print(f'  Behavior package ID={behavior_pkg.PackageID}')

    existing_activities = get_activity_elements(behavior_pkg)
    print(f'  Existing Activity elements in Behavior: {len(existing_activities)}')

    # Check out / unlock the Behavior package if needed
    vc_ok, vc_msg = _vc_checkout(behavior_pkg, repo)

    if not vc_ok:
        # Fall back: add new elements directly to the module package itself.
        # Also try to unlock the module package element before proceeding.
        mod_vc_ok, mod_vc_msg = _vc_checkout(module_pkg, repo)
        if not mod_vc_ok:
            # Proceed anyway — some EA VC setups report locked but still allow writes.
            print(f'  WARNING: Behavior locked ({vc_msg}); '
                  f'{module_name} also locked ({mod_vc_msg}). '
                  f'Attempting writes anyway.', file=sys.stderr)
            print()
            print('  ACTION REQUIRED: Package is locked. Unlock it in EA first:')
            print(f'    1. In EA, open the diagram for the \"{module_name}\" package')
            print( '    2. Select the locked element (or the diagram background)')
            print( '    3. Press Ctrl + L to unlock')
            print( '    4. Re-run this script')
            print()
        else:
            print(f'  Behavior locked ({vc_msg}); new elements will be added '
                  f'directly to {module_name} package ({mod_vc_msg}).')
        write_pkg = module_pkg
        # Also include Activity elements directly on the module package
        existing_activities.update(get_activity_elements(module_pkg))
    else:
        print(f'  Version control: {vc_msg}')
        write_pkg = behavior_pkg

    reports: List[FuncReport] = []
    for func_name, xml_func in sorted(xml_funcs.items()):
        print(f'  Processing: {func_name} ...', end=' ')
        try:
            rpt = _import_function(
                xml_func, write_pkg, existing_activities, repo, dry_run)
            reports.append(rpt)
            print(rpt.status)
        except Exception as exc:
            import traceback
            print(f'ERROR: {exc}')
            traceback.print_exc()
            reports.append(FuncReport(func_name=func_name, status='error',
                                       changes=[EaChange('error', func_name, str(exc))]))

    # --- Sync class operations (e.g. TouchSM_API class under module package) ---
    if class_el is not None:
        print(f'  Syncing operations on class \"{class_el.Name}\" ...')
        for func_name, xml_func in sorted(xml_funcs.items()):
            op_changes = _sync_class_operation(class_el, xml_func, dry_run)
            # Attach operation changes to the matching FuncReport (or log directly)
            rpt = next((r for r in reports if r.func_name == func_name), None)
            for ch in op_changes:
                print(f'    [{ch.kind}] {ch.object}: {ch.detail}')
                if rpt:
                    rpt.changes.append(ch)
    else:
        print('  NOTE: class element not found via SourceFile TV; '
              'skipping operation sync.')

    # Write ea_id values back into the XML files so subsequent imports can
    # match StateNodes by ElementID instead of guessing by Subtype.
    if not dry_run:
        _write_eaids_to_xml(diagrams_dir, module_name, xml_funcs)

    return reports


def _write_eaids_to_xml(diagrams_dir: str, module_name: str,
                         xml_funcs: Dict[str, XmlFunction]) -> None:
    """Write ea_id attributes back to the SwDetailedDesignDiagram XML files."""
    import xml.etree.ElementTree as _ET
    for fname in sorted(os.listdir(diagrams_dir)):
        if ('SwDetailedDesignDiagram' not in fname
                or module_name not in fname
                or not fname.endswith('.xml')):
            continue
        fpath = os.path.join(diagrams_dir, fname)
        try:
            tree = _ET.parse(fpath)
        except _ET.ParseError:
            continue
        changed = False
        root = tree.getroot()
        for mod_el in root.findall('Module'):
            for func_el in mod_el.findall('Function'):
                fname2 = (func_el.get('name') or '').strip()
                xml_func = xml_funcs.get(fname2)
                if xml_func is None:
                    continue
                for s_el in func_el.findall('Step'):
                    g = (s_el.get('guid') or '').strip()
                    step = xml_func.steps.get(g)
                    if step and step.ea_id:
                        cur = s_el.get('eaId', '0')
                        if str(step.ea_id) != cur:
                            s_el.set('eaId', str(step.ea_id))
                            changed = True
        if changed:
            _ET.indent(tree, space='  ')
            tree.write(fpath, encoding='unicode', xml_declaration=False)


# ===========================================================================
# Report formatting
# ===========================================================================

def format_report(reports: List[FuncReport], module_name: str,
                  dry_run: bool) -> str:
    lines = []
    lines.append('=' * 70)
    lines.append('EA Import Diagrams - Change Report')
    lines.append(f'Module      : {module_name}')
    lines.append(f'Mode        : {"DRY RUN (no EA writes)" if dry_run else "LIVE"}')
    lines.append('=' * 70)
    lines.append('')

    created   = [r for r in reports if r.status == 'created']
    updated   = [r for r in reports if r.status == 'updated' and r.has_changes()]
    unchanged = [r for r in reports if r.status == 'unchanged']
    skipped   = [r for r in reports if r.status == 'skipped']
    errors    = [r for r in reports if r.status == 'error']

    lines.append('Summary:')
    lines.append(f'  Created   : {len(created)}')
    lines.append(f'  Updated   : {len(updated)}')
    lines.append(f'  Unchanged : {len(unchanged)}')
    lines.append(f'  Skipped   : {len(skipped)}')
    lines.append(f'  Errors    : {len(errors)}')
    lines.append('')

    if created:
        lines.append('-- CREATED ' + '-' * 58)
        for r in created:
            lines.append(f'  + {r.func_name}')
            for ch in r.changes:
                lines.append(f'      [{ch.kind}] {ch.object}  {ch.detail}')
        lines.append('')

    if updated:
        lines.append('-- UPDATED ' + '-' * 58)
        for r in updated:
            lines.append(f'  ~ {r.func_name}')
            for ch in r.changes:
                lines.append(f'      [{ch.kind}] {ch.object}  {ch.detail}')
        lines.append('')

    if skipped:
        lines.append('-- SKIPPED (stub-only functions) ' + '-' * 37)
        for r in skipped:
            lines.append(f'  - {r.func_name}')
        lines.append('')

    if errors:
        lines.append('-- ERRORS ' + '-' * 59)
        for r in errors:
            lines.append(f'  ! {r.func_name}')
            for ch in r.changes:
                lines.append(f'      {ch.detail}')
        lines.append('')

    if unchanged:
        lines.append('-- UNCHANGED ' + '-' * 56)
        for r in unchanged:
            lines.append(f'  = {r.func_name}')
        lines.append('')

    lines.append('=' * 70)
    return '\n'.join(lines)


# ===========================================================================
# CLI
# ===========================================================================

def main(argv: List[str]) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog='ea_import_diagrams_from_xml',
        description=(
            'Import C-parsed activity flow graphs into Enterprise Architect\n'
            'via COM automation. EA must be running with the project open.\n'
            'Use .venv32\\Scripts\\python.exe (32-bit) to run this tool.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'module',
        help='Module name to import, e.g. SwMod_TouchSM.',
    )
    parser.add_argument(
        '--diagrams', '-d',
        dest='diagrams_dir',
        metavar='DIR',
        default=None,
        help=(
            f'Directory containing SwDetailedDesignDiagram XML files '
            f'(default: {_DEFAULT_DIAGRAMS_DIR}).'
        ),
    )
    parser.add_argument(
        '--functions', '-f',
        dest='functions',
        metavar='FUNC1,FUNC2',
        default=None,
        help='Comma-separated list of function names to restrict import to.',
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        dest='dry_run',
        help='Parse and diff but do not write anything to EA.',
    )
    parser.add_argument(
        '--source-file', '-s',
        dest='source_file',
        metavar='FILE',
        default=None,
        help=(
            'Path to the C source file (e.g. input/touchsm/core/touchsm1c1.c). '
            'Used to locate the exact EA package via the SourceFile tagged value, '
            'avoiding ambiguity when the same module name exists in both the '
            'Project and Platform layers.'
        ),
    )
    parser.add_argument(
        '--report', '-r',
        dest='report_file',
        metavar='FILE',
        default=None,
        help='Write change report to FILE (also printed to stdout).',
    )

    args = parser.parse_args(argv[1:])
    diagrams_dir   = args.diagrams_dir or _DEFAULT_DIAGRAMS_DIR
    function_filter = (
        [f.strip() for f in args.functions.split(',') if f.strip()]
        if args.functions else None
    )

    # â”€â”€ Dry-run: no EA connection needed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if args.dry_run:
        print('DRY RUN mode: parsing XML and reporting planned changes (no EA writes).')
        xml_funcs = load_xml_functions(diagrams_dir, args.module)
        if not xml_funcs:
            print(f'ERROR: No diagram XMLs found for {args.module} in {diagrams_dir}',
                  file=sys.stderr)
            sys.exit(1)
        if function_filter:
            xml_funcs = {k: v for k, v in xml_funcs.items() if k in function_filter}
        reports = []
        for func_name, xml_func in sorted(xml_funcs.items()):
            code_steps = [s for s in xml_func.steps.values()
                          if s.type in ('Action', 'Decision', 'StateNode')]
            non_todo = [s for s in code_steps
                        if s.name not in ('', '/* TODO: implement */')]
            if not non_todo:
                reports.append(FuncReport(func_name=func_name, status='skipped',
                                           changes=[EaChange('unchanged', func_name,
                                                             'only TODO stubs â€“ skipped')]))
            else:
                n_steps = len(code_steps)
                n_flows = sum(len(s.flows) for s in xml_func.steps.values())
                reports.append(FuncReport(
                    func_name=func_name, status='created',
                    changes=[
                        EaChange('created', func_name,
                                  f'Activity: {n_steps} steps, {n_flows} flows'),
                    ],
                ))
        report_text = format_report(reports, args.module, dry_run=True)
        print('\n' + report_text)
        if args.report_file:
            with open(args.report_file, 'w', encoding='utf-8') as fh:
                fh.write(report_text)
            print(f'\nReport written to: {args.report_file}')
        return

    # â”€â”€ Live mode: connect to EA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print('Connecting to Enterprise Architect ...')
    repo = None

    # EA.App is the COM progid that EA reliably registers in the Running
    # Object Table. EA.Repository usually is not registered there.
    # Always verify the handle is usable (Models.Count) — a crashed/restored
    # EA session can leave a stale COM object that appears connected but fails
    # with internal error 61704 on any real call.
    try:
        ea_app = win32com.client.GetActiveObject('EA.App')
        candidate = ea_app.Repository
        candidate.Models.Count   # smoke-test: raises if session is broken
        repo = candidate
        print('  Attached to running EA instance (via EA.App).')
    except Exception:
        pass

    # Fallback: launch a new EA instance and open the project ourselves
    if repo is None:
        try:
            repo = win32com.client.Dispatch('EA.Repository')
            repo.OpenFile(EA_PROJECT)
            print(f'  Opened project in new EA instance: {EA_PROJECT}')
        except Exception as exc:
            print(f'\nERROR: Cannot connect to EA: {exc}', file=sys.stderr)
            print('', file=sys.stderr)
            print('  Make sure Enterprise Architect is installed and the project', file=sys.stderr)
            print(f'  exists at: {EA_PROJECT}', file=sys.stderr)
            sys.exit(1)

    reports = import_module(
        module_name     = args.module,
        repo            = repo,
        diagrams_dir    = diagrams_dir,
        dry_run         = False,
        function_filter = function_filter,
        source_file     = args.source_file,
    )

    report_text = format_report(reports, args.module, dry_run=False)
    print('\n' + report_text)

    if args.report_file:
        with open(args.report_file, 'w', encoding='utf-8') as fh:
            fh.write(report_text)
        print(f'\nReport written to: {args.report_file}')


if __name__ == '__main__':
    main(sys.argv)

