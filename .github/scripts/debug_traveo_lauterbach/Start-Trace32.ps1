# =============================================================================
# Start-Trace32.ps1 - Open the TRACE32 MASTER and application-core SLAVE windows.
#
# Launches t32marm.exe directly with the project startup script (LT_STARTUP_SCRIPT
# / auto-discovered, see config.ps1) + app ELF, which flashes the target and arms
# the default breakpoints. This is more reliable than `run.py debug_trace32`,
# which sometimes only opens a single blank PowerView.
#
# Requires $env:LT_VARIANT to be set (see config.ps1 / SKILL.md).
#
# NOTE: a `-EnableRemoteApi` option (launching with `-c core.t32` to enable
# t32rem/RCL) was tried and bench-tested on one project's AMP flow - CONFIRMED
# NOT VIABLE there: it loaded a generic, wrong-architecture session with no
# AMP setup at all, because `core.t32` (built for the single-instance
# flash-only flow in tools/ci_scripts/jenkins/download/flasher.py) did not
# compose with that variant's AMP startup script. This may or may not apply to
# your project/chip - re-verify on the bench before relying on it. Removed;
# use Send-Trace32Command.ps1 (keystroke automation) to drive the GUI.
#
# Usage:
#   $env:LT_VARIANT = 'tviib_2m_aravalli_s3p'   # example - use YOUR project's variant
#   .\Start-Trace32.ps1                    # kills stale sessions, then opens master+slave
#   .\Start-Trace32.ps1 -NoKill            # do not kill existing sessions first
#
# TIMING (bench-observed 2026-07-15): the MASTER/SLAVE window TITLES can appear
# within ~12s, but the underlying AMP flash + master->slave handoff can take
# noticeably longer to fully settle. Sending breakpoint/Go commands too soon
# after window-detection has produced both a misleading "stuck at the old
# default breakpoint" false alarm AND a genuine "target system down" error on
# different runs. Default wait raised from 12s to 60s to give the handshake
# room to finish before any script proceeds to send commands - do not shorten
# this without re-verifying on the bench.
# =============================================================================
param(
    [switch] $NoKill,
    [int]    $WaitSeconds = 60
)

. "$PSScriptRoot\config.ps1"

if (-not $NoKill) {
    Write-Host "[start] Closing any existing TRACE32 session gracefully (avoids the PODBUS 'device already used by other GUI' lock caused by force-killing)..."
    Close-Trace32Gracefully
}

if (-not (Test-Path $LT_StartupScript)) { throw "Startup script not found: $LT_StartupScript" }
if (-not (Test-Path $LT_AbsFile))       { throw "App ELF not found: $LT_AbsFile (build the variant first)" }

Write-Host "[start] Launching TRACE32 (flash + AMP master/slave)..."
Push-Location $LT_BuildDir
try {
    # -s <script> runs the startup PRACTICE script; the ELF is passed as its argument.
    & $LT_Trace32Exe -s $LT_StartupScript ("bin\{0}.abs" -f $LT_Variant)
    Start-Sleep -Seconds $WaitSeconds
}
finally {
    Pop-Location
}

$master = Get-MasterProcess
$slave  = Get-SlaveProcess
Get-Process t32marm -ErrorAction SilentlyContinue |
    Select-Object Id, Responding, MainWindowTitle | Format-Table -AutoSize

# The "Welcome to TRACE32!" onboarding modal appears on EVERY fresh launch (even with its own
# "Show this dialog at start" unchecked, since each launch gets a fresh temp profile) - it does
# NOT block the underlying flash/PRACTICE script, but leaving it up risks corrupting the next
# automated keystroke command sent by Send-OneCommand. Dismiss it once, on both windows, here.
if ($master) { Dismiss-Trace32WelcomeDialog -Process $master | Out-Null }
if ($slave)  { Dismiss-Trace32WelcomeDialog -Process $slave  | Out-Null }

if ($master -and $slave) {
    Write-Host "[start] OK - MASTER (PID $($master.Id)) and CM4 SLAVE1 (PID $($slave.Id)) are up."
} else {
    Write-Warning "[start] Master/slave windows not both detected. If you see only 'TRACE32 PowerView', re-run Start-Trace32.ps1."
    # NOTE: a generic 'TRACE32 PowerView' title can hide a SEPARATE blocking
    # error dialog (e.g. PODBUS 'device already used by other GUI') with the
    # SAME generic title - Get-Process.MainWindowTitle only exposes one window
    # per process and may pick the blank one behind it. Screenshot every
    # top-level window so the real state (including hidden dialogs) is visible.
    $diagShots = Save-Trace32DiagnosticScreenshots
    if ($diagShots.Count) {
        Write-Warning "[start] Saved $($diagShots.Count) diagnostic screenshot(s) - inspect these for a hidden error dialog:"
        $diagShots | ForEach-Object { Write-Warning "  $_" }
    }
}
