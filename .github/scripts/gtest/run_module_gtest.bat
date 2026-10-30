@echo off
REM Generic Module GTest Runner
REM Usage: run_module_gtest.bat <source_file>
REM Example: run_module_gtest.bat ambstemp1c1.c
REM
REM This batch file is a wrapper that calls the PowerShell implementation

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_module_gtest.ps1" %*
exit /b %ERRORLEVEL%
