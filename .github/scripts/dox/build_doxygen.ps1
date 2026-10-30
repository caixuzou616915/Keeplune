<#
.SYNOPSIS
    Generic Doxygen build and documentation coverage verification for automotive C modules.

.DESCRIPTION
    Replaces all module-specific build_doxygen_<module>.ps1 scripts.
    Steps performed:
      1. Locates the module under pkg\em_s3p_hud\ by searching for its Doxyfile.
      2. Discovers source files in core/ and adapt/ (pkg + app/pkg mirrors).
      3. Extracts all function definitions from .c files and declarations from .h files.
      4. Compares against:
           - Chapter 5 (.dox) - public interface diagram coverage
           - Chapter 7 (.dox) - activity diagram coverage (public + private)
         Prints a colour-coded coverage table and lists missing diagrams.
      5. Resolves doxygen, dot, and plantuml tools (3-tier: process env -> registry -> fallback paths).
      6. Runs Doxygen.

.PARAMETER WorkspaceFolder
    Root workspace folder, e.g. c:\Projects\chery_roof_display

.PARAMETER ModuleName
    Module folder name (lowercase), e.g. powmon, touchq, usmngsm

.PARAMETER FunctionPrefix
    PascalCase prefix used in function names, e.g. PowMon, TouchQ, UsMngSM.
    If omitted, auto-detected from source .c files.

.PARAMETER VerifyOnly
    Skip the Doxygen build; only run the coverage verification report.

.EXAMPLE
    .\build_doxygen.ps1 -WorkspaceFolder "c:\Projects\chery_roof_display" -ModuleName "powmon"
    .\build_doxygen.ps1 -WorkspaceFolder "c:\Projects\chery_roof_display" -ModuleName "touchq" -VerifyOnly
    .\build_doxygen.ps1 -WorkspaceFolder "c:\Projects\chery_roof_display" -ModuleName "usmngsm" -FunctionPrefix "UsMngSM"
#>
param(
    [Parameter(Mandatory=$true)] [string]$WorkspaceFolder,
    [Parameter(Mandatory=$true)] [string]$ModuleName,
    [Parameter(Mandatory=$false)][string]$FunctionPrefix = "",
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
$ModuleUpper = $ModuleName.ToUpper()

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  Doxygen Build + Coverage Verification: $ModuleUpper" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# Helper: read environment variable from Windows registry (user + system).
# Needed because VS Code tasks run in a subprocess that may not inherit env.
# ---------------------------------------------------------------------------
function Get-EnvFromRegistry {
    param([string]$Name)
    $u = (Get-ItemProperty "HKCU:\Environment" -Name $Name -ErrorAction SilentlyContinue).$Name
    if (-not [string]::IsNullOrWhiteSpace($u)) { return $u }
    $s = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" `
          -Name $Name -ErrorAction SilentlyContinue).$Name
    if (-not [string]::IsNullOrWhiteSpace($s)) { return $s }
    return $null
}

# ===========================================================================
# STEP 1 - Locate module
# ===========================================================================
Write-Host "`n[1/4] Locating module '$ModuleName'..." -ForegroundColor White

