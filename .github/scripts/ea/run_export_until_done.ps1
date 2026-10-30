param(
    [int]$MaxAttempts = 20,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs = @()
)

# Retry-loop driver for export_sequence_diagrams.py. EA's COM automation
# server can crash the whole process silently and unpredictably partway
# through a full-model export (see README.md "EA COM instability"). This
# driver just re-invokes the script - which resumes via its own
# `_export_manifest.json` checkpoint - until every discovered diagram has
# been exported or progress stalls.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File run_export_until_done.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File run_export_until_done.ps1 --scope SwSubSys_TouchCtl
#   powershell -NoProfile -ExecutionPolicy Bypass -File run_export_until_done.ps1 -MaxAttempts 30 --fresh

$ea = $PSScriptRoot
$py = Join-Path $ea ".venv32\Scripts\python.exe"
$script = Join-Path $ea "export_sequence_diagrams.py"
$outDir = Join-Path (Split-Path (Split-Path (Split-Path $ea -Parent) -Parent) -Parent) "ai_output\arch_design\diagrams"
$manifest = Join-Path $outDir "_export_manifest.json"

function Get-ManifestCount {
    if (-not (Test-Path $manifest)) { return 0 }
    $n = & $py -c "import json,sys; print(len(json.load(open(sys.argv[1]))))" $manifest 2>$null
    if (-not $n) { return 0 }
    return [int]$n
}

# Discovered/target diagram count is parsed from the script's own log output
# (`[info] Found N sequence diagram(s)...` or, with --scope, the
# `--scope '...' matched M of N` line) rather than hardcoded, so this driver
# stays correct regardless of --scope or model changes.
function Get-TargetCount([string]$logPath) {
    $content = Get-Content -Path $logPath -Encoding Unicode -Raw -ErrorAction SilentlyContinue
    if (-not $content) { return -1 }
    $m = [regex]::Match($content, "matched (\d+) of \d+")
    if ($m.Success) { return [int]$m.Groups[1].Value }
    $m = [regex]::Match($content, "Found (\d+) sequence diagram")
    if ($m.Success) { return [int]$m.Groups[1].Value }
    return -1
}

$prevCount = -1
$target = -1
$count = 0

for ($i = 1; $i -le $MaxAttempts; $i++) {
    $log = Join-Path $ea "run_$i.log"
    Write-Output "=== Attempt $i ==="
    & $py -u $script @ExtraArgs *> $log
    $exit = $LASTEXITCODE
    Write-Output "  exit code: $exit"

    if ($target -lt 0) {
        $target = Get-TargetCount $log
    }
    $count = Get-ManifestCount
    Write-Output "  manifest count: $count / $target"

    if ($target -ge 0 -and $count -ge $target) {
        Write-Output "DONE_ALL_EXPORTED"
        break
    }
    if ($count -eq $prevCount) {
        Write-Output "STUCK_NO_PROGRESS"
        break
    }
    $prevCount = $count
}
Write-Output "FINAL_MANIFEST_COUNT=$count / $target"
