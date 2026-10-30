"""
Generate C function skeletons from SwDetailedDesignDiagram XML files.

Usage:
    python xml_to_c.py [input] [output_dir]

    input       â€“ path to a single .xml file or a directory of .xml files
                  (defaults to the project ai_output/ folder)
    output_dir  â€“ where to write the generated .c files
                  (defaults to ai_output/generated_c/)

For each XML file the script produces one .c skeleton file containing one
function per <Function> element.  The flow-graph is traversed recursively
and converted to C with:

    StateNode  â†’ function entry / exit
    Action     â†’ C statement (or /* TODO */ comment when not plain C)
    Decision   â†’ if / else  (guards "Yes"/"No") or switch-like comment
    Interface  â†’ traceability comment only  (no executable code)

Back-edges (loops) are detected via DFS colouring and wrapped in
    /* LOOP_BACK â†’ <target name> */
so that a human reviewer can decide on the correct while/do-while construct.
"""

from __future__ import annotations

import os
import re
import sys
import textwrap
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RETURN_TYPE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'_v[A-Z_]|_v$|Void', re.I), 'void'),
    (re.compile(r'_bo[A-Z_]|_bo$|Bool', re.I), 'boolean'),
    (re.compile(r'_u8[A-Z_]|_u8$'), 'uint8'),
    (re.compile(r'_u16[A-Z_]|_u16$'), 'uint16'),
    (re.compile(r'_u32[A-Z_]|_u32$'), 'uint32'),
    (re.compile(r'_s8[A-Z_]|_s8$'), 'sint8'),
    (re.compile(r'_s16[A-Z_]|_s16$'), 'sint16'),
    (re.compile(r'_s32[A-Z_]|_s32$'), 'sint32'),
    (re.compile(r'_en[A-Z_]|_en$'), 'tEnumType /* TODO: refine type */'),
]

# Regex: name starts with identifier chars and is followed by an operator or
# parenthesis â€“ these are very likely C statements already.
# Also matches pointer-dereference targets: *ptr = val, (*ptr).field, etc.
_C_EXPR_RE = re.compile(
    r'^'
    r'(?:\*+)?'                        # optional leading dereference(s): *ptr, **ptr
    r'[A-Za-z_][A-Za-z0-9_]*'        # leading identifier
    r'\s*'
    r'(?:'
    r'[\(\[=!<>+\-\*/&|^~]'           # operator or call
    r'|->|\.'                          # member access
    r')'
)

# Words that mark a statement as pure descriptive (not C code)
_DESCRIPTION_WORDS = re.compile(
    r'\b(check|trigger|transit|continue|increment|update|process|'
    r'calculate|determine|handle|initialize|configure|'
    r'wait|receive|request|verify|validate)\b',
    re.I,
)

# EA action names often carry a leading English verb before a C expression:
#   "Set X = Y"  â†’  "X = Y"
#   "Read X from Y" â†’  not C, keep as comment
#   "Reset X to 0"  â†’  not unambiguously C, keep as comment
# Note: "Return" is intentionally excluded â€“ "return X" is already
# recognised as C by looks_like_c() via the 'return ' prefix check.
_EA_VERB_PREFIX_RE = re.compile(
    r'^(?:Set|Clear|Assign|Enable|Disable|Store|Write|Send|Start|Stop)\s+',
    re.I,
)

# Guards like "result == E_OK" â€“ group(1) is the switch variable, group(2) is the case value.
_GUARD_EQ_RE = re.compile(r'^([A-Za-z_]\w*)\s*==\s*(\S+)$')


def _strip_ea_prefix(name: str) -> str:
    """Strip a leading English verb prefix from an EA action name.

    Returns the stripped string, or the original if no prefix matched.
    """
    return _EA_VERB_PREFIX_RE.sub('', name).strip()

# Single AUTOSAR-style identifier (no spaces, underscores typical)
# e.g. SysCtlSM_vShutdown  ->  void function call
_AUTOSAR_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]+$')


