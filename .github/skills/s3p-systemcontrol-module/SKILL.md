---
name: s3p-systemcontrol-module
description: >-
  Comprehensive reference for the S3P System Control module (system state management,
  watchdog management, error aggregation, inter-module coordination) for creating
  targeted unit and integration tests. Use when: writing test cases for boot/shutdown
  sequences, watchdog timeout/recovery, or error aggregation; working with DIDs
  0xFD90-0xFD93.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# S3P System Control Module Skill

## Overview
This skill provides comprehensive information about the S3P System Control module for creating targeted unit and integration tests. The System Control module is responsible for overall system coordination, watchdog management, and system-level control of the S3P SITS system.

## Module Purpose
The System Control module manages:
- **System initialization**: Startup and boot sequences
- **System state management**: Tracking and managing global system states
- **Watchdog management**: Monitoring system health and safety
- **Error aggregation**: Collecting and managing system-wide errors
- **Inter-module coordination**: Orchestrating communication between components
- **System shutdown**: Graceful shutdown procedures
- **Fault recovery**: Recovering from errors and anomalies

## Component Architecture

### External Interfaces
```
System Control Module
├── System State Management
│   ├── Boot sequence coordination
│   ├── Operational state tracking
│   └── Shutdown sequence
│
├── Watchdog Management
│   ├── Watchdog timer control
│   ├── Watchdog kick/refresh
│   ├── Timeout detection
│   └── Recovery actions
│
├── Error Management
│   ├── Error aggregation
│   ├── Error prioritization
│   ├── Error reporting
│   └── Error history logging
│
├── CAN Bus Interface (UDS)
│   ├── DID 0xFD90: System State
│   ├── DID 0xFD91: System Health
│   ├── DID 0xFD92: Error Summary
│   └── DID 0xFD93: System Statistics
│
├── Signal Interface
│   ├── System enable signals
│   ├── Error indication signals
│   ├── Status signals
│   └── Control signals
│
└── Module Interfaces
    ├── Power Control (power sequencing)
    ├── All other modules (health monitoring)
    └── CAN Bus (communication)
```

### System States
```
State 0: INIT
- System initializing
- Modules starting up
- Self-tests running
- Duration: 5-10 seconds

State 1: READY
- All modules initialized
- System ready for operation
- Can accept requests
- All subsystems functional

State 2: ACTIVE
- System in normal operation
- All features available
- Monitoring ongoing
- Performance optimized

State 3: DEGRADED
- Reduced functionality
- Some modules impaired
- Operation continues
- Error correction active

State 4: ERROR
- System error detected
- Limited operation
- Recovery attempted
- Manual intervention may be needed

State 5: SHUTDOWN
- Graceful shutdown in progress
- Modules shutting down
- State saved if needed
- Power-down sequence
```

## Key Data Structures

### System State DID (0xFD90)
```
Field                   Range       Description
CurrentSystemState     0-5         Current operational state
TargetSystemState      0-5         Requested target state
TimeInState            0-65535     Time in current state (seconds)
IsStateStable          0-1         0=Transitioning, 1=Stable
StateTransitionCount   0-65535     Number of transitions
```

### System Health DID (0xFD91)
```
Field                   Range       Description
OverallHealth          0-100       System health percentage
ModuleHealthBitmap    (bitmap)     Individual module health
WatchdogStatus         0-3         Watchdog state
LastWatchdogKick      0-65535     Time since last kick (ms)
SystemUptime          0-4294967    Uptime in seconds
```

### Error Summary DID (0xFD92)
```
Field                   Range       Description
ActiveErrorCount      0-255       Number of active errors
HighestErrorSeverity  0-3         Most severe error level
MostRecentErrorCode   0x00-0xFF   Latest error
CriticalErrorCount    0-255       Count of critical errors
ErrorHistory          (array)     Recent error codes
```

### System Statistics DID (0xFD93)
```
Field                   Range       Description
TotalBootTime         0-65535     Time to full operation (ms)
BootSuccessCount      0-65535     Successful boots
BootFailureCount      0-65535     Failed boots
RecoveryCount         0-65535     Recovery events
LastErrorRecoveryTime 0-65535     Last recovery duration (ms)
```

## Test Scenarios by Feature

