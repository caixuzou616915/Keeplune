---
name: robot-framework-integration
description: >-
  Guides the creation and management of Robot Framework test cases for automated
  integration testing in the S3P HUD project. Use when: creating integration tests
  spanning multiple components; building BVT (Build Verification Tests); testing
  system workflows and state transitions; validating CAN/UDS communication between
  components; writing human-readable, maintainable test suites.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# Robot Framework Integration Testing Skill

## Overview
This skill guides the creation and management of Robot Framework test cases for automated integration testing in the S3P HUD project. Robot Framework tests validate end-to-end system behavior, workflows, and multi-component interactions.

## When to Use This Skill
- Creating integration tests that span multiple components
- Building BVT (Build Verification Tests)
- Testing system workflows and state transitions
- Validating communication between components (CAN, UDS, etc.)
- Creating test suites that need to be human-readable and maintainable

## Project Structure

### Resources Folder (`resources/`)
Contains reusable components imported by test files:
- **Platform Keywords** (`*_pf.robot`): Implementation details, DID access, signal manipulation
- **Project Keywords** (`*_prj.robot`): Project-specific configurations and utilities
- Configuration files (`prjcfg_*.robot`): Global variables and constants

### Tests Folder (`tests/`)
Contains executable test suites that import and use resources:
- Test cases that exercise system functionality
- Integration test scenarios
- BVT test definitions

## Test File Structure

### Resource File Template
```robot
*** Settings ***
Documentation  Description of resource purpose
Resource   path/to/dependency.robot

*** Keywords ***
#--------------------------------- Keyword Group Description ------------------------------------------

My Custom Keyword
    [Documentation]    Brief description of what the keyword does
    [Arguments]        ${param1}    ${param2}
    Log to console     Starting keyword execution
    # Implementation here
    ${result}=    Some Operation    ${param1}
    RETURN    ${result}
```

### Test File Template
```robot
*** Settings ***
Documentation  This is a SW Automated Integration Test for S3P_HUD project.
Resource       ../../resources/module_name/module_pf.robot
Resource       ../../resources/module_name/module_prj.robot

*** Test Cases ***
Test Case Name - Scenario Description
    [Documentation]    Brief description of test
    [Tags]    smoke    integration    module_name
    Log to console     Starting test
    # Test implementation using keywords from resources

*** Keywords ***
# Local test-specific keywords (if needed)
```

## Key Patterns

### 1. Keyword Organization
Group related keywords with section comments:
```robot
*** Keywords ***
#--------------------------------- DID Read Operations ------------------------------------------
Read DID And Validate
    [Arguments]    ${did_name}    ${expected_value}
    ${result}=    Read DID    ${did_name}
    Should Be Equal    ${result}    ${expected_value}

#--------------------------------- State Transition Operations ------------------------------------------
Transition To Operating State
    [Arguments]    ${mode}
    Set Signal    HudOpModeReq    ${mode}
    Wait Until Keyword Succeeds    10s    1s    Verify State    ${mode}
```

### 2. Variable Management
Define project-wide variables in resource files:
```robot
*** Variables ***
# ECU States
${ECU_Shutdown}         0x00
${ECU_Standby}          0x01
${ECU_Ready}            0x02
${ECU_DispOn}           0x03

# Voltage Settings
${NormalVoltage}        14
${NormalCurrent}        5
```

### 3. Imports and Dependencies
Always specify dependencies clearly:
```robot
*** Settings ***
Documentation  Platform-specific keywords for module_name
Resource       ../../resources/S3P_Common/s3p_common_pf.robot
Resource       ../../resources/dnga_common/dnga_common_pf.robot
```

### 4. Test Tagging Convention
Use tags for test organization and filtering:
- `smoke` - Quick sanity checks
- `regression` - Full regression testing
- `integration` - Integration tests
- `bvt` - Build verification tests
- `module_name` - Component-specific tests
- `slow` - Tests that take longer to execute

```robot
Test Case Name
    [Tags]    integration    module_name    regression
    # Test implementation
```

