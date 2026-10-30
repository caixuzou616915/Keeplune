---
name: s3p-sits-project-config
description: >-
  Documents project-specific configurations, constants, utilities, and common patterns
  used across S3P SITS Robot Framework tests (ECU states, UDS session/reset types, power
  supply settings). Use when: looking up shared variables/constants for test
  implementation; writing new Robot Framework resources for the S3P SITS project.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# Project Configuration & Utilities Skill

## Overview
This skill documents project-specific configurations, constants, utilities, and common patterns used across S3P SITS tests. It provides the building blocks for test implementation.

## Project Structure Reference

```
S3P_SITS_Project/
├── resources/                      # Reusable keywords and variables
│   ├── prjcfg_*.robot             # Global project configurations
│   ├── S3P_**/                    # Module-specific resources
│   │   ├── *_pf.robot             # Platform keywords
│   │   └── *_prj.robot            # Project keywords
│   └── dnga_common/               # Common utilities
├── tests/                         # Test suites
│   ├── *.robot                    # Top-level test suites
│   └── S3P_**/                    # Module-specific tests
└── templates/                     # Test templates
```

## Global Project Configurations

### ECU Operating States
```robot
*** Variables ***
# ECU Main Operating States
${ECU_Shutdown}         0x00    # System powered off
${ECU_Standby}          0x01    # Low-power standby mode
${ECU_Ready}            0x02    # System ready for operation
${ECU_DispOn}           0x03    # Display activated
${ECU_ProjectionOFF}    0x00    # Projection disabled (value 4 in spec)
${ECU_ProjectionON}     0x01    # Projection enabled (value 5 in spec)
${ECU_FCWON}            0x06    # Forward Collision Warning active
```

### Diagnostic Session Types (UDS)
```robot
*** Variables ***
${defaultSession}           0x01        # Default diagnostic session
${programmingSession}       0x02        # Programming/flashing mode
${extendedDiagSession}      0x03        # Extended diagnostics
```

### Reset Types (UDS)
```robot
*** Variables ***
${hardReset}                0x01        # Hard reset (power cycle)
${keyOnOffReset}            0x02        # KL15 reset (ignition)
${softReset}                0x03        # Soft reset
```

### Power Supply Configuration
```robot
*** Variables ***
# Voltage Settings
${NormalVoltage}            14          # Normal automotive voltage (volts)
${NormalCurrent}            5           # Normal current consumption (amps)
${UnderVoltage}             5           # Under-voltage threshold
${OverVoltage}              20          # Over-voltage threshold
${VoltageRampTime}          100         # Voltage ramp time (ms)

# Critical Thresholds
${VOLTAGE_MIN_VALID}        10          # Minimum valid voltage
${VOLTAGE_MAX_VALID}        18          # Maximum valid voltage
${VOLTAGE_TOLERANCE}        0.5         # Voltage tolerance (±volts)
```

### Timing Constants
```robot
*** Variables ***
# Standard Timeouts
${TIMEOUT_STANDARD}         10s         # Standard operation timeout
${TIMEOUT_EXTENDED}         30s         # Extended operation timeout
${TIMEOUT_STARTUP}          5s          # System startup timeout
${TIMEOUT_CALIBRATION}      15s         # Calibration timeout

# Retry Parameters
${RETRY_INTERVAL}           500ms       # Interval between retries
${MAX_RETRIES}              3           # Maximum retry attempts

# Delays
${DELAY_POWER_ON}           1s          # Delay after power on
${DELAY_POWER_OFF}          2s          # Delay before re-power
${DELAY_STATE_STABLE}       500ms       # Delay to stabilize state
```

### Communication Configuration
```robot
*** Variables ***
# CAN Bus
${CAN_INTERFACE}            CANoe_Virtual_Channel_1
${CAN_BAUDRATE}             500000      # 500 kbps
${CAN_TIMEOUT}              5s

# UDS Services
${UDS_SERVICE_READ_DID}     0x22        # ReadDataByIdentifier
${UDS_SERVICE_WRITE_DID}    0x2E        # WriteDataByIdentifier
${UDS_SERVICE_ECU_RESET}    0x11        # ECUReset
${UDS_SERVICE_SESSION}      0x10        # DiagnosticSessionControl

# DIDs (Data Identifiers)
${DID_EyeBox_Status}        0xFD40      # EyeBox current status
${DID_EyeBox_Position}      0xFD41      # EyeBox motor position
${DID_System_Status}        0xFD30      # System health status
```

## Module-Specific Configurations

