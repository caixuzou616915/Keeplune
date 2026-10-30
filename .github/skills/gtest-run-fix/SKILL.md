---
name: gtest-run-fix
description: >
  Builds, executes, and troubleshoots Google Test cases for automotive embedded software modules, focusing on compilation,
  test execution, coverage analysis, and iterative fixing to achieve 100% CTC.
  Use when: building and running Google Test cases; analyzing Code Test Coverage (CTC) reports; troubleshooting compilation errors;
  fixing missing headers or dependencies; iterating to achieve 100% function, line, and branch coverage.
  Triggers: "build and run tests", "coverage analysis", "debug test failures".
metadata:
  author: "Zhao Jianbo, Lee Xin Yee"
  version: "1.0.0"
---
# Google Test Build, Run & Fix Skill

This skill helps build, execute, and troubleshoot Google Test cases for automotive embedded software modules, focusing on compilation, test execution, coverage analysis, and iterative fixing to achieve 100% CTC.

## When to Use This Skill

Use this skill when:
- Building and running Google Test cases
- Analyzing Code Test Coverage (CTC) reports
- Troubleshooting compilation errors in test projects
- Fixing missing headers or dependencies
- Iterating to achieve 100% function, line, and branch coverage
## Test Infrastructure Overview

### File Locations

```
[Module Path]/test/gtest/
+-- CMakeLists.txt                          # Build configuration
+-- [module]_testrunner.sh                  # Test execution script
+-- tests/
|   +-- unittest_[module]_pf_test.cpp      # Platform test implementation
|   +-- sample_test.cpp                     # Placeholder
+-- prj/
|   +-- unittest_[module]_pf/
|   |   +-- CMakeLists.txt                  # Platform variant config
|   |   +-- global_overrides.h              # Global overrides
|   +-- tfr/
|       +-- stub/
|       |   +-- [module]_stub.h             # Stub declarations
|       +-- mocks/
|           +-- mock_[module]_pf.hpp        # Mock declarations
|           +-- mock_[module]_pf.cpp        # Mock implementations
+-- bin/
    +-- gcc-ctc/                            # Build output
```

### Common Headers Repository
Many common headers available at:
```
[Project Root]/pkg/em_s3p_hud/s3phudcommon/s3phuddef/test/gtest/common_ext/
```

- Debugging test failures
- Resolving build configuration issues

## Prerequisites

Before using this skill, ensure:
- Mock files are generated (use gtest-mock-creation skill)
- Test cases are implemented (use gtest-testcase-gen skill)
- Test file structure is set up correctly

## Tools and Utilities

### Find-HeaderPath.ps1 Script
Located at `[Project Root]\.github\scripts\gtest\Find-HeaderPath.ps1`

**Purpose**: Quickly locate header files in the project to resolve missing header compilation errors.

**Usage**:
```powershell
.github\scripts\gtest\Find-HeaderPath.ps1 "header_name.h"
```

**Features**:
- Searches entire project directory
- Displays all matching file paths
- Shows relative paths from project root
- Provides CMakeLists.txt update recommendations
- Lists common include path patterns

**Example**:
```powershell
cd C:\Projects\s3p_arav
.github\scripts\gtest\Find-HeaderPath.ps1 "Std_Types.h"
```

This tool is essential for quickly resolving "header file not found" errors during test compilation.

## Build and Execution Process

### Step 5: Always Reference the Clean File (Critical for Debugging)

**Purpose**: Use the preprocessed clean file as your primary reference when fixing test issues.

#### Why This Matters
When troubleshooting test failures, compilation errors, or coverage gaps, **always refer to `<filename>_clean.tmp`** instead of the original source file because:

1. **Function Signatures Are Exact**: All macros like `STATIC` are expanded to `static`, eliminating ambiguity
2. **All Code Is Visible**: All #include files are merged—you see the complete implementation
3. **Macro Expansion**: Function-like macros (SYN_*, wrapper macros) are expanded to their actual calls
4. **Type Definitions**: All typedef and struct definitions are visible in context
5. **Conditional Compilation**: You see exactly which code paths are compiled based on #ifdef conditions
6. **No Surprises**: What you see is exactly what the compiler sees

#### Clean File Location
```
[Module Path]/core/<filename>_clean.tmp
```

**Example**:
```
pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1_clean.tmp
```

#### If Clean File Doesn't Exist
Generate it before proceeding:
```bash
cd [Project Root]
python .github/scripts/gtest/gen_standard_c.py [source_file.c] --execute --clean
```

