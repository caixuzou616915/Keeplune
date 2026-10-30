# =============================================================================
# config.ps1 - Shared configuration & helpers for Lauterbach TRACE32 automation
# Target: any Traveo II (or similar) variant debugged with Lauterbach TRACE32.
#
# This file is PROJECT-AGNOSTIC. The variant name, chip/core names and window
# titles are NOT hardcoded here - they must be supplied per-project via
# environment variables (set them once per shell session before running any
# of the scripts in this folder):
#
#   $env:LT_VARIANT         (REQUIRED) build variant name, e.g. 'tviib_2m_aravalli_s3p'
#   $env:LT_VARIANT_CONFIG  (optional) build config, default 'Debug'
#   $env:LT_MASTER_TITLE    (optional) wildcard match for the master core window
#                            title, e.g. '*CM0+*MASTER*'. Default: '*MASTER*'
#   $env:LT_SLAVE_TITLE     (optional) wildcard match for the application core
#                            window title, e.g. '*CM4*SLAVE1*'. Default: '*SLAVE*'
#   $env:LT_STARTUP_SCRIPT  (optional) path (relative to repo root, or absolute)
#                            to the PRACTICE startup/flash script (*.cmm). If
#                            unset, auto-discovered as the single *.cmm file
#                            directly under app/variants/<variant>/source/Lauterbach_scripts
#                            (excluding the 'actions' subfolder).
#   $env:LT_ABS_FILE        (optional) path to the app ELF (*.abs). If unset,
#                            derived as build/<variant>.<config>/bin/<variant>.abs
#
# Example (bench-verified project - see SKILL.md "Worked example"):
#   $env:LT_VARIANT      = 'tviib_2m_aravalli_s3p'
#   $env:LT_MASTER_TITLE = 'TRACE32 for ARM - CYT2B93CAS-CM0+ - MASTER'
#   $env:LT_SLAVE_TITLE  = 'TRACE32 for ARM -CYT2B93CAS-CM4 - SLAVE1'
#
# Dot-source this at the top of every other script:
#     . "$PSScriptRoot\config.ps1"
#
# Nothing here is machine-specific-hardcoded: the TRACE32 path (conan short hash)
# and the repo root are auto-detected at runtime.
# =============================================================================

$ErrorActionPreference = 'Stop'

# --- Target identifiers - supplied by the caller, not hardcoded -------------
if (-not $env:LT_VARIANT) {
    throw ('LT_VARIANT is not set. Example: $env:LT_VARIANT = ''tviib_2m_aravalli_s3p'' ' +
           '(replace with YOUR project''s variant name) before running these scripts. See SKILL.md.')
}
$Global:LT_Variant       = $env:LT_VARIANT
$Global:LT_VariantConfig = if ($env:LT_VARIANT_CONFIG) { $env:LT_VARIANT_CONFIG } else { 'Debug' }
$Global:LT_VariantLabel  = "$LT_Variant.$LT_VariantConfig"
$Global:LT_MasterTitle   = if ($env:LT_MASTER_TITLE) { $env:LT_MASTER_TITLE } else { '*MASTER*' }
$Global:LT_SlaveTitle    = if ($env:LT_SLAVE_TITLE)  { $env:LT_SLAVE_TITLE }  else { '*SLAVE*' }
$Global:LT_GitBash       = 'C:\Program Files\Git\bin\bash.exe'

# --- Locate the repository root --------------------------------------------
# Walk up from this script until we find run.py + econ_config.sh.
function Find-RepoRoot {
    $dir = Split-Path -Parent $PSScriptRoot          # .github/scripts
    while ($dir) {
        if ((Test-Path (Join-Path $dir 'run.py')) -and
            (Test-Path (Join-Path $dir 'econ_config.sh'))) {
            return $dir
        }
        $parent = Split-Path -Parent $dir
        if ($parent -eq $dir) { break }
        $dir = $parent
    }
    throw "Repo root not found (expected run.py + econ_config.sh above $PSScriptRoot)."
}

