---
name: gtest-mock-creation
description: >
  Creates comprehensive Google Mock (GMock) and stub files for plain C source files in automotive embedded systems.
  Use when: creating mock files for C modules that need unit testing; creating stub header files for test infrastructure;
  setting up test infrastructure for automotive embedded software; mocking RTE functions; mocking external module dependencies.
  Triggers: "mock generation", "stub creation", "test infrastructure".
metadata:
  author: "Lee Xin Yee, Zhao Jianbo"
  version: "1.0.0"
---
# Google Mock and Stub Creation Skill

This skill helps create comprehensive Google Mock (GMock) and stub files for plain C source files in automotive embedded systems, following the latest project guidelines and AUTOSAR standards.

## When to Use This Skill

Use this skill when:
- Creating mock files for C modules that need unit testing
- Creating stub header files for test infrastructure
- Setting up test infrastructure for automotive embedded software
- Mocking RTE (Runtime Environment) functions
- Mocking external module dependencies (SigCtl, NvM, ComM, etc.)
- Mocking internal STATIC functions within a module
- Following AUTOSAR and automotive coding standards
- Resolving type conflicts between test and production code

## Prerequisites

Before using this skill, ensure:
- Source .c file exists with function declarations
- Header files (.h, 1ci.h, 1ca.h) are available
- Understanding of static vs. external linkage in C
- Familiarity with Google Test Framework basics

## Mock and Stub File Structure

For a source file `[module].c`, create:
```
[Module Path]/test/gtest/prj/tfr/
├── mocks/
│   ├── mock_[MODULE]_pf.hpp    # Mock class declarations
│   └── mock_[MODULE]_pf.cpp    # Mock implementations and C wrappers
└── stub/
    └── [MODULE]_stub.h         # Type definitions and declarations
```

## Step-by-Step Process

### Step 0: Generate Preprocessed Clean File (Recommended)

**Purpose**: Generate a macro-expanded, single-file version of the source code for accurate analysis.

#### Why Use This Step?
- Expands all macros (STATIC, function-like macros, etc.)
- Merges all #include files into one file
- Provides pure C standard code without preprocessor directives
- Eliminates ambiguity in function signatures and types
- Makes dependency analysis more accurate

#### Script Location
```
[Project Root]\.github\scripts\gtest\gen_standard_c.py
```

#### Usage
```bash
cd [Project Root]
python .github/scripts/gtest/gen_standard_c.py [source_file.c] --execute --clean
```

**Example**:
```bash
cd C:\Projects\s3p_arav
python .github/scripts/gtest/gen_standard_c.py vsgen1c1.c --execute --clean
```

#### Expected Output
```
Found: pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1.c

Original command:
[compilation command shown]

Modified command:
[preprocessor command with -E flag]

Command saved to: gen.bat

================================================================================
Executing: gen.bat
================================================================================

Command executed successfully!
Return code: 0

Cleaning preprocessed file...
Input:  pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1_new.tmp
Output: pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1_clean.tmp

Cleaning completed:
  Lines read:               45,678
  Lines written:            12,345
  Lines skipped (#line):    5,432
  Lines skipped (empty):    27,901

Cleaned file saved to: pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1_clean.tmp
```

#### Generated Files
- `<filename>_new.tmp`: Preprocessed file with #line directives (in source directory)
- `<filename>_clean.tmp`: Cleaned file without #line directives and empty lines (in source directory)
- `gen.bat`: Batch file with preprocessor command (in project root)

#### Important Notes
1. **If preprocessing fails**: Pause and ask the user if they want to continue with the original source file.
2. **If successful**: Use `<filename>_clean.tmp` for all subsequent analysis and mock generation.
3. **Fallback**: If preprocessing fails or user chooses to skip, proceed with the original source file.

#### Decision Point
```
Preprocessing successful?
├─ YES → Use <filename>_clean.tmp for mock generation
│         All function signatures are expanded and clear
│         All macros are resolved
│         Single file contains all dependencies
│
└─ NO  → Ask user if they want to continue
    ├─ User says YES → Use original <filename>.c
    │                   May encounter macro-related issues
    │                   May need manual signature analysis
    │
    └─ User says NO  → Stop and investigate preprocessing error
                        Check compile_commands.json
                        Verify build configuration
```

#### What to Do After Preprocessing
- **Analyze `<filename>_clean.tmp`** instead of original source file
- All STATIC macros are expanded to `static`
- All function-like macros are expanded to their actual implementations
- All type definitions are visible in one file
- External dependencies are clearly visible

---

### Step 1: Analyze Source File (or Clean File)

**Note**: If Step 0 was successful, analyze `<filename>_clean.tmp` instead of `<filename>.c`.

#### 1.1 Identify External Dependencies
List all functions from OTHER modules:
- RTE functions: `Rte_Call_*`, `Rte_Read_*`, `Rte_Write_*`
- Standard library: `strnlen`, `memcpy`, etc.
- Other module APIs: `SigCtl_*`, `NvM_*`, `ComM_*`
- Adapter/platform functions

#### 1.2 Identify Internal Functions
List all STATIC (file-scope) functions:
- These use the `STATIC` macro (defined as `static` in production)
- Only mock those called by functions under test
- Group by functional responsibility

#### 1.3 Create Dependency Map
```
Function Under Test
    ├── Calls Internal Function A  → Internal Mock
    ├── Calls Internal Function B  → Internal Mock
    └── Calls External Function C  → MockAllInOne
```

#### 1.4 Reference File Selection
- If `<filename>_clean.tmp` exists and preprocessing was successful:
  - **Primary reference**: `<filename>_clean.tmp` (for function signatures, type analysis)
  - **Secondary reference**: Original `<filename>.c` (for conditional compilation context)
- If preprocessing failed or was skipped:
  - **Primary reference**: Original `<filename>.c`
  - May need to manually expand macros

**Throughout the rest of this skill, when referring to "source file", use the appropriate reference file as determined above.**

### Step 2: Update CMakeLists.txt for Mock and Stub Files

After creating mock and stub files, update the CMakeLists.txt to reference them:

**File**: `[Module Path]/test/gtest/CMakeLists.txt`

#### Update Mock Files Section
```cmake
################ Test Case mock files #################
set(MOCK_FILES
    ${TFR_MOCKS_DIR}/mock_[module]_pf.cpp
    ${TFR_MOCKS_DIR}/mock_[module]_pf.hpp
)  
source_group("Mocks"                FILES ${MOCK_FILES})
```

