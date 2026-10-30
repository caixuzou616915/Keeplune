"""
Tool: import_code_to_diagrams.py

Reverse direction: reads generated C source files and creates or updates
the SwDetailedDesignDiagram XML files that represent activity diagrams.

Workflow
--------
For every function body found in the C source:
  1. Parse the C body into a flow graph (steps + control flows).
  2. Look for an existing SwDetailedDesignDiagram XML file that already
     contains a <Function> element with the same name.
  3.  a) If found: compare the parsed graph with the stored graph and update
         changed/added/removed steps.  Preserve existing GUIDs wherever
         possible so EA can reconcile changes.
      b) If not found: generate a new XML file (or append to a module XML
         if the module file already exists).
  4. Write a human-readable report of every change made.

The C parser is intentionally conservative: it recognises the *same* patterns
that xmi_to_c.py and xml_to_c.py emit, so round-trip stability is guaranteed
for auto-generated code.  Hand-edited C bodies that follow the same coding
style are also handled correctly.

Usage
-----
Single file:
    python scripts/import_code_to_diagrams.py ai_output/generated_c/SwMod_TouchSM.c

Directory (all .c files):
    python scripts/import_code_to_diagrams.py ai_output/generated_c/

Multiple files:
    python scripts/import_code_to_diagrams.py file1.c file2.c ...

Options
-------
--diagrams DIR   Directory containing/receiving the diagram XML files.
                 Defaults to <project_root>/ai_output/.
--report FILE    Write the change report to FILE instead of stdout.
--dry-run        Parse and diff but do not write any XML files.
--module NAME    Override the module name (auto-detected from filename).
--functions F,.. Comma-separated list of function names to process.
--push-to-ea     After writing diagram XMLs, automatically import them into
                 Enterprise Architect via COM (calls ea_import_diagrams_from_xml
                 internally). EA must be running. Requires .venv32 Python.

Output
------
Updated/created SwDetailedDesignDiagram*.xml files in the diagrams directory.
A change report printed to stdout (or written to --report FILE).
"""

from __future__ import annotations

import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------
_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_TOOL_DIR)))
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _SRC_DIR)
sys.path.insert(0, _TOOL_DIR)

from config.settings import OUTPUT_DIR  # noqa: E402

_DEFAULT_DIAGRAMS_DIR = OUTPUT_DIR


# ===========================================================================
# Step / Graph data structures (same semantics as xml_to_c.Step / FlowGraph)
# ===========================================================================

@dataclass
class CStep:
    """A single node in a function's flow graph reconstructed from C code."""
    guid: str
    name: str                    # human-readable label (the C statement text)
    type: str                    # StateNode | Action | Decision
    flows: List[Tuple[str, str, str]] = field(default_factory=list)
    # (toName, toGuid, guard)

    def signature(self) -> str:
        """Normalised string for equality comparison (ignores GUIDs)."""
        flows_sig = "|".join(
            f"{g}:{n}" for _, g, n in sorted(self.flows, key=lambda f: f[2])
        )
        return f"{self.type}:{self.name}::{flows_sig}"


@dataclass
class CFuncGraph:
    """Flow graph for one C function."""
    func_name: str
    steps: Dict[str, CStep] = field(default_factory=dict)   # guid → CStep
    entry_guid: Optional[str] = None
    exit_guid: Optional[str] = None
    return_type: str = ''   # extracted from C signature, e.g. 'Std_ReturnType'
    raw_params: str = ''    # raw param list string, e.g. 'uint8 a, const uint8* b'

    def ordered_steps(self) -> List[CStep]:
        """Return steps in BFS order from entry."""
        if not self.entry_guid:
            return list(self.steps.values())
        result, seen, queue = [], set(), [self.entry_guid]
        while queue:
            g = queue.pop(0)
            if g in seen or g not in self.steps:
                continue
            seen.add(g)
            result.append(self.steps[g])
            for _, to_g, _ in self.steps[g].flows:
                if to_g not in seen and to_g in self.steps:
                    queue.append(to_g)
        # append unreachable (should not happen normally)
        for g, s in self.steps.items():
            if g not in seen:
                result.append(s)
        return result


def _new_guid() -> str:
    return "{" + str(uuid.uuid4()).upper() + "}"


# ===========================================================================
# C body tokeniser / parser
# ===========================================================================

# Matches a single-line comment  /* ... */  (non-greedy, no newlines inside)
_SL_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)

# Strip leading language-keyword decorators so we get the bare condition
_IF_STRIP_RE   = re.compile(r'^\s*if\s*\(\s*(.*?)\s*\)\s*$', re.DOTALL)
_ELSE_RE       = re.compile(r'^\s*else\s*$')
_SWITCH_RE     = re.compile(r'^\s*switch\s*\(\s*(\w+)\s*\)\s*$')
_CASE_RE       = re.compile(r'^\s*case\s+(\S+?)\s*:\s*$')
_DEFAULT_RE    = re.compile(r'^\s*default\s*:\s*$')
_BREAK_RE      = re.compile(r'^\s*break\s*;\s*$')
_RETURN_RE     = re.compile(r'^\s*return\b.*;\s*$')
# Also match pointer-deref assignments like  *ptr = value;
_STMT_RE       = re.compile(r'^\s*[\*A-Za-z_].*;\s*$')


def _strip_comment(line: str) -> str:
    """Remove /* ... */ comment spans from a line, return stripped text."""
    return _SL_COMMENT_RE.sub('', line).strip()


def _is_todo(line: str) -> bool:
    return 'TODO' in line or 'TODO:' in line