### S3P_EyeBox Module
```robot
*** Variables ***
# Operating Modes
${EYEBOX_MODE_OPERATING}    0           # Normal operating mode
${EYEBOX_MODE_READY}        1           # Ready/standby mode
${EYEBOX_MODE_SLEEP}        2           # Sleep mode
${EYEBOX_MODE_WAIT_REF}     3           # Waiting for reference

# Status Fields
${EYEBOX_ADJUSTMENT_IDLE}   0           # No adjustment active
${EYEBOX_ADJUSTMENT_ACTIVE} 1           # Adjustment in progress
${EYEBOX_MOTOR_IDLE}        1           # Motor not moving
${EYEBOX_MOTOR_MOVING}      0           # Motor actively moving

# Position Ranges
${EYEBOX_POS_MIN}           0
${EYEBOX_POS_MAX}           100
${EYEBOX_POS_CENTER}        50

# Motor Parameters
${EYEBOX_MOTOR_TIMEOUT}     20s
${EYEBOX_CALIBRATION_TIME}  10s
${EYEBOX_STEP_SIZE}         5           # Position step size
```

### S3P_PowerControl Module
```robot
*** Variables ***
# Power States
${POWER_STATE_OFF}          0x00
${POWER_STATE_INIT}         0x01
${POWER_STATE_READY}        0x02
${POWER_STATE_ACTIVE}       0x03
${POWER_STATE_SLEEP}        0x04
${POWER_STATE_ERROR}        0xFF

# Power Thresholds
${POWER_THRESHOLD_LOW}      5V
${POWER_THRESHOLD_HIGH}     20V
${POWER_THRESHOLD_HYSTERESIS} 0.5V
```

### S3P_Illumination Module
```robot
*** Variables ***
# Brightness Levels
${BRIGHTNESS_MIN}           0           # Off
${BRIGHTNESS_MAX}           100         # Maximum brightness
${BRIGHTNESS_DEFAULT}       50          # Default level

# Light Modes
${LIGHT_MODE_OFF}           0
${LIGHT_MODE_MANUAL}        1
${LIGHT_MODE_AUTO}          2
${LIGHT_MODE_ADAPTIVE}      3

# Color Temperature
${COLOR_TEMP_WARM}          3000K       # Warm white
${COLOR_TEMP_NEUTRAL}       4000K       # Neutral white
${COLOR_TEMP_COOL}          6500K       # Cool white
```

## Common Utility Keywords

### Power Management
```robot
Apply Voltage
    [Arguments]    ${voltage}    ${current}=5
    [Documentation]    Apply voltage to the system under test
    Set Power Supply    voltage=${voltage}    current=${current}
    Wait    ${DELAY_POWER_ON}

Perform Power Cycle
    [Arguments]    ${voltage}=${NormalVoltage}    ${delay}=2s
    [Documentation]    Power off and back on with specified delay
    Remove Power
    Wait    ${delay}
    Apply Voltage    ${voltage}

Remove Power
    [Documentation]    Remove power from system
    Set Power Supply    voltage=0    current=0
```

### DID Access Utilities
```robot
Read DID Value
    [Arguments]    ${did}    ${service}=0x22
    [Documentation]    Read DID value via UDS service
    Send UDS Request    ${service}    ${did}
    ${response}=    Get UDS Response
    RETURN    ${response}

Write DID Value
    [Arguments]    ${did}    ${value}    ${service}=0x2E
    [Documentation]    Write DID value via UDS service
    Send UDS Request    ${service}    ${did}    ${value}
    ${status}=    Get UDS Response Status
    RETURN    ${status}

Validate DID Content
    [Arguments]    ${did}    ${expected_content}
    [Documentation]    Read DID and validate content matches
    ${actual}=    Read DID Value    ${did}
    Should Contain    ${actual}    ${expected_content}
```

### Signal Management
```robot
Set Signal Value
    [Arguments]    ${signal_name}    ${value}    ${bus}=${CAN_INTERFACE}
    [Documentation]    Set CAN signal to specified value
    CANoe Set Signal    ${signal_name}    ${value}    ${bus}

Get Signal Value
    [Arguments]    ${signal_name}    ${bus}=${CAN_INTERFACE}
    [Documentation]    Read current CAN signal value
    ${value}=    CANoe Get Signal    ${signal_name}    ${bus}
    RETURN    ${value}

Wait For Signal
    [Arguments]    ${signal_name}    ${expected_value}    ${timeout}=${TIMEOUT_STANDARD}
    [Documentation]    Wait for signal to reach expected value
    Wait Until Keyword Succeeds    ${timeout}    ${RETRY_INTERVAL}
    ...    Signal Value Should Be    ${signal_name}    ${expected_value}
```

