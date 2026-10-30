---
name: s3p-powercontrol-module
description: >-
  Comprehensive reference for the S3P Power Control module (power distribution, voltage
  regulation, thermal management, power states) for creating targeted unit and
  integration tests. Use when: writing test cases for power mode transitions or fault
  detection; testing voltage/current monitoring; working with DIDs 0xFD30-0xFD34.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# S3P Power Control Module Skill

## Overview
This skill provides comprehensive information about the S3P Power Control module for creating targeted unit and integration tests. The Power Control module is responsible for managing power distribution, voltage regulation, thermal management, and system power states in the S3P SITS system.

## Module Purpose
The Power Control module manages:
- **Power distribution**: Managing power to subsystems
- **Voltage regulation**: Maintaining stable voltage levels
- **Current monitoring**: Tracking power consumption
- **Thermal management**: Temperature monitoring and control
- **Power modes**: Transitioning between power states
- **Fault detection**: Power anomaly detection and recovery

## Component Architecture

### External Interfaces
```
Power Control Module
├── Power Input Interface
│   ├── Main battery input (12V/24V)
│   ├── Input current monitoring
│   └── Input protection (fuse, breaker)
│
├── Power Distribution Interface
│   ├── ECU supply rail
│   ├── Motor supply rail
│   ├── Sensor supply rail
│   └── Communication supply rail
│
├── Monitoring Interface
│   ├── Voltage sensing (multiple rails)
│   ├── Current sensing (total and per-rail)
│   ├── Temperature sensors
│   └── Fault detection
│
├── CAN Bus Interface (UDS)
│   ├── DID 0xFD30: System Status
│   ├── DID 0xFD31: Power State
│   ├── DID 0xFD32: Voltage Levels
│   ├── DID 0xFD33: Current Consumption
│   └── DID 0xFD34: Temperature
│
└── Control Signals
    ├── Sleep/Wake requests
    ├── Power mode transitions
    └── Emergency shutdown
```

### Power States
```
State 0: OFF
- System powered down
- Minimal current draw (standby only)
- No subsystem operation

State 1: INIT
- System initializing
- Power rails being stabilized
- Self-tests running
- Transition to READY

State 2: READY
- All subsystems ready
- Normal operating voltage
- Can accept requests
- Low power consumption

State 3: ACTIVE
- All subsystems powered
- Full functionality available
- Higher current consumption
- Normal operation

State 4: SLEEP
- Reduced power mode
- Non-critical systems powered down
- Quick wake-up capability
- Minimal current draw

State 5: THERMAL_THROTTLE
- Temperature exceeding threshold
- Reduced functionality
- Monitoring active
- Recovery when cooled

State 6: FAULT
- System error detected
- Protection mechanisms active
- Manual intervention required
- Safe state maintenance
```

## Key Data Structures

### Power State DID (0xFD31)
```
Field                   Range       Description
CurrentPowerState      0-6         Current operational state
TargetPowerState       0-6         Requested next state
StateTransitionTime    0-65535     Time in ms since last transition
IsStable               0-1         0=Transitioning, 1=Stable
```

### Voltage Levels DID (0xFD32)
```
Field                   Range       Description
MainBatteryVoltage     0-255       Input voltage (x0.1V)
ECUSupplyVoltage       0-255       ECU rail voltage (x0.1V)
MotorSupplyVoltage     0-255       Motor rail voltage (x0.1V)
SensorSupplyVoltage    0-255       Sensor rail voltage (x0.1V)
CommSupplyVoltage      0-255       Communication rail voltage (x0.1V)
```

### Current Consumption DID (0xFD33)
```
Field                   Range       Description
InputCurrent           0-65535     Total input current (x0.01A)
ECUCurrent             0-65535     ECU rail current (x0.01A)
MotorCurrent           0-65535     Motor rail current (x0.01A)
SensorCurrent          0-65535     Sensor rail current (x0.01A)
CommCurrent            0-65535     Communication rail current (x0.01A)
```

### Temperature DID (0xFD34)
```
Field                   Range       Description
PCBTemperature         0-255       Main PCB temp in °C
PowerStageTemperature  0-255       Power stage temp in °C
MaxTemperature         0-255       Maximum measured temp
ThermalStatus          0-3         0=Normal, 1=Warn, 2=Throttle, 3=Critical
```

## Test Scenarios by Feature

