---
name: s3p-eyebox-module
description: >-
  Comprehensive reference for the S3P EyeBox module (stepper motor positioning, eye
  tracking, calibration) for creating targeted unit and integration tests. Use when:
  writing test cases for motor movement/position tracking; testing operating mode
  transitions (OPERATING/READY/SLEEP/WAIT_REFERENCE); working with DIDs 0xFD40-0xFD42.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# S3P EyeBox Module Skill

## Overview
This skill provides comprehensive information about the S3P EyeBox module for creating targeted unit and integration tests. The EyeBox is responsible for adjusting the head-up display projection to follow the driver's eye position, requiring precise motor control and state management.

## Module Purpose
The EyeBox module controls:
- **Motor movement**: Stepper motor positioning
- **Position tracking**: Current position monitoring
- **State management**: Operating modes and transitions
- **Safety features**: Boundary limits, error detection
- **Calibration**: Motor reference and synchronization

## Component Architecture

### External Interfaces
```
EyeBox Module
├── Motor Control Interface (PWM)
│   ├── Step signal (digital)
│   ├── Direction signal (digital)
│   └── Enable signal (digital)
│
├── Position Sensor Interface (Analog/Digital)
│   ├── Current position feedback
│   └── Reference position calibration
│
├── CAN Bus Interface (UDS)
│   ├── DID 0xFD40: EyeBox Status Read
│   ├── DID 0xFD41: Position Read
│   ├── DID 0xFD42: Motor Speed Read
│   └── Signal Interface (Sig_EyeBoxOpModeReq, etc.)
│
└── Power Management
    └── Power state from PowerControl module
```

### Operating Modes
```
Mode 0: OPERATING
- Motor idle, ready to move
- Normal operating mode
- Responds to position adjustment requests

Mode 1: READY
- Standby mode
- Motor can be activated
- Lower power consumption

Mode 2: SLEEP
- Minimal power mode
- Motor disabled
- No position adjustments possible

Mode 3: WAIT_REFERENCE
- Calibration mode
- Motor seeking reference position
- Cannot accept position requests

Mode 4: WAIT_MOVEMENT
- Motor in motion
- Position being adjusted
- Transition to OPERATING when complete
```

## Key Data Structures

### Status DID (0xFD40)
```
Field                   Range       Description
OperationMode          0-4         Current operating mode
AdjustmentStatus       0-1         0=Idle, 1=Adjusting
MotorReferencingStatus 0-1         0=Not referenced, 1=Referenced
ErrorCode              0x00-0xFF   Error condition codes
Reserved               -           Padding/future use
```

### Position DID (0xFD41)
```
Field                   Range       Description
CurrentPosition        0-100       Current motor position (%)
TargetPosition         0-100       Target position (%)
PositionValid          0-1         Position data validity flag
MotorSpeed             0-255       Current motor speed (steps/sec)
```

## Test Scenarios by Feature

### Feature 1: State Transitions
**Scenario: Valid State Transitions**
```
Transitions:
Shutdown → Standby  (PowerOn)
Standby  → Operating (OpModeRequest=0)
Operating → Sleep   (SleepRequest)
Sleep    → Operating (WakeRequest)
Any State → Shutdown (PowerOff)

Test Cases Needed:
1. Each valid transition from requirement
2. Each transition with proper timing
3. Signal updates during transition
4. No side effects after transition
```

**Scenario: Invalid State Transitions (Negative Testing)**
```
Invalid Paths:
Shutdown → Operating (should fail, must go through Standby)
Operating → Shutdown (should fail, must go through Ready first)
Sleep → Operating (should fail, must go through Ready)

Test Cases Needed:
1. Attempt invalid transition
2. Verify rejection/error code
3. State remains unchanged
4. No partial state changes
```

### Feature 2: Motor Position Control
**Scenario: Position Adjustment Workflow**
```
Workflow:
1. Request new position (0-100)
2. Motor starts moving
3. Position updates in real-time
4. Motor reaches target
5. Status changes to IDLE
6. Final position verified

Test Cases Needed:
1. Set position to MIN (0)
2. Set position to MAX (100)
3. Set position to MID (50)
4. Intermediate positions (25, 75)
5. Position unchanged requests
6. Rapid position changes
```

