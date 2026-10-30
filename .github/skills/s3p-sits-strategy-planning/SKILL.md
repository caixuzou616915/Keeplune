---
name: s3p-sits-strategy-planning
description: >-
  Guides the process of analyzing requirements and creating comprehensive test plans and
  strategies for the S3P HUD project, bridging requirements and test implementation.
  Use when: analyzing a new requirement before writing tests; defining test scope
  (in/out); selecting unit/integration/system test levels.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# Test Strategy & Planning Skill

## Overview
This skill guides the process of analyzing requirements and creating comprehensive test plans and strategies for the S3P HUD project. It bridges requirements and test implementation.

## Test Planning Process

### Phase 1: Requirement Analysis
Before writing any tests, analyze the requirement to understand:

1. **Functional Scope**: What does the component/feature do?
2. **Inputs**: What inputs does it accept?
3. **Outputs**: What outputs should it produce?
4. **States**: What states can it be in?
5. **Transitions**: How does it move between states?
6. **Constraints**: What are the limits and constraints?
7. **Error Cases**: What can go wrong?
8. **Dependencies**: What other components does it depend on?
9. **Safety Criticality**: Is it safety-critical?
10. **Regulatory Requirements**: ASPICE, MISRA, etc.?

### Phase 2: Test Scope Definition
Define what will and won't be tested:

**In Scope**:
- Component functionality
- State transitions
- Boundary conditions
- Error handling
- Dependencies (via mocks/stubs)

**Out of Scope**:
- Third-party library internals
- Hardware driver internals
- Performance optimization
- Code coverage metrics (separate concern)

### Phase 3: Test Strategy Selection
Choose appropriate testing levels:

**Unit Testing (GTF)**
- Test individual functions
- Use mocks for dependencies
- Focus on logic correctness
- High coverage target (>80%)

**Integration Testing (Robot Framework)**
- Test component interactions
- Validate workflows
- Use real or simulated hardware
- Coverage of end-to-end scenarios

**System/BVT Testing**
- Full system validation
- Real hardware
- Production-like environment

## Test Case Design Workflow

### Step 1: Requirement to Test Cases
For each requirement, create test cases:

```
REQUIREMENT: EyeBox shall transition from Operating mode to Sleep mode 
            when SleepRequest signal is received

ANALYSIS:
- Inputs: Current state, SleepRequest signal value
- Valid Preconditions: Must be in Operating mode (mode=0)
- Valid Trigger: SleepRequest = 1
- Expected Output: Mode changed to Sleep (mode=2)
- Invalid Preconditions: Wrong state transitions (if attempted from Standby, etc.)
- Error Handling: Invalid signal values should be ignored

TEST CASES GENERATED:
1. Valid Transition: Operating → Sleep with SleepRequest
2. Invalid Transition: Attempt transition from Standby (should fail)
3. Boundary: SleepRequest value = 0 (should not trigger)
4. Boundary: SleepRequest value = 1 (should trigger)
5. Error Guessing: Power loss during transition recovery
```

### Step 2: Map to Design Techniques
Select appropriate design techniques for each test case:

| Test Case | Technique | Rationale |
|-----------|-----------|-----------|
| Valid Transition | State Transition Testing | Tests state machine |
| Invalid Transition | Error Guessing | Tests invalid sequence handling |
| SleepRequest Boundary | Boundary Value Analysis | Tests boundary values (0, 1) |
| Power Loss | Error Guessing | Tests recovery mechanism |

### Step 3: Define Test Data
Specify exact input values and expected outputs:

```
TEST CASE: Valid Transition Operating to Sleep
INPUTS:
  - Current Mode: 0 (Operating)
  - SleepRequest: 1
  - Timeout: 10s

EXPECTED OUTPUTS:
  - New Mode: 2 (Sleep)
  - AdjustmentStatus: 0 (Idle)
  - No error codes
  - Status change within 500ms
```

