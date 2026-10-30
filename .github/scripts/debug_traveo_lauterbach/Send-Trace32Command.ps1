# =============================================================================
# Send-Trace32Command.ps1 - Send one or more commands to the application-core SLAVE window.
#
# The default `debug_trace32` session has NO remote API (t32rem fails), so we
# drive the GUI by focusing the slave window and sending keystrokes. Commands are
# sent ONE AT A TIME - multi-line pastes get concatenated and fail.
#
# Usage:
#   .\Send-Trace32Command.ps1 -Command 'Break.List'
#   .\Send-Trace32Command.ps1 -Command @('Break.Delete /ALL','Go')
# =============================================================================
param(
    [Parameter(Mandatory)] [string[]] $Command,
    [int] $SettleMs = 900
)

. "$PSScriptRoot\config.ps1"

$slave = Send-SlaveCommands -Commands $Command -SettleMs $SettleMs
Write-Host "[send] Sent $($Command.Count) command(s) to the application-core SLAVE window (PID $($slave.Id))."