def infer_return_type(func_name: str) -> str:
    for pattern, rtype in _RETURN_TYPE_PATTERNS:
        if pattern.search(func_name):
            return rtype
    return 'void'


def looks_like_c(name: str) -> bool:
    """Heuristic: return True if name looks like a C expression/statement."""
    name = name.strip()
    if not name:
        return False
    # Explicit return statement
    if name.startswith('return ') or name.startswith('return;'):
        return True
    # Assignment / call pattern with operator
    if _C_EXPR_RE.match(name):
        # But reject if it reads like plain English
        if not _DESCRIPTION_WORDS.search(name):
            return True
    # Single AUTOSAR-style identifier with no spaces = void function call
    if _AUTOSAR_IDENT_RE.match(name) and '_' in name:
        return True
    return False


# Regex to strip an 'if' keyword wrapper from an EA Decision name:
#   "if (expr)"  â†’  group(1) = expr
#   "if expr"    â†’  group(1) = expr
_IF_WRAPPER_RE = re.compile(r'^if\s*\((.+)\)\s*$', re.DOTALL | re.IGNORECASE)
_IF_PREFIX_RE  = re.compile(r'^if\s+(.+)$',           re.DOTALL | re.IGNORECASE)


def _extract_c_condition(condition: str):
    """Try to extract a usable C expression from an EA Decision node name.

    Returns (expr, is_c) where is_c is True if expr can be placed directly
    inside 'if (...)' in generated C code.

    Handles:
      - "if (expr)"        â†’ (expr, True/False depending on looks_like_c)
      - "if expr"          â†’ (expr, True/False)
      - "plain_C_expr"     â†’ (expr, True)   when looks_like_c succeeds
      - descriptive English â†’ (condition, False)
    """
    stripped = condition.strip()
    if not stripped or stripped == 'TODO_CONDITION':
        return condition, False

    def _check(inner: str):
        inner = inner.strip().replace('\r\n', '\n').replace('\r', '\n')
        first_line = inner.split('\n')[0].strip()
        if looks_like_c(first_line):
            return inner, True
        return None

    m = _IF_WRAPPER_RE.match(stripped)
    if m:
        result = _check(m.group(1))
        if result:
            return result

    m2 = _IF_PREFIX_RE.match(stripped)
    if m2:
        result = _check(m2.group(1))
        if result:
            return result

    # Try using the condition text directly (no 'if' prefix in EA name)
    first_line = re.split(r'[\r\n]', stripped)[0].strip()
    if looks_like_c(first_line):
        return stripped.replace('\r\n', '\n').replace('\r', '\n'), True

    return condition, False


def _emit_if_line(emitter: 'CEmitter', condition: str, indent: str) -> None:
    """Emit 'if (...)' using real C when the condition is extractable, else a comment."""
    c_expr, is_c = _extract_c_condition(condition)
    if is_c:
        lines = c_expr.split('\n')
        if len(lines) == 1:
            emitter.emit(f"{indent}if ({c_expr})")
        else:
            # Multi-line condition: keep opening ( on first line, close ) on last
            emitter.emit(f"{indent}if ({lines[0].rstrip()}")
            for ln in lines[1:-1]:
                emitter.emit(f"{indent}        {ln.strip()}")
            emitter.emit(f"{indent}        {lines[-1].strip()})")
    else:
        emitter.emit(f"{indent}if (/* {condition} */)")


def c_statement(name: str) -> str:
    """Format an action name as a C statement line."""
    name = name.strip()
    if name.endswith(";"):
        return name
    # Bare AUTOSAR identifier with no parens/operators = void function call
    if _AUTOSAR_IDENT_RE.match(name) and "(" not in name and "=" not in name:
        return name + "();"
    return name + ";"


