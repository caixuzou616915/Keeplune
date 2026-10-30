---
name: s3p-appmodemng-module
description: >-
  Comprehensive reference for the S3P Application Mode Management module (operational
  modes, mode transitions, mode-specific configuration) for creating targeted unit and
  integration tests. Use when: writing test cases for mode change requests/transitions;
  testing mode persistence or feature availability per mode; working with DIDs
  0xFD50-0xFD53.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# S3P Application Mode Management Module Skill

## Overview
This skill provides comprehensive information about the S3P Application Mode Management module for creating targeted unit and integration tests. The Application Mode Management module is responsible for handling different operational modes, mode transitions, and mode-specific configurations in the S3P SITS system.

## Module Purpose
The Application Mode Management module manages:
- **Operational modes**: Different system operating modes
- **Mode transitions**: Safe transitions between modes
- **Mode configuration**: Mode-specific settings and parameters
- **Mode persistence**: Saving/restoring mode state
- **Feature availability**: Enabling/disabling features per mode
- **Mode-specific behavior**: Adapting behavior based on current mode

## Component Architecture

### External Interfaces
```
Application Mode Management Module
├── Mode Request Interface
│   ├── Mode change requests
│   ├── Mode transition validation
│   └── Mode rejection reasons
│
├── Configuration Interface
│   ├── Mode-specific parameters
│   ├── Feature enable/disable
│   └── Timeout values
│
├── CAN Bus Interface (UDS)
│   ├── DID 0xFD50: Current App Mode
│   ├── DID 0xFD51: Available Modes
│   ├── DID 0xFD52: Mode Configuration
│   └── DID 0xFD53: Mode Permissions
│
├── Signal Interface
│   ├── Mode state signals
│   ├── Feature availability signals
│   └── Mode constraint signals
│
└── Dependent Modules
    ├── Power Control (power state sync)
    ├── EyeBox Control (feature control)
    ├── Illumination (feature control)
    └── System Control (overall coordination)
```

### Application Modes
```
Mode 0: STANDBY
- Low power operation
- Minimal functionality
- Quick transition to ACTIVE
- Current: 1A max

Mode 1: DEMO
- Demonstration/showcase mode
- Limited features enabled
- Safe operational mode
- Used in showrooms

Mode 2: STANDARD
- Normal consumer operation
- Full feature set
- Standard timing parameters
- Standard power consumption

Mode 3: PERFORMANCE
- Enhanced mode
- Optimized response times
- Enhanced features
- Higher power consumption

Mode 4: DIAGNOSTIC
- Service/diagnostic mode
- Full internal access
- Extended logging
- Special commands available

Mode 5: PRODUCTION_TEST
- Manufacturing test mode
- Test points accessible
- Bypass some safety checks
- Production verification
```

## Key Data Structures

### Current App Mode DID (0xFD50)
```
Field                   Range       Description
CurrentMode            0-5         Current operational mode
RequestedMode          0-5         Requested mode (if transitioning)
ModeTransitionState    0-3         0=Stable, 1=Requested, 2=Transitioning, 3=Error
TimeInCurrentMode      0-65535     Time in seconds in current mode
```

### Available Modes DID (0xFD51)
```
Field                   Range       Description
AvailableModes         (bitmap)    Bit mask of available modes
RestrictedModes        (bitmap)    Bit mask of restricted modes
PermissionLevel        0-3         User permission level (0=Demo, 1=Standard, 2=Advanced, 3=Service)
```

### Mode Configuration DID (0xFD52)
```
Field                   Range       Description
MaxBrightness          0-100       Max brightness in current mode
MaxRefreshRate         0-120       Max refresh rate in mode
MotorSpeedLimit        0-255       Motor speed limit (0-100%)
ResponseTimeoutMs      100-60000   Mode-specific timeout
EnabledFeatures        (bitmap)    Feature enable bitmap
```

## Test Scenarios by Feature