$doxyfileObj = Get-ChildItem -Path "$WorkspaceFolder\pkg" -Recurse -Filter "Doxyfile" `
    -ErrorAction SilentlyContinue |
    Where-Object { $_.DirectoryName -match "\\$([regex]::Escape($ModuleName))\\doc$" } |
    Select-Object -First 1

if ($null -eq $doxyfileObj) {
    Write-Host "  ERROR: No Doxyfile found for module '$ModuleName'." -ForegroundColor Red
    Write-Host "  Expected: $WorkspaceFolder\pkg\...\$ModuleName\doc\Doxyfile" -ForegroundColor Yellow
    exit 1
}

$docDir     = $doxyfileObj.DirectoryName          # .../powmon/doc
$moduleRoot = Split-Path $docDir -Parent          # .../powmon
$doxDir     = Join-Path $docDir "dox"             # .../powmon/doc/dox

Write-Host "  Module root : $moduleRoot" -ForegroundColor Green
Write-Host "  Doc dir     : $docDir"     -ForegroundColor Green

# Collect source directories from pkg/ and app/pkg/ mirrors
$srcDirs = [System.Collections.Generic.List[string]]::new()
foreach ($sub in @("core", "adapt")) {
    $p = Join-Path $moduleRoot $sub
    if (Test-Path $p) { $srcDirs.Add($p) }
}
$appPkgRoot = Join-Path $WorkspaceFolder "app\pkg"
if (Test-Path $appPkgRoot) {
    $appModDir = Get-ChildItem -Path $appPkgRoot -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $ModuleName } | Select-Object -First 1
    if ($null -ne $appModDir) {
        foreach ($sub in @("core", "adapt")) {
            $p = Join-Path $appModDir.FullName $sub
            if (Test-Path $p) { $srcDirs.Add($p) }
        }
    }
}

Write-Host "  Source dirs : $($srcDirs -join '; ')" -ForegroundColor Green

# ===========================================================================
# STEP 2 - Auto-detect function prefix if not supplied
# ===========================================================================
if ([string]::IsNullOrWhiteSpace($FunctionPrefix)) {
    foreach ($dir in $srcDirs) {
        $cFiles = Get-ChildItem $dir -Filter "*.c" -ErrorAction SilentlyContinue
        foreach ($f in $cFiles) {
            $hit = Get-Content $f.FullName |
                Where-Object { $_ -match "^(?:STATIC\s+)?FUNC\s*\([^)]+\)\s*([A-Z][A-Za-z0-9]+)_" } |
                Select-Object -First 1
            if ($null -ne $hit -and $hit -match "^(?:STATIC\s+)?FUNC\s*\([^)]+\)\s*([A-Z][A-Za-z0-9]+)_") {
                $FunctionPrefix = $Matches[1]
                break
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($FunctionPrefix)) { break }
    }
}

if ([string]::IsNullOrWhiteSpace($FunctionPrefix)) {
    # Last resort: capitalise first letter
    $FunctionPrefix = $ModuleName.Substring(0,1).ToUpper() + $ModuleName.Substring(1)
    Write-Host "  WARNING: Could not auto-detect prefix. Using '$FunctionPrefix'. Pass -FunctionPrefix to override." `
        -ForegroundColor Yellow
}
Write-Host "  Func prefix : $FunctionPrefix" -ForegroundColor Green

# ===========================================================================
# STEP 3 - Documentation coverage verification
# ===========================================================================
Write-Host "`n[2/4] Verifying documentation coverage..." -ForegroundColor White

$pe = [regex]::Escape($FunctionPrefix)   # escaped prefix for regex use

# Patterns to detect function DEFINITIONS at column 0 in .c files
# Pattern A: AUTOSAR FUNC macro  - (STATIC )FUNC(...) Prefix(_|__)Name(
# Pattern B: traditional static  - static <rettype> Prefix(__?)Name(
$defPatA = "^(?:STATIC\s+)?FUNC\s*\([^)]+\)\s*(${pe}_{1,2}[A-Za-z0-9_]+)\s*\("
$defPatB = "^static\s+.*?\b(${pe}_{1,2}[A-Za-z0-9_]+)\s*\("

# Pattern to detect function declarations in .h files
# Covers: extern FUNC(...) or extern rettype or plain rettype before the function name
$declPat = "(?:extern\s+)?(?:FUNC\s*\([^)]+\)|[A-Za-z_][\w\s\*]+)\s+(${pe}_[A-Za-z0-9_]+)\s*\("

$srcFunctions = [System.Collections.Specialized.OrderedDictionary]::new()  # name -> "public"/"private"
$hdrFunctions = [System.Collections.Generic.HashSet[string]]::new()

foreach ($dir in $srcDirs) {

    # --- Public declarations from header files ---
    foreach ($f in (Get-ChildItem $dir -Filter "*.h" -ErrorAction SilentlyContinue)) {
        foreach ($line in (Get-Content $f.FullName)) {
            if ($line -match $declPat) {
                $hdrFunctions.Add($Matches[1]) | Out-Null
            }
        }
    }

    # --- All function definitions from .c files ---
    foreach ($f in (Get-ChildItem $dir -Filter "*.c" -ErrorAction SilentlyContinue)) {
        foreach ($line in (Get-Content $f.FullName)) {
            # Skip comment lines
            if ($line -match "^\s*//" -or $line -match "^\s*\*") { continue }

            $name = $null
            if ($line -match $defPatA) { $name = $Matches[1] }
            elseif ($line -match $defPatB) { $name = $Matches[1] }

            if ($null -ne $name -and -not $srcFunctions.Contains($name)) {
                $srcFunctions[$name] = if ($name -match "__") { "private" } else { "public" }
            }
        }
    }
}

