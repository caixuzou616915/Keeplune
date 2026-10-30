---
name: gtest-testcase-gen
description: >
  Implements comprehensive test cases for automotive embedded software modules using Google Test Framework,
  focusing on test structure and test case implementation.
  Use when: implementing unit test cases for C modules in automotive projects; creating test fixtures and test cases;
  setting up Google Test file structure; writing tests with AAA (Arrange-Act-Assert) pattern; testing boundary conditions and error paths.
  Triggers: "test case generation", "unit test implementation", "test structure setup".
metadata:
  author: "Lee Xin Yee, Zhao Jianbo"
  version: "1.0.0"
---
# Google Test Case Generation Skill

This skill helps implement comprehensive test cases for automotive embedded software modules using Google Test Framework, focusing on test structure and test case implementation.

## When to Use This Skill

Use this skill when:
- Implementing unit test cases for C modules in automotive projects
- Creating test fixtures and test cases
- Setting up Google Test file structure
- Writing tests with AAA (Arrange-Act-Assert) pattern
- Testing boundary conditions and error paths
- Implementing test logic for AUTOSAR module functions (vInit, vMainFunction, etc.)

## Test Infrastructure Overview

### File Locations

```
[Module Path]/test/gtest/
├── CMakeLists.txt                          # Build configuration
├── [module]_testrunner.sh                  # Test execution script
├── tests/
|   ├── unittest_[module]_pf_test.cpp      # Platform test implementation
|   └── sample_test.cpp                     # Placeholder
├── prj/
|   ├── unittest_[module]_pf/
|   |   ├── CMakeLists.txt                  # Platform variant config
|   |   └── global_overrides.h              # Global overrides
|   └── tfr/
|       ├── stub/
|       |   └── [module]_stub.h             # Stub declarations
|       └── mocks/
|           ├── mock_[module]_pf.hpp        # Mock declarations
|           └── mock_[module]_pf.cpp        # Mock implementations
└── bin/
    └── gcc-ctc/                            # Build output
```

### Common Headers Repository
Many common headers available at:
```
[Project Root]/pkg/em_s3p_hud/s3phudcommon/s3phuddef/test/gtest/common_ext/
```

## Step-by-Step Implementation

### Step 0: Verify Preprocessed Clean File Exists (Recommended)

**Purpose**: Ensure you have the macro-expanded, single-file version for accurate test case design.

#### Why Use This Step?
- Provides clear view of all function signatures (no macros)
- Shows all function implementations in one file
- Makes it easier to understand code paths and branches
- Eliminates ambiguity when designing test cases
- Helps identify all branches and conditions to cover

#### Check for Clean File
The clean file should have been generated during mock creation (Step 0 in gtest-mock-creation skill):
```
[Module Path]/core/<filename>_clean.tmp
```

**Example**:
```
pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1_clean.tmp
```

#### If Clean File Doesn't Exist
Generate it using:
```bash
cd [Project Root]
python .github/scripts/gtest/gen_standard_c.py [source_file.c] --execute --clean
```

**Example**:
```bash
cd C:\Projects\s3p_arav
python .github/scripts/gtest/gen_standard_c.py vsgen1c1.c --execute --clean
```

#### Decision Point
```
Clean file exists?
├─ YES → Use <filename>_clean.tmp for test case analysis
│         Better understanding of:
│         - Function signatures (macros expanded)
│         - All branches and conditions
│         - Complete code paths
│         - Type definitions
│
└─ NO  → Ask user if they want to generate it
    ├─ User says YES → Run gen_standard_c.py
    │                   Then proceed with clean file
    │
    └─ User says NO  → Use original <filename>.c
                        May be harder to analyze
                        May miss some branches
```

#### What to Do After Verification
- **Analyze `<filename>_clean.tmp`** for understanding code structure
- Identify all functions to test
- Count branches and conditions
- Design test cases based on expanded code
- **Still include original `<filename>.c`** in test file via `extern \"C\"`

**Throughout the rest of this skill, when analyzing code structure and designing test cases, refer to `<filename>_clean.tmp` if available.**

---

### Step 1: Set Up Test File Structure

Create: `[Module Path]/test/gtest/tests/unittest_[module]_pf_test.cpp`

```cpp
// System headers
#include "cdef.h"
#include "gtest/gtest.h"

// Mock headers
#include "../tfr/mocks/[mock header file]"

// Source file under test
extern "C" {
    #include "../../core/[module].c"
    #include "../tfr/stub/[module]_stub.h"
}

// CTC pragma to skip coverage analysis
#pragma CTC SKIP
```

