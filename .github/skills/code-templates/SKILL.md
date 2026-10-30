---
name: code-templates
description: C source code generation templates for automotive modules. Provides standardized `.h` and `.c` file templates with proper structure, headers, type definitions, and function signatures following automotive conventions.
applies-to: ["*.c", "*.h"]
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# Code Templates Skill

Provides standardized, reusable C source code templates for generating automotive module skeletons. Used by the Doxygen agent (Mode 3: Skeleton Generation) and other code generation workflows.

## Purpose

This skill centralizes all code generation templates and rules to:
- Eliminate duplication across different code generation tools
- Ensure consistency with automotive naming conventions
- Provide templates for `.h` (headers) and `.c` (implementation) files
- Support both core and adaptation layer code generation
- Enable reuse across agents and workflows

## Template Categories

1. **Header Files (.h)** — Public interfaces and type definitions
2. **Implementation Files (.c)** — Functions and data structures
3. **Type Definitions** — Structs and enumerations
4. **Function Signatures** — Public and private declarations
5. **Activity Diagram Mapping** — Logic flow to C code conversion

---

# Header File Templates

## Core Module Header (`[module]1c1.h`)

This is the **public interface header** for a module. Use this when generating core module headers.

```c
/*****************************************************************************
* Title        : [module]1c1.h
* Description  : Public interface header for [Module] module
* MS Revision  : [extracted from existing doc]
* 
* Created on   : [Current Date]
* Responsible  : [TODO: Add responsible person]
* Guidelines   : SMK 4.21
* Template name: SWMODxC1.H, Revision 1.9
*****************************************************************************/

#ifndef [MODULE]1C1_H
#define [MODULE]1C1_H

/*--- System Header Files ---*/
#include "Std_Types.h"
#include "Rte_[Module].h"
/* TODO: Add other required system includes */

/*--- External/Foreign Header Files ---*/
/* TODO: Add external module includes */

/*--- Own Header Files ---*/
#include "[module]1ci.h"
/* TODO: Add other own header files */

/*====================== PUBLIC TYPE DEFINITIONS =========================*/

/* [Extract from class diagram - typedef struct entries] */
typedef struct {
    uint8  u8Member1;
    uint16 u16Member2;
    boolean boFlag;
} [Module]_tstDataStruct;

/* [Extract from class diagram - typedef enum entries] */
typedef enum {
    [Module]_nenStateIdle = 0x00U,
    [Module]_nenStateActive = 0x01U,
    [Module]_nenStateError = 0x02U
} [Module]_tenStateType;

/*====================== PUBLIC FUNCTION DECLARATIONS ====================*/

/**
* @brief Initialize [Module] module
* @details Called during system startup to initialize module
* @return void
*/
extern void [Module]_vInit(void);

/**
* @brief Main cyclic function for [Module] module
* @details Called periodically by OS task
* @return void
*/
extern void [Module]_vMainFunction(void);

/* [Generate one extern declaration per public function from interface diagram] */

#endif /* [MODULE]1C1_H */
```

**Key Rules for Core Headers:**
- ✅ Include `Rte_[Module].h` for RTE integration
- ✅ Include `[module]1ci.h` for internal config
- ✅ Use `extern` for all public function declarations
- ✅ Place type definitions before function declarations
- ✅ Guard with `#ifndef [MODULE]1C1_H` include guard
- ✅ Add standard copyright and revision header

---

## Adaptation Module Header (`[module]1ca.h`)

This is the **adaptation/extension interface header**. Use this for platform-specific implementations.

```c
/*****************************************************************************
* Title        : [module]1ca.h
* Description  : Adaptation interface header for [Module] module
* MS Revision  : [extracted from existing doc]
* 
* Created on   : [Current Date]
* Responsible  : [TODO: Add responsible person]
* Guidelines   : SMK 4.21
*****************************************************************************/

#ifndef [MODULE]1CA_H
#define [MODULE]1CA_H

#include "Std_Types.h"
#include "[module]1c1.h"
/* TODO: Add adaptation-specific includes */

/*====================== ADAPTATION FUNCTION DECLARATIONS ================*/

/**
* @brief RTE operation wrapper for [function_name]
* @param [param1] [description]
* @return void
*/
extern void [Module]__vRteWrapper(uint8 u8Param);

/* [Generate one extern declaration per adaptation function] */

#endif /* [MODULE]1CA_H */
```

