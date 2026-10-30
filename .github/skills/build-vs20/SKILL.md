---
name: build-vs20
description: >-
  Full VS20 repository build sequence for the Traveo II tviic_6m platform: checkout,
  environment setup, and building all targets (FLU, FBL, second core, endprod) in
  dependency order via Git Bash. Use when: running a full clean VS20 build; building
  individual targets in the correct order; troubleshooting build script failures;
  performing an incremental rebuild after a fix.
argument-hint: 'Build endprod | Build all (FLU + FBL + second + endprod) | Build endprod incremental only'
metadata:
  author: "Goh Eng Fook"
  version: "1.0.0"
---

# build-vs20

Full VS20 repository build sequence for the Traveo II tviic_6m platform.  
Performs checkout (if needed), environment setup, and builds all targets in dependency order.

## Build Sequence

The VS20 full build follows this exact order:

```
1. ./checkout.sh          (only if needed — new workspace or manifest changed)
2. source econ_config.sh  (sets up CMB build environment)
3. ./zz_build_tviic_6m_flu.sh          (Flash Updater)
4. ./zz_build_tviic_6m_fbl.sh          (Bootloader)
5. ./zz_build_tviic_6m_endprod_second.sh  (Second core — CM7_1)
6. ./zz_build_tviic_6m_endprod.sh      (Main application — CM7_0)
```

**Dependency order rationale:**  
- FLU must be built first (no dependencies on others).
- FBL depends on FLU artifacts being present.
- endprod_second must be built before endprod (endprod links against second core binary).
- endprod is built last as the top-level application.

## Prerequisites

- **Git Bash**: `D:\Tool\Common\Git\bin\bash.exe` — **ALL build commands MUST run via this bash.exe. Running scripts directly in PowerShell or CMD will FAIL** (econ_config.sh requires `realpath` and other bash builtins)
- **Project root detected**: folder with `run.py` + `econ_config.sh` + `app/variants/tviic_6m_endprod`
- **Network access**: only needed if `./checkout.sh` is required (git clone/fetch)

## ⚠️ CRITICAL RULE: ALL Commands Must Run in Bash

**Every build command — without exception — must be executed inside `D:\Tool\Common\Git\bin\bash.exe`.**

`econ_config.sh` sets up the CMB environment and requires bash features (`realpath`, `source`, arrays).  
Running `.sh` scripts in PowerShell or CMD directly will silently fail or produce wrong results.

**Correct** — all commands via bash wrapper or `bash.exe -c`:
```bash
# Inside bash wrapper script:
source econ_config.sh
./zz_build_tviic_6m_flu.sh
```

**Wrong** — never call build scripts from PowerShell directly:
```powershell
# WRONG — do not do this:
.\zz_build_tviic_6m_flu.sh
```

## Checkout Decision

Run `./checkout.sh` ONLY when:
- The workspace is freshly cloned (no `pkg/` subdirectories present)
- The user explicitly requests checkout
- The `default.xml` manifest was updated and submodules need syncing

Skip checkout if `pkg/` directories already exist and user didn't request it.

## Execution — Use the Bash Wrapper + CMD Window (Verified Working)

The **only** reliable execution method for VS20_WD builds is the bash wrapper pattern documented in the  
**"Reliable CMD Window Execution Pattern"** section below. It:
- Runs all commands inside `bash.exe` (required)
- Shows live progress in a visible CMD window
- Captures per-target exit codes with `__<TARGET>_DONE__:<ec>` markers

**Do NOT** use `& $gitBash -c "..."` inline from PowerShell for long builds — output buffering hides errors and progress is invisible.

## Important Notes

