---
name: s3p-sits-design-techniques
description: >-
  Standard test design techniques (Boundary Value Analysis, Equivalence Partitioning,
  State Transition, Decision Table, Error Guessing, Scenario Testing) for creating
  comprehensive, efficient S3P HUD test cases. Use when: selecting a test design
  technique for a requirement; identifying edge cases and critical scenarios.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# Test Design Techniques Skill

## Overview
This skill describes standard test design techniques used to create comprehensive, efficient test cases for the S3P HUD project. Each technique has specific applications and helps identify edge cases and critical scenarios.

## When to Use Each Technique

Use this decision matrix to select appropriate techniques:

| Requirement Type | Technique | Best For |
|-----------------|-----------|----------|
| Numeric ranges | Boundary Value Analysis | Edge cases, min/max validation |
| Valid/Invalid inputs | Equivalence Partitioning | Coverage with minimal tests |
| State-based behavior | State Transition Testing | Workflows, mode changes |
| Complex conditions | Decision Table Testing | Multiple condition combinations |
| Error scenarios | Error Guessing | Robustness, fault handling |
| Complex workflows | Scenario Testing | End-to-end flows |

## Technique 1: Equivalence Partitioning

### Concept
Divide input domain into groups (partitions) where all values behave similarly. Test one representative value from each partition.

### Partitions Identify
- **Valid partitions**: Inputs the system should accept
- **Invalid partitions**: Inputs the system should reject
- **Boundary partitions**: Edge cases between valid and invalid

### Example 1: EyeBox Operating Modes
```
System accepts operating modes 0-3 for different states
System rejects negative values and values > 3

PARTITIONS:
- Invalid Negative:    -1, -100        (Test: -1)
- Valid Modes:         0, 1, 2, 3      (Test: 0, 2, 3)
- Invalid High:        4, 100, 1000    (Test: 4)

TEST CASES:
1. Set mode to -1         → Reject
2. Set mode to 0          → Accept, Operating
3. Set mode to 1          → Accept, Standby
4. Set mode to 3          → Accept, Shutdown
5. Set mode to 4          → Reject
```

### Example 2: Voltage Ranges
```
Valid voltage: 10V - 18V (automotive range)
Below minimum: < 10V
Normal operation: 10V - 18V
Above maximum: > 18V

PARTITIONS:
- Under Voltage:   5V, 8V, 9.9V      (Test: 5V)
- Normal Voltage:  10V, 14V, 18V     (Test: 14V)
- Over Voltage:    18.1V, 20V, 30V   (Test: 20V)

TEST CASES:
1. Apply 5V        → Under-voltage error
2. Apply 14V       → Normal operation
3. Apply 20V       → Over-voltage error
```

### Test Case Template
```robot
Test Case - Equivalence Partition [Partition Name]
    [Documentation]    Tests [component] with [partition] value
    ...
    ...    PARTITION: [partition category]
    ...    REPRESENTATIVE VALUE: [value to test]
    ...    EXPECTED BEHAVIOR: [system response]
    [Tags]    equivalence-partition    ${component}
    
    # Setup
    Setup Component    ${default_state}
    
    # Execute with test value
    Send Input    ${test_value}
    
    # Verify partition response
    Verify Expected Response    ${expected_result}
```

## Technique 2: Boundary Value Analysis

### Concept
Test values at and just beyond the boundaries of input ranges. Boundaries are error-prone areas.

### Boundary Types
- **Lower boundary**: Minimum valid value and just below
- **Upper boundary**: Maximum valid value and just above
- **Closed/Open**: Inclusive vs exclusive boundaries

### Boundary Test Strategy
For range [Min, Max], test:
- `Min - 1` (just below minimum)
- `Min` (at minimum)
- `Min + 1` (just above minimum)
- `Mid` (middle value)
- `Max - 1` (just below maximum)
- `Max` (at maximum)
- `Max + 1` (just above maximum)

### Example 1: EyeBox Position Range
```
Valid positions: 0 to 100 (inclusive)

BOUNDARY VALUES:
- Just Below Min:  -1
- At Min:          0
- Just Above Min:  1
- Middle:          50
- Just Below Max:  99
- At Max:          100
- Just Above Max:  101

TEST CASES:
1. Position -1    → Out of range error
2. Position 0     → Valid, start position
3. Position 1     → Valid
4. Position 50    → Valid, middle
5. Position 99    → Valid
6. Position 100   → Valid, end position
7. Position 101   → Out of range error
```

