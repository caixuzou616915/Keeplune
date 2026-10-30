# =============================================================================
# Get-CallStack.ps1 - Show and screenshot the application-core call stack (frame chain).
#
# VERIFIED on the bench (2026-07-14): `FRAME.NAME()`/`FRAME.OFFSET()` PRACTICE
# functions and the `Frame.List` command do NOT exist on this TRACE32/target
# ("no function 'FRAME.NAME' exists", "unknown command" respectively) - there is
# no known headless/text-dump method. The only working method is the GUI
# `Frame.view /Caller /Locals` window, captured via screenshot. Example verified
# output for VidCtlSM_vMainFunction:
#   -000 VidCtlSM_vMainFunction()
#   -001 Os_Entry_Task_ASW_Mid()
#      . Rte_CurrentEvent = 1080
#      . Rte_ShutdownFlag = 0
#   -002 Os_DispatchECC(asm)
#
# The core must be HALTED (e.g. via Set-Breakpoint.ps1) for a meaningful stack.
#
# Usage:
#   .\Get-CallStack.ps1
#   .\Get-CallStack.ps1 -OutFile callstack.png
# =============================================================================
param(
    [string] $OutFile = 'callstack.png',
    [int]    $SettleMs = 1200
)

. "$PSScriptRoot\config.ps1"

Send-SlaveCommands -Commands @('Frame.view /Caller /Locals') -SettleMs $SettleMs | Out-Null

& "$PSScriptRoot\Capture-Trace32.ps1" -OutFile $OutFile
Write-Host "[callstack] Call stack window captured to $OutFile. View the image to read the frame chain."
