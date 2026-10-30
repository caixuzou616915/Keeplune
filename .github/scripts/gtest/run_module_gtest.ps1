#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generic Module GTest Runner for GTF
.DESCRIPTION
    Finds and runs GTF unit tests for a given C source file
    
    Author: Zhao Jianbo
    Supported by: UX SW AI Community
.PARAMETER SourceFile
    The C source file name (e.g., ambstemp1c1.c)
.EXAMPLE
    .\run_module_gtest.ps1 ambstemp1c1.c
#>

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$SourceFile
)

$ErrorActionPreference = "Stop"

# Get project root directory (traverse up from script location)
# Script location: .github/scripts/gtest/ -> need to go up 3 levels to project root
$ProjectRoot = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "GTF Module Test Runner" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"
Write-Host "Source File: $SourceFile"
Write-Host ""

# Set HUD_PROJECT_ROOT environment variable
$env:HUD_PROJECT_ROOT = $ProjectRoot
Write-Host "Setting HUD_PROJECT_ROOT=$env:HUD_PROJECT_ROOT"

# Search for source file in pkg directory
Write-Host ""
Write-Host "Searching for source file: $SourceFile" -ForegroundColor Yellow

$file = Get-ChildItem -Path "$ProjectRoot\pkg" -Filter $SourceFile -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $file) {
    Write-Host "ERROR: Source file '$SourceFile' not found in pkg directory" -ForegroundColor Red
    exit 1
}

Write-Host "Found file: $($file.FullName)" -ForegroundColor Green

# Find module path (traverse up to find test/gtest folder)
$modulePath = $file.DirectoryName

while ($modulePath -and $modulePath.StartsWith($ProjectRoot)) {
    $testGtestPath = Join-Path $modulePath "test\gtest"
    if (Test-Path $testGtestPath) {
        $relativePath = $modulePath.Substring($ProjectRoot.Length + 1)
        $moduleTestPath = Join-Path $relativePath "test\gtest"
        Write-Host "Module path: $relativePath" -ForegroundColor Green
        Write-Host "Test path: $moduleTestPath" -ForegroundColor Green
        break
    }
    $modulePath = Split-Path $modulePath -Parent
}

if (-not $modulePath -or $modulePath.Length -le $ProjectRoot.Length) {
    Write-Host "ERROR: No test/gtest folder found for this module" -ForegroundColor Red
    exit 3
}

# Find testrunner script in test directory
$testDirectory = Join-Path $ProjectRoot $moduleTestPath
Write-Host ""
Write-Host "Searching for testrunner script in: $testDirectory" -ForegroundColor Yellow

$testrunnerScripts = Get-ChildItem -Path $testDirectory -Filter "*testrunner.sh" -File -ErrorAction SilentlyContinue

if ($testrunnerScripts.Count -eq 0) {
    Write-Host "ERROR: No testrunner script (*testrunner.sh) found in test directory" -ForegroundColor Red
    exit 4
}

$testrunnerScript = $testrunnerScripts[0].Name
Write-Host "Found testrunner script: $testrunnerScript" -ForegroundColor Green

# Convert Windows paths to Unix-style paths for bash
$projectRootUnix = $ProjectRoot -replace '\\', '/' -replace '^([A-Z]):', '/$1'
$moduleTestPathUnix = $moduleTestPath -replace '\\', '/'

# Run GTF tests following the correct procedure
Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "Running GTF Tests" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

# Build bash command
$bashCommand = "cd '$projectRootUnix' && source ./econ_config.sh && cd '$projectRootUnix/$moduleTestPathUnix' && . conan_prepare.sh && ./$testrunnerScript"

Write-Host "Executing: bash -c `"$bashCommand`"" -ForegroundColor Yellow
Write-Host ""

# Execute the bash command directly (not using Start-Process to preserve output)
& bash -c $bashCommand
$exitCode = $LASTEXITCODE

# Check exit code
if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Test execution failed with exit code $exitCode" -ForegroundColor Red
    exit $exitCode
}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host "GTF Tests Completed Successfully" -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Green

exit 0