**Key Rules for Adaptation Headers:**
- ✅ Include core header `[module]1c1.h` for dependencies
- ✅ Prefix functions with `[Module]__` (double underscore) for adaptation code
- ✅ Use `extern` for public adaptation functions
- ✅ Focus on RTE wrappers and platform-specific code
- ✅ Guard with `#ifndef [MODULE]1CA_H` include guard

---

# Implementation File Templates

## Core Module Implementation (`[module]1c1.c`)

This is the **core implementation file** with all module logic.

```c
/*****************************************************************************
* Title        : [module]1c1.c
* Description  : Implementation of [Module] module
* MS Revision  : [extracted from existing doc]
* 
* Created on   : [Current Date]
* Responsible  : [TODO: Add responsible person]
* Guidelines   : SMK 4.21
* Template name: SWMODxC1.C, Revision 1.9
*****************************************************************************/

/*--- System Header Files ---*/
#include "Std_Types.h"
#include "Rte_[Module].h"
/* TODO: Add other required system includes */

/*--- Foreign Header Files ---*/
/* TODO: Add external module includes */

/*--- Own Header Files ---*/
#include "[module]1c1.h"
#include "[module]1ci.h"
#include "[module]1ca.h"

/*====================== STATIC DATA & VARIABLES ==========================*/

/* [Extract from class diagram - static data members] */
static boolean [Module]__boInitialized = FALSE;
static [Module]_tenStateType [Module]__enCurrentState = [Module]_nenStateIdle;
static [Module]_tstDataStruct [Module]__stRuntimeData = {0};

/*====================== STATIC FUNCTION PROTOTYPES ======================*/

/* [Extract from class diagram - private functions] */
static void [Module]__vStateMachine(void);
static void [Module]__vProcessData(void);

/*====================== PUBLIC FUNCTION IMPLEMENTATIONS =================*/

/**
* @brief Initialize [Module] module
* @details Initialization sequence:
*   1. Reset internal state
*   2. Initialize data structures
*   3. Set initial RTE values
* @return void
*/
void [Module]_vInit(void)
{
    if (TRUE == [Module]__boInitialized) {
        /* TODO: Report DET error - already initialized */
        return;
    }

    /* Initialize internal data structures */
    [Module]__stRuntimeData.u8Member1 = 0U;
    [Module]__stRuntimeData.u16Member2 = 0U;
    [Module]__stRuntimeData.boFlag = FALSE;

    /* Set initial state */
    [Module]__enCurrentState = [Module]_nenStateIdle;

    /* Write initial values to RTE */
    /* TODO: Add Rte_Write_* calls for initial outputs */

    [Module]__boInitialized = TRUE;
}

/**
* @brief Main cyclic function for [Module] module
* @details Cyclic execution sequence (from activity diagram):
*   - Read RTE inputs
*   - Execute state machine
*   - Process data
*   - Write RTE outputs
* @return void
*/
void [Module]_vMainFunction(void)
{
    if (FALSE == [Module]__boInitialized) {
        return;  /* Module not initialized */
    }

    /* Read RTE inputs */
    /* TODO: Add Rte_Read_* calls for input ports */

    /* Execute state machine */
    [Module]__vStateMachine();

    /* Process data */
    [Module]__vProcessData();

    /* Write RTE outputs */
    /* TODO: Add Rte_Write_* calls for output ports */
}

/*====================== PRIVATE FUNCTION IMPLEMENTATIONS ================*/

/**
* @brief Internal state machine logic
* @details State transitions from activity diagram
* @return void
*/
static void [Module]__vStateMachine(void)
{
    switch ([Module]__enCurrentState) {
        case [Module]_nenStateIdle:
            /* TODO: Add state idle logic from activity diagram */
            break;

        case [Module]_nenStateActive:
            /* TODO: Add state active logic from activity diagram */
            break;

        case [Module]_nenStateError:
            /* TODO: Add error handling logic from activity diagram */
            break;

        default:
            /* TODO: Add error handling for unexpected state */
            break;
    }
}

/**
* @brief Process module data
* @details Data processing sequence from activity diagram
* @return void
*/
static void [Module]__vProcessData(void)
{
    /* TODO: Add data processing logic from activity diagram */
}
```

