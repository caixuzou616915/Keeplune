---
name: s3p-mts-traceability
description: "S3P function-level MTS traceability: checks if SwMod_[Module]_functions.json exists (generates via enterprise-architect skill if missing), validates that every GTest test case has a @Req_ID annotation linking to function trace IDs from the JSON, produces a Markdown coverage report showing which functions and test cases are linked or unlinked, and reports uncovered functions to the user for proper test case creation."
argument-hint: "<MODULE_NAME> -- e.g. AmbSTemp, TouchSM, VidCtlSM"
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# S3P MTS Traceability Skill

Bridges the EA function export JSON (`SwMod_[Module]_functions.json`) with GTest unit test `@Req_ID` annotations to produce a full traceability coverage report.

## Primary Tool

All analysis, fixing, and stub generation is handled by a single Python script:

```
.github/scripts/gtest/gtest_traceability.py
```

**Modes:**

| Command | Effect |
|---------|--------|
| `--analyze` | Parse CPP + JSON, write `SwMod_[Module]_traceability_state.json`. Read-only. |
| `--fix` | Analyze + auto-apply high-confidence + interactive prompt for low-confidence |
| `--apply FILE` | Apply a user-edited state JSON to CPP files |
| `--dry-run` | Preview all changes without writing any files (combine with any mode) |
| `--non-interactive` | Skip prompts — for CI/batch use |

**Quick start:**

```bash
# See what would change (safe preview)
python .github/scripts/gtest/gtest_traceability.py --module AmbSTemp --fix --dry-run

# Fix everything: outdated IDs, missing @Req_ID, generate stubs for uncovered functions
python .github/scripts/gtest/gtest_traceability.py --module AmbSTemp --fix

# Analyze only, then edit the JSON, then apply
python .github/scripts/gtest/gtest_traceability.py --module AmbSTemp --analyze
# ... edit ai_output/doc/SwMod_AmbSTemp_traceability_state.json ...
python .github/scripts/gtest/gtest_traceability.py --module AmbSTemp --apply ai_output/doc/SwMod_AmbSTemp_traceability_state.json
```

## When to Use
- Verifying that every test case traces back to a known function via `@Req_ID`
- Checking which functions have no test coverage in the `@Req_ID` links
- Ensuring GUIDs in `@Req_ID` annotations match actual function trace IDs from the EA export
- Generating a traceability report for ASPICE / MTS compliance
- After adding new test cases — confirm they are correctly annotated
- Before a release — audit full module test traceability

## Inputs

| Input | CLI flag | Description |
|-------|----------|-------------|
| `MODULE_NAME` | `--module` | Module name without `SwMod_` prefix. Case-insensitive. E.g. `AmbSTemp`, `TouchSM` |
| `TESTS_DIR` | `--tests-dir` | Path to the `test/gtest/tests/` folder. Auto-detected under `pkg/` if omitted |
| `JSON_PATH` | `--json` | Explicit path to `SwMod_[Module]_Functions.json`. Auto-detected from `ai_output/doc/` if omitted |
| `--out` | `--out` | State JSON output path. Defaults to `ai_output/doc/SwMod_[Module]_traceability_state.json` |

Typical auto-detected locations:
```
ai_output/doc/SwMod_AmbSTemp_Functions.json
pkg/em_s3p_hud/ambientsense/ambstemp/test/gtest/tests/unittest_ambstemp_pf_test.cpp
```

---

## Trace ID Assignment Rules

These rules apply whenever the agent **creates**, **edits**, or **validates** a `trace_id` field
in `SwMod_[Module]_Functions.json` or a `@Req_ID` annotation in a GTest file.
Following these rules is **mandatory** — wrong GUIDs break traceability links.

### Rule 1 — Activity Diagram GUID (primary, preferred)

A function's `trace_id` **must** be the GUID of the **EA Activity Diagram** that describes the
function's detailed behaviour:

```
FunctionName|{ActivityDiagramGUID}
```

The activity diagram GUID is what `export_module_functions.py` writes when an activity diagram
exists in the EA model for that function.

### Rule 2 — Parent Class (SW Unit) fallback