### Step 2: Implement Test Fixtures

```cpp
namespace {
    using namespace std;
    using namespace testing;
    
    // Fixture for non-initialized tests
    class ModuleTestNormalFixture : public ::testing::Test
    {
    public:
        MockAllInOne mock_module;
        
        virtual void SetUp(void) {
            // Reset module state
            Module__boInitialized = FALSE;
            // Initialize other test preconditions
        }
        
        virtual void TearDown(void) {
            // Cleanup after each test
        }
    };
    
    // Fixture with initialized module
    class ModuleTestInitializedFixture : public ModuleTestNormalFixture
    {
    public:
        MockAllInOne mock_module_init;
        
        virtual void SetUp(void) {
            ModuleTestNormalFixture::SetUp();
            
            // Set up initialized state
            EXPECT_CALL(mock_module_init, Rte_Call_Function(_))
                .WillOnce(Return(E_OK));
            
            Module_vInit();
            Module__boInitialized = TRUE;
        }
    };
}
```

### Step 3: Implement Test Cases Following AAA Pattern

#### Test Case Template

```cpp
/**
* @Req_ID: REQ_[Module]_Function_TestScenario
* @Variant: S3P-DS
* @Description: Clear description of what is being tested
* @TestTechnique : <Technique1>, <Technique2>
* @Input : Test Steps :
* <br>1. Set <variable> = <value>
* <br>2. Expect <mock_function>() to be called <N> times
* <br>3. call <function_under_test>()
* @Result:
* <br>1. Expect <variable> to be equal to <expected_value>
* <br>2. Expect return value to be <expected_return>
* @FunctionSafety : No
* @Security: Non-SPR
* @TestMaturity: Released
*/
TEST_F(ModuleTestNormalFixture, Test_FunctionName_Scenario)
{
    // === ARRANGE ===
    // Set up preconditions, initialize variables, set mock expectations
    Module_tstData stTestData;
    stTestData.u8Value = 0x10;
    
    EXPECT_CALL(mock_module, Rte_Call_Function(_))
        .Times(1)
        .WillOnce(Return(E_OK));
    
    // === ACT ===
    // Call the function under test
    Std_ReturnType result = Module_vFunction(&stTestData);
    
    // === ASSERT ===
    // Verify expected results
    EXPECT_EQ(result, E_OK);
    EXPECT_EQ(stTestData.u8Value, 0x20);
}
```

### Step 4: Test Techniques Reference

Each test case **MUST** include a `@TestTechnique` annotation in its doc comment. Select one or more techniques from the following list based on what the test validates. Use comma-separated values for multiple techniques.

#### 4.1 Boundary Value Analysis (BVA)
- **Criteria:** All boundaries tested. If arrays or multiple variables/parameters are in use, combinations of boundary conditions are considered.
- **When to use:** Parameters with numeric ranges, array lengths, thresholds, min/max values.
- **Pattern:** Test at boundary value, boundary ±1 (just below, at, just above the boundary).
- **Implementation:**
```cpp
/**
* @TestTechnique : Boundary Value Analysis
*/
TEST_F(Fixture, Test_Function_BelowBoundary)
{
    uint16 pu16DataLength = EXPECTED_LENGTH - 0x01U;  // Below boundary
    result = Function(pu16DataLength);
    EXPECT_EQ(result, E_NOT_OK);
}

TEST_F(Fixture, Test_Function_AboveBoundary)
{
    uint16 pu16DataLength = EXPECTED_LENGTH + 0x01U;  // Above boundary
    result = Function(pu16DataLength);
    EXPECT_EQ(result, E_OK);
}
```
- **Naming convention:** `_MinValue`, `_MaxValue`, `_BelowBoundary`, `_AboveBoundary`, `_RoundingUp`, `_RoundingDown`