**Key Rules for Core Implementation:**
- ✅ Include own headers: `[module]1c1.h`, `[module]1ci.h`, `[module]1ca.h`
- ✅ Declare static data at module level with initialization
- ✅ Declare static (private) function prototypes before implementations
- ✅ Prefix private functions with `__` (double underscore)
- ✅ Add comprehensive function documentation comments
- ✅ Initialize flags/states with default values
- ✅ Mark incomplete sections with `/* TODO: ... */` comments
- ✅ Follow automotive naming conventions for variables

---

## Adaptation Module Implementation (`[module]1ca.c`)

This is the **adaptation/extension implementation file** with platform-specific wrappers.

```c
/*****************************************************************************
* Title        : [module]1ca.c
* Description  : Adaptation implementation for [Module] module
* MS Revision  : [extracted from existing doc]
* 
* Created on   : [Current Date]
* Responsible  : [TODO: Add responsible person]
* Guidelines   : SMK 4.21
*****************************************************************************/

#include "[module]1c1.h"
#include "[module]1ci.h"
#include "[module]1ca.h"
/* TODO: Add adaptation-specific includes */

/*====================== ADAPTATION FUNCTION IMPLEMENTATIONS =============*/

/**
* @brief RTE wrapper for adaptation-specific operations
* @param u8Param Parameter from caller
* @return void
*/
void [Module]__vRteWrapper(uint8 u8Param)
{
    /* TODO: Implement RTE write/read wrapper logic */
    (void)Rte_Write_PP_[Module]_[Output]((Std_ReturnType)u8Param);
}

/* [Generate one implementation per adaptation function] */
```

**Key Rules for Adaptation Implementation:**
- ✅ Include core header `[module]1c1.h` for dependencies
- ✅ Include adaptation headers `[module]1ci.h` and `[module]1ca.h`
- ✅ Use `void` cast for unused return values: `(void)RteCall(...)`
- ✅ Prefix functions with module name and double underscore
- ✅ Document RTE wrapper functions thoroughly
- ✅ Keep implementations focused on RTE integration

---

# Type Definition Templates

## Struct Definition Pattern

From Class Diagram:
```
class Module_tstRuntimeData {
    +u8Member1:uint8
    +u16Member2:uint16
    +boFlag:boolean
    +enState:Module_tenStateType
}
```

Generated Header:
```c
typedef struct {
    uint8               u8Member1;
    uint16              u16Member2;
    boolean             boFlag;
    Module_tenStateType enState;
} Module_tstRuntimeData;
```

**Rules for Struct Generation:**
- ✅ Use automotive type prefixes: `u8`, `u16`, `u32`, `bo`, `en`, `st`
- ✅ Use proper type names: `uint8`, `uint16`, `uint32`, `boolean`
- ✅ Name structs with pattern: `[Module]_tst[StructName]`
- ✅ Align member declarations for readability
- ✅ End with semicolon after closing brace
- ✅ Place struct definitions in `.h` file (public header)

---

## Enumeration Definition Pattern

From Class Diagram:
```
enum Module_tenStateType {
    Module_nenIdle
    Module_nenActive
    Module_nenError
}
```

Generated Header:
```c
typedef enum {
    Module_nenIdle   = 0x00U,
    Module_nenActive = 0x01U,
    Module_nenError  = 0x02U
} Module_tenStateType;
```

**Rules for Enum Generation:**
- ✅ Use automotive naming: `[Module]_ten[EnumName]` for enum type
- ✅ Use hex values with `U` suffix: `0x00U`, `0x01U`, etc.
- ✅ Prefix enum values: `[Module]_nen[EnumValue]`
- ✅ Sequentially assign hex values (0x00U, 0x01U, 0x02U, etc.)
- ✅ No `+` or `-` visibility prefixes in enum declarations
- ✅ Align value assignments for readability
- ✅ End with semicolon after closing brace

---

# Function Signature Templates

## Public Function Declarations

From Interface Diagram:
```
interface "module1c1.h" as iface {
    Module_vInit() : void
    Module_vMainFunction() : void
    Module_u32GetStatus(uint8 u8Channel) : uint32
    Module_vSetConfig(const Module_tstConfig* pstConfig) : void
}
```

Generated Header Declarations:
```c
extern void Module_vInit(void);
extern void Module_vMainFunction(void);
extern uint32 Module_u32GetStatus(uint8 u8Channel);
extern void Module_vSetConfig(const Module_tstConfig* pstConfig);
```