#### Update Stub Files Section
```cmake
################ Test Case stub files #################
set(STUB_FILES
    ${TFR_STUBS_DIR}/[module]_stub.h
) 
source_group("Stub"                FILES ${STUB_FILES})
```

**Important**: Always ensure MOCK_FILES and STUB_FILES in CMakeLists.txt match the actual files in the directories.

**Note**: Test file updates are handled in the [gtest-implementation](../gtest-implementation/SKILL.md) skill.

### Step 3: Create Mock Header (mock_[module]_pf.hpp)

```cpp
#pragma once

#ifndef MOCK_[MODULE]_PF_HPP
#define MOCK_[MODULE]_PF_HPP

extern "C" {
    #include "[module]_stub.h"
    #include "Rte_[MODULE].h"
    #include "[module]1c1.h"
    #include "[module]1ca.h"  // Adapter
    #include "[module]1ci.h"  // Internal types
}

// ============================================================================
// EXTERNAL DEPENDENCIES MOCK (MockAllInOne)
// ============================================================================
struct MockAllInOne
{
    MockAllInOne();
    ~MockAllInOne();
    
    // Mock all external dependencies
    MOCK_METHOD<N>(<function_name>, <return_type>(<param_types>));
    // ... more external function mocks
};

// ============================================================================
// INTERNAL FUNCTION MOCKS (Grouped by Functionality)
// ============================================================================

// Group 1: Request Application Functions
struct Mock_[Module]_Internal_RequestApplication {
    Mock_[Module]_Internal_RequestApplication();
    ~Mock_[Module]_Internal_RequestApplication();
    
    MOCK_METHOD<N>(<function_name>, <return_type>(<param_types>));
};

// Group 2: Process State Functions
struct Mock_[Module]_Internal_ProcessState {
    Mock_[Module]_Internal_ProcessState();
    ~Mock_[Module]_Internal_ProcessState();
    
    MOCK_METHOD<N>(<function_name>, <return_type>(<param_types>));
};

#endif /* MOCK_[MODULE]_PF_HPP */
```

### Step 4: MOCK_METHOD Macro Usage

```cpp
MOCK_METHOD0(FunctionName, ReturnType());                      // 0 parameters
MOCK_METHOD1(FunctionName, ReturnType(Type1));                 // 1 parameter
MOCK_METHOD2(FunctionName, ReturnType(Type1, Type2));          // 2 parameters
MOCK_METHOD3(FunctionName, ReturnType(Type1, Type2, Type3));   // 3 parameters
// ... up to MOCK_METHOD10
```

**Examples:**
```cpp
// void function, no parameters
MOCK_METHOD0(Module__vProcessState, void());

// Returns uint8, 2 parameters
MOCK_METHOD2(Module__u8GetValue, uint8(uint8 index, boolean flag));

// Returns pointer, 5 parameters
MOCK_METHOD5(Module__u8ReadDidElement, Std_ReturnType(
    Module_tenDidElement enDidElementId,
    uint8* pu8Data,
    Dcm_OpStatusType u8OpStatus,
    uint16* pu16DataLength,
    Dcm_NegativeResponseCodeType* pu8ErrorCode
));
```

### Step 5: Create Mock Implementation (mock_[module]_pf.cpp)

```cpp
#include "gtest/gtest.h"
#include "[module]_stub.h"
#include "mock_[MODULE]_pf.hpp"

using namespace ::testing;
using namespace std;

// ============================================================================
// GLOBAL MOCK INSTANCE POINTERS
// ============================================================================
MockAllInOne* mock_all_in_one = nullptr;
Mock_[Module]_Internal_RequestApplication* mock_reqAppl = nullptr;

// ============================================================================
// MockAllInOne IMPLEMENTATION
// ============================================================================
MockAllInOne::MockAllInOne()
{
    mock_all_in_one = this;
}

MockAllInOne::~MockAllInOne()
{
    mock_all_in_one = nullptr;
}

// ============================================================================
// C WRAPPER FUNCTIONS FOR EXTERNAL DEPENDENCIES ONLY
// ============================================================================
// CRITICAL: All wrapper functions MUST be wrapped in extern "C" block
// to provide C linkage for the C code to call them

extern "C" {

ReturnType FunctionName(ParamType1 param1, ParamType2 param2)
{
    if (mock_all_in_one != nullptr) {
        return mock_all_in_one->FunctionName(param1, param2);
    }
    return DEFAULT_VALUE;  // Optional: provide safe default
}

// More external function wrappers...

} // extern "C"

// ============================================================================
// INTERNAL MOCK CLASS IMPLEMENTATIONS
// ============================================================================
Mock_[Module]_Internal_RequestApplication::Mock_[Module]_Internal_RequestApplication()
{
    mock_reqAppl = this;
}

Mock_[Module]_Internal_RequestApplication::~Mock_[Module]_Internal_RequestApplication()
{
    mock_reqAppl = nullptr;
}
```

**CRITICAL REQUIREMENTS:**

1. **extern "C" for Wrapper Functions**: ALL C wrapper functions MUST be wrapped in an `extern "C"` block to provide C linkage. Without this, you will get linker errors like `undefined reference to 'FunctionName'`.

2. **Only External Dependencies Get Wrappers**: Create C wrapper functions ONLY for external dependencies in MockAllInOne. Do NOT create wrappers for internal STATIC functions.

3. **Null Pointer Safety**: Optionally check if mock pointer is not null before calling mock method to avoid crashes if mock is not initialized.
```

### Step 6: Create Stub Header ([module]_stub.h)

Place in: `test/gtest/prj/tfr/stub/[module]_stub.h`

#### **CRITICAL: Stub File Rules**

⚠️ **STUB FILES MUST ONLY CONTAIN:**
1. ✅ `#include` directives for required headers
2. ✅ `#define` macros for test-specific configuration
3. ✅ Type definitions (typedef, struct declarations) if absolutely necessary
4. ✅ Function prototypes/declarations if needed for wrapper functions
5. ✅ Type definition for NvM_BlockType related need to declare, look for declaration (i.e. NvmRomBlocks.c) and declare with initial values
6. ✅ Static variables defined in the source file

⚠️ **STUB FILES MUST NEVER CONTAIN:**
1. ❌ Variable definitions (e.g., `uint8 variable = 0;`)
2. ❌ Global variable declarations (e.g., `extern uint8 variable;`)
3. ❌ Function implementations
4. ❌ Initialization of any data structures

