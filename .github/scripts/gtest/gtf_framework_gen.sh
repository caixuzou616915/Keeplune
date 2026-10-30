#!/bin/bash

################################################################################
# GTF (Google Test Framework) Unified Setup and Execution Script
################################################################################
#
# Author: Zhao Jianbo
# Supported by: UX SW AI Community
#
# PURPOSE:
#   This unified script handles both automatic and manual GTF test harness
#   generation for automotive embedded C modules. It combines full automation
#   with GTF installation and interactive GUI modes in a single tool.
#
# WHAT IT DOES:
#   AUTO MODE (default):
#     1. Configures CMB environment via econ_config.sh
#     2. Installs GTF Framework via Conan (if not already installed)
#     3. Activates GTF Python virtual environment
#     4. Launches run_gtest_gui.sh for automatic test harness generation
#
#   MANUAL MODE:
#     1. Configures CMB environment via econ_config.sh
#     2. Launches python run.py gtf --gui for interactive GTF GUI
#
# USAGE:
#   ./gtf_framework_gen.sh <module_path> [variant] [mode]
#
# PARAMETERS:
#   module_path (MANDATORY): Absolute or relative path to the module directory
#                           containing the C source files to be tested.
#                           Can also accept .c/.h files (uses parent directory)
#                           Examples:
#                           - C:/Projects/s3p_arav/pkg/em_s3p_hud/videoctl/vsgen
#                           - pkg/em_s3p_hud/videoctl/vsgen
#                           - pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1.c
#
#   variant (OPTIONAL):     Build variant name (default: "pf")
#                           Common variants: pf, db, flu
#                           The variant determines build configuration and
#                           creates a corresponding CMake project folder.
#
#   mode (OPTIONAL):        Generation mode (default: "auto")
#                           - auto   : Automatic generation with GTF installation
#                           - manual : Interactive GUI mode (requires user input)
#
# EXAMPLES:
#   # Auto mode with default variant (pf)
#   ./gtf_framework_gen.sh C:/Projects/s3p_arav/pkg/em_s3p_hud/videoctl/vsgen
#
#   # Auto mode with custom variant
#   ./gtf_framework_gen.sh pkg/em_s3p_hud/videoctl/vsgen db
#
#   # Manual (interactive) mode
#   ./gtf_framework_gen.sh pkg/em_s3p_hud/videoctl/vsgen pf manual
#
#   # Using file path (auto-detects directory)
#   ./gtf_framework_gen.sh pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1.c pf auto
#
# OUTPUT:
#   If successful, creates the following test harness structure:
#   <module_path>/test/gtest/
#   ├── CMakeLists.txt                       # Main CMake configuration
#   ├── unittest_configs.cmake               # Coverage settings
#   ├── prj/
#   │   └── unittest_<module>_<variant>/    # Variant-specific project folder (e.g., unittest_diag_pf)
#   │       └── CMakeLists.txt
#   ├── tests/                               # Test case files location
#   ├── prj/tfr/
#   │   ├── mocks/                           # Mock files for dependencies
#   │   └── stub/                            # Stub header files
#   └── adapt/
#       ├── GTFconfig.xml                    # GTF configuration
#       └── conanfile.txt                    # GTF version specification
#
# PREREQUISITES:
#   - CMB environment configured (.econ folder with econ_config.sh)
#   - Conan package manager installed
#   - Git installed (version >= 2.31.1)
#   - Python 3.9.x installed
#   - Bash shell available
#   - PySide2 for GTF GUI: pip install PySide2
#
# ENVIRONMENT:
#   - Project Root: C:/Projects/s3p_arav
#   - CMB Config: econ_config.sh in project root
#   - GTF Installation: gtf_bin/ folder in project root (auto mode)
#   - GTF Version: 3.9.1 (conti_gen_dev1/testing)
#
# NOTES FOR AI AGENTS:
#   - This script is designed for Phase 0 (Test Infrastructure Setup) of the
#     GTF workflow as described in the GTest mode instructions
#   - AUTO MODE is recommended for first-time setup and automated workflows
#   - MANUAL MODE is useful when customization or troubleshooting is needed
#   - After running this script, verify test infrastructure exists:
#     * <module_path>/test/gtest/CMakeLists.txt
#     * <module_path>/test/gtest/unittest_configs.cmake
#     * <module_path>/test/gtest/prj/unittest_<module>_<variant>/
#   - If the project already exists, GTF will report "project already exists"
#   - Use this script BEFORE Phase A (Mock Generation) to ensure test harness
#     structure is properly created
#
# TROUBLESHOOTING:
#   - "econ_config.sh not found": Run from project root directory
#   - "Failed to install GTF Framework": Check Conan credentials and network
#   - "ModuleNotFoundError: PySide2": Install via 'pip install PySide2'
#   - "project already exists": Test harness already created, safe to continue
#   - Script hangs in manual mode: GTF GUI is waiting for user interaction
#   - Invalid mode error: Mode must be "auto" or "manual"
#
# EXIT CODES:
#   0  - Success (test harness created or already exists)
#   1  - Error (check output for specific error message)
#
################################################################################

