# hud_tc_runner.ps1 - Run HUD debugger test cases via GHS Multi and report PASS/FAIL
#
# WHAT: drives the GHS Multi debugger against a running Traveo II ECU to read the
# HUD / App-Mode-Manager state variable (AmmSM__enCurrentMode) and, optionally,
# to force the HUD ON/OFF and verify the resulting state. It reuses the SAME
# proven env + multi invocation as the bench debug playback (see repo memory).
#
# TEST CASES (in .github/scripts/debug_traveo_ghs/):
#   read  -> hud_tc01_read_state.rc  (read-only: report current HUD state)
#   on    -> hud_tc02_turn_on.rc     (force ProjectionOn=40, expect enCurrentMode==40)
#   off   -> hud_tc03_turn_off.rc    (force Ready=20,        expect enCurrentMode!=40)
#   all   -> run read, on, off in sequence
#
# PRECONDITION: ECU already flashed and CANoe running with KL15 ON.
#
# USAGE:
#   .\hud_tc_runner.ps1 -Tc read
#   .\hud_tc_runner.ps1 -Tc on
#   .\hud_tc_runner.ps1 -Tc all
#   .\hud_tc_runner.ps1 -Tc read -Variant tviib_e4m_aravalli_s3p -Repo C:\Project\JB\s3p\sw.sys.tv2.meta-repo-ux
[CmdletBinding()]
param(
    [ValidateSet('read', 'on', 'off', 'all')]
    [string]$Tc = 'read',
    [string]$Variant = 'tviib_e4m_aravalli_s3p',   # app-core variant on this bench
    [string]$Repo,                                  # repo root; auto-detected if omitted
    [string]$GhsConanPath = 'D:\.conan\short\0426ef\1',  # holds multi.exe (from repo memory)
    [string]$GhsLmHost = '@ls-ghs-sg-1.int.automotive-wan.com',
    [int]$MaxAttempts = 3,                           # retry transient verify/connect glitches
    [int]$TimeoutSec = 240                           # safety cap per attempt (verify can be slow)
)

$ErrorActionPreference = 'Stop'

# Transient probe/verify/connect glitches that WARRANT a retry (not a real config error).
# Verified 2026-07-16: full `verify -all` intermittently aborts with "MULTI command stack"
# on the readback-protected HSM/SHE ROM; a plain re-run succeeds within 1-2 tries.
$transientPattern = 'MULTI command stack|not connected to a debug server|hardbrk: not allowed|' +
                    'Could not detect a flash device|Memory write failed|already connected'

# AmmSM_tenStates decode table (from ammsm_interfaces.swcd)
$stateNames = @{
    0  = 'ShutDown'; 10 = 'Standby'; 11 = 'WaitReady'; 19 = 'WaitStandby'; 20 = 'Ready'
    21 = 'WaitOpPos'; 28 = 'WaitReadyPos'; 29 = 'WaitDisplayOff'; 30 = 'WaitDisplayOn'
    31 = 'WaitBacklightOn'; 39 = 'WaitBacklightOff'; 40 = 'ProjectionOn'; 50 = 'PowerFail'
    59 = 'WaitDirectControl'; 60 = 'DirectControl'
}