**Why?** Variable definitions in stub files cause **type redefinition errors** when the source file is included in tests via `extern "C"`. The source file already defines these variables, and including them again creates conflicts.

#### Purpose
The stub header provides necessary type definitions and declarations for the test environment without redefining types that exist elsewhere (like in `cdef.h`).

#### Correct Stub File Template

```cpp
#ifndef [MODULE]_STUB_H
#define [MODULE]_STUB_H

// ============================================================================
// DESCRIPTION
// ============================================================================
// This stub file provides necessary header includes and type definitions
// for testing the [module] component. It should ONLY contain includes and
// macros - NO variable definitions or function implementations.

// ============================================================================
// SYSTEM HEADERS (in extern "C" block)
// ============================================================================
extern "C" {
    #include "Std_Types.h"           // Standard types
    #include "Rte_Type.h"            // RTE types
    #include "[module]1ca.h"         // Adapter header
    #include "[module]1ci.h"         // Internal interface header
    #include "[module]1c1.h"         // Module header
    // ... add more as needed
}

// ============================================================================
// TEST-SPECIFIC MACROS
// ============================================================================
// Define any test-specific configuration macros here

#ifndef SWL_USE_DOUBLE_BANK
#define SWL_USE_DOUBLE_BANK          // Example: Enable feature for testing
#endif

#ifndef [MODULE]_GTEST
#define [MODULE]_GTEST               // Test environment flag
#endif

// ============================================================================
// TYPE DEFINITIONS (ONLY IF ABSOLUTELY NECESSARY)
// ============================================================================
// Only add type definitions here if they are missing from the headers above
// and are required for compilation. Prefer fixing the actual headers instead.

// Example (use sparingly):
// typedef struct {
//     uint8 field1;
//     uint16 field2;
// } TestOnlyType_t;

#endif // [MODULE]_STUB_H
```

#### What to Include
✅ **Include**:
- Standard type headers (`Std_Types.h`, `Rte_Type.h`)
- Module-specific headers (`[module]1ca.h`, `[module]1ci.h`, `[module]1c1.h`)
- Type definition headers needed by the module
- Headers with structure definitions used in tests

❌ **DO NOT Include**:
- Headers that redefine basic types (conflicts with `cdef.h`)
- Implementation files (.c files)
- Headers already included by `global_overrides.h`
- Variable definitions or global variable declarations

#### Common Mistakes and Fixes

**❌ WRONG - Including variable definitions:**
```cpp
// stub file - DON'T DO THIS!
extern "C" {
    #include "module.h"
}

// WRONG - Don't define variables here!
uint8 ModuleName__u8Variable = 0;
boolean ModuleName__boInitialized = FALSE;
```

**✅ CORRECT - Only includes:**
```cpp
// stub file - CORRECT
extern "C" {
    #include "module.h"
}
// Variables are defined in the source file and will be included
// in the test file via extern "C" { #include "module.c" }
```

**❌ WRONG - Function implementations:**
```cpp
// stub file - DON'T DO THIS!
extern "C" {
    #include "module.h"
}

void HelperFunction(void) {
    // Implementation here
}
```

**✅ CORRECT - Function prototypes only (if needed for wrappers):**
```cpp
// stub file - CORRECT (if you need forward declarations)
extern "C" {
    #include "module.h"
}

// Function prototypes for wrapper functions (if needed)
// These are implemented in the mock .cpp file
void WrapperFunction(void);
```

#### Handling Type Conflicts
If you encounter type redefinition errors:

**Problem**: `conflicting declaration 'typedef unsigned int uint32'`

**Solution**:
```cpp
// WRONG - Don't redefine basic types
typedef unsigned int uint32;

// CORRECT - Let cdef.h handle basic types
// Just include the headers you need
extern "C" {
    #include "Std_Types.h"  // Includes basic types
}
```

#### Example with Module-Specific Types (usmngsm module)
```cpp
#ifndef USMNGSM_STUB_H
#define USMNGSM_STUB_H

// ============================================================================
// DESCRIPTION
// ============================================================================
// Stub file for User State Manager (usmngsm) component testing.

// ============================================================================
// SYSTEM HEADERS
// ============================================================================
extern "C" {
    // Standard types
    #include "Std_Types.h"
    #include "Rte_Type.h"
    
    // Module headers
    #include "usmngsm1ca.h"   // Adapter interface
    #include "usmngsm1ci.h"   // Internal interface
    #include "usmngsm1c1.h"   // Public interface
    
    // Module-specific type definitions (if needed)
    #include "usmngsm_types.h"
}

// ============================================================================
// TEST-SPECIFIC MACROS
// ============================================================================
#ifndef USMNGSM_GTEST
#define USMNGSM_GTEST
#endif

#endif /* USMNGSM_STUB_H */
```

#### Troubleshooting Stub File Issues

**Error:** `error: conflicting declaration` or `error: redefinition of 'variable'`

**Cause:** Variable is defined both in the stub file and in the source file.

**Solution:** Remove ALL variable definitions from the stub file. Only keep `#include` directives.

---

**Error:** `error: 'Type' does not name a type`

**Cause:** Missing type definition or header include.

**Solution:** 
1. First, try adding the appropriate header file to the stub's `extern "C"` block
2. If the type is truly missing, add a typedef (but this indicates a problem in the source headers)

---

**Error:** `undefined reference to 'function'`

**Cause:** Function is declared but not defined anywhere, or not properly mocked.

**Solution:**
1. If it's an external dependency, add it to the mock class and implement the wrapper
2. If it's an internal static function, check if you need to create an internal mock class

---

**Error:** `error: 'Type' already defined`

**Cause:** Type is defined in multiple places (stub file and included headers).

**Solution:** Remove the type definition from the stub file. Let the included headers provide it.

#### Stub File Best Practices

1. **Minimize Content**: Keep stub files as minimal as possible. They should primarily be include wrappers.

2. **Document Why**: If you must add a typedef or macro, document WHY it's needed:
   ```cpp
   // NOTE: CustomType_t is not defined in any header and is required for testing
   typedef struct { uint8 field; } CustomType_t;
   ```

3. **Check Source First**: Before adding anything to the stub, check if it can be obtained from existing headers.

4. **Use Conditional Compilation**: Match the module's conditional compilation:
   ```cpp
   #if(STD_ON == PROJECT_FEATURE)
       #include "feature_specific_header.h"
   #endif
   ```

5. **Header Guard Naming**: Use clear, unique names:
   ```cpp
   #ifndef MODULE_STUB_H
   #define MODULE_STUB_H
   // ...
   #endif // MODULE_STUB_H
   ```

