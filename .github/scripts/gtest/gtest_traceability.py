#!/usr/bin/env python3
"""
gtest_traceability.py — S3P GTest @Req_ID traceability tool

Analyzes and fixes @Req_ID annotations in GTest CPP files against
SwMod_[Module]_Functions.json (EA function export).

Three operations:
  --analyze     Parse CPP + JSON, write state JSON. Read-only.
  --fix         Analyze + auto-apply high-confidence + prompt for low-confidence.
  --apply FILE  Apply a (user-edited) state JSON to CPP files.

All operations support --dry-run to preview without writing.

Usage:
  python gtest_traceability.py --module AmbSTemp --fix
  python gtest_traceability.py --module AmbSTemp --analyze
  python gtest_traceability.py --module AmbSTemp --fix --dry-run
  python gtest_traceability.py --module AmbSTemp --apply ai_output/doc/SwMod_AmbSTemp_traceability_state.json
  python gtest_traceability.py --module AmbSTemp --fix --non-interactive   # CI mode
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

# ── Confidence thresholds ─────────────────────────────────────────────────────
CONFIDENCE_AUTO = 0.70   # >= this → auto-apply without prompting
CONFIDENCE_SHOW = 0.30   # >= this → show as candidate in interactive prompt

# ── Regex patterns ────────────────────────────────────────────────────────────
TOKEN_RE    = re.compile(r'([\w:<>&][\w:<>& ]*\w|[\w:<>&])\|\{([^}]+)\}')
REQ_ID_RE   = re.compile(r'@Req_ID\s*:\s*(.+)')
TEST_DECL_RE = re.compile(r'^\s*TEST(?:_F|_P)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)')


# ══════════════════════════════════════════════════════════════════════════════
# JSON loading
# ══════════════════════════════════════════════════════════════════════════════

def find_functions_json(project_root, module_name):
    """Search ai_output/doc/ for SwMod_<Module>_Functions.json (case-insensitive on module segment)."""
    for variant in ('Functions', 'functions'):
        for path in glob.glob(os.path.join(project_root, 'ai_output', 'doc', f'SwMod_*_{variant}.json')):
            stem = os.path.basename(path)
            m = re.match(rf'^SwMod_(.+?)_{variant}\.json$', stem)
            if m and m.group(1).lower() == module_name.lower():
                return path
    return None


def parse_functions_json(json_path):
    """Return (functions, classes, guid_lookup).

    functions:   {name.lower(): {name, trace_id, class_name, class_trace_id}}
    classes:     {name.lower(): {class_name, trace_id}}
    guid_lookup: {GUID.upper(): entry_from_functions}
    """
    with open(json_path, encoding='utf-8-sig') as f:
        data = json.load(f)

    functions   = {}
    classes     = {}
    guid_lookup = {}

    for cls in data.get('classes', []):
        cn = cls['class_name']
        ct = cls.get('trace_id', '')
        classes[cn.lower()] = {'class_name': cn, 'trace_id': ct}

        for fn in cls.get('functions', []):
            name = fn['name']
            tid  = fn['trace_id']
            entry = {'name': name, 'trace_id': tid,
                     'class_name': cn, 'class_trace_id': ct}
            functions[name.lower()] = entry

            guid_m = re.search(r'\{([^}]+)\}', tid)
            if guid_m:
                guid_lookup[guid_m.group(1).upper()] = entry

    return functions, classes, guid_lookup


# ══════════════════════════════════════════════════════════════════════════════
# CPP parsing
# ══════════════════════════════════════════════════════════════════════════════

def _extract_test_body(lines, start_idx):
    """Return the text between the first matching { } pair from start_idx."""
    depth   = 0
    started = False
    body    = []

    for line in lines[start_idx:]:
        for ch in line:
            if ch == '{':
                depth += 1
                started = True
            elif ch == '}':
                depth -= 1
        if started:
            if depth <= 0:
                break
            body.append(line)

    return ''.join(body)


def _parse_tokens(raw_list):
    """Parse ['FuncName|{GUID}', ...] into token dicts."""
    tokens = []
    for raw in raw_list:
        m = TOKEN_RE.match(raw.strip())
        if m:
            tokens.append({'name': m.group(1), 'guid': m.group(2).upper(),
                           'raw': raw.strip()})
        else:
            tokens.append({'name': raw.strip(), 'guid': None,
                           'raw': raw.strip(), 'malformed': True})
    return tokens


def parse_test_file(cpp_path):
    """Return list of test dicts from a GTest CPP file.

    Each dict:
      fixture, test_name, tokens, has_req_id, line (1-based),
      file, body, comment_start (1-based or None)
    """
    with open(cpp_path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    tests = []
    i = 0

    while i < len(lines):
        stripped = lines[i].rstrip()

        # ── Start of a multi-line Doxygen block ( /** ... */ )
        if '/**' in stripped and '*/' not in stripped:
            comment_start = i
            req_tokens_raw = []
            i += 1

            while i < len(lines):
                cl = lines[i].rstrip()
                rid_m = REQ_ID_RE.search(cl)
                if rid_m:
                    req_tokens_raw = [t.strip() for t in rid_m.group(1).split('&')
                                      if t.strip()]
                if '*/' in cl:
                    i += 1
                    break
                i += 1

            # Skip blank lines between comment and TEST declaration
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines):
                break

            test_m = TEST_DECL_RE.match(lines[i])
            if test_m:
                tests.append({
                    'fixture':       test_m.group(1),
                    'test_name':     test_m.group(2),
                    'tokens':        _parse_tokens(req_tokens_raw),
                    'has_req_id':    bool(req_tokens_raw),
                    'line':          i + 1,
                    'file':          cpp_path,
                    'body':          _extract_test_body(lines, i + 1),
                    'comment_start': comment_start + 1,  # 1-based
                })
                i += 1
            continue

        # ── TEST without a preceding Doxygen block
        test_m = TEST_DECL_RE.match(lines[i])
        if test_m:
            tests.append({
                'fixture':       test_m.group(1),
                'test_name':     test_m.group(2),
                'tokens':        [],
                'has_req_id':    False,
                'line':          i + 1,
                'file':          cpp_path,
                'body':          _extract_test_body(lines, i + 1),
                'comment_start': None,
            })

        i += 1

    return tests


# ══════════════════════════════════════════════════════════════════════════════
# Confidence scoring
# ══════════════════════════════════════════════════════════════════════════════

def _func_base_name(func_name, module_name):
    """Strip module prefix: AmbSTemp_vInit → vInit, AmbSTemp__vFoo → vFoo."""
    m = re.match(rf'^{re.escape(module_name)}_+(.+)$', func_name, re.IGNORECASE)
    return m.group(1) if m else func_name


def score_candidates(test_name, test_body, functions, module_name):
    """Return {func_name: {entry, confidence, signals}} for all candidates.

    Scoring:
      +0.80  test name starts with  Test_<FuncBase>_  or  Test_<FuncBase> (end)
      +0.50  function base name appears anywhere in test name
      +0.35  function name mentioned anywhere in test body (call or mock)
      +0.05  bonus when only one function scores above zero (sole candidate)
    """
    scored = []

    for fname, entry in functions.items():
        func_name = entry['name']
        fbase     = _func_base_name(func_name, module_name)
        score     = 0.0
        signals   = []

        # Signal 1a — strict prefix: Test_vInit_Scenario
        if re.match(rf'^Test_{re.escape(fbase)}(_|$)', test_name, re.IGNORECASE):
            score += 0.80
            signals.append(f'strict_prefix:{fbase}')
        # Signal 1b — base name anywhere in test name
        elif fbase.lower() in test_name.lower():
            score += 0.50
            signals.append(f'name_contains:{fbase}')

        # Signal 2 — function name in test body (direct call OR mock expectation)
        if re.search(rf'\b{re.escape(func_name)}\b', test_body):
            score += 0.35
            signals.append(f'body_ref:{func_name}')

        if score >= CONFIDENCE_SHOW:
            scored.append((func_name, score, signals, entry))

    # Sole-candidate bonus
    if len(scored) == 1:
        fn, sc, sig, ent = scored[0]
        scored = [(fn, min(sc + 0.05, 1.0), sig + ['sole_candidate'], ent)]

    return {
        fn: {'entry': ent, 'confidence': round(sc, 2), 'signals': sig}
        for fn, sc, sig, ent in scored
    }


# ══════════════════════════════════════════════════════════════════════════════
# Token validation
# ══════════════════════════════════════════════════════════════════════════════

def validate_token(token, functions, classes, guid_lookup):
    """Return (status, resolved_entry, suggested_new_trace_id).

    Status values:
      VALID         — name and GUID both match JSON
      GUID_MISMATCH — name found, GUID differs   → auto-update GUID
      NAME_MISMATCH — GUID found, name differs   → auto-update name
      STALE         — neither found              → needs human/AI review
    """
    name = token['name']
    guid = token.get('guid')

    entry = functions.get(name.lower()) or classes.get(name.lower())

    if entry:
        json_guid_m = re.search(r'\{([^}]+)\}', entry['trace_id'])
        json_guid   = json_guid_m.group(1).upper() if json_guid_m else None

        if guid and json_guid and guid != json_guid:
            return 'GUID_MISMATCH', entry, entry['trace_id']
        return 'VALID', entry, None

    # GUID reverse-lookup: function was renamed but GUID is still valid
    if guid and guid in guid_lookup:
        entry = guid_lookup[guid]
        return 'NAME_MISMATCH', entry, entry['trace_id']

    return 'STALE', None, None


# ══════════════════════════════════════════════════════════════════════════════
# Fixture inference
# ══════════════════════════════════════════════════════════════════════════════

def infer_fixture(target_class, all_tests, functions):
    """Return the most-used fixture among tests tracing functions of target_class.
    Falls back to the most-used fixture overall."""
    class_counts  = defaultdict(int)
    overall_counts = defaultdict(int)

    for test in all_tests:
        overall_counts[test['fixture']] += 1
        for tok in test['tokens']:
            entry = functions.get(tok['name'].lower())
            if entry and entry.get('class_name') == target_class:
                class_counts[test['fixture']] += 1

    if class_counts:
        return max(class_counts, key=class_counts.get)
    if overall_counts:
        return max(overall_counts, key=overall_counts.get)
    return 'TestFixture'


# ══════════════════════════════════════════════════════════════════════════════
# Full analysis
# ══════════════════════════════════════════════════════════════════════════════

def analyze(module_name, functions, classes, guid_lookup, all_tests):
    """Produce the state dict: outdated, untraced, stale, uncovered_functions."""
    outdated             = []
    untraced             = []
    stale_tokens         = []
    covered_func_names   = set()  # lower-case function names touched by any test

    for test in all_tests:
        file_rel = os.path.relpath(test['file']).replace('\\', '/')
        test_id  = f'{test["fixture"]}::{test["test_name"]}'

        if not test['has_req_id']:
            # ── Completely untraced test
            candidates = score_candidates(
                test['test_name'], test['body'], functions, module_name)
            auto   = {k: v for k, v in candidates.items()
                      if v['confidence'] >= CONFIDENCE_AUTO}
            manual = {k: v for k, v in candidates.items()
                      if v['confidence'] <  CONFIDENCE_AUTO}

            for k in auto:
                covered_func_names.add(k.lower())

            untraced.append({
                'test_id':        test_id,
                'fixture':        test['fixture'],
                'test_name':      test['test_name'],
                'file':           file_rel,
                'line':           test['line'],
                'proposals_auto': [
                    {'function': k, 'trace_id': v['entry']['trace_id'],
                     'confidence': v['confidence'], 'signals': v['signals']}
                    for k, v in auto.items()
                ],
                'proposals_manual': [
                    {'function': k, 'trace_id': v['entry']['trace_id'],
                     'confidence': v['confidence'], 'signals': v['signals']}
                    for k, v in manual.items()
                ],
                'auto_apply': bool(auto),
            })

        else:
            # ── Test has @Req_ID — validate each token
            token_updates = []
            for tok in test['tokens']:
                status, entry, replacement = validate_token(
                    tok, functions, classes, guid_lookup)

                if status == 'VALID':
                    if entry and 'name' in entry:
                        covered_func_names.add(entry['name'].lower())

                elif status in ('GUID_MISMATCH', 'NAME_MISMATCH'):
                    token_updates.append({
                        'old': tok['raw'],
                        'new': replacement,
                        'reason': status,
                        'auto_apply': True,
                    })
                    if entry and 'name' in entry:
                        covered_func_names.add(entry['name'].lower())

                else:  # STALE
                    stale_tokens.append({
                        'test_id': test_id,
                        'file':    file_rel,
                        'line':    test['line'],
                        'token':   tok['raw'],
                        'reason':  'NOT_IN_JSON',
                    })

            if token_updates:
                outdated.append({
                    'test_id':   test_id,
                    'fixture':   test['fixture'],
                    'test_name': test['test_name'],
                    'file':      file_rel,
                    'line':      test['line'],
                    'updates':   token_updates,
                })

    # ── Functions with no test coverage at all
    # Functions using SW Unit GUID fallback are considered covered at class
    # level -- no Activity Diagram exists in EA. They are flagged separately.
    uncovered = []
    no_activity_diagram = []
    GUID_RE = re.compile(r"\{([^}]+)\}")
    for fname, entry in functions.items():
        fn_m  = GUID_RE.search(entry["trace_id"])
        cls_m = GUID_RE.search(entry.get("class_trace_id", ""))
        is_fallback = (fn_m and cls_m and fn_m.group(1).upper() == cls_m.group(1).upper())
        if fname not in covered_func_names:
            if is_fallback:
                no_activity_diagram.append({
                    "function":   entry["name"],
                    "trace_id":   entry["trace_id"],
                    "class_name": entry["class_name"],
                })
            else:
                safe_base = _func_base_name(entry["name"], module_name)
                fixture   = infer_fixture(entry["class_name"], all_tests, functions)
                uncovered.append({
                    "function":            entry["name"],
                    "trace_id":            entry["trace_id"],
                    "class_name":          entry["class_name"],
                    "suggested_fixture":   fixture,
                    "suggested_test_name": f"Test_{safe_base}_Normal",
                })
    return {
        'module':               module_name,
        'outdated':             outdated,
        'untraced':             untraced,
        'stale':                stale_tokens,
        'uncovered_functions':  uncovered,
        'no_activity_diagram':  no_activity_diagram,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CPP file patching  (all edits are batched per file to preserve line numbers)
# ══════════════════════════════════════════════════════════════════════════════

def _build_req_id_line(trace_ids):
    return ' * @Req_ID: ' + ' & '.join(trace_ids)


class FilePatcher:
    """Collect all edits for one CPP file, then apply them bottom-to-top."""

    def __init__(self, path):
        self.path   = path
        self._edits = []  # list of (line_1based, action, data)

    def schedule_req_id_update(self, test_line_1based, new_trace_ids):
        """Replace or insert @Req_ID for the test at test_line_1based."""
        self._edits.append((test_line_1based, 'req_id', new_trace_ids))

    def schedule_stub_append(self, stub_text):
        """Append a test stub at the end of the file."""
        self._edits.append((None, 'append', stub_text))

    def apply(self, dry_run=False):
        """Apply all scheduled edits.  Returns list of human-readable change descriptions."""
        if not self._edits:
            return []

        with open(self.path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        descriptions = []

        # ── Process @Req_ID edits bottom-to-top (preserves line numbers)
        req_edits = [(ln, data) for ln, action, data in self._edits if action == 'req_id']
        req_edits.sort(key=lambda x: x[0], reverse=True)

        for test_line_1based, new_trace_ids in req_edits:
            idx = test_line_1based - 1  # 0-based TEST_F line

            # Walk back to find the end of the preceding comment block
            j = idx - 1
            while j >= 0 and not lines[j].strip():
                j -= 1

            new_line_text = _build_req_id_line(new_trace_ids) + '\n'

            if j >= 0 and lines[j].rstrip() == '*/':
                # Comment block exists — search it for an existing @Req_ID
                k = j - 1
                found = False
                while k >= 0 and '/**' not in lines[k]:
                    if REQ_ID_RE.search(lines[k]):
                        indent = re.match(r'^(\s*\*?\s*)', lines[k]).group(1)
                        lines[k] = indent.rstrip() + ' ' + new_line_text.lstrip()
                        descriptions.append(f'Updated @Req_ID at line {k+1}')
                        found = True
                        break
                    k -= 1

                if not found:
                    # Insert @Req_ID as first line after /**
                    open_idx = k  # line with /**
                    lines.insert(open_idx + 1, new_line_text)
                    descriptions.append(f'Inserted @Req_ID after /** at line {open_idx+1}')

            else:
                # No comment block — insert a minimal one before the TEST_F line
                block = [
                    '/**\n',
                    new_line_text,
                    ' * @Variant: S3P-DS\n',
                    ' * @Description: TODO\n',
                    ' * @FunctionSafety: No\n',
                    ' */\n',
                ]
                for offset, bline in enumerate(block):
                    lines.insert(idx + offset, bline)
                descriptions.append(f'Inserted comment block with @Req_ID before line {idx+1}')

        # ── Append stubs at end of file
        appends = [data for _, action, data in self._edits if action == 'append']
        for stub in appends:
            stub_with_newline = '\n\n' + stub + '\n'

            # Insert before the last closing namespace / } line
            insert_at = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                stripped = lines[i].strip()
                if stripped in ('}', '} // namespace') or re.match(r'^\}.*//.*namespace', stripped):
                    insert_at = i
                    break
            lines.insert(insert_at, stub_with_newline)
            descriptions.append('Appended test stub')

        if not dry_run:
            with open(self.path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

        return descriptions


# ══════════════════════════════════════════════════════════════════════════════
# Interactive prompt
# ══════════════════════════════════════════════════════════════════════════════

def prompt_user(test_id, proposals_manual):
    """Return list of selected trace_id strings, or [] to skip."""
    print(f'\n{"-" * 60}')
    print(f'NEEDS REVIEW: {test_id}')

    if proposals_manual:
        print('Low-confidence candidates:')
        for i, p in enumerate(proposals_manual, 1):
            print(f'  [{i}] {p["function"]}  '
                  f'(confidence {p["confidence"]:.0%}, '
                  f'signals: {", ".join(p["signals"])})')
    else:
        print('  No candidates found automatically.')

    print('\nOptions:')
    print('  Enter number(s) separated by space to select from the list above')
    print('  Enter  FuncA|{GUID} , FuncB|{GUID}  to specify tokens manually')
    print('  Press Enter to skip (leave untraced for now)')

    try:
        user_input = input('Your choice: ').strip()
    except (EOFError, KeyboardInterrupt):
        return []

    if not user_input:
        return []

    # Try numeric selection
    parts = user_input.split()
    selected_by_number = []
    all_numeric = True
    for part in parts:
        try:
            idx = int(part)
            if 1 <= idx <= len(proposals_manual):
                selected_by_number.append(proposals_manual[idx - 1]['trace_id'])
            else:
                all_numeric = False
                break
        except ValueError:
            all_numeric = False
            break

    if all_numeric and selected_by_number:
        return selected_by_number

    # Free-text token(s)
    return [t.strip() for t in user_input.split(',') if t.strip()]


# ══════════════════════════════════════════════════════════════════════════════
# Apply / fix
# ══════════════════════════════════════════════════════════════════════════════

def _test_lookup(all_tests):
    """Build index: (file_abs, test_name) → test dict."""
    return {(t['file'], t['test_name']): t for t in all_tests}


def _resolve_path(rel, test_files):
    """Find the absolute path in test_files that ends with rel."""
    rel_norm = rel.replace('\\', '/')
    for tf in test_files:
        if tf.replace('\\', '/').endswith(rel_norm):
            return tf
    return None


def _pick_best_file(test_files, class_name, all_tests, functions):
    """Choose the test file most associated with class_name."""
    counts = defaultdict(int)
    for test in all_tests:
        for tok in test['tokens']:
            entry = functions.get(tok['name'].lower())
            if entry and entry.get('class_name') == class_name:
                counts[test['file']] += 1
    if counts:
        return max(counts, key=counts.get)
    return test_files[0] if test_files else None


def run_fix(state, all_tests, functions, test_files, dry_run, non_interactive):
    """Build FilePatcher objects for all CPP files, schedule edits, then apply."""
    patchers  = {}   # abs_path → FilePatcher
    test_idx  = _test_lookup(all_tests)
    summary   = {'outdated_fixed': 0, 'traced': 0, 'skipped': 0}

    def get_patcher(path):
        if path not in patchers:
            patchers[path] = FilePatcher(path)
        return patchers[path]

    # ── 1. Fix outdated tokens (GUID_MISMATCH / NAME_MISMATCH) — always auto
    for item in state['outdated']:
        file_abs = _resolve_path(item['file'], test_files)
        if not file_abs:
            continue
        test = test_idx.get((file_abs, item['test_name']))
        if not test:
            continue

        # Build updated token list: replace old with new, keep rest unchanged
        tok_map = {tok['raw']: tok['raw'] for tok in test['tokens']}
        for upd in item['updates']:
            tok_map[upd['old']] = upd['new']

        new_ids = list(tok_map.values())
        get_patcher(file_abs).schedule_req_id_update(test['line'], new_ids)
        summary['outdated_fixed'] += 1
        reasons = ', '.join(u['reason'] for u in item['updates'])
        print(f'  {"[DRY]" if dry_run else "FIX "} outdated @Req_ID in '
              f'{item["test_name"]}  ({reasons})')

    # ── 2. Add @Req_ID to untraced tests
    for item in state['untraced']:
        file_abs = _resolve_path(item['file'], test_files)
        if not file_abs:
            continue
        test = test_idx.get((file_abs, item['test_name']))
        if not test:
            continue

        if item['auto_apply'] and item['proposals_auto']:
            new_ids = [p['trace_id'] for p in item['proposals_auto']]
            get_patcher(file_abs).schedule_req_id_update(test['line'], new_ids)
            summary['traced'] += 1
            funcs = ', '.join(p['function'] for p in item['proposals_auto'])
            print(f'  {"[DRY]" if dry_run else "ADD "} @Req_ID to '
                  f'{item["test_name"]}  -> {funcs}')

        elif not non_interactive:
            chosen = prompt_user(item['test_id'], item['proposals_manual'])
            if chosen:
                get_patcher(file_abs).schedule_req_id_update(test['line'], chosen)
                summary['traced'] += 1
                print(f'  {"[DRY]" if dry_run else "ADD "} @Req_ID to '
                      f'{item["test_name"]}  (user selection)')
            else:
                summary['skipped'] += 1
                print(f'  SKIP {item["test_id"]}')
        else:
            summary['skipped'] += 1
            print(f'  SKIP {item["test_id"]}  (low confidence, non-interactive)')

    # ── Apply all patchers
    for path, patcher in patchers.items():
        descs = patcher.apply(dry_run=dry_run)
        if descs and dry_run:
            for d in descs:
                print(f'       would: {d}  ({os.path.basename(path)})')

    return summary


# ══════════════════════════════════════════════════════════════════════════════
# Project helpers
# ══════════════════════════════════════════════════════════════════════════════

def find_project_root():
    """Walk up from cwd looking for a .github directory."""
    p = os.getcwd()
    while p != os.path.dirname(p):
        if os.path.isdir(os.path.join(p, '.github')):
            return p
        p = os.path.dirname(p)
    return os.getcwd()


def find_tests_dir(project_root, module_name):
    """Search pkg/ for a test/gtest/tests directory under a folder named module_name."""
    for d in glob.glob(os.path.join(project_root, 'pkg', '**', 'test', 'gtest', 'tests'),
                       recursive=True):
        parts = d.replace('\\', '/').split('/')
        if any(p.lower() == module_name.lower() for p in parts):
            return d
    return None


def print_summary_table(state):
    auto_count   = sum(1 for u in state['untraced'] if u['auto_apply'])
    manual_count = sum(1 for u in state['untraced'] if not u['auto_apply'])
    SEP = '=' * 60
    print(f'\n{SEP}')
    print(f'  Module                  : {state["module"]}')
    print(f'  Outdated @Req_IDs       : {len(state["outdated"])}  (auto-fix)')
    print(f'  Untraced -- auto-apply  : {auto_count}')
    print(f'  Untraced -- needs review: {manual_count}')
    print(f'  Stale tokens            : {len(state["stale"])}  (needs human review)')
    print(f'  Uncovered functions     : {len(state["uncovered_functions"])}  (test cases needed)')
    no_act = state.get('no_activity_diagram', [])
    if no_act:
        print(f'  No Activity Diagram     : {len(no_act)}  (SW Unit fallback -- covered)')
    print(f'{SEP}')


# ══════════════════════════════════════════════════════════════════════════════
# Report generation (Markdown / HTML)
# ══════════════════════════════════════════════════════════════════════════════

def _esc_md(s):
    """Escape Markdown special chars in table cells."""
    return str(s).replace('|', '\\|').replace('`', "'")


def _esc_html(s):
    """Escape HTML special chars."""
    return (str(s)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def generate_report(state, summary, report_path, dry_run=False):
    """Write a detailed traceability report.

    Format is determined by the file extension of *report_path*:
      .html  → HTML report
      .md    → Markdown report  (default / fallback)
    """
    import datetime
    module    = state['module']
    now       = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    outdated  = state['outdated']
    untraced  = state['untraced']
    stale     = state['stale']
    uncovered = state['uncovered_functions']
    no_activity = state.get('no_activity_diagram', [])
    auto_count   = sum(1 for u in untraced if u['auto_apply'])
    manual_count = sum(1 for u in untraced if not u['auto_apply'])

    fmt = 'html' if report_path.lower().endswith('.html') else 'md'

    if fmt == 'md':
        lines = []
        lines.append(f'# Traceability Report — {module}')
        lines.append(f'')
        lines.append(f'**Generated:** {now}  ')
        lines.append(f'**Mode:** {"DRY RUN (no files written)" if dry_run else "applied"}  ')
        lines.append(f'')
        lines.append(f'## Summary')
        lines.append(f'')
        lines.append(f'| Category | Count | Action |')
        lines.append(f'|----------|------:|--------|')
        lines.append(f'| Outdated @Req_IDs (GUID mismatch) | {len(outdated)} | Auto-fixed |')
        lines.append(f'| Untraced — auto-applied | {auto_count} | @Req_ID added |')
        lines.append(f'| Untraced — needs review | {manual_count} | Manual action needed |')
        lines.append(f'| Stale tokens | {len(stale)} | Manual review needed |')
        lines.append(f'| Uncovered functions | {len(uncovered)} | Test cases required |')
        lines.append(f'| No Activity Diagram (SW Unit fallback) | {len(no_activity)} | Considered covered |')
        lines.append(f'')

        # ── Outdated
        if outdated:
            lines.append(f'## Outdated @Req_IDs ({len(outdated)} tests)')
            lines.append(f'')
            lines.append(f'These tests had a valid function name but an outdated GUID — auto-fixed.')
            lines.append(f'')
            lines.append(f'| Test | File | Line | Old Token | New Token | Reason |')
            lines.append(f'|------|------|-----:|-----------|-----------|--------|')
            for item in outdated:
                fname = _esc_md(os.path.basename(item['file']))
                for upd in item['updates']:
                    lines.append(
                        f'| `{_esc_md(item["test_name"])}` '
                        f'| {fname} | {item["line"]} '
                        f'| `{_esc_md(upd["old"])}` '
                        f'| `{_esc_md(upd["new"])}` '
                        f'| {upd["reason"]} |'
                    )
            lines.append(f'')

        # ── Untraced auto
        auto_items = [u for u in untraced if u['auto_apply']]
        if auto_items:
            lines.append(f'## Untraced Tests — Auto-applied ({len(auto_items)})')
            lines.append(f'')
            lines.append(f'@Req_ID was missing; confidence ≥ 0.70 so it was added automatically.')
            lines.append(f'')
            lines.append(f'| Test | File | Line | Added @Req_ID | Confidence |')
            lines.append(f'|------|------|-----:|--------------|------------|')
            for item in auto_items:
                fname = _esc_md(os.path.basename(item['file']))
                for p in item.get('proposals_auto', []):
                    lines.append(
                        f'| `{_esc_md(item["test_name"])}` '
                        f'| {fname} | {item["line"]} '
                        f'| `{_esc_md(p["function"])}` '
                        f'| {p["confidence"]:.2f} |'
                    )
            lines.append(f'')

        # ── Untraced manual
        manual_items = [u for u in untraced if not u['auto_apply']]
        if manual_items:
            lines.append(f'## Untraced Tests — Needs Review ({len(manual_items)})')
            lines.append(f'')
            lines.append(f'Confidence < 0.70; could not auto-apply. Manual @Req_ID annotation required.')
            lines.append(f'')
            lines.append(f'| Test | File | Line | Candidates |')
            lines.append(f'|------|------|-----:|------------|')
            for item in manual_items:
                fname = _esc_md(os.path.basename(item['file']))
                cands = ', '.join(
                    f'`{_esc_md(p["function"])}` ({p["confidence"]:.2f})'
                    for p in item.get('proposals_review', [])
                )
                lines.append(
                    f'| `{_esc_md(item["test_name"])}` '
                    f'| {fname} | {item["line"]} '
                    f'| {cands or "—"} |'
                )
            lines.append(f'')

        # ── Stale
        if stale:
            lines.append(f'## Stale Tokens ({len(stale)} — Manual Review Required)')
            lines.append(f'')
            lines.append(
                f'> **What is a stale token?**  \n'
                f'> A `@Req_ID` token whose function name **and** GUID are both absent from  \n'
                f'> `SwMod_{module}_Functions.json`. The design element was likely deleted or  \n'
                f'> renamed in the EA model. These cannot be auto-fixed — a developer must  \n'
                f'> either replace the token with the correct function name from the JSON,  \n'
                f'> or remove it if the function no longer exists in the design.'
            )
            lines.append(f'')
            lines.append(f'| Test | File | Line | Stale Token |')
            lines.append(f'|------|------|-----:|-------------|')
            for item in stale:
                fname = _esc_md(os.path.basename(item['file']))
                lines.append(
                    f'| `{_esc_md(item["test_id"])}` '
                    f'| {fname} | {item["line"]} '
                    f'| `{_esc_md(item["token"])}` |'
                )
            lines.append(f'')

        # ── Uncovered functions
        if uncovered:
            lines.append(f'## Uncovered Functions ({len(uncovered)} — Test Cases Required)')
            lines.append(f'')
            lines.append(
                f'> \u26a0\ufe0f No test has a `@Req_ID` linking to these functions.  \n'
                f'> Please create proper test cases for each function and annotate them with the correct `@Req_ID` token.  \n'
                f'> Do **NOT** add placeholder `GTEST_SKIP()` stubs \u2014 implement real tests.'
            )
            lines.append(f'')
            lines.append(f'| # | Function | Class | Trace ID | Action Required |')
            lines.append(f'|---|----------|-------|----------|-----------------|')
            for i, fn in enumerate(uncovered, 1):
                lines.append(
                    f'| {i} '
                    f'| `{_esc_md(fn["function"])}` '
                    f'| {_esc_md(fn["class_name"])} '
                    f'| `{_esc_md(fn["trace_id"])}` '
                    f'| \u26a0\ufe0f Create test case(s) |'
                )
            lines.append(f'')


        # ── No Activity Diagram (SW Unit fallback -- covered)
        if no_activity:
            lines.append(f'## No Activity Diagram -- SW Unit Fallback ({len(no_activity)} -- Considered Covered)')
            lines.append(f'')
            lines.append(
                f'> &#x2139;&#xFE0F; These functions have no Activity Diagram in EA.  \n'
                f'> Their @Req_ID falls back to the SW Unit Class GUID.  \n'
                f'> They are **considered covered** -- no additional test cases required.'
            )
            lines.append(f'')
            lines.append(f'| # | Function | Class | Trace ID |')
            lines.append(f'|---|----------|-------|----------|')
            for i, fn in enumerate(no_activity, 1):
                lines.append(
                    f'| {i} '
                    f'| `{_esc_md(fn["function"])}` '
                    f'| {_esc_md(fn["class_name"])} '
                    f'| `{_esc_md(fn["trace_id"])}` |'
                )
            lines.append(f'')
        content = '\n'.join(lines)

    else:  # HTML
        def th(cols):
            return '<tr>' + ''.join(f'<th>{c}</th>' for c in cols) + '</tr>'

        def td_row(cells):
            return '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'

        css = (
            'body{font-family:sans-serif;margin:2em;color:#222}'
            'h1{color:#1a4a8a}h2{color:#1a4a8a;border-bottom:2px solid #1a4a8a;padding-bottom:4px}'
            'table{border-collapse:collapse;width:100%;margin-bottom:1.5em}'
            'th{background:#1a4a8a;color:#fff;padding:6px 10px;text-align:left}'
            'td{padding:5px 10px;border:1px solid #ccc;vertical-align:top}'
            'tr:nth-child(even){background:#f5f7fa}'
            'code{background:#eef;padding:1px 4px;border-radius:3px;font-size:.9em}'
            '.badge-ok{background:#2e7d32;color:#fff;border-radius:4px;padding:2px 7px;font-size:.85em}'
            '.badge-warn{background:#e65100;color:#fff;border-radius:4px;padding:2px 7px;font-size:.85em}'
            '.badge-info{background:#1565c0;color:#fff;border-radius:4px;padding:2px 7px;font-size:.85em}'
            '.badge-stale{background:#6a1a6a;color:#fff;border-radius:4px;padding:2px 7px;font-size:.85em}'
            'blockquote{background:#fff8e1;border-left:4px solid #f9a825;padding:.6em 1em;margin:0 0 1em}'
        )

        def summary_badge(count, label, cls):
            return (f'<span class="badge-{cls}">{count}</span> {label}')

        body_parts = []
        body_parts.append(f'<h1>Traceability Report &mdash; {_esc_html(module)}</h1>')
        body_parts.append(f'<p><strong>Generated:</strong> {now} &nbsp; '
                          f'<strong>Mode:</strong> {"DRY RUN (no files written)" if dry_run else "applied"}</p>')

        # summary table
        body_parts.append('<h2>Summary</h2>')
        body_parts.append('<table>')
        body_parts.append(th(['Category', 'Count', 'Action']))
        rows = [
            (f'{len(outdated)}', 'Outdated @Req_IDs (GUID mismatch)', 'Auto-fixed', 'ok'),
            (f'{auto_count}',   'Untraced — auto-applied',           '@Req_ID added', 'ok'),
            (f'{manual_count}', 'Untraced — needs review',           'Manual action needed', 'warn'),
            (f'{len(stale)}',   'Stale tokens',                      'Manual review needed', 'stale'),
            (f'{len(uncovered)}','Uncovered functions',               'Test cases required',     'warn'),
            (f'{len(no_activity)}','No Activity Diagram (SW Unit fallback)', 'Considered covered', 'info'),
        ]
        for cnt, cat, act, cls in rows:
            body_parts.append(
                f'<tr><td>{cat}</td>'
                f'<td><span class="badge-{cls}">{cnt}</span></td>'
                f'<td>{act}</td></tr>'
            )
        body_parts.append('</table>')

        # ── Outdated
        if outdated:
            body_parts.append(f'<h2>Outdated @Req_IDs ({len(outdated)} tests)</h2>')
            body_parts.append('<p>These tests had a valid function name but an outdated GUID &mdash; auto-fixed.</p>')
            body_parts.append('<table>')
            body_parts.append(th(['Test', 'File', 'Line', 'Old Token', 'New Token', 'Reason']))
            for item in outdated:
                fname = _esc_html(os.path.basename(item['file']))
                for upd in item['updates']:
                    body_parts.append(td_row([
                        f'<code>{_esc_html(item["test_name"])}</code>',
                        fname, str(item['line']),
                        f'<code>{_esc_html(upd["old"])}</code>',
                        f'<code>{_esc_html(upd["new"])}</code>',
                        upd['reason'],
                    ]))
            body_parts.append('</table>')

        # ── Untraced auto
        if auto_items:
            body_parts.append(f'<h2>Untraced Tests &mdash; Auto-applied ({len(auto_items)})</h2>')
            body_parts.append('<p>@Req_ID was missing; confidence &ge; 0.70 so it was added automatically.</p>')
            body_parts.append('<table>')
            body_parts.append(th(['Test', 'File', 'Line', 'Added @Req_ID', 'Confidence']))
            for item in auto_items:
                fname = _esc_html(os.path.basename(item['file']))
                for p in item.get('proposals_auto', []):
                    body_parts.append(td_row([
                        f'<code>{_esc_html(item["test_name"])}</code>',
                        fname, str(item['line']),
                        f'<code>{_esc_html(p["function"])}</code>',
                        f'{p["confidence"]:.2f}',
                    ]))
            body_parts.append('</table>')

        # ── Untraced manual
        if manual_items:
            body_parts.append(f'<h2>Untraced Tests &mdash; Needs Review ({len(manual_items)})</h2>')
            body_parts.append('<p>Confidence &lt; 0.70; manual @Req_ID annotation required.</p>')
            body_parts.append('<table>')
            body_parts.append(th(['Test', 'File', 'Line', 'Candidates']))
            for item in manual_items:
                fname = _esc_html(os.path.basename(item['file']))
                cands = ', '.join(
                    f'<code>{_esc_html(p["function"])}</code> ({p["confidence"]:.2f})'
                    for p in item.get('proposals_review', [])
                )
                body_parts.append(td_row([
                    f'<code>{_esc_html(item["test_name"])}</code>',
                    fname, str(item['line']),
                    cands or '&mdash;',
                ]))
            body_parts.append('</table>')

        # ── Stale
        if stale:
            body_parts.append(f'<h2>Stale Tokens ({len(stale)} &mdash; Manual Review Required)</h2>')
            body_parts.append(
                '<blockquote><strong>What is a stale token?</strong><br>'
                f'A <code>@Req_ID</code> token whose function name <em>and</em> GUID are both absent from '
                f'<code>SwMod_{_esc_html(module)}_Functions.json</code>. The design element was likely deleted or '
                'renamed in the EA model. These cannot be auto-fixed &mdash; a developer must either replace the '
                'token with the correct function name from the JSON, or remove it if the function no longer exists '
                'in the design.</blockquote>'
            )
            body_parts.append('<table>')
            body_parts.append(th(['Test', 'File', 'Line', 'Stale Token']))
            for item in stale:
                fname = _esc_html(os.path.basename(item['file']))
                body_parts.append(td_row([
                    f'<code>{_esc_html(item["test_id"])}</code>',
                    fname, str(item['line']),
                    f'<code>{_esc_html(item["token"])}</code>',
                ]))
            body_parts.append('</table>')

        # ── Uncovered functions
        if uncovered:
            body_parts.append(f'<h2>Uncovered Functions ({len(uncovered)} &mdash; Test Cases Required)</h2>')
            body_parts.append(
                '<blockquote>&#x26A0;&#xFE0F; No test has a <code>@Req_ID</code> linking to these functions. '
                'Please create proper test cases for each function and annotate them with the correct '
                '<code>@Req_ID</code> token. Do <strong>NOT</strong> add placeholder '
                '<code>GTEST_SKIP()</code> stubs &mdash; implement real tests.</blockquote>'
            )
            body_parts.append('<table>')
            body_parts.append(th(['#', 'Function', 'Class', 'Trace ID', 'Action Required']))
            for i, fn in enumerate(uncovered, 1):
                body_parts.append(td_row([
                    str(i),
                    f'<code>{_esc_html(fn["function"])}</code>',
                    _esc_html(fn['class_name']),
                    f'<code>{_esc_html(fn["trace_id"])}</code>',
                    '&#x26A0;&#xFE0F; Create test case(s)',
                ]))
            body_parts.append('</table>')


        # -- No Activity Diagram (SW Unit fallback -- covered)
        if no_activity:
            body_parts.append(f'<h2>No Activity Diagram -- SW Unit Fallback ({len(no_activity)} -- Considered Covered)</h2>')
            body_parts.append(
                '<blockquote>&#x2139;&#xFE0F; These functions have no Activity Diagram in EA. '
                'Their <code>@Req_ID</code> falls back to the SW Unit Class GUID. '
                'They are <strong>considered covered</strong> -- no additional test cases required.</blockquote>'
            )
            body_parts.append('<table>')
            body_parts.append(th(['#', 'Function', 'Class', 'Trace ID']))
            for i, fn in enumerate(no_activity, 1):
                body_parts.append(td_row([
                    str(i),
                    f'<code>{_esc_html(fn["function"])}</code>',
                    _esc_html(fn['class_name']),
                    f'<code>{_esc_html(fn["trace_id"])}</code>',
                ]))
            body_parts.append('</table>')
        content = (
            f'<!DOCTYPE html><html lang="en"><head>'
            f'<meta charset="UTF-8">'
            f'<title>Traceability Report — {_esc_html(module)}</title>'
            f'<style>{css}</style>'
            f'</head><body>'
            + '\n'.join(body_parts) +
            f'</body></html>'
        )

    if dry_run:
        print(f'[DRY RUN] Report would be written to: {report_path}')
        return

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Report   -> {report_path}')


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='S3P GTest @Req_ID traceability tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)

    parser.add_argument('--module',   required=True,
                        help='Module name, e.g. AmbSTemp')
    parser.add_argument('--json',     dest='json_path',
                        help='Path to SwMod_[Module]_Functions.json (auto-detected)')
    parser.add_argument('--tests-dir', dest='tests_dir',
                        help='Path to test/gtest/tests/ (auto-detected)')

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--analyze', action='store_true',
                      help='Parse + write state JSON, no changes to CPP files')
    mode.add_argument('--fix',     action='store_true',
                      help='Analyze + auto-apply high-confidence + prompt for rest')
    mode.add_argument('--apply',   metavar='STATE_JSON',
                      help='Apply a (possibly user-edited) state JSON to CPP files')

    parser.add_argument('--dry-run',         action='store_true',
                        help='Preview all changes without writing any files')
    parser.add_argument('--out',
                        help='State JSON output path '
                             '(default: ai_output/doc/SwMod_<Module>_traceability_state.json)')
    parser.add_argument('--non-interactive', action='store_true',
                        help='Skip interactive prompts — CI/batch mode')
    parser.add_argument('--report', metavar='PATH',
                        help='Write a detailed report to PATH (.md or .html). '
                             'Defaults to ai_output/<Module>/traceability/SwMod_<Module>_traceability_report.md '
                             'when --report is given without a value.',
                        nargs='?', const='auto')

    args = parser.parse_args()

    project_root = find_project_root()
    print(f'Project root: {project_root}')

    # ── Locate functions JSON
    json_path = args.json_path or find_functions_json(project_root, args.module)
    if not json_path or not os.path.isfile(json_path):
        print(f'\nERROR: SwMod_{args.module}_Functions.json not found in ai_output/doc/')
        print(f'       Generate it first:')
        print(f'       & ".venv32\\python.exe" .github/scripts/ea/export_module_functions.py '
              f'SwMod_{args.module}')
        sys.exit(1)

    functions, classes, guid_lookup = parse_functions_json(json_path)
    print(f'JSON : {json_path}')
    print(f'       {len(functions)} functions in {len(classes)} classes')

    # ── Locate test files
    if args.apply:
        with open(args.apply, encoding='utf-8') as f:
            state = json.load(f)
        print(f'State: {args.apply}')
    tests_dir = args.tests_dir or find_tests_dir(project_root, args.module)
    if not tests_dir:
        print(f'\nERROR: test/gtest/tests/ not found for module {args.module}')
        print(f'       Provide --tests-dir explicitly')
        sys.exit(1)

    test_files = sorted(glob.glob(os.path.join(tests_dir, '*.cpp')))
    if not test_files:
        print(f'\nERROR: No *.cpp files found in {tests_dir}')
        sys.exit(1)

    all_tests = []
    for tf in test_files:
        all_tests.extend(parse_test_file(tf))

    print(f'Tests: {tests_dir}')
    print(f'       {len(test_files)} file(s), {len(all_tests)} test cases')

    # ── Analyze (always needed for --fix and --analyze)
    if not args.apply:
        state = analyze(args.module, functions, classes, guid_lookup, all_tests)

    print_summary_table(state)

    # ── Write state JSON
    out_path = args.out or os.path.join(
        project_root, 'ai_output', 'doc',
        f'SwMod_{args.module}_traceability_state.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
    print(f'\nState JSON -> {out_path}')

    if args.analyze:
        print('Analyze-only mode.  Run --fix to apply changes.')
        if args.report:
            if args.report == 'auto':
                report_path = os.path.join(
                    project_root, 'ai_output', args.module, 'traceability',
                    f'SwMod_{args.module}_traceability_report.md')
            else:
                report_path = args.report
            generate_report(state, {}, report_path, dry_run=args.dry_run)
        return

    # ── Apply fixes
    label = '[DRY RUN] ' if args.dry_run else ''
    print(f'\n{label}Applying fixes...\n{"-" * 60}')

    summary = run_fix(
        state, all_tests, functions, test_files,
        dry_run=args.dry_run,
        non_interactive=args.non_interactive,
    )

    print(f'\n{"-" * 60}')
    print(f'Results{" (DRY RUN - no files written)" if args.dry_run else ""}:')
    print(f'  Outdated @Req_IDs fixed : {summary["outdated_fixed"]}')
    print(f'  @Req_IDs added          : {summary["traced"]}')
    print(f'  Skipped (need review)   : {summary["skipped"]}')
    no_act = state.get('no_activity_diagram', [])
    if no_act:
        print('\nINFO: %d function(s) use SW Unit GUID fallback (no Activity Diagram in EA):' % len(no_act))
        for fn in no_act:
            print(f'  ~~  {fn["function"]}  [{fn["trace_id"]}]')
    if state['uncovered_functions']:
        print(f'\nWARNING: {len(state["uncovered_functions"])} function(s) have no @Req_ID link:')
        for fn in state['uncovered_functions']:
            print(f'  \u26a0\ufe0f  {fn["function"]}  [{fn["trace_id"]}]')
        print('  Please create proper test cases and annotate with the correct @Req_ID token.')

    if state['stale']:
        print(f'\nWARNING: {len(state["stale"])} stale token(s) require manual review:')
        for s in state['stale']:
            print(f'  {s["test_id"]}  token: {s["token"]}')

    # -- Optional report
    if args.report:
        if args.report == 'auto':
            report_path = os.path.join(
                project_root, 'ai_output', args.module, 'traceability',
                f'SwMod_{args.module}_traceability_report.md')
        else:
            report_path = args.report
        generate_report(state, summary, report_path, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