### Feature 1: Mode Transitions
**Scenario: Valid Mode Transitions**
```
Common Transitions:
STANDBY ↔ STANDARD (common usage)
STANDARD → PERFORMANCE (user request)
PERFORMANCE → STANDARD (resource management)
ANY MODE → STANDBY (power saving)
STANDARD → DIAGNOSTIC (service)
DIAGNOSTIC → STANDARD (service end)
PRODUCTION_TEST ↔ DIAGNOSTIC (manufacturing)

Test Cases Needed:
1. Each valid transition
2. Transition timing verification
3. Configuration updates
4. Signal updates during transition
5. Feature availability changes
```

**Scenario: Invalid Mode Transitions (Negative Testing)**
```
Invalid Paths:
DEMO → PERFORMANCE (permission too low)
PRODUCTION_TEST → STANDARD (manufacturing mode)
DIAGNOSTIC ← STANDBY (wrong sequence)
Mode X → Mode X (already in mode)

Test Cases Needed:
1. Attempt invalid transitions
2. Verify rejection with reason
3. Current mode remains unchanged
4. Configuration not partially applied
```

### Feature 2: Permission-Based Mode Access
**Scenario: User Permission Levels**
```
Permission Levels:
- Demo User: DEMO, STANDBY, STANDARD only
- Standard User: STANDARD, PERFORMANCE, STANDBY
- Advanced User: STANDARD, PERFORMANCE, DIAGNOSTIC, STANDBY
- Service: All modes

Test Cases Needed:
1. Demo user can't access PERFORMANCE
2. Standard user can't access DIAGNOSTIC
3. Service user can access all modes
4. Permission validation on mode request
5. Permission denied error handling
```

### Feature 3: Mode-Specific Feature Control
**Scenario: Feature Availability Per Mode**
```
Feature Matrix:
- STANDBY: Navigation, basic controls
- DEMO: All visual features, limited interaction
- STANDARD: All features
- PERFORMANCE: All features + enhanced
- DIAGNOSTIC: All + debug features
- PRODUCTION_TEST: Test points only

Test Cases Needed:
1. Features enabled in target mode
2. Features disabled in target mode
3. Feature availability signals updated
4. Incompatible features prevented
5. Feature access validation
```

### Feature 4: Mode Configuration Application
**Scenario: Configuration Per Mode**
```
Configuration Changes:
- Brightness limits per mode
- Refresh rate per mode
- Motor speed limits per mode
- Response timeouts per mode
- Feature availability per mode

Test Cases Needed:
1. Configuration loaded on mode entry
2. Configuration applied to subsystems
3. Validation of configuration values
4. Timeout compliance
5. Motor speed limits enforced
```

### Feature 5: Mode Persistence
**Scenario: Saving/Restoring Mode**
```
Persistence:
- Save current mode to NvM
- Restore on power-up
- Last valid mode remembered
- Fallback to STANDBY on error

Test Cases Needed:
1. Mode saved to NvM
2. Mode restored after power cycle
3. Invalid mode triggers fallback
4. NvM corruption handling
5. Mode history tracking
```

### Feature 6: Mode Transition Constraints
**Scenario: Constraint-Based Transitions**
```
Constraints:
- Can't transition during critical operation
- Power level must be sufficient
- Required subsystems must be ready
- Thermal state must be acceptable

Test Cases Needed:
1. Transition blocked during motor movement
2. Transition blocked if insufficient power
3. Transition blocked if subsystem not ready
4. Thermal constraint enforcement
5. Error handling for blocked transition
```

## Mock Requirements

### Mode Configuration Manager Mock
```cpp
class MockModeConfigManager {
public:
    MOCK_METHOD(bool, IsTransitionAllowed, 
        (uint8_t from_mode, uint8_t to_mode));
    MOCK_METHOD(bool, HasPermission, 
        (uint8_t mode, uint8_t permission_level));
    MOCK_METHOD(void, ApplyModeConfiguration, (uint8_t mode));
    MOCK_METHOD(bool, IsModeAvailable, (uint8_t mode));
};
```