# --- Activity diagrams documented in Chapter 7 (private functions, §7.1.1) ---
$activityFns = [System.Collections.Generic.HashSet[string]]::new()
$ch7File = Get-ChildItem $doxDir -Filter "*_7_internal_design.dox" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -ne $ch7File) {
    foreach ($line in (Get-Content $ch7File.FullName)) {
        # Match:  title **PowMon_vInit**  or  title **PowMon__vHelper**
        if ($line -match "title \*\*(${pe}_{1,2}[A-Za-z0-9_]+)\*\*") {
            $activityFns.Add($Matches[1]) | Out-Null
        }
    }
}

# --- Public interface + activity diagrams documented in Chapter 5 ---
$ifaceFns = [System.Collections.Generic.HashSet[string]]::new()
$ch5File = Get-ChildItem $doxDir -Filter "*_5_export_interface.dox" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -ne $ch5File) {
    foreach ($line in (Get-Content $ch5File.FullName)) {
        # Match interface diagram entries with or without +/- prefix:
        #   "  PowMon_vInit() : void"   (no prefix, indented)
        #   "  +PowMon_vInit():void"    (with + prefix)
        if ($line -match "^\s*[+\-]?\s*(${pe}_[A-Za-z0-9_]+)\s*\(") {
            $ifaceFns.Add($Matches[1]) | Out-Null
        }
        # Also collect public function activity diagram titles from Ch5 §5.1.1
        # Exported function activities live in Ch5, not Ch7.
        if ($line -match "title \*\*(${pe}_[A-Za-z0-9_]+)\*\*") {
            $activityFns.Add($Matches[1]) | Out-Null
        }
    }
}

# --- Print coverage table ---
$col1 = 48; $col2 = 10; $col3 = 16
Write-Host ""
Write-Host ("  {0,-$col1} {1,-$col2} {2,-$col3} {3}" -f `
    "Function", "Scope", "Ch5 Interface", "Ch7 Activity") -ForegroundColor White
Write-Host ("  " + ("-" * 85)) -ForegroundColor DarkGray

$missing  = [System.Collections.Generic.List[string]]::new()
$ch5miss  = [System.Collections.Generic.List[string]]::new()
$covered  = 0

foreach ($fn in $srcFunctions.Keys) {
    $scope = $srcFunctions[$fn]

    $ch5mark = if ($scope -eq "public") {
        if ($ifaceFns.Contains($fn))   { "  [OK]" } else { "  [MISS]" }
    } else { "  n/a" }

    $ch7mark = if ($activityFns.Contains($fn)) { "  [OK]" } else { "  [MISS]" }

    $hasCh5Issue = ($scope -eq "public") -and ($ch5mark -like "*MISS*")
    $hasCh7Issue = $ch7mark -like "*MISS*"

    if ($hasCh7Issue) { $missing.Add($fn) } else { $covered++ }
    if ($hasCh5Issue) { $ch5miss.Add($fn) }

    $color = if ($hasCh5Issue -or $hasCh7Issue) { "Yellow" } else { "Green" }
    Write-Host ("  {0,-$col1} {1,-$col2} {2,-$col3} {3}" -f `
        $fn, $scope, $ch5mark, $ch7mark) -ForegroundColor $color
}

Write-Host ("  " + ("-" * 85)) -ForegroundColor DarkGray
Write-Host ""

$total = $srcFunctions.Count
$pct   = if ($total -gt 0) { [math]::Round(($covered / $total) * 100, 1) } else { 0 }
$coverColor = if ($pct -lt 80) { "Yellow" } elseif ($pct -lt 100) { "Cyan" } else { "Green" }