# Ensure we're running in bash
bash --version > /dev/null 2>&1

################################################################################
# PARAMETER PARSING AND VALIDATION
################################################################################

# Check if module path is provided
if [ -z "$1" ]; then
    echo "ERROR: Module path not provided"
    echo "Usage: $0 <module_path> [variant] [mode]"
    echo ""
    echo "Parameters:"
    echo "  module_path : Path to the module (relative or absolute)"
    echo "  variant     : Variant suffix (default: pf)"
    echo "  mode        : auto (default) or manual"
    echo ""
    echo "Examples:"
    echo "  $0 pkg/em_s3p_hud/videoctl/vsgen"
    echo "  $0 pkg/em_s3p_hud/videoctl/vsgen db"
    echo "  $0 pkg/em_s3p_hud/videoctl/vsgen pf manual"
    exit 1
fi

INPUT_PATH="$1"
VARIANT="${2:-pf}"
MODE="${3:-auto}"

# Display defaults if not provided
if [ -z "$2" ]; then
    echo "Using default variant: pf"
fi
if [ -z "$3" ]; then
    echo "Using default mode: auto"
fi

# Validate mode
if [ "$MODE" != "auto" ] && [ "$MODE" != "manual" ]; then
    echo "ERROR: Invalid mode \"$MODE\". Must be \"auto\" or \"manual\""
    exit 1
fi

################################################################################
# PATH PROCESSING
################################################################################

# Get project root directory (navigate up from .github/scripts/gtest/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Script is in .github/scripts/gtest/, project root is 3 levels up: ../../..
PATH_PROJECT_REPO="$( cd "$SCRIPT_DIR/../../.." && pwd )"

# Remove quotes if present
INPUT_PATH="${INPUT_PATH//\"/}"

# Check if input is a file (has .c or .h extension) - if so, get directory
if [[ "$INPUT_PATH" == *.c ]] || [[ "$INPUT_PATH" == *.h ]]; then
    INPUT_PATH="$(dirname "$INPUT_PATH")"
    echo "Detected file path, using directory: $INPUT_PATH"
fi

# Remove trailing slash if present
INPUT_PATH="${INPUT_PATH%/}"
INPUT_PATH="${INPUT_PATH%\\}"

# Check if path ends with /core or \core - if so, use parent directory (module level)
if [[ "$INPUT_PATH" == */core ]] || [[ "$INPUT_PATH" == *\\core ]]; then
    INPUT_PATH="${INPUT_PATH%/core}"
    INPUT_PATH="${INPUT_PATH%\\core}"
    echo "Detected 'core' subfolder, using module path: $INPUT_PATH"
fi

# Check if it's an absolute path (contains project root path)
if [[ "$INPUT_PATH" == *"$PATH_PROJECT_REPO"* ]]; then
    # It's an absolute path within project - make it relative
    MODULE_PATH="${INPUT_PATH#$PATH_PROJECT_REPO/}"
    MODULE_PATH="${INPUT_PATH#$PATH_PROJECT_REPO\\}"
    echo "Converting absolute path to relative: $MODULE_PATH"
else
    # It's already a relative path
    MODULE_PATH="$INPUT_PATH"
fi

# Normalize path separators to forward slashes
MODULE_PATH_BASH="${MODULE_PATH//\\//}"

################################################################################
# EXTRACT MODULE NAME FROM CMAKELISTS.TXT
################################################################################

# Get the CMakeLists.txt path and extract module_name
CMAKELISTS_PATH="$PATH_PROJECT_REPO/$MODULE_PATH_BASH/test/gtest/CMakeLists.txt"

if [ -f "$CMAKELISTS_PATH" ]; then
    # Extract module_name from CMakeLists.txt (line like: set(module_name diag))
    MODULE_NAME=$(grep -m1 "^set(module_name" "$CMAKELISTS_PATH" | sed 's/.*module_name[[:space:]]*\([^)]*\).*/\1/')
    if [ -z "$MODULE_NAME" ]; then
        # Fallback: use last part of path as module name
        MODULE_NAME="${MODULE_PATH##*/}"
        echo "Warning: Could not extract module_name from CMakeLists.txt, using: $MODULE_NAME"
    fi
else
    # Fallback: use last part of path as module name
    MODULE_NAME="${MODULE_PATH##*/}"
    echo "Warning: CMakeLists.txt not found, using module path suffix: $MODULE_NAME"
fi

################################################################################
# MODE SELECTION AND EXECUTION
################################################################################

echo "================================================"
echo "GTF Test Harness Generation"
echo "================================================"
echo "Module Path: $MODULE_PATH"
echo "Module Name: $MODULE_NAME"
echo "Variant: $VARIANT"
echo "Mode: $MODE"
echo "Expected Test Harness: $MODULE_PATH/test/gtest/"
echo "Expected Variant Project: $MODULE_PATH/test/gtest/prj/unittest_${MODULE_NAME}_${VARIANT}/"
echo "================================================"