#### 4.2 Equivalence Partitioning (EP)
- **Criteria:** All equivalent classes sufficiently considered. Test cases for "negative tests" (checks for invalid, unexpected or out-of-range inputs).
- **When to use:** Inputs that can be grouped into classes with the same expected behavior.
- **Pattern:** Pick one representative value from each equivalence class (valid class, invalid class, edge class).
- **Implementation:**
```cpp
/**
* @TestTechnique : Equivalence Partitioning
*/
TEST_F(Fixture, Test_Function_AllEquivalenceClasses)
{
    struct TestCase {
        InputType input;
        ExpectedType expected;
    };
    TestCase testCases[] = {
        {VALID_INPUT_CLASS_A,   EXPECTED_A},    // Valid class A
        {VALID_INPUT_CLASS_B,   EXPECTED_B},    // Valid class B
        {INVALID_INPUT,         E_NOT_OK},      // Invalid class (negative test)
        {OUT_OF_RANGE_INPUT,    E_NOT_OK},      // Out-of-range class
    };
    for (int i = 0; i < (sizeof(testCases)/sizeof(testCases[0])); ++i) {
        result = Function(testCases[i].input);
        EXPECT_EQ(result, testCases[i].expected);
    }
}
```

#### 4.3 Fault Insertion Testing (Fault Injection Test)
- **Criteria:** The system's fault tolerance tested by injecting faults ("robustness tests", e.g., power failure).
- **When to use:** NULL pointers, invalid parameters, error return codes, shutdown states, incorrect message formats, unexpected conditions.
- **Pattern:** Inject fault → verify graceful error handling (E_NOT_OK, error codes, DET/DLT logs).
- **Implementation:**
```cpp
/**
* @TestTechnique : Fault Insertion Testing
*/
// NULL pointer injection with combinations
TEST_F(Fixture, Test_Function_NullPtr)
{
    struct Testcase {
        uint8* pu8Data;
        uint16* pu16Len;
        uint8 u8ExpectedDetCalls;
    };
    Testcase testcases[] = {
        {NULL_PTR, &validLen, 1},          // Single NULL
        {&validData, NULL_PTR, 1},         // Other param NULL
        {NULL_PTR, NULL_PTR, 2},           // Multiple NULLs
    };
    for (int i = 0; i < count; ++i) {
        EXPECT_CALL(mock, ReportError(_, _, _)).Times(testcases[i].u8ExpectedDetCalls);
        result = Function(testcases[i].pu8Data, testcases[i].pu16Len);
        EXPECT_EQ(result, E_NOT_OK);
    }
}

// Invalid status injection
TEST_F(Fixture, Test_Function_InvalidOpStatus)
{
    Dcm_OpStatusType u8OpStatus = DIAG_INVALID;
    result = Function(u8OpStatus);
    EXPECT_EQ(result, E_NOT_OK);
    EXPECT_EQ(errorCode, DCM_E_CONDITIONSNOTCORRECT);
}

// Shutdown flag injection
TEST_F(Fixture, Test_Function_ShutdownFlagSet)
{
    Module__boShutdown = TRUE;
    result = Function(validInput);
    EXPECT_EQ(result, E_NOT_OK);
}
```

#### 4.4 Memory Testing (if relevant)
- **Criteria:** Permitted amount of dynamic memory allocated. Allocated memory completely released in all situations, even in the event of errors.
- **When to use:** Functions that allocate/free dynamic memory (malloc/free, new/delete).
- **Pattern:** Verify allocation limits, verify deallocation in ALL paths including error paths.
- **Implementation:**
```cpp
/**
* @TestTechnique : Memory Testing
*/
TEST_F(Fixture, Test_Function_MemoryAllocation)
{
    // Verify allocation within permitted limits
    Function_vAllocate(PERMITTED_SIZE);
    EXPECT_NE(ptr, nullptr);
}

TEST_F(Fixture, Test_Function_MemoryReleasedOnError)
{
    // Verify memory released even on error path
    EXPECT_CALL(mock, ExternalCall()).WillOnce(Return(E_NOT_OK));
    Function_vProcess();  // Should free allocated memory despite error
    // Verify no memory leak
}
```
- **Note:** Not commonly used in embedded automotive (mostly static allocation). Apply when dynamic memory exists.

#### 4.5 Error Guessing
- **Criteria:** Failure conditions correctly handled (Exceptions).
- **When to use:** Known common failure patterns based on domain knowledge and experience.
- **Pattern:** Based on experience, guess likely error scenarios and test them.
- **Implementation:**
```cpp
/**
* @TestTechnique : Error Guessing
*/
// Double initialization
TEST_F(Fixture, Test_vInit_AlreadyInitialized)
{
    Module__boInitialized = TRUE;
    EXPECT_CALL(mock, ReportError(_, DETLOG_E_ALREADY_INITIALIZED(), _)).Times(1);
    Module_vInit();
    // Verify no re-initialization occurred
}

// Calling function when not initialized
TEST_F(Fixture, Test_vMainFunction_NotInitialized)
{
    Module__boInitialized = FALSE;
    EXPECT_CALL(mock, ReportError(_, DETLOG_E_NOT_INITIALIZED(), _)).Times(1);
    Module_vMainFunction();
}
```