def _comment_text(line: str) -> str:
    """Extract text from a /* ... */ comment line."""
    m = re.search(r'/\*\s*(.*?)\s*\*/', line, re.DOTALL)
    return m.group(1).strip() if m else line.strip()


class _Token:
    """Simple token produced by the C line scanner."""
    __slots__ = ('kind', 'text', 'line_no')
    # kinds: IF_COND, ELSE, SWITCH, CASE, DEFAULT, BREAK, RETURN, STMT,
    #        TODO, COMMENT, LBRACE, RBRACE, BLANK
    def __init__(self, kind: str, text: str, line_no: int):
        self.kind    = kind
        self.text    = text
        self.line_no = line_no

    def __repr__(self) -> str:
        return f"Token({self.kind}, {self.text!r})"


def tokenise_body(lines: List[str]) -> List[_Token]:
    """Scan the lines of a C function body and produce a token stream."""
    tokens: List[_Token] = []
    i = 0
    while i < len(lines):
        raw  = lines[i]
        bare = raw.strip()
        ln   = i + 1

        if not bare:
            tokens.append(_Token('BLANK', '', ln))
            i += 1
            continue

        if bare == '{':
            tokens.append(_Token('LBRACE', '{', ln))
            i += 1
            continue

        if bare == '}' or bare == '};':
            tokens.append(_Token('RBRACE', '}', ln))
            i += 1
            continue

        if _BREAK_RE.match(bare):
            tokens.append(_Token('BREAK', 'break', ln))
            i += 1
            continue

        # Multi-line comment that spans lines: collect until */
        if bare.startswith('/*') and '*/' not in bare:
            collected = [bare]
            i += 1
            while i < len(lines) and '*/' not in lines[i]:
                collected.append(lines[i].strip())
                i += 1
            if i < len(lines):
                collected.append(lines[i].strip())
                i += 1
            full = ' '.join(collected)
            text = _comment_text(full)
            if _is_todo(text):
                tokens.append(_Token('TODO', text, ln))
            else:
                tokens.append(_Token('COMMENT', text, ln))
            continue

        # Single-line comment
        if bare.startswith('/*') and bare.endswith('*/'):
            text = _comment_text(bare)
            if _is_todo(text):
                tokens.append(_Token('TODO', text, ln))
            else:
                tokens.append(_Token('COMMENT', text, ln))
            i += 1
            continue

        # Strip trailing inline comments (both /* ... */ and // ...) before
        # matching control-flow keywords and statements.
        bare_nc = re.sub(r'\s*//.*$', '', _SL_COMMENT_RE.sub('', bare)).strip()

        if _ELSE_RE.match(bare_nc):
            tokens.append(_Token('ELSE', 'else', ln))
            i += 1
            continue

        if _DEFAULT_RE.match(bare_nc):
            tokens.append(_Token('DEFAULT', 'default', ln))
            i += 1
            continue

        m = _CASE_RE.match(bare_nc)
        if m:
            tokens.append(_Token('CASE', m.group(1), ln))
            i += 1
            continue

        m = _SWITCH_RE.match(bare_nc)
        if m:
            tokens.append(_Token('SWITCH', m.group(1), ln))
            i += 1
            continue

        # else if (cond) – emit ELSE then fall into IF_COND handling below
        _ELSE_IF_RE_local = re.compile(r'^\s*else\s+if\s*\(', re.IGNORECASE)
        if _ELSE_IF_RE_local.match(bare_nc):
            tokens.append(_Token('ELSE', 'else', ln))
            # strip 'else ' prefix and re-process as if (cond)
            bare = re.sub(r'^\s*else\s+', '', bare, count=1)
            bare_nc = re.sub(r'^\s*else\s+', '', bare_nc, count=1)
            # fall through to if (cond) handling below

        # if (cond) – possibly multi-line condition
        if bare_nc.startswith('if (') or bare_nc.startswith('if('):
            # Collect lines until the condition is balanced
            collected = bare
            depth = collected.count('(') - collected.count(')')
            j = i + 1
            while depth > 0 and j < len(lines):
                nxt = lines[j].strip()
                collected += ' ' + nxt
                depth += nxt.count('(') - nxt.count(')')
                j += 1
            # Remove trailing {
            cond_line = collected.rstrip(' {').strip()
            m2 = _IF_STRIP_RE.match(cond_line)
            cond = m2.group(1) if m2 else cond_line
            # Strip comment wrappers  /* cond */
            cond = re.sub(r'^/\*\s*', '', cond)
            cond = re.sub(r'\s*\*/$', '', cond)
            tokens.append(_Token('IF_COND', cond.strip(), ln))
            i = j
            continue

        if _RETURN_RE.match(bare_nc):
            val = re.sub(r'^\s*return\s+', '', bare_nc).rstrip(';').strip()
            tokens.append(_Token('RETURN', val, ln))
            i += 1
            continue

        if _STMT_RE.match(bare_nc):
            tokens.append(_Token('STMT', bare_nc.rstrip(';').strip(), ln))
            i += 1
            continue

        # Anything else: treat as a comment / label
        tokens.append(_Token('COMMENT', bare, ln))
        i += 1

    return tokens


# ===========================================================================
# Flow graph builder from token stream
# ===========================================================================

