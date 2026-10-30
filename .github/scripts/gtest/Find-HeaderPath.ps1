<#
.SYNOPSIS
    Locates header files in the project for resolving missing header issues in GTF tests.

.DESCRIPTION
    Searches the project directory for a specified header file and displays all matching paths.
    Primarily used to resolve compilation errors due to missing headers in Google Test projects.
    
    Author: Zhao Jianbo
    Supported by: UX SW AI Community

.PARAMETER FileName
    The name of the header file to search for (e.g., Std_Types.h, s3phuddef.h)

.PARAMETER ProjectRoot
    Optional. The root directory of the project. Defaults to the script's directory.

.EXAMPLE
    .\Find-HeaderPath.ps1 "Std_Types.h"
    
    Searches for Std_Types.h in the project and displays all matching paths.

.EXAMPLE
    .\Find-HeaderPath.ps1 "vidcond1c1.h" -ProjectRoot "C:\Projects\s3p_arav"
    
    Searches for vidcond1c1.h starting from the specified project root.

.NOTES
    Author: GTF Test Automation
    Version: 1.0
    Date: 2026-02-11
#>

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$FileName,
    
    [Parameter(Mandatory=$false)]
    [string]$ProjectRoot = ""
)

# Determine project root
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    # Try: script is in scripts/gtest/, so traverse up 2 levels to project root
    $ProjectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    
    # If that doesn't yield a valid project root, require the caller to provide it explicitly.
    if (-not (Test-Path $ProjectRoot)) {
        Write-Error "Cannot determine project root. Use -ProjectRoot parameter."
        exit 1
    }
}

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "GTF Header File Search Utility" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Searching for: $FileName" -ForegroundColor Yellow
Write-Host "Project Root:  $ProjectRoot" -ForegroundColor Yellow
Write-Host ""

# Search for the file
Write-Host "Searching... (this may take a few seconds)" -ForegroundColor Gray
$results = Get-ChildItem -Path $ProjectRoot -Filter $FileName -Recurse -ErrorAction SilentlyContinue | Select-Object FullName, Directory

if ($results) {
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host "FOUND $($results.Count) MATCH(ES):" -ForegroundColor Green
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host ""
    
    $index = 1
    foreach ($result in $results) {
        Write-Host "[$index] Full Path:" -ForegroundColor Cyan
        Write-Host "    $($result.FullName)" -ForegroundColor White
        Write-Host ""
        Write-Host "    Directory:" -ForegroundColor Gray
        Write-Host "    $($result.Directory)" -ForegroundColor Gray
        Write-Host ""
        
        # Compute relative path from project root
        $relativePath = $result.FullName.Replace($ProjectRoot, "").TrimStart('\', '/')
        Write-Host "    Relative Path from Project Root:" -ForegroundColor Gray
        Write-Host "    $relativePath" -ForegroundColor Gray
        Write-Host ""
        Write-Host "----------------------------------------------------------------" -ForegroundColor DarkGray
        $index++
    }
    
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "RECOMMENDED ACTIONS:" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Note the directory path where the header is located" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "2. Update CMakeLists.txt at:" -ForegroundColor Yellow
    Write-Host "   [Module Path]\test\gtest\prj\unittest_[module]_pf\CMakeLists.txt" -ForegroundColor White
    Write-Host ""
    Write-Host "3. Add to target_include_directories() section:" -ForegroundColor Yellow
    Write-Host '   PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../relative/path/to/header/dir"' -ForegroundColor White
    Write-Host ""
    Write-Host "4. Calculate relative path from unittest_[module]_pf/ to the header directory" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "COMMON HEADER LOCATIONS (Quick Reference):" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "AUTOSAR Headers (Std_Types.h, Rte_Type.h, etc.):" -ForegroundColor Gray
    Write-Host '  PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../../../app/pkg/em_s3p_hud/s3phudcommon/s3phuddef/test/gtest/common_ext"' -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Module-specific headers in same package (videoctl/vidcond, etc.):" -ForegroundColor Gray
    Write-Host '  PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../../[module_name]/core"' -ForegroundColor DarkGray
    Write-Host ""
    
} else {
    Write-Host "================================================================" -ForegroundColor Red
    Write-Host "NO MATCHES FOUND" -ForegroundColor Red
    Write-Host "================================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Possible reasons:" -ForegroundColor Yellow
    Write-Host "  - File does not exist in project" -ForegroundColor Gray
    Write-Host "  - File is in an excluded directory (node_modules, .git, etc.)" -ForegroundColor Gray
    Write-Host "  - Filename is misspelled" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Try:" -ForegroundColor Yellow
    Write-Host "  - Check spelling of filename" -ForegroundColor Gray
    Write-Host "  - Search with wildcard: .\Find-HeaderPath.ps1 '*filename*'" -ForegroundColor Gray
    Write-Host "  - Verify file exists in project" -ForegroundColor Gray
    Write-Host ""
}

Write-Host ""