**Rules for Function Signatures:**
- ✅ Extract return type from `: returnType` in diagram
- ✅ Extract parameter list from parentheses `(param1, param2, ...)`
- ✅ Use `extern` for public functions in headers
- ✅ Use `static` for private functions in `.c` files
- ✅ Match automotive naming convention:
  - Return type prefix: `v` (void), `u8`, `u16`, `u32`, `bo`, `en`
  - Function verb: `Init`, `MainFunction`, `SetConfig`, etc.
- ✅ Use proper type names: `uint8`, `uint16`, `uint32`, `boolean`, custom types
- ✅ Add descriptive parameter names, not just types
- ✅ Include `void` if no parameters: `Module_vInit(void);`

---

# Activity Diagram to Implementation Mapping

This section explains how to convert activity diagrams into actual C code.

## Mapping Rules

| Activity Diagram Element | C Code Equivalent |
|--------------------------|-------------------|
| `start` | Function entry point |
| `end` | Function return/exit |
| `:Action;` | Regular statement or function call |
| `if (condition?)` | `if (condition) {` |
| `then (yes)` | Code inside if block |
| `else (no)` | `else {` code block `}` |
| `endif` | `}` (closing if block) |
| `switch (var?)` | `switch (var) {` |
| `case (value)` | `case value:` |
| `endswitch` | `}` (closing switch block) |
| `:Rte_Call_Port(param)\|` | `Rte_Call_Port(param);` or `(void)Rte_Call_Port(param);` |
| `note right: comment` | `/* comment */` |
| Loops | `while (condition)` or `for (...)`  |

## Example Mapping

### Activity Diagram:
```
start
  :Read input data;
  
  if (Validation OK?) then (yes)
    :Process data;
    :Update state;
  else (no)
    :Report error;
    :Log to DET;
  endif
  
  :Write output;
end
```

### Generated C Implementation:
```c
static void Module__vProcessData(void)
{
    uint32 u32InputData;
    
    /* Read input data */
    Rte_Read_RP_Module_InputData(&u32InputData);
    
    /* Validate input */
    if (u32InputData >= MIN_VALID_VALUE && u32InputData <= MAX_VALID_VALUE) {
        /* Process data */
        Module__stRuntimeData.u32ProcessedValue = u32InputData * SCALE_FACTOR;
        
        /* Update state */
        Module__enCurrentState = Module_nenStateActive;
    } else {
        /* Report error */
        Det_ReportError(MODULE_ID, INSTANCE_ID, FUNC_ID, MODULE_E_INVALID_DATA);
        
        /* Log to DET (if available) */
        /* TODO: Add DET logging if configured */
    }
    
    /* Write output */
    Rte_Write_PP_Module_OutputStatus(Module__enCurrentState);
}
```

---

# Code Generation Patterns

## Pattern 1: Initialization Function

Use this pattern for module initialization functions.

```c
void [Module]_vInit(void)
{
    if (TRUE == [Module]__boInitialized) {
        /* Report error - already initialized */
        return;
    }

    /* Initialize data structures */
    /* ... set default values ... */
    
    /* Set initial state */
    [Module]__enCurrentState = [Module]_nenStateIdle;
    
    /* Initialize RTE outputs */
    /* TODO: Add Rte_Write_* calls */
    
    [Module]__boInitialized = TRUE;
}
```

**Key Points:**
- ✅ Guard against multiple initialization
- ✅ Reset all state variables and flags
- ✅ Set initial values for outputs
- ✅ Set `boInitialized` flag last

---

## Pattern 2: Main Cyclic Function

Use this pattern for cyclic (periodic) task functions.

```c
void [Module]_vMainFunction(void)
{
    if (FALSE == [Module]__boInitialized) {
        return;  /* Module not initialized */
    }

    /* Read RTE inputs */
    /* TODO: Add Rte_Read_* calls */

    /* Execute state machine */
    [Module]__vStateMachine();

    /* Process data */
    [Module]__vProcessData();

    /* Write RTE outputs */
    /* TODO: Add Rte_Write_* calls */
}
```

**Key Points:**
- ✅ Check initialization before proceeding
- ✅ Read inputs first
- ✅ Execute core logic (state machine, processing)
- ✅ Write outputs last
- ✅ Keep function clean and modular

---