### Example 2: Timeout Values
```
Valid timeout: 1000ms to 10000ms

BOUNDARY VALUES:
- 999ms    → Too short
- 1000ms   → Minimum (accept)
- 1001ms   → Above minimum
- 5500ms   → Middle
- 9999ms   → Below maximum
- 10000ms  → Maximum (accept)
- 10001ms  → Too long

TEST CASES:
1. Timeout 999ms    → Timeout error
2. Timeout 1000ms   → Success
3. Timeout 10000ms  → Success
4. Timeout 10001ms  → Invalid range error
```

### Test Case Template
```robot
Test Case - Boundary Value [Description]
    [Documentation]    Tests [component] at boundary: [boundary description]
    ...
    ...    BOUNDARY: [lower/upper/both]
    ...    TEST VALUES: [min-1], [min], [min+1], ..., [max-1], [max], [max+1]
    [Tags]    boundary-value    ${component}
    
    FOR    ${boundary_value}    IN    @{boundary_values}
        ${expected}=    Get Expected For Boundary    ${boundary_value}
        Send Request    value=${boundary_value}
        Verify Result Matches    ${expected}
    END
```

## Technique 3: State Transition Testing

### Concept
Identify all states and possible transitions between them. Test each valid transition and reject invalid ones.

### State Diagram Example: EyeBox Control
```
States: Shutdown → Standby → Ready → OperatingMode → Sleep → Shutdown
         └─────────────────────────────────────────────────┘

TRANSITIONS:
- Shutdown → Standby: PowerOn signal
- Standby → Ready: OpMode request
- Ready → OperatingMode: Projection on signal
- OperatingMode → Sleep: Sleep request
- Sleep → Ready: Wake signal
- Any State → Shutdown: Power off

INVALID TRANSITIONS (should be rejected):
- Shutdown → Ready (must go through Standby first)
- Sleep → OperatingMode (must go through Ready)
- OperatingMode → Shutdown (must transition through intermediate states)
```

### Transition Test Matrix
```
FROM STATE    TO STATE           TRIGGER              EXPECTED RESULT
Shutdown      Standby            PowerOn              Success + signal update
Shutdown      Ready              OpMode request       Error (invalid transition)
Standby       Ready              OpMode request       Success
Ready         OperatingMode      ProjectionOn         Success
OperatingMode Sleep              SleepRequest         Success
Sleep         Shutdown           PowerOff             Success + cleanup
```

### Test Case Template
```robot
Test Case - State Transition From [FromState] To [ToState]
    [Documentation]    Tests valid transition from [FromState] to [ToState]
    ...
    ...    TRANSITION: [FromState] → [ToState]
    ...    TRIGGER: [signal/event]
    ...    EXPECTED SIGNALS: [list of expected signal values]
    [Tags]    state-transition    ${component}
    
    # Setup initial state
    Transition To State    ${from_state}
    Verify Current State    ${from_state}
    
    # Execute transition
    Trigger Event    ${transition_trigger}
    
    # Verify new state
    Verify Current State    ${to_state}
    Verify Signals Updated    ${expected_signals}
    Verify No Side Effects    ${from_state}    ${to_state}

Test Case - Invalid Transition Rejected [FromState] To [InvalidState]
    [Documentation]    Tests that invalid transition is rejected
    [Tags]    state-transition    negative-test    ${component}
    
    Transition To State    ${from_state}
    
    # Attempt invalid transition
    TRY
        Trigger Invalid Event    ${invalid_transition}
        Fail    Should have rejected invalid transition
    EXCEPT    InvalidTransition
        Log    Correctly rejected invalid transition
    END
    
    # Verify state unchanged
    Verify Current State    ${from_state}
```

## Technique 4: Error Guessing

### Concept
Use experience and intuition to guess likely error-prone areas. Based on common mistakes and failure patterns.

### Common Error Scenarios
- **Null/Uninitialized**: Null pointers, uninitialized variables
- **Off-by-One**: Array bounds, loop counters
- **Division by Zero**: Mathematical operations
- **Timing**: Race conditions, timeouts
- **Resource Leaks**: Memory, file handles
- **State Inconsistency**: Multiple state variables out of sync
- **Communication Errors**: CAN frame corruption, checksum failures
- **Parameter Combinations**: Unexpected parameter combinations

