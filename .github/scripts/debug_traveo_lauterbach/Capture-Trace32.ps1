# =============================================================================
# Capture-Trace32.ps1 - Screenshot the application-core SLAVE window for verification/evidence.
#
# Brings the slave window to the foreground, then captures the primary screen to
# a PNG. Relative -OutFile values are written under <repoRoot>\ai_output\debug\
# (created if missing); pass a rooted/absolute path to save elsewhere.
#
# Usage:
#   .\Capture-Trace32.ps1
#   .\Capture-Trace32.ps1 -OutFile bp_evidence.png
# =============================================================================
param(
    [string] $OutFile
)

. "$PSScriptRoot\config.ps1"

$slave = Get-SlaveProcess
if (-not $slave) { throw "Application-core SLAVE window not found (pattern '$LT_SlaveTitle'). Run Start-Trace32.ps1 first." }

# Auto-restore if minimized (bench-verified 2026-07-15) - a minimized window
# captures as blank AND silently drops keystrokes ("command locked") - see
# Restore-Trace32WindowIfMinimized in config.ps1 for details.
Restore-Trace32WindowIfMinimized -Hwnd $slave.MainWindowHandle

if (-not $OutFile) { $OutFile = "trace32_slave_{0:yyyyMMdd_HHmmss}.png" -f (Get-Date) }
if (-not [System.IO.Path]::IsPathRooted($OutFile)) {
    $debugDir = Join-Path $LT_RepoRoot 'ai_output\debug'
    if (-not (Test-Path $debugDir)) { New-Item -ItemType Directory -Path $debugDir -Force | Out-Null }
    $OutFile = Join-Path $debugDir $OutFile
}

# NOTE: WScript.Shell AppActivate() can return True yet NOT actually raise the
# window - Windows' foreground-lock restriction silently blocks activation when
# it isn't triggered by a real interactive user keystroke (e.g. called from an
# automated script). That caused CopyFromScreen() to capture whatever window
# genuinely had focus (VS Code) instead of TRACE32. Fix: capture directly from
# the window handle via PrintWindow, which works regardless of z-order/focus.
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Trace32CaptureNative {
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@

$hwnd = $slave.MainWindowHandle
$rect = New-Object Trace32CaptureNative+RECT
[Trace32CaptureNative]::GetClientRect($hwnd, [ref]$rect) | Out-Null
$width  = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
if ($width -le 0 -or $height -le 0) { throw "CM4 SLAVE1 window has invalid/minimized dimensions ($width x $height)." }

$bmp      = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$hdc      = $graphics.GetHdc()
# PW_RENDERFULLCONTENT = 2 (needed for modern/layered/GPU-composited windows)
$ok = [Trace32CaptureNative]::PrintWindow($hwnd, $hdc, 2)
$graphics.ReleaseHdc($hdc)
if (-not $ok) { Write-Warning "[capture] PrintWindow returned false - image may be blank." }
$bmp.Save($OutFile, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose(); $bmp.Dispose()

Write-Host "[capture] Saved $OutFile"
Write-Output $OutFile