### Step 4: Create Test Implementation Plan
Document which tests go to GTF vs Robot Framework:

**GTF Unit Tests** (test low-level functions):
- Mode validation logic
- Signal parsing
- State machine transitions
- Error code generation

**RF Integration Tests** (test component interaction):
- End-to-end workflow
- Multiple component coordination
- Hardware interaction
- Timeout and retry logic

## Traceability Matrix Template

Create mapping between requirements and tests:

```
TRACEABILITY MATRIX: EyeBox Control Module

Requirement ID | Description | Test Cases | Status | Coverage
REQ_EB_001    | Mode transitions | TC_EB_001, TC_EB_002, TC_EB_003 | Complete | 100%
REQ_EB_002    | Error handling | TC_EB_010, TC_EB_011 | Complete | 95%
REQ_EB_003    | Power cycling | TC_EB_020 | In Progress | 0%
REQ_EB_004    | Calibration | TC_EB_030, TC_EB_031 | Not Started | 0%

SUMMARY:
Total Requirements: 4
Covered: 2 (50%)
Partially Covered: 1 (25%)
Not Covered: 1 (25%)
```

## Test Categorization

### By Risk Level
```
CRITICAL (Must pass before release):
- Safety-critical functionality
- Power management
- Communication reliability
- Error recovery

HIGH (Should pass):
- Core feature workflows
- State transitions
- Boundary conditions
- Performance thresholds

MEDIUM (Nice to have):
- Edge cases
- Error guessing scenarios
- Extended timeouts
- Stress testing

LOW (Future):
- Performance optimization
- Stress testing variations
- Extended coverage
```

### By Test Type
```
POSITIVE TESTS:
- Valid inputs
- Happy path
- Normal operation

NEGATIVE TESTS:
- Invalid inputs
- Error conditions
- Edge cases

ROBUSTNESS TESTS:
- Boundary values
- Extreme conditions
- Resource constraints
```

## Test Naming Convention

### Format
`Test<Module><Feature><Scenario><Expected>`

### Examples
```
TestEyeBoxModeTransitionFromOperatingToSleepSuccess
TestEyeBoxModeTransitionInvalidStateRejected
TestEyeBoxPositionBoundaryValueMinimum
TestEyeBoxPositionBoundaryValueMaximum
TestEyeBoxPowerLossRecovery
TestEyeBoxConcurrentCommandHandling
```

### Components
- **Module**: Component under test (EyeBox, PowerControl, etc.)
- **Feature**: Specific feature being tested
- **Scenario**: Specific condition or case
- **Expected**: Expected result or behavior

## Requirement Analysis Template

Use this template for each requirement:

```
REQUIREMENT ID: REQ_MODULE_XXX

REQUIREMENT TEXT:
"Describe the requirement in detail"

PRIORITY: Critical | High | Medium | Low

SAFETY CRITICALITY: Yes | No

COMPONENT UNDER TEST:
- Primary: Component being tested
- Dependencies: Components it depends on
- Mocks Needed: List of mocks/stubs required

TEST APPROACH:
- Level: Unit (GTF) | Integration (RF) | Both
- Technique(s): [List design techniques]
- Complexity: Low | Medium | High

TEST CASES:
1. [Test Case Name]
   Input: [Describe inputs]
   Expected: [Describe expected output]
   
2. [Test Case Name]
   ...

TRACEABILITY:
- Related Requirements: [List related reqs]
- Design Document: [SDD reference]
- Test Report Link: [Link to results]

COVERAGE ASSESSMENT:
- Logic: 100% | 80% | etc.
- Paths: All | Most | Some
- Edge Cases: Covered | Partial | None
```

## Test Estimation

### Effort Estimation
For each requirement:
- **Analysis**: 0.5-1 day
- **Design**: 1-2 days
- **Implementation**: 2-5 days
- **Execution & Debug**: 1-3 days
- **Documentation**: 0.5-1 day
- **Review**: 0.5-1 day

