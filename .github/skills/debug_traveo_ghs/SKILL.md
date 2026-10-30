---
name: debug_traveo_ghs
description: >-
  Flash, debug, and inspect a Traveo II ECU via the GHS Multi debugger: flash and bring the
  system to running state; read/write runtime variables; set print-and-continue breakpoints;
  temporarily override a value at runtime without reflashing; root-cause an unexpected reset
  by walking the call chain to Mcu_PerformReset.
  Use when: flashing after a build; starting a fresh debug session; reading or writing ECU
  globals at runtime; tracing/monitoring a function with a breakpoint; bench-testing a changed
  threshold/flag without a rebuild; investigating spontaneous/periodic resets.
argument-hint: 'Describe the task, e.g.: flash ECU and start system; read FSM_u32HwErrorFlags; write g_WdgM_SE_Status=1; break on Mcu_PerformReset and print EXEA__u32RecordCntr; raise a current threshold at runtime; find what calls Mcu_PerformReset'
---

# Traveo II — GHS Multi Flash & Debug

## Overview

Flashes a Traveo II ECU via the GHS Multi debugger and drives runtime debug operations against
it: bring the system to a running state, read/write globals, set print-and-continue hardware
breakpoints, temporarily override a guarded value without reflashing, and root-cause an
unexpected reset by walking the call chain to `Mcu_PerformReset`. All operations are driven by
playback `.rc` scripts fed to GHS Multi (`multi -p <script>.rc -R <log>.txt`) — there is no
interactive session; every capability below is a self-contained, scripted recipe.

## Prerequisites

> **PREREQUISITE: CANoe must be running with KL15 ON before any flash or debug operation.**
> Without it, the ECU SWD bus returns `Unexpected ack b000` and Multi cannot connect.
> Start CANoe first (e.g. `Start-CANoe.ps1`, sets KL15=1/IGN_ACC).

> **Two known benches — check which one you're on before running any command below:**
>
> | | Bench A (primary, Capabilities 2-6 below) | Bench B (portable, Capabilities 1 & 7) |
> |---|---|---|
> | Variant | `tviib_e4m_aravalli_s3p_db` | `tviic_6m_endprod` |
> | Cores | **cm4** = app core (`debugger.program.1`), **cm0plus** = HSM/SHE (`debugger.program.0`, no app symbols) — ONLY cm0+cm4 | cm0plus + **cm7_0** + cm7_1 (triple core) |
> | App-core routing | `alias m4 route cm4` once, then prefix every command `m4 ` | prefix every command `m7_0 ` (or `m7_1` for second core) — `switch -component` gets PERMANENTLY stuck in cm0plus, so the prefix is mandatory, not just a convenience |
> | Write syntax | `m4 set VAR = VAL` / `m4 print VAR = VAL` | `m7_0 VAR = VALUE` — **NOT** `m7_0 set VAR = VALUE` (`set` is parsed as an expression keyword and fails) |
>
> Adjust `$buildDir`, the `.py`/`.rc` debug script path, and the `GHS_LM*`/conan probe path to
> whichever bench you are currently working with — do not mix core-prefix syntax across benches.

## Implementation Files

