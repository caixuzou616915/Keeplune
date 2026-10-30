# =============================================================================
# Write-Variable.ps1 - Write a NUMERIC value to a variable on the application core,
# then read it back.
#
# CRITICAL SYNTAX (verified on the bench):
#   OK:   Var.Set VidCtlSM__enCurrOpMode=9        (no spaces, numeric literal)
#   FAIL: Var.Set VAR = VidCtlSM_nenDisplayOn     (spaces + symbolic enum name -> silent no-op)
# Convert enum names to their numeric value before writing.
#
# The read-back happens while halted; a cyclic *_vMainFunction will overwrite the
# value on the next cycle if you Go, so verify before resuming.
#
# Usage:
#   .\Write-Variable.ps1 -Variable VidCtlSM__enCurrOpMode -Value 9
# =============================================================================
param(
    [Parameter(Mandatory)] [string] $Variable,
    [Parameter(Mandatory)] [int]    $Value,   # numeric literal only (int enforces this)
    [switch] $Capture
)

. "$PSScriptRoot\config.ps1"

$cmds = @(
    "PRINT `"$Variable Before = `" Var.VALUE($Variable)"
    "Var.Set $Variable=$Value"                 # NO spaces around '='
    "Var.View %E $Variable"
    "PRINT `"$Variable After = `" Var.VALUE($Variable)"
)

Send-SlaveCommands -Commands $cmds -SettleMs 1000 | Out-Null
Write-Host "[write] Wrote $Variable = $Value and read it back (see Var.View / AREA lines)."

if ($Capture) {
    & "$PSScriptRoot\Capture-Trace32.ps1" -OutFile ("write_{0}.png" -f $Variable)
}