$Global:LT_RepoRoot = Find-RepoRoot
$Global:LT_BuildDir = Join-Path $LT_RepoRoot ("build\{0}" -f $LT_VariantLabel)

# --- Startup (flash) script - auto-discovered unless LT_STARTUP_SCRIPT is set
# The filename itself is chip/BSP-specific (e.g. cyt2bl_flash_2M.cmm) so it
# cannot be derived from the variant name alone; find the one *.cmm directly
# under .../Lauterbach_scripts (not inside its 'actions' subfolder).
function Find-StartupScript {
    if ($env:LT_STARTUP_SCRIPT) {
        $p = $env:LT_STARTUP_SCRIPT
        if (-not [System.IO.Path]::IsPathRooted($p)) { $p = Join-Path $LT_RepoRoot $p }
        return $p
    }
    $scriptsDir = Join-Path $LT_RepoRoot ("app\variants\{0}\source\Lauterbach_scripts" -f $LT_Variant)
    if (-not (Test-Path $scriptsDir)) { return $null }
    $hit = Get-ChildItem $scriptsDir -Filter '*.cmm' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}

$Global:LT_StartupScript = Find-StartupScript
$Global:LT_AbsFile = if ($env:LT_ABS_FILE) {
    if ([System.IO.Path]::IsPathRooted($env:LT_ABS_FILE)) { $env:LT_ABS_FILE } else { Join-Path $LT_RepoRoot $env:LT_ABS_FILE }
} else {
    Join-Path $LT_BuildDir ("bin\{0}.abs" -f $LT_Variant)
}

# --- Locate t32marm.exe and derive P4_SYS ----------------------------------
# 1) Prefer the path of an already-running t32marm process.
# 2) Otherwise search D:\.conan\short\*\bin\windows64\t32marm.exe (and C:).
function Find-Trace32Exe {
    $proc = Get-Process t32marm -ErrorAction SilentlyContinue |
            Where-Object { $_.Path } | Select-Object -First 1
    if ($proc) { return $proc.Path }

    foreach ($drive in @('D', 'C', 'E')) {
        $root = "${drive}:\.conan\short"
        if (Test-Path $root) {
            $hit = Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
                   ForEach-Object { Join-Path $_.FullName '1\bin\windows64\t32marm.exe' } |
                   Where-Object { Test-Path $_ } | Select-Object -First 1
            if ($hit) { return $hit }
        }
    }
    throw "t32marm.exe not found. Start a debug session once, or check D:\.conan\short\*\bin\windows64\."
}

$Global:LT_Trace32Exe = Find-Trace32Exe
# P4_SYS = the '...\1' system dir (parent of bin\windows64)
$Global:LT_P4_SYS = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $LT_Trace32Exe))

Write-Host "[config] Repo root : $LT_RepoRoot"
Write-Host "[config] Build dir : $LT_BuildDir"
Write-Host "[config] t32marm   : $LT_Trace32Exe"
Write-Host "[config] P4_SYS    : $LT_P4_SYS"

# --- Window helpers ---------------------------------------------------------
# Uses $LT_SlaveTitle / $LT_MasterTitle (from LT_SLAVE_TITLE / LT_MASTER_TITLE,
# or the generic '*SLAVE*' / '*MASTER*' defaults) so these are never hardcoded
# to a specific chip/core name here.
function Get-SlaveProcess {
    Get-Process t32marm -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like $LT_SlaveTitle } | Select-Object -First 1
}

function Get-MasterProcess {
    Get-Process t32marm -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like $LT_MasterTitle } | Select-Object -First 1
}

function Test-Trace32Running {
    [bool](Get-Process t32marm -ErrorAction SilentlyContinue)
}