class _GraphBuilder:
    """
    Recursive-descent builder that turns the flat token stream for one
    C function body into a CFuncGraph.
    """

    def __init__(self, func_name: str):
        self._fname  = func_name
        self._graph  = CFuncGraph(func_name=func_name)
        self._tokens: List[_Token] = []
        self._pos    = 0

    # ── Convenience ────────────────────────────────────────────────────────

    def _add(self, step: CStep) -> CStep:
        self._graph.steps[step.guid] = step
        return step

    def _peek(self) -> Optional[_Token]:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _consume(self, kind: str = None) -> Optional[_Token]:
        t = self._peek()
        if t and (kind is None or t.kind == kind):
            self._pos += 1
            return t
        return None

    def _skip_blanks(self) -> None:
        while self._peek() and self._peek().kind == 'BLANK':
            self._pos += 1

    # ── Top-level entry ────────────────────────────────────────────────────

    def build(self, tokens: List[_Token]) -> CFuncGraph:
        self._tokens = tokens
        self._pos    = 0

        entry = CStep(_new_guid(), '', 'StateNode')
        self._add(entry)
        self._graph.entry_guid = entry.guid

        exit_step = CStep(_new_guid(), '', 'StateNode')
        self._add(exit_step)
        self._graph.exit_guid = exit_step.guid

        last = self._parse_stmts(exit_step.guid)
        if last and last != exit_step.guid:
            self._graph.steps[last].flows.append(('', exit_step.guid, ''))

        entry.flows.append(('', list(self._graph.steps.keys())[2] if len(self._graph.steps) > 2
                             else exit_step.guid, ''))
        # fix entry flow to first real step
        real_steps = [g for g in self._graph.steps if g not in (entry.guid, exit_step.guid)]
        if real_steps:
            entry.flows = [('', real_steps[0], '')]
        else:
            entry.flows = [('', exit_step.guid, '')]

        return self._graph

    # ── Statement list parser ──────────────────────────────────────────────

    def _parse_stmts(self, break_target: str,
                     stop_at_case: bool = False) -> Optional[str]:
        """
        Parse a sequence of statements at the current indent level.
        Returns the guid of the *last* step emitted, or None if no steps
        were emitted.  Links consecutive steps together.

        When *stop_at_case* is True (used by _parse_switch) the loop stops
        before the next CASE or DEFAULT token so each case gets its own body.
        """
        prev_guid: Optional[str] = None
        self._skip_blanks()

        while self._peek() and self._peek().kind not in ('RBRACE',):
            if stop_at_case and self._peek().kind in ('CASE', 'DEFAULT', 'BREAK'):
                break
            tok = self._peek()

            if tok.kind == 'BLANK':
                self._consume()
                continue

            # ── if / else / else-if ────────────────────────────────────────
            if tok.kind == 'IF_COND':
                self._consume()
                dec_guid, join_guid = self._parse_if_stmt(
                    tok.text, break_target)
                if prev_guid:
                    self._graph.steps[prev_guid].flows.append(
                        ('', dec_guid, ''))
                prev_guid = join_guid
                continue

            # ── switch / case ──────────────────────────────────────────────
            if tok.kind == 'SWITCH':
                self._consume()
                self._skip_blanks()
                self._consume('LBRACE')
                # _parse_switch now returns (decision_guid, join_guid) so the
                # switch Decision is reachable from the main flow, allowing
                # _place_chain to properly handle nested if/else branches.
                switch_dec, switch_join = self._parse_switch(tok.text, break_target)
                self._consume('RBRACE')
                self._skip_blanks()
                if prev_guid and switch_dec:
                    self._graph.steps[prev_guid].flows.append(
                        ('', switch_dec, ''))
                prev_guid = switch_join
                continue

            # ── return ────────────────────────────────────────────────────
            if tok.kind == 'RETURN':
                self._consume()
                s = CStep(_new_guid(), f'return {tok.text}', 'Action')
                self._add(s)
                if prev_guid:
                    self._graph.steps[prev_guid].flows.append(
                        (s.name, s.guid, ''))
                # return always flows to exit
                s.flows.append(('', self._graph.exit_guid, ''))
                prev_guid = s.guid
                continue

            # ── statement ─────────────────────────────────────────────────
            if tok.kind == 'STMT':
                self._consume()
                s = CStep(_new_guid(), tok.text, 'Action')
                self._add(s)
                if prev_guid:
                    self._graph.steps[prev_guid].flows.append(
                        (s.name, s.guid, ''))
                prev_guid = s.guid
                continue

            # ── comment (descriptive, not TODO) – skip, not a diagram step ─
            if tok.kind == 'COMMENT':
                self._consume()
                continue

            # ── TODO – emit a stub Action ─────────────────────────────────
            if tok.kind == 'TODO':
                self._consume()
                s = CStep(_new_guid(), '/* TODO: implement */', 'Action')
                self._add(s)
                if prev_guid:
                    self._graph.steps[prev_guid].flows.append(
                        (s.name, s.guid, ''))
                prev_guid = s.guid
                continue

            # ── break – handled by switch parser; skip here ───────────────
            if tok.kind == 'BREAK':
                self._consume()
                continue

            # Default: skip unknown token
            self._consume()

        return prev_guid

    def _parse_branch(self, break_target: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse a brace-delimited branch; return (first_guid, last_guid)."""
        first_key = len(self._graph.steps)
        last = self._parse_stmts(break_target)
        new_keys = list(self._graph.steps.keys())[first_key:]
        first = new_keys[0] if new_keys else None
        return first, last

    def _parse_if_stmt(self, cond_text: str, break_target: str
                       ) -> Tuple[str, str]:
        """
        Parse a complete if / else-if / else chain starting from the already-
        consumed IF_COND token text.  Handles any depth of  else-if  by
        recursing.  Returns (decision_guid, join_guid).
        """
        node = CStep(_new_guid(), cond_text, 'Decision')
        self._add(node)

        # TRUE branch (always brace-delimited)
        self._skip_blanks()
        self._consume('LBRACE')
        true_first, true_last = self._parse_branch(break_target)
        self._consume('RBRACE')
        self._skip_blanks()

        # FALSE / else / else-if branch
        false_first: Optional[str] = None
        false_last:  Optional[str] = None
        if self._peek() and self._peek().kind == 'ELSE':
            self._consume()   # consume 'else'
            self._skip_blanks()
            if self._peek() and self._peek().kind == 'IF_COND':
                # else if (cond) { ... } – recurse
                inner_tok = self._consume()  # consume the IF_COND token
                inner_dec, inner_join = self._parse_if_stmt(
                    inner_tok.text, break_target)
                false_first = inner_dec
                false_last  = inner_join
            else:
                # plain else { ... }
                self._consume('LBRACE')
                false_first, false_last = self._parse_branch(break_target)
                self._consume('RBRACE')
                self._skip_blanks()

        # Join / merge node
        join = CStep(_new_guid(), '', 'StateNode')
        self._add(join)

        # Wire TRUE → join
        if true_last:
            self._graph.steps[true_last].flows.append(('', join.guid, ''))
        # Wire FALSE → join
        if false_last:
            self._graph.steps[false_last].flows.append(('', join.guid, ''))

        # Wire decision flows
        if true_first:
            node.flows.append((
                self._graph.steps[true_first].name, true_first, 'TRUE'))
        else:
            node.flows.append(('', join.guid, 'TRUE'))

        if false_first:
            node.flows.append((
                self._graph.steps[false_first].name, false_first, 'FALSE'))
        else:
            node.flows.append(('', join.guid, 'FALSE'))

        return node.guid, join.guid

    def _parse_switch(self, var: str, outer_break_target: str) -> Optional[str]:
        """
        Parse case / default branches inside a switch block.
        Handles fall-through (cases without a terminal break) by wiring the
        last step of a fall-through case directly to the first step of the
        next case body.
        Returns (decision_guid, join_guid).
        """
        # Decision node for the switch condition
        decision = CStep(_new_guid(), var, 'Decision')
        self._add(decision)

        join = CStep(_new_guid(), '', 'StateNode')
        self._add(join)

        self._skip_blanks()
        current_cases: List[str] = []

        # Records for fall-through wiring: (guards, first_guid, last_guid, had_break)
        case_records: List[Tuple[List[str], str, Optional[str], bool]] = []

        while self._peek() and self._peek().kind not in ('RBRACE',):
            tok = self._peek()

            if tok.kind == 'BLANK':
                self._consume()
                continue

            if tok.kind == 'CASE':
                self._consume()
                current_cases.append(tok.text)
                continue

            if tok.kind == 'DEFAULT':
                self._consume()
                current_cases.append('default')
                continue

            if tok.kind == 'BREAK':
                self._consume()
                # Terminal break outside a case body — reset pending cases
                current_cases = []
                continue

            # Any real statement/control starts a case body
            if current_cases:
                first_key = len(self._graph.steps)
                last = self._parse_stmts(join.guid, stop_at_case=True)
                new_keys = list(self._graph.steps.keys())[first_key:]
                first_case_guid = new_keys[0] if new_keys else join.guid

                # Check for terminal break after the body
                self._skip_blanks()
                had_break = False
                if self._peek() and self._peek().kind == 'BREAK':
                    self._consume()
                    had_break = True

                case_records.append(
                    (list(current_cases), first_case_guid, last, had_break))
                current_cases = []
                continue

            self._consume()

        # ── Wire decision → first step of each case, and handle fall-through ──
        for idx, (guards, first_guid, last_guid, had_break) in enumerate(case_records):
            for guard in guards:
                decision.flows.append((
                    self._graph.steps[first_guid].name
                    if first_guid in self._graph.steps else '',
                    first_guid,
                    guard
                ))

            if last_guid and last_guid in self._graph.steps:
                last_step = self._graph.steps[last_guid]
                goes_to_exit = any(
                    t == self._graph.exit_guid for _, t, _ in last_step.flows
                )
                if not goes_to_exit:
                    if not had_break and idx + 1 < len(case_records):
                        # Fall-through: wire to first step of next case body
                        next_first = case_records[idx + 1][1]
                        last_step.flows.append(('', next_first, ''))
                    else:
                        last_step.flows.append(('', join.guid, ''))

        return decision.guid, join.guid


# ===========================================================================
# C file parser  →  {func_name: CFuncGraph}
# ===========================================================================

# Matches a C function signature line.
# Handles both plain C (optional static + return type) and
# Autosar-style  FUNC(rettype)  /  FUNC(rettype, memclass)  prefixes.
_FUNC_SIG_RE = re.compile(
    r'^(?:'
    r'FUNC\s*\([^)]+\)\s+'          # FUNC(rettype) or FUNC(rettype, memclass)
    r'|(?:static\s+)?(?:\w[\w\s\*]*?\s+)'  # or regular return type
    r')'
    r'(\w+)'                         # function name  ← group 1
    r'\s*\('                         # opening paren
    r'.*'                            # params (may be on same line)
)

# Detect variable declaration / initialisation lines that should NOT become steps
_VAR_DECL_RE = re.compile(
    r'^\s*(?:static\s+|const\s+|volatile\s+)*'
    r'(?:unsigned\s+|signed\s+)?'
    r'\w+\s+\**\w+\s*(?:=.*)?;'
)


def _is_var_decl(line: str) -> bool:
    """Return True for lines like 'Std_ReturnType retVal = (Std_ReturnType)0;'"""
    bare = line.strip()
    # Quick heuristic: retVal-style initialisations are decls, not actions
    if re.match(r'^\w+\s+\w+\s*=', bare):
        return True
    return False


def parse_c_file(c_path: str) -> Dict[str, CFuncGraph]:
    """
    Parse a generated .c file and return a dict mapping function name →
    CFuncGraph.  Only functions with non-trivial bodies (at least one
    statement other than a single retVal declaration) are included.
    """
    with open(c_path, encoding='utf-8', errors='replace') as fh:
        source = fh.read()

    graphs: Dict[str, CFuncGraph] = {}

    # Split into lines; find function boundaries at column-0 braces
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _FUNC_SIG_RE.match(line)
        if not m:
            i += 1
            continue

        func_name = m.group(1)

        # Extract return type and raw parameter list from the signature
        func_sig_line = lines[i]
        _m_macro = re.match(r'^FUNC\s*\(([^,)]+)', func_sig_line)
        if _m_macro:
            _return_type = _m_macro.group(1).strip()
        else:
            _idx_name = func_sig_line.find(func_name)
            _return_type = func_sig_line[:_idx_name].strip() if _idx_name > 0 else ''
        # Collect signature text (may span multiple lines) to extract params
        _sig_text = func_sig_line
        _sig_j = i
        _raw_params = ''
        while True:
            _after = _sig_text[_sig_text.find(func_name) + len(func_name):]
            if '(' in _after:
                _depth = 0
                _collecting = False
                _buf = ''
                for _ch in _after:
                    if _ch == '(':
                        _depth += 1
                        _collecting = True
                    elif _ch == ')':
                        _depth -= 1
                        if _depth == 0:
                            break
                        _buf += _ch
                    elif _collecting:
                        _buf += _ch
                if _depth <= 0:
                    _raw_params = _buf.strip()
                    break
            _sig_j += 1
            if _sig_j >= len(lines):
                break
            _sig_text += ' ' + lines[_sig_j].strip()

        # Find the opening brace (may be same line or next)
        j = i
        while j < len(lines) and '{' not in lines[j]:
            j += 1
        if j >= len(lines):
            i += 1
            continue

        # Find the matching closing brace at column 0
        brace_depth = 0
        body_lines: List[str] = []
        k = j
        while k < len(lines):
            ln = lines[k]
            brace_depth += ln.count('{') - ln.count('}')
            if k > j:
                body_lines.append(ln)
            if brace_depth == 0 and k > j:
                break
            k += 1

        # Filter out pure variable declarations at the top of the function
        content_lines = [
            ln for ln in body_lines
            if ln.strip() and not _is_var_decl(ln)
        ]
        if not content_lines:
            i = k + 1
            continue

        tokens = tokenise_body(body_lines)
        # Skip if only TODO / blank
        real_tokens = [t for t in tokens
                       if t.kind not in ('BLANK', 'TODO', 'LBRACE', 'RBRACE', 'BREAK')]
        if not real_tokens:
            # Still create a stub graph so we can write a placeholder
            pass

        builder = _GraphBuilder(func_name)
        graph = builder.build(tokens)
        graph.return_type = _return_type
        graph.raw_params = _raw_params
        graphs[func_name] = graph

        i = k + 1

    return graphs


# ===========================================================================
# XML serialisation
# ===========================================================================

_XML_PREAMBLE = '<?xml version="1.0" encoding="utf-8"?>\n'


def _graph_to_func_xml(graph: CFuncGraph,
                        existing_guids: Dict[str, str],
                        func_guid: str,
                        stereotype: str = '',
                        diagram_guid: str = '') -> ET.Element:
    """
    Serialise a CFuncGraph to a <Function> XML element.

    Parameters
    ----------
    graph           : the parsed flow graph
    existing_guids  : mapping step_name -> existing guid (from current XML,
                      unnamed steps excluded)
    func_guid       : GUID to use for the <Function> element itself
    """
    func_el = ET.Element('Function',
                         name=graph.func_name,
                         guid=func_guid,
                         stereotype=stereotype,
                         diagramGuid=diagram_guid or _new_guid(),
                         returnType=graph.return_type,
                         rawParams=graph.raw_params)

    # First pass: build fresh_guid -> assigned_guid remap for ALL steps.
    # Named steps reuse their existing GUID for the *first* occurrence only;
    # subsequent steps with the same name keep their fresh UUID to avoid
    # collapsing distinct nodes into one.
    guid_remap: Dict[str, str] = {}
    used_existing: set = set()
    for step in graph.ordered_steps():
        if step.name:
            existing = existing_guids.get(step.name)
            if existing and existing not in used_existing:
                guid_remap[step.guid] = existing
                used_existing.add(existing)
            else:
                guid_remap[step.guid] = step.guid
        else:
            guid_remap[step.guid] = step.guid   # always fresh for unnamed

    # Second pass: emit XML using the remap for both step GUIDs and flows.
    # Guard against duplicate remapped GUIDs (can happen when two distinct
    # CStep objects share the same step.name and collapse to the same GUID).
    emitted_guids: set = set()
    for step in graph.ordered_steps():
        remapped = guid_remap[step.guid]
        if remapped in emitted_guids:
            continue
        emitted_guids.add(remapped)
        step_el = ET.SubElement(func_el, 'Step',
                                name=step.name,
                                type=step.type,
                                guid=guid_remap[step.guid])
        for to_name, to_guid, guard in step.flows:
            # Resolve via guid remap (correct); name-based lookup would
            # collapse '' -> StateNode guid and mis-route entry's first flow.
            resolved_to = guid_remap.get(to_guid, to_guid)
            ET.SubElement(step_el, 'Flow',
                          toName=to_name,
                          toGuid=resolved_to,
                          guard=guard)

    return func_el


def _build_xml_document(module_name: str,
                         module_guid: str,
                         functions: List[ET.Element]) -> ET.Element:
    root = ET.Element('SwDetailedDesignDiagrams')
    mod_el = ET.SubElement(root, 'Module',
                            name=module_name,
                            guid=module_guid)
    for f in functions:
        mod_el.append(f)
    ET.indent(root, space='  ')
    return root


def _write_xml(root: ET.Element, path: str) -> None:
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(ET.tostring(root, encoding='unicode'))


# ===========================================================================
# Diff engine
# ===========================================================================

@dataclass
class StepChange:
    kind: str          # 'added' | 'removed' | 'modified' | 'unchanged'
    step_name: str
    old_value: str = ''
    new_value: str = ''


@dataclass
class FuncDiff:
    func_name: str
    status: str           # 'new' | 'updated' | 'unchanged'
    changes: List[StepChange] = field(default_factory=list)

    def has_changes(self) -> bool:
        return bool(self.changes) or self.status == 'new'


def _diff_graph_vs_xml(graph: CFuncGraph,
                        func_el: Optional[ET.Element]) -> FuncDiff:
    """
    Compare a parsed CFuncGraph against an existing <Function> XML element.

    Returns a FuncDiff describing what has changed.
    """
    if func_el is None:
        return FuncDiff(func_name=graph.func_name, status='new',
                        changes=[StepChange('added', s.name)
                                 for s in graph.steps.values()])

    # Build a normalised step map from the existing XML
    existing: Dict[str, str] = {}   # name → type
    for s in func_el.findall('Step'):
        n = (s.get('name') or '').strip()
        t = (s.get('type') or '').strip()
        existing[n] = t

    new_steps: Dict[str, str] = {
        (s.name or '').strip(): s.type
        for s in graph.steps.values()
    }

    changes: List[StepChange] = []

    for name, typ in new_steps.items():
        if name not in existing:
            changes.append(StepChange('added', name, new_value=typ))
        elif existing[name] != typ:
            changes.append(StepChange('modified', name,
                                      old_value=existing[name],
                                      new_value=typ))

    for name in existing:
        if name not in new_steps:
            changes.append(StepChange('removed', name, old_value=existing[name]))

    status = 'updated' if changes else 'unchanged'
    return FuncDiff(func_name=graph.func_name, status=status, changes=changes)


# ===========================================================================
# Existing XML management
# ===========================================================================

def _load_existing_diagrams(diagrams_dir: str,
                              module_name: str) -> Dict[str, Tuple[str, ET.Element]]:
    """
    Find all existing SwDetailedDesignDiagram XML files for the module and
    return a dict mapping function_name → (xml_path, <Function> Element).
    """
    result: Dict[str, Tuple[str, ET.Element]] = {}
    try:
        for fname in sorted(os.listdir(diagrams_dir)):
            if ('SwDetailedDesignDiagram' not in fname
                    or module_name not in fname
                    or not fname.endswith('.xml')):
                continue
            fpath = os.path.join(diagrams_dir, fname)
            try:
                tree = ET.parse(fpath)
                root = tree.getroot()
                for mod_el in root.findall('Module'):
                    for func_el in mod_el.findall('Function'):
                        name = (func_el.get('name') or '').strip()
                        if name:
                            result[name] = (fpath, func_el)
            except ET.ParseError:
                pass
    except OSError:
        pass
    return result


def _existing_step_guids(func_el: Optional[ET.Element]) -> Dict[str, str]:
    """Return mapping step_name -> existing_guid from an existing <Function>.

    Unnamed steps (type='StateNode', name='') are intentionally excluded so
    entry and exit StateNodes always receive fresh unique GUIDs on each
    regeneration.  When both StateNodes share name='' the dict would collapse
    them to one key, causing both nodes to get the same GUID (the original
    collision bug that made entry and exit indistinguishable).
    """
    if func_el is None:
        return {}
    result: Dict[str, str] = {}
    for s in func_el.findall('Step'):
        name = (s.get('name') or '').strip()
        if not name:          # skip unnamed steps (entry/exit StateNodes)
            continue
        result[name] = s.get('guid') or _new_guid()
    return result


def _get_or_create_xml_path(module_name: str, diagrams_dir: str,
                              existing_paths: Dict[str, str]) -> str:
    """
    Return the XML path to write new functions into.  Reuses the first
    existing module XML if any; otherwise creates a fresh filename.
    """
    # If there is already a file for this module, use it
    for p in existing_paths.values():
        if module_name in p:
            return p
    # Create a new file
    guid_compact = _new_guid().replace('{', '').replace('}', '').replace('-', '')
    fname = f'SwDetailedDesignDiagramSwMod_{module_name.replace("SwMod_", "")}{guid_compact[:30]}.xml'
    return os.path.join(diagrams_dir, fname)


# ===========================================================================
# Report generation
# ===========================================================================

def format_report(diffs: List[FuncDiff], c_path: str, dry_run: bool) -> str:
    lines = []
    lines.append('=' * 70)
    lines.append('Import Code to Diagrams - Change Report')
    lines.append(f'Source file : {c_path}')
    lines.append(f'Mode        : {"DRY RUN (no files written)" if dry_run else "LIVE"}')
    lines.append('=' * 70)
    lines.append('')

    new_funcs      = [d for d in diffs if d.status == 'new']
    updated_funcs  = [d for d in diffs if d.status == 'updated']
    unchanged_funcs= [d for d in diffs if d.status == 'unchanged']

    lines.append(f'Summary:')
    lines.append(f'  New functions     : {len(new_funcs)}')
    lines.append(f'  Updated functions : {len(updated_funcs)}')
    lines.append(f'  Unchanged         : {len(unchanged_funcs)}')
    lines.append('')

    if new_funcs:
        lines.append('-- NEW (no existing diagram) ' + '-' * 41)
        for d in new_funcs:
            lines.append(f'  + {d.func_name}')
        lines.append('')

    if updated_funcs:
        lines.append('-- UPDATED ' + '-' * 58)
        for d in updated_funcs:
            lines.append(f'  ~ {d.func_name}')
            for ch in d.changes:
                if ch.kind == 'added':
                    lines.append(f'      [+] step added    : {ch.step_name!r}')
                elif ch.kind == 'removed':
                    lines.append(f'      [-] step removed  : {ch.step_name!r}  (was {ch.old_value})')
                elif ch.kind == 'modified':
                    lines.append(f'      [~] type changed  : {ch.step_name!r}  {ch.old_value} -> {ch.new_value}')
        lines.append('')

    if unchanged_funcs:
        lines.append('-- UNCHANGED ' + '-' * 56)
        for d in unchanged_funcs:
            lines.append(f'  = {d.func_name}')
        lines.append('')

    lines.append('=' * 70)
    return '\n'.join(lines)


# ===========================================================================
# Core import function
# ===========================================================================

def import_c_file(
    c_path: str,
    diagrams_dir: str = _DEFAULT_DIAGRAMS_DIR,
    module_name: Optional[str] = None,
    dry_run: bool = False,
    function_filter: Optional[List[str]] = None,
) -> Tuple[List[FuncDiff], str]:
    """
    Parse *c_path*, compare against existing diagram XMLs, write updates,
    and return (list_of_FuncDiff, report_text).

    If *function_filter* is given only those function names are processed;
    all other parsed functions are silently ignored.
    """
    if not os.path.isfile(c_path):
        raise FileNotFoundError(c_path)

    # Derive module name from filename: SwMod_TouchSM.c → SwMod_TouchSM
    if module_name is None:
        basename = os.path.splitext(os.path.basename(c_path))[0]
        module_name = basename.split('_skeleton')[0]

    print(f'Parsing: {c_path}')
    graphs = parse_c_file(c_path)
    print(f'  Found {len(graphs)} function(s).')

    if function_filter:
        graphs = {k: v for k, v in graphs.items() if k in function_filter}
        print(f'  Filter applied: {len(graphs)} function(s) to process.')

    existing = _load_existing_diagrams(diagrams_dir, module_name)
    print(f'  Existing diagram entries: {len(existing)}')

    diffs: List[FuncDiff] = []
    # Track which XML paths will be modified
    # path → {'root', 'module_el', 'module_name', 'module_guid'}
    xml_updates: Dict[str, dict] = {}

    # Pre-determine a single "new functions" target file so all new functions
    # end up in ONE file rather than one file per function.
    all_existing_paths = sorted({p for p, _ in existing.values()})
    default_new_path = (all_existing_paths[0] if all_existing_paths
                        else _get_or_create_xml_path(
                            module_name, diagrams_dir,
                            {n: p for n, (p, _) in existing.items()}
                        ))

    for func_name, graph in sorted(graphs.items()):
        existing_entry   = existing.get(func_name)
        existing_func_el = existing_entry[1] if existing_entry else None
        existing_path    = existing_entry[0] if existing_entry else None

        diff = _diff_graph_vs_xml(graph, existing_func_el)
        diffs.append(diff)

        # Choose the target XML file
        target_path = existing_path if existing_path else default_new_path

        if target_path not in xml_updates:
            if os.path.isfile(target_path):
                try:
                    tree = ET.parse(target_path)
                    root = tree.getroot()
                    mod_el = root.find('Module')
                    xml_updates[target_path] = {
                        'root':        root,
                        'module_el':   mod_el,
                        'module_name': (mod_el.get('name') if mod_el else module_name),
                        'module_guid': (mod_el.get('guid') if mod_el else _new_guid()),
                    }
                except ET.ParseError:
                    pass

            if target_path not in xml_updates:
                root = ET.Element('SwDetailedDesignDiagrams')
                mod_el = ET.SubElement(root, 'Module',
                                       name=module_name,
                                       guid=_new_guid())
                xml_updates[target_path] = {
                    'root':        root,
                    'module_el':   mod_el,
                    'module_name': module_name,
                    'module_guid': mod_el.get('guid', ''),
                }

        mod_el = xml_updates[target_path]['module_el']

        existing_guids = _existing_step_guids(existing_func_el)
        func_guid      = (existing_func_el.get('guid') if existing_func_el else None) or _new_guid()
        stereotype     = (existing_func_el.get('stereotype') if existing_func_el else '') or ''
        diagram_guid   = (existing_func_el.get('diagramGuid')
                          if existing_func_el else '') or _new_guid()

        new_func_el = _graph_to_func_xml(
            graph, existing_guids, func_guid, stereotype, diagram_guid)

        if existing_func_el is not None and mod_el is not None:
            for idx, child in enumerate(list(mod_el)):
                if child.get('name') == func_name:
                    mod_el.remove(child)
                    mod_el.insert(idx, new_func_el)
                    break
        elif mod_el is not None:
            mod_el.append(new_func_el)

    if not dry_run:
        os.makedirs(diagrams_dir, exist_ok=True)
        for path, info in xml_updates.items():
            root = info['root']
            ET.indent(root, space='  ')
            _write_xml(root, path)
            print(f'  Written: {path}')

    report = format_report(diffs, c_path, dry_run)
    return diffs, report


# ===========================================================================
# CLI
# ===========================================================================

def _push_to_ea(
    processed_modules: Dict[str, str],
    diagrams_dir: str,
    function_filter: Optional[List[str]],
) -> None:
    """
    Connect to EA and import all modules whose XMLs were just written.

    Lazily imports ea_import_diagrams_from_xml so that win32com is only
    required when --push-to-ea is actually used.
    """
    import importlib.util
    import win32com.client

    # Load the sibling tool as a module
    _tool_path = os.path.join(_TOOL_DIR, 'ea_import_diagrams_from_xml.py')
    spec = importlib.util.spec_from_file_location('ea_import_diagrams_from_xml', _tool_path)
    _ea_imp = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(_ea_imp)  # type: ignore[union-attr]

    print('\n--- Pushing diagrams to Enterprise Architect ---')
    repo = None
    try:
        ea_app = win32com.client.GetActiveObject('EA.App')
        candidate = ea_app.Repository
        candidate.Models.Count   # smoke-test
        repo = candidate
        print('  Attached to running EA instance (via EA.App).')
    except Exception:
        pass

    if repo is None:
        try:
            from config.settings import EA_PROJECT  # noqa: E402
            repo = win32com.client.Dispatch('EA.Repository')
            repo.OpenFile(EA_PROJECT)
            print(f'  Opened project in new EA instance: {EA_PROJECT}')
        except Exception as exc:
            print(f'\nERROR: Cannot connect to EA: {exc}', file=sys.stderr)
            print('  Make sure Enterprise Architect is running with the project open,', file=sys.stderr)
            print('  and that you are using .venv32 (32-bit Python + pywin32).', file=sys.stderr)
            return

    for module_name, c_path in processed_modules.items():
        print(f'\nImporting {module_name} into EA ...')
        reports = _ea_imp.import_module(
            module_name=module_name,
            repo=repo,
            diagrams_dir=diagrams_dir,
            dry_run=False,
            function_filter=function_filter,
            source_file=c_path,
        )
        report_text = _ea_imp.format_report(reports, module_name, dry_run=False)
        print(report_text)


def main(argv: List[str]) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog='import_code_to_diagrams',
        description=(
            'Parse generated C source file(s) and create/update\n'
            'SwDetailedDesignDiagram XML activity diagram files.\n'
            'Optionally push the updated diagrams into EA via --push-to-ea.\n'
            'Generates a report of all changes made.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'sources',
        nargs='+',
        metavar='FILE_OR_DIR',
        help=(
            'One or more .c files, or a directory containing .c files. '
            'Example: ai_output/generated_c/SwMod_TouchSM.c'
        ),
    )
    parser.add_argument(
        '--diagrams', '-d',
        dest='diagrams_dir',
        metavar='DIR',
        default=None,
        help=(
            f'Directory containing/receiving diagram XML files '
            f'(default: {_DEFAULT_DIAGRAMS_DIR}).'
        ),
    )
    parser.add_argument(
        '--module', '-m',
        dest='module_name',
        metavar='NAME',
        default=None,
        help='Override module name (auto-detected from filename).',
    )
    parser.add_argument(
        '--report', '-r',
        dest='report_file',
        metavar='FILE',
        default=None,
        help='Write change report to FILE instead of stdout.',
    )
    parser.add_argument(
        '--functions', '-f',
        dest='functions',
        metavar='FUNC1,FUNC2',
        default=None,
        help=(
            'Comma-separated list of function names to restrict processing to. '
            'All other parsed functions are ignored. Useful for importing a '
            'single new function from a large source file.'
        ),
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        dest='dry_run',
        help='Parse and diff but do not write any XML files.',
    )
    parser.add_argument(
        '--push-to-ea',
        action='store_true',
        dest='push_to_ea',
        help=(
            'After writing diagram XMLs, automatically import them into '
            'Enterprise Architect via COM. EA must be running with the '
            'project open. Requires .venv32 (32-bit Python + pywin32). '
            'Ignored when --dry-run is set.'
        ),
    )

    args = parser.parse_args(argv[1:])
    diagrams_dir = args.diagrams_dir or _DEFAULT_DIAGRAMS_DIR
    function_filter = (
        [f.strip() for f in args.functions.split(',') if f.strip()]
        if args.functions else None
    )

    # Expand directories to .c files
    c_files: List[str] = []
    for src in args.sources:
        if os.path.isdir(src):
            c_files.extend(
                os.path.join(src, f)
                for f in sorted(os.listdir(src))
                if f.endswith('.c')
            )
        elif os.path.isfile(src):
            c_files.append(src)
        else:
            print(f'WARNING: not found: {src}', file=sys.stderr)

    if not c_files:
        print('ERROR: No .c files found.', file=sys.stderr)
        sys.exit(1)

    all_reports: List[str] = []
    # module_name -> c_path for successful conversions (used by --push-to-ea)
    processed_modules: Dict[str, str] = {}

    for c_path in c_files:
        # Derive module name the same way import_c_file() does
        _module = args.module_name
        if _module is None:
            _module = os.path.splitext(os.path.basename(c_path))[0].split('_skeleton')[0]

        try:
            _, report = import_c_file(
                c_path,
                diagrams_dir=diagrams_dir,
                module_name=args.module_name,
                dry_run=args.dry_run,
                function_filter=function_filter,
            )
            all_reports.append(report)
            print(report)
            if not args.dry_run:
                processed_modules[_module] = c_path
        except FileNotFoundError:
            print(f'ERROR: File not found: {c_path}', file=sys.stderr)
        except Exception as exc:
            print(f'ERROR processing {c_path}: {exc}', file=sys.stderr)
            import traceback
            traceback.print_exc()

    if args.report_file and all_reports:
        with open(args.report_file, 'w', encoding='utf-8') as fh:
            fh.write('\n\n'.join(all_reports))
        print(f'\nReport written to: {args.report_file}')

    if args.push_to_ea and not args.dry_run and processed_modules:
        _push_to_ea(processed_modules, diagrams_dir, function_filter)


if __name__ == '__main__':
    main(sys.argv)