**Example**:
```bash
cd C:\Projects\s3p_arav
python .github/scripts/gtest/gen_standard_c.py vsgen1c1.c --execute --clean
```

#### When to Use Clean File
Use `<filename>_clean.tmp` for:
- ✅ Understanding function signatures when fixing compilation errors
- ✅ Analyzing code branches and conditions for coverage
- ✅ Identifying all function calls and dependencies
- ✅ Verifying macro expansions
- ✅ Understanding static variable scope and usage
- ✅ Debugging test logic and expected behavior
- ✅ Counting total branches for coverage target

Use original `<filename>.c` for:
- ✅ Understanding conditional compilation context (#ifdef blocks)
- ✅ Checking original code structure and organization
- ✅ Verifying macro definitions

**Critical Rule**: When in doubt about implementation details, **always check `<filename>_clean.tmp` first**.

---

### Step 6: Update CMakeLists.txt Include Paths (Recommended)

Before building tests, it's recommended to automatically scan for missing header includes and update CMakeLists.txt using the include path updater script.

#### Script Location
```
[Project Root].github\\scripts\\gtest\\patch_cmake_lists.py
```

#### Usage
```bash
# Navigate to project root
cd [Project Root]

# Run the include path updater
python .github/scripts/gtest/patch_cmake_lists.py [source_file_name.c]
```

**Example**:
```bash
cd C:\Projects\s3p_arav
python .github/scripts/gtest/patch_cmake_lists.py vsgen1c1.c
```

#### What the Script Does
1. **Scans all header includes** from:
   - Source file (.c)
   - Test files (unittest_*_test.cpp)
   - Mock files (mock_*.hpp/cpp)
   - Stub files (stub*.h)

2. **Searches for headers** in project using priority order:
   - Priority folders (configured in script)
   - Common locations (pkg/, app/)
   - Module-specific paths

3. **Updates CMakeLists.txt** automatically:
   - Adds missing include paths to `target_include_directories()`
   - Uses correct relative paths with `${CMAKE_CURRENT_SOURCE_DIR}`
   - Adds comments showing which headers require each path
   - Example: `# Auto-generated (for: Platform_Types.h, Rte_Type.h, Std_Types.h)`

4. **Reports findings**:
   - Lists headers found and their locations
   - Shows which paths were added
   - Warns about headers not found in project

#### Expected Output
```
ℹ Starting GTF Include Path Update
ℹ Source File: vsgen1c1.c
✓ Found source file: C:\Projects\s3p_arav\pkg\em_s3p_hud\vsgen\core\vsgen1c1.c
✓ Found 19 unique header includes
ℹ Current CMakeLists.txt has 32 include directories

ℹ Searching for header file paths in project...
  Searching for: Platform_Types.h -> Found: app/pkg/.../common_ext
  ...
  
✓ Added 7 new include paths to CMakeLists.txt
  + app/pkg/em_s3p_hud/.../common_ext (for: Platform_Types.h, Rte_Type.h, Std_Types.h)
  + pkg/em_s3p_hud/vsgen/core (for: vsgen1c1.h, vsgen1ct.h)
  ...

✓ GTF Include Path Update Complete!
```

#### Script Options
```bash
# Basic usage
python .github/scripts/gtest/patch_cmake_lists.py [source_file.c]

# Remove includes for headers that cannot be found
python .github/scripts/gtest/patch_cmake_lists.py [source_file.c] --remove-unfound

# Specify different build variant (default: pf)
python .github/scripts/gtest/patch_cmake_lists.py [source_file.c] --variant pf
```

#### Benefits
- ✅ Saves time locating and calculating header paths
- ✅ Prevents compilation errors due to missing includes
- ✅ Documents which headers require each path (clear comments)
- ✅ Maintains consistent relative path format
- ✅ Reduces manual path calculation errors

#### When to Use
- **Always use** before first build attempt
- After adding new test files or mock files
- When compilation fails with "header not found" errors
- After updating module dependencies
- When switching between modules or build variants

**Note**: The script automatically detects the module structure and variant-specific CMakeLists.txt location. It will not overwrite existing manual includes.

---

### Step 7: Build and Run Tests

#### Build Commands
```bash
# Navigate to project root
cd [Project Root]

# Run module tests (full build and execution)
.github\scripts\gtest\run_module_gtest.bat [source_file_name.c]
```

**Example**:
```bash
cd C:\Projects\s3p_arav
.github\scripts\gtest\run_module_gtest.bat ambstemp1c1.c
```

#### Expected Output
```
===============================================================================
  ........ GTF -- Run script <./[module]_testrunner.sh> ........  
===============================================================================
...
[RUN] Running unittest for gcc-ctc
...
[==========] Running X tests from Y test fixtures.
[----------] Global test environment set-up.
...
[----------] X tests from [Module name]TestNormalFixture
[ RUN      ] [Module name]TestNormalFixture.Test_vInit_Success
[       OK ] [Module name]TestNormalFixture.Test_vInit_Success (0 ms)
...
[==========] X tests from Y test fixtures ran. (XXX ms total)
[  PASSED  ] X tests.
```

#### Compiling Solution Hints:
**When encountering "header file not found" errors:**

1. **Automatically update** with the include path updater:
   - Use `.github/scripts/gtest/patch_cmake_lists.py` (recommended first step)
   - See **Step 6: Update CMakeLists.txt Include Paths** above

2. **If automatic update doesn't find headers** - Search and copy manually:
   - Location: `[Project Root]\.github\scripts\gtest\patch_cmake_lists.py`
   - Location: `[Project Root]\.github\scripts\gtest\Find-HeaderPath.ps1` (for searching)

3. **Update variant CMakeLists.txt** (if needed after running scripts):
   - Location: `[Module Path]/test/gtest/prj/unittest_[module]_[variant]/CMakeLists.txt`
   - Add correct relative path in `target_include_directories()` section

**See Issue 3 for detailed instructions on resolving missing headers.**

---

### Step 8: Analyze CTC Coverage

#### Coverage Report Location
Open the CTC coverage report at:
```
- CTC coverage report: [Module Path]\test\gtest\bin\metrics\coverage\ctc\html\index.html
- `[Module Path]/test/gtest/bin/gcc-ctc/coverage/`
- `[Module Path]/test/gtest/build/coverage/`
- `[Module Path]/test/gtest/bin/metrics/reports/`
```

**Example**:
```
C:\Projects\arav_s3p\pkg\em_s3p_hud\touchctl\touchq\test\gtest\bin\metrics\coverage\ctc\html\index.html
```

#### Coverage Analysis Steps
1. Open the index.html file in a web browser
2. Navigate to the source file (`[Module name].c`) you're analyzing
3. Check coverage indicators:
   - **Red lines**: Not covered (need tests)
   - **Yellow lines**: Partially covered (missing branches)
   - **Green lines**: Fully covered

**Critical**: When analyzing uncovered code, **always refer to `<filename>_clean.tmp`** to understand:
- The exact code that needs coverage (macros expanded)
- All branches in conditions (no macro ambiguity)
- Function implementations (all includes merged)
- Why a line might be uncovered (see actual compiled code)

**Example**:
```bash
# View coverage report (shows line 245 is uncovered)
# Open: C:\Projects\s3p_arav\pkg\em_s3p_hud\videoctl\vsgen\test\gtest\bin\metrics\coverage\ctc\html\index.html
# Find vsgen1c1.c and note the uncovered lines
# Then open clean file to see what's at those lines
notepad pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1_clean.tmp
# Jump to line 245 to see the actual code
# Design test case based on expanded code
```

#### Target Coverage
- **Function Coverage**: 100%
- **Line Coverage**: 100%
- **Branch Coverage**: 100%

---

### Step 9: Iterate to Achieve 100% Coverage

#### If Coverage < 100%:

1. **Identify Uncovered Lines**
   - Review coverage report
   - Note line numbers not covered
   - Identify which functions/branches are missing

2. **Analyze Why Not Covered** (**Use `<filename>_clean.tmp`**)
   - **Open the clean file** and navigate to uncovered line numbers
   - Understand the exact code at those lines (macros expanded)
   - Determine the reason:
     * Missing test case for a specific path?
     * Unreachable code (dead code)?
     * Configuration-specific code (#ifdef blocks)?
     * Error path not tested?
   - Check function signatures in clean file (not original)
   - Trace function calls in clean file to understand dependencies

3. **Add Missing Test Cases** (Reference `<filename>_clean.tmp`)
   - Design tests based on actual function signatures from clean file
   - Create test for uncovered path (check condition in clean file)
   - Test both TRUE and FALSE branches of conditions (identify conditions in clean file)
   - Test error conditions and edge cases (verify error paths in clean file)
   - Test boundary values (check boundary logic in clean file)

4. **Re-run Tests**
   - Clean build if needed: `rm -rf bin/gcc-ctc`
   - Run: `[Project Root].github\\scripts\\gtest\\run_module_gtest.bat [source_file_name.c]`
   - Check new coverage report

5. **Repeat Until 100%**
   - Continue adding tests until all lines, branches, and functions are covered

---

### Step 10: Verify All Requirements Met

#### Final Checklist:
- [ ] All test cases implemented
- [ ] All tests pass consistently
- [ ] 100% Function coverage achieved
- [ ] 100% Line coverage achieved
- [ ] 100% Branch coverage achieved
- [ ] No memory leaks detected
- [ ] No compiler warnings
- [ ] Test documentation complete
- [ ] Uses AAA pattern (Arrange-Act-Assert)
- [ ] Proper @Req_ID, @Description, etc.

---

## Common Issues and Solutions

### Issue 0: General Debugging Principle - Always Check Clean File First
**Key Rule**: When encountering ANY issue (compilation error, test failure, coverage gap), **always check `<filename>_clean.tmp` FIRST** before attempting fixes.

**Why**: The clean file shows you:
- Exact function signatures (macros expanded)
- Actual code the compiler sees
- All includes merged into one view
- Type definitions in context
- Branch conditions without macro confusion

**Workflow**:
```bash
# 1. Generate clean file if not already done
cd [Project Root]
python .github/scripts/gtest/gen_standard_c.py [source_file.c] --execute --clean

# 2. When debugging, ALWAYS open clean file
notepad pkg/em_s3p_hud/[module_path]/core/[filename]_clean.tmp

# 3. Search for the problematic function/line in clean file
# 4. Understand the actual implementation
# 5. Design your fix based on what you see in clean file
```

**Common Mistakes to Avoid**:
- ❌ Looking only at original source (misses macro expansions)
- ❌ Guessing function signatures (check clean file)
- ❌ Assuming macro behavior (verify in clean file)
- ❌ Missing branches (count them in clean file)

**Remember**: Original source = how developer wrote it. Clean file = what compiler actually compiles.

---

### Issue 1: Mock Generation Template Placeholders
**Problem**: Mock files contain `{name}_stub.h` or `MOCK_METHOD1 (, Std_ReturnType(boolean arg0))` 
**Solution**: 
- Edit `[Module name]_mock.hpp` to replace `{name}_stub.h` with `[Module name]_stub.h`
- Remove malformed MOCK_METHOD declarations (empty function name)
- Ensure stub file doesn't conflict with cdef.h type definitions

### Issue 2: Type Conflicts (uint32, uint16, etc.)
**Problem**: `conflicting declaration 'typedef unsigned int uint32'`
**Solution**:
- Use basic C types (unsigned short, unsigned char, etc.) in stub file
- Don't redefine types already in cdef.h
- Let global_overrides.h include cdef.h first

### Issue 3: Missing Header Files
**Problem**: `fatal error: [header_name].h: No such file or directory` - any header file not found during compilation

**Solution Workflow** (2-step approach):

---

#### **Step 1️⃣: Automatically Update CMakeLists.txt (Recommended First)**

Use the automatic include path updater script to scan all includes and update CMakeLists.txt:

**Script:** `.github/scripts/gtest/patch_cmake_lists.py`

**Usage:**
```bash
cd [Project Root]
python .github/scripts/gtest/patch_cmake_lists.py [source_file_name.c]
```

**Example:**
```bash
cd C:\Projects\s3p_arav
python .github/scripts/gtest/patch_cmake_lists.py vsgen1c1.c
```

**What It Does:**
1. Scans ALL includes from source, test, mock, and stub files
2. Searches project for each header file
3. Calculates correct relative paths
4. **Automatically updates CMakeLists.txt** with missing paths
5. Adds helpful comments showing which headers each path provides

**Expected Output:**
```
ℹ Starting GTF Include Path Update
ℹ Source File: vsgen1c1.c
✓ Found 20 unique header includes

ℹ Searching for header file paths in project...
  Searching for: Std_Types.h -> Found: app/pkg/.../common_ext
  Searching for: missing_header.h -> NOT FOUND

✓ Added 7 new include paths to CMakeLists.txt
  + app/pkg/.../common_ext (for: Std_Types.h, Rte_Type.h)
  ...

✓ GTF Include Path Update Complete!
```

**After running the script:**
1. **Rebuild the project** to see if errors are resolved:
```bash
cd [Module Path]\test\gtest
rm -rf bin/gcc-ctc
[Project Root].github\\scripts\\gtest\\run_module_gtest.bat [source_file].c
```

2. **If headers are STILL missing**, check script output for "NOT FOUND" headers → Proceed to Step 2️⃣

---

#### **Step 2️⃣: If Headers Still Missing - Search and Copy to Common_ext**

**Only perform this step if compilation still fails** with "No such file or directory" errors after Step 1.

**2a. Search for the missing header using Find-HeaderPath.ps1**:

```powershell
cd [Project Root]
.github\scripts\gtest\Find-HeaderPath.ps1 "[header_name].h"
```

**Examples**:
```powershell
.github\scripts\gtest\Find-HeaderPath.ps1 "Std_Types.h"
.github\scripts\gtest\Find-HeaderPath.ps1 "cdef_deprecated.h"
.github\scripts\gtest\Find-HeaderPath.ps1 "s3phuddef.h"
```

**2b. Copy found header to centralized common_ext location**:

Once the script shows you the header location, copy it to the shared folder:

```powershell
Copy-Item -Path "c:\Projects\arav_s3p\[source_path_from_search]\[header_name].h" `
          -Destination "c:\Projects\arav_s3p\pkg\em_s3p_hud\s3phudcommon\s3phuddef\test\gtest\common_ext\[header_name].h" `
          -Force
```

**Complete Example**:
```powershell
# 1. Search for cdef_deprecated.h
.github\scripts\gtest\Find-HeaderPath.ps1 "cdef_deprecated.h"
# Returns: pkg/em_swlmemcrydrv/test/gtest/prj/tfr/common/cdef_deprecated.h

# 2. Copy to common_ext
Copy-Item -Path "c:\Projects\arav_s3p\pkg\em_swlmemcrydrv\test\gtest\prj\tfr\common\cdef_deprecated.h" `
          -Destination "c:\Projects\arav_s3p\pkg\em_s3p_hud\s3phudcommon\s3phuddef\test\gtest\common_ext\cdef_deprecated.h" `
          -Force

# 3. Verify copy succeeded
Get-ChildItem "c:\Projects\arav_s3p\pkg\em_s3p_hud\s3phudcommon\s3phuddef\test\gtest\common_ext\cdef_deprecated.h" | Select-Object Name, Length
```

**2c. Rebuild to verify compilation succeeds**:
```bash
cd [Module Path]\test\gtest
rm -rf bin/gcc-ctc
[Project Root].github\\scripts\\gtest\\run_module_gtest.bat [source_file].c
```

---

#### **Benefits of common_ext Location**
- ✅ Shared across multiple modules (TouchQ, TouchSM, DesCtl, etc.)
- ✅ Single maintenance point for AUTOSAR and type definition headers
- ✅ Avoids code duplication

---

#### **Quick Reference: Common Header Locations**

| Header | Typical Location |
|--------|------------------|
| `Std_Types.h`, `Rte_Type.h`, `Platform_Types.h` | `app/pkg/.../common_ext/` |
| `s3phuddef.h` | `pkg/em_s3p_hud/s3phudcommon/s3phuddef/core/` |
| `cdef.h` | `pkg/em_fbm/test/gtest/prj/tfr/common/` |
| `cdef_ce.h` | `pkg/em_s3p_hud/communication/sbcomi2c/test/gtest/prj/tfr/common/` |
| `cdef_common.h` | `pkg/em_uartex/test/gtest/prj/tfr/common/` |
| `cdef_deprecated.h` | `pkg/em_swlmemcrydrv/test/gtest/prj/tfr/common/` |
| Module-specific (e.g., `vidcond1c1.h`, `desctl1c1.h`) | `pkg/em_s3p_hud/[module]/core/` |

---

### Issue 4: sample_test.cpp Missing
**Problem**: `Cannot find source file: sample_test.cpp`
**Solution**:
- Create empty placeholder: `test/gtest/tests/sample_test.cpp`
- Content: `// Empty sample test file\n// This file is required by CMakeLists.txt but not used`

### Issue 5: Mock Not Called / EXPECT_CALL Expectation Not Met
**Problem**: `EXPECT_CALL` expectation not met
**Solution**: 
- Verify function is actually called in source code
- Check mock setup is correct
- Ensure correct parameter matchers used (`_` for any value)
- Check if mock object is passed to the right scope

### Issue 6: Compilation Errors
**Problem**: Cannot find header files during build

**Solution**:

**🚀 FIRST ACTION: Run Automatic Include Path Updater**

Before manually searching for headers, **always run** the automatic script:

```bash
cd [Project Root]
python .github/scripts/gtest/patch_cmake_lists.py [source_file.c]
```

**Example:**
```bash
cd C:\Projects\s3p_arav
python .github/scripts/gtest/patch_cmake_lists.py vsgen1c1.c
```

This script will:
- Scan all includes from source, test, mock, and stub files
- Find headers automatically
- Update CMakeLists.txt with correct paths
- Report which headers couldn't be found

**After running the script, rebuild and check if errors are resolved.**

See **Step 6** in the main workflow above for detailed documentation on this script.

---

**If errors persist after running the script:**

1. **Check the script output** - it will list headers that couldn't be found
2. **Verify those headers exist** in your project or dependencies
3. **If headers are truly missing**, you may need to:
   - Copy them from external dependencies
   - Add them to stub files
   - Update module dependencies
4. **For manual header location and CMakeLists.txt updates**, see **Issue 3** above

**Other compilation checks**:
- Verify include paths in CMakeLists.txt
- Ensure mock files exist and are syntactically correct
- Check for type conflicts between cdef.h and stub files
- Verify no circular includes

### Issue 7: Tests Fail
**Problem**: Assertions fail
**Solution**:
- Review test logic
- Check expected vs actual values
- Verify mock returns correct values
- Ensure state is set up correctly in SetUp()
- Check if module state persists between tests (reset in TearDown)

### Issue 8: Coverage Gaps
**Problem**: Some lines still not covered after adding tests

**Solution** (**Always use `<filename>_clean.tmp`**):

1. **Open the clean file** and go to the uncovered line numbers from the coverage report
2. **Analyze the actual code**:
   ```bash
   # Example: Coverage report shows lines 245-248 uncovered
   notepad pkg/em_s3p_hud/[module]/core/[filename]_clean.tmp
   # Navigate to lines 245-248
   # See the actual condition and branches (macros expanded)
   ```
3. **Identify what's missing**:
   - Add test for specific conditional branch (see condition in clean file)
   - Test both TRUE and FALSE paths of if/while conditions (count paths in clean file)
   - Test error conditions (E_NOT_OK paths) - verify error handling in clean file
   - Test boundary values (0, max, max+1, min-1) - check bounds logic in clean file
   - Check for unreachable code or dead code (visible in clean file)
4. **Design targeted test** based on clean file analysis
5. **Re-run and verify** coverage improves

**Example**:
```cpp
// Coverage report: Line 245 not covered
// Check clean file line 245:
if (value > MAX_THRESHOLD) {  // <-- This TRUE branch not tested
    processOverflow();
}

// Solution: Add test for value > MAX_THRESHOLD
TEST_F(ModuleTestNormalFixture, Test_ProcessValue_Overflow) {
    uint8 value = MAX_THRESHOLD + 1;  // Force TRUE branch
    Module_ProcessValue(value);
    // Verify processOverflow() was called
}
```

**Key Point**: Don't guess what code needs coverage—**see it in the clean file**.

### Issue 9: Build Directory Cache
**Problem**: Changes not taking effect in build
**Solution**:
- Clean build directory: `rm -rf bin/gcc-ctc`
- Rebuild from scratch
- Ensure file edits are saved before running tests
- Check if old object files are being used

### Issue 10: Using SYN_ Macros in EXPECT_CALL Statements
**Problem**: 
```
error: invalid cast from type 'const testing::internal::AnythingMatcher' to type 'Adc_ValueGroupType*'
EXPECT_CALL(mock_ext, SYN_Adc_SetupResultBuffer(_)).WillOnce(Return(E_OK));
```
**Cause**: The `SYN_*` macro expands with hardcoded parameters, causing type casting issues when used with GoogleMock's `_` matcher.

**Solution**: Use the **underlying function name** in EXPECT_CALL instead of the macro:
```cpp
// ❌ WRONG: Using macro in EXPECT_CALL
#define SYN_Adc_SetupResultBuffer(pBuffer)  Adc_SetupResultBuffer(AdcConf_AdcGroup_AmSeS_TemperatureGroup_Cfg, (Adc_ValueGroupType*)(pBuffer))
EXPECT_CALL(mock_ext, SYN_Adc_SetupResultBuffer(_)).WillOnce(Return(E_OK));  // FAILS!

// ✅ CORRECT: Call underlying function directly
EXPECT_CALL(mock_ext, Adc_SetupResultBuffer(_, _)).WillOnce(Return(E_OK));
```

**Common patterns**:
```cpp
// Macros to underlying functions mapping:
SYN_Adc_GetGroupStatus()              → Adc_GetGroupStatus(_)
SYN_Adc_ReadGroup(buf)                → Adc_ReadGroup(_, _)
SYN_Adc_StartGroupConversion()        → Adc_StartGroupConversion(_)
SYN_Adc_SetupResultBuffer(buf)        → Adc_SetupResultBuffer(_, _)
SYN_DTC_u8SetDTCStatusPassed(id)      → DTC_u8SetDTCFailure(_, DEM_EVENT_STATUS_PASSED)
SYN_DTC_u8SetDTCStatusFailed(id)      → DTC_u8SetDTCFailure(_, DEM_EVENT_STATUS_FAILED)
```

**Note**: Ensure your mocks are declared with the underlying function signatures, not the macro names.

### Issue 12: Undefined Reference to Function During Linking
**Problem**: 
```
undefined reference to `TABLES_boLUTFrmtChkSign16Bits'
undefined reference to `NvM_ASR40_SetRamBlockStatus'
```
**Cause**: Mock wrapper functions are missing or not properly exported with `extern "C"` linkage.

**Solution**: Ensure all mocked functions have C wrapper implementations in mock .cpp file:
```cpp
// In mock_[module]_pf.cpp

// Make sure wrappers are in extern "C" block (if at file scope)
// OR ensure they're not inside namespace blocks

boolean TABLES_boLUTFrmtChkSign16Bits(const sint16* ps16Table, uint16 u16MaxFormat, uint8 u8ExpectedFormat)
{
    return mock_all_in_one->TABLES_boLUTFrmtChkSign16Bits(ps16Table, u16MaxFormat, u8ExpectedFormat);
}

// For ASR40 variants, add additional wrapper if needed:
Std_ReturnType NvM_ASR40_SetRamBlockStatus(NvM_BlockIdType BlockId, boolean Changed)
{
    return NvM_SetRamBlockStatus(BlockId, Changed);
}
```

### Issue 13: SetArgPointee Index After Changing from Macro to Function
**Problem**: Test fails or crashes after changing from macro-based EXPECT_CALL to function-based.

**Cause**: When switching from `SYN_Adc_ReadGroup(buf)` (1 param) to `Adc_ReadGroup(group, buf)` (2 params), the `SetArgPointee` index changes.

**Solution**: Update `SetArgPointee` index to match new parameter position:
```cpp
// ❌ WRONG: Old macro version (1 parameter)
EXPECT_CALL(mock_ext, SYN_Adc_ReadGroup(_))
    .WillOnce(DoAll(
        SetArgPointee<0>(1000),  // Parameter 0 was the buffer
        Return(E_OK)
    ));

// ✅ CORRECT: Underlying function (2 parameters)
EXPECT_CALL(mock_ext, Adc_ReadGroup(_, _))
    .WillOnce(DoAll(
        SetArgPointee<1>(1000),  // Now parameter 1 is the buffer (0 is group)
        Return(E_OK)
    ));
```

### Issue 14: Typos in Test Constant Names
**Problem**: 
```
error: 'AMBSTEMPSENSBORFAIL_QUALTIME' was not declared in this scope
```
**Cause**: Typo in constant name used in test.

**Solution**: Check the actual constant name in the source code and fix the typo:
```cpp
// ❌ WRONG: Typo in name
uint16 u16QualTime = AMBSTEMPSENSBORFAIL_QUALTIME;  // Missing 'OR'

// ✅ CORRECT:
uint16 u16QualTime = AMBSTEMPSENSORFAIL_QUALTIME;
```

### Issue 15: Copy-Item Command Fails When Copying Header
**Problem**: 
```
Copy-Item: Cannot find path '[path]\[header_name].h' because it does not exist.
```
**Cause**: The source file path provided is incorrect or file doesn't actually exist at that location.

**Solution**:

Refer to **Issue 3: Step 2️⃣ (2a)** and re-verify the header path returned by Find-HeaderPath.ps1:

```powershell
cd [Project Root]
.github\scripts\gtest\Find-HeaderPath.ps1 "[header_name].h"
```

Ensure the path returned is **exact and correct** before attempting the copy operation. If the file still cannot be found:
1. The header may not exist in this project at all
2. It may be located in an external dependency 
3. The project structure may have changed

---

## Quick Start Commands

### Navigate to Test Directory
```bash
cd [Project Root]\[Module Path]\test\gtest
```

**Example**:
```bash
cd C:\Projects\s3p_arav\pkg\em_s3p_hud\ambientsense\ambstemp\test\gtest
```

### Run Tests (Full Build)
```bash
[Project Root].github\\scripts\\gtest\\run_module_gtest.bat [source_file_name.c]
```

**Example**:
```bash
C:\Projects\s3p_arav.github\\scripts\\gtest\\run_module_gtest.bat ambstemp1c1.c
```

### Clean Build Directory
```bash
cd [Module Path]\test\gtest
rm -rf bin/gcc-ctc
```

### Find Missing Header Files

**See Issue 3** for comprehensive troubleshooting of missing header file errors.

The standard workflow is:
1. **First**: Run `.github/scripts/gtest/patch_cmake_lists.py` to automatically update CMakeLists.txt
2. **If still missing**: Use `.github/scripts/gtest/Find-HeaderPath.ps1` to locate and copy to common_ext

---

## Coverage Analysis Workflow

### 1. Run Tests and Generate Coverage
```bash
[Project Root].github\\scripts\\gtest\\run_module_gtest.bat [source_file_name.c]
```

### 2. Open Coverage Report
Navigate to and open in a web browser:
```
[Module Path]\test\gtest\bin\metrics\coverage\ctc\html\index.html
```

**Example**:
```
C:\Projects\arav_s3p\pkg\em_s3p_hud\ambsense\ambstemp\test\gtest\bin\metrics\coverage\ctc\html\index.html
```

### 3. Identify Gaps
- Look for red/yellow lines in `[Module name].c`
- Note line numbers and conditions not covered

### 4. Add Targeted Tests
For each uncovered line:
- Determine what condition would execute that line
- Create a test case that sets up that condition
- Verify the line is now covered

### 5. Verify 100% Coverage
Re-run and confirm all metrics at 100%

---

## Best Practices

1. **Clean Build When Needed**: After significant changes, clean the build directory
2. **Check Coverage After Each Test**: Run tests frequently to track coverage progress
3. **Fix Compilation Errors First**: Don't proceed with coverage until all tests compile
4. **Document Unreachable Code**: If code truly can't be tested, document why
5. **Use Common Headers**: Check common_ext folder before creating stub headers
6. **Incremental Testing**: Add a few tests, run, check coverage, repeat

---

## References

- Test Case Implementation: [gtest-testcase-gen](../gtest-testcase-gen/SKILL.md)
- Mock Creation: [gtest-mock-creation](../gtest-mock-creation/SKILL.md)
- Full Implementation Steps: [GTEST_IMPLEMENTATION_STEPS.md](GTEST_IMPLEMENTATION_STEPS.md)

---

---

## Quick Reference: Using Clean File for Debugging

### Generate Clean File
```bash
cd [Project Root]
python gen_standard_c.py [source_file.c] --execute --clean
```

### Clean File Location
```
[Module Path]/core/<filename>_clean.tmp
```

### When to Use Clean File

| Task | Use Clean File For | Example |
|------|-------------------|---------|
| **Compilation Errors** | Exact function signatures (macros expanded) | `error: too few arguments to function 'FuncName'` → Check clean file for actual signature |
| **Compilation Errors** | Exact function signatures (macros expanded) | `error: too few arguments to function 'FuncName'` → Check clean file for actual signature |
| **Test Failures** | Understanding exact code behavior | Test expects wrong value → Check clean file to see actual logic |
| **Coverage Gaps** | Identifying all branches and conditions | Line not covered → Check clean file to see what condition triggers it |
| **Mock Creation** | Accurate function parameter types | MOCK_METHOD signature → Get exact types from clean file |
| **Test Design** | Counting total branches for complete coverage | Need 100% coverage → Count all if/else/switch in clean file |
| **Debugging Logic** | Understanding macro expansions | `STATIC` function behavior → See `static` in clean file |

### Quick Workflow
```bash
# 1. Issue encountered (compilation error, test failure, coverage gap)
# 2. Open clean file
notepad [Module Path]/core/[filename]_clean.tmp

# 3. Search for function/line mentioned in error
# 4. Analyze actual code (macros expanded)
# 5. Design solution based on what you see
# 6. Implement fix
# 7. Re-test
```

### Remember
- ✅ Clean file = What the compiler actually compiles
- ✅ Original file = How the developer wrote it
- ✅ When in doubt, **check clean file first**

---

## Output Format

When troubleshooting or analyzing coverage, provide:
1. Current coverage metrics (%, line numbers)
2. Identified gaps and root causes
3. Proposed test cases to fill gaps
4. Build errors and resolutions
5. Final coverage results after fixes