**Scenario: Motor Timeout & Error Handling**
```
Error Conditions:
- Motor stalled (no movement detected)
- Position sensor error
- Timeout during movement
- Concurrent movement requests

Test Cases Needed:
1. Motor timeout after 20 seconds
2. Stall detection and recovery
3. Error code generation
4. Safe state transition on error
5. Recovery procedure validation
```

### Feature 3: Calibration & Referencing
**Scenario: Motor Calibration Flow**
```
Calibration Process:
1. Receive calibration request
2. Transition to WAIT_REFERENCE mode
3. Move motor to reference position
4. Detect reference position marker
5. Reset position counter to 0
6. Transition to OPERATING mode

Test Cases Needed:
1. Calibration from OPERATING state
2. Calibration from STANDBY state
3. Calibration timeout (should fail)
4. Interruption during calibration
5. Validation of reference position
6. Position counter reset verification
```

### Feature 4: Power State Integration
**Scenario: Power Transitions**
```
Power Transitions:
OFF → INIT (initialization)
INIT → READY (motor check)
READY → ACTIVE (ready for commands)
ACTIVE → SLEEP (low power)
Any State → OFF (power down)

Test Cases Needed:
1. PowerOn/PowerOff signal handling
2. Power-up initialization sequence
3. Graceful power-down
4. State on power loss
5. Recovery after power restoration
```

### Feature 5: Boundary Conditions
**Scenario: Position Boundary Values**
```
Boundaries:
- Min Position: 0
- Max Position: 100
- Just Below Min: -1 (invalid)
- Just Above Max: 101 (invalid)

Test Cases Needed:
1. Set position to 0 (minimum)
2. Set position to 100 (maximum)
3. Set position to -1 (below range)
4. Set position to 101 (above range)
5. Overflow/underflow protection
```

**Scenario: Timeout Boundary Values**
```
Boundaries:
- Min Timeout: 1000ms
- Standard Timeout: 20000ms
- Max Timeout: 60000ms
- Below Min: 500ms (should fail)
- Above Max: 120000ms (should timeout)

Test Cases Needed:
1. Fast timeout (500ms - should fail)
2. Standard timeout (20s - should pass)
3. Extended timeout (60s - should pass)
4. Very long timeout (120s - should timeout)
```

### Feature 6: Signal Interface
**Scenario: CAN Signal Handling**
```
Signals from HUD Controller:
- Sig_HudOpModeReq: Requested operating mode
- Sig_HudProjectionReq: Projection on/off
- Sig_HudBrightnessReq: Brightness level
- Sig_HudSleepReq: Sleep mode request

Signals to HUD Controller:
- Sig_EyeBoxOpMode: Current mode
- Sig_EyeBoxStatus: Component status
- Sig_EyeBoxPosition: Current position
- Sig_EyeBoxError: Error flags

Test Cases Needed:
1. Signal value parsing
2. Invalid signal value rejection
3. Signal timeout handling
4. Signal frequency validation
5. Signal correlation with behavior
```

## Mock Requirements

### Motor Mock
```cpp
class MockMotor {
public:
    MOCK_METHOD(void, Move, (int direction, int speed));
    MOCK_METHOD(void, Stop, ());
    MOCK_METHOD(int, GetPosition, ());
    MOCK_METHOD(bool, IsReferenced, ());
    MOCK_METHOD(void, Calibrate, ());
};
```

### CAN Bus Mock
```cpp
class MockCANBus {
public:
    MOCK_METHOD(void, SendMessage, (uint32_t id, const uint8_t* data, uint8_t len));
    MOCK_METHOD(bool, ReceiveMessage, (uint32_t* id, uint8_t* data, uint8_t* len));
    MOCK_METHOD(void, SetSignal, (const std::string& name, int value));
    MOCK_METHOD(int, GetSignal, (const std::string& name));
};
```