Write-Host "  Activity diagram coverage : $covered / $total functions ($pct%)" -ForegroundColor $coverColor

if ($ch5miss.Count -gt 0) {
    Write-Host "  Missing from Ch5 interface ($($ch5miss.Count)):" -ForegroundColor Yellow
    $ch5miss | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
}

if ($missing.Count -gt 0) {
    Write-Host "  Missing Ch7 activity diagrams ($($missing.Count)):" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
} else {
    Write-Host "  All functions have Ch7 activity diagrams." -ForegroundColor Green
}

if ($VerifyOnly) {
    Write-Host "`n[Verify-only mode - Doxygen build skipped]`n" -ForegroundColor Cyan
    exit 0
}

# ===========================================================================
# STEP 4 - Resolve build tools (doxygen, dot, plantuml)
# ===========================================================================
Write-Host "`n[3/4] Resolving build tools..." -ForegroundColor White

# --- Doxygen ---
$doxyBin = $null
$doxyCmd = Get-Command "doxygen" -ErrorAction SilentlyContinue
if ($null -ne $doxyCmd) {
    $doxyBin = $doxyCmd.Source
} else {
    @(
        "C:\Program Files\doxygen\bin\doxygen.exe",
        "C:\tools\doxygen\bin\doxygen.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1 |
        ForEach-Object { $doxyBin = $_ }
}
if ($null -eq $doxyBin) {
    Write-Host "  ERROR: doxygen not found in PATH or known locations." -ForegroundColor Red
    exit 1
}
Write-Host "  doxygen  : $doxyBin" -ForegroundColor Green

# --- GraphViz dot (optional - call graphs) ---
$dotPath = $env:DOT_PATH
if ([string]::IsNullOrWhiteSpace($dotPath)) { $dotPath = Get-EnvFromRegistry "DOT_PATH" }
if ([string]::IsNullOrWhiteSpace($dotPath)) {
    $dotCmd = Get-Command "dot" -ErrorAction SilentlyContinue
    if ($null -ne $dotCmd) { $dotPath = Split-Path $dotCmd.Source -Parent }
}
if (-not [string]::IsNullOrWhiteSpace($dotPath)) {
    $env:DOT_PATH = $dotPath
    if ($env:PATH -notlike "*$dotPath*") { $env:PATH = "$dotPath;$env:PATH" }
    Write-Host "  dot      : $dotPath" -ForegroundColor Green
} else {
    Write-Host "  WARNING: dot.exe not found - GraphViz call graphs will be disabled." -ForegroundColor Yellow
}

# --- PlantUML JAR ---
$puJar = $env:PLANTUML_JAR_PATH
if ([string]::IsNullOrWhiteSpace($puJar)) { $puJar = Get-EnvFromRegistry "PLANTUML_JAR_PATH" }
if ([string]::IsNullOrWhiteSpace($puJar)) {
    @(
        "C:\ProgramData\chocolatey\lib\plantuml\tools\plantuml.jar",
        "C:\tools\plantuml\plantuml.jar",
        "$env:USERPROFILE\.plantuml\plantuml.jar"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1 |
        ForEach-Object { $puJar = $_ }
}
if ([string]::IsNullOrWhiteSpace($puJar)) {
    Write-Host "  ERROR: PLANTUML_JAR_PATH not set and plantuml.jar not found." -ForegroundColor Red
    exit 1
}
$env:PLANTUML_JAR_PATH = $puJar
Write-Host "  plantuml : $puJar" -ForegroundColor Green

# ===========================================================================
# STEP 5 - Run Doxygen
# ===========================================================================
Write-Host "`n[4/4] Building documentation..." -ForegroundColor White
Write-Host "  Working dir : $docDir" -ForegroundColor Green

Push-Location $docDir
& $doxyBin "Doxyfile"
$exitCode = $LASTEXITCODE
Pop-Location

if ($exitCode -ne 0) {
    Write-Host "`n  ERROR: Doxygen exited with code $exitCode" -ForegroundColor Red
    exit $exitCode
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Green
Write-Host "  Build Complete: $ModuleUpper" -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
Write-Host "  HTML: $(Join-Path $docDir 'ms\html\index.html')" -ForegroundColor Cyan
Write-Host ""
