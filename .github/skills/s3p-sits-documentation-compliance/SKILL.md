---
name: s3p-sits-documentation-compliance
description: >-
  Ensures test cases meet automotive industry standards and project compliance
  requirements including MISRA C/C++, ASPICE 4.0, and internal documentation standards.
  Use when: writing GTF/Robot Framework test documentation blocks; verifying test
  traceability to requirements; checking coverage metrics and safety classification.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# Test Documentation & Compliance Skill

## Overview
This skill ensures all test cases meet automotive industry standards and project compliance requirements including MISRA C/C++, ASPICE 4.0, and internal documentation standards.

## Compliance Standards

### ASPICE 4.0 (Automotive SPICE)
ASPICE defines requirements for testing processes:
- **Scope**: All test activities must be documented and traceable
- **Traceability**: Each test must link to a requirement or SWDD
- **Test Approach**: Define test strategy before implementation
- **Evidence**: Test results and coverage metrics must be collected
- **Reviews**: Test cases undergo peer review before execution

### MISRA Compliance
- Follow MISRA C/C++ coding guidelines in all test code
- Use appropriate variable types and avoid unsafe constructs
- Document deviations with justification when necessary
- Apply static analysis tools to test code

### Project-Specific Requirements
- All tests must have complete documentation blocks
- Test traceability to requirements is mandatory
- Coverage metrics must be tracked and reported
- Functional safety classification required for safety-critical tests

## Test Case Documentation Template

### GTF Unit Tests
```cpp
/**
* @Trace: REQ_MODULE_001 or SDD_Component_Function_01
* @Variant: Variant_1, Variant_2 (from specification)
* @Description: Clear description of what is being tested
* <br>TestStep1: {first step of test}
* <br>TestStep2: {second step of test}
* <br>TestStep3: {third step of test}
* @DesignTechnique: Equivalence Partitioning | Boundary Value Analysis | State Transition | Error Guessing | Decision Table
* @Input: Input values/conditions for the test
* @Result: Expected output and behavior
* <br>Result_Line2: {additional expected results}
* <br>Result_Line3: {more expected results}
* @FunctionSafety: yes/no
* @Security: non-SPR/SPR
* @TestMaturity: draft/review-ready/released
* @TechnicalRegulation: non-LTR/LTR
* @ChangeRequest: N/A or JIRA-XXXX link
*/
TEST(TestSuite, TestName)
{
    // Test implementation
}
```

### Robot Framework Tests (Integration Tests)

Documentation is written as `#` comments **inside the test case body**, using the project-standard fields.
Do **NOT** use `/** ... */` blocks or `[Documentation]` with `@` tags for Robot Framework tests.

```robot
*** Settings ***
Documentation  Integration Test for Module Functionality
...            Validates component interaction and system workflows

*** Test Cases ***
Test_Case_Name
#
#    ...[Req_ID]
#    ...              REQ_MODULE_001
#    ...[Documentation]
#    ...              Short description of what this test validates.
#    ...
#    ...              TestStep1: Initialize component to known state.
#    ...              TestStep2: Send state transition request.
#    ...              TestStep3: Wait for transition completion.
#    ...              TestStep4: Verify final state and side effects.
#    ...[Input]
#    ...              Input values and conditions used by the test
#    ...[Expected Result]
#    ...              Component transitions to target state within timeout.
#    ...              All signals updated correctly. No error codes generated.
#    ...[FSM]         NO
#    ...[Variant]     S3P-HUD
    [Tags]    integration    module_name    regression
    # Test implementation keywords
```

## Documentation Block Fields

### Robot Framework `#` Comment Fields

| Field | Mandatory | Description |
|-------|-----------|-------------|
| `[Req_ID]` | Yes | Requirement or SWDD ID (e.g. `REQ_MODULE_001`) |
| `[Documentation]` | Yes | Test description and numbered `TestStep1:`, `TestStep2:` … steps |
| `[Input]` | Yes | Input values, signals, voltages, states used by the test |
| `[Expected Result]` | Yes | Measurable expected outputs and behavior |
| `[FSM]` | Yes | `YES` if test covers a state machine, otherwise `NO` |
| `[Variant]` | Yes | Product variant (e.g. `S3P-HUD`); use `N/A` if not variant-specific |

### `[Req_ID]` (Mandatory)
- Links test to requirement or design document
- Format: `REQ_COMPONENT_###` or `SDD_COMPONENT_###`
- Multiple IDs allowed — one per line
- Example: `REQ_EyeBox_001`

