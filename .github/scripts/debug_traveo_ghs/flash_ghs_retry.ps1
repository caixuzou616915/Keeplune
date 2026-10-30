# flash_ghs_retry.ps1 — Resilient GHS Multi flash for TVII ECUs (auto cleanup + retry)
#
# WHY: `run.py <variant> flash_ghs` drives the GHS probe via mpserv. On this bench the
# probe intermittently returns "Memory write failed at 0x100000aa" / "Could not detect a
# flash device at 0x10000000" / "another application already connected" - a KNOWN transient
# hardware/USB glitch (see repo memory) that succeeds within 1-3 retries once mpserv/multi are
# killed and the probe is allowed to settle. A single-shot flash therefore looks "broken" even
# though the tooling is correct. This wrapper kills stale probe holders, settles, and retries.
#
# It is project-agnostic: pass the variant and (optionally) the repo root. The flash command,
# git-bash, econ sourcing and success/failure detection are all handled here.
#
# USAGE:
#   .\flash_ghs_retry.ps1 -Variant tviib_e4m_aravalli_s3p.Debug
#   .\flash_ghs_retry.ps1 -Variant tviic_6m_endprod.Debug -MaxRetries 5
#   .\flash_ghs_retry.ps1 -Variant tviib_e4m_aravalli_s3p.Debug -Repo C:\Project\JB\s3p\sw.sys.tv2.meta-repo-ux
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Variant,                 # e.g. tviib_e4m_aravalli_s3p.Debug
    [string]$Repo,                    # repo root; auto-detected from CWD upward if omitted
    [int]$MaxRetries = 3,             # attempts before giving up
    [int]$SettleSeconds = 6           # wait after killing mpserv/multi, before each attempt
)

$ErrorActionPreference = 'Stop'

# --- Resolve git bash (this machine: C:\Program Files\Git; fallback D:\Tool\Common\Git) ---
$gitBash = @(
    "C:\Program Files\Git\bin\bash.exe",
    "D:\Tool\Common\Git\bin\bash.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $gitBash) { throw "git bash not found (needs realpath). Install Git for Windows." }

# --- Resolve repo root (must contain run.py + econ_config.sh) ---
if (-not $Repo) {
    $dir = (Get-Location).Path
    while ($dir -and -not ((Test-Path "$dir\run.py") -and (Test-Path "$dir\econ_config.sh"))) {
        $parent = Split-Path $dir -Parent
        if ($parent -eq $dir) { $dir = $null; break }
        $dir = $parent
    }
    $Repo = $dir
}
if (-not $Repo -or -not (Test-Path "$Repo\run.py") -or -not (Test-Path "$Repo\econ_config.sh")) {
    throw "Repo root with run.py + econ_config.sh not found. Pass -Repo explicitly."
}
$bRoot = '/' + $Repo.Substring(0,1).ToLower() + $Repo.Substring(2).Replace('\','/')
Write-Host "[flash] repo=$Repo  variant=$Variant  maxRetries=$MaxRetries" -ForegroundColor Cyan

# Transient probe/target errors that WARRANT a retry (vs a real config/toolchain error)
$transientPattern = 'Could not detect a flash device|Memory write failed|already connected|Unexpected ack|target ignored halt|trg_run\(\) failed'

$logDir = Join-Path $env:TEMP "tvii_flash"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$safeVar = ($Variant -replace '[^\w.-]', '_')

for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
    Write-Host "[flash] attempt $attempt/$MaxRetries - clearing stale probe holders..." -ForegroundColor Yellow
    Stop-Process -Name "multi","mpserv","mpserv64","gmpserv" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds $SettleSeconds

    $log = Join-Path $logDir ("flash_" + $safeVar + "_try" + $attempt + ".log")
    $bashCmd = "cd $bRoot && source econ_config.sh && ./run.py $Variant flash_ghs 2>&1"
    Write-Host "[flash] running: run.py $Variant flash_ghs" -ForegroundColor Gray

    # econ_config.sh / git write progress (e.g. "Reset branch 'release/2.11'") to stderr.
    # Under $ErrorActionPreference='Stop' a native stderr line raises NativeCommandError and
    # aborts the wrapper even though the flash itself is fine. Relax it just for this call.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try   { $output = & $gitBash -c $bashCmd 2>&1 }
    finally { $ErrorActionPreference = $prevEap }
    $output | Tee-Object -FilePath $log | Out-Null

    # Success = run.py status summary shows the flash action as OK
    $ok = $output | Select-String -Pattern "flash_ghs\s+[\d.]+s\s+OK" -Quiet
    if ($ok) {
        Write-Host "[flash] SUCCESS on attempt $attempt (log: $log)" -ForegroundColor Green
        exit 0
    }

    $isTransient = $output | Select-String -Pattern $transientPattern -Quiet
    if ($isTransient) {
        Write-Warning "[flash] attempt $attempt hit a transient probe/target error - will retry."
        continue
    }

    # Non-transient failure (config/toolchain/build) - retrying won't help; surface it.
    Write-Error "[flash] attempt $attempt failed with a NON-transient error. See $log"
    $output | Select-String -Pattern "ERROR|error|failed|does not exist|not connected" |
        Select-Object -Last 15 | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    exit 1
}

Write-Error "[flash] FAILED after $MaxRetries attempts - all transient probe/target glitches. Check the GHS probe USB cable and target power (KL15), then re-run."
exit 2
