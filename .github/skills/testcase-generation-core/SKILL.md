---
name: testcase-generation-core
description: >
  Shared base skill for requirement-based test case generation across SITS and SSTS.
  Defines common coverage patterns, output formats (Markdown + JSONL), quality gates,
  and chapter-level traceability matrix rules.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# Core Test Case Generation Skill (Shared)

## Purpose

Provide reusable generation logic shared by:

- SITS (sub-system integration testing)
- SSTS (system testing)

This skill defines the generic pattern, while SITS/SSTS profile skills define
scope-specific behavior.

## Common generation pattern

For each chapter or requirement group, generate at least:

- Positive tests
- Negative tests
- Boundary tests
- Equivalent Class tests
- State Transition tests

Core rules:

- Deduplicate similar scenarios.
- Ensure coverage completeness.
- Keep outputs concise and structured.
- Keep expected outcomes objectively verifiable.

## Output format A: Human-readable Markdown

Use this template per test case:

```md
Test case id: SSTS-001
Test case name: <short descriptive title>
Objective: <purpose of the test>
Preconditions: <required setup>
Test steps:
1. <step 1>
2. <step 2>
Expected result:
- <verifiable outcome>
Test data: <sample input values, or N/A>
Priority: 1|2|3
Tags: <comma-separated tags>
Traceability: <chapter or section number>
```

## Output format B: JSONL

One JSON object per line:

```json
{"TestID":"SSTS-001","Title":"<title>","Objective":"<objective>","Preconditions":"<setup>","Steps":["<step 1>","<step 2>"],"ExpectedResult":"<verifiable outcome>","TestData":"<sample inputs or N/A>","Priority":1,"Tags":["Functional"],"Traceability":"<chapter/section>","TestType":"Positive"}
```

JSONL constraints:

- Exact key names and casing.
- `Priority` numeric only (`1`, `2`, `3`).
- `Steps` and `Tags` arrays.
- `TestType` in `{Positive, Negative, Boundary, EquivalentClass, StateTransition}`.
- Valid JSON, one line per case.

## Required fields

Every generated test case must include:

- Test ID: stable sequential `SSTS-###`
- Title
- Objective
- Preconditions
- Steps
- Expected Result
- Test Data
- Priority (`1` high, `2` medium, `3` low)
- Tags
- Traceability

## Traceability matrix

Create chapter-level matrix:

```md
| Chapter | Covered Test IDs |
|---|---|
| 2.1 | SSTS-001, SSTS-002 |
```

Matrix rules:

- Include every input chapter/section.
- No uncovered chapter allowed.

## Consistency checks

- IDs are unique and sequential.
- Markdown and JSONL represent the same logical cases.
- No duplicates by intent.
- Coverage families present for each relevant chapter.
