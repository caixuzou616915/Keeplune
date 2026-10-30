# =============================================================================
# Read-Variable.ps1 - Read a runtime variable / enum from the application core.
#
# Opens a Var.View window (symbolic enum decode) and PRINTs the numeric value to
# the TRACE32 AREA/log. Works for globals and file-static variables once ELF
# symbols are loaded. Read while the core is halted at a breakpoint for a stable
# value (cyclic functions overwrite state vars every cycle).
#
# Usage:
#   .\Read-Variable.ps1 -Variable VidCtlSM__enCurrOpMode
#   .\Read-Variable.ps1 -Variable VidCtlSM__enCurrOpMode -Capture
# =============================================================================
param(
    [Parameter(Mandatory)] [string] $Variable,
    [switch] $Capture
)

. "$PSScriptRoot\config.ps1"

$cmds = @(
    "Var.View %E $Variable"
    "PRINT `"$Variable = `" Var.VALUE($Variable)"
)

Send-SlaveCommands -Commands $cmds -SettleMs 1000 | Out-Null
Write-Host "[read] Requested value of '$Variable' (see the Var.View window / AREA line)."

if ($Capture) {
    & "$PSScriptRoot\Capture-Trace32.ps1" -OutFile ("read_{0}.png" -f $Variable)
}
