# Export every slide of a .pptx to PNG via PowerPoint COM, for visual QA.
# Usage: powershell -File render_pptx.ps1 -Pptx deck.pptx [-OutDir qa] [-Width 1600]
param(
    [Parameter(Mandatory = $true)][string]$Pptx,
    [string]$OutDir,
    [int]$Width = 1600
)

$ErrorActionPreference = 'Stop'
$Pptx = (Resolve-Path $Pptx).Path
if (-not $OutDir) { $OutDir = Join-Path (Split-Path $Pptx) 'qa' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path
Get-ChildItem $OutDir -Filter 'slide-*.png' -ErrorAction SilentlyContinue | Remove-Item -Force

$ppt = $null; $pres = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    # ReadOnly, Untitled=false, WithWindow=false
    $pres = $ppt.Presentations.Open($Pptx, $true, $false, $false)
    $height = [int]($Width * $pres.PageSetup.SlideHeight / $pres.PageSetup.SlideWidth)
    for ($i = 1; $i -le $pres.Slides.Count; $i++) {
        $out = Join-Path $OutDir ("slide-{0:D2}.png" -f $i)
        $pres.Slides.Item($i).Export($out, 'PNG', $Width, $height)
        Write-Host "wrote $out"
    }
}
finally {
    if ($pres) { $pres.Close() | Out-Null; [void][Runtime.InteropServices.Marshal]::ReleaseComObject($pres) }
    if ($ppt) { $ppt.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) }
}