def wrap_comment(text: str, indent: str, width: int = 100) -> List[str]:
    """Wrap a long text into /* ... */ comment lines."""
    text = text.strip()
    if not text:
        return []
    lines = textwrap.wrap(text, width - len(indent) - 6) or [text]
    if len(lines) == 1:
        return [f"{indent}/* {lines[0]} */"]
    result = [f"{indent}/* {lines[0]}"]
    for line in lines[1:-1]:
        result.append(f"{indent} * {line}")
    result.append(f"{indent} * {lines[-1]} */")
    return result


# ---------------------------------------------------------------------------
# Graph data structures
# ---------------------------------------------------------------------------

class Step:
    __slots__ = ('guid', 'name', 'type', 'flows', 'traces')

    def __init__(self, guid: str, name: str, stype: str):
        self.guid = guid
        self.name = name
        self.type = stype
        self.flows: List[Tuple[str, str, str]] = []   # (toName, toGuid, guard)
        self.traces: List[Tuple[str, str]] = []        # (reqDocType, tracedToId)

    def __repr__(self) -> str:
        return f"Step({self.type}, {self.name!r}, {self.guid})"


class FlowGraph:
    def __init__(self):
        self.steps: Dict[str, Step] = {}          # guid â†’ Step
        self.in_degree: Dict[str, int] = defaultdict(int)

    def add_step(self, step: Step) -> None:
        self.steps[step.guid] = step

    def build_in_degrees(self) -> None:
        self.in_degree = defaultdict(int)
        for step in self.steps.values():
            for _, to_guid, _ in step.flows:
                if to_guid in self.steps:
                    self.in_degree[to_guid] += 1

    def find_entry(self) -> Optional[str]:
        """Return the guid of the entry StateNode (lowest in-degree, type StateNode)."""
        self.build_in_degrees()
        candidates = [
            guid for guid, step in self.steps.items()
            if step.type == 'StateNode'
            and self.in_degree.get(guid, 0) == 0
        ]
        if candidates:
            return candidates[0]
        # fallback: any step with in_degree == 0
        candidates = [
            guid for guid in self.steps
            if self.in_degree.get(guid, 0) == 0
        ]
        return candidates[0] if candidates else None

    def find_exit(self) -> Optional[str]:
        """Return the guid of the exit StateNode (no outgoing flows)."""
        for guid, step in self.steps.items():
            if step.type == 'StateNode' and not step.flows:
                return guid
        return None

    def find_join(self, guid_a: str, guid_b: str) -> Optional[str]:
        """Find the nearest common successor of guid_a and guid_b via BFS."""
        def reachable(start: str) -> Dict[str, int]:
            dist: Dict[str, int] = {}
            queue = [(start, 0)]
            while queue:
                cur, d = queue.pop(0)
                if cur in dist:
                    continue
                dist[cur] = d
                for _, nxt, _ in self.steps.get(cur, Step('', '', '')).flows:
                    if nxt in self.steps and nxt not in dist:
                        queue.append((nxt, d + 1))
            return dist

        reach_a = reachable(guid_a)
        reach_b = reachable(guid_b)
        common = set(reach_a) & set(reach_b)
        if not common:
            return None
        # Return the closest common node (sum of distances)
        return min(common, key=lambda g: reach_a[g] + reach_b[g])


# ---------------------------------------------------------------------------
# Code emitter
# ---------------------------------------------------------------------------

class CEmitter:
    def __init__(self):
        self._lines: List[str] = []

    def emit(self, line: str = '') -> None:
        self._lines.append(line)

    def lines(self) -> List[str]:
        return self._lines


def _collect_traces(func_el: ET.Element) -> List[Tuple[str, str]]:
    """Collect all traceability links from <Step type="Interface"> elements."""
    traces = []
    for step in func_el.findall('Step'):
        if step.get('type') == 'Interface':
            for tt in step.findall('TableTracedTo'):
                doc_type = (tt.findtext('reqDocType') or '').strip()
                traced_id = (tt.findtext('TracedToId') or '').strip()
                if traced_id:
                    traces.append((doc_type, traced_id))
    return traces