6. **Order Matters**: Include headers in dependency order (base types first, then derived types):
   ```cpp
   extern "C" {
       #include "Std_Types.h"      // Base types first
       #include "Rte_Type.h"       // Then RTE types
       #include "module_types.h"   // Then module-specific types
       #include "module.h"         // Finally module interface
   }
   ```

7. **Section Comments**: Use clear section dividers for organization:
   ```cpp
   // ============================================================================
   // SYSTEM HEADERS
   // ============================================================================
   ```

#### Common Issues

**Issue 1: Header Not Found**
```
fatal error: [module]1ca.h: No such file or directory
```
**Solution**: Check if the header exists in your module. If not, remove the include line.

**Issue 2: Type Redefinition**
```
error: conflicting declaration 'typedef unsigned short uint16'
```
**Solution**: Remove type definitions from stub file. Let `cdef.h` (included via `global_overrides.h`) handle basic types.

**Issue 3: Circular Dependencies**
**Solution**: Only include headers directly needed. Avoid including the source file's own header if it creates circular dependencies.

**Issue 4: Cannot Mock SYN_ Macros Directly**
```
error: expected identifier before '(' token
   MOCK_METHOD0(SYN_Adc_GetGroupStatus, Adc_StatusType());
```
**Problem**: Attempting to mock function-like macros (e.g., `SYN_Adc_GetGroupStatus()`, `SYN_DTC_u8SetDTCStatusPassed()`) that expand with parameters.

**Solution**: Mock the **underlying functions** that the macros call, not the macros themselves.

Example:
```cpp
// ❌ WRONG: Trying to mock the macro
#define SYN_Adc_GetGroupStatus()  Adc_GetGroupStatus(AdcConf_AdcGroup_AmSeS_TemperatureGroup_Cfg)
MOCK_METHOD0(SYN_Adc_GetGroupStatus, Adc_StatusType());  // FAILS!

// ✅ CORRECT: Mock the underlying function
MOCK_METHOD1(Adc_GetGroupStatus, Adc_StatusType(Adc_GroupType Group));

// C wrapper
Adc_StatusType Adc_GetGroupStatus(Adc_GroupType Group)
{
    return mock_all_in_one->Adc_GetGroupStatus(Group);
}

// In tests, the macro expands correctly:
EXPECT_CALL(mock_ext, Adc_GetGroupStatus(_)).WillOnce(Return(ADC_IDLE));
```

Common macro patterns to watch for:
- `SYN_Adc_*` macros → Mock underlying `Adc_*` functions
- `SYN_DTC_*` macros → Mock underlying `DTC_u8SetDTCFailure` function
- `SYN_DETServ_*` macros → Mock underlying `Det_ReportError` function

**Issue 5: MOCK_METHOD Parameter Count Mismatch**
```
error: static assertion failed: MOCK_METHOD<N> must match argument count.
   MOCK_METHOD9(HVAC_Library_Division32, sint32(...8 parameters...));
```
**Problem**: MOCK_METHOD9 used but function only has 8 parameters.

**Solution**: Count function parameters carefully, excluding return type.
```cpp
// Function signature: sint32 HVAC_Library_Division32(sint32 a, sint32 b, sint32 c, sint32 d, sint8 e, sint8 f, sint8 g, boolean h)
// That's 8 parameters, not 9!

// ✅ CORRECT:
MOCK_METHOD8(HVAC_Library_Division32, sint32(sint32 s32Dividend, sint32 s32Divisor, 
    sint32 s32MaxOutput, sint32 s32MinOutput, sint8 s8DividendFractDigits, 
    sint8 s8DivisorFractDigits, sint8 s8OutputFractDigits, boolean boSaturation));
```

**Issue 6: Type Already Defined in Headers**
```
error: conflicting declaration 'typedef uint8 Adc_StatusType'
```
**Problem**: Stub file redefining types already declared in included headers (e.g., `Adc_StatusType` is an enum in `Adc.h`).

**Solution**: Don't redefine types that come from included headers. Only add forward declarations for truly missing types.
```cpp
// ❌ WRONG: Redefining existing types
#ifndef Adc_StatusType
typedef uint8 Adc_StatusType;  // Already defined as enum in Adc.h!
#endif

// ✅ CORRECT: Let the header define it
extern "C" {
    #include "Adc.h"  // Provides Adc_StatusType enum
}
// Note: Do not redefine
```

**Issue 7: Conflicting extern/static Declarations**
```
error: 'Module__stSigCtlContext' was declared 'extern' and later 'static'
```
**Problem**: Stub file declares variable as `extern` but source file defines it as `static` using a macro.

**Solution**: Don't declare the variable in stub file. Let the source file handle it.
```cpp
// ❌ WRONG: In stub file
extern SigCtl_tstContext AmbSTemp__stSigCtlContext;  // Conflicts with static definition

// ✅ CORRECT: Comment it out or remove
// Note: AmbSTemp__stSigCtlContext is defined in ambstemp1c1.c - do not declare extern here
```

**Issue 8: Missing Function Wrapper for ASR40 Variants**
```
undefined reference to `NvM_ASR40_SetRamBlockStatus'
```
**Problem**: Code calls `NvM_SetRamBlockStatus` but it's defined as a macro to `NvM_ASR40_SetRamBlockStatus`.

**Solution**: Add wrapper for the ASR40 variant name if the macro maps to it.
```cpp
// If macro exists: #define NvM_SetRamBlockStatus  NvM_ASR40_SetRamBlockStatus

// In mock .hpp:
MOCK_METHOD2(NvM_SetBlockProtection, Std_ReturnType(NvM_BlockIdType BlockId, boolean ProtectionEnabled));
// Note: May need ASR40 variant wrapper

// In mock .cpp:
Std_ReturnType NvM_SetRamBlockStatus(NvM_BlockIdType BlockId, boolean Changed)
{
    return mock_all_in_one->NvM_SetBlockProtection(BlockId, Changed);
}

// Add ASR40 variant wrapper if needed:
Std_ReturnType NvM_ASR40_SetRamBlockStatus(NvM_BlockIdType BlockId, boolean Changed)
{
    return NvM_SetRamBlockStatus(BlockId, Changed);
}
```

---

### Step 7: Update CMakeLists.txt Include Paths (Automatic)

**Purpose**: Automatically scan all includes from mock, stub, and source files, then update the variant-specific CMakeLists.txt with missing header paths to prevent compilation errors.

#### Why This Step Is Critical
After creating mock and stub files, you've introduced new `#include` directives. The build system needs to know where to find these headers. Missing include paths cause compilation failures like:
```
fatal error: [header_name].h: No such file or directory
```