### Feature 1: Power State Transitions
**Scenario: Valid State Transitions**
```
Transitions:
OFF → INIT (PowerOn signal)
INIT → READY (Initialization complete)
READY → ACTIVE (Request active mode)
ACTIVE → SLEEP (Request sleep mode)
SLEEP → ACTIVE (Wake signal)
Any State → OFF (PowerOff signal)
Any State → FAULT (Error detected)
FAULT → READY (Manual recovery)

Test Cases Needed:
1. Each valid transition
2. Proper timing verification
3. Voltage stabilization checks
4. State signal updates
5. Side effects validation (currents, temps)
```

**Scenario: Invalid State Transitions (Negative Testing)**
```
Invalid Paths:
INIT → SLEEP (should fail, must go to READY first)
OFF → ACTIVE (should fail, must go through INIT)
SLEEP → INIT (should fail, invalid transition)

Test Cases Needed:
1. Attempt invalid transitions
2. Verify rejection/error code
3. State remains unchanged
4. No partial state changes
```

### Feature 2: Voltage Regulation
**Scenario: Voltage Stability and Regulation**
```
Test Range:
- Input voltage: 9V - 16V (automotive range)
- Expected regulation: ±0.5V from nominal
- Ripple: < 100mV
- Response time: < 500ms to load change

Test Cases Needed:
1. Input voltage at minimum (9V)
2. Input voltage at maximum (16V)
3. Normal operating voltage (12V/24V)
4. Sudden load increase (motor start)
5. Sudden load decrease
6. Ripple and noise analysis
7. Line regulation (PARD analysis)
```

**Scenario: Voltage Failure Detection**
```
Failure Scenarios:
- Under-voltage (< 9V)
- Over-voltage (> 16V)
- Voltage dropout (sudden loss)
- Single rail failure
- Output voltage corruption

Test Cases Needed:
1. Under-voltage detection
2. Over-voltage detection
3. Voltage dropout handling
4. Per-rail fault detection
5. Safe shutdown on fault
6. Error code generation
```

### Feature 3: Current Management
**Scenario: Current Monitoring and Limiting**
```
Current Limits:
- Total system: 30A max
- Motor rail: 10A max
- Sensor rail: 2A max
- Communication rail: 1A max
- ECU rail: 3A max

Test Cases Needed:
1. Monitor currents within limits
2. Detect over-current conditions
3. Implement current limiting
4. Log peak currents
5. Alert on threshold approach (80%, 90%, 100%)
6. Emergency shutdown on critical over-current
```

### Feature 4: Thermal Management
**Scenario: Temperature Monitoring and Throttling**
```
Temperature Thresholds:
- Normal: 0-70°C
- Warning: 70-90°C
- Throttle: 90-110°C
- Critical: > 110°C

Test Cases Needed:
1. Temperature monitoring accuracy
2. Warning threshold detection
3. Throttling activation at 90°C
4. Functionality reduction during throttle
5. Recovery when cooled below 80°C
6. Critical shutdown at 110°C
```

### Feature 5: Sleep Mode Management
**Scenario: Sleep Mode Entry and Exit**
```
Sleep Mode:
- Reduces non-critical power draw
- Maintains communication capability
- Quick wake-up (< 1s to full active)
- Maintains state information

Test Cases Needed:
1. Enter sleep from READY
2. Enter sleep from ACTIVE
3. Wake from sleep stimulus
4. Wake timing verification
5. State preservation check
6. Current draw verification in sleep
7. Concurrent wake signals
```

### Feature 6: Power-Up Initialization Sequence
**Scenario: Controlled Power-Up**
```
Sequence:
1. Power detection
2. Voltage stabilization (< 100ms)
3. System initialization
4. Self-tests
5. Ready for operation

Test Cases Needed:
1. Gradual voltage ramp-up
2. Voltage stability during init
3. Init timeout handling
4. Self-test verification
5. Recovery from failed init
```

## Mock Requirements

### ADC Mock (Analog to Digital Converter)
```cpp
class MockADC {
public:
    MOCK_METHOD(uint16_t, ReadVoltage, (uint8_t channel));
    MOCK_METHOD(uint16_t, ReadCurrent, (uint8_t channel));
    MOCK_METHOD(uint16_t, ReadTemperature, (uint8_t channel));
    MOCK_METHOD(bool, IsCalibrated, ());
};
```

### Power Rail Mock
```cpp
class MockPowerRail {
public:
    MOCK_METHOD(void, Enable, ());
    MOCK_METHOD(void, Disable, ());
    MOCK_METHOD(bool, IsEnabled, ());
    MOCK_METHOD(void, SetCurrentLimit, (uint16_t limit_mA));
    MOCK_METHOD(uint16_t, GetCurrentLimit, ());
};
```