def _parse_function(func_el: ET.Element) -> FlowGraph:
    """Build a FlowGraph from a <Function> XML element."""
    graph = FlowGraph()

    for step_el in func_el.findall('Step'):
        guid = step_el.get('guid', '')
        name = (step_el.get('name') or '').strip()
        stype = (step_el.get('type') or '').strip()

        step = Step(guid, name, stype)

        for flow_el in step_el.findall('Flow'):
            to_name = (flow_el.get('toName') or '').strip()
            to_guid = (flow_el.get('toGuid') or '').strip()
            guard = (flow_el.get('guard') or '').strip()
            if to_guid:
                step.flows.append((to_name, to_guid, guard))

        for tt in step_el.findall('TableTracedTo'):
            doc_type = (tt.findtext('reqDocType') or '').strip()
            traced_id = (tt.findtext('TracedToId') or '').strip()
            if traced_id:
                step.traces.append((doc_type, traced_id))

        graph.add_step(step)

    graph.build_in_degrees()
    return graph


def _emit_step(
    guid: str,
    graph: FlowGraph,
    emitter: CEmitter,
    indent: str,
    visited: Set[str],
    back_edges: Set[Tuple[str, str]],
    path: List[str],
    stop_at: Optional[str],
) -> None:
    """Recursively emit C code for a step and its successors."""

    # Stop conditions
    if guid == stop_at:
        return
    if guid not in graph.steps:
        return
    if guid in visited:
        # We reached a node we already emitted â€” this is a back-edge target
        # (loop join) â€” just emit a comment and return.
        step = graph.steps[guid]
        name_hint = step.name or step.type
        for line in wrap_comment(f"/* LOOP_BACK â†’ {name_hint} */", indent):
            emitter.emit(line)
        return

    visited.add(guid)
    path.append(guid)
    step = graph.steps[guid]

    # â”€â”€ StateNode â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if step.type == 'StateNode':
        if not step.flows:
            # Exit node â€“ nothing to emit, caller handles closing brace
            path.pop()
            return

        # Entry node or merge node â€“ just follow the single outgoing flow
        for _, to_guid, _ in step.flows:
            _emit_step(to_guid, graph, emitter, indent, visited,
                       back_edges, path, stop_at)

    # â”€â”€ Interface â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    elif step.type == 'Interface':
        if step.traces:
            ids = ', '.join(f"{d}:{i}" for d, i in step.traces)
            for line in wrap_comment(f"Traced to: {ids}", indent):
                emitter.emit(line)
        # Interface nodes carry no control flow in the activity diagram
        # (they appear as swim-lane labels), so we stop here.

    # â”€â”€ Action â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    elif step.type == 'Action':
        if step.traces:
            ids = ', '.join(t[1] for t in step.traces)
            for line in wrap_comment(f"/* @Trace: {ids} */", indent):
                emitter.emit(line)

        # A single EA action node may store multiple "Set X = Y" assignments
        # separated by \r\n (EA encodes multi-line text this way).
        sub_names = [s.strip() for s in re.split(r'\r?\n', step.name) if s.strip()]
        if not sub_names:
            sub_names = ['']  # empty name â†’ emit TODO

        for sub in sub_names:
            # Always check for EA verb prefix FIRST.  The general
            # looks_like_c() test can falsely accept "Set *ptr = val"
            # ("Set" is an identifier, "*" is an operator), so we must
            # strip the prefix before deciding how to emit.
            bare = _strip_ea_prefix(sub)
            if bare != sub:
                # Had an EA prefix (Set / Clear / Assign / etc.)
                if looks_like_c(bare):
                    for line in wrap_comment(sub, indent):
                        emitter.emit(line)
                    emitter.emit(f"{indent}{c_statement(bare)}")
                else:
                    for line in wrap_comment(sub, indent):
                        emitter.emit(line)
                    emitter.emit(f"{indent}/* TODO: implement */")
            elif looks_like_c(sub):
                emitter.emit(f"{indent}{c_statement(sub)}")
            else:
                # Descriptive action â€“ emit as comment + TODO
                for line in wrap_comment(sub, indent):
                    emitter.emit(line)
                emitter.emit(f"{indent}/* TODO: implement */")

        if step.flows:
            _, to_guid, _ = step.flows[0]
            _emit_step(to_guid, graph, emitter, indent, visited,
                       back_edges, path, stop_at)

    # â”€â”€ Decision â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    elif step.type == 'Decision':
        flows = step.flows
        yes_flows = [f for f in flows if f[2].lower() in ('yes', 'true')]
        no_flows  = [f for f in flows if f[2].lower() in ('no', 'false')]
        other_flows = [f for f in flows if f[2].lower() not in ('yes', 'true', 'no', 'false')]

        condition = step.name.rstrip('?').strip() if step.name else 'TODO_CONDITION'

        if yes_flows and no_flows:
            # Standard if / else
            join_guid = graph.find_join(yes_flows[0][1], no_flows[0][1])

            _emit_if_line(emitter, condition, indent)
            emitter.emit(f"{indent}{{")
            yes_visited = set(visited)
            yes_path = list(path)
            _emit_step(yes_flows[0][1], graph, emitter, indent + '    ',
                       yes_visited, back_edges, yes_path, join_guid)
            emitter.emit(f"{indent}}}")
            emitter.emit(f"{indent}else")
            emitter.emit(f"{indent}{{")
            no_visited = set(visited)
            no_path = list(path)
            _emit_step(no_flows[0][1], graph, emitter, indent + '    ',
                       no_visited, back_edges, no_path, join_guid)
            emitter.emit(f"{indent}}}")

            # Merge visited from both branches into the main visited set
            visited.update(yes_visited)
            visited.update(no_visited)

            # Continue after the join point
            if join_guid and join_guid != stop_at:
                _emit_step(join_guid, graph, emitter, indent, visited,
                           back_edges, path, stop_at)

        elif other_flows and not yes_flows and not no_flows:
            default_flows = [f for f in other_flows if f[2].strip().lower() == 'default']
            case_flows    = [f for f in other_flows
                             if f[2].strip().lower() != 'default' and f[2].strip()]

            # Detect "VAR == VALUE" guards (e.g. "result == E_OK") and infer
            # the switch variable even when there is no explicit "default" guard.
            eq_pairs = [(f, _GUARD_EQ_RE.match(f[2].strip())) for f in case_flows]
            inferred_switch_var = None
            rewritten_case_flows = case_flows
            if case_flows and all(m for _, m in eq_pairs):
                lhs_vars = {m.group(1) for _, m in eq_pairs}  # type: ignore[union-attr]
                if len(lhs_vars) == 1:
                    inferred_switch_var = next(iter(lhs_vars))
                    rewritten_case_flows = [
                        (n, g, m.group(2))  # type: ignore[union-attr]
                        for (n, g, _), m in eq_pairs
                    ]

            sw_var = inferred_switch_var or condition
            sw_case_flows = rewritten_case_flows

            if (default_flows or inferred_switch_var) and _AUTOSAR_IDENT_RE.match(sw_var):
                # Switch statement: either an explicit "default" guard was present,
                # or all guards share the same "VAR == VALUE" pattern.
                emitter.emit(f"{indent}switch ({sw_var})")
                emitter.emit(f"{indent}{{")  
                switch_base = set(visited)
                for to_name, to_guid, guard in sw_case_flows:
                    # Guard may be "VAL_A or VAL_B" â€“ split on " or "
                    cases = [c.strip() for c in re.split(r'\s+or\s+', guard, flags=re.I)]
                    for c in cases:
                        emitter.emit(f"{indent}    case {c}:")
                    branch_visited = set(switch_base)
                    branch_path = list(path)
                    _emit_step(to_guid, graph, emitter, indent + '        ',
                               branch_visited, back_edges, branch_path, stop_at)
                    emitter.emit(f"{indent}        break;")
                    visited.update(branch_visited)
                for to_name, to_guid, guard in default_flows:
                    emitter.emit(f"{indent}    default:")
                    branch_visited = set(switch_base)
                    branch_path = list(path)
                    _emit_step(to_guid, graph, emitter, indent + '        ',
                               branch_visited, back_edges, branch_path, stop_at)
                    emitter.emit(f"{indent}        break;")
                    visited.update(branch_visited)
                emitter.emit(f"{indent}}}")
            else:
                # No recognisable pattern â€“ emit as comments
                # Fall through the first branch as best-effort
                if other_flows:
                    _emit_step(other_flows[0][1], graph, emitter, indent, visited,
                               back_edges, path, stop_at)

        else:
            # Mixed or single-branch decision
            _emit_if_line(emitter, condition, indent)
            emitter.emit(f"{indent}{{")
            all_flows = yes_flows + no_flows + other_flows
            for to_name, to_guid, guard in all_flows:
                label = guard if guard else to_name
                branch_visited = set(visited)
                branch_path = list(path)
                emitter.emit(f"{indent}    /* [{label}] */")
                _emit_step(to_guid, graph, emitter, indent + '    ',
                           branch_visited, back_edges, branch_path, stop_at)
                visited.update(branch_visited)
            emitter.emit(f"{indent}}}")

    else:
        # Unknown type â€“ emit comment
        for line in wrap_comment(f"[{step.type}] {step.name}", indent):
            emitter.emit(line)
        if step.flows:
            _, to_guid, _ = step.flows[0]
            _emit_step(to_guid, graph, emitter, indent, visited,
                       back_edges, path, stop_at)

    path.pop()