#### Script Location
```
[Project Root]\.github\scripts\gtest\patch_cmake_lists.py
```

#### Usage
```bash
cd [Project Root]
python .github/scripts/gtest/patch_cmake_lists.py [source_file_name.c]
```

**Example**:
```bash
cd C:\Projects\s3p_arav
python .github/scripts/gtest/patch_cmake_lists.py vsgen1c1.c
```

#### What the Script Does Automatically
1. **Scans all header includes** from:
   - Source file (vsgen1c1.c)
   - Mock files (mock_vsgen_pf.hpp/cpp)
   - Stub files (vsgen_stub.h)
   - Test files (unittest_vsgen_pf_test.cpp)

2. **Searches project** for each header with priority order:
   - Priority folders (common_ext, s3phudcommon)
   - pkg/ directory
   - app/ directory
   - Module-specific directories

3. **Updates CMakeLists.txt** automatically:
   - Adds missing paths to `target_include_directories()`
   - Uses correct relative paths with `${CMAKE_CURRENT_SOURCE_DIR}`
   - Adds helpful comments showing which headers each path provides
   - Example comment: `# Auto-generated for Std_Types.h, Platform_Types.h`

4. **Reports status**:
   - Lists found headers and their locations
   - Shows paths added to CMakeLists.txt
   - Warns about headers not found (may need manual attention)

#### Expected Output
```
ℹ Starting GTF Include Path Update
ℹ Source File: vsgen1c1.c

✓ Found source file: C:\Projects\s3p_arav\pkg\em_s3p_hud\videoctl\vsgen\core\vsgen1c1.c
✓ Found test harness: C:\Projects\s3p_arav\pkg\em_s3p_hud\videoctl\vsgen\test\gtest

ℹ Collecting test source files...
ℹ Found 1 test file(s)
ℹ Found 2 mock file(s)
ℹ Found 3 stub file(s)

✓ Found 20 unique header includes

ℹ Searching for header file paths in project...
  Searching for: Std_Types.h -> Found: app/pkg/.../common_ext
  Searching for: vidcond1c1.h -> Found: pkg/em_s3p_hud/videoctl/vidcond/core
  ...

✓ Added 7 new include paths to CMakeLists.txt
  + app/pkg/em_s3p_hud/.../common_ext (for: Std_Types.h, Rte_Type.h)
  + pkg/em_s3p_hud/videoctl/vidcond/core (for: vidcond1c1.h)
  ...

✓ GTF Include Path Update Complete!
```

#### When to Run This Script
**Mandatory** after:
- Creating new mock files
- Creating new stub files
- Adding new #include statements to mock/stub files
- Modifying header dependencies

**Optional** (but recommended):
- Before first build attempt
- When switching between modules
- After updating module dependencies

#### Script Options
```bash
# Basic usage (recommended)
python .github/scripts/gtest/patch_cmake_lists.py [source_file.c]

# Remove #include lines for headers that cannot be found
python .github/scripts/gtest/patch_cmake_lists.py [source_file.c] --remove-unfound

# Specify different build variant (default: pf)
python .github/scripts/gtest/patch_cmake_lists.py [source_file.c] --variant pf
```

#### Benefits
- ✅ **Prevents compilation errors** before they happen
- ✅ **Saves time** - no manual path calculation needed
- ✅ **Documents dependencies** with auto-generated comments
- ✅ **Maintains consistency** across all test projects
- ✅ **Handles nested paths** correctly
- ✅ **Prioritizes common headers** (common_ext, s3phudcommon)

#### Integration with Mock Creation Workflow
```
Step 0: Generate clean file (optional)
   ↓
Step 1-6: Create mocks and stubs
   ↓
Step 7: Run patch_cmake_lists.py ← YOU ARE HERE
   ↓
Next: Implement test cases (gtest-testcase-gen skill)
   ↓
Build and run tests (gtest-run-fix skill)
```

#### What Happens in CMakeLists.txt
The script updates the variant-specific CMakeLists.txt:
```
[Module Path]/test/gtest/prj/unittest_[module]_[variant]/CMakeLists.txt
```

It adds entries like:
```cmake
target_include_directories(${variant_name}
    PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../../../app/pkg/em_s3p_hud/s3phudcommon/s3phuddef/test/gtest/common_ext"  # Auto-generated for Std_Types.h, Rte_Type.h, Platform_Types.h
    PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../../videoctl/vidcond/core"  # Auto-generated for vidcond1c1.h
    # ... more paths as needed
)
```

#### Troubleshooting

**If script reports headers not found:**
1. Review the list of missing headers
2. Check if they're truly needed (maybe typos in #include?)
3. Run with `--remove-unfound` to clean up if appropriate
4. Or manually locate and add to CMakeLists.txt

**If build still fails after running script:**
1. Check the script output for warnings
2. Verify all reported paths are correct
3. Re-run the script to ensure changes were applied
4. See gtest-run-fix skill for additional troubleshooting

**Important Notes:**
- The script does NOT overwrite existing manual includes
- It only adds new paths that are missing
- Generated comments help track which headers need each path
- Re-run anytime you add new mock/stub files

---

## Critical Rules for Macros and Function Signatures

### ⚠️ CRITICAL: Understanding Macros vs Functions

**THE GOLDEN RULE**: You can ONLY mock **FUNCTIONS**, never **MACROS**.

#### What is the Difference?

**Macros** are preprocessor text replacements that expand before compilation:
```c
// This is a MACRO - expands at compile time
#define SYN_Adc_ReadGroup(pBuffer) Adc_ReadGroup(AdcGroup_ID, (Type*)(pBuffer))

// When you write:
SYN_Adc_ReadGroup(buffer);

// The preprocessor expands it to:
Adc_ReadGroup(AdcGroup_ID, (Type*)(buffer));
```

**Functions** are actual compiled code that can be mocked:
```c
// This is a FUNCTION - can be mocked
Std_ReturnType Adc_ReadGroup(Adc_GroupType Group, Adc_ValueGroupType* DataBufferPtr);
```

### Macro Rule 1: Never Mock Macros