#### 4.6 State Transition Testing
- **Criteria:** State Transition Tree applied. "Negative" test cases considered to test for robustness aspects (Extended State Transition Tree).
- **When to use:** State machines, mode transitions, init/shutdown sequences.
- **Pattern:** Use struct arrays to test ALL valid transitions (positive tree) AND ALL invalid transitions (negative/extended tree).
- **Implementation:**
```cpp
/**
* @TestTechnique : State Transition Testing
*/
// Positive: Valid state transitions
TEST_F(Fixture, Test_ReqOpMode_ValidTransitions)
{
    struct stTestCase {
        OperationMode currentMode;
        OperationMode requestedMode;
        boolean fastOff;
    };
    stTestCase testCases[] = {
        {MODE_OFF,   MODE_READY, FALSE},   // Off → Ready
        {MODE_READY, MODE_ON,    FALSE},   // Ready → On
        {MODE_ON,    MODE_READY, FALSE},   // On → Ready
        {MODE_ON,    MODE_READY, TRUE},    // On → Ready (fast)
        {MODE_ON,    MODE_ON,    FALSE},   // Same state (no-op)
    };
    for (uint8 i = 0; i < count; i++) {
        EXPECT_CALL(mock, GetCurrentMode()).WillOnce(Return(testCases[i].currentMode));
        EXPECT_CALL(mock, SetRequestedMode(_, _)).Times(1);
        result = Module_u8ReqOpMode(testCases[i].requestedMode, testCases[i].fastOff);
        EXPECT_EQ(result, E_OK);
    }
}

// Negative: Invalid state transitions (Extended State Transition Tree)
TEST_F(Fixture, Test_ReqOpMode_InvalidTransitions)
{
    stTestCase testCases[] = {
        {MODE_OFF, MODE_ON,  FALSE},   // Off → On (invalid, must go through Ready)
        {MODE_ON,  MODE_OFF, FALSE},   // On → Off (invalid, must go through Ready)
    };
    for (uint8 i = 0; i < count; i++) {
        EXPECT_CALL(mock, GetCurrentMode()).WillOnce(Return(testCases[i].currentMode));
        EXPECT_CALL(mock, ReportError(_, DETLOG_E_INVALID_OPERATION_MODE(), _)).Times(1);
        result = Module_u8ReqOpMode(testCases[i].requestedMode, testCases[i].fastOff);
        EXPECT_EQ(result, E_NOT_OK);
    }
}
```

#### Combining Techniques
Multiple techniques can be combined in a single test case when appropriate:
```
@TestTechnique : Fault Insertion Testing, State Transition Testing
@TestTechnique : Fault Insertion Testing, Boundary Value Analysis
@TestTechnique : State Transition Testing, Fault Insertion Testing
@TestTechnique : Statement Testing, Decision Testing, Condition Testing
```

---

### Step 5: Test Design Principles

**Important**: If you have `<filename>_clean.tmp` available:
1. **Analyze it first** to understand:
   - All function implementations (macros expanded)
   - All branches (if/else, switch/case, while/for)
   - All conditions and their paths
   - Function call relationships
2. **Design test cases** to cover all branches and conditions found
3. **Calculate expected coverage**: Count total branches to know your target

**Example Analysis Workflow**:
```bash
# Open the clean file to analyze
notepad pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1_clean.tmp

# Count branches (grep or manual):
# - Count 'if' statements
# - Count 'else' branches  
# - Count 'case' labels in switches
# - Count loop conditions

# Design tests to cover each branch
```

#### Boundary Testing
Always test boundary values:
```cpp
// Test minimum value
TEST_F(ModuleTestNormalFixture, Test_Function_MinValue)
{
    uint8 u8Value = 0;  // Minimum
    Module_vProcessValue(u8Value);
    // Verify behavior
}

// Test maximum value
TEST_F(ModuleTestNormalFixture, Test_Function_MaxValue)
{
    uint8 u8Value = 255;  // Maximum
    Module_vProcessValue(u8Value);
    // Verify behavior
}

// Test boundary crossing
TEST_F(ModuleTestNormalFixture, Test_Function_BoundaryPlus1)
{
    uint8 u8Threshold = 100;
    Module_vProcessValue(u8Threshold + 1);
    // Verify threshold crossing behavior
}
```

