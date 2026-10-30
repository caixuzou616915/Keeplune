---
name: sits-testcase-generation
description: >
  Profile skill for sub-system integration test case generation (SITS). Uses the shared
  testcase-generation-core pattern and adds integration/interface-level focus,
  interaction behavior checks, and subsystem boundary validation.
metadata:
  author: "Zhao Jianbo"
  version: "2.0.0"
---

# SITS Test Case Generation Profile

## Scope

Use for sub-system integration testing (SITS):

- Interface-level behavior between connected subsystems
- Data flow and protocol interaction checks
- Integration error handling and boundary robustness

## Inherits from core

Apply all rules from `testcase-generation-core` first, then apply this SITS profile.

## SITS-specific emphasis

- Preconditions should define subsystem wiring, simulation/stub setup, and communication state.
- Steps should target interface stimuli and cross-subsystem handoffs.
- Expected results should validate interface outputs, state transitions, and synchronization behavior.
- Prefer tags such as: `Integration`, `Interface`, `Functional`, `Negative`, `Boundary`, `StateTransition`.

## SITS quality focus

- Validate both happy-path and interface-fault scenarios.
- Include timing/ordering-sensitive transitions where relevant.
- Ensure integration points are covered in both directions (producer/consumer where applicable).
- Maintain chapter-level traceability to integration requirement sections.

## When to choose SITS vs SSTS

Choose this profile when requirements are primarily about subsystem interfaces,
integration flows, and contract behavior between components.