## Pattern 3: State Machine Function

Use this pattern for state-based logic.

```c
static void [Module]__vStateMachine(void)
{
    switch ([Module]__enCurrentState) {
        case [Module]_nenStateIdle:
            /* Idle state logic */
            if (some_condition) {
                /* Transition to next state */
                [Module]__enCurrentState = [Module]_nenStateActive;
            }
            break;

        case [Module]_nenStateActive:
            /* Active state logic */
            if (completion_condition) {
                [Module]__enCurrentState = [Module]_nenStateIdle;
            }
            break;

        case [Module]_nenStateError:
            /* Error recovery logic */
            /* Attempt recovery or remain in error state */
            break;

        default:
            /* Unexpected state – log error */
            [Module]__enCurrentState = [Module]_nenStateError;
            break;
    }
}
```

**Key Points:**
- ✅ Use switch/case for clear state transitions
- ✅ Check conditions for state transitions
- ✅ Include default case for error handling
- ✅ Add comments for each state
- ✅ Use `break;` to exit each case

---

# Naming Conventions Reference

## Variable Prefixes

| Prefix | Type | Example |
|--------|------|---------|
| `u8` | uint8 | `u8Counter`, `u8Status` |
| `u16` | uint16 | `u16Timer`, `u16Voltage` |
| `u32` | uint32 | `u32Data`, `u32Timestamp` |
| `bo` | boolean | `boInitialized`, `boFlag` |
| `en` | enum | `enCurrentState`, `enPowerMode` |
| `st` | struct | `stRuntimeData`, `stConfiguration` |
| `au8` | uint8 array | `au8Buffer`, `au8Data` |
| `au16` | uint16 array | `au16LookupTable` |
| `f32` | float32 | `f32Voltage` |
| `f64` | float64 | `f64Temperature` |

## Struct/Enum Naming

| Category | Pattern | Example |
|----------|---------|---------|
| Struct types | `[Module]_tst[StructName]` | `PowMon_tstRuntimeData` |
| Enum types | `[Module]_ten[EnumName]` | `PowMon_tenPowerRange` |
| Enum values | `[Module]_nen[EnumValue]` | `PowMon_nenIdle` |
| Function names | `[Module]_[ReturnType][VerbName]` | `Module_vInit`, `Module_u32GetValue` |

## Function Naming

| Category | Pattern | Example |
|----------|---------|---------|
| Public void function | `[Module]_v[FunctionName]` | `Module_vInit` |
| Public return function | `[Module]_[Type][FunctionName]` | `Module_u16GetVoltage` |
| Private/static function | `[Module]__v[FunctionName]` | `Module__vStateMachine` |
| RTE wrapper | `[Module]__v[RteName]` | `Module__vUvIndication` |

---

# Best Practices

1. **Always include copyright header** with Title, Description, MS Revision, Created date, Responsible person, and Guidelines reference

2. **Use TODO markers** for incomplete sections to guide developers: `/* TODO: Implement ... */`

3. **Group code logically** — separations with comments:
   - System Header Files
   - Foreign Header Files (external modules)
   - Own Header Files
   - Static Data & Variables
   - Static Function Prototypes
   - Public Function Implementations
   - Private Function Implementations

4. **Document all functions** with:
   - `@brief` — One-line summary
   - `@details` — Detailed description and sequence
   - `@param` — Parameter descriptions (if any)
   - `@return` — Return value description

5. **Initialize all static variables** with appropriate default values

6. **Use `(void)` cast** for RTE calls when return value is not used: `(void)Rte_Write_PP_(...)`

7. **Follow automotive style** — 4-space indentation, no tabs, consistent formatting

---

# Usage in Code Generation Tools

When using this skill in code generation workflows (e.g., Doxygen Skeleton Generation Mode):

1. **For headers:** Use Core Header or Adaptation Header template as base
2. **For implementations:** Use Core Implementation or Adaptation Implementation template
3. **For types:** Apply Struct/Enum Definition patterns
4. **For functions:** Apply Function Signature templates and appropriate Pattern (Initialization, Cyclic, State Machine, etc.)
5. **For logic:** Use Activity Diagram to Implementation Mapping rules to convert diagrams to code

---

# Related Skills

- **plantuml-diagrams** — Generate activity diagrams that feed into code implementation
- **mts-traceability** — Link generated code to requirements and tests
