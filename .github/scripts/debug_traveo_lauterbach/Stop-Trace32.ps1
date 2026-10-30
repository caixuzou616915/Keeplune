# =============================================================================
# Stop-Trace32.ps1 - Close all TRACE32 processes gracefully and confirm they are gone.
#
# Default behavior sends WM_CLOSE to every TRACE32 window (like clicking the X),
# so TRACE32 releases the PowerDebug/probe connection cleanly - CONFIRMED
# (2026-07-14, official Lauterbach guidance) that force-killing instead causes
# the "device already used by other GUI" PODBUS lock on the next launch. Only
# falls back to Stop-Process -Force if graceful close times out.
#
# -Force skips straight to TerminateProcess (old behavior) - avoid unless the
# graceful path is misbehaving, since it recreates the lock-dialog risk.
#
# Usage:
#   .\Stop-Trace32.ps1
#   .\Stop-Trace32.ps1 -Force
# =============================================================================
param(
    [switch] $Force
)

. "$PSScriptRoot\config.ps1"

if ($Force) {
    Write-Host "[stop] Force-killing TRACE32 processes (skips graceful WM_CLOSE - may cause 'device already used by other GUI' on next launch)..."
    Stop-Process -Name t32marm,t32marm64,t32rem,t32start,t32mciserver,t32tcpusb -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
} else {
    Write-Host "[stop] Closing TRACE32 gracefully (WM_CLOSE)..."
    Close-Trace32Gracefully
}

$remaining = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like 't32*' -or $_.Name -like '*trace32*' -or $_.Name -like '*lauterbach*' }

if ($remaining) {
    Write-Warning "[stop] Still running:"
    $remaining | Select-Object Name, Id, MainWindowTitle | Format-Table -AutoSize
    exit 1
}
Write-Host "[stop] No TRACE32-related processes are running."