### Feature 1: System Boot Sequence
**Scenario: Successful Boot**
```
Boot Sequence:
1. Power on
2. Initialize hardware
3. Start modules in order
4. Run self-tests
5. Reach READY state
6. Ready for operation

Expected Timing:
- Total: 5-10 seconds
- Each module: < 2 seconds
- Self-tests: < 3 seconds

Test Cases Needed:
1. Complete boot sequence
2. Timing verification
3. Module startup order
4. Boot success confirmation
5. Ready state validation
```

**Scenario: Failed Boot Recovery**
```
Failure Scenarios:
- Module initialization timeout
- Self-test failure
- Missing required module
- Power insufficient

Recovery Actions:
- Retry module start
- Log error
- Attempt graceful degradation
- Manual intervention needed

Test Cases Needed:
1. Detect boot failure
2. Attempt recovery
3. Log error details
4. User notification
5. Recovery outcome validation
```

### Feature 2: Watchdog Management
**Scenario: Normal Watchdog Operation**
```
Watchdog Parameters:
- Timeout: 2 seconds (typical)
- Kick interval: 1 second
- Failure: System reset

Test Cases Needed:
1. Regular watchdog kick
2. Kick timing verification
3. Watchdog timeout handling
4. System reset verification
5. Recovery after reset
```

**Scenario: Watchdog Timeout**
```
Timeout Scenarios:
- Application hangs
- Deadlock condition
- Interrupt storm
- Resource exhaustion

Recovery:
- System reset
- Boot sequence restart
- Error logging
- Recovery attempt

Test Cases Needed:
1. Trigger watchdog timeout
2. Verify system reset
3. Verify error logging
4. Recovery to READY state
5. Boot counter increment
```

### Feature 3: Error Management
**Scenario: Error Detection and Aggregation**
```
Error Sources:
- Module errors
- Communication errors
- Hardware errors
- Sensor errors
- Timeout errors

Error Handling:
- Collect errors
- Prioritize by severity
- Log to history
- Report via DID

Test Cases Needed:
1. Single error detection
2. Multiple errors aggregation
3. Error priority ranking
4. Error history tracking
5. Error clearing
```

**Scenario: Error Recovery**
```
Recovery Strategies:
- Retry operation
- Restart module
- Reduce functionality
- Enter degraded mode
- System shutdown if critical

Test Cases Needed:
1. Error triggers recovery
2. Recovery executes correctly
3. System state after recovery
4. Error cleared on success
5. Retry count management
```

### Feature 4: Module Health Monitoring
**Scenario: Continuous Health Monitoring**
```
Health Metrics:
- Module responsiveness
- Communication status
- Self-test results
- Resource usage
- Temperature

Monitoring Actions:
- Regular checks
- Health scoring
- Threshold detection
- Alert generation

Test Cases Needed:
1. Module responsiveness check
2. Health score calculation
3. Threshold comparison
4. Alert generation
5. Health trend tracking
```

**Scenario: Degraded Mode Transition**
```
Degradation Triggers:
- Module health < 50%
- Communication loss
- Critical resource exhaustion
- Temperature warning

Actions in Degraded Mode:
- Reduce functionality
- Disable non-essential features
- Maintain operation
- Attempt recovery
- Continue monitoring

Test Cases Needed:
1. Trigger degradation condition
2. Transition to DEGRADED state
3. Feature availability reduction
4. Operation continuation
5. Recovery to ACTIVE
```

### Feature 5: Graceful Shutdown
**Scenario: Controlled Shutdown**
```
Shutdown Sequence:
1. Receive shutdown request
2. Notify all modules
3. Save critical state
4. Disable features gracefully
5. Power down sequence

Shutdown Types:
- Normal shutdown (user requested)
- Emergency shutdown (critical error)
- Soft shutdown (standby mode)

Test Cases Needed:
1. Initiate shutdown
2. Verify module notification
3. State save verification
4. Feature disable sequence
5. Power-down confirmation
```

### Feature 6: System Statistics and Logging
**Scenario: Boot Statistics**
```
Boot Metrics:
- Boot count
- Successful boots
- Failed boots
- Boot time distribution
- Recovery statistics

Test Cases Needed:
1. Log successful boot
2. Log failed boot
3. Track recovery count
4. Measure boot time
5. Statistics persistence
```