### NvM (Non-Volatile Memory) Mock
```cpp
class MockNvM {
public:
    MOCK_METHOD(void, WriteMode, (uint8_t mode));
    MOCK_METHOD(uint8_t, ReadMode, ());
    MOCK_METHOD(bool, IsValid, (uint8_t mode));
    MOCK_METHOD(void, EraseData, ());
};
```

### Subsystem State Mock
```cpp
class MockSubsystemState {
public:
    MOCK_METHOD(bool, IsReady, (uint8_t subsystem));
    MOCK_METHOD(bool, IsBusy, (uint8_t subsystem));
    MOCK_METHOD(uint8_t, GetPowerState, ());
    MOCK_METHOD(bool, IsOperating, ());
};
```

## Key Test Data

### Mode Test Values
```
VALID MODES:
- 0: STANDBY
- 1: DEMO
- 2: STANDARD
- 3: PERFORMANCE
- 4: DIAGNOSTIC
- 5: PRODUCTION_TEST

INVALID MODES:
- 6, 7, 255 (undefined modes)
```

### Permission Levels
```
- 0: Demo User (limited)
- 1: Standard User (normal)
- 2: Advanced User (diagnostic)
- 3: Service (all access)
```

### Configuration Boundary Values
```
Brightness:
- Min: 0 (off)
- Max: 100 (full)
- Typical: 50

Refresh Rate (Hz):
- Min: 10
- Max: 120
- Standard: 60

Motor Speed Limit (%):
- Min: 0 (disabled)
- Max: 100 (full speed)
- Standard: 80
```

## Error Codes
```
0x00: No error
0x01: Invalid mode requested
0x02: Permission denied for mode
0x03: Mode transition not allowed
0x04: Subsystem not ready for transition
0x05: Power insufficient for mode
0x06: Thermal constraints violated
0x07: Mode configuration error
0x08: NvM write failure
0x09: Transition timeout
0xFF: Unknown mode error
```

## Common Test Patterns

### Pattern 1: Mode Transition Test
```robot
Test Case - Mode Transition [FromMode] To [ToMode]
    Set Application Mode    ${from_mode}
    Verify Mode Active    ${from_mode}
    Request Mode Change    ${to_mode}
    Wait For Mode Transition    10s
    Verify Mode Active    ${to_mode}
    Verify Configuration Applied
    Verify Features Updated
    Verify No Error Codes
```

### Pattern 2: Permission Test
```robot
Test Case - Permission [UserLevel] Cannot Access [Mode]
    Set User Permission Level    ${user_level}
    Request Mode Change    ${restricted_mode}
    Verify Request Rejected
    Verify Error Code    PERMISSION_DENIED
    Verify Mode Unchanged
```

### Pattern 3: Feature Availability Test
```robot
Test Case - Feature [FeatureName] Available In Mode [Mode]
    Set Application Mode    ${mode}
    Verify Feature Enabled    ${feature}
    Test Feature Functionality
    Verify Feature Works In Mode

Test Case - Feature [FeatureName] Disabled In Mode [Mode]
    Set Application Mode    ${mode}
    Verify Feature Disabled    ${feature}
    Verify Feature Access Blocked
```

## GTF Unit Test Structure