### Watchdog Mock
```cpp
class MockWatchdog {
public:
    MOCK_METHOD(void, Enable, ());
    MOCK_METHOD(void, Disable, ());
    MOCK_METHOD(void, Kick, ());
    MOCK_METHOD(bool, WasTriggered, ());
};
```

## Key Test Data

### Voltage Test Values
```
BOUNDARY VALUES:
- Input Minimum: 9V
- Just Below Min: 8.9V
- Input Maximum: 16V
- Just Above Max: 16.1V
- Normal 12V: 12V, 13V, 14V
- Normal 24V: 24V, 25V, 26V

EQUIVALENCE PARTITIONS:
- Critical Low: 0V, 5V, 8.9V
- Valid Low: 9V, 10V, 11V
- Valid Mid: 12V, 13V, 14V
- Valid High: 15V, 16V
- Critical High: 16.1V, 20V, 30V
```

### Current Test Values
```
BOUNDARY VALUES:
- Minimum: 0A
- Normal Idle: 1A
- Normal Active: 15A
- Maximum Safe: 30A
- Over-Current: 31A, 35A, 50A

EQUIVALENCE PARTITIONS:
- Standby: 0A, 0.5A, 1A
- Normal: 5A, 15A, 25A
- Over-Current: 31A, 40A, 60A
```

### Temperature Test Values
```
BOUNDARY VALUES:
- Minimum: -10°C
- Room Temp: 25°C
- Normal Op: 50°C, 70°C
- Warning Threshold: 70°C
- Throttle Threshold: 90°C
- Critical Threshold: 110°C
- Dangerous: 120°C, 150°C

EQUIVALENCE PARTITIONS:
- Cold: -10°C, 0°C, 25°C
- Normal: 50°C, 70°C
- Warm: 75°C, 85°C
- Hot: 95°C, 105°C
- Critical: 115°C, 130°C
```

## Error Codes
```
0x00: No error
0x01: Under-voltage detected
0x02: Over-voltage detected
0x03: Over-current detected
0x04: Over-temperature detected
0x05: Rail failure
0x06: Initialization timeout
0x07: Thermal throttling active
0x08: Watchdog timeout (recovery)
0x09: Supply rail instability
0xFF: Unknown power error
```

## Common Test Patterns

### Pattern 1: Voltage Transition Test
```robot
Test Case - Voltage Transition [FromVoltage] To [ToVoltage]
    Apply Voltage    ${from_voltage}
    Wait For Stabilization    5s
    Verify Voltage Stable    ${from_voltage}
    Ramp Voltage To    ${to_voltage}
    Monitor Voltage During Transition
    Verify Final Voltage    ${to_voltage}
    Verify No Errors During Transition
```

### Pattern 2: Current Limit Test
```robot
Test Case - Current Limit [RailName] Enforcement
    Enable Power Rail    ${rail_name}
    Set Current Limit    ${limit}
    Gradually Increase Load    until_current=${limit}
    Verify Current Capped    at=${limit}
    Verify No Over-Current Shutdown
    Remove Load
    Verify Rail Still Functional
```

### Pattern 3: Power State Transition Test
```robot
Test Case - Power State Transition [FromState] To [ToState]
    Set Power State    ${from_state}
    Verify State Stable    ${from_state}
    Request State Change    ${to_state}
    Monitor Transition
    Verify Final State    ${to_state}
    Verify Voltages Correct
    Verify Currents Normalized
    Verify No Error Codes
```

### Pattern 4: Thermal Test
```robot
Test Case - Thermal Throttling At [Temperature]
    Setup Thermal Chamber    ${temperature}
    Wait For Thermal Equilibrium
    Verify System Active
    Monitor Performance    baseline
    Verify Throttling Triggered    at=${temperature}
    Monitor Reduced Performance
    Verify Safe Operation
```

## GTF Unit Test Structure