### `[Documentation]` (Mandatory)
- Clear, concise explanation of test purpose
- Include numbered test steps: `TestStep1: ...`, `TestStep2: ...`
- Should answer: "What is being tested and why?"

### `[Input]` (Mandatory)
- Specific input values used in test
- Include ranges, boundary values, and special cases
- Example: `NormalVoltage=14V, off_time=10ms, cycles=100`

### `[Expected Result]` (Mandatory)
- Expected output and behavior
- Should be measurable and verifiable
- Include all expected side effects
- Multiple lines allowed

### `[FSM]` (Mandatory)
- `YES` — Test exercises a state machine transition
- `NO` — Test is not state-machine-focused

### `[Variant]` (Mandatory)
- `S3P-HUD` — Default project variant
- Use `N/A` if not variant-specific

## Test Group Documentation Template

### GTF Test Groups (C++ unit tests only)
```cpp
/**
* @GroupName: Functional Area or Component Name
* @Description: Description of tests in this group
* @Order: -1 (execution order; -1 = default)
*/
```

### Robot Framework Test Groups
Groups are defined by organizing test cases in the same file.
No separate group block is needed — the file/section structure defines the group.
Use the `*** Settings ***` `Documentation` field to describe the overall test group purpose.

## Traceability Requirements

### Requirements Mapping
Every test must trace back to:
- **Functional Requirements** (REQ_*)
- **Software Design Documents** (SDD_*)
- **System Design Documents** (HLD_*)

### Traceability Matrix
Create a mapping document showing:
| Requirement | Test Case | Status | Coverage |
|-------------|-----------|--------|----------|
| REQ_001 | TC_001, TC_002 | Complete | 100% |
| REQ_002 | TC_003 | Partial | 50% |

### Coverage Reporting
- Track requirements covered by test cases
- Identify untested requirements
- Report coverage metrics in test reports
- Flag uncovered requirements for risk assessment

## MISRA Compliance in Tests

### Guidelines
1. **Variable Declarations**: Declare all variables at function start
2. **Type Safety**: Use appropriate types, avoid implicit conversions
3. **Function Complexity**: Keep functions focused and simple
4. **Comments**: Document non-obvious logic
5. **Error Handling**: Check return values and error codes
6. **Memory**: Proper allocation and deallocation
7. **Macros**: Use safely, avoid side effects

### Test Code Example
```cpp
/**
* @Trace: REQ_SAFETY_001
* ...other documentation...
*/
TEST(SafetyTests, VerifyBoundaryCondition)
{
    // MISRA compliant: proper variable declaration
    int16_t test_value = 100;
    int16_t result = 0;
    bool status = false;
    
    // Error checking and type safety
    if (test_value >= 0 && test_value <= 1000) {
        status = FunctionUnderTest(test_value, &result);
    }
    
    // Assertion with proper comparison
    ASSERT_TRUE(status);
    EXPECT_EQ(result, 150);
}
```

## Documentation Checklist

Before committing test code, verify:

- [ ] All tests have complete documentation blocks
- [ ] @Trace fields link to valid requirements
- [ ] @FunctionSafety is set correctly (yes/no only)
- [ ] Test steps are clear and numbered
- [ ] Input values specified precisely
- [ ] Expected results are measurable
- [ ] Design technique is documented
- [ ] No MISRA violations in test code
- [ ] Code follows project naming conventions
- [ ] Comments explain non-obvious logic
- [ ] Functions are focused (single responsibility)
- [ ] All error paths tested
- [ ] Appropriate security/privacy handling

## Compliance Validation Tools

### Static Analysis
- Run static checkers on test code
- Enforce MISRA rules
- Report violations in CI/CD pipeline

### Documentation Validation
- Automated parsing of documentation blocks
- Verify required fields are present
- Validate field values against allowed options
- Check traceability completeness

### Coverage Metrics
- Collect code coverage from GTF runs
- Measure requirements coverage
- Generate coverage reports
- Identify gaps

## Peer Review Process

1. **Code Review**: Check for MISRA compliance and clarity
2. **Documentation Review**: Verify completeness and accuracy
3. **Traceability Review**: Confirm links to requirements
4. **Test Validation**: Execute tests and verify results
5. **Compliance Approval**: Sign-off from test lead

## Reporting Requirements

Test reports must include:
- Test execution summary (passed/failed/skipped)
- Coverage metrics (code and requirements)
- Traceability matrix
- Any deviations or waivers
- Recommendations for future testing

## Related Skills
- `test-design-techniques` - For test design methodology
- `robot-framework-integration` - For RF test documentation patterns
- `test-strategy-planning` - For test planning and strategy
