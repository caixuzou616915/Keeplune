# =============================================================================
# Set-Breakpoint.ps1 - Break on an application function on the application core.
#
# Removes the default post-flash breakpoints (Startup_Init, ErrorHook,
# Det_ASR40_ReportError, Mcu_PerformReset), sets a Program breakpoint on the
# requested symbol, runs, and waits for the hit.
#
# GOTCHA (bench-verified 2026-07-15): if the default breakpoints are cleared in
# the SAME batch/settle window as the new Break.Set + Go, a call stack captured
# right after the WAIT can still show the core halted at the OLD default
# breakpoint (e.g. Startup_Init/_RESET), looking like the core never released
# from reset. This is a FALSE ALARM, not a real hang - the deletion just hadn't
# fully settled before Go ran. Fix: delete defaults as their OWN step, confirm
# with Break.List, THEN set+Go as a second step. Do not conclude the target/core
# is stuck from a single capture without first clearing+verifying an empty
# Break.List this way.
#
# Usage:
#   .\Set-Breakpoint.ps1 -Symbol VidCtlSM_vMainFunction
#   .\Set-Breakpoint.ps1 -Symbol VidCtlSM_vMainFunction -WaitSeconds 30 -KeepDefaults
# =============================================================================
param(
    [Parameter(Mandatory)] [string] $Symbol,
    [int]    $WaitSeconds = 20,
    [switch] $KeepDefaults
)

. "$PSScriptRoot\config.ps1"

if (-not $KeepDefaults) {
    # Step 1: clear default post-flash breakpoints as their OWN settled step, and
    # verify via Break.List before proceeding - do not chain this into the same
    # batch as Break.Set/Go (see gotcha above).
    Send-SlaveCommands -Commands @('Break.Delete /ALL', 'Break.List') -SettleMs 1500 | Out-Null
    Write-Host "[bp] Cleared default breakpoints (verify empty Break.List via a screenshot if unsure)."
}

# Step 2: set the real breakpoint and run.
$cmds = @(
    "Break.Set $Symbol /Program"
    'Break.Enable /ALL'
    'Break.List'
    'Go'
    "WAIT !STATE.RUN() $WaitSeconds.s"
)

$slave = Send-SlaveCommands -Commands $cmds -SettleMs 1100
Write-Host "[bp] Breakpoint on '$Symbol' set; ran and waited up to ${WaitSeconds}s for the hit."
Write-Host "[bp] Use Capture-Trace32.ps1 to screenshot the stop state, or Read-Variable.ps1 to inspect."