#### Valid and Invalid Inputs
Test both valid and error conditions:
```cpp
// Valid input
TEST_F(ModuleTestNormalFixture, Test_Function_ValidInput)
{
    EXPECT_CALL(mock_module, ExternalFunction(_))
        .WillOnce(Return(E_OK));
    
    Std_ReturnType result = Module_vFunction(VALID_PARAM);
    EXPECT_EQ(result, E_OK);
}

// Invalid input
TEST_F(ModuleTestNormalFixture, Test_Function_InvalidInput)
{
    EXPECT_CALL(mock_module, ExternalFunction(_))
        .WillOnce(Return(E_NOT_OK));
    
    Std_ReturnType result = Module_vFunction(INVALID_PARAM);
    EXPECT_EQ(result, E_NOT_OK);
}

// Null pointer
TEST_F(ModuleTestNormalFixture, Test_Function_NullPointer)
{
    Std_ReturnType result = Module_vFunction(NULL);
    EXPECT_EQ(result, E_NOT_OK);
}
```

#### Branch Coverage
Test all conditional branches:
```cpp
// Test TRUE branch
TEST_F(ModuleTestNormalFixture, Test_Function_ConditionTrue)
{
    Module__boFlag = TRUE;
    Module_vProcessFlag();
    // Verify TRUE path behavior
}

// Test FALSE branch
TEST_F(ModuleTestNormalFixture, Test_Function_ConditionFalse)
{
    Module__boFlag = FALSE;
    Module_vProcessFlag();
    // Verify FALSE path behavior
}
```

#### State Transitions
Verify state changes:
```cpp
TEST_F(ModuleTestNormalFixture, Test_Function_StateTransition)
{
    // === ARRANGE ===
    Module__enState = MODULE_STATE_IDLE;
    
    EXPECT_CALL(mock_module, Rte_Call_Start())
        .WillOnce(Return(E_OK));
    
    // === ACT ===
    Module_vStartOperation();
    
    // === ASSERT ===
    EXPECT_EQ(Module__enState, MODULE_STATE_RUNNING);
}
```

### Step 5: Common Test Patterns

#### Testing Init Functions
```cpp
TEST_F(ModuleTestNormalFixture, Test_vInit_Success)
{
    // === ARRANGE ===
    Module__boInitialized = FALSE;
    
    EXPECT_CALL(mock_module, NvM_ReadBlock(_, _))
        .WillOnce(DoAll(
            SetArgPointee<1>(validData),
            Return(E_OK)
        ));
    
    // === ACT ===
    Module_vInit();
    
    // === ASSERT ===
    EXPECT_TRUE(Module__boInitialized);
    EXPECT_EQ(Module__enState, MODULE_STATE_INIT);
}

TEST_F(ModuleTestNormalFixture, Test_vInit_AlreadyInitialized)
{
    // === ARRANGE ===
    Module__boInitialized = TRUE;
    
    // === ACT ===
    Module_vInit();
    
    // === ASSERT ===
    // Verify no re-initialization occurred
    EXPECT_TRUE(Module__boInitialized);
}
```

#### Testing Cyclic Functions
```cpp
TEST_F(ModuleTestInitializedFixture, Test_vMainFunction_NormalOperation)
{
    // === ARRANGE ===
    EXPECT_CALL(mock_module_init, Rte_Read_Input(_))
        .WillOnce(DoAll(
            SetArgPointee<0>(testValue),
            Return(E_OK)
        ));
    
    EXPECT_CALL(mock_module_init, Rte_Write_Output(_))
        .Times(1);
    
    // === ACT ===
    Module_vMainFunction();
    
    // === ASSERT ===
    // Verify processing occurred correctly
}
```

#### Testing Error Handling
```cpp
TEST_F(ModuleTestNormalFixture, Test_Function_ErrorRecovery)
{
    // === ARRANGE ===
    EXPECT_CALL(mock_module, ExternalCall())
        .WillOnce(Return(E_NOT_OK));
    
    EXPECT_CALL(mock_module, ReportError(_))
        .Times(1);
    
    // === ACT ===
    Module_vProcessWithError();
    
    // === ASSERT ===
    EXPECT_EQ(Module__enErrorState, MODULE_ERROR_ACTIVE);
}
```