**❌ WRONG - Trying to mock a macro:**
```cpp
// In mock header
MOCK_METHOD1(SYN_Adc_ReadGroup, Std_ReturnType(Adc_ValueGroupType*));  // WRONG!

// In test
EXPECT_CALL(mock, SYN_Adc_ReadGroup(_));  // COMPILATION ERROR!
```

**✅ CORRECT - Mock the underlying function:**
```cpp
// In mock header
MOCK_METHOD2(Adc_ReadGroup, Std_ReturnType(Adc_GroupType, Adc_ValueGroupType*));

// In test
EXPECT_CALL(mock, Adc_ReadGroup(_, _));  // Correct!
```

### Macro Rule 2: Identify Macro Expansions

When you encounter a macro in the source code, you MUST:

1. **Find the macro definition** (usually in adapter or config headers)
2. **Identify the underlying function** that the macro calls
3. **Mock the underlying function**, not the macro

#### Example 1: ADC Macros

**Macro Definition:**
```c
// In adapter header: module1ci.h
#define SYN_Adc_GetGroupStatus()          Adc_GetGroupStatus(AdcConf_AdcGroup_ID)
#define SYN_Adc_ReadGroup(pBuffer)        Adc_ReadGroup(AdcConf_AdcGroup_ID, (Adc_ValueGroupType*)(pBuffer))
#define SYN_Adc_SetupResultBuffer(pBuf)   Adc_SetupResultBuffer(AdcConf_AdcGroup_ID, (Adc_ValueGroupType*)(pBuf))
#define SYN_Adc_StartGroupConversion()    Adc_StartGroupConversion(AdcConf_AdcGroup_ID)
```

**What to Mock:**
```cpp
// Mock the REAL ADC functions, not the SYN_* macros
MOCK_METHOD1(Adc_GetGroupStatus, Adc_StatusType(Adc_GroupType));
MOCK_METHOD2(Adc_ReadGroup, Std_ReturnType(Adc_GroupType, Adc_ValueGroupType*));
MOCK_METHOD2(Adc_SetupResultBuffer, Std_ReturnType(Adc_GroupType, Adc_ValueGroupType*));
MOCK_METHOD1(Adc_StartGroupConversion, void(Adc_GroupType));
```

**In Tests:**
```cpp
// ❌ WRONG
EXPECT_CALL(mock, SYN_Adc_GetGroupStatus());  // ERROR!

// ✅ CORRECT - The macro expands to this, so mock this
EXPECT_CALL(mock, Adc_GetGroupStatus(_));  // Note: takes 1 parameter (group ID)
```

#### Example 2: DET Error Reporting Macros

**Macro Definition:**
```c
// In adapter header
#define SYN_DETServ_Module_ReportErr(Instance, Api, Error) \
    (void)Det_ReportError((uint16)(Module_ID), (uint8)(Instance), (uint8)(Api), (uint8)(Error))

// Det_ReportError is further defined as:
#define Det_ReportError Det_ASR40_ReportError
```

**What to Mock:**
```cpp
// Mock the REAL Det function, not the SYN_* macro
MOCK_METHOD4(Det_ASR40_ReportError, Std_ReturnType(uint16, uint8, uint8, uint8));
```

**In Tests:**
```cpp
// ❌ WRONG
EXPECT_CALL(mock, SYN_DETServ_Module_ReportErr(_, _, _));  // ERROR! Only 3 params, but real function has 4

// ✅ CORRECT - Mock the underlying function with correct parameter count
EXPECT_CALL(mock, Det_ASR40_ReportError(_, _, _, _));  // 4 parameters: ModuleId, InstanceId, ApiId, ErrorId
```

#### Example 3: DLT Logging Macros - CANNOT BE MOCKED!

**Macro Definition:**
```c
// DLT macros expand to inline code blocks, not function calls
#define Module_DLTLOG_ERROR(msg) \
    do { \
        /* inline code here */ \
    } while(0)
```

**What to Do:**
```cpp
// In tests - DO NOT try to mock these
// ❌ WRONG
EXPECT_CALL(mock, MODULE_DLTLOG_ERROR(_));  // Cannot mock!
EXPECT_CALL(mock, DETLOG_E_ERROR());        // Cannot mock!

// ✅ CORRECT - Simply remove these expectations
// Add a comment explaining why:
// NOTE: DLT macros (MODULE_DLTLOG_*) expand to inline code and cannot be mocked.
// NOTE: DETLOG_E_* macros are not function calls and cannot be mocked.
```

### Macro Rule 3: Match Function Signatures Exactly

When creating mocks, you MUST match the **exact signature** from the real function declaration.

#### Common Signature Mistakes

**❌ WRONG - Parameter type mismatch:**
```cpp
// Real function
extern boolean TABLES_boLUTFrmtChkSign16Bits(
    const sint16 pi16Table[], 
    uint16 u16TableSize, 
    TABLES_ten2DimensionCurveMode en2DimensionCurveMode);  // Note: enum type!

// Wrong mock
MOCK_METHOD3(TABLES_boLUTFrmtChkSign16Bits, boolean(const sint16*, uint16, uint8));  // ❌ uint8 is wrong!
```

**✅ CORRECT - Exact type match:**
```cpp
// Correct mock - matches real signature exactly
MOCK_METHOD3(TABLES_boLUTFrmtChkSign16Bits, boolean(const sint16*, uint16, TABLES_ten2DimensionCurveMode));
```

**❌ WRONG - Parameter count mismatch:**
```cpp
// Real function
extern void TABLES_vAssignTable(uint32 u32TableIndex, const void* pvTableAddress);

// Wrong mock - wrong types
MOCK_METHOD2(TABLES_vAssignTable, void(uint16, const sint16*));  // ❌ uint16 and sint16* are wrong!
```

**✅ CORRECT:**
```cpp
MOCK_METHOD2(TABLES_vAssignTable, void(uint32, const void*));  // ✅ Matches exactly
```

### Macro Rule 4: C Linkage Requirements for Wrapper Functions

For mock wrapper functions in `.cpp` files to be callable from C code, they MUST have C linkage.

**❌ WRONG - No extern "C":**
```cpp
// In mock_module.cpp - WRONG!
void ExternalFunction(uint8 param) {  // C++ linkage by default
    return mock_all_in_one->ExternalFunction(param);
}
```
This causes **linker errors**: `undefined reference to 'ExternalFunction'`

**✅ CORRECT - Wrap in extern "C":**
```cpp
// In mock_module.cpp - CORRECT!
extern "C" {

void ExternalFunction(uint8 param) {  // Now has C linkage
    return mock_all_in_one->ExternalFunction(param);
}

// All other wrapper functions for external dependencies
// ...

} // extern "C"
```