def generate_function(func_el: ET.Element, module_name: str) -> List[str]:
    """Return lines of C code for a single <Function> element."""
    func_name = func_el.get('name', 'unknown_function')
    stereotype = (func_el.get('stereotype') or '').strip()

    graph = _parse_function(func_el)

    # Collect function-level traceability (from Interface steps)
    traces = _collect_traces(func_el)

    emitter = CEmitter()

    # â”€â”€ Doxygen-style function header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _notes   = func_el.get("notes", "").strip()
    _params  = func_el.findall("Param")

    emitter.emit('/**')
    if _notes:
        # First sentence as @brief, rest as @details
        _brief, _, _rest = _notes.partition('.')
        emitter.emit(f' * @brief  {_brief.strip()}.')
        if _rest.strip():
            emitter.emit(f' * @details {_rest.strip()}')
    else:
        emitter.emit(f' * @brief  {func_name}')
    if stereotype:
        emitter.emit(f' * @note   Stereotype: {stereotype}')
    if _params:
        emitter.emit(' *')
        for _p in _params:
            _pname  = _p.get('name', '')
            _ptype  = _p.get('type', '')
            _pnotes = _p.get('notes', '')
            if _pname:
                _ptag = f'[{_ptype}] ' if _ptype else ''
                emitter.emit(f' * @param  {_ptag}{_pname}  {_pnotes}' if _pnotes else f' * @param  {_ptag}{_pname}')
    if traces:
        emitter.emit(' *')
        for doc_type, traced_id in traces:
            emitter.emit(f' * @Trace  {doc_type}: {traced_id}')
    emitter.emit(' *')
    emitter.emit(' * @note   AUTO-GENERATED SKELETON -- review and complete all TODO items.')
    emitter.emit(' */')

    rtype = infer_return_type(func_name)
    emitter.emit(f'{rtype} {func_name}(void)')
    emitter.emit('{')

    # â”€â”€ Function body â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    entry = graph.find_entry()
    if entry is None:
        emitter.emit('    /* TODO: no entry point found in activity diagram */')
    else:
        visited: Set[str] = set()
        back_edges: Set[Tuple[str, str]] = set()
        path: List[str] = []
        _emit_step(entry, graph, emitter, '    ', visited, back_edges, path, None)

    emitter.emit('}')
    emitter.emit('')  # blank line between functions

    return emitter.lines()