**Scenario: Uptime and Reliability**
```
Reliability Metrics:
- System uptime
- MTBF (Mean Time Between Failures)
- MTTR (Mean Time To Repair)
- Error rate
- Recovery success rate

Test Cases Needed:
1. Track uptime
2. Calculate reliability metrics
3. Detect anomalies
4. Generate reports
5. Trend analysis
```

## Mock Requirements

### Watchdog Mock
```cpp
class MockWatchdog {
public:
    MOCK_METHOD(void, Enable, ());
    MOCK_METHOD(void, Disable, ());
    MOCK_METHOD(void, Kick, ());
    MOCK_METHOD(bool, IsActive, ());
    MOCK_METHOD(bool, WasTriggered, ());
    MOCK_METHOD(void, SetTimeout, (uint16_t timeout_ms));
};
```

### Module Manager Mock
```cpp
class MockModuleManager {
public:
    MOCK_METHOD(bool, InitializeModule, (const std::string& module));
    MOCK_METHOD(bool, IsModuleReady, (const std::string& module));
    MOCK_METHOD(uint8_t, GetModuleHealth, (const std::string& module));
    MOCK_METHOD(bool, ShutdownModule, (const std::string& module));
    MOCK_METHOD(uint16_t, GetBootTime, ());
};
```

### Error Handler Mock
```cpp
class MockErrorHandler {
public:
    MOCK_METHOD(void, ReportError, (uint8_t error_code, uint8_t severity));
    MOCK_METHOD(bool, HasActiveErrors, ());
    MOCK_METHOD(uint8_t, GetHighestSeverity, ());
    MOCK_METHOD(void, ClearError, (uint8_t error_code));
};
```

## Key Test Data

### System State Values
```
VALID STATES:
- 0: INIT
- 1: READY
- 2: ACTIVE
- 3: DEGRADED
- 4: ERROR
- 5: SHUTDOWN

TRANSITIONS:
Valid: INIT→READY→ACTIVE, ACTIVE↔DEGRADED, Any→ERROR, Any→SHUTDOWN
Invalid: READY→ACTIVE (must go through intermediate)
```

### Timing Test Values
```
Boot Timing (seconds):
- Target: 5-10
- Min: 3
- Max: 15
- Acceptable: 5-10

Watchdog Timeout (ms):
- Standard: 2000
- Min: 500
- Max: 5000

Error Recovery (ms):
- Target: < 500
- Min: 100
- Max: 2000
```

## Error Codes
```
0x00: No error
0x01: Boot timeout
0x02: Module initialization failed
0x03: Self-test failed
0x04: Watchdog triggered
0x05: Critical error detected
0x06: Communication error
0x07: Resource exhaustion
0x08: Thermal limit exceeded
0x09: Power fault
0x0A: Recovery failed
0xFF: Unknown system error
```

## Common Test Patterns

### Pattern 1: Boot Sequence Test
```robot
Test Case - Complete Boot Sequence
    [Tags]    system-control    boot
    Power On System
    Wait For Boot Completion    10s
    Verify System State    READY
    Verify All Modules Ready
    Verify System Health    > 90%
    Verify No Critical Errors
```

### Pattern 2: Watchdog Test
```robot
Test Case - Watchdog Timeout Triggers Reset
    [Tags]    system-control    watchdog
    System In Active Operation
    Stop Watchdog Kick    simulate=hang
    Wait For Timeout    3s
    Verify System Reset
    Verify Boot Sequence Started
    Verify Recovery Complete
```

### Pattern 3: Error Aggregation Test
```robot
Test Case - Multiple Errors Aggregated
    [Tags]    system-control    error-handling
    Trigger Error    module=EyeBox    code=0x01
    Trigger Error    module=Power    code=0x05
    Read Error Summary
    Verify Error Count    2
    Verify Highest Severity    Highest
```

## GTF Unit Test Structure