### State Verification
```robot
Verify Operating State
    [Arguments]    ${component}
    [Documentation]    Verify component is in operating state
    ${status}=    Read Component Status    ${component}
    Should Contain    ${status}    "OperationMode": 0
    Should Contain    ${status}    "MotorReferencingStatus": 1

Verify Ready State
    [Arguments]    ${component}
    [Documentation]    Verify component is ready
    ${status}=    Read Component Status    ${component}
    Should Contain    ${status}    "OperationMode": 1
    Should Contain    ${status}    "AdjustmentStatus": 0

Verify Component Idle
    [Arguments]    ${component}
    [Documentation]    Verify component is idle and not processing
    ${status}=    Read Component Status    ${component}
    Should Contain    ${status}    "MotorReferencingStatus": 1
    Should Not Contain    ${status}    "AdjustmentStatus": 1
```

### Timeout and Retry Patterns
```robot
Wait Until Component Ready
    [Arguments]    ${component}    ${timeout}=${TIMEOUT_STANDARD}
    [Documentation]    Wait for component to reach ready state
    Wait Until Keyword Succeeds    ${timeout}    ${RETRY_INTERVAL}
    ...    Verify Ready State    ${component}

Retry Operation
    [Arguments]    ${keyword}    ${max_attempts}=${MAX_RETRIES}
    [Documentation]    Retry operation up to max attempts
    FOR    ${attempt}    IN RANGE    1    ${max_attempts}+1
        TRY
            ${result}=    Run Keyword    ${keyword}
            RETURN    ${result}
        EXCEPT    *
            Continue For Loop If    ${attempt} < ${max_attempts}
            Fail    Operation failed after ${max_attempts} attempts
        END
    END
```

### Setup and Teardown Templates
```robot
Initialize Test Environment
    [Documentation]    Common setup for all tests
    Log to console    Initializing test environment
    Apply Voltage    ${NormalVoltage}    ${NormalCurrent}
    Connect To CAN    ${CAN_INTERFACE}
    Wait Until Component Ready    SystemController
    Set Diagnostic Session    ${defaultSession}

Cleanup Test Environment
    [Documentation]    Common cleanup after tests
    Log to console    Cleaning up test environment
    Reset All Signals
    Remove Power
    Disconnect From CAN
    Log to console    Test cleanup completed
```

## Error Codes and Status Codes

```robot
*** Variables ***
# Common Error Codes
${ERROR_NO_ERROR}           0x00        # No error
${ERROR_GENERAL}            0xFF        # General error
${ERROR_TIMEOUT}            0x01        # Operation timeout
${ERROR_OUT_OF_RANGE}       0x02        # Value out of range
${ERROR_INVALID_STATE}      0x03        # Invalid state for operation
${ERROR_CHECKSUM}           0x04        # Checksum or CRC error
${ERROR_COMMUNICATION}      0x05        # Communication error
${ERROR_HARDWARE}           0x06        # Hardware error
${ERROR_NOT_INITIALIZED}    0x07        # Component not initialized
```

## Test Environment Setup

### CANoe Configuration
```robot
*** Keywords ***
Initialize CANoe
    [Documentation]    Initialize CANoe simulation environment
    Connect CANoe    config_file=canoe_config.cfg
    Load Database    database=S3P_SITS.dbc
    Start Measurement
    Wait    500ms

Shutdown CANoe
    [Documentation]    Graceful CANoe shutdown
    Stop Measurement
    Disconnect CANoe
```

### Hardware Setup Verification
```robot
Verify Hardware Ready
    [Documentation]    Verify all hardware is connected and ready
    Verify Power Supply Connected
    Verify CAN Interface Ready
    Verify ECU Accessible
    Verify Test Tools Available
```

## Data Handling

### Signal Formatting
```robot
Format CAN Message
    [Arguments]    ${service_id}    ${data}
    [Documentation]    Format data for CAN transmission
    ${formatted}=    Evaluate    '0x{:02X}'.format(${service_id})
    RETURN    ${formatted}

Parse DID Response
    [Arguments]    ${raw_response}
    [Documentation]    Parse DID response into structured data
    ${parsed}=    Convert String To Dictionary    ${raw_response}
    RETURN    ${parsed}
```

## Common Test Data Files

Reference data files in `templates/` folder:
- `robot_properties.py` - Python utilities
- `resource_templates/` - Template resources
- `test_templates/` - Template test cases

## Project-Specific Conventions

1. **Naming**: Use descriptive names with underscores
2. **Variables**: Uppercase for constants, lowercase for temporary
3. **Keywords**: Action-oriented verbs at start (Read, Set, Verify, Wait)
4. **Comments**: Document non-obvious logic
5. **Imports**: List all dependencies clearly
6. **Organization**: Group related keywords with comments

## Integration with Other Skills

- `robot-framework-integration` - Uses these configs in test files
- `s3p-sits-design-techniques` - Uses variables for test data
- `s3p-eyebox-module` - Provides module-specific values
- All module skills build on this foundation

## Maintenance

- Update variables when hardware changes
- Document new constants in this skill
- Keep timeout values realistic for CI/CD
- Review and validate all threshold values quarterly