### Example Estimate
```
Module: EyeBox Control
Requirement Count: 5 requirements
Average per Req: 4 days
Total: 20 days
Team Size: 2 developers
Timeline: 10 days (2 devs in parallel)
Buffer: 20% = 2 days
Final Estimate: 12 days
```

## Dependency Identification

### Create Dependency Matrix
```
Component | Depends On | Mock? | Stub? | Notes
EyeBox    | Motor Ctrl | Yes   | Yes   | Need motor mock for unit tests
EyeBox    | Power Mgmt | Yes   | Yes   | Mock power state signals
EyeBox    | CAN Bus    | No    | Yes   | Use CANoe simulation
```

## Risk Assessment

### Common Risks
```
RISK: Incomplete requirement specification
IMPACT: Test cases miss important scenarios
MITIGATION: Conduct thorough requirement review with stakeholders

RISK: Flaky tests (intermittent failures)
IMPACT: Reduces confidence in test results
MITIGATION: Implement proper timeouts and retry logic

RISK: Test environment unavailability
IMPACT: Cannot execute tests
MITIGATION: Use simulator/mock environment, CI/CD integration

RISK: Inadequate mocking
IMPACT: Tests don't isolate component properly
MITIGATION: Design mocks early, validate mock behavior
```

## Test Plan Document Outline

```
1. OVERVIEW
   - Purpose of test plan
   - Scope (what's tested)
   - Document version and history

2. TEST OBJECTIVES
   - Goals and success criteria
   - Quality targets (coverage %)

3. TEST SCOPE
   - In-scope items
   - Out-of-scope items
   - Assumptions

4. TEST APPROACH
   - Testing levels (unit, integration, system)
   - Test techniques
   - Automation strategy

5. TEST SCHEDULE
   - Timeline
   - Milestones
   - Resource allocation

6. REQUIREMENTS TO TEST MAPPING
   - Traceability matrix
   - Coverage summary

7. TEST ENVIRONMENT
   - Hardware setup
   - Software tools
   - CANoe configuration

8. TEST DELIVERABLES
   - Test cases
   - Test results
   - Coverage reports
   - Test artifacts

9. RISKS AND MITIGATION
   - Identified risks
   - Mitigation strategies
   - Contingency plans

10. APPROVAL
    - Sign-off from stakeholders
    - Test lead approval
```

## Test Implementation Workflow

```
1. Analyze Requirement
   ↓
2. Identify Test Scenarios
   ↓
3. Select Design Techniques
   ↓
4. Create Test Cases (design)
   ↓
5. Review Test Design
   ↓
6. Implement Tests (code)
   ↓
7. Execute Tests
   ↓
8. Analyze Results
   ↓
9. Report Coverage & Issues
   ↓
10. Close/Defer Gaps
```

## Coverage Metrics

### Requirement Coverage
- % of requirements with test cases
- % of requirements with passing tests
- Trace back failures to requirements

### Code Coverage (GTF)
- Line coverage: 80%+
- Branch coverage: 75%+
- Path coverage: 50%+

### Test Maturity Metrics
- % of tests in "released" state
- % of tests reviewed
- Average review cycles per test

## Quality Gates

Before release:
- ✅ All requirements have tests
- ✅ All tests passing
- ✅ Code coverage > 80%
- ✅ No critical/high risks open
- ✅ All tests documented and reviewed
- ✅ Traceability complete

## Related Skills
- `test-design-techniques` - For selecting design techniques
- `test-documentation-compliance` - For documenting test cases
- `robot-framework-integration` - For RF implementation
- Module-specific skills - For component-specific analysis

## Tools and Artifacts

- Requirement Management: JIRA / Requirement Tool
- Traceability: Excel/Database
- Test Results: GTF reports, RF logs
- Coverage: Code coverage tools, GTF coverage reports
- Documentation: Markdown, Word docs
