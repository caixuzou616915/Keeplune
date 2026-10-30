@echo off
REM ============================================================================
REM GTF Framework Test Generation - Windows Wrapper
REM ============================================================================
REM
REM Author: Zhao Jianbo
REM Supported by: UX SW AI Community
REM
REM Purpose:
REM   Windows batch wrapper for gtf_framework_gen.sh unified script.
REM   Provides convenient CMD/PowerShell access to GTF test harness generation.
REM
REM Syntax:
REM   gtf_framework_gen.bat <module_path> [variant] [mode]
REM
REM Parameters:
REM   module_path : (Required) Path to module directory
REM                 - Can be absolute or relative
REM                 - Can point to .c/.h file (extracts directory)
REM                 - Can point to /core subfolder (uses parent)
REM                 Examples:
REM                   pkg\em_s3p_hud\videoctl\vsgen
REM                   pkg\em_s3p_hud\videoctl\vsgen\core
REM                   C:\Projects\s3p_arav\pkg\em_s3p_hud\videoctl\vsgen
REM
REM   variant     : (Optional, Default: pf) Build variant suffix
REM                 Common values: pf, db, flu, rel
REM
REM   mode        : (Optional, Default: auto) Execution mode
REM                 - auto   : Full automation with GTF installation
REM                 - manual : Interactive GUI for customization
REM
REM Examples:
REM   REM Auto mode (default) - Full automation
REM   gtf_framework_gen.bat "pkg\em_s3p_hud\videoctl\vsgen"
REM   gtf_framework_gen.bat "pkg\em_s3p_hud\videoctl\vsgen" pf auto
REM
REM   REM Manual mode - Interactive GUI
REM   gtf_framework_gen.bat "pkg\em_s3p_hud\videoctl\vsgen" pf manual
REM
REM   REM Custom variant with auto mode
REM   gtf_framework_gen.bat "pkg\em_s3p_hud\videoctl\vsgen" db auto
REM
REM Prerequisites:
REM   - Bash accessible from Windows PATH (Git Bash, WSL, MSYS2)
REM   - CMB environment configured (.econ folder with econ_config.sh)
REM   - All prerequisites from gtf_framework_gen.sh
REM
REM Notes:
REM   - This wrapper calls gtf_framework_gen.sh via bash
REM   - For detailed documentation, see gtf_framework_gen_USAGE.md
REM   - For AI agent usage, see .github/agents/GTest.agent.md
REM
REM ============================================================================

SETLOCAL EnableDelayedExpansion

REM Check if module path is provided
if "%1"=="" (
    echo ================================================
    echo GTF Framework Test Generation - Windows Wrapper
    echo ================================================
    echo.
    echo ERROR: Module path not provided
    echo.
    echo Usage: %~nx0 ^<module_path^> [variant] [mode]
    echo.
    echo Parameters:
    echo   module_path : ^(Required^) Path to module directory
    echo                 - Can be absolute or relative
    echo                 - Can point to .c/.h file or /core subfolder
    echo.
    echo   variant     : ^(Optional, Default: pf^) Build variant
    echo                 Common: pf, db, flu, rel
    echo.
    echo   mode        : ^(Optional, Default: auto^) Execution mode
    echo                 - auto   : Full automation with GTF installation
    echo                 - manual : Interactive GUI
    echo.
    echo Examples:
    echo   REM Auto mode ^(default^) - Recommended
    echo   %~nx0 "pkg\em_s3p_hud\videoctl\vsgen"
    echo   %~nx0 "pkg\em_s3p_hud\videoctl\vsgen" pf auto
    echo.
    echo   REM Manual mode - Interactive GUI
    echo   %~nx0 "pkg\em_s3p_hud\videoctl\vsgen" pf manual
    echo.
    echo   REM Custom variant
    echo   %~nx0 "pkg\em_s3p_hud\videoctl\vsgen" db auto
    echo.
    echo For detailed usage, see: gtf_framework_gen_USAGE.md
    echo ================================================
    exit /b 1
)

SET MODULE_PATH=%~1
SET VARIANT=%2
SET MODE=%3

REM Set defaults
if "%VARIANT%"=="" SET VARIANT=pf
if "%MODE%"=="" SET MODE=auto

echo ================================================
echo GTF Test Harness Generation (Windows)
echo ================================================
echo Module Path: %MODULE_PATH%
echo Variant: %VARIANT%
echo Mode: %MODE%
echo ================================================
echo.
echo Calling gtf_framework_gen.sh via bash...
echo.

REM Run the bash script
bash -c "./gtf_framework_gen.sh '%MODULE_PATH%' '%VARIANT%' '%MODE%'"

if %ERRORLEVEL% neq 0 (
    echo.
    echo ================================================
    echo ERROR: Script execution failed
    echo ================================================
    echo Exit Code: %ERRORLEVEL%
    echo.
    echo Possible causes:
    echo   - Bash not found in PATH
    echo   - gtf_framework_gen.sh not found
    echo   - CMB environment not configured
    echo   - GTF installation failed ^(auto mode^)
    echo   - Test harness generation failed
    echo.
    echo Check the output above for details.
    echo For troubleshooting, see: gtf_framework_gen_USAGE.md
    echo ================================================
    exit /b 1
)

echo.
echo ================================================
echo GTF Test Harness Generation Completed
echo ================================================
echo.
echo Next Steps:
echo   1. Validate test infrastructure was created:
echo      - %MODULE_PATH%\test\gtest\CMakeLists.txt
echo      - %MODULE_PATH%\test\gtest\unittest_configs.cmake
echo      - %MODULE_PATH%\test\gtest\prj\unittest_*_%VARIANT%\
echo.
echo   2. If validation passes, proceed to Phase A ^(Mock Generation^)
echo   3. If validation fails, check output above for errors
echo.
echo For GTest workflow, see: .github\agents\GTest.agent.md
echo ================================================

ENDLOCAL
