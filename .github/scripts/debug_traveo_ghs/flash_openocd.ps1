#!/usr/bin/env pwsh
# TVII ECU Flash via OpenOCD/KitProg3 (fallback when GHS probe unavailable, portable/auto-detects project root)

Stop-Process -Name "multi","mpserv" -Force -ErrorAction SilentlyContinue

# Detect TVII build repo
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
$bRoot = '/' + $projectRoot.Substring(0,1).ToLower() + $projectRoot.Substring(2).Replace('\','/')

$openocd  = '"C:/Program Files (x86)/Infineon/Auto Flash Utility 1.4/bin/openocd.exe"'
$scripts  = '"C:/Program Files (x86)/Infineon/Auto Flash Utility 1.4/scripts"'
$sflash   = "$bRoot/pkg/hsm/cm0plus_fw/generic/sflash_single_bank_6m.srec"
$hsm      = "$bRoot/pkg/hsm/cm0plus_fw/generic/hsm_she_ext_6m.s19"
$fbl      = "$bRoot/build/tviic_6m_fbl.Debug/bin/tviic_6m_fbl.s19"
$app      = "$bRoot/build/tviic_6m_endprod.Debug/bin/tviic_6m_endprod.s19"
$app2     = "$bRoot/build/tviic_6m_endprod_second.Debug/bin/tviic_6m_endprod_second.s19"

$cmd = "$openocd -s $scripts " +
       "-f interface/kitprog3.cfg " +
       "-f target/traveo2_6m.cfg " +
       '-c "init; reset init; flash erase_sector traveo2_6m_work_cm0 0 last; ' +
       "traveo2 sflash_restrictions 3; program $sflash verify; " +
       "program $hsm verify; " +
       "program $fbl verify; " +
       "program $app verify; " +
       "program $app2 verify; " +
       'exit"'

$output = Invoke-Expression "& $cmd 2>&1"
Write-Host $output
$verifyCount = ($output | Select-String "Verified OK").Count
Write-Host "Verified: $verifyCount/5 files"
if ($verifyCount -lt 5) { Write-Warning "Not all files verified! Check binary paths." }