# --- Robust window/dialog detection -----------------------------------------
# Get-Process's MainWindowTitle only reports ONE window per process (whichever
# the .NET runtime happens to expose as "main"). When t32marm opens with a
# blocking error dialog (e.g. PODBUS "device already used by other GUI"), that
# dialog is a SEPARATE top-level window with the SAME generic "TRACE32
# PowerView" title as the blank host window behind it - MainWindowTitle can
# silently pick the blank one, hiding the real error. Use EnumWindows to see
# every visible top-level window per PID and check their actual text content.
if (-not ('Trace32WinEnum' -as [type])) {
    Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Collections.Generic;
public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
public class Trace32WinEnum {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    public static List<IntPtr> GetTopWindows(uint pid) {
        var result = new List<IntPtr>();
        EnumWindows((hWnd, lParam) => {
            uint windowPid;
            GetWindowThreadProcessId(hWnd, out windowPid);
            if (windowPid == pid && IsWindowVisible(hWnd)) { result.Add(hWnd); }
            return true;
        }, IntPtr.Zero);
        return result;
    }
    public static string GetText(IntPtr hWnd) {
        int len = GetWindowTextLength(hWnd);
        var sb = new StringBuilder(len + 1);
        GetWindowText(hWnd, sb, sb.Capacity);
        return sb.ToString();
    }
}
"@
}

# --- Auto-restore a minimized window (bench-verified 2026-07-15) -----------
# ROOT CAUSE FOUND: TRACE32 windows can silently end up MINIMIZED (Windows
# reports minimized windows at position -32000,-32000 via GetWindowRect - a
# well-known sentinel). While minimized, the command line shows a red
# "command locked" status and SILENTLY DROPS every keystroke sent via
# Send-OneCommand - no error, just a blank-looking window and commands that
# appear to have no effect (e.g. Break.Delete/Break.Set/Go never take effect,
# a capture looks totally blank). Call this before sending any keystrokes AND
# before capturing a screenshot, so this failure mode can't happen silently.
function Restore-Trace32WindowIfMinimized {
    param([Parameter(Mandatory)] [IntPtr] $Hwnd)
    $rect = New-Object RECT
    [Trace32WinEnum]::GetWindowRect($Hwnd, [ref]$rect) | Out-Null
    if ($rect.Left -le -30000 -or $rect.Top -le -30000) {
        Write-Host "[config] Window was minimized (rect $($rect.Left),$($rect.Top)) - restoring."
        [Trace32WinEnum]::ShowWindow($Hwnd, 9)  | Out-Null   # SW_RESTORE
        [Trace32WinEnum]::ShowWindow($Hwnd, 1)  | Out-Null   # SW_SHOWNORMAL
        Start-Sleep -Milliseconds 400
    }
}

# --- Dismiss the "Welcome to TRACE32!" onboarding dialog (bench-verified 2026-08-12) ------
# ROOT CAUSE FOUND: this modal appears on EVERY fresh MASTER/SLAVE launch - even when its own
# "Show this dialog at start" checkbox is already UNCHECKED - because each launch gets a fresh
# temp AMP profile/config dir, so TRACE32 never "remembers" the preference across launches.
# It is a PURELY VISUAL overlay: the underlying PRACTICE/flash script keeps running underneath
# it (confirmed via the native `run.py <variant>.<config> debug_trace32` action: CPU/flash
# configuration succeeded while the dialog was still on-screen). The real damage is indirect:
# while this modal owns focus, keystrokes sent by Send-OneCommand's ESC/Ctrl+A/Backspace/paste
# sequence can be swallowed or misdirected into the modal instead of the command line, which
# previously produced a misleading "syntax error" on the next real command (it looked like a
# genuine SYStem.CPU/device-support problem but wasn't - see SKILL.md history). Only a plain
# ESC via AppActivate+SendKeys reliably dismisses it - WM_CLOSE-by-window-title and simulated
# mouse clicks on its visible X were BOTH tried and proved unreliable (a mouse click even
# mis-landed and toggled the checkbox instead, due to a DPI/logical-vs-physical coordinate
# mismatch between PrintWindow-captured pixels and screen coordinates). Call this once right
# after every launch (Start-Trace32.ps1) and defensively before every Send-OneCommand, so a
# stray relaunch of this dialog never corrupts the next automated command.
function Dismiss-Trace32WelcomeDialog {
    param([Parameter(Mandatory)] $Process)
    $found = $false
    foreach ($hWnd in [Trace32WinEnum]::GetTopWindows([uint32]$Process.Id)) {
        $title = [Trace32WinEnum]::GetText($hWnd)
        if ($title -like '*Welcome to TRACE32*') { $found = $true }
    }
    if (-not $found) { return $false }
    Write-Host "[config] 'Welcome to TRACE32!' dialog detected on PID $($Process.Id) - dismissing via ESC."
    $wshell = New-Object -ComObject WScript.Shell
    if (-not $wshell.AppActivate([int]$Process.Id)) { Start-Sleep -Milliseconds 300; $wshell.AppActivate([int]$Process.Id) | Out-Null }
    Start-Sleep -Milliseconds 300
    $wshell.SendKeys('{ESC}')
    Start-Sleep -Milliseconds 600
    return $true
}