# Change to project directory
cd "$PATH_PROJECT_REPO" || exit 1

# Prepare full package root path for GTF (used by both modes)
PACKAGE_ROOT_BASH="$PATH_PROJECT_REPO/$MODULE_PATH_BASH"

if [ "$MODE" = "manual" ]; then
    ############################################################################
    # MANUAL MODE: Interactive GUI
    ############################################################################
    echo ""
    echo "=== MANUAL MODE: Interactive GTF GUI ==="
    echo ""
    
    echo "Step 1: Sourcing econ_config.sh..."
    if [ ! -f "econ_config.sh" ]; then
        echo "Error: econ_config.sh not found in current directory!"
        exit 1
    fi
    
    # Source econ_config without arguments
    set --
    . ./econ_config.sh || true
    set -- "$INPUT_PATH" "$VARIANT" "$MODE"
    
    echo "✓ econ_config.sh sourced"
    echo ""
    
    echo "Step 2: Launching GTF GUI (Interactive Mode)..."
    echo "Command: python run.py gtf --opt=\"--gui -a=\\\"-p $PACKAGE_ROOT_BASH -v $VARIANT\\\"\""
    echo ""
    
    python run.py gtf --opt="--gui -a=\"-p $PACKAGE_ROOT_BASH -v $VARIANT\""
    
    echo ""
    echo "================================================"
    echo "GTF GUI (Manual Mode) execution completed"
    echo "================================================"
    
else
    ############################################################################
    # AUTO MODE: Automatic generation with GTF installation
    ############################################################################
    echo ""
    echo "=== AUTO MODE: Automatic GTF Setup and Generation ==="
    echo ""
    
    # Save script arguments before sourcing econ_config.sh
    SAVED_MODULE_PATH="$MODULE_PATH"
    SAVED_VARIANT="$VARIANT"
    SAVED_PACKAGE_ROOT="$PACKAGE_ROOT_BASH"
    
    # Step 1: Source CMB Environment Configuration
    echo "Step 1: Sourcing econ_config.sh..."
    if [ ! -f "econ_config.sh" ]; then
        echo "Error: econ_config.sh not found in current directory!"
        exit 1
    fi
    
    # Source econ_config.sh without arguments by clearing positional parameters
    set --
    . ./econ_config.sh || true
    
    # Restore script arguments
    set -- "$SAVED_MODULE_PATH" "$SAVED_VARIANT"
    
    echo "✓ econ_config.sh sourced (continuing...)"
    echo ""
    
    # Step 2: GTF Framework Installation
    echo "Step 2: Checking GTF Framework installation..."
    if [ ! -d "gtf_bin" ]; then
        echo "gtf_bin folder not found. Installing GTF Framework..."
        conan install GT_Framework/3.9.1@conti_gen_dev1/testing -g=virtualenv -if gtf_bin
        if [ $? -ne 0 ]; then
            echo "Error: Failed to install GTF Framework"
            exit 1
        fi
        echo "✓ GTF Framework installed successfully"
    else
        echo "✓ gtf_bin folder already exists, skipping installation"
    fi
    echo ""
    
    # Step 3: Navigate to GTF Installation Directory
    echo "Step 3: Changing to gtf_bin directory..."
    cd gtf_bin
    if [ $? -ne 0 ]; then
        echo "Error: Failed to change to gtf_bin directory"
        exit 1
    fi
    echo "✓ Changed to gtf_bin directory"
    echo ""
    
    # Step 4: Activate GTF Environment and Launch GTF GUI
    echo "Step 4: Activating GTF environment and running GTF GUI..."
    echo "Command: . ./activate.sh && . run_gtest_gui.sh -p \"$SAVED_PACKAGE_ROOT\" -v \"$SAVED_VARIANT\""
    echo ""
    
    # Clear positional parameters before sourcing to prevent argument conflicts
    set --
    . ./activate.sh && . run_gtest_gui.sh -p "$SAVED_PACKAGE_ROOT" -v "$SAVED_VARIANT"
    set -- "$SAVED_MODULE_PATH" "$SAVED_VARIANT"
    
    echo ""
    echo "================================================"
    echo "GTF GUI (Auto Mode) execution completed"
    echo "================================================"
fi

# Return to project directory
cd "$PATH_PROJECT_REPO" || exit 1

################################################################################
# COMPLETION
################################################################################
echo ""
echo "NEXT STEPS FOR AI AGENTS:"
echo "1. Validate test infrastructure was created successfully:"
echo "   - Check: $MODULE_PATH/test/gtest/CMakeLists.txt"
echo "   - Check: $MODULE_PATH/test/gtest/unittest_configs.cmake"
echo "   - Check: $MODULE_PATH/test/gtest/prj/unittest_${MODULE_NAME}_${VARIANT}/"
echo "2. If all files exist, proceed to Phase A (Mock Generation)"
echo "3. If validation fails, check GTF GUI output above for errors"
echo ""
echo "To manually verify, run:"
echo "  ls -la $MODULE_PATH/test/gtest/"
echo ""