## Mock Usage Patterns

### Setting Expectations
```cpp
// Expect call once
EXPECT_CALL(mock_module, Function(_))
    .Times(1);

// Expect call with specific parameter
EXPECT_CALL(mock_module, Function(42))
    .Times(1);

// Expect call and return value
EXPECT_CALL(mock_module, Function(_))
    .WillOnce(Return(E_OK));

// Expect multiple calls with different returns
EXPECT_CALL(mock_module, Function(_))
    .WillOnce(Return(E_OK))
    .WillOnce(Return(E_NOT_OK));

// Expect call and set output parameter
EXPECT_CALL(mock_module, Function(_, _))
    .WillOnce(DoAll(
        SetArgPointee<1>(outputValue),
        Return(E_OK)
    ));

// Match any parameter
EXPECT_CALL(mock_module, Function(_))
    .Times(AtLeast(1));
```

### Common Matchers
```cpp
_                // Any value
Eq(value)        // Equal to value
Ne(value)        // Not equal to value
Gt(value)        // Greater than value
Lt(value)        // Less than value
IsNull()         // Null pointer
NotNull()        // Non-null pointer
```

## Best Practices

1. **One Assert Per Concept**: Focus each test on one behavior
2. **Descriptive Names**: Use clear test names describing scenario
3. **Independent Tests**: Each test should run independently
4. **Fast Tests**: Keep tests fast, avoid sleeps/delays
5. **Deterministic**: Tests should always produce same result
6. **Coverage**: Aim for 100% line and branch coverage
7. **Documentation**: Use @Req_ID and @Description comments
8. **AAA Pattern**: Always follow Arrange-Act-Assert structure
9. **Clean Fixtures**: Reset state in SetUp/TearDown
10. **No Standard Library Tests**: Focus on module-specific functions

## Test Case Checklist

### Documentation:
- [ ] `@Req_ID` with function name and GUID
- [ ] `@Variant` specified (e.g., S3P-DS)
- [ ] `@Description` clearly states what is being verified
- [ ] `@TestTechnique` annotated with applicable technique(s)
- [ ] `@Input` with numbered test steps using `<br>` tags
- [ ] `@Result` with numbered expected outcomes using `<br>` tags
- [ ] `@FunctionSafety` set to Yes or No
- [ ] `@Security` set (e.g., Non-SPR)
- [ ] `@TestMaturity` set (e.g., Released)

### Test Techniques Coverage:
- [ ] **Boundary Value Analysis**: All boundaries tested (min, max, ±1); combinations considered for multiple params/arrays
- [ ] **Equivalence Partitioning**: All equivalent classes covered; negative tests for invalid/unexpected/out-of-range inputs
- [ ] **Fault Insertion Testing**: NULL pointers, invalid params, shutdown states, incorrect formats tested
- [ ] **Memory Testing** (if relevant): Dynamic memory allocated within limits; released in all paths including errors
- [ ] **Error Guessing**: Common failure patterns tested (double init, uninitialized calls, etc.)
- [ ] **State Transition Testing** (if state machine): Both valid transitions (positive tree) AND invalid transitions (extended tree) tested

### Implementation:
- [ ] Follows AAA (Arrange-Act-Assert) pattern
- [ ] Tests one specific scenario
- [ ] Covers all branches (TRUE/FALSE paths)
- [ ] Uses appropriate mock expectations with correct `.Times()` and `.WillOnce()`
- [ ] Has clear, descriptive name matching scenario
- [ ] Runs independently
- [ ] Verifies error reporting (DET/DLT) where applicable

## Next Steps

After implementing test cases, use the **gtest-run-fix** skill to:
- Build and run tests
- Analyze coverage reports
- Fix compilation issues
- Iterate to achieve 100% coverage

## References

- Full guideline: [GTEST_IMPLEMENTATION_STEPS.md](GTEST_IMPLEMENTATION_STEPS.md)
- Mock Creation Skill: [gtest-mock-creation](../gtest-mock-creation/SKILL.md)
- Build and Coverage Skill: [gtest-run-fix](../gtest-run-fix/SKILL.md)

## Output Format

When implementing tests, provide:
1. Complete test file with all test cases
2. Test fixture setup code
3. Mock expectation configurations
4. Explanation of test coverage strategy
5. List of test scenarios covered