If **no activity diagram exists** for the function in the EA model, use the **parent class
(SW unit) `trace_id`** verbatim as the function's `trace_id`.
Copy the class `trace_id` value as-is into the function's `trace_id` field:

```json
{
  "class_name": "VidConD_ErrorMonitoring",
  "trace_id": "VidConD_ErrorMonitoring|{8B32748B-AC1B-4a86-87C9-B2345DD11026}",
  "functions": [
    {
      "name": "VidConD_ErrMon__vInit",
      "trace_id": "VidConD_ErrorMonitoring|{8B32748B-AC1B-4a86-87C9-B2345DD11026}"
    }
  ]
}
```

### Rule 3 — Forbidden GUIDs (NEVER use)

| Forbidden source | Why |
|---|---|
| EA **Operation** element GUID (class method entry in EA) | Not a traceable design artefact |
| EA **Action** node GUID (call-action node *inside* an activity diagram) | Belongs to the diagram flow, not the function spec |
| Any other EA object GUID (component, port, connector, note, requirement…) | Creates wrong traceability link |

> **Key distinction:** An Activity Diagram GUID (Rule 1) is the GUID of the *diagram container*
> that specifies the function's behaviour. An **Action** GUID is the GUID of a *node inside* a
> diagram — a different EA element with a different GUID. Using an Action GUID instead of the
> diagram GUID creates a false traceability link.

### Rule 4 — Functions Pending EA Update

When a function exists in code but has no EA activity diagram yet (new class not yet modelled),
use this provisional pattern and mark it explicitly:

```json
{
  "name": "MyModule_NewFunction",
  "trace_id": "ParentClassName|{PARENT_CLASS_GUID} [PENDING_EA_UPDATE]"
}
```

The `[PENDING_EA_UPDATE]` marker signals that the trace_id is provisional. Replace it with the
real activity diagram GUID once the EA model is updated and `export_module_functions.py` re-run.

### Rule 5 — GUID Validation Check

When building or reviewing the JSON, validate each function entry's GUID:

1. Extract the GUID from the `trace_id` field.
2. Check whether the same GUID appears as the `trace_id` of an **Action-level** entry
   (e.g. in a `VidConD_Behavior`-style class that holds activity diagram action nodes).
   If yes → it is an **Action GUID** → Rule 3 violation → do **not** use it.
3. If the GUID only appears as a class-level `trace_id` → it is a **Class GUID** →
   acceptable only as the Rule 2 fallback.
4. If the GUID does not appear elsewhere in the JSON → expected **Activity Diagram GUID**
   → valid for Rule 1.

### Rule 6 -- Trace ID Format in Markdown Files

When generating or writing `doc/SwMod_[Module].md`, trace IDs in table cells
**must use an unescaped `|`** -- never backslash-escaped:

**Valid:**   `FunctionName|{GUID}`
**Invalid:** `FunctionName\|{GUID}`  (backslash NOT needed, breaks re-parsing)

When generating the Markdown, write the trace_id directly from the JSON without escaping:

```python
# Correct -- do NOT escape the pipe
trace_cell = fn["trace_id"]  # use as-is from JSON: Name|{GUID}
L.append("| %d | `%s` | %s |" % (i, fn["name"], trace_cell))
```

When parsing the function list Markdown back, use an end-of-line boundary
so the full trace_id (including `|{GUID}`) is captured correctly:

```python
# Correct parser -- match up to trailing " |" at end of row
fn_rows = re.findall(
    r'^\|\s*\d+\s*\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*$',
    section_text, re.MULTILINE
)
# Incorrect (stops at first | in trace_id, truncates GUID):
# r'^\|\s*\d+\s*\|\s*`([^`]+)`\s*\|\s*([^|\n]+?)\s*\|'  <-- DO NOT USE
```

### Rule 7 -- Encoding and Unconventional Characters in Markdown Output

When generating `doc/SwMod_[Module].md`, follow these encoding rules to avoid
corrupted or unreadable output:

**1. Always write files as plain UTF-8 without BOM:**
```python
# Correct
open(path, 'w', encoding='utf-8').write(text)

# Wrong -- produces BOM (\ufeff) at start of file
open(path, 'w', encoding='utf-8-sig').write(text)
```

**2. Never use `unicode_escape` or `repr()` on string content.**
These produce literal escape sequences like `u{2013}` or `u{B7}` in the output
instead of actual characters. Always use UTF-8 for reading and writing.

**3. Always read source files as UTF-8:**
```python
# Correct
text = open(path, encoding='utf-8').read()

# Wrong -- causes double-encoding artifacts like SÂ³P instead of S3P
text = open(path, encoding='latin-1').read()
```

**4. Replace special Unicode separators with plain ASCII before writing:**
Common offenders and their ASCII replacements:

| Character | Code | Replace with |
|---|---|---|
| En-dash (--) | U+2013 | `-` |
| Middle dot (·) | U+00B7 | `-` |
| Em-dash (---) | U+2014 | `-` |
| Non-breaking space | U+00A0 | ` ` (regular space) |
| Superscript 3 (³) in project name | U+00B3 | `3` |

Apply this cleanup before writing to file:
```python
text = text.replace('\u2013', '-').replace('\u00b7', '-').replace('\u2014', '-')
text = text.replace('\u00a0', ' ')
# Project name fix if sourced from EA: S³P -> S3P
text = text.replace('S\u00b3P', 'S3P').replace('SÂ³P', 'S3P')
```

**5. Strip any BOM from text before writing:**
```python
text = text.lstrip('\ufeff')
open(path, 'w', encoding='utf-8').write(text)
```

## What the Tool Does

### Step 1 — Locate or Generate `SwMod_[Module]_Functions.json`

Search `ai_output/doc/` (case-insensitive). If not found, generate via enterprise-architect skill:

```bash
& ".venv32\python.exe" .github/scripts/ea/export_module_functions.py SwMod_<MODULE>
```

### Step 2 — Build Function Lookup Table

Parses the JSON into:
- `functions`: `name.lower() → {name, trace_id, class_name}`
- `classes`:   `name.lower() → {class_name, trace_id}`
- `guid_lookup`: `GUID.upper() → entry` (for reverse-lookup when function is renamed)

### Step 3 — Parse All Test CPP Files

Collects all `*.cpp` under `test/gtest/tests/`. For each test:
- Extracts fixture name, test name, line number, test body
- Parses `@Req_ID` tokens from the preceding `/** ... */` block

### Step 4 — Classify Each Test

| Class | Condition | Tool action |
|-------|-----------|-------------|
| `OUTDATED` | Token name found in JSON but GUID differs → `GUID_MISMATCH` | Auto-fix GUID |
| `OUTDATED` | Token GUID found in JSON but name differs → `NAME_MISMATCH` | Auto-fix name |
| `STALE` | Neither name nor GUID found in JSON | Flag for human review |
| `UNTRACED (auto)` | No `@Req_ID`, confidence ≥ 0.70 | Auto-add `@Req_ID` |
| `UNTRACED (review)` | No `@Req_ID`, confidence < 0.70 | Interactive prompt |
| `VALID` | Token matches JSON exactly | No action |

### Step 5 — Confidence Scoring (for UNTRACED tests)

| Signal | Score |
|--------|-------|
| Test name starts with `Test_<FuncBase>_` | +0.80 |
| Function base name anywhere in test name | +0.50 |
| Function name mentioned in test body | +0.35 |
| Only one candidate scores above zero | +0.05 bonus |

**Auto-apply threshold: ≥ 0.70.** Multiple functions can score above threshold — all are included in `@Req_ID`.

### Step 6 — Report Uncovered Functions to User

For each function in the JSON with zero `@Req_ID` links, **do NOT generate `GTEST_SKIP()` stubs**. Instead, report the uncovered functions to the user and request proper test case creation.

**Report format:**

```
⚠️ Uncovered functions — test cases required:

| # | Function | Class | Trace ID | Action Required |
|---|----------|-------|----------|-----------------|
| 1 | AmbSTemp_vFoo | AmbSTemp_API | AmbSTemp_vFoo|{GUID} | ⚠️ Create test case(s) |
```

**Message to user:**
> The functions listed above have no test cases linked via `@Req_ID`.
> Please create proper test cases for each function and annotate them with the correct `@Req_ID` token.
> Do NOT add placeholder `GTEST_SKIP()` stubs — implement real tests that verify the function's behaviour.

**Why not stubs?** Stub tests with `GTEST_SKIP()` give a false sense of traceability coverage. They appear in reports as "covered" while providing zero verification of correctness. Real test cases must exercise the function logic.

### Step 7 — State JSON Output

Written to `ai_output/doc/SwMod_[Module]_traceability_state.json`:

```json
{
  "module": "AmbSTemp",
  "outdated": [
    { "test_name": "Test_vInit_WrongLut", "updates": [
        {"old": "AmbSTemp_vInit|{OLD}", "new": "AmbSTemp_vInit|{NEW}", "reason": "GUID_MISMATCH"}
    ]}
  ],
  "untraced": [
    { "test_name": "Test_vFoo_Normal", "auto_apply": true,
      "proposals_auto": [{"function": "AmbSTemp_vFoo", "confidence": 0.85}] }
  ],
  "stale": [
    { "test_id": "Fixture::Test_Old", "token": "Deleted_Func|{GONE}", "reason": "NOT_IN_JSON" }
  ],
  "uncovered_functions": [
    { "function": "AmbSTemp_pstGetTmpByChannelId", "suggested_fixture": "AmbSTempPfTestInitialDoneFixture" }
  ]
}
```

### Implementation Reference

The complete implementation of all steps above lives in:

```
.github/scripts/gtest/gtest_traceability.py
```

Key functions in the script:

| Function | Purpose |
|----------|---------|
| `find_functions_json()` | Step 1 — locate JSON in `ai_output/doc/` |
| `parse_functions_json()` | Step 2 — build function/class/GUID tables |
| `parse_test_file()` | Step 3 — extract tests + `@Req_ID` tokens |
| `validate_token()` | Step 4 — classify each token (VALID/GUID_MISMATCH/NAME_MISMATCH/STALE) |
| `score_candidates()` | Step 5 — confidence scoring for untraced tests |
| `FilePatcher` | Batch CPP edits bottom-to-top (preserves line numbers) |
| `analyze()` | Orchestrate steps 1–5, return state dict |
| `run_fix()` | Apply state dict to CPP files |

---

### Phase 1 — Locate or Generate `SwMod_[Module]_functions.json`

#### Step 1.1 Resolve JSON path
Search `ai_output/doc/` for `SwMod_<Module>_functions.json` (case-insensitive match on the module name segment).

```python
import glob, os, re

def find_functions_json(project_root, module_name):
    pattern = os.path.join(project_root, 'output', 'doc', f'SwMod_*_Functions.json')
    candidates = glob.glob(pattern, recursive=False)
    # also try lowercase variant
    pattern_lc = os.path.join(project_root, 'output', 'doc', f'SwMod_*_functions.json')
    candidates += glob.glob(pattern_lc, recursive=False)
    for c in candidates:
        stem = os.path.basename(c)  # e.g. SwMod_TouchSM_Functions.json
        # Extract module segment between SwMod_ and _Functions
        m = re.match(r'^SwMod_(.+?)_[Ff]unctions\.json$', stem)
        if m and m.group(1).lower() == module_name.lower():
            return c
    return None
```

#### Step 1.2 Generate JSON if missing
If the file does not exist, invoke the enterprise-architect skill to export it:

```bash
# Requires EA open with the project loaded + 32-bit Python
& ".venv32\python.exe" .github/scripts/ea/export_module_functions.py SwMod_<MODULE>
```

The output is written to `ai_output/doc/SwMod_<MODULE>_Functions.json` (and `.md`).

After generation, re-run Step 1.1 to confirm the file exists before continuing.

**If EA is unavailable** (no 32-bit Python, EA not open), report the missing file and stop:
```
ERROR: ai_output/doc/SwMod_AmbSTemp_functions.json not found.
       Run: & ".venv32\python.exe" .github/scripts/ea/export_module_functions.py SwMod_AmbSTemp
       Then re-run this skill.
```

---

### Phase 2 — Build Function Lookup Table from JSON

Parse the JSON and build a flat lookup of all functions:

```python
import json

def build_function_table(json_path):
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    functions = {}   # name (lowercase) -> {name, trace_id, class_name, class_trace_id}
    classes = {}     # class_name (lowercase) -> {class_name, trace_id}

    for cls in data.get('classes', []):
        cn = cls['class_name']
        ct = cls.get('trace_id', '')
        classes[cn.lower()] = {'class_name': cn, 'trace_id': ct}
        for fn in cls.get('functions', []):
            fname = fn['name']
            tid = fn['trace_id']   # e.g. "AmbSTemp_vInit|{B5D6D92B-...}"
            functions[fname.lower()] = {
                'name': fname,
                'trace_id': tid,
                'class_name': cn,
                'class_trace_id': ct,
            }

    return functions, classes
```

**JSON structure reference:**
```json
{
  "module": { "name": "SwMod_AmbSTemp", ... },
  "classes": [
    {
      "class_name": "AmbSTemp_API",
      "trace_id": "AmbSTemp_API|{GUID}",
      "functions": [
        { "number": 1, "name": "AmbSTemp_vInit", "trace_id": "AmbSTemp_vInit|{GUID}" },
        ...
      ]
    }
  ]
}
```

Also build a **GUID reverse-lookup**: GUID string → `{name, trace_id}` for unresolved-token diagnosis.

```python
guid_to_entry = {}
for entry in functions.values():
    m = re.search(r'\{([^}]+)\}', entry['trace_id'])
    if m:
        guid_to_entry[m.group(1).upper()] = entry
```

> **Trace ID validity (Rules 1-5 above):** Every `trace_id` in the JSON must come from
> an **EA Activity Diagram GUID** (Rule 1) or the **parent class trace_id** (Rule 2 fallback).
> Never use Operation GUIDs or Action node GUIDs — see the Trace ID Assignment Rules section.

---

### Phase 3 — Discover and Parse GTest Test Files

#### Step 3.1 Auto-detect test files
If `TESTS_DIR` is not provided, search under `pkg/` for the module's test folder:

```python
def find_tests_dir(project_root, module_name):
    # Search for directories matching */test/gtest/tests that contain module name
    pattern = os.path.join(project_root, 'pkg', '**', 'test', 'gtest', 'tests')
    candidates = glob.glob(pattern, recursive=True)
    for d in candidates:
        # Parent directory name should match module (case-insensitive)
        parts = d.replace('\\', '/').split('/')
        for p in parts:
            if p.lower() == module_name.lower():
                return d
    return None
```

Collect all `*.cpp` files in the tests directory.

#### Step 3.2 Extract test cases from CPP files

For each CPP file, scan line-by-line:
1. Detect Doxygen comment blocks (`/** ... */`)
2. Extract `@Req_ID` from within the comment block
3. Detect the immediately following `TEST_F(...)`, `TEST_P(...)`, or `TEST(...)` declaration

```python
import re

TEST_PATTERN = re.compile(r'^\s*TEST(?:_F|_P)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)')
REQ_ID_PATTERN = re.compile(r'@Req_ID\s*:\s*(.+)')
TOKEN_PATTERN = re.compile(r'([\w:<>&]+)\|\{([^}]+)\}')

def parse_test_file(cpp_path):
    tests = []
    with open(cpp_path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    in_comment = False
    current_req_ids = []    # list of raw token strings from @Req_ID
    comment_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        if '/**' in stripped and not in_comment:
            in_comment = True
            current_req_ids = []
            comment_lines = [stripped]
            continue

        if in_comment:
            comment_lines.append(stripped)
            m = REQ_ID_PATTERN.search(stripped)
            if m:
                # May span to next line — but normally on one line
                raw = m.group(1).strip()
                # Split on ' & '
                current_req_ids = [t.strip() for t in raw.split('&') if t.strip()]
            if '*/' in stripped:
                in_comment = False
            continue

        m = TEST_PATTERN.match(line)
        if m:
            fixture, test_name = m.group(1), m.group(2)
            parsed_tokens = []
            for raw_token in current_req_ids:
                tm = TOKEN_PATTERN.match(raw_token.strip())
                if tm:
                    parsed_tokens.append({'name': tm.group(1), 'guid': tm.group(2).upper()})
                else:
                    parsed_tokens.append({'name': raw_token, 'guid': None, 'malformed': True})
            tests.append({
                'fixture': fixture,
                'test_name': test_name,
                'req_ids': parsed_tokens,
                'has_req_id': len(parsed_tokens) > 0,
                'line': i + 1,
                'file': cpp_path,
            })
            current_req_ids = []

    return tests
```

**Key parsing rules:**
- Tokens separated by ` & ` (space-ampersand-space)
- Each token: `FunctionName|{GUID}` — single curly braces
- Token names may contain `<`, `>`, `:` for templated/HTML-encoded names
- A test with no `@Req_ID` anywhere in the preceding comment → `has_req_id = False` → flagged `[UNTRACED]`
- A `@Req_ID` present but with malformed tokens → flagged `[MALFORMED]`

---

### Phase 4 — Cross-Reference Functions ↔ Test Tokens

For each test case token, resolve against the function table:

```python
import html

def resolve_token(token, functions, classes, guid_to_entry):
    name = token['name']
    guid = token['guid']
    result = {'token': token, 'status': None, 'resolved_to': None, 'rule': None}

    # Rule 5: HTML-entity normalisation
    decoded_name = html.unescape(name)

    # Rule 1: Direct function name match (case-sensitive preferred, then case-insensitive)
    if decoded_name.lower() in functions:
        entry = functions[decoded_name.lower()]
        result['status'] = 'TRACED'
        result['resolved_to'] = entry
        result['rule'] = '1' if decoded_name == name else '1+5'
        # Rule 2: Also trace parent class
        result['parent_class'] = functions[decoded_name.lower()]['class_name']
        return result

    # Rule 3: Class fallback
    if decoded_name.lower() in classes:
        entry = classes[decoded_name.lower()]
        result['status'] = 'TRACED'
        result['resolved_to'] = entry
        result['rule'] = '3' if decoded_name == name else '3+5'
        return result

    # GUID reverse-lookup (secondary check)
    if guid and guid in guid_to_entry:
        entry = guid_to_entry[guid]
        result['status'] = 'TRACED'
        result['resolved_to'] = entry
        result['rule'] = '1+GUID'
        return result

    result['status'] = 'UNRESOLVED'
    result['rule'] = '4'
    return result
```

Collect:
- `covered_functions`: set of function names that appear in at least one resolved token
- `covered_classes`: set of class names traced via Rule 2 or Rule 3
- `unresolved_tokens`: list of tokens that matched nothing in the function table

---

### Phase 5 — Compute Coverage Metrics

```python
all_function_names = set(e['name'] for e in functions.values())
covered_names = covered_functions | covered_classes

uncovered_functions = all_function_names - covered_names

total = len(all_function_names)
covered = len(all_function_names & covered_names)
coverage_pct = (covered / total * 100) if total else 0.0
```

---

### Phase 6 — Generate Traceability Report

Output to `ai_output/doc/SwMod_[Module]_traceability_report.md`.

#### Section A: Function Coverage

```markdown
## Function Coverage

| Metric | Count |
|--------|------:|
| Total functions in JSON | N |
| Functions linked by @Req_ID | C |
| Functions NOT linked | U |
| Coverage | X% |

### Covered Functions

| # | Function | Class | Trace ID | Linked by Test(s) |
|---|----------|-------|----------|--------------------|
| 1 | `AmbSTemp_vInit` | `AmbSTemp_API` | `AmbSTemp_vInit|{...}` | `Test_vInit_WrongLut`, `Test_vInit_Normal` |

### Uncovered Functions (No @Req_ID link)

| # | Function | Class | Trace ID |
|---|----------|-------|----------|
| 1 | `AmbSTemp__vFoo` | `AmbSTemp_Core` | `AmbSTemp__vFoo|{...}` |
```

#### Section B: Test Case Traceability

```markdown
## Test Case Traceability

| Test Case | Fixture | File | Line | @Req_ID Tokens | Status | Notes |
|-----------|---------|------|------|----------------|--------|-------|
| `Test_vInit_WrongLut` | `AmbSTempPfTestNormalFixture` | `unittest_ambstemp_pf_test.cpp` | 697 | `Test_vInit\|{...}`, `AmbSTemp_IntCfg\|{...}` | TRACED | Rule 1, Rule 3 |
| `Test_Orphan` | `SomeFixture` | `unittest_ambstemp_pf_test.cpp` | 800 | — | UNTRACED | Missing @Req_ID |
| `Test_BadGuid` | `SomeFixture` | `unittest_ambstemp_pf_test.cpp` | 900 | `AmbSTemp_vFoo\|{DEAD-GUID}` | UNRESOLVED | GUID not in JSON |
```

Status values:
- `TRACED` — all tokens resolved to known functions/classes
- `PARTIAL` — some tokens resolved, some UNRESOLVED
- `UNTRACED` — no `@Req_ID` annotation at all

---

### Phase 7 -- Generate HTML Summary Report

After analyzing traceability, generate a self-contained HTML summary report for easy browsing and stakeholder review.

#### Script reference
```
.github/scripts/gtest/ms_traceability_html.py
.github/scripts/gtest/ms_traceability_html.cmd
```

#### Usage
```bash
# Windows wrapper (same arguments, shorter invocation)
.github\scripts\gtest\ms_traceability_html.cmd ^
  --xml pkg/em_s3p_hud/videoctl/vidcond/MS_VidConD.xml ^
  --tests-dir pkg/em_s3p_hud/videoctl/vidcond/test/gtest/tests ^
  --out pkg/em_s3p_hud/videoctl/vidcond/test/gtest/tests/vidcond_traceability_summary.html ^
  --title "VidConD Traceability Summary"

# Module-wide HTML summary (all *.cpp in tests dir)
python .github/scripts/gtest/ms_traceability_html.py \
  --xml pkg/em_s3p_hud/videoctl/vidcond/MS_VidConD.xml \
  --tests-dir pkg/em_s3p_hud/videoctl/vidcond/test/gtest/tests \
  --out pkg/em_s3p_hud/videoctl/vidcond/test/gtest/tests/vidcond_traceability_summary.html \
  --title "VidConD Traceability Summary"

# Single test-file HTML summary
python .github/scripts/gtest/ms_traceability_html.py \
  --xml pkg/em_s3p_hud/videoctl/vidcond/MS_VidConD.xml \
  --cpp pkg/em_s3p_hud/videoctl/vidcond/test/gtest/tests/unittest_errmon_pf_test.cpp \
  --out report_errmon_traceability.html
```

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--xml` | Yes | Path to Enterprise Architect model XML (`MS_*.xml`) |
| `--tests-dir` | Yes* | Folder containing test `.cpp` files (module-wide report) |
| `--cpp` | Yes* | Single test `.cpp` file (single-file report) |
| `--out` | Yes | Output HTML path |
| `--title` | No | HTML report title (default: `MTS Traceability Summary`) |
| `--max-uncovered` | No | Max uncovered model tokens shown (default: 40) |
| `--quiet` | No | Suppress progress logs |

`*` Exactly one of `--tests-dir` or `--cpp` is required.
- `UNRESOLVED` — all tokens fail to resolve
- `MALFORMED` — `@Req_ID` present but token format is invalid

#### Section C: Unresolved Tokens

```markdown
## Unresolved Tokens

| Token (from @Req_ID) | GUID | Test Case | File | Reason |
|----------------------|------|-----------|------|--------|
| `AmbSTemp_vFoo\|{DEAD-...}` | `DEAD-...` | `Test_BadGuid` | `unittest_...cpp` | Name and GUID not found in JSON |
```

#### Section D: Summary

```markdown
## Summary

| Metric | Count |
|--------|------:|
| Total functions in JSON | N |
| Functions linked by tests | C |
| Uncovered functions | U |
| Function coverage | X% |
| Total test cases | T |
| Traced test cases | TR |
| Untraced test cases | UT |
| Test cases with UNRESOLVED tokens | UR |
| Total @Req_ID tokens | TOK |
| Resolved tokens | R |
| Unresolved tokens | UNR |
```

---

## Key Rules and Pitfalls

### @Req_ID Format
```
@Req_ID: FunctionName|{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX} & ClassName|{...}
```
- Single curly braces `{}` — not double
- Separator is ` & ` (space-ampersand-space); splitting on bare `&` will corrupt HTML-entity names like `bo<Action>`
- Function names may contain `<`, `>`, `:` — use `[\w:<>&]+` in regex, not just `\w+`
- Token names are **case-sensitive** against the JSON — match exactly before falling back to case-insensitive

### JSON File Naming
- The file may be named `SwMod_AmbSTemp_Functions.json` (capital F) or `swmod_ambstemp_functions.json` depending on the tool version
- Always do a case-insensitive glob match
- The enterprise-architect tool `export_module_functions.py` writes to `ai_output/doc/SwMod_<Module>_Functions.json`

### Tests Directory Discovery
- Some modules place tests under `pkg/<area>/<subsystem>/<module>/test/gtest/tests/`
- Walk up parent directories from any found `.cpp` and match the module segment
- Collect **all** `*.cpp` files in the directory — a module may have multiple test files

### Class Traces (Rule 3)
- `@Req_ID` often includes the **class name** (e.g. `AmbSTemp_API|{...}`) alongside function names
- Class names are in `classes[].class_name` and `classes[].trace_id` in the JSON
- These are valid traces — count them in coverage for the class itself, but they do **not** count as covering the individual functions inside the class

### Parent Class Auto-Trace (Rule 2)
- When a function is resolved (Rule 1), its parent class is automatically marked as co-traced
- Record this as Rule 2 in the notes column — the class was not explicitly listed in `@Req_ID`

### Test Name Normalization in `Test_vInit` vs `AmbSTemp_vInit`
- Some `@Req_ID` annotations use `Test_<FuncName>` instead of the actual function name
- These will **not** resolve via Rule 1 or Rule 3 (they are not in the JSON)
- They will resolve via GUID reverse-lookup if the GUID matches
- If neither name nor GUID resolves: flag `[UNRESOLVED]` — developer must correct the annotation

### Enterprise Architect Skill Dependency
- If `SwMod_[Module]_functions.json` does not exist, this skill must trigger the enterprise-architect skill:
  ```
  Use enterprise-architect skill: export_module_functions.py SwMod_<MODULE>
  ```
- This requires EA to be open and 32-bit Python with `pywin32` installed
- Check `.venv32\python.exe` exists before attempting
- The generated JSON goes to `ai_output/doc/` automatically

---

## Example Usage Prompts

```
Run s3p-mts-traceability for AmbSTemp
```

Equivalent tool command:
```bash
python .github/scripts/gtest/gtest_traceability.py --module AmbSTemp --fix
```

```
Dry-run traceability check for TouchSM — show what would change without editing files
```
```bash
python .github/scripts/gtest/gtest_traceability.py --module TouchSM --fix --dry-run
```

```
Analyze only — write state JSON for review before applying
```
```bash
python .github/scripts/gtest/gtest_traceability.py --module AmbSTemp --analyze
```

```
CI mode — fix all high-confidence issues, skip interactive prompts
```
```bash
python .github/scripts/gtest/gtest_traceability.py --module AmbSTemp --fix --non-interactive
```

---

## Output Files

| File | Description |
|------|-------------|
| `ai_output/doc/SwMod_[Module]_traceability_state.json` | Full analysis state (outdated, untraced, stale, uncovered) |

If the JSON was auto-generated in this session, these are also created by the enterprise-architect skill:

| File | Description |
|------|-------------|
| `ai_output/doc/SwMod_[Module]_Functions.json` | EA function export (JSON) |
| `ai_output/doc/SwMod_[Module]_Functions.md` | EA function export (Markdown) |

---

## Integration with Other Skills

| Skill | When to use together |
|-------|---------------------|
| `enterprise-architect` | Generate the JSON input when it's missing (Phase 1) |
| `mts-traceability` | When the module uses an MS XML model file instead of the functions JSON |
| `gtest-testcase-gen` | After identifying uncovered functions — generate missing test cases |
| `.github:mts-traceability` | Agent-mode version of the MTS traceability workflow (MS XML → MTS trace data XML) |