### Example: EyeBox Motor Control
```
LIKELY ERROR SCENARIOS:
1. Motor requested while already moving        → Collision handling
2. Position out of range for acceleration      → Boundary case
3. Power loss during movement                  → State recovery
4. Invalid calibration data                    → Data validation
5. Concurrent motor commands                   → Arbitration logic
6. Timeout without motor response              → Watchdog/timeout handling
7. Incorrect axis for position query           → Parameter validation
8. Motor stalled (not responding)              → Fault detection
```

### Test Case Template
```robot
Test Case - Error Scenario [Description]
    [Documentation]    Tests handling of [error scenario]
    ...
    ...    SCENARIO: [error description]
    ...    LIKELY CAUSE: [what goes wrong]
    ...    EXPECTED HANDLING: [how system should respond]
    [Tags]    error-guessing    robustness    ${component}
    
    # Setup to trigger error
    Setup Error Condition    ${condition}
    
    # Trigger operation
    Perform Operation    ${parameters}
    
    # Verify error handling
    Verify Error Detected
    Verify Error Code    ${expected_error}
    Verify Graceful Degradation
    Verify Recovery Path    ${recovery_action}
```

## Technique 5: Decision Table Testing

### Concept
Create table of conditions and their combinations, then test each row.

### Example: Light Activation Logic
```
CONDITION COMBINATIONS:
| Position | Brightness | AutoMode | Expected |
|----------|-----------|----------|----------|
| 0        | 0         | Off      | Off      |
| 0        | 50        | Off      | Off      |
| 1        | 50        | Off      | On       |
| 1        | 50        | On       | On       |
| 1        | 0         | On       | Off      |
| 2        | 100       | Off      | On       |
| 2        | 100       | On       | On       |
```

### Test Case Template
```robot
Test Case - Decision Table Row [RowNumber]
    [Documentation]    Tests combination: [condition values]
    [Tags]    decision-table    ${component}
    
    Set Condition    Position    ${position}
    Set Condition    Brightness   ${brightness}
    Set Condition    AutoMode     ${automode}
    
    Trigger Logic
    
    Verify Output    ${expected_output}
```

## Scenario Testing

### Concept
Test realistic end-to-end workflows combining multiple operations.

### Example: HUD Startup Scenario
```
SCENARIO: Complete HUD startup with eye tracking

STEPS:
1. Power on HUD
2. Wait for system initialization (should complete in < 5s)
3. Verify all components in ready state
4. Request projection on
5. Eye tracking calibration runs
6. Verify projection active and eye tracking enabled
7. Request brightness adjustment
8. Verify brightness changes applied
9. Perform state transitions
10. Shutdown gracefully

CHECKPOINTS:
- Each step completes within timeout
- All state signals updated correctly
- No error codes generated
- System stable after completion
```

## Combining Techniques

For comprehensive coverage, combine techniques:

```robot
Test Suite - EyeBox Complete Coverage
    # Equivalence Partitioning: mode values
    Test Mode Invalid Negative
    Test Mode Valid Range
    Test Mode Invalid High
    
    # Boundary Value Analysis: position
    Test Position At Minimum
    Test Position At Maximum
    Test Position Just Beyond Range
    
    # State Transitions
    Test Valid State Transitions
    Test Invalid State Transitions
    
    # Error Guessing
    Test Motor Timeout Error
    Test Concurrent Commands Error
    Test Power Loss Recovery
    
    # Scenario Testing
    Test Complete Startup Scenario
    Test Complete Shutdown Scenario
```

## Test Case Template Summary
```robot
*** Test Cases ***
Test Case Name - Technique [TechniqueName]
    [Documentation]    One-line summary
    ...
    ...    TECHNIQUE: [Equivalence Partitioning | Boundary Value | State Transition | Error Guessing | Decision Table]
    ...    OBJECTIVE: [What is being tested]
    ...    TEST DATA: [Input values]
    ...    EXPECTED RESULT: [What should happen]
    [Tags]    ${technique_tag}    ${component_tag}
    
    # Setup
    # Execute
    # Verify
```

## Related Skills
- `test-documentation-compliance` - For proper test documentation
- `robot-framework-integration` - For RF test implementation
- `test-strategy-planning` - For test planning using these techniques
