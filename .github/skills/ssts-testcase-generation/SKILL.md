---
name: ssts-testcase-generation
description: >
  Profile skill for system test case generation (SSTS). Uses the shared
  testcase-generation-core pattern and adds system-level scope, end-to-end
  behavior focus, and customer-visible outcome validation.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# SSTS Test Case Generation Profile

## Scope

Use for system testing (SSTS):

- End-to-end behavior across multiple subsystems
- System requirements and use-case validation
- Customer-visible outcomes and safety/system-level acceptance criteria

## Inherits from core

Apply all rules from `testcase-generation-core` first, then apply this SSTS profile.

## SSTS-specific emphasis

- Preconditions should reflect full system setup and orchestration context.
- Steps should validate complete flow from trigger to final system behavior.
- Expected results should prioritize system-visible and user-visible outcomes.
- Prefer tags such as: `System`, `Functional`, `E2E`, `Negative`, `Boundary`, `Safety`.

## SSTS quality focus

- Validate interactions spanning more than one subsystem.
- Ensure failure handling is validated at system level.
- Include nominal and degraded/abnormal operating scenarios.
- Maintain chapter-level traceability to system requirement sections.

## When to choose SSTS vs SITS

Choose this profile when requirement language is system-level, end-to-end,
or customer-facing rather than interface-level integration behavior.
