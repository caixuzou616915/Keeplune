# setup.ps1 — Flash TVII ECU and bring system to running state (portable, auto-detects project root)
# CRITICAL: econ_config.sh reads stdin — always use single-line -c "..." with && chaining
param(
    [switch]$SkipCANoe,
    [switch]$SkipFlash
)

# Detect TVII build repo (first *:\Work\** folder with run.py + econ_config.sh + app\variants\tviic_6m_endprod)
$projectRoot = [IO.DriveInfo]::GetDrives() |
    Where-Object { $_.IsReady -and $_.DriveType -eq 'Fixed' } |
    ForEach-Object { Get-ChildItem "$($_.Name)Work" -Directory -ErrorAction SilentlyContinue |
                     Get-ChildItem -Directory -ErrorAction SilentlyContinue } |
    Where-Object {
        (Test-Path "$($_.FullName)\run.py") -and
        (Test-Path "$($_.FullName)\econ_config.sh") -and
        (Test-Path "$($_.FullName)\app\variants\tviic_6m_endprod") -and
        (Test-Path "$($_.FullName)\Start-CANoe.ps1")   # disambiguates from other TVII repos
    } |
    Select-Object -First 1 -ExpandProperty FullName
if (-not $projectRoot) { throw "No TVII build repo found" }
Write-Host "[OK] TVII repo: $projectRoot"

$bRoot    = '/' + $projectRoot.Substring(0,1).ToLower() + $projectRoot.Substring(2).Replace('\','/')
$buildDir = "$projectRoot\build\tviic_6m_endprod.Debug"
# git bash MUST have realpath (Git for Windows); msys bash loops in econ_config.sh.
# Prefer C:\Program Files\Git; fall back to D:\Tool\Common\Git if that's where it lives.
$gitBash  = @("C:\Program Files\Git\bin\bash.exe","D:\Tool\Common\Git\bin\bash.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $gitBash) { throw "git bash not found (needs realpath). Install Git for Windows." }
$multiExe = "D:/.conan/short/bceabf/1/_ide/multi"
$envCmd   = "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/bceabf/1:/d/.conan/short/bceabf/1/_ide:`$PATH'"

# 1. CANoe
if (-not $SkipCANoe) {
    Write-Host "[1/3] Starting CANoe..."
    & "$projectRoot\Start-CANoe.ps1"
    Write-Host "[1/3] CANoe started."
}

# 2. Flash — separate bash call required (econ_config.sh reads stdin)
if (-not $SkipFlash) {
    Write-Host "[2/3] Flashing ECU (flash_ghs)..."
    Stop-Process -Name "multi","mpserv" -Force -ErrorAction SilentlyContinue
    & $gitBash -c "cd $bRoot && source econ_config.sh && ./run.py tviic_6m_endprod.Debug flash_ghs 2>&1"
    Write-Host "[2/3] Flash complete."
}

# 3. System running — VERIFY (non-blocking in GRTL) + wait 90s + target gc
Write-Host "[3/3] Starting GHS Multi + VERIFY + target gc..."
Stop-Process -Name "multi","mpserv" -Force -ErrorAction SilentlyContinue
Set-Content "$buildDir\autorun.rc" "wait -time 3000`npython -b -f ../../app/variants/tviic_6m_endprod/debug/tvii_debug_6mb.py VERIFY`nwait -time 90000`ntarget gc" -Encoding ASCII
Start-Process $gitBash -ArgumentList "-c", "$envCmd; cd $bRoot/build/tviic_6m_endprod.Debug && $multiExe -nosplash -servertimeout 120 debug.ghsmc -p autorun.rc" -NoNewWindow
Write-Host "[OK] GHS Multi launched. VERIFY running — system running in ~100s."