# --- Graceful shutdown -------------------------------------------------------
# CONFIRMED ROOT CAUSE (2026-07-14, via official Lauterbach guidance -
# https://stackoverflow.com/a/48460326): force-killing t32marm (TerminateProcess,
# i.e. Stop-Process -Force) is EXACTLY what the vendor docs list as a cause of
# the "device already used by other GUI" PODBUS lock on the NEXT launch
# ("you've started TRACE32 after the process was killed - process removed from
# execution without properly closing the application"). Every prior kill/relaunch
# cycle in this repo's automation used Stop-Process -Force, which is the likely
# self-inflicted cause of the repeated lock dialog seen throughout this session.
# Sends WM_CLOSE (0x0010) to every visible top-level t32marm window - the same
# signal a real user clicking the window's X sends - so TRACE32 releases the
# PowerDebug/probe connection cleanly before exiting. Falls back to Stop-Process
# -Force only if processes are still alive after the timeout.
#
# NOTE: a t32rem-based "InterCom M4 QUIT"/"QUIT" clean-quit (the protocol-level
# equivalent of the Python RCL library's `dbg.cmd("Quit"); dbg.disconnect()`
# pattern in sw.tool.robot-gen-library's python/Debugger/Lauterbach.py) was
# tried here too, but it requires the session to have been launched with the
# remote API enabled (RCL=NETASSIST) - confirmed 2026-07-14 that this is NOT
# viable for this variant's AMP flow (see Start-Trace32.ps1), so remote API is
# never enabled and that path was removed. WM_CLOSE is the only graceful method.
function Close-Trace32Gracefully {
    param([int] $TimeoutSeconds = 6)

    $WM_CLOSE = 0x0010
    $hadAny = $false
    foreach ($hwnd in (Get-Trace32TopWindows)) {
        $hadAny = $true
        [Trace32WinEnum]::PostMessage([IntPtr]$hwnd, $WM_CLOSE, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
    }
    if (-not $hadAny) { return }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline -and (Get-Process t32marm -ErrorAction SilentlyContinue)) {
        Start-Sleep -Milliseconds 300
    }
    $stillRunning = Get-Process t32marm -ErrorAction SilentlyContinue
    if ($stillRunning) {
        Write-Warning "[config] Graceful WM_CLOSE did not fully close TRACE32 within ${TimeoutSeconds}s - force-killing as last resort."
        Stop-Process -Name t32marm,t32marm64,t32rem,t32start,t32mciserver,t32tcpusb -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    } else {
        Write-Host "[config] TRACE32 closed gracefully (WM_CLOSE) - PowerDebug connection released cleanly."
    }
}

