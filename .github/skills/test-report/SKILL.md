---
name: test-report
description: >-
  Generates and maintains on-target use-case test reports (a matching .md + .html
  pair, e.g. VsMon_UseCaseTesting.md/.html) for embedded C modules tested via GHS
  Multi / Lauterbach TRACE32 debugger. Use this skill whenever the user asks to
  create, author, simplify, restructure, or expand a "use case testing" report,
  wants to add a new UC-xx test case, wants to fill in test results after running
  something on-target, or is editing a file matching *_UseCaseTesting.* /
  *_Testing.md. Always use this skill's canonical structure instead of inventing a
  new layout, and prefer it even if the user just says "write up the test results"
  for a module that was just debugged on-target. Covers both authoring test cases
  up front (with Result cells left as "pending") and filling in Result cells later
  from an actual test run.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# Test Report Skill

Produces consistent, non-bloated use-case test reports for on-target testing
(GHS Multi / Lauterbach) of embedded C modules. This packages the report structure
iterated on for `VsMon_UseCaseTesting.md`/`.html` so every module's report looks and
reads the same way, and stays easy to regenerate/update as new test runs come in.

## When to use this

- Authoring a **new** use-case test report for a module before it's been run on target
  (Result cells start as "pending"/TBD).
- **Filling in results** after an on-target test session (updating Result cells + the
  per-use-case Summary + the top Summary table's status).
- The user says the report is "too much content" / "too verbose" / wants it
  "simplified", or conversely wants a step "expanded" into more detail — the fix is
  always to conform to the structure below, not to invent a new one.
- Any file under `ai_output/` (or similar) named like `<Module>_UseCaseTesting.md`,
  or paired `.html`.

## Canonical report structure

Every report is a single page with exactly two parts:

### 1. Header + Summary table

```
# <Module> Use Case Testing

**Module**: `<Module>` (<one-line description>, <ASIL level if applicable>) — links to
core file(s)
**Method**: On-target (GHS Multi / Lauterbach TRACE32 debugger) — breakpoints on
internal functions + direct read/override of internal RAM variables.

---

## Summary

| # | Test Case | Result / Status |
|---|-----------|------------------|
| UC-01 | <short title> | ✅ PASS |
| UC-02 | <short title> | ⚠️ PARTIAL (...) |
```

The Summary table is the **only** place a reader needs to check to know overall status
— keep each row to one line, no narrative.

### 2. One detailed section per use case

For each `UC-xx`, in this exact order:

1. `### UC-xx — <title>` heading.
2. **Description / Purpose** — one prose paragraph (not a table row). What behavior is
   being confirmed and why.
3. **Traceability** — one prose line: which functions (and file) are under test, and
   which diagram (activity/sequence `.puml`) this exercises, if any.
4. **Test Script(s)** — one prose line naming the actual RC/Python script file(s) used
   to run this on target (e.g. `UC01_match.rc`, `run_UC01_match.sh`). If a use case has
   multiple phases/batches, name each phase's script explicitly — never collapse
   multiple scripts into one summarized row (see "Expanding a summarized step" below).
5. A **step table**, one row per test step, with exactly these 5 columns:

   | # | What to do | How to do exactly | Expectation | Result |
   |---|-----------|--------------------|--------------|--------|

   - **What to do**: the intent of the step in plain English (e.g. "Inject a region
     result equal to the reference CRC").
   - **How to do exactly**: the literal command/technique used (debugger syntax,
     script name, breakpoint type). This is the only place raw commands belong.
   - **Expectation**: what should happen. Use `None` (not an empty cell) if the step
     has no independent pass/fail expectation of its own (e.g. a pure setup step).
   - **Result**: what was actually observed, prefixed with a status icon (see
     vocabulary below). Before the step has been executed, put `⏳ pending` here —
     never leave it blank.

6. A **Summary** line/callout after the table — 1-3 sentences giving the overall
   verdict for this use case and the single most important caveat, if any. This is
   the only narrative prose allowed per use case besides the purpose paragraph.

### Status vocabulary (use consistently, both in the table and the icons)

| Icon | Meaning |
|---|---|
| ✅ | PASS — matched expectation |
| ⚠️ | PARTIAL / INCONCLUSIVE — mechanism confirmed but not fully proven, or a genuine anomaly needing a rerun |
| ❌ | FAIL / BLOCKED — did not match expectation, or a precondition made the check unreachable |
| ℹ️ | Informational only — no pass/fail attached (baseline reads, design confirmations, setup) |
| ⏳ | pending — step authored but not yet executed on target |

## Rules that keep reports from re-bloating

- **Never inline full execution logs** in the report. Point to the archived script
  file (`Test Script(s)` line) instead — the reader can open the `.rc`/`.sh`/`.py`
  file or the log under `build/<variant>/` for raw evidence.
- **One step = one table row.** If a single row's "How to do exactly" cell would need
  to describe more than one distinct technique/script (e.g. "batches A-E"), that's a
  sign it must be split into one row per batch/phase — each with its own script
  reference, expectation, and result. Never summarize multiple sub-checks into a
  single row once there's more than one script or more than one pass/fail outcome
  buried inside it.
- **Description/Purpose and Traceability are prose, not table rows.** Only the
  step-by-step mechanics belong in the table.
- **Keep the top Summary table one line per use case.** Detail always lives in that
  use case's own section, never in the top table.
- Always keep the `.md` and paired `.html` in sync — the `.html` mirrors the same
  content with the CSS in `assets/report_template.html` (status colors: `.pass`
  green, `.partial` amber, `.blocked` red, `.info` grey).

## Workflow

1. **Before testing**: author the report with every planned use case and step, using
   `⏳ pending` for all Result cells and leaving each Summary as "Not yet executed."
   Either write the `.md`/`.html` directly following the structure above, or describe
   the test cases as a JSON spec (see `references/example_spec.json`) and run the
   generator script (below) to scaffold both files.
2. **After an on-target run**: update only the Result cells for the steps actually
   executed, the affected UC's Summary line, and that UC's row in the top Summary
   table. Do not rewrite unrelated sections.
3. **When asked to simplify**: collapse narrative back down to the structure above —
   do not delete the step table itself, only remove excess prose/duplicated evidence.
4. **When asked to expand a step**: split it into one row per sub-check/script per the
   "Rules" section above, never leave a still-summarized row.

## Generator script (optional convenience)

`scripts/generate_test_report.py` renders a `.md` + `.html` pair from a JSON spec, so a
new module's report starts from the exact canonical structure without hand-typing the
HTML/CSS boilerplate. It is optional — hand-editing the `.md`/`.html` directly is just
as valid, especially for small result updates.

```
python .github/skills/test-report/scripts/generate_test_report.py \
    --spec my_module_report.json \
    --out-md ai_output/MyModule_UseCaseTesting.md \
    --out-html ai_output/MyModule_UseCaseTesting.html
```

See `references/example_spec.json` for the full JSON schema (module header, list of
use cases, each with `description`, `traceability`, `scripts`, `steps[]`, `summary`).
Re-running the script after editing the JSON (e.g. filling in real `result` values) is
the fastest way to keep a large report's `.md`/`.html` in sync — but for small,
one-off result updates, editing the two files directly is simpler than round-tripping
through the JSON.