**Template:**
```cpp
// ============================================================================
// C WRAPPER FUNCTIONS FOR EXTERNAL DEPENDENCIES
// ============================================================================

extern "C" {

// Wrapper for function 1
ReturnType Function1(ParamType1 p1, ParamType2 p2) {
    if (mock_all_in_one != nullptr) {
        return mock_all_in_one->Function1(p1, p2);
    }
    return DEFAULT_VALUE;  // Optional: return default if mock not set
}

// Wrapper for function 2
void Function2(ParamType param) {
    if (mock_all_in_one != nullptr) {
        mock_all_in_one->Function2(param);
    }
}

// ... more wrappers

} // extern "C"
```

### Macro Rule 5: How to Find Real Function Signatures

When creating mocks, follow these steps:

1. **Locate the function declaration** in the header files
2. **Check for typedefs** and use the actual typedef names
3. **Count parameters carefully** including the types
4. **Look for const qualifiers** and match them exactly
5. **Check pointer levels** (e.g., `Type*` vs `Type**`)

**Tools to find signatures:**
```bash
# Search for function declaration in headers
grep -r "FunctionName" path/to/headers/

# Check the actual header file
cat path/to/header.h | grep "FunctionName"
```

### Troubleshooting Checklist for Macros

When you encounter mock-related errors:

- [ ] Is this a macro or a function? (Use `grep` to find definition)
- [ ] If macro, what function does it call?
- [ ] Does the mock signature match the real function exactly?
- [ ] Are all parameter types correct (including typedefs)?
- [ ] Is the parameter count correct?
- [ ] Are wrapper functions wrapped in `extern "C"`?
- [ ] Is the mock class pointer initialized to `nullptr`?
- [ ] Are tests calling the underlying function, not the macro?
- [ ] Have you removed EXPECT_CALL for un-mockable macros?

## Mock Organization Rules

### Rule 1: MockAllInOne - External Dependencies Only

**Contains**: ALL functions from OTHER modules

✅ Include:
- RTE functions (`Rte_Call_*`, `Rte_Read_*`, `Rte_Write_*`)
- Standard library functions (`strnlen`, `memcpy`)
- Functions from other modules (`SigCtl_*`, `IllumSM_*`)
- Platform/adapter external functions
- System services (`NvM_*`, `ComM_*`, `WdgM_*`)

❌ DO NOT include:
- STATIC (static) functions from the same source file

### Rule 2: Internal Mock Classes - Grouped by Functionality

**Contains**: STATIC functions from the SAME source file

**Common groupings:**
- **RequestApplication**: Functions requesting operation modes
- **ProcessState**: State transition functions
- **ProcessPowerState**: Power state management
- **StateMachine**: State machine processing
- **ProcessTimerCountdown**: Timer management
- **WakeUpApplication**: Wake-up and initialization
- **ProcessDidElement**: Diagnostic DID handling
- **MainFunction**: Main function helpers

### Rule 3: No Duplicate Mocks

- Each function appears in ONLY ONE mock class
- STATIC (internal) → internal mock class
- External → MockAllInOne
- Never mock the same function in both places

## Key Points

### C Wrapper Functions - CRITICAL REQUIREMENTS
- **MUST use extern "C" linkage**: ALL C wrapper functions in the .cpp file MUST be wrapped in an `extern "C" { }` block
- **Only for external dependencies** in MockAllInOne - never for internal STATIC functions
- **Pattern**:
```cpp
extern "C" {
    ReturnType FunctionName(params...)
    {
        if (mock_all_in_one != nullptr) {
            return mock_all_in_one->FunctionName(params...);
        }
        return DEFAULT_VALUE;  // Optional safety
    }
}
```
- **Why**: Without `extern "C"`, the C++ compiler mangles function names, causing "undefined reference" linker errors when C code tries to call them

### Macro Mocking - CRITICAL RULES
- **NEVER mock macros directly** - you can only mock functions
- **Always find the underlying function** that a macro expands to
- **Mock the underlying function** with its exact signature
- **In tests, expect calls to the underlying function**, not the macro
- **Un-mockable macros**: DLT logging, inline code macros, assertion macros cannot be mocked - remove EXPECT_CALL for these

### Stub Files - CRITICAL RULES  
- **ONLY contain**: `#include` directives, `#define` macros, essential type definitions
- **NEVER contain**: Variable definitions, global variable declarations, function implementations
- **Why**: Variables in stub files cause redefinition errors since the source file already defines them

### Conditional Compilation
Use consistently in both .hpp and .cpp:
```cpp
// In .hpp
#if(STD_ON == PROJECT_FEATURE)
    MOCK_METHOD0(Function, ReturnType());
#endif

// In .cpp - same condition
#if(STD_ON == PROJECT_FEATURE)
extern "C" {
    ReturnType Function() {
        return mock_all_in_one->Function();
    }
}
#endif
```

### Function Signature Matching
- **Match parameter count exactly** - MOCK_METHOD3 for 3 params, not 2 or 4
- **Match parameter types exactly** - use typedefs as they are (e.g., `TABLES_ten2DimensionCurveMode`, not `uint8`)
- **Match const qualifiers** - if function has `const Type*`, mock must too
- **Match pointer levels** - `Type*` vs `Type**` matters

### Best Practices

1. **Mock Naming**: Use snake_case for global pointers, PascalCase for classes
2. **Header Guards**: Use both `#pragma once` and `#ifndef` guards
3. **StrictMock**: Use `StrictMock<MockAllInOne>` for better testing
4. **Section Comments**: Use dividers for clarity
5. **Documentation**: Comment complex mock groups
6. **Null Safety**: Check mock pointers before calling (optional but recommended)
7. **Minimal Stubs**: Keep stub files as minimal as possible

## Common Pitfalls to Avoid

❌ **Wrong**: Mocking internal functions in MockAllInOne
```cpp
struct MockAllInOne {
    MOCK_METHOD0(Module__u8InternalFunc, Std_ReturnType(...));  // This is STATIC!
};
```

✅ **Correct**: Use internal mock class
```cpp
struct Mock_Module_Internal_Process {
    MOCK_METHOD0(Module__u8InternalFunc, Std_ReturnType(...));
};
```

❌ **Wrong**: Creating C wrapper for internal functions
```cpp
Std_ReturnType Module__u8InternalFunc(...)  // NO! Internal function
{
    return mock_all_in_one->Module__u8InternalFunc(...);
}
```