```cpp
TEST_F(SystemControlFixture, BootSequenceComplete)
{
    EXPECT_CALL(module_mgr_mock, InitializeModule).WillRepeatedly(Return(true));
    EXPECT_CALL(module_mgr_mock, IsModuleReady).WillRepeatedly(Return(true));
    
    uint16_t boot_time = system_control.BootSystem();
    
    EXPECT_GE(boot_time, 5000);  // 5 seconds minimum
    EXPECT_LE(boot_time, 10000); // 10 seconds maximum
    EXPECT_EQ(system_control.GetSystemState(), STATE_READY);
}

TEST_F(SystemControlFixture, WatchdogKickPreventTimeout)
{
    watchdog_mock.SetTimeout(2000);
    watchdog_mock.Enable();
    
    // Kick every 1 second for 5 seconds
    for (int i = 0; i < 5; i++) {
        watchdog_mock.Kick();
        Wait(1000);
    }
    
    EXPECT_FALSE(watchdog_mock.WasTriggered());
}

TEST_F(SystemControlFixture, ErrorAggregation)
{
    error_handler_mock.ReportError(0x01, SEVERITY_WARNING);
    error_handler_mock.ReportError(0x05, SEVERITY_CRITICAL);
    
    EXPECT_TRUE(system_control.HasErrors());
    EXPECT_EQ(system_control.GetActiveErrorCount(), 2);
    EXPECT_EQ(system_control.GetHighestErrorSeverity(), SEVERITY_CRITICAL);
}
```

## Robot Framework Integration Test Structure

```robot
*** Settings ***
Documentation  Integration Tests for S3P System Control Module
Resource       ../../resources/S3P_SystemControl/s3p_systemcontrol_pf.robot
Resource       ../../resources/S3P_Common/s3p_common_pf.robot

*** Test Cases ***
Complete Boot Sequence To Ready State
    [Documentation]    Tests full system boot
    [Tags]    integration    boot    system-control
    Power On System
    Wait For Boot Completion    10s
    Verify System State    READY
    Verify All Modules Initialized
    Verify System Health Score    90-100%
    Verify No Critical Errors

Watchdog Timeout Triggers System Reset
    [Documentation]    Tests watchdog safety mechanism
    [Tags]    integration    watchdog    safety
    Boot System To Active
    Verify Watchdog Active
    Simulate Application Hang    duration=3s
    Wait For Watchdog Timeout
    Verify System Reset
    Verify Boot Restart Automatic
    Verify Recovery Successful

Multiple Errors Aggregated And Prioritized
    [Documentation]    Tests error collection and prioritization
    [Tags]    integration    error-handling
    Inject Module Error    module=EyeBox    severity=WARNING
    Inject Module Error    module=Power    severity=CRITICAL
    Inject Module Error    module=Illumination    severity=INFO
    Read Error Summary
    Verify Error Count    3
    Verify Highest Severity    CRITICAL
    Verify Error Priority Order    Correct

System Graceful Shutdown
    [Documentation]    Tests controlled shutdown sequence
    [Tags]    integration    shutdown    graceful
    Boot System To Active
    Verify System Operational
    Request Graceful Shutdown
    Monitor Shutdown Sequence    duration=5s
    Verify All Modules Shutdown
    Verify State Saved
    Verify Power Down Complete
```

## Coverage Goals

### Code Coverage Targets
- **Line Coverage**: ≥85%
- **Branch Coverage**: ≥80%
- **Path Coverage**: ≥70%

### Functional Coverage
- ✓ Boot sequence (success and failure)
- ✓ All system state transitions
- ✓ Watchdog operation
- ✓ Error detection and aggregation
- ✓ Module health monitoring
- ✓ Graceful shutdown
- ✓ System statistics and logging
- ✓ Recovery mechanisms
- ✓ Inter-module coordination

## Related Skills
- `robot-framework-integration` - For RF test implementation
- `test-design-techniques` - For test design patterns
- `test-documentation-compliance` - For test documentation
- `project-config-utilities` - For system constants
- `test-strategy-planning` - For test planning

## Module-Specific Files

Location: `resources/S3P_SystemControl/`
- `s3p_systemcontrol_pf.robot` - Platform-specific keywords
- `s3p_systemcontrol_prj.robot` - Project-specific utilities

## Troubleshooting Common Issues

### Issue: Boot Timeout
- Check module initialization order
- Verify self-test timing
- Check power supply stability
- Monitor CPU load during boot

### Issue: Watchdog Triggering False Positives
- Increase timeout value
- Check application critical sections
- Verify kick interval
- Monitor system load

### Issue: Errors Not Being Reported
- Check error reporting paths
- Verify module health checks
- Validate error codes
- Check CAN bus communication

### Issue: System Not Recovering
- Verify recovery logic
- Check shutdown sequence
- Monitor power cycling
- Validate boot counter