```cpp
TEST_F(AppModeMngFixture, ValidModeTransition)
{
    // Setup
    app_mode.SetCurrentMode(MODE_STANDARD);
    EXPECT_CALL(config_mock, IsTransitionAllowed)
        .WillOnce(Return(true));
    
    // Execute
    bool result = app_mode.RequestModeChange(MODE_PERFORMANCE);
    
    // Verify
    EXPECT_TRUE(result);
    EXPECT_EQ(app_mode.GetCurrentMode(), MODE_PERFORMANCE);
}

TEST_F(AppModeMngFixture, PermissionDeniedForMode)
{
    app_mode.SetUserPermissionLevel(DEMO_USER);
    EXPECT_CALL(config_mock, HasPermission)
        .WillOnce(Return(false));
    
    bool result = app_mode.RequestModeChange(MODE_DIAGNOSTIC);
    
    EXPECT_FALSE(result);
    EXPECT_NE(app_mode.GetCurrentMode(), MODE_DIAGNOSTIC);
    EXPECT_EQ(app_mode.GetErrorCode(), ERROR_PERMISSION_DENIED);
}

TEST_F(AppModeMngFixture, FeatureAvailabilityChange)
{
    app_mode.SetCurrentMode(MODE_STANDARD);
    EXPECT_TRUE(app_mode.IsFeatureEnabled(FEATURE_NAVIGATION));
    
    app_mode.RequestModeChange(MODE_STANDBY);
    EXPECT_FALSE(app_mode.IsFeatureEnabled(FEATURE_VIDEO));
}
```

## Robot Framework Integration Test Structure

```robot
*** Settings ***
Documentation  Integration Tests for S3P App Mode Management
Resource       ../../resources/S3P_AppModeMng/s3p_appmodemng_pf.robot
Resource       ../../resources/S3P_Common/s3p_common_pf.robot

*** Test Cases ***
Mode Transition From Standard To Performance
    [Documentation]    Validates mode transition and feature updates
    [Tags]    integration    mode-transition    appmodemng
    Set Application Mode    STANDARD
    Verify Mode Active    STANDARD
    Request Mode Change    PERFORMANCE
    Wait For Mode Transition    5s
    Verify Mode Active    PERFORMANCE
    Verify Enhanced Features Enabled
    Verify Motor Speed Increased
    Verify No Error Codes

Demo User Cannot Access Diagnostic Mode
    [Documentation]    Tests permission-based access control
    [Tags]    integration    permission    security
    Set User Permission Level    DEMO_USER
    Request Mode Change    DIAGNOSTIC
    Verify Request Rejected    PERMISSION_DENIED
    Verify Mode Unchanged    DEMO
    
Performance Mode Configuration Applied
    [Documentation]    Validates mode-specific configuration
    [Tags]    integration    configuration    appmodemng
    Request Mode Change    PERFORMANCE
    Verify Brightness Limit    100
    Verify Refresh Rate    120Hz
    Verify Motor Speed Limit    100%
    Verify Response Timeout    5000ms

Mode Persistence After Power Cycle
    [Documentation]    Tests mode save/restore functionality
    [Tags]    integration    persistence    nvm
    Request Mode Change    PERFORMANCE
    Verify Mode Saved    to=NvM
    Perform Power Cycle
    Verify Mode Restored    PERFORMANCE
    Verify Configuration Restored
```

## Coverage Goals

### Code Coverage Targets
- **Line Coverage**: ≥85%
- **Branch Coverage**: ≥80%
- **Path Coverage**: ≥70%

### Functional Coverage
- ✓ All valid mode transitions
- ✓ All permission levels and restrictions
- ✓ Feature availability in each mode
- ✓ Configuration application per mode
- ✓ Mode persistence (save/restore)
- ✓ Transition constraints
- ✓ Error handling and recovery

## Related Skills
- `robot-framework-integration` - For RF test implementation
- `test-design-techniques` - For test design patterns
- `test-documentation-compliance` - For test documentation
- `project-config-utilities` - For mode constants
- `test-strategy-planning` - For test planning

## Module-Specific Files

Location: `resources/S3P_AppModeMng/`
- `s3p_appmodemng_pf.robot` - Platform-specific keywords
- `s3p_appmodemng_prj.robot` - Project-specific utilities

## Troubleshooting Common Issues

### Issue: Mode Transition Timeout
- Check subsystem readiness
- Verify power state sufficient
- Check configuration loading time
- Validate signal updates

### Issue: Features Not Disabled
- Verify feature availability signals
- Check feature control logic
- Validate mode configuration
- Check subsystem coordination

### Issue: Permission Check Failing
- Verify user permission level set
- Check permission table accuracy
- Validate permission logic
- Check NvM permission storage