✅ **Correct**: Only external functions get C wrappers

❌ **Wrong**: Incorrect parameter count
```cpp
MOCK_METHOD2(FunctionWith3Params, ReturnType(Type1, Type2, Type3));  // Wrong!
```

✅ **Correct**: Match parameter count
```cpp
MOCK_METHOD3(FunctionWith3Params, ReturnType(Type1, Type2, Type3));
```

❌ **Wrong**: Redefining types in stub file
```cpp
// In [module]_stub.h
typedef unsigned int uint32;     // WRONG! Conflicts with cdef.h
typedef unsigned short uint16;   // WRONG! Already defined
```

✅ **Correct**: Let standard headers handle types
```cpp
// In [module]_stub.h
extern "C" {
    #include "Std_Types.h"  // Provides uint8, uint16, uint32, etc.
}
```

❌ **Wrong**: Multiple declarations in stub
```cpp
// In [module]_stub.h
extern void SomeFunction(void);  // Already declared in header
void AnotherFunction(void);      // Duplicate declaration
```

✅ **Correct**: Include proper headers instead
```cpp
// In [module]_stub.h
extern "C" {
    #include "[module]1ci.h"  // Contains function declarations
}
```

❌ **Wrong**: Variable definitions in stub file
```cpp
// In [module]_stub.h
uint8 ModuleName__u8Variable = 0;       // WRONG! Causes redefinition
boolean ModuleName__boInitialized = FALSE;  // WRONG!
```

✅ **Correct**: No variable definitions in stub
```cpp
// In [module]_stub.h - ONLY includes
extern "C" {
    #include "Std_Types.h"
    #include "[module]1c1.h"
}
// Variables come from source file via test include
```

❌ **Wrong**: Trying to mock macros
```cpp
// WRONG - SYN_Adc_GetGroupStatus is a macro!
MOCK_METHOD0(SYN_Adc_GetGroupStatus, Adc_StatusType());
```

✅ **Correct**: Mock underlying function
```cpp
// Correct - mock the real function the macro calls
MOCK_METHOD1(Adc_GetGroupStatus, Adc_StatusType(Adc_GroupType));
```

❌ **Wrong**: Missing extern "C" for wrappers
```cpp
// In mock .cpp - WRONG!
void ExternalFunction(uint8 param) {
    return mock_all_in_one->ExternalFunction(param);
}
```

✅ **Correct**: Wrap in extern "C"
```cpp
// In mock .cpp - CORRECT!
extern "C" {
    void ExternalFunction(uint8 param) {
        return mock_all_in_one->ExternalFunction(param);
    }
}
```

❌ **Wrong**: Type mismatch in mock signature
```cpp
// Real function uses TABLES_ten2DimensionCurveMode (enum)
MOCK_METHOD3(TABLES_boLUTFrmtChkSign16Bits, boolean(const sint16*, uint16, uint8));  // Wrong type!
```

✅ **Correct**: Exact type match
```cpp
MOCK_METHOD3(TABLES_boLUTFrmtChkSign16Bits, boolean(const sint16*, uint16, TABLES_ten2DimensionCurveMode));
```

## Checklist

Before completing mock creation, verify:

### Analysis Phase
- [ ] Analyzed source file for external dependencies
- [ ] Identified STATIC internal functions
- [ ] Grouped internal functions by functionality
- [ ] Created dependency map (function → dependencies)
- [ ] Identified all macros and their underlying functions

### Mock Header (.hpp)
- [ ] Created mock header with proper guards (`#pragma once` and `#ifndef`)
- [ ] Declared MockAllInOne with all external dependencies
- [ ] Created internal mock classes for grouped functions
- [ ] Used correct MOCK_METHOD<N> macros (matching parameter count)
- [ ] Matched function signatures exactly (types, const, pointers)
- [ ] Handled conditional compilation consistently
- [ ] Added namespace declarations
- [ ] Mocked underlying functions for macros (not the macros themselves)

### Mock Implementation (.cpp)
- [ ] Implemented constructors/destructors for all mock classes
- [ ] Declared global mock pointers (initialized to nullptr)
- [ ] Created C wrappers for ALL external functions
- [ ] Wrapped ALL C wrappers in `extern "C"` block
- [ ] Did NOT create C wrappers for internal functions
- [ ] Handled conditional compilation consistently (matching .hpp)
- [ ] Added null pointer checks for safety (optional)

### Stub Header (_stub.h)
- [ ] Created stub header file with proper includes
- [ ] Stub file does NOT redefine types from cdef.h
- [ ] Stub file does NOT create duplicate declarations
- [ ] Stub file does NOT contain variable definitions
- [ ] Stub file does NOT contain function implementations
- [ ] Stub file includes only necessary headers in extern "C" block
- [ ] Added test-specific macros if needed
- [ ] Documented any unusual type definitions with comments

### CMakeLists.txt
- [ ] Updated CMakeLists.txt with mock file names in MOCK_FILES section
- [ ] Updated CMakeLists.txt with stub file names in STUB_FILES section
- [ ] Verified paths are correct relative to TFR_MOCKS_DIR and TFR_STUBS_DIR

### Organization and Quality
- [ ] Verified no duplicate mocks (each function in only ONE place)
- [ ] Used correct naming conventions (snake_case for pointers, PascalCase for classes)
- [ ] Added section divider comments for clarity
- [ ] Verified all external dependencies are in MockAllInOne
- [ ] Verified all internal STATIC functions are in internal mock classes
- [ ] Added comments for complex groupings or conditional code

### Testing Compilation
- [ ] Tested compilation of mock files
- [ ] Resolved any type conflicts or redefinition errors
- [ ] Verified no "undefined reference" linker errors
- [ ] Verified no "conflicting declaration" errors
- [ ] Tested that macros expand correctly in tests

## References

- Example mocks in: `test/gtest/prj/tfr/mocks/`
- Test Case Generation: [gtest-testcase-gen](../gtest-testcase-gen/SKILL.md)
- Build & Coverage: [gtest-run-fix](../gtest-run-fix/SKILL.md)

## Output Format

When creating mocks, provide:
1. Complete mock header file (mock_[module]_pf.hpp)
2. Complete mock implementation file (mock_[module]_pf.cpp)
3. Stub header file ([module]_stub.h)
4. CMakeLists.txt updates for MOCK_FILES and STUB_FILES sections
5. Explanation of mock organization decisions
6. List of external vs. internal functions identified