### Power Management Mock
```cpp
class MockPowerManager {
public:
    MOCK_METHOD(uint8_t, GetPowerState, ());
    MOCK_METHOD(void, RequestMode, (uint8_t mode));
    MOCK_METHOD(bool, IsPowerAvailable, ());
};
```

## Key Test Data

### Position Test Values
```
BOUNDARY VALUES:
- Minimum Valid: 0
- Just Below Min: -1
- Maximum Valid: 100
- Just Above Max: 101
- Mid-range: 50
- Quartiles: 25, 75

EQUIVALENCE PARTITIONS:
- Invalid Negative: -1, -100
- Valid Low: 0-25
- Valid Mid: 26-75
- Valid High: 76-100
- Invalid High: 101, 1000
```

### Timeout Test Values
```
BOUNDARY VALUES:
- Minimum: 1000ms
- Just Below Min: 999ms
- Standard: 20000ms
- Maximum: 60000ms
- Just Above Max: 60001ms

EQUIVALENCE PARTITIONS:
- Too Short: 100ms, 500ms, 999ms
- Valid Short: 1000ms, 5000ms
- Valid Long: 20000ms, 30000ms
- Valid Extended: 40000ms, 60000ms
- Invalid Long: 120000ms
```

### State Test Values
```
MODE VALUES:
- Operating: 0
- Ready: 1
- Sleep: 2
- WaitReference: 3
- WaitMovement: 4
- Invalid: 5, 255

STATUS FLAGS:
- Idle: 0
- Adjusting: 1
- Referenced: 1
- NotReferenced: 0
```

## Error Codes
```
0x00: No error
0x01: Motor timeout
0x02: Position out of range
0x03: Invalid mode transition
0x04: Calibration failed
0x05: Motor stalled
0x06: Position sensor error
0x07: CAN communication error
0x08: Power insufficient
0xFF: Unknown error
```

## Common Test Patterns

### Pattern 1: State Transition Test
```robot
Test Case - State Transition [FromState] To [ToState]
    Initialize Component To State    ${from_state}
    Trigger State Change    ${trigger_signal}    ${trigger_value}
    Wait For State Change    ${to_state}    timeout=5s
    Verify State    ${to_state}
    Verify Signals Updated    [expected_signals]
    Verify No Error Codes
```

### Pattern 2: Position Adjustment Test
```robot
Test Case - Adjust Position To [Position]
    Set Position Request    ${position}
    Wait For Motor Start
    Monitor Position Change
    Wait For Motor Stop
    Verify Final Position    ${position}
    Verify Movement Time Within Limits
    Verify No Error Codes
```

### Pattern 3: Error Handling Test
```robot
Test Case - Handle [ErrorScenario]
    Setup Error Condition    ${condition}
    Trigger Operation
    Wait For Error Detection
    Verify Error Code    ${expected_error}
    Verify Safe State
    Verify Recovery Path
```

### Pattern 4: Boundary Test
```robot
Test Case - Position Boundary [BoundaryValue]
    Set Position Request    ${boundary_value}
    [If Valid]
        Verify Position Set
    [If Invalid]
        Verify Rejection
        Verify No State Change
```

## GTF Unit Test Structure

```cpp
TEST_F(EyeBoxControlFixture, ModeTransitionOperatingToSleep)
{
    // Setup: Component in OPERATING mode
    EXPECT_CALL(motor_mock, GetPosition).WillRepeatedly(Return(50));
    EXPECT_CALL(power_mock, GetPowerState).WillOnce(Return(POWER_ACTIVE));
    
    // Execute: Request sleep mode
    eyebox.SetModeRequest(MODE_SLEEP);
    
    // Verify: Mode changed, motor stopped
    EXPECT_EQ(eyebox.GetCurrentMode(), MODE_SLEEP);
    EXPECT_CALL(motor_mock, Stop).Times(1);
}

TEST_F(EyeBoxControlFixture, PositionAdjustmentBoundaryMinimum)
{
    eyebox.SetMode(MODE_OPERATING);
    
    eyebox.SetPositionRequest(0);  // Minimum valid
    eyebox.ExecuteMotorControl();
    
    EXPECT_EQ(eyebox.GetPosition(), 0);
    EXPECT_FALSE(eyebox.HasError());
}

TEST_F(EyeBoxControlFixture, PositionAdjustmentOutOfRange)
{
    eyebox.SetMode(MODE_OPERATING);
    
    eyebox.SetPositionRequest(101);  // Above maximum
    
    EXPECT_TRUE(eyebox.HasError());
    EXPECT_EQ(eyebox.GetErrorCode(), ERROR_OUT_OF_RANGE);
}
```