All scripts live under `.github/scripts/debug_traveo_ghs/` — see [Resources](#resources) below
for the full list and which capability each one backs.

## Usage

Pick the capability that matches the requested task (see `argument-hint` above for phrasing
examples), then jump to the matching subsection under [Workflow](#workflow):

| Need | Capability |
|------|------------|
| Flash + bring system up (Bench B) | 1 |
| Read a runtime/NOINIT variable (Bench A) | 2 |
| Write a runtime variable (Bench A) | 3 |
| Break on a function and print values (Bench A) | 4 |
| Temporarily override a guarded value at runtime (Bench A) | 5 |
| Root-cause an unexpected reset (Bench A) | 6 |
| Read / write / breakpoint (Bench B) | 7 |
| Automated multi-TC test execution (Bench B) | 8 |

## Command Execution — Timeouts & Status Polling (MANDATORY)

GHS Multi (`multi.exe` / `mpserv`) frequently **blocks the terminal even after the command has
already failed** — e.g. `Could not open file …` (missing binary), probe lost, KL15 dropped, or
an RC script left without a final `quit`. The RC playback ends but the process never returns
cleanly, so a naive unbounded wait hangs forever. Always bound the wait, then decide status from
the log — never assume success because the call "returned".

**Rules (apply to Capabilities 1–4 and the `traveo-basic-system-test` skill):**

1. **Terminate the script.** Every `-p` playback `.rc` MUST end with `quit` so Multi exits. Every
   bash launch MUST end with `; echo EXITCODE=$?` as a completion marker.
2. **Always pass an explicit `timeout`** to the terminal call — never omit it for flash/debug/test:

   | Operation | `run.py` / RC | timeout (ms) | Hard cap before "HUNG" |
   |-----------|---------------|--------------|------------------------|
   | Flash (`flash_ghs` / `flash_debug_ghs`) | full flash sequence | `240000` (4 min) | 300000 |
   | VERIFY only | `tvii_debug_4mbe.py VERIFY` | `120000` (2 min) | 150000 |
   | Read / Write / Breakpoint | VERIFY + run + read | `150000` | 180000 |
   | Basic system test (per test) | VERIFY + window + read | `180000` | 210000 |

3. **Verify status from the log/stdout — do not trust the return alone.** After the call returns
   (or times out), scan the `-R` log tail and stdout for:
   - **FAIL** keywords (case-insensitive): `error`, `Unknown`, `does not exist`, `Can not`,
     `Could not`, `not connected`, `Unexpected ack`, `failed`, `SEH`, `Probe Error`.
   - **PASS** markers: `Flash programming complete`, `Verified OK`, `EXITCODE=0`.
   - If a FAIL keyword appears → stop, report the decisive line, fix root cause. If only PASS
     markers → proceed.
4. **On timeout (still running) → treat as HUNG, not "in progress":** kill the debug processes,
   read the log tail to diagnose, and report. Do **not** re-issue another blind wait.
   ```powershell
   Stop-Process -Name "multi","mpserv","mpserv64","gmpserv" -Force -ErrorAction SilentlyContinue
   Get-Content "$buildDir\log\flash.log","$buildDir\<test>_out.txt" -Tail 40 -ErrorAction SilentlyContinue
   ```
5. **Reusable status check** (run right after any flash/test command):
   ```powershell
   # $log = the -R log file or flash.log for this run
   $tail = Get-Content $log -Tail 60 -ErrorAction SilentlyContinue
   $fail = $tail | Select-String -Pattern 'error|Unknown|does not exist|Can ?not|Could not|not connected|Unexpected ack|failed|SEH|Probe Error'
   $pass = $tail | Select-String -Pattern 'Flash programming complete|Verified OK|EXITCODE=0'
   if     ($fail) { Write-Host "STATUS: FAIL -> $($fail[-1].Line.Trim())" }
   elseif ($pass) { Write-Host "STATUS: PASS -> $($pass[-1].Line.Trim())" }
   else           { Write-Host "STATUS: UNKNOWN/HUNG - inspect $log" }
   ```
6. **Report** the derived status (PASS / FAIL / HUNG) plus the decisive log line before moving to
   the next pipeline step.

---

## Workflow

### General Rules (verified routing & playback, applies to ALL capabilities below)

- In `-p` playback `switch -component cm4` does NOT redirect subsequent commands. Define
  `alias m4 route cm4` once after VERIFY, then prefix EVERY app-core command with `m4 `.
- **`mprintf` with variable args HANGS** in playback — use plain `print EXPR` for values;
  keep `mprintf` for literal text only.
- **Wait-for-halt:** `wait -breakortime N` is INVALID (returns instantly). Use `wait -stop -time N`.
  After a hardbrk hit the core is already halted — do NOT add `target gh`/`halt`.
- Static / file-local vars need file-qualified syntax: `m4 print "file.c"#var` (also for writes:
  `m4 print "file.c"#var = <val>`).
- **Software breakpoints are IMPOSSIBLE in flash.** `break` is a flow-control keyword
  (`Usage: break [-fail | -succeed]`), and `b <symbol>` on a ROM address returns
  `Cannot set a software breakpoint in ROM. Use the hardbrk command`. `b file.c:line`
  → `No match`; `b "file.c":line` → `Invalid Address`. **Always use `hardbrk rolling <symbol>`.**
- cm0plus VERIFY emits a huge harmless `INCOHERENT` dump — filter it out when reading the log
  (`Where-Object { $_ -notmatch "INCOHERENT" }`).
- **Skip `verify -all` for read/write/breakpoint sessions.** It re-reads the readback-protected
  HSM ROM — slow (~min) and intermittently aborts with a 60+ MB dump. Export `TVII_SKIP_VERIFY=1`
  before launching `multi`; the (unmodified) `tvii_debug_*.py` honors it and skips verify while
  still connecting + arming breakpoints. `VERIFY` mode is still the right EXECUTION_MODE.
- **A failed command hangs `multi`.** On any command error in `-p` playback MULTI prints
  `Warning: Some commands are thrown away owing to command failure` and discards the REST of the
  script — *including `quit`* — so the GUI never closes and a naive wait blocks until timeout.
  **Fail fast**: poll the `-R` log for error markers (`Syntax Checking|Unexpected token|thrown
  away owing to command failure|not successful|No match|Invalid Address|Cannot set|Cannot find`)
  and kill `multi` as soon as one appears.
- **Delete breakpoints with `D` (all) or `d <sym>` — NOT `delete`.** `m4 delete` fails with
  `Unknown name "delete" in expression` (while running) or `Cannot find global symbol "delete"`.
  (See the codebase's own `multi.rc`, which uses `d /force <sym>` and `D`.)
- **No C-variable assignments inside a breakpoint action block.** `{ "file.c"#var = val }` →
  `Unexpected token found after command end`; `{ eval ... }` silently no-ops. Inside a block use
  a MULTI command (e.g. `target mw <w> <addr> <val>`, `hardbrk delete=1`, `mprintf` literal).
  To force a value reliably, prefer a HALTING breakpoint + top-level `m4 print "file.c"#var = val`
  while halted (that write form IS honored), then `m4 D` before resuming.
- **After `target gc`, a bare `wait -stop` watches the ACTIVE component (cm0plus, already halted)
  and returns instantly** — a following write then fails with `Process Running`. Use the read
  pattern: `wait -time N` → `m4 halt` → `wait -stop -time N` → write.
- **Resuming from a breakpoint AT the current PC re-hits it immediately**, so the function body
  never executes (e.g. an injected request is never consumed). `m4 D` (delete the BP) BEFORE
  `target gc` so the body runs once.
- **`Start-Job` does NOT inherit `Push-Location`.** When launching `multi` inside a job, the
  bash `cd` MUST be an absolute path (`cd /c/.../build/<variant>.Debug`) or multi pops a
  `Can't find file "debug.ghsmc"` dialog and hangs.

---

### Capability 1 — Flash & Run (Bench B, `tviic_6m_endprod`, portable auto-detect)

Steps: (1) start CANoe measurement; (2) flash all binaries via `flash_ghs`; (3) launch GHS
Multi with VERIFY + `target gc`. Project root is auto-detected — no hardcoded workspace path.

### One-Command Setup

```powershell
& "<repo>\.github\scripts\debug_traveo_ghs\setup.ps1"
```

### Manual Steps

**0. Detect project root** (scans `*:\Work\**` on all fixed drives for the first folder with
the TVII build-repo signature; reuse `$projectRoot`/`$bRoot` in every step below):
```powershell
$projectRoot = [IO.DriveInfo]::GetDrives() |
    Where-Object { $_.IsReady -and $_.DriveType -eq 'Fixed' } |
    ForEach-Object { Get-ChildItem "$($_.Name)Work" -Directory -ErrorAction SilentlyContinue |
                     Get-ChildItem -Directory -ErrorAction SilentlyContinue } |
    Where-Object {
        (Test-Path "$($_.FullName)\run.py") -and
        (Test-Path "$($_.FullName)\econ_config.sh") -and
        (Test-Path "$($_.FullName)\app\variants\tviic_6m_endprod") -and   # TVII-specific marker
        (Test-Path "$($_.FullName)\Start-CANoe.ps1")                      # disambiguates from other TVII repos
    } |
    Select-Object -First 1 -ExpandProperty FullName

if (-not $projectRoot) { throw "No TVII build repo found — expected *:\Work\**  with run.py + econ_config.sh + app\variants\tviic_6m_endprod" }
Write-Host "[OK] TVII repo detected: $projectRoot"

$bRoot    = '/' + $projectRoot.Substring(0,1).ToLower() + $projectRoot.Substring(2).Replace('\','/')  # bash path
$buildDir = "$projectRoot\build\tviic_6m_endprod.Debug"
```

**1. Start CANoe:**
```powershell
& "$projectRoot\Start-CANoe.ps1"
```

**2. Flash ECU** (econ_config.sh single-line constraint: never use heredoc):
```powershell
Stop-Process -Name "multi","mpserv" -Force -ErrorAction SilentlyContinue
& "C:\Program Files\Git\bin\bash.exe" -c "cd $bRoot && source econ_config.sh && ./run.py tviic_6m_endprod.Debug flash_ghs 2>&1"
```
Flashes in order: HSM SHE → sflash → FBL → App endprod → App second core.

> **Intermittent "Could not detect a flash device at 0x10000000" / "Memory write failed at
> 0x100000aa" / "already connected" is a KNOWN transient probe/USB glitch** — the exact same
> `mpserv` binary + args succeed on a later attempt once stale probe holders are killed and the
> probe settles (verified: identical tooling, success/failure intermixed across back-to-back
> runs). **Do NOT conclude the scripts/config are broken from a single failed flash.** Prefer
> the resilient wrapper, which kills `multi`/`mpserv`, settles, and retries up to N times,
> distinguishing transient probe errors (retry) from real config/toolchain errors (surface):
>
> ```powershell
> & "<repo>\.github\scripts\debug_traveo_ghs\flash_ghs_retry.ps1" -Variant <variant>.Debug
> # e.g. -Variant tviib_e4m_aravalli_s3p.Debug   (Bench A)
> #      -Variant tviic_6m_endprod.Debug         (Bench B)
> ```
> It auto-detects the repo root and git-bash; pass `-Repo <path>` / `-MaxRetries <n>` to override.

**3. System Running (VERIFY + target gc):**
```powershell
Stop-Process -Name "multi","mpserv" -Force -ErrorAction SilentlyContinue
Set-Content "$buildDir\autorun.rc" "wait -time 3000`npython -b -f ../../app/variants/tviic_6m_endprod/debug/tvii_debug_6mb.py VERIFY`nwait -time 90000`ntarget gc" -Encoding ASCII
$envCmd = "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/bceabf/1:/d/.conan/short/bceabf/1/_ide:`$PATH'"
& "C:\Program Files\Git\bin\bash.exe" -c "$envCmd; cd $bRoot/build/tviic_6m_endprod.Debug && D:/.conan/short/bceabf/1/_ide/multi -nosplash -servertimeout 300 debug.ghsmc -p autorun.rc 2>&1"
```
VERIFY connects the probe, downloads symbols to cm0plus/cm7_0/cm7_1, then `target gc` starts
all cores. Takes ~90-100s. **Run Multi in the foreground of `& bash -c "..."`** (see Critical
GRTL Facts below for why `Start-Process`/`& disown` are unreliable here).

### Fallback — flash via OpenOCD/KitProg3 (GHS probe unavailable)

```powershell
& "<repo>\.github\scripts\debug_traveo_ghs\flash_openocd.ps1"
```

### Error Handling

| Issue | Action |
|-------|--------|
| `ECON has not been executed` | `source econ_config.sh` is required — do NOT set env vars manually for flash |
| `Could not detect a flash device` / `Memory write failed at 0x100000aa` / `already connected` | KNOWN transient probe/USB glitch — NOT a script/config defect (same `mpserv` succeeds on retry). Use `flash_ghs_retry.ps1` (kills probe holders, settles, retries). If it still fails after all retries, check the GHS probe USB cable + target power (KL15) |
| `realpath: command not found` | Wrong bash — use `C:\Program Files\Git\bin\bash.exe` only (not msys bash, which lacks `realpath` and loops in econ_config.sh) |
| `debug.ghsmc` not found | Run: `source econ_config.sh && python app/variants/common/addon_cmb/debug_gen.py <variant>.Debug` |
| VERIFY fails / loops | `Stop-Process -Name mpserv -Force` then retry Step 3 |
| CANoe won't start | `Stop-Process -Name CANoe64 -Force` then re-run the CANoe start script |
| `Vector CANoe (View Only)` in window title | Simulation license not active — ask user to press **F9 inside the CANoe window**; verify `$app.Measurement.Running` is `True` |
| Wrong project detected (`$projectRoot`) | Multiple TVII repos on the machine — ensure the target repo has `Start-CANoe.ps1` at its root (used to disambiguate) |
| Multi-line script with econ_config.sh | econ_config.sh reads stdin — always use single-line `-c "..."` with `&&` chaining |
| Multi exits in <5s / probe not acquired | Used `Start-Process` or `& disown` — **NEVER** use them; run Multi as foreground `& bash -c "..."`, either directly (blocks) or inside `Start-Job` (for timeout control) — `mpserv` cannot acquire the SWD probe without inheriting the terminal's process group |
| INCOHERENT warnings during VERIFY | HSM region is encrypted at runtime; does not match ELF — expected, not an error |
| `Error: General Error` + `just_did_rom_to_ram_copy failed` | Expected during VERIFY on TVII; safe to ignore — VERIFY continues and halts at `Startup_Init` |
| `Syntax error at or near "=="` on RC line 1 | An RC comment/banner line contains `==`. GHS parses `//`-wrapped comments and chokes on `==`. Keep RC files command-only — no `===` banners; use short `;` comments without `==` |
| `target: not connected to a debug server` / `hardbrk: not allowed, no connection` | RC ran the debug script in `RESET` mode. RESET skips the connect/common block. **Always use `VERIFY`** for read/write/breakpoint — it runs prepare_target+reset+halt and attaches mpserv |
| VERIFY aborts at RC line 2 with `MULTI command stack` (after the INCOHERENT dump) | `verify -all` intermittently fails on the readback-protected HSM/SHE ROM. **Best fix: export `TVII_SKIP_VERIFY=1`** so the debug script skips verify entirely (connect/read/write/breakpoint don't need it) — `run_debug_rc.ps1` does this automatically. Otherwise just re-run; it completes within 1–2 tries (`hud_tc_runner.ps1` auto-retries) |

---

### Capability 2 — Read Variable

Choose the pattern based on what you're reading.

### Pattern A — NOINIT variable (error logs, reset counters, watchdog state)

VERIFY halts at `Startup_Init` BEFORE RAM zeroing — NOINIT values from the last run are still
present. Read immediately, no need to release the system. **Total time: ~95s.**

```powershell
$buildDir = "build\tviib_e4m_aravalli_s3p_db.Debug"
$varFile  = "ammsm1c1.c"             # <-- file that declares the (static) var
$varName  = "AmmSM__enCurrentMode"   # <-- change this

Stop-Process -Name "multi","mpserv","mpserv64","gmpserv" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 4
Remove-Item "$buildDir\read_var_out.txt" -ErrorAction SilentlyContinue

Set-Content "$buildDir\read_var.rc" @"
wait -time 3000
python -b -f ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.py VERIFY
wait -time 2000
alias m4 route cm4
m4 print "$varFile"#$varName
wait -time 1000
quit
"@

& "C:\Program Files\Git\bin\bash.exe" -c "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/dc601f/1:/d/.conan/short/dc601f/1/_ide:`$PATH'; cd build/tviib_e4m_aravalli_s3p_db.Debug; multi -nosplash -servertimeout 60 debug.ghsmc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/multi.rc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.rc -R read_var_out.txt -p read_var.rc; echo EXITCODE=`$?"

Get-Content "$buildDir\read_var_out.txt" | Where-Object { $_ -notmatch "INCOHERENT" } | Select-String $varName
```

### Pattern B — Runtime variable (set after system starts running)

VERIFY halts at `Startup_Init`, then `target gc` releases all cores. Wait for system init,
then halt and read. **Total time: ~107s.**

```powershell
$buildDir = "build\tviib_e4m_aravalli_s3p_db.Debug"
$varFile  = "ammsm1c1.c"             # <-- file that declares the var
$varName  = "AmmSM__enCurrentMode"   # <-- change this

Stop-Process -Name "multi","mpserv","mpserv64","gmpserv" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 4
Remove-Item "$buildDir\read_var_out.txt" -ErrorAction SilentlyContinue

Set-Content "$buildDir\read_var.rc" @"
wait -time 3000
python -b -f ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.py VERIFY
wait -time 2000
alias m4 route cm4
target gc
wait -time 10000
m4 halt
wait -stop -time 5000
m4 print "$varFile"#$varName
wait -time 1000
target gc
quit
"@

& "C:\Program Files\Git\bin\bash.exe" -c "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/dc601f/1:/d/.conan/short/dc601f/1/_ide:`$PATH'; cd build/tviib_e4m_aravalli_s3p_db.Debug; multi -nosplash -servertimeout 60 debug.ghsmc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/multi.rc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.rc -R read_var_out.txt -p read_var.rc; echo EXITCODE=`$?"

Get-Content "$buildDir\read_var_out.txt" | Where-Object { $_ -notmatch "INCOHERENT" } | Select-String $varName
```

### Multiple Variables

Add more `m4 print` lines in the RC (plain `print`, NOT `mprintf` with var args):
```
m4 print "ammsm1c1.c"#AmmSM__enCurrentMode
m4 print myStruct.field
m4 print myArray[0]
```

### Error Handling

| Issue | Action |
|-------|--------|
| `No match` for app symbol | Command ran on cm0plus — prefix it with `m4 ` (don't use `switch -component`) |
| Playback hangs on a read | `mprintf` with var args — use plain `m4 print EXPR` |
| Static var → GUI dialog / hang | Qualify with file name: `m4 print "file.c"#var` |
| VERIFY fails / hangs | `Stop-Process -Name mpserv -Force` then retry |
| Log file empty | VERIFY (~90s) is still running — wait longer or check Multi exited cleanly |
| Value is 0 for NOINIT | Variable may not be NOINIT — use Pattern B instead |

---

### Capability 3 — Write Variable

```powershell
$buildDir = "build\tviib_e4m_aravalli_s3p_db.Debug"
$varName  = "g_WdgM_SE_Status"   # <-- change this
$value    = "1"                  # <-- change this

Stop-Process -Name "multi","mpserv","mpserv64","gmpserv" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 4
Remove-Item "$buildDir\write_var_out.txt" -ErrorAction SilentlyContinue

Set-Content "$buildDir\write_var.rc" @"
wait -time 3000
python -b -f ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.py VERIFY
wait -time 2000
alias m4 route cm4
target gc
wait -time 10000
m4 halt
wait -stop -time 5000
m4 print $varName
m4 set $varName = $value
m4 print $varName
wait -time 1000
target gc
quit
"@

& "C:\Program Files\Git\bin\bash.exe" -c "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/dc601f/1:/d/.conan/short/dc601f/1/_ide:`$PATH'; cd build/tviib_e4m_aravalli_s3p_db.Debug; multi -nosplash -servertimeout 60 debug.ghsmc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/multi.rc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.rc -R write_var_out.txt -p write_var.rc; echo EXITCODE=`$?"

Get-Content "$buildDir\write_var_out.txt" | Where-Object { $_ -notmatch "INCOHERENT" } | Select-String $varName
```

### GRTL Write Syntax (prefix each with `m4 ` in playback)

```
m4 set myVar = 42
m4 set myVar = 0xDEADBEEF
m4 set myStruct.field = 0
m4 set myArray[3] = 255
```

### Error Handling

| Issue | Action |
|-------|--------|
| Write ignored | Variable may be const / in flash ROM (RAM vars only) |
| `No match` for app symbol | Command ran on cm0plus — prefix it with `m4 ` |
| Script returns instantly after halt | Used `wait -breakortime` — replace with `wait -stop -time N` |
| VERIFY fails | `Stop-Process -Name mpserv -Force` then retry |

---

### Capability 4 — Breakpoint & Print (print-and-continue)

```powershell
$buildDir = "build\tviib_e4m_aravalli_s3p_db.Debug"
$funcName = "AmmSM__vSysModeStateChange"   # <-- function to break on (hardbrk symbol)
$varName  = "AmmSM__enCurrentMode"          # <-- static var to print (file-qualified)
$varFile  = "ammsm1c1.c"

Stop-Process -Name "multi","mpserv","mpserv64","gmpserv" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 4
Remove-Item "$buildDir\bp_out.txt" -ErrorAction SilentlyContinue

Set-Content "$buildDir\bp_script.rc" @"
wait -time 3000
python -b -f ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.py VERIFY
wait -time 2000
alias m4 route cm4
m4 mprintf("Setting HW BP on $funcName\n")
m4 hardbrk rolling $funcName
target gc
wait -stop -time 60000
wait -time 2000
m4 mprintf("=== BP REACHED ===\n")
m4 print `$r0
m4 print `$r1
m4 print "$varFile"#$varName
wait -time 2000
m4 mprintf("=== READ DONE ===\n")
wait -time 1000
quit
"@

& "C:\Program Files\Git\bin\bash.exe" -c "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/dc601f/1:/d/.conan/short/dc601f/1/_ide:`$PATH'; cd build/tviib_e4m_aravalli_s3p_db.Debug; multi -nosplash -servertimeout 60 debug.ghsmc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/multi.rc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.rc -R bp_out.txt -p bp_script.rc; echo EXITCODE=`$?"

# VERIFY+run ~90-110s. Filter the harmless INCOHERENT dump when reading:
Get-Content "$buildDir\bp_out.txt" | Where-Object { $_ -notmatch "INCOHERENT" } | Select-Object -Last 40
```

### Key GRTL Commands

| Command | Purpose |
|---------|---------|
| `alias m4 route cm4` | Define app-core routing alias (do once after VERIFY) |
| `m4 hardbrk rolling FUNC` | **Hardware** breakpoint at function entry (flash builds) |
| `wait -stop -time N` | Block until a core halts, or timeout after N ms |
| `target gc` | Go all cores |
| `m4 print $r0` / `m4 print $r1` | Read 1st / 2nd ARM arg register (args at func entry) |
| `m4 print "file.c"#var` | Read a static / file-local variable |
| `m4 delete` | Remove all breakpoints |

### To break at a LINE inside an `if`

(e.g. "line 2336 when the condition is satisfied") put the breakpoint on the FUNCTION CALLED
on that line — it is only invoked when the condition is true. A hardbrk stops at function
ENTRY, BEFORE the prologue copies args to the stack, so named params read STALE garbage —
read the ARM AAPCS arg registers instead: `$r0` = 1st arg, `$r1` = 2nd arg. Static/file-local
vars need `"file.c"#var` syntax.

### Error Handling

| Issue | Action |
|-------|--------|
| `Cannot set a software breakpoint in ROM` | Flash build — use `m4 hardbrk rolling FUNC`, never `break`/`b` |
| `Usage: break [-fail | -succeed]` | `break` is flow-control, not a BP command; use `hardbrk` |
| `No match` / `Invalid Address` on `b file:line` | `b` won't take file:line in flash; break on the symbol with hardbrk |
| Args read as stale garbage at BP | HW BP stops before prologue — read `$r0`/`$r1` instead of named params |
| `No match` for app symbol | Command ran on cm0plus — prefix it with `m4 ` (don't rely on `switch -component`) |
| Script returns instantly / reads stale value | Used `wait -breakortime` — replace with `wait -stop -time N` |
| Hang right after BP hit | Remove `target gh`/`halt` (core already halted) and any `mprintf` with var args |
| Timeout — BP not hit | Function not called in window; increase `wait -stop -time` or check name |
| Multiple hit | Add `m4 delete` after first hit to remove the breakpoint |

---

### Capability 5 — Temporarily Override a Value at Runtime

Override is **volatile**: lost on power-cycle, active **only while the debugger is attached**.
It does NOT modify flash and does NOT touch CRC-protected NvB parameters.

### Decide which method to use

| Situation | Method |
|-----------|--------|
| Plain global, written once, read back later | **Direct write** |
| Value re-loaded every cycle / re-entry, or one-shot write gets overwritten | **Breakpoint-intercept write** |
| Value is guarded (double-inverse, CRC, range clamp) | **Breakpoint-intercept at the setter argument** so firmware recomputes the guard |

**Method 1 — Direct write.** For a simple global that is not re-loaded by code, set it once
after init: `m4 set <var> = <val>` (or `m4 print <var> = <val>`; see Capability 3 for syntax,
file-qualify statics: `m4 print "file.c"#var = <val>`).

**Method 2 — Breakpoint-intercept write.** Set a HW BP at the exact instruction that
loads/stores the value, rewrite the source register, and **auto-continue**. The override
survives every re-load (e.g. each state re-entry). This is the robust approach for cyclic,
state-machine, or safety values.

### Key enabler — `hardbrk` brace command blocks (verified work in `-p`)

```
m4 hardbrk <addr> { eval $rN = <val>; mprintf("literal text\n"); c }
```

- The block runs on every hit; the trailing `c` **auto-continues** (no foreground halt).
- `if ($x == N) { ... }` conditionals and `eval $rN = VAL` register writes work in the block.
- Syntax reference: `multi.rc` `setSWBPwa()` / `jade_set_exception_vector_bps()`
  (`if` / `eval` / `while` / `$exists` / `c` / `Q`). NOTE: **software-bp** brace blocks
  (`b /s FUNC { }`) hang in playback — only `hardbrk` blocks are safe.
- Keep `mprintf` to **literal text only**; `mprintf("%x",$rN)` with var args hangs.

### Choosing the break site (generic rules)

- Break where the **source register already holds the value** — a `bl` call site (the
  argument register) or a store instruction — not at a setter ENTRY that runs **every
  cycle**. An every-cycle BP halts the core each tick, slows it drastically, and
  **trips the watchdog (WdgM) → reset**. Prefer a rare call site.
- Find the exact address: `gdump -N -ytext -ylabfunc <abs> > out.txt` →
  per-line `0xADDR: bytes mnemonic` with function labels (`-asm` alone strips addresses).
- Beware **safety guards**: a bare field write may trip a double-inverse (`value` + `~value`)
  or a cyclic CRC. Prefer letting the firmware's own setter recompute the inverse/CRC by
  rewriting its **argument** at the call site, rather than poking the stored field.
- Confirm the override took effect by reading the resulting stored field back after the BP.

### Drive a state machine to a target state (multi-gate override)

When the goal is not one value but a *resulting state* (e.g. walk an app mode SM to a
target mode) that is held back by several gates re-evaluated every cycle, override **all**
of them, each at the point it is consumed:

- **Inject AFTER any upstream override, at the branch/switch dispatch.** If a later line
  re-forces your value (e.g. `if (failsafe && req > 0) req = Standby;`), a BP at the
  original read site (the `bl`-return `mov rN,r0`) is silently clobbered. Move the inject to
  the **`switch` dispatch** (`mov r0,rN` immediately before the jump table) — the *last*
  point the value is read before the decision. Re-derive that address with
  `gdump -N -ytext -ylabfunc` and map it to the C `switch`.
- **A var re-set inside the same function after your entry-clear is overwritten.** Clearing
  it at the function ENTRY does not stick if the function writes it again later. Clear it at
  the **consumption point** (right before the branch that reads it), not at entry.
- **Some clears must run every cycle — and a minimal block can be safe.** Global flags
  (failsafe/safe-mode) re-asserted each tick by other code must be cleared at a
  frequently-run function entry every cycle. The WdgM warning still applies, but a
  *tiny* `hardbrk <entry> { eval "file.c"#flag = 0; c }` ran 70 s with NO watchdog reset
  here. Keep the block minimal; if WdgM trips, shorten the drive or kick the watchdog.
- **Pin the request to the terminal target.** If the request can overshoot (e.g. ReqMode
  drives toward ProjectionOn(40), passing *through* WaitDispOn(30)), force the request to
  the exact target so the SM settles there instead of moving on.
- **Budget time and read the SETTLED value.** The SM advances one step per cycle and waits
  on downstream subsystems (display/illum/eyebox reaching Ready) — budget tens of seconds
  (≈70 s observed), then `target gc; wait -time N; m4 halt; m4 print <stateVar>`. Do not try
  to halt exactly on the transition.
- **Trace progression** by logging a register in the block:
  `m4 hardbrk <transitionFn-entry> { print $rN; c }` (use `print`, never `mprintf` var-args).
  Note: direct field writes (e.g. `CurrentMode = WaitReady`) that bypass the transition
  notifier won't show in such a trace.
- Keep the **reset/limit override armed** the whole time: clearing a safety gate may let the
  system command the very load that triggered the original fault, so the reset bypass (see
  Capability 6) is your safety net.

### General recipe for any "set value temporarily" request

1. Identify the variable, its set/load site, and any safety guard (inverse, CRC, range clamp).
2. `gdump -N -ytext -ylabfunc <abs>` → get the exact load/store/`bl` address (build-specific).
3. Break where the source register holds the value; rewrite via `eval $rN = <val>`
   (or write field + inverse together if no setter recomputes them).
4. End the block with `c` to auto-continue; read back the stored field to confirm.
5. Keep the session attached for the test duration (see below).

### Runnable template

```powershell
$buildDir = "build\tviib_e4m_aravalli_s3p_db.Debug"
$bpAddr   = "0x........"   # <-- bl call site / store of the value (re-derive via gdump after a rebuild)
$reg      = "r0"          # <-- register that holds the value at $bpAddr
$newVal   = "0x...."      # <-- value to force in
$readBack = '"file.c"#StructInstance.field'   # <-- field to read back to confirm

Stop-Process -Name "multi","mpserv","mpserv64","gmpserv" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 4
Remove-Item "$buildDir\override_out.txt" -ErrorAction SilentlyContinue

Set-Content "$buildDir\override.rc" @"
wait -time 3000
python -b -f ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.py VERIFY
wait -time 2000
alias m4 route cm4
m4 mprintf("Installing override at $bpAddr\n")
m4 hardbrk $bpAddr { eval `$$reg = $newVal; mprintf(">>> OVERRIDE APPLIED\n"); c }
target gc
wait -time 90000
m4 halt
m4 print $readBack
target gc
wait -time 1000
quit
"@

& "C:\Program Files\Git\bin\bash.exe" -c "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/dc601f/1:/d/.conan/short/dc601f/1/_ide:`$PATH'; cd build/tviib_e4m_aravalli_s3p_db.Debug; multi -nosplash -servertimeout 60 debug.ghsmc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/multi.rc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.rc -R override_out.txt -p override.rc; echo EXITCODE=`$?"

Get-Content "$buildDir\override_out.txt" | Where-Object { $_ -notmatch "INCOHERENT" } | Select-Object -Last 30
```

### Keep the override active during a real test

The template above ends with `quit` → session detaches → override is gone. For an actual
bench test, keep the session **attached** with the BP armed: replace the trailing
`wait`/`quit` with a long/indefinite `wait` so the hardbrk stays live. KL15 must stay ON.

### Example — raise a guarded LED off-state current limit (10 mA → 100 mA)

A concrete application of Method 2 against a CRC/double-inverse-guarded safety parameter,
to stop a SafeState2 → SafeState3 MCU-reset escalation by raising ONLY the off-state limit:

- The value is loaded ONCE per state entry as the argument of a setter call:
  `IsmD__vSetLEDCurrentThreshold(IsmD_stNvBParameters...u16LEDCurrentBoundaryOffState)`.
- Disassembly (`gdump -N -ytext -ylabfunc`, addresses build-specific):
  ```
  0x100550fe: ldrh.w r0,[r8,#64]   ; load off-state 0x64 (=10mA) into r0
  0x10055102: bl     0x10055d5c     ; call IsmD__vSetLEDCurrentThreshold
  ```
- Break at the `bl` (`0x10055102`): `r0` already holds the value, and this site runs only
  on state entry (rare) → no watchdog risk. Force `r0 = 0x3E8` (=1000 = 100 mA, ≤ clamp).
- The setter recomputes the double-inverse itself → safety var stays valid; CRC untouched.
- **Verified result:** BP hit, stored `u16LEDCurrentThreshold = 1000` (0x3E8),
  `...Inv = 64535` (0xFC17 → `~(1000 ^ 64535) = 0`). Target ran 90 s with NO reset.

### Error Handling

| Issue | Action |
|-------|--------|
| Override ignored / field stays old value | Reg not the value source at that PC — break at the `bl`/store where it is |
| Core slows to a crawl / unexpected reset | BP at an every-cycle site trips WdgM — move BP to a rare call site |
| Double-inverse storage failure after write | You poked a double-inverse field directly — rewrite the setter ARG instead |
| CRC checksum failure after write | You changed CRC-protected NvB data — override the runtime load, not the param |
| `b /s FUNC { }` hangs in playback | Software-bp brace blocks hang — use `hardbrk <addr> { ... }` |
| `mprintf` hangs | Used variable args — keep `mprintf` literal-only; read values with `m4 print` |
| `No match` for app symbol | Command ran on cm0plus — prefix with `m4 ` |
| Injected value clobbered / has no effect despite BP hitting | A downstream guard re-forces it after your read site — move the inject to the `switch`/branch dispatch (`mov r0,rN`), after the guard |
| Var keeps reverting even with an every-cycle clear | It is re-set *inside the same function* after your entry-clear — clear it at the consumption point (just before the branch that reads it), not at entry |
| State never advances even with gate forced | Another gate is still active (failsafe/safe-mode flag) — clear ALL gates each cycle; give the SM tens of seconds and read the settled value |
| `Green Hills Probe error 89 (SWD protocol error)` / `trg_run() failed` mid-run | Peripheral power-on transient (display/backlight) after clearing a safety gate perturbs the SWD bus — usually self-recovers; keep the reset/limit override armed and retry |

---

### Capability 6 — Root-Cause an Unexpected Reset

Reconstruct the call chain that reaches `Mcu_PerformReset` via GHS Multi.

### Strategy: walk the reset call chain via `$lr`

Almost every deliberate reset funnels through `Mcu_PerformReset`. There is **no textual
backtrace** in `-p` playback (`bt` parses as `b t`). Reconstruct the chain manually:

1. `hardbrk rolling Mcu_PerformReset` (and any suspected intermediate functions).
2. On hit, read the return address `$lr` and the ARM AAPCS arg registers `$r0..$r3`
   (HW BP stops at function ENTRY, before the prologue — named params are stale).
3. Clear the Thumb bit of `$lr` (odd → subtract 1) and resolve it in the `.map`
   (`build/.../bin/<variant>.map`, symbol range `addr .. addr+size`) to find the caller.
4. Re-arm a hardbrk on that caller, repeat until you reach the originating monitor.

This chain-walk is the generic technique; the same four steps apply regardless of which
monitor (watchdog, CRC, over-current, stack, exception handler, etc.) raised the reset.

### Common reset-trigger families to suspect

- **Watchdog (WdgM/Wdg)** — a supervised entity missed its deadline (often caused by the
  core being halted too long, e.g. a BP at an every-cycle site).
- **Application error / safe-state escalation** — a module detected a fault and requested a
  reset (`...ApplicationErrorReset`, `...EnterSafeStateN`, `...TriggerMcuReset`).
- **CRC / double-inverse integrity** — a protected parameter or RAM block failed validation.
- **Unhandled exception / hard fault** — reset issued from a fault/exception handler.

For an app-error escalation, the typical args at the `...ApplicationErrorReset` entry are
`$r0 = ModuleId`, `$r1 = ErrorId`; decode them against the module's id/error headers.
NOTE: a recovery/reset helper is often called MULTIPLE times per boot — filter on the
reset-option argument to distinguish the **real** reset from a startup **re-report** of the
previous cause (recorded in NOINIT RAM).

### Example chain (CONFIRMED) — LED over-current safe-state escalation

A worked instance of the chain-walk above:

```
Mcu_PerformReset
  <- SysCtlSM__vDoExceptionRecovery(AppErrorExc=26, ImmediatelyReset=0)
  <- SysCtlSM_vApplicationErrorReset(ModuleId, ErrorId)
  <- IsmD__vTriggerMcuReset
  <- IsmD__vEnterSafeState3(ErrorId)
  <- ismd1c4.c LED current monitor
```

- Evidence at `SysCtlSM_vApplicationErrorReset` entry:
  `$r0 = 0x30A0` = `IsmD_nModuleId`, `$r1 = ErrorId`, `$lr` in `IsmD__vTriggerMcuReset`.
- **ErrorId map (ismd1c3.h):** `1` = DblInverseStorageFail, `2` = CrcChecksumCmprFail,
  `3` = LedOvrCurSST2 (over-current while already in SafeState2AllOff), `4` = DispBlPinLevel.
- `SysCtlSM__vDoExceptionRecovery` is called MULTIPLE times per boot — filter on the
  reset-option arg (`$r3`): `0` = Immediately (the real reset), `2` = NoReset (startup
  reporting of the PREVIOUS cause, recorded in NOINIT RAM).

### Pre-armed breakpoints (from tvii_debug_4mbe.py)

After VERIFY, the script auto-arms `Startup_Init`, `ErrorHook`, `Mcu_PerformReset`
(all `hardbrk rolling`). VERIFY halts at `Startup_Init`. If your own BP is inactive,
`target gc` may stop at `Mcu_PerformReset` (the reset trap). `m4 delete` the pre-armed
BPs after VERIFY so only your wanted BP is active.

### Runnable template

Replace the breakpoint target with the function you currently suspect; re-run, read
`$lr`/`$r0..$r3`, resolve the caller, then move the breakpoint one level up the chain.

```powershell
$buildDir = "build\tviib_e4m_aravalli_s3p_db.Debug"
Stop-Process -Name "multi","mpserv","mpserv64","gmpserv" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 4
Remove-Item "$buildDir\reset_dbg_out.txt" -ErrorAction SilentlyContinue

Set-Content "$buildDir\reset_dbg.rc" @"
wait -time 3000
python -b -f ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.py VERIFY
wait -time 2000
alias m4 route cm4
m4 hardbrk rolling Mcu_PerformReset
target gc
wait -stop -time 60000
m4 mprintf("=== RESET TRAP REACHED ===\n")
m4 print `$r0
m4 print `$r1
m4 print `$r3
m4 print `$lr
wait -time 1000
quit
"@

& "C:\Program Files\Git\bin\bash.exe" -c "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/dc601f/1:/d/.conan/short/dc601f/1/_ide:`$PATH'; cd build/tviib_e4m_aravalli_s3p_db.Debug; multi -nosplash -servertimeout 60 debug.ghsmc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/multi.rc -rc ../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.rc -R reset_dbg_out.txt -p reset_dbg.rc; echo EXITCODE=`$?"

Get-Content "$buildDir\reset_dbg_out.txt" | Where-Object { $_ -notmatch "INCOHERENT" } | Select-Object -Last 40
```

### Resolve an address in the .map / disassembly

- Caller from `$lr`: `grep_search` the `.map` (`includeIgnoredFiles: true`) for the symbol
  whose `addr <= ($lr & ~1) < addr+size`.
- Exact instruction address (for a follow-up BP): `gdump -N -ytext -ylabfunc <abs> > out.txt`
  gives per-line `0xADDR: bytes mnemonic` WITH function labels. `-asm` alone strips addresses.

### Error Handling

| Issue | Action |
|-------|--------|
| `bt` prints usage / no backtrace | `bt` = `b t`; reconstruct chain from `$lr` + `.map` instead |
| Stops at `Mcu_PerformReset` immediately | Pre-armed reset trap — `m4 delete` pre-armed BPs after VERIFY |
| Args read as stale garbage | HW BP stops before prologue — read `$r0..$r3`, not named params |
| Many `DoExceptionRecovery` hits | Filter `$r3`: 0 = real reset, 2 = startup re-report of previous cause |
| `No match` for app symbol | Command ran on cm0plus — prefix with `m4 ` |
| Missing coverage / SEH error | Hidden memory fault — see GTF troubleshooting; check uninit pointers |

---

### Capability 7 — Read / Write / Breakpoint (Bench B, `tviic_6m_endprod`, portable auto-detect)

Same operations as Capabilities 2-4, but for the triple-core `tviic_6m_endprod` bench, using
the `$projectRoot`/`$bRoot` auto-detect from Capability 1 and the `m7_0`/`m7_1` core prefix
instead of the `m4` alias. **`switch -component` gets PERMANENTLY stuck in cm0plus on this
bench** (not just "doesn't redirect this command" as on Bench A) — always prefix every
app-core command with `m7_0 ` (or `m7_1` for the second core).

### Read Variable

```powershell
$varName  = "FSM_u16WatchdogResetInfo"   # <-- change this

Stop-Process -Name "multi","mpserv" -Force -ErrorAction SilentlyContinue
Remove-Item "$buildDir\read_var_out.txt" -ErrorAction SilentlyContinue

Set-Content "$buildDir\read_var.rc" @"
wait -time 3000
python -b -f ../../app/variants/tviic_6m_endprod/debug/tvii_debug_6mb.py VERIFY
wait -time 90000
m7_0 mprintf("$varName = %d (0x%X)\n", $varName, $varName)
target gc
wait -time 1000
quit
"@ -Encoding ASCII

$ghsEnv = "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/bceabf/1:/d/.conan/short/bceabf/1/_ide:`$PATH'"
& "C:\Program Files\Git\bin\bash.exe" -c "$ghsEnv; cd $bRoot/build/tviic_6m_endprod.Debug && /d/.conan/short/bceabf/1/_ide/multi -nosplash -servertimeout 300 debug.ghsmc -R read_var_out.txt -p read_var.rc 2>&1" | Out-Null
Get-Content "$buildDir\read_var_out.txt" -ErrorAction SilentlyContinue | Select-String $varName
```

For a runtime variable set only after boot, release the cores first (`target gc`, wait ~1s,
`m7_0 halt`, read, `m7_0 c`) instead of reading immediately at the `Startup_Init` halt.

### Write Variable

```powershell
$varName  = "g_WdgM_SE_Status"   # <-- change this
$value    = "1"                  # <-- change this

Stop-Process -Name "multi","mpserv" -Force -ErrorAction SilentlyContinue
Remove-Item "$buildDir\write_var_out.txt" -ErrorAction SilentlyContinue

Set-Content "$buildDir\write_var.rc" @"
wait -time 3000
python -b -f ../../app/variants/tviic_6m_endprod/debug/tvii_debug_6mb.py VERIFY
wait -time 90000
m7_0 mprintf("Before: $varName = %d\n", $varName)
m7_0 $varName = $value
m7_0 mprintf("After:  $varName = %d\n", $varName)
target gc
wait -time 1000
quit
"@ -Encoding ASCII

$ghsEnv = "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/bceabf/1:/d/.conan/short/bceabf/1/_ide:`$PATH'"
& "C:\Program Files\Git\bin\bash.exe" -c "$ghsEnv; cd $bRoot/build/tviic_6m_endprod.Debug && /d/.conan/short/bceabf/1/_ide/multi -nosplash -servertimeout 300 debug.ghsmc -R write_var_out.txt -p write_var.rc 2>&1" | Out-Null
Get-Content "$buildDir\write_var_out.txt" -ErrorAction SilentlyContinue | Select-String $varName
```

> **GRTL write syntax on this bench:** `m7_0 VAR = VALUE` — **NOT** `m7_0 set VAR = VALUE`
> (`set` is parsed as an expression keyword and fails).

### Breakpoint + Print + Continue

```powershell
$funcName = "Mcu_PerformReset"      # <-- function to break on
$varName  = "EXEA__u32RecordCntr"   # <-- variable to print

Stop-Process -Name "multi","mpserv" -Force -ErrorAction SilentlyContinue
Remove-Item "$buildDir\bp_out.txt" -ErrorAction SilentlyContinue

Set-Content "$buildDir\bp.rc" @"
wait -time 3000
python -b -f ../../app/variants/tviic_6m_endprod/debug/tvii_debug_6mb.py VERIFY
wait -time 90000
m7_0 hardbrk rolling $funcName { mprintf("=== BP: $funcName ===\n"); mprintf("$varName = %d (0x%X)\n", $varName, $varName) }
target gc
wait -time 30000
quit
"@ -Encoding ASCII

$ghsEnv = "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/bceabf/1:/d/.conan/short/bceabf/1/_ide:`$PATH'"
& "C:\Program Files\Git\bin\bash.exe" -c "$ghsEnv; cd $bRoot/build/tviic_6m_endprod.Debug && /d/.conan/short/bceabf/1/_ide/multi -nosplash -servertimeout 300 debug.ghsmc -R bp_out.txt -p bp.rc 2>&1" | Out-Null
Get-Content "$buildDir\bp_out.txt" -ErrorAction SilentlyContinue | Select-String "BP:|$varName"
```

> On this bench a rolling `hardbrk` callback does **NOT** need a trailing `go` — rolling
> breakpoints auto-continue. Adding `; go` fails with `Unknown name "go" in expression`.

### Critical GRTL Facts specific to Bench B

| Rule | Detail |
|------|--------|
| `switch -component` after VERIFY | Permanently stuck in cm0plus — **always use the `m7_0`/`m7_1` prefix**, not just "prefer" it |
| `m7_0 VAR = VALUE` | Correct write syntax — NOT `m7_0 set VAR = VALUE` |
| VERIFY is non-blocking | `python -b -f ... VERIFY` returns immediately — add `wait -time 90000` after it |
| `servertimeout` | Must be `300`, not `60`/`120` — to survive the 90s VERIFY + Python script runtime safely |
| `& disown; exit` in bash | Unreliable — **NEVER use Start-Process** either (`mpserv` fails to acquire the probe without terminal context) |
| **Run Multi via `& bash -c "..."`** | The ONLY reliable way: `& "C:\Program Files\Git\bin\bash.exe" -c "$ghsEnv; cd ... && multi ... 2>&1"` in the **foreground** of a PowerShell terminal, or inside `Start-Job` |
| `econ_config.sh` constraint | Reads stdin — never use inside multiline heredoc; always single-line `-c "..."` |
| `print()` in GHS Multi Python | `print()` output is NOT captured in `-R` log — use `debugger.RunCommands('mprintf("...")')` or write to a hardcoded absolute file path via `open(path, "a")` |
| `__file__` in GHS Multi Python | Unreliable when invoked with `-b -f script.py` from an `.rc` file — use **hardcoded absolute paths** for output files |
| Rolling breakpoint `go` keyword | `hardbrk rolling FUNC { mprintf("..."); go }` — **`go` is invalid** in GHS Multi expression context; rolling breakpoints auto-continue, remove `; go` entirely |
| NOINIT SRAM write | `m7_0 *(unsigned char*)0xADDRESS = VALUE` — direct byte write while target is halted at `Startup_Init` |
| NOINIT SRAM read | `m7_0 target mr 1 0xADDRESS` — read 1 byte; parse value after the last `:` in `cmdExecOutput` |
| `target gc` in Python | `debugger.RunCommands("target gc")` — not `go` |

### Error Handling

| Issue | Action |
|-------|--------|
| Variable not found | Symbol not in `cm7_0` — try the `m7_1` prefix (second core) |
| Value 0 for a runtime var | Used the NOINIT (immediate-read) pattern — release the cores first, then halt and read |
| Write ignored | Variable may be const or in flash ROM |
| Multi exits in <5s | Used `Start-Process` — switch to `& bash -c "..."` in the foreground, or `Start-Job` |
| No output in `-R` log from Python | Used `print()` — switch to `open(path,"a").write()` + `mprintf` via `debugger.RunCommands` |
| `Unknown name "go" in expression` | Remove `; go` from the rolling breakpoint callback — rolling breakpoints auto-continue |

---

### Capability 8 — Automated Multi-TC Test Execution (Bench B)

For running multiple test cases sequentially against a live ECU (e.g. JIRA test campaigns).

### Pattern: Start-Job + `& bash` (REQUIRED — NOT Start-Process)

```powershell
# --- configure for your project ---
$buildDir = "$projectRoot\build\tviic_6m_endprod.Debug"   # from Capability 1 detection block
$bash     = "C:\Program Files\Git\bin\bash.exe"
$ghsEnv   = "export GHS_LMHOST='@ls-ghs-sg-1.int.automotive-wan.com'; export GHS_LMWHICH='ghs'; export PATH='/d/.conan/short/bceabf/1:/d/.conan/short/bceabf/1/_ide:`$PATH'"
$tcList   = @('TC01','TC02','TC03')   # <-- list your TCs
$timeout  = 210   # seconds per TC
# ----------------------------------

foreach ($tc in $tcList) {
    $i = $tc -replace '\D',''   # extract numeric suffix for .rc filename
    Stop-Process -Name "multi","mpserv" -Force -EA SilentlyContinue
    Start-Sleep -Seconds 3
    Remove-Item "$buildDir\${tc}_result.txt" -EA SilentlyContinue

    $bashCmd = "$ghsEnv; cd $bRoot/build/tviic_6m_endprod.Debug && /d/.conan/short/bceabf/1/_ide/multi -nosplash -servertimeout 300 debug.ghsmc -R ${tc}_out.txt -p tc${i}.rc 2>&1"
    $job = Start-Job -ScriptBlock { param($b,$cmd); & $b -c $cmd } -ArgumentList $bash, $bashCmd

    # Poll for END marker in result file (no $using: — use captured $buildDir)
    $elapsed = 0
    while ($elapsed -lt $timeout) {
        Start-Sleep 10; $elapsed += 10
        $rf = "$buildDir\${tc}_result.txt"
        if ((Test-Path $rf) -and (Get-Content $rf -Raw) -match "END ===") { break }
        if ($job.State -eq 'Completed') { break }
    }
    Receive-Job $job -EA SilentlyContinue | Out-Null
    Remove-Job $job -Force -EA SilentlyContinue
    Stop-Process -Name "multi","mpserv" -Force -EA SilentlyContinue

    if (Test-Path "$buildDir\${tc}_result.txt") { Get-Content "$buildDir\${tc}_result.txt" }
    else { Write-Host "$tc NO RESULT" }
}
```

> **Why NOT `Start-Process`?** It spawns bash without inheriting the terminal's process group —
> `mpserv` cannot acquire the SWD probe and Multi exits silently in <5s. Always run Multi as
> foreground `& bash -c "..."` — either directly (blocks) or inside `Start-Job` (for timeout
> control).

> **Why NOT `$using:var` in while-loop?** `$using:` is only valid inside a
> `Start-Job`/`Invoke-Command` ScriptBlock. Use plain `$var` in the outer polling loop.

### GHS Multi Python script template

See `.github/scripts/debug_traveo_ghs/tc_runner.py` — invoke from the `.rc` as
`python -b -f tc_runner.py <TC_ID> <RESULT_DIR_WIN>`. Rules baked into the template:

1. NEVER use `print()` — not captured in the `-R` log.
2. NEVER use `__file__` — unreliable with `-b -f`.
3. NEVER put `; go` in a rolling breakpoint callback — rolling auto-continues.
4. Always resume with `debugger.RunCommands("target gc")` — not `"go"`.
5. Pass the result dir as `argv[2]` so the script stays project-agnostic.

### `.rc` script template

```
wait -time 3000
python -b -f ../../app/variants/tviic_6m_endprod/debug/tvii_debug_6mb.py VERIFY
wait -time 90000
python -b -f tc_runner.py TC01 D:\path\to\build\dir
wait -time 30000
quit
```

> The trailing `wait -time 30000` after the Python invocation acts as a safety net for
> Multi's script sequencer. Adjust to match your longest expected TC runtime.

---

## Outputs

Every capability writes its evidence to a `-R <name>_out.txt` playback log in the build
directory (`$buildDir\*_out.txt`) — filter out the harmless cm0plus `INCOHERENT` VERIFY dump
with `Where-Object { $_ -notmatch "INCOHERENT" }` before inspecting. Read/write capabilities
report the variable's value via `print`/`mprintf` lines in that log; breakpoint capabilities
report register values (`$r0`-`$r3`, `$lr`) at the hit; the automated multi-TC capability
(8) additionally writes a per-TC `${tc}_result.txt` with an `END ===` completion marker.

## Resources

Location: `.github/scripts/debug_traveo_ghs/`

- `README.md` — index of every script here: purpose, bench (A/B), generic-vs-hardcoded, and a
  "writing a new test" recipe + the Bench-A MULTI gotchas (start here)
- `run_debug_rc.ps1` — **generic runner** for ANY `.rc` playback on Bench A (`cm4`): exports
  `TVII_SKIP_VERIFY=1`, time-boxes `multi`, and FAILS FAST on MULTI errors; parameterized
  (`-Rc`,`-Variant`,`-Repo`,`-GhsConanPath`,`-SuccessMarker`,`-TimeoutSec`). Use this to run
  read/write/breakpoint/state-machine `.rc` files instead of a bespoke per-module runner
- `flash_ghs_retry.ps1` — resilient `run.py <variant> flash_ghs` with auto cleanup + retry on transient probe glitches, project-agnostic (auto-detects repo root + git-bash); use for ANY variant/bench (Capability 1)
- `setup.ps1` — one-command CANoe start + flash + VERIFY/`target gc`, auto-detects project root (Capability 1)
- `flash_openocd.ps1` — OpenOCD/KitProg3 flash fallback when the GHS probe is unavailable (Capability 1)
- `read_var.rc` — generic GHS Multi `.rc` template for reading a variable, Bench B/`m7_0` (Capability 7)
- `write_var.rc` — generic GHS Multi `.rc` template for writing a variable, Bench B/`m7_0` (Capability 7)
- `breakpoint.rc` — generic GHS Multi `.rc` template for a print-and-continue breakpoint, Bench B/`m7_0` (Capability 7)
- `tc_runner.py` — GHS Multi Python template for automated multi-TC execution (Capability 8)
- `hud_tc_runner.ps1` + `hud_tc0{1,2,3}.rc` — worked Bench-A example: a per-module state-machine
  test set (AmmSM/HUD) with state-name decode + retry; copy this pattern for new modules