# ---------------------------------------------------------------------------
# XML file processing
# ---------------------------------------------------------------------------

def process_xml_file(xml_path: str, output_dir: str) -> str:
    """Parse one XML file and write the corresponding .c skeleton file.

    Returns the path of the generated .c file.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    module_el = root.find('Module')
    if module_el is None:
        # Older format: root IS the module container
        module_el = root

    module_name = module_el.get('name', os.path.splitext(os.path.basename(xml_path))[0])

    all_lines: List[str] = []

    # File-level header
    all_lines += [
        '/*',
        f' * Module  : {module_name}',
        f' * Source  : {os.path.basename(xml_path)}',
        ' *',
        ' * AUTO-GENERATED C SKELETON',
        ' * Generated from SwDetailedDesignDiagram XML export.',
        ' * Review every TODO item before use.',
        ' *',
        ' * NOTE: Return types and parameter lists are inferred from naming',
        ' *       conventions and may need correction.',
        ' */',
        '',
        '#include "stdtypes.h"  /* TODO: include correct headers */',
        '',
    ]

    func_elements = module_el.findall('Function')
    if not func_elements:
        all_lines.append(f'/* No <Function> elements found in {xml_path} */')
    else:
        for func_el in func_elements:
            try:
                func_lines = generate_function(func_el, module_name)
                all_lines.extend(func_lines)
            except Exception as exc:  # noqa: BLE001
                fname = func_el.get('name', '?')
                all_lines.append(f'/* ERROR generating {fname}: {exc} */')
                all_lines.append('')

    # Sanitize module name for use as a filename
    safe_module_name = re.sub(r'[\\/:*?"<>|]', '_', module_name)

    os.makedirs(output_dir, exist_ok=True)
    out_filename = safe_module_name + '_skeleton.c'
    out_path = os.path.join(output_dir, out_filename)
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(all_lines))

    return out_path


# ---------------------------------------------------------------------------
# Per-class generation (uses JSON class->source_file mapping)
# ---------------------------------------------------------------------------

def process_xml_per_class(xml_path, json_path, output_dir):
    # type: (str, str, str) -> List[str]
    """Parse one XML file and write separate .c/.h per EA class.

    Uses a JSON mapping (from export_module_functions.py) that has
    class_name -> source_file so each class writes its own files.
    Returns list of generated file paths.
    """
    import json as _json
    with open(json_path, 'r', encoding='utf-8-sig') as _fh:
        mapping = _json.load(_fh)

    tree = ET.parse(xml_path)
    root = tree.getroot()
    module_el = root.find('Module')
    if module_el is None:
        module_el = root

    module_name = mapping.get('module', {}).get('name', module_el.get('name', 'Unknown'))

    func_map = {}  # type: Dict[str, ET.Element]
    for func_el in module_el.findall('Function'):
        name = func_el.get('name', '')
        if name:
            func_map[name] = func_el

    os.makedirs(output_dir, exist_ok=True)
    generated = []  # type: List[str]

    for cls in mapping.get('classes', []):
        class_name  = cls.get('class_name', 'Unknown')
        source_file = cls.get('source_file', '')
        func_list   = cls.get('functions', [])

        if not source_file or not func_list:
            continue

        header_file = re.sub(r'\.c$', '.h', source_file)

        # --- .c file ---
        c_lines = [
            '/*',
            ' * Class   : ' + class_name,
            ' * Module  : ' + module_name,
            ' *',
            ' * AUTO-GENERATED C SKELETON',
            ' * Generated from SwDetailedDesignDiagram XML by xml_to_c.py',
            ' * Review every TODO item before use.',
            ' *',
            ' * Function bodies derived from EA activity diagram steps:',
            ' *   StateNode -> entry/exit | Action -> C statement',
            ' *   Decision  -> if/else or switch | Loops -> LOOP_BACK comment',
            ' */',
            '',
            '#include "stdtypes.h"',
            '#include "' + header_file + '"',
            '',
        ]

        for func_info in func_list:
            func_name = func_info.get('name', '')
            if func_name not in func_map:
                c_lines.append('/* WARNING: ' + func_name + ' not found in XML */')
                c_lines.append('')
                continue
            try:
                c_lines.extend(generate_function(func_map[func_name], module_name))
                c_lines.append('')
            except Exception as exc:
                c_lines.append('/* ERROR generating ' + func_name + ': ' + str(exc) + ' */')
                c_lines.append('')

        c_path = os.path.join(output_dir, source_file)
        with open(c_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(c_lines))
        generated.append(c_path)

        # --- .h file ---
        guard = re.sub(r'[^A-Z0-9_]', '_', header_file.upper())
        h_lines = [
            '/*',
            ' * Class   : ' + class_name,
            ' * Module  : ' + module_name,
            ' * AUTO-GENERATED HEADER',
            ' */',
            '',
            '#ifndef ' + guard,
            '#define ' + guard,
            '',
            '#include "stdtypes.h"',
            '',
            '/* Function prototypes */',
        ]
        for func_info in func_list:
            func_name = func_info.get('name', '')
            if func_name in func_map:
                rtype = infer_return_type(func_name)
                h_lines.append(rtype + ' ' + func_name + '(void);')
        h_lines += ['', '#endif  /* ' + guard + ' */', '']

        h_path = os.path.join(output_dir, header_file)
        with open(h_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(h_lines))
        generated.append(h_path)

    return generated


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv):
    # type: (List[str]) -> None
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate C skeletons from SwDetailedDesignDiagram XML.',
    )
    parser.add_argument('input', nargs='?',
                        help='XML file or directory (default: ai_output/)')
    parser.add_argument('output_dir', nargs='?',
                        help='Output directory (default: ai_output/generated_c/)')
    parser.add_argument('--per-class', action='store_true',
                        help='Generate one .c/.h per EA class (requires --json-mapping)')
    parser.add_argument('--json-mapping',
                        help='Path to SwMod_*_Functions.json for per-class generation')

    args = parser.parse_args(argv[1:])

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    inp     = args.input      or os.path.join(project_root, 'ai_output')
    out_dir = args.output_dir or os.path.join(project_root, 'ai_output', 'generated_c')

    # Per-class mode
    if args.per_class:
        if not args.json_mapping:
            print('ERROR: --per-class requires --json-mapping <path>', file=sys.stderr)
            sys.exit(1)
        if not os.path.isfile(inp):
            print('ERROR: --per-class requires a single XML file, got: ' + inp, file=sys.stderr)
            sys.exit(1)
        generated = process_xml_per_class(inp, args.json_mapping, out_dir)
        for p in generated:
            print('Generated: ' + p)
        return

    # Original single-file mode
    if os.path.isfile(inp):
        xml_files = [inp]
    elif os.path.isdir(inp):
        xml_files = [
            os.path.join(inp, f)
            for f in os.listdir(inp)
            if f.lower().endswith('.xml')
        ]
    else:
        print('ERROR: ' + inp + ' is not a file or directory', file=sys.stderr)
        sys.exit(1)

    if not xml_files:
        print('No XML files found.', file=sys.stderr)
        sys.exit(1)

    for xml_path in sorted(xml_files):
        try:
            out_path = process_xml_file(xml_path, out_dir)
            print('Generated: ' + out_path)
        except Exception as exc:
            print('ERROR processing ' + xml_path + ': ' + str(exc), file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv)