# Returns every visible top-level HWND (as [long]) for all running t32marm processes.
function Get-Trace32TopWindows {
    $handles = @()
    foreach ($p in (Get-Process t32marm -ErrorAction SilentlyContinue)) {
        foreach ($h in [Trace32WinEnum]::GetTopWindows([uint32]$p.Id)) { $handles += $h }
    }
    return $handles
}

# Checks all t32marm top-level windows for the PODBUS "already used by other
# GUI" fatal dialog by screenshotting each one (via the proven PrintWindow
# technique - see Capture-Trace32.ps1) and OCR is NOT used here since it's
# unverified; instead this saves one PNG per window so a human/agent can look.
# Returns the list of saved file paths (empty if only 0-1 windows exist).
function Save-Trace32DiagnosticScreenshots {
    param([string] $OutDir = (Join-Path $LT_RepoRoot 'ai_output\debug'))
    if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
    Add-Type -AssemblyName System.Drawing -ErrorAction SilentlyContinue
    $saved = @()
    $i = 0
    foreach ($hwnd in (Get-Trace32TopWindows)) {
        $i++
        $rect = New-Object RECT
        [Trace32WinEnum]::GetClientRect([IntPtr]$hwnd, [ref]$rect) | Out-Null
        $w = $rect.Right - $rect.Left; $h = $rect.Bottom - $rect.Top
        if ($w -le 0 -or $h -le 0) { continue }
        $path = Join-Path $OutDir ("diag_win{0}_{1:yyyyMMdd_HHmmss}.png" -f $i, (Get-Date))
        try {
            $bmp = New-Object System.Drawing.Bitmap $w, $h
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $hdc = $g.GetHdc()
            [Trace32WinEnum]::PrintWindow([IntPtr]$hwnd, $hdc, 2) | Out-Null
            $g.ReleaseHdc($hdc)
            $bmp.Save($path)
            $g.Dispose(); $bmp.Dispose()
            $saved += $path
        } catch { }
    }
    return $saved
}

# --- Focus + one-command-at-a-time sender ----------------------------------
# Sends a single TRACE32 command into the given process' command line.
# Clears the line first (ESC, Ctrl+A, Backspace) so nothing gets concatenated.
function Send-OneCommand {
    param(
        [Parameter(Mandatory)] $Process,
        [Parameter(Mandatory)] [string] $Command,
        [int] $SettleMs = 900
    )
    Restore-Trace32WindowIfMinimized -Hwnd $Process.MainWindowHandle
    Dismiss-Trace32WelcomeDialog -Process $Process | Out-Null
    $wshell = New-Object -ComObject WScript.Shell
    if (-not $wshell.AppActivate([int]$Process.Id)) {
        Start-Sleep -Milliseconds 300
        $wshell.AppActivate([int]$Process.Id) | Out-Null
    }
    Start-Sleep -Milliseconds 300
    $wshell.SendKeys('{ESC}');        Start-Sleep -Milliseconds 200
    $wshell.SendKeys('^a');           Start-Sleep -Milliseconds 100
    $wshell.SendKeys('{BACKSPACE}');  Start-Sleep -Milliseconds 200
    Set-Clipboard -Value $Command
    $wshell.SendKeys('^v');           Start-Sleep -Milliseconds 250
    $wshell.SendKeys('~')             # Enter
    Write-Host "  [t32] $Command"
    Start-Sleep -Milliseconds $SettleMs
}

# Convenience: send a list of commands to the application-core slave, one at a time.
function Send-SlaveCommands {
    param(
        [Parameter(Mandatory)] [string[]] $Commands,
        [int] $SettleMs = 900
    )
    $slave = Get-SlaveProcess
    if (-not $slave) { throw "Application-core SLAVE window not found (pattern '$LT_SlaveTitle'). Run Start-Trace32.ps1 first." }
    foreach ($c in $Commands) { Send-OneCommand -Process $slave -Command $c -SettleMs $SettleMs }
    return $slave
}