## Common Keywords to Implement

### Communication Keywords
```robot
Read DID And Validate
    [Arguments]    ${service}    ${did}    ${expected}
    ${actual}=    Read DID    ${service}    ${did}
    Should Be Equal    ${actual}    ${expected}

Send UDS Request
    [Arguments]    ${service_id}    ${data}
    ${response}=    Send CAN Message    ${service_id}    ${data}
    RETURN    ${response}
```

### State Management Keywords
```robot
Verify Operating State
    ${expected}=    Set Variable    "OperationMode": 0
    ${actual}=    Read Did And Validate    Service    DID    ${expected}
    Should Contain    ${actual}    ${expected}

Transition To State
    [Arguments]    ${target_state}
    Set Signal    StateRequest    ${target_state}
    Wait Until Keyword Succeeds    5s    500ms    Verify State    ${target_state}
```

### Setup/Teardown Keywords
```robot
Initialize Test Environment
    Log to console    Initializing test environment
    Connect To CAN    ${CAN_CONFIG}
    Reset ECU
    Wait Until Ready    10s

Cleanup Test Environment
    Log to console    Cleaning up test environment
    Reset ECU
    Disconnect From CAN
```

## Best Practices

### 1. Keyword Naming
- Use descriptive, action-oriented names
- Start with verb: `Read`, `Verify`, `Set`, `Transition`, etc.
- Include context: `EyeBox Expect in Operating State`
- Avoid abbreviations that reduce clarity

### 2. Documentation
Every keyword should have a clear `[Documentation]` field:
```robot
My Keyword
    [Documentation]    Reads the EyeBox status DID and validates it matches expected values
    [Arguments]    ${expected_status}
    # Implementation
```

### 3. Reusability
- Put common logic in resource files
- Create generic keywords that accept parameters
- Avoid hardcoding values; use variables instead

### 4. Error Handling
Use appropriate error handling patterns:
```robot
Safe Operation
    TRY
        Perform Operation
    EXCEPT    Error occurred
        Log    Operation failed: ${error}
        Cleanup Resources
    END
```

### 5. Logging
Add meaningful console output for debugging:
```robot
My Keyword
    Log to console    Starting operation with param=${param}
    ${result}=    Do Something    ${param}
    Log to console    Operation completed, result=${result}
    RETURN    ${result}
```

## Test Data Management

### Use Variables for Configuration
```robot
*** Variables ***
${TIMEOUT_STANDARD}     10s
${TIMEOUT_EXTENDED}     30s
${RETRY_INTERVAL}       500ms
${MAX_RETRIES}          5

${CAN_BUS_NAME}         CANoe_Virtual_Channel_1
${UDS_SESSION_TYPE}     ${0x01}  # Default session
```

### External Configuration
For complex configurations, reference external files:
```robot
*** Settings ***
Variables    ../config/project_variables.py
```

## Debugging Tips

1. **Use extensive logging**: `Log to console` and `Log` statements help trace execution
2. **Break down complex tests**: Use many small keywords instead of large test cases
3. **Add debug output**: Include variable values in log statements
4. **Use test tags**: Run specific test subsets during development

## Project-Specific Resources

This project uses:
- **CANoe** for CAN simulation and signal manipulation
- **UDS** (Unified Diagnostic Services) for ECU communication
- **Multiple DIDs** for data access
- **State machines** for component behavior
- **Hardware integration** with power supplies and I2C connections

Reference the project resources folder for available keywords and variables specific to your module.

## Resources Location
- Keywords: `resources/<MODULE_NAME>/<MODULE_NAME>_pf.robot` (platform) and `_prj.robot` (project)
- Configuration: `resources/prjcfg_*.robot`
- Common utilities: `resources/<COMMON_MODULE>/`

## Related Skills
- `test-documentation-compliance` - For test documentation requirements
- `test-design-techniques` - For test case design patterns
- `project-config-utilities` - For project-specific configurations
- Module-specific skills (e.g., `s3p-eyebox-module`) - For component-specific keywords