# --- git bash (needed to launch multi with the same env as the bench flow) ---
$gitBash = @(
    "C:\Program Files\Git\bin\bash.exe",
    "D:\Tool\Common\Git\bin\bash.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $gitBash) { throw "git bash not found. Install Git for Windows." }

# --- repo root (contains run.py + econ_config.sh) ---
if (-not $Repo) {
    $dir = (Get-Location).Path
    while ($dir -and -not ((Test-Path "$dir\run.py") -and (Test-Path "$dir\econ_config.sh"))) {
        $parent = Split-Path $dir -Parent
        if ($parent -eq $dir) { $dir = $null; break }
        $dir = $parent
    }
    $Repo = $dir
}
if (-not $Repo -or -not (Test-Path "$Repo\run.py")) { throw "Repo root not found. Pass -Repo." }

$buildDir = Join-Path $Repo "build\$Variant.Debug"
if (-not (Test-Path (Join-Path $buildDir 'debug.ghsmc'))) {
    throw "debug.ghsmc not found in $buildDir. Flash/build the variant first."
}
$scriptDir = Join-Path $Repo '.github\scripts\debug_traveo_ghs'
if (-not (Test-Path $GhsConanPath)) {
    Write-Warning "GHS conan path '$GhsConanPath' not found - multi may not be on PATH. Pass -GhsConanPath."
}

# repo path as git-bash absolute (e.g. C:\a\b -> /c/a/b)
$bBuild = '/' + $buildDir.Substring(0, 1).ToLower() + $buildDir.Substring(2).Replace('\', '/')
$bConan = '/' + $GhsConanPath.Substring(0, 1).ToLower() + $GhsConanPath.Substring(2).Replace('\', '/')

$tcMap = @{
    read = @{ rc = 'hud_tc01_read_state.rc'; tag = 'HUD_TC01'; name = 'Read HUD state' }
    on   = @{ rc = 'hud_tc02_turn_on.rc'; tag = 'HUD_TC02'; name = 'Turn HUD ON' }
    off  = @{ rc = 'hud_tc03_turn_off.rc'; tag = 'HUD_TC03'; name = 'Turn HUD OFF' }
}
$order = if ($Tc -eq 'all') { @('read', 'on', 'off') } else { @($Tc) }

# Launch multi via git-bash in the FOREGROUND (the only form that reliably acquires the SWD
# probe - Start-Job/Start-Process do NOT). `-nodisplay` runs multi headless so that if the RC
# aborts before its final `quit`, multi still EXITS instead of dropping to an interactive GUI
# (that orphaned GUI was the original "stuck forever" hang). Returns $true always; git/multi
# stderr is tolerated (no throw).
function Invoke-MultiWithTimeout([string]$bash, [int]$timeoutSec) {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $gitBash -c $bash 2>&1 | Out-Null
        return $true
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
}

function Invoke-HudTc([string]$key) {
    $tc = $tcMap[$key]
    $rcPath = Join-Path $scriptDir $tc.rc
    if (-not (Test-Path $rcPath)) { throw "Test case RC not found: $rcPath" }
    $bRc = '/' + $rcPath.Substring(0, 1).ToLower() + $rcPath.Substring(2).Replace('\', '/')
    $outWin = Join-Path $buildDir ($tc.tag + '_out.txt')
    $rcDbg = "../../app/variants/$Variant/debug/ghs"

    Write-Host "`n=== $($tc.tag): $($tc.name) ===" -ForegroundColor Cyan

    $cur = $null
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        if (Test-Path $outWin) { Remove-Item $outWin -Force -ErrorAction SilentlyContinue }
        # kill stale probe holders so multi can attach cleanly
        Stop-Process -Name "multi", "mpserv", "mpserv64", "gmpserv" -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3

        $bash = @(
            "export GHS_LMHOST='$GhsLmHost'",
            "export GHS_LMWHICH='ghs'",
            "export PATH='$bConan`:$bConan/_ide:`$PATH'",
            "cd $bBuild",
            "multi -nosplash -servertimeout 120 debug.ghsmc " +
            "-rc $rcDbg/multi.rc -rc $rcDbg/tvii_debug_4mbe.rc " +
            "-R $($tc.tag)_out.txt -p $bRc"
        ) -join '; '

        Write-Host "[$($tc.tag)] attempt $attempt/$MaxAttempts (timeout ${TimeoutSec}s)..." -ForegroundColor DarkGray
        $finished = Invoke-MultiWithTimeout $bash $TimeoutSec

        if (-not (Test-Path $outWin)) {
            Write-Warning "[$($tc.tag)] attempt $attempt produced no log - retrying."
            continue
        }
        # stream only our HUD_ marker lines out of the multi-MB verify log
        $hudLines = Select-String -Path $outWin -Pattern ($tc.tag + ':') -SimpleMatch |
        ForEach-Object { ($_.Line -replace '^\s*//.*$', '').Trim() } | Where-Object { $_ }
        $m = Select-String -Path $outWin -Pattern 'AmmSM__enCurrentMode = (\d+)' | Select-Object -Last 1
        if ($m) { $cur = [int]$m.Matches[0].Groups[1].Value }

        if ($null -ne $cur) {
            $hudLines | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
            break   # got a reading - done
        }

        $isTransient = Select-String -Path $outWin -Pattern $transientPattern -Quiet
        if (-not $finished) { Write-Warning "[$($tc.tag)] attempt $attempt timed out - retrying." }
        elseif ($isTransient) { Write-Warning "[$($tc.tag)] attempt $attempt hit a transient probe/verify glitch - retrying." }
        else { Write-Warning "[$($tc.tag)] attempt ${attempt}: no reading captured - retrying." }
    }

    if ($null -eq $cur) {
        Write-Host "[$($tc.tag)] RESULT: ERROR - no HUD state read after $MaxAttempts attempts (see $outWin)" -ForegroundColor Red
        return
    }
    $nm = if ($stateNames.ContainsKey($cur)) { $stateNames[$cur] } else { "Unknown($cur)" }
    $hud = if ($cur -eq 40) { 'HUD ON (projecting)' } elseif ($cur -in 30, 31) { 'HUD turning ON' }
    elseif ($cur -in 29, 39) { 'HUD turning OFF' } else { 'HUD OFF' }

    switch ($key) {
        'read' { $pass = $true }   # read-only: always report, no expected value
        'on' { $pass = ($cur -eq 40) }
        'off' { $pass = ($cur -ne 40) }
    }
    $verdict = if ($key -eq 'read') { 'INFO' } elseif ($pass) { 'PASS' } else { 'FAIL' }
    $color = if ($verdict -eq 'FAIL') { 'Red' } elseif ($verdict -eq 'PASS') { 'Green' } else { 'Cyan' }
    Write-Host "[$($tc.tag)] $verdict - AmmSM__enCurrentMode=$cur ($nm) => $hud" -ForegroundColor $color
}

foreach ($k in $order) { Invoke-HudTc $k }
Write-Host "`nDone. Full logs: $buildDir\HUD_TC0*_out.txt" -ForegroundColor DarkGray
