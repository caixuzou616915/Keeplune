<#
.SYNOPSIS
  Generic runner for a GHS Multi `.rc` playback script against a running Traveo II ECU
  (Bench A / application core cm4). Verify is skipped, multi is time-boxed, and the run
  fails fast on common MULTI errors.

.DESCRIPTION
  This is the generic engine behind ANY module debugger test set (VidCtlSM, AmmSM/HUD, ...).
  It knows nothing about the .rc content - you supply the .rc (built from the read_var.rc /
  write_var.rc / breakpoint.rc templates or hand-written). It:
    * kills stale multi/mpserv, sets TVII_SKIP_VERIFY=1 (skips slow `verify -all`),
    * launches `multi ... -p <Rc>` in a background job with an ABSOLUTE cd
      (Start-Job does NOT inherit Push-Location),
    * polls the -R log for a success marker OR common MULTI error markers,
    * kills multi promptly and prints the result (fail-fast, no indefinite hang).

  Requirements: CANoe running with KL15 ON, and the variant already flashed
  (build\<Variant>.Debug\debug.ghsmc must exist).

.PARAMETER Rc
  .rc playback file name (relative to the variant build dir) or absolute path.

.PARAMETER Out
  -R log file name (in the build dir). Default: <RcBaseName>_out.txt.

.PARAMETER Variant
  App-core variant. Bench A default: tviib_e4m_aravalli_s3p.

.PARAMETER Repo
  Repo root (contains run.py + econ_config.sh). Auto-detected upward from CWD if omitted.

.PARAMETER GhsConanPath
  Conan short dir holding multi.exe. Default 0426ef (this variant's ghs-multi 8.x).

.PARAMETER SuccessMarker
  Text that marks successful completion in the -R log. Default 'RESULT END'
  (put `mprintf("RESULT END\n")` at the end of your .rc).

.PARAMETER TimeoutSec
  Hard cap - multi is killed if neither success nor error marker appears. Default 160.

.EXAMPLE
  .\run_debug_rc.ps1 -Rc tc1_directcontrol.rc

.EXAMPLE
  .\run_debug_rc.ps1 -Rc my_read.rc -SuccessMarker 'READ DONE' -TimeoutSec 120
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Rc,
    [string]$Out,
    [string]$Variant = 'tviib_e4m_aravalli_s3p',
    [string]$Repo,
    [string]$GhsConanPath = 'D:\.conan\short\0426ef\1',
    [string]$SuccessMarker = 'RESULT END',
    [int]$TimeoutSec = 160
)

$ErrorActionPreference = 'SilentlyContinue'

# --- Resolve repo root (contains run.py + econ_config.sh) ---
if (-not $Repo) {
    $dir = (Get-Location).Path
    while ($dir -and -not ((Test-Path "$dir\run.py") -and (Test-Path "$dir\econ_config.sh"))) {
        $parent = Split-Path $dir -Parent
        if ($parent -eq $dir) { $dir = $null; break }
        $dir = $parent
    }
    $Repo = $dir
}
if (-not $Repo) { throw "Repo root (run.py + econ_config.sh) not found. Pass -Repo explicitly." }

$buildDir = Join-Path $Repo "build\$Variant.Debug"
if (-not (Test-Path (Join-Path $buildDir 'debug.ghsmc'))) {
    throw "debug.ghsmc not found in $buildDir - flash/build the variant first."
}
if (-not $Out) { $Out = [IO.Path]::GetFileNameWithoutExtension($Rc) + '_out.txt' }

$bash = @('C:\Program Files\Git\bin\bash.exe', 'D:\Tool\Common\Git\bin\bash.exe') |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $bash) { throw 'git bash not found. Install Git for Windows.' }
if (-not (Test-Path $GhsConanPath)) { Write-Warning "GhsConanPath '$GhsConanPath' not found - multi may not be on PATH." }

# git-bash absolute paths (C:\a\b -> /c/a/b)
$bBuild = '/' + $buildDir.Substring(0, 1).ToLower() + $buildDir.Substring(2).Replace('\', '/')
$bConan = '/' + $GhsConanPath.Substring(0, 1).ToLower() + $GhsConanPath.Substring(2).Replace('\', '/')

Stop-Process -Name 'multi', 'mpserv', 'mpserv64', 'gmpserv' -Force
Start-Sleep -Seconds 4
Remove-Item (Join-Path $buildDir $Out) -Force

# TVII_SKIP_VERIFY=1 set externally so tvii_debug_*.py skips the slow `verify -all`
# WITHOUT editing that (shared) script. Absolute `cd` because Start-Job ignores Push-Location.
$cmd = "export TVII_SKIP_VERIFY=1; export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; " +
       "export PATH='$bConan`:$bConan/_ide:`$PATH'; cd '$bBuild' || exit 3; " +
       "multi -nosplash -servertimeout 120 debug.ghsmc " +
       "-rc ../../app/variants/$Variant/debug/ghs/multi.rc " +
       "-rc ../../app/variants/$Variant/debug/ghs/tvii_debug_4mbe.rc " +
       "-R $Out -p $Rc"

$job = Start-Job -ScriptBlock { param($b, $c) & $b -c $c } -ArgumentList $bash, $cmd

# Fail-fast poll: success marker OR a MULTI error marker (MULTI discards the rest of the
# script - incl. `quit` - on a command error, so the GUI would otherwise hang until timeout).
$outPath  = Join-Path $buildDir $Out
$errRegex = 'Syntax Checking|Unexpected token|thrown away owing to command failure|not successful|No match|Invalid Address|Cannot set|Cannot find'
$elapsed = 0
$status = 'timeout'
while ($elapsed -lt $TimeoutSec) {
    Start-Sleep -Seconds 3; $elapsed += 3
    if (Test-Path $outPath) {
        if (Select-String -Path $outPath -Pattern ([regex]::Escape($SuccessMarker)) -Quiet) { $status = 'ok'; break }
        if (Select-String -Path $outPath -Pattern $errRegex -Quiet) { $status = 'error'; break }
    }
    if ($job.State -eq 'Completed') { break }
}
Start-Sleep -Seconds 1
Stop-Process -Name 'multi', 'mpserv' -Force
Receive-Job $job | Out-Null
Remove-Job $job -Force

switch ($status) {
    'ok'      { Write-Host "[$Rc] COMPLETED in ~${elapsed}s" -ForegroundColor Green }
    'error'   { Write-Host "[$Rc] DEBUGGER ERROR after ~${elapsed}s - see context below" -ForegroundColor Red }
    'timeout' { Write-Host "[$Rc] TIMEOUT after ${elapsed}s - killed multi" -ForegroundColor Yellow }
}
if ($status -eq 'error') {
    Write-Host '=== error context ==='
    Get-Content $outPath | Select-String -Pattern $errRegex -Context 2, 1
}
Write-Host "=== $Out (filtered tail) ==="
Get-Content $outPath | Where-Object { $_ -notmatch 'INCOHERENT' } | Select-Object -Last 30