```cpp
TEST_F(PowerControlFixture, VoltageRegulationWithinTolerance)
{
    // Setup: Apply input voltage
    EXPECT_CALL(adc_mock, ReadVoltage(MAIN_VOLTAGE_CHANNEL))
        .WillRepeatedly(Return(VOLTAGE_12V_ADC_VALUE));
    
    // Execute: Get regulated output
    uint16_t output = power_control.GetOutputVoltage();
    
    // Verify: Output within ±0.5V
    EXPECT_GE(output, VOLTAGE_12V_MIN_ADC);
    EXPECT_LE(output, VOLTAGE_12V_MAX_ADC);
}

TEST_F(PowerControlFixture, OverVoltageDetection)
{
    EXPECT_CALL(adc_mock, ReadVoltage(MAIN_VOLTAGE_CHANNEL))
        .WillRepeatedly(Return(VOLTAGE_16_1V_ADC_VALUE));
    
    power_control.Update();
    
    EXPECT_TRUE(power_control.HasError());
    EXPECT_EQ(power_control.GetErrorCode(), ERROR_OVERVOLTAGE);
}

TEST_F(PowerControlFixture, CurrentLimitingActivation)
{
    EXPECT_CALL(current_mock, ReadCurrent(MOTOR_RAIL))
        .WillRepeatedly(Return(CURRENT_31A_VALUE));
    
    power_control.Update();
    
    EXPECT_TRUE(power_control.IsCurrentLimited(MOTOR_RAIL));
    EXPECT_LE(power_control.GetActualCurrent(MOTOR_RAIL), 
              power_control.GetCurrentLimit(MOTOR_RAIL));
}
```

## Robot Framework Integration Test Structure

```robot
*** Settings ***
Documentation  Integration Tests for S3P Power Control Module
Resource       ../../resources/S3P_PowerControl/s3p_powercontrol_pf.robot
Resource       ../../resources/S3P_Common/s3p_common_pf.robot

*** Test Cases ***
Power State Transition From Off To Ready
    [Documentation]    Validates power-up sequence
    [Tags]    integration    power-state    powercontrol
    Apply Voltage    12V    Normal Current
    Wait For Power Initialization    5s
    Verify Power State    READY
    Verify All Rails Active
    Verify Voltages Within Range
    Verify No Error Codes

Voltage Regulation Boundary Minimum
    [Documentation]    Tests minimum input voltage (9V)
    [Tags]    integration    boundary-value    voltage
    Apply Voltage    9V    Normal Current
    Wait For Stabilization    2s
    Verify Output Voltage Within Range    11.5V-12.5V
    Monitor For Errors    5s
    Verify No Warnings

Voltage Regulation Boundary Maximum
    [Documentation]    Tests maximum input voltage (16V)
    [Tags]    integration    boundary-value    voltage
    Apply Voltage    16V    Normal Current
    Wait For Stabilization    2s
    Verify Output Voltage Within Range    11.5V-12.5V
    Monitor For Errors    5s
    Verify No Warnings

Over-Current Detection And Limiting
    [Documentation]    Tests current limiting at motor rail
    [Tags]    integration    robustness    powercontrol
    Enable Power Rail    MotorRail
    Set Motor Rail Current Limit    10A
    Gradually Increase Load    until_current=10.5A
    Verify Current Limited    at=10A
    Verify Error Code    OVER_CURRENT
    Verify Motor Rail Still Enabled
    Verify Recovery Path

Sleep Mode Power Consumption
    [Documentation]    Verifies reduced current in sleep
    [Tags]    integration    power-efficiency
    Transition To Power State    ACTIVE
    Measure Current Consumption    baseline_active
    Transition To Power State    SLEEP
    Measure Current Consumption    baseline_sleep
    Verify Sleep Current    less_than_1A
    Verify Quick Wake    less_than_1s
```

## Coverage Goals

### Code Coverage Targets
- **Line Coverage**: ≥85%
- **Branch Coverage**: ≥80%
- **Path Coverage**: ≥70%

### Functional Coverage
- ✓ All power state transitions (valid and invalid)
- ✓ Voltage regulation (min, normal, max)
- ✓ Current monitoring and limiting
- ✓ Thermal management
- ✓ Error detection and recovery
- ✓ Sleep mode entry/exit
- ✓ Power initialization sequence
- ✓ All rails and subsystems

## Related Skills
- `robot-framework-integration` - For RF test implementation
- `test-design-techniques` - For test design patterns
- `test-documentation-compliance` - For test documentation
- `project-config-utilities` - For power-specific constants
- `test-strategy-planning` - For test planning

## Module-Specific Files

Location: `resources/S3P_PowerControl/`
- `s3p_powercontrol_pf.robot` - Platform-specific keywords
- `s3p_powercontrol_prj.robot` - Project-specific utilities

Location: `tests/S3P_PowerControl/` (if exists)
- Integration test suite files

## Troubleshooting Common Issues

### Issue: Voltage Regulation Unstable
- Check input voltage stability
- Verify load changes are smooth
- Check capacitor health
- Validate feedback network

### Issue: Over-Current Detection Not Working
- Verify current sensor calibration
- Check ADC reading accuracy
- Validate threshold configuration
- Check current path continuity

### Issue: Sleep Mode Not Reducing Power
- Verify peripherals disabled
- Check clock gating
- Monitor all rail currents
- Validate control signals