## Robot Framework Integration Test Structure

```robot
*** Settings ***
Documentation  Integration Tests for S3P_EyeBox Module
Resource       ../../resources/S3P_EyeBox/s3p_eyebox_pf.robot
Resource       ../../resources/S3P_EyeBox/s3p_eyebox_prj.robot
Resource       ../../resources/S3P_Common/s3p_common_pf.robot

*** Test Cases ***
EyeBox State Transition From Operating To Sleep
    [Documentation]    Validates state transition with signal verification
    [Tags]    integration    state-transition    eyebox
    Initialize EyeBox To Operating Mode
    Request Sleep Mode
    Verify Mode Changed To Sleep
    Verify Motor Idle
    Verify No Error Codes

EyeBox Position Boundary Value Minimum
    [Documentation]    Tests position at minimum boundary (0)
    [Tags]    integration    boundary-value    eyebox
    Initialize EyeBox To Operating Mode
    Request Position    0
    Wait For Motor Stop
    Verify Position    0
    Verify Movement Completed

EyeBox Position Boundary Value Maximum
    [Documentation]    Tests position at maximum boundary (100)
    [Tags]    integration    boundary-value    eyebox
    Initialize EyeBox To Operating Mode
    Request Position    100
    Wait For Motor Stop
    Verify Position    100
    Verify Movement Completed

EyeBox Position Out Of Range Rejected
    [Documentation]    Tests rejection of out-of-range position
    [Tags]    integration    negative-test    eyebox
    Initialize EyeBox To Operating Mode
    Request Position    101
    Verify Position Request Rejected
    Verify Position Unchanged
    Verify Error Code    OUT_OF_RANGE
```

## Coverage Goals

### Code Coverage Targets
- **Line Coverage**: ≥85% (branch transitions critical)
- **Branch Coverage**: ≥80% (all conditions)
- **Path Coverage**: ≥70% (state machine paths)

### Functional Coverage
- ✓ All valid state transitions
- ✓ All mode combinations
- ✓ Boundary positions (0, 50, 100)
- ✓ Error conditions (timeout, stall, out-of-range)
- ✓ Power state transitions
- ✓ Signal handling
- ✓ Calibration flow

## Related Skills
- `robot-framework-integration` - For RF test implementation
- `test-design-techniques` - For test design patterns
- `test-documentation-compliance` - For test documentation
- `project-config-utilities` - For EyeBox-specific constants
- `test-strategy-planning` - For test planning

## Module-Specific Files

Location: `resources/S3P_EyeBox/`
- `s3p_eyebox_pf.robot` - Platform-specific keywords
- `s3p_eyebox_prj.robot` - Project-specific utilities

Location: `tests/S3P_EyeBox/`
- `s3p_eyebox_ITS_pf.robot` - Integration test suite
- `s3p_eyebox_ITS_prj.robot` - Project-specific test utilities

## Troubleshooting Common Issues

### Issue: Motor Movement Not Detected
- Check motor mock expectations
- Verify signal routing to motor driver
- Validate motor enable signal

### Issue: Timeout Errors in Calibration
- Increase calibration timeout
- Verify reference position sensor
- Check motor speed configuration

### Issue: Position Feedback Incorrect
- Validate position sensor data
- Check position counter initialization
- Verify calibration state

### Issue: State Transitions Failing
- Verify current state matches precondition
- Check signal value ranges
- Validate state machine logic