- **`set -e`** is used in all build scripts — the build stops on first error.
- **econ_config.sh** must be sourced fresh in each bash invocation (env vars don't persist across separate `bash -c` calls).
- **Never use heredocs** with `econ_config.sh` — it reads stdin. Always use single-line `-c "..."`.
- **Use `D:\Tool\Common\Git\bin\bash.exe`** — msys bash lacks `realpath` and causes infinite loops.
- Each `zz_build_*.sh` script internally calls `python run.py <variant>.Debug <actions>` with the appropriate action chain (tresos_generate, cmake_generate, post_build_local, build, memusage, etc.).

## Build Output Locations

| Target | Output Directory |
|--------|-----------------|
| FLU | `build/tviic_6m_flu.Debug/bin/` |
| FBL | `build/tviic_6m_fbl.Debug/bin/` |
| Second Core | `build/tviic_6m_endprod_second.Debug/bin/` |
| Endprod | `build/tviic_6m_endprod.Debug/bin/` |

## Verified Build Timings (VS20_WD — tviic_6m, full clean build)

| Target  | Compile files | Time     | Notes |
|---------|--------------|----------|-------|
| FLU     | 62           | 6m 04s   | Tresos gen ~5min, GHS compile ~50s |
| FBL     | 865          | 15m 41s  | Largest build — DCM/NvM/PduR heavy |
| SECOND  | ~200         | 10m 51s  | Second core (CM7_1) |
| ENDPROD | ~1800        | 52m 11s  | Main application — longest phase |
| **Total** |            | **~85 min** | Clean full build |

## Reliable CMD Window Execution Pattern (Verified Working)

The only reliable way to show live build progress in a visible CMD window on Windows:

### Step 1 — Write bash wrapper via Python (avoids BOM + encoding issues)

```python
# C:\Temp\make_wrapper.py
import os, datetime
ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
tmp = os.environ['TEMP'].replace('\\', '/')
log_win = os.environ['TEMP'] + f'\\build_vs20_{ts}.log'
log_bash = f"/{tmp[0].lower()}/{tmp[3:].replace(chr(92),'/')}/build_vs20_{ts}.log"
wrap_win = os.environ['TEMP'] + f'\\build_wrap_{ts}.sh'
wrap_bash = f"/{tmp[0].lower()}/{tmp[3:].replace(chr(92),'/')}/build_wrap_{ts}.sh"

wrap = f"""#!/bin/bash
set -o pipefail
LOG="{log_bash}"
cd 'd:/Work/VS20/VS20_WD' || exit 1
source econ_config.sh

run_target() {{
    local name=$1; shift
    local t_start=$(date +%s)
    printf '\\n========================================\\n  BUILDING: %s\\n========================================\\n' "$name" | tee -a "$LOG"
    "$@" 2>&1 | tee -a "$LOG"
    local ec=${{PIPESTATUS[0]}}
    local t_end=$(date +%s)
    local elapsed=$((t_end - t_start))
    echo "__${{name}}_DONE__:${{ec}}:${{elapsed}}" >> "$LOG"
    return $ec
}}

run_target FLU     bash ./zz_build_tviic_6m_flu.sh
run_target FBL     bash ./zz_build_tviic_6m_fbl.sh
run_target SECOND  bash ./zz_build_tviic_6m_endprod_second.sh
run_target ENDPROD bash ./zz_build_tviic_6m_endprod.sh

echo '__ALL_BUILD_DONE__' >> "$LOG"
"""
with open(wrap_win, 'w', encoding='utf-8', newline='\n') as f:
    f.write(wrap)

bat = f'@echo off\ntitle VS20 Build - FLU / FBL / SECOND / ENDPROD\n"D:\\Tool\\Common\\Git\\bin\\bash.exe" "{wrap_bash}"\necho.\necho === BUILD COMPLETE - window stays open for review ===\npause\n'
with open(r'C:\Temp\run_vs20_build.bat', 'w', encoding='utf-8') as f:
    f.write(bat)

with open(r'C:\Temp\build_paths.txt', 'w') as f:
    f.write(f"{log_win}\n{wrap_win}\n{log_bash}\n{wrap_bash}\n")
print('WRAPPER_OK')
print(f'Log: {log_win}')
```

### Step 2 — Run the Python generator

```powershell
python C:\Temp\make_wrapper.py
```

### Step 3 — Launch CMD window (bat file approach — most reliable)

```powershell
Start-Process "cmd.exe" -ArgumentList "/k C:\Temp\run_vs20_build.bat"
```

### Step 4 — Poll for completion (use hardcoded path from step 1 output)

```powershell
$lf = "C:\Users\<user>\AppData\Local\Temp\build_vs20_<timestamp>.log"
$timeout = 7200; $elapsed = 0
do {
    Start-Sleep -Seconds 60; $elapsed += 60
    $lc = Get-Content $lf -Raw -ErrorAction SilentlyContinue
    $flu = if ($lc -match '__FLU_DONE__:(\d+):(\d+)')    { "FLU=ec$($Matches[1])" } else { "FLU=..." }
    $fbl = if ($lc -match '__FBL_DONE__:(\d+):(\d+)')    { "FBL=ec$($Matches[1])" } else { "FBL=..." }
    $sec = if ($lc -match '__SECOND_DONE__:(\d+):(\d+)')  { "SEC=ec$($Matches[1])" } else { "SEC=..." }
    $end = if ($lc -match '__ENDPROD_DONE__:(\d+):(\d+)') { "END=ec$($Matches[1])" } else { "END=..." }
    Write-Host "[${elapsed}s] $flu  $fbl  $sec  $end"
} while (($lc -notmatch '__ALL_BUILD_DONE__') -and ($elapsed -lt $timeout))
```

### Step 5 — Parse final results

```powershell
# Parse and display the formatted build summary table:
powershell -ExecutionPolicy Bypass -File C:\Temp\parse_build_report.ps1
```

## PowerShell 5.1 Pitfalls (Windows — CRITICAL)

- **`-replace` with script block `{ }` does NOT work** in PS 5.1 — produces corrupted output. Use character indexing:
  ```powershell
  function ToBash($p) { '/' + $p[0].ToString().ToLower() + '/' + ($p.Substring(3) -replace '\\','/') }
  ```
- **`Set-Content -Encoding UTF8` adds BOM** (`\ufeff`) — always write files via Python with `encoding='utf-8', newline='\n'`
- **Multi-line blocks in `run_in_terminal`** — only first line executes. Run each statement individually.
- **Variable scope in polling loops** — `$logFile` set in one terminal call is lost in another. Always hardcode the path string.
- **`Start-Process cmd.exe` with bash arguments** — direct quoting is unreliable. Use a `.bat` file launcher instead.
- **`tee -a` output buffering** — the log file may not update until the subprocess (e.g., tresos eclipse Java) finishes. The CMD window shows live output, but the log file lags.

## Tresos Generation Behavior

- Tresos (EB tresos Studio) runs as a Java/Eclipse process (~3 GB RAM)
- Takes **5–15 minutes** per variant to generate code
- Output is buffered — log file stays static during generation
- Monitor with: `Get-ChildItem "build\<variant>\eclipse\workspace" -Recurse -File | Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-5) } | Measure-Object`
- Eclipse `.metadata/.log` warnings like `"Could not install bundle"` are non-fatal — generation continues

## Error Recovery

If a build step fails:
1. Parse the compiler/linker error from stdout/stderr
2. Read the failing source file for context
3. Apply the fix
4. Re-run only the failed step (incremental: `python run.py <variant>.Debug build_incremental`)
5. If incremental succeeds, continue with the next target in sequence
6. Max 5 retry attempts per target before escalating to user
