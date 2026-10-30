---
name: debug_lauterbach_py
description: >-
  Headless, Python-only control of Lauterbach TRACE32 for a Traveo II (or similar) target. Two
  paths: (1) PREFERRED - LAUNCH TRACE32 yourself with lauterbach-trace32-pystart + RCL enabled,
  then drive the full AMP master/slave flash+start flow over the Remote API (t32py_pystart.py,
  bench-verified working 2026-08-07); (2) legacy ctypes/t32api64.dll binding that ATTACHES to an
  already-running RCL-enabled session (t32py_client.py). Use for: flashing SFLASH/HSM/FBL/App and
  starting both cores headlessly; scriptable reads/writes/breakpoints/PRACTICE; live flash status;
  proper power-off that releases the USB PODBUS device. The pystart path SOLVES the old blocker
  (the project's `run.py ... debug_trace32` launch has no RCL listener to attach to) by launching
  TRACE32 with RCL turned on instead of attaching.
argument-hint: 'variant=<name> op=connect|breakpoint|read|write|eval|practice [--function F] [--variable V] [--value N] [--expression E] [--script S] [--simulate]  |  pystart: python t32py_pystart.py [--shutdown|--connect-only|--no-start] [--set-break SYM] [--read VAR] [--write VAR=VAL] [--do-app CMM] [--variant V]'
metadata:
  author: "Zhao Jianbo"
  version: "2.2.0"
  source: "Lauterbach manuals: Controlling TRACE32 via Python 3 (app_python.pdf); lauterbach-trace32-pystart / -rcl. Bench-verified on tviib_e4m_aravalli_s3p (CYT2BL7CAE, LA-3770 USB)."
---

# Lauterbach TRACE32 control via Python (TRACE32 Remote API / RCL)

## Overview

This skill drives TRACE32 **headlessly from Python**. There are two independent paths:

- **PREFERRED (pystart launch + RCL) - `t32py_pystart.py`**: launches TRACE32 itself via
  `lauterbach-trace32-pystart` with the RCL interface enabled, so there is always a live Remote
  API to drive. This is what makes the project's **AMP master/slave flash+start flow work
  headlessly** - it does the full `cyt2bl_flash_e4M.cmm` (reset -> erase -> program
  SFLASH/HSM/FBL/App -> spawn + attach the CM4 slave) and starts both cores. **Bench-verified
  working 2026-08-07.**
- **Legacy (ctypes attach) - `t32py_client.py`**: uses the `t32api64.dll` ctypes binding to
  *attach* to an **already-running, RCL-enabled** TRACE32 session. Needs no pip install but
  cannot start its own RCL listener - see the historical note below for why that path could not
  reach this project's AMP session.

> **Status update (2026-08-07): the AMP flow now WORKS via the pystart path (`t32py_pystart.py`).**
> The earlier "NOT usable" verdict applied only to the *attach* approach, which required an RCL
> block in the project's launch config that gets regenerated on every launch. The fix was to stop
> trying to attach and instead **launch TRACE32 from Python with RCL enabled** - pystart builds
> its own config with RCL on, bypassing the regenerated-temp-config problem entirely. See
> "Working AMP flow (pystart)" below. The historical attach findings are retained further down for
> context.

<details>
<summary>Historical: why the legacy <em>attach</em> path could not reach this project's AMP session (2026-08-05)</summary>

> **Status (attach path, bench-verified 2026-08-05, conclusive): NOT usable for this project's AMP
> session - the launch mechanism makes RCL config injection impractical. Use the pystart path or
> `debug_traveo_lauterbach`.**
> Findings from the real-hardware comparison test against `debug_traveo_lauterbach`:
> 1. **Fixed a real bug**: `t32api64.dll` is NOT shipped next to `t32marm.exe`
>    (`bin\windows64\`) in this project's conan-packaged TRACE32 install - that folder only has
>    hostmci/libusb/t32cadi/etc. The DLL actually lives under
>    `demo\api\python\legacy\t32api64.dll` (or `demo\api\capi\dll\t32api64.dll`).
>    `t32py_config.py`'s `t32_dll_path()` now searches both locations (and honors a new
>    `T32PY_DLL` env var override); this was a genuine blocker, now resolved.
> 2. **Confirmed the AMP gap is real**: after fixing #1, attaching (`t32py_run.py --op read`)
>    against a normally-launched session (`python run.py <variant>.Debug debug_trace32`, per the
>    HARD RULE) fails with `T32_Init() failed, rc=-1` - the standard project launch config does
>    **not** contain an `RCL=NETASSIST`/`PORT=20000` block, so there is nothing for this skill to
>    attach to today.
> 3. **Tried injecting RCL without touching the launch mechanism** (kept 100% HARD-RULE compliant
>    - still only `Start-Trace32.ps1` / `python run.py ... debug_trace32`): found the SLAVE
>    (CM4) core's `-c` config file at `build/<variant>.Debug/T32_M4.t32` and appended the RCL
>    block to it, then relaunched via `Start-Trace32.ps1`. **Both AMP windows still came up with
>    the correct chip/arch titles - gotcha #2's "wrong-architecture session" failure was NOT
>    reproduced this time.** However, `T32_Init()` still failed - `netstat`/`Test-NetConnection`
>    confirmed nothing was ever listening on port 20000. Root cause: `Get-CimInstance
>    Win32_Process -Filter "Name='t32marm.exe'"` showed the SLAVE is actually launched with
>    `-c C:\Users\<user>\AppData\Local\Temp\T32_M4.t32` - a **different, dynamically regenerated**
>    file in the Windows Temp folder (fresh contents/conan-hash every single launch), NOT the
>    persistent copy under `build/<variant>.Debug/`. Editing the build-dir copy is a no-op; the
>    live file is regenerated (without any RCL block) by the conan `templates_trace32` package's
>    internal logic on every launch, before this skill (or any repo-level script) gets a chance to
>    touch it. The **MASTER** core, for reference, is launched with no `-c` flag at all (just
>    `-s <startup.cmm> <abs>`), so it has no config file to inject RCL into either.
> - **Verdict (final)**: `debug_lauterbach_py` cannot be made to work against this project's AMP
>   session without modifying the vendor `templates_trace32` conan package itself (out of scope -
>   don't attempt to patch a conan-cached vendor package). There is no supported, repo-level way
>   to get an RCL listener into this project's AMP launch today. Use `debug_traveo_lauterbach`
>   (GUI automation) as the only working method for this project's AMP session.
>   `debug_lauterbach_py` remains valid for a flash-only/single-instance session (matches the
>   already-proven `t32rem` flash-only flow, gotcha #13) - just not for AMP master+slave here.

</details>

## Working AMP flow (pystart) - `t32py_pystart.py`  ✅ bench-verified 2026-08-07

The breakthrough that made the AMP flow work headlessly: **stop trying to attach to the project's
launch; launch TRACE32 from Python instead, with RCL enabled.** `t32py_pystart.py` uses
`lauterbach-trace32-pystart` to spawn the MASTER PowerView with an `RCLInterface(port=20000)`, so
pystart writes its own config with RCL on - there is nothing to inject and no regenerated temp
config to fight. The single MASTER RCL connection then drives the whole AMP session; the CM4
SLAVE1 is spawned by the project's own CMM (`TargetSystem.NewInstance M4`) and commanded via
`InterCom M4 ...` over that same connection.

### Install (one time)

```powershell
python -m pip install --user lauterbach-trace32-pystart lauterbach-trace32-rcl pywin32
```

(`pywin32` is optional - only used to detect the modal PODBUS "device already used" dialog.)

### Run

```powershell
# Prereq: CANoe running, KL15 ON, probe connected, target powered.
$env:LT_VARIANT = 'tviib_e4m_aravalli_s3p'
cd <repoRoot>\.github\scripts\debug_lauterbach_py

python t32py_pystart.py                 # full flow: launch -> flash (SFLASH/HSM/FBL/App) -> Go both cores; KEEP OPEN
python t32py_pystart.py --shutdown       # same, but proper SYStem.Down + QUIT power-off at the end
python t32py_pystart.py --connect-only   # launch + connect + report status, then clean power-off
python t32py_pystart.py --no-start       # launch + flash, but leave cores halted
python t32py_pystart.py --variant <name> # override $LT_VARIANT

# Debug ops (after start) - app-core breakpoints + variable read/write, all repeatable:
python t32py_pystart.py --set-break AmmSM_vMainFunction `
                        --read AmmSM__enCurrentMode --read AmmSM__enReqMode `
                        --write AmmSM__enReqMode=2

# Breakpoint + call stack (current function + immediate caller):
python t32py_pystart.py --set-break EyeBSM__boGetShutdownFlag --stack
```

**Default is KEEP-OPEN**: on success the session (both cores running) is left up and only the RCL
automation link is dropped, so you can debug interactively. The **next** launch cleanly `QUIT`s
that left-open instance first (pre-launch graceful cleanup), so the USB device is still released
properly - you do **not** need `--shutdown` between runs. Use `--shutdown` for a one-shot
flash-and-power-off (CI); `--connect-only` always shuts down. On **failure** it always performs a
proper `SYStem.Down` + `QUIT` so the USB PODBUS device is released cleanly (see gotcha "device
already used").

### Programmatic status checks (PREFERRED over screenshots) - `--attach`

**Always verify state via this Python/RCL path, not via `debug_traveo_lauterbach`'s screenshots,
whenever a session is already up.** Screenshot-based GUI inspection (the other skill) should only
be used as a fallback when this skill genuinely can't apply (e.g. `lauterbach-trace32-pystart`/
`-rcl` can't be installed on this machine) - not as the default status-check method.

```powershell
# Attach to an ALREADY-RUNNING (keep-open) session - NO reflash, no GUI, no screenshot:
python t32py_pystart.py --attach --read SysCtlSM__enCurrentState
python t32py_pystart.py --attach --read MyVar1 --read MyVar2 --write MyFlag=1
```

`--attach` connects straight to the RCL port (`$T32PY_PORT`, default `20000`) of a session left
open by a previous run, runs whatever `--read`/`--write`/`--set-break`/`--stack` ops you pass, and
disconnects (leaving TRACE32 running) - it never launches or flashes. This is the lightest-weight
way to answer "is the software still running?" / "what's the current state?" without a full
flash cycle and without a single screenshot.

If you need to check state programmatically without even `t32py_pystart.py`'s CLI overhead
(e.g. from an ad-hoc one-off script), you can connect directly:
```python
import lauterbach.trace32.rcl as t32api
dbg = t32api.connect(node='localhost', port=20000)
print(dbg.fnc('Var.VALUE(SysCtlSM__enCurrentState)'))   # e.g. 1 = Running
print(dbg.fnc('STATE.RUN()'))                            # True while the core is executing
```
Bench-verified 2026-08-12: this reconnects to an already-open pystart-launched session (same RCL
port) without disturbing it or requiring a reflash.

### Debug ops - breakpoints, read, write (bench-verified 2026-08-07)

| Flag | Targets | Mechanism |
|------|---------|-----------|
| `--set-break SYM` | CM4 app core | `InterCom M4 Break.Set SYM` - the breakpoint must halt CM4 execution, so it's set on the app-core slave. Example: `AmmSM_vMainFunction` (the Amm state-machine main), `EyeBSM__boGetShutdownFlag`. |
| `--read VAR` | app variable | Loads the app ELF **symbols only** into the MASTER (`Data.LOAD.Elf <abs> /NoCODE /NoRegister /NoClear`), then `dbg.fnc("Var.VALUE(VAR)")`. The CM0+ master shares the memory bus with CM4, and the CMM enables `SYStem.Option DUALPORT ON`, so run-time reads work while the app runs. |
| `--write VAR=VAL` | app variable | `Var.Set VAR=VAL` (numeric literal, no spaces around `=`) then reads it back to confirm. Verified: `AmmSM__enReqMode=2 -> read back 2`. |
| `--stack` / `--stack-frames N` | CM4 app core | Waits (up to 30s) for the app core to halt (`STATE.RUN()` via `PRINT`+`AREA` on the slave), then reports the call stack via `get_call_stack()` - see "Call stack capture" below. |
| `--do-app CMM` (repeatable) / `--do-timeout S` | CM4 app core | Runs a **Debug Test Case** script compiled by the `debug-test-cases` skill (`dtc_tool.py compile --target t32`) via `InterCom M4 DO "<cmm>"`, then polls the AREA log the script opens for `DTC\|<id>\|END` / `ABORT` (timeout → `END` + `AREA.CLOSE` on the slave). Exit code 4 if any script aborted or timed out; the session is still kept open. Not yet bench-verified. |

> Reads/writes go through the **master** RCL connection (symbols loaded there); breakpoints go to
> the **app core** via InterCom. There is only one RCL connection (to the master) - the CM4 slave
> is driven by `InterCom M4 ...`, and app variables are reached via the shared memory bus rather
> than a second RCL port.

### Call stack capture (bench-verified 2026-08-07)

The obvious approaches **do not work** on this TRACE32 build/target:
- `Frame.List` is not a recognized command ("unknown command"); the correct name is bare `Frame`
  - but `Frame` is a **GUI window** command, so its output never flows through `AREA.OPEN
  "<file>" /Create` text redirection (the file always comes back empty).
- The high-level unwind functions `FRAME.COUNT()` / `FRAME.FUNCTION(n)` / `FRAME.ADDRESS(n)` /
  `ADDRESS.FUNCTION(addr)` **do not exist** on this build ("no function ... exists" - likely no
  HLL stack-unwind feature/license here).

**What actually works** - `get_call_stack()` in `t32py_pystart.py` uses `PRINT "...",<expr>`
(a genuine text-stream command, unlike the `Frame` window command) redirected through
`AREA.OPEN "<file>" /Create`, forwarded to the CM4 slave via InterCom, evaluating:
- `Register(PC)`, `Register(LR)`, `Register(SP)` - raw register values.
- `sYmbol.NAME(P:0x<addr>)` - resolves an address to its function name.
- `STATE.RUN()` - halt detection (`FALSE` = halted); polled before reading registers.

This reliably yields a **2-frame** call stack: `#0` = currently-halted function (from PC),
`#1` = its immediate caller (from LR). Example (`EyeBSM__boGetShutdownFlag`):
```
SP=0x800C3D0
#0 (current) PC=0x100C9810  EyeBSM__boGetShutdownFlag
#1 (caller)  LR=0x100C6C25  EyeBSM_vMainFunction
```

**Deeper frames are NOT reliable.** A manual stack-scan (`Data.Long(D:Register(SP)+offset)` over
many words, filtering for odd/thumb-bit addresses in the app's code range, resolved via
`sYmbol.NAME`) was tried as a heuristic extension: the word immediately after LR often resolves to
a plausible next ancestor (e.g. `Os_Entry_Task_ASW_Mid`, the OS task entry - seen consistently as
the LR-caller of every `*_vMainFunction` breakpoint too), but words further up the stack quickly
turn into unrelated/bogus symbols (leftover stack content from earlier, unrelated calls - e.g.
`ComM_EvaluateChannel`, `BswM_ExecuteActionList` showed up for an EyeBSM breakpoint). **Do not
present a scanned "full backtrace" as fact** - without real unwind tables there's no reliable way
to distinguish a genuine saved return address from stack garbage past the first 1-2 words.

**Gotcha - stale breakpoints steal the halt**: breakpoints persist across script runs as long as
the session stays open (default keep-open). If an old breakpoint on a frequently-called function
(e.g. `IllumSM_vMainFunction`, called every cycle) is still armed, `Go` will re-hit it BEFORE a
newly-armed, rarer breakpoint - and `get_call_stack()` will silently report the wrong function.
Always `InterCom <slave_alias> Break.Delete /ALL` before arming a new breakpoint for an isolated
test, unless multiple breakpoints are intentionally wanted.

### What it does, step by step

1. **Sweep** any TRACE32 left running by a previous run and shut it down **gracefully over RCL**
   (`SYStem.Down` + `QUIT`, which releases the PODBUS USB lock), force-killing only a wedged
   instance that has no RCL. Then launch the MASTER via pystart (`USBConnection`, `t32marm`,
   unique per-run `id`/`title`, `RCLInterface(port=20000)`).
2. **Actively poll** the RCL TCP port (no blind sleep); if it never opens, report the exact
   fatal cause (see "How to read status/errors from Python").
3. **Connect** RCL (retries; `timeout=180` so long AMP commands don't spuriously time out).
4. **Settle** ~12s for the debug HW, then run the project CMM **non-blocking** (`DO`) and poll
   `PRACTICE.SD()` to completion, **streaming live status** (`state=...` + TRACE32 message line).
   Fails fast if the MASTER never leaves `system down`; auto-retries once (reset + rerun).
5. **Start**: wait for the CM4 slave to be InterCom-responsive, delete the default post-flash
   breakpoints, `Go` the slave (app core), then `Go` the master (CM0+).
6. **Optional debug ops** (`--set-break`/`--read`/`--write`), then **keep open** (default) or
   proper power-off (`--shutdown`/`--connect-only`/failure).

### How to read status/errors from Python (the two phases)

| Phase | What's available | API |
|-------|------------------|-----|
| **After RCL connects** (target attached) | live run-state + message line | `dbg.get_state()` (0 down / 1 halted / 2 stopped / 3 running), `dbg.get_message()` -> `(text, type)` with error bit `0x2`, `dbg._get_practice_state()`, `dbg.fnc("SYStem.MODE()")`, `dbg.fnc("STATE.RUN()")` |
| **Before RCL is up** (fatal startup dialogs, e.g. PODBUS "device already used") | invisible to RCL - use the process/console instead | `powerview._process.poll()` (alive/exit code); pystart pipes t32marm console to loggers `lauterbach.trace32.pystart.stdout/stderr` (the script attaches a `_FatalLogCatcher`); `win32gui` window scan (`_detect_fatal_dialog_windows`) as a backstop |

> `dbg.get_state()` and some `dbg.fnc(...)` results come back as little-endian `bytes`/`bytearray`,
> not `int` - always normalize with `_as_int()` before comparing/using as a dict key, or you get
> `unhashable type: 'bytearray'`.

### Gotchas specific to the pystart AMP flow (bench-learned 2026-08-07)

1. **"TRACE32 device already used by other GUI"** is a **driver-level PODBUS lock**, not just a
   process. **Force-killing `t32marm` frees the process but NOT the lock** - only TRACE32's own
   `SYStem.Down`/`QUIT` releases the USB device. If a prior run is force-killed instead of
   properly QUITting, the next launch fails with this dialog **even with zero processes running**
   - if that happens, only an elevated PnP device reset or a physical probe power-cycle clears it
   (the script's `_reset_podbus_usb()` attempts this automatically but needs admin rights).
   => Always let the script power off (`graceful_shutdown()` / the default keep-open + next-launch
   cleanup) rather than closing the process from Task Manager.
2. **`InterCom name M4 already exists`**: do **not** add a pystart `IntercomInterface` - the CMM's
   `TargetSystem.NewInstance M4` already sets up the AMP slot. An explicit `IntercomInterface`
   pre-claims the `M4` name so `NewInstance` fails and every `InterCom M4 ...` returns
   "no response from InterCom". Leave `T32PY_INTERCOM_PORT` unset.
3. **"no response from InterCom"** right after attach is usually a **transient** timing hiccup: the
   slave instance exists (`INTERCOM.PING(M4)` may flip) but isn't ready. Wait for it to be
   *responsive* (poll `INTERCOM.PING`) + a short settle before sending it commands, and retry the
   command on this message rather than aborting. (If it's *persistent* with the MASTER stuck
   `system down`, that's an attach failure, not this - check KL15/power.)
4. **MASTER stuck at `system down` for the whole run** = the debugger never attached (SYStem.Up
   failed). The app never flashes. Almost always **target not powered / KL15 OFF** or the probe
   didn't connect. The script fails fast after `SYSTEM_UP_GRACE` (30s) instead of idling.
5. **Don't drive the CMM too early**: the RCL port opens seconds before the debug HW is ready;
   the ~12s `POST_CONNECT_SETTLE` before flashing avoids an attach miss.
6. **CMM working directory must be `app/variants`** (exactly 2 segments below repo root): the CMM
   uses `../../build/...` and `../../app/variants/common/...` relative paths.
7. **Success leaves the GUI running by default** (keep-open) - do NOT `powerview.wait()` (it
   blocks forever, and if a fatal dialog is up it hangs). pystart does not kill the child when
   Python exits (no atexit hook), so exiting the script leaves the debugger up cleanly. The next
   launch's pre-launch cleanup gracefully QUITs it first.
8. **CMM script discovery must try MULTIPLE folder conventions - do not hardcode one project's
   layout.** `RuntimeConfig._discover_cmm()` used to hardcode
   `app/variants/<variant>/debug/Lauterbach/` (correct for `tviib_e4m_aravalli_s3p`, the original
   bench-verified project) with no fallback - this broke immediately on `tviib_2m_aravalli_s3p`,
   whose scripts actually live under `app/variants/<variant>/source/Lauterbach_scripts/` (the
   SAME convention `debug_traveo_lauterbach/config.ps1`'s `Find-StartupScript` already used).
   Fixed (2026-08-12): `_discover_cmm()` now tries `t32py_config.py`'s own
   `resolved_startup_script()` first (which also honors `LT_STARTUP_SCRIPT` if set), THEN falls
   back to the old `debug/Lauterbach` layout, and only raises `ConfigError` (asking the user to
   set `T32PY_CMM` explicitly) if NEITHER convention matches. If you add support for a third
   project with yet another layout, extend this same fallback chain rather than replacing it -
   and if you genuinely can't determine the right convention, the error message IS the
   "ask the user" fallback (it names both paths checked) - don't guess a new hardcoded path.
9. **The "Welcome to TRACE32!" onboarding modal appears on EVERY fresh launch** (MASTER at
   startup, and again on the AMP-spawned SLAVE) - even with its own "Show this dialog at start"
   checkbox already unchecked, since each launch gets a fresh temp profile/config dir.
   **CORRECTED (2026-08-12, same day, after further bench testing): this dialog IS NOT purely
   visual - it genuinely BLOCKS TRACE32's own command/message processing, which blocks RCL calls
   (`dbg.get_message()`/`dbg.fnc()`) made from the same thread.** A live run stalled 100+ seconds
   with the main polling loop stuck on an RCL call, and resumed the instant the dialog was
   dismissed externally. (The earlier "proof" that it didn't block anything was flawed - that
   test always dismissed the dialog via PowerShell *before* querying state, so it never actually
   tested with the dialog still up.) Because of this:
   - Dismissal now runs on an **independent background daemon thread**
     (`_welcome_dialog_watcher`, started in `run_init_script`) polling every ~2s, NOT as a step
     inside the same RCL polling loop that could already be stuck on a prior blocking call in the
     same iteration (that placement is unreachable if the earlier call is what's hung).
   - The watcher's `win32com.client.Dispatch("WScript.Shell")` calls need
     `pythoncom.CoInitialize()`/`CoUninitialize()` around them, since a background thread never
     otherwise initializes COM - without this, `AppActivate`/`SendKeys` can silently misbehave
     (appear to succeed but not actually reach the window).
   - `_dismiss_welcome_dialog_windows()` (needs `pywin32`) does the actual ESC via
     `AppActivate`+`SendKeys("{ESC}")` - the only dismissal method proven reliable. Do not replace
     this with `WM_CLOSE`-by-window-title or a simulated mouse click on its visible X button; both
     were tried on the bench and found unreliable (the mouse click even mis-landed and toggled the
     checkbox back ON, from a DPI/logical-vs-physical coordinate mismatch).
10. **`Go` on the MASTER can fail with `('target running', ...)`** if the CMM's own `SYStem.Up`
    already brought it to a running state during the flash script (bench-verified: `STATE.RUN()`/
    `SYStem.UP()` both `TRUE` right after the CMM completes, before any explicit `Go`).
    `finish_startup()` now checks `dbg.get_state()` first and only issues `Go` on the MASTER if it
    isn't already running (code `3`) - treating "already running" as success, not a fatal error.

## Two ways Lauterbach supports Python (per the manual)

| Approach | Requires | Used here? |
|----------|----------|------------|
| `lauterbach.trace32.rcl` (PYRCL) | Python 3.6+, pip-install the wheel from `~~/demo/api/python/rcl/dist` | Not implemented (optional future upgrade - see "Extending to PYRCL" below) |
| **Legacy `ctypes` + `t32api64.dll`** | Nothing extra - the DLL ships in every TRACE32 install, but NOT always next to t32marm.exe - see bench-verified note above (this project: `demo\api\python\legacy\t32api64.dll`) | **Yes - `t32py_client.py`** |

The legacy approach was chosen for this skill because it needs zero extra installation and is
fully documented with concrete call sequences in the manual; PYRCL is functionally nicer but
adds a wheel-install dependency step that hasn't been validated on this network yet.

## Prerequisite: RCL must be enabled on the TRACE32 session

Every function in this skill talks to `T32_Init`/`T32_Attach`/`T32_Cmd`, which only work if the
config file the TRACE32 instance was started with contains:

```
RCL=NETASSIST
PACKLEN=1024
PORT=20000
```

(or `RCL=NETTCP` for TCP mode). Without this block, `T32_Attach` fails immediately - this is the
**same** requirement `t32rem.exe` has (see `debug_traveo_lauterbach/SKILL.md` gotchas #2, #13,
#14). Use `t32py_make_rcl_config.py` to produce an RCL-enabled copy of an existing project
config without touching the original.

## Target parameters

Reuses the **same `LT_*` environment variables** as `debug_traveo_lauterbach` (same project, same
variant/paths), plus new `T32PY_*` variables for the Remote API connection itself:

| Variable | Required? | Meaning | Default |
|----------|-----------|---------|---------|
| `LT_VARIANT` | **Yes** | Build variant name | - |
| `LT_VARIANT_CONFIG` | No | Build config suffix | `Debug` |
| `LT_STARTUP_SCRIPT` | No (auto-discovered) | PRACTICE startup/flash `.cmm` (only used with `--start`) | single `*.cmm` under `app/variants/<variant>/source/Lauterbach_scripts/` |
| `LT_ABS_FILE` | No (derived) | App ELF (`.abs`) path | `build/<variant>.<config>/bin/<variant>.abs` |
| `T32PY_NODE` | No | RCL host | `localhost` |
| `T32PY_PORT` | No | RCL port | `20000` |
| `T32PY_PACKLEN` | No | RCL packet length | `1024` |
| `T32PY_DEVICE` | No | `T32_Attach` device id (1 = TRACE32 debugger/simulator) | `1` |
| `T32PY_EXE` | No (auto-detected) | Full path to `t32marm.exe` | detected from a running process or `D:/C:/E:/.conan/short/*/1/bin/windows64/` |

## Implementation files

All under `.github/scripts/debug_lauterbach_py/` (Python 3).

| Script | Purpose |
|--------|---------|
| **`t32py_pystart.py`** | **PREFERRED / working AMP flow.** Launches TRACE32 via `lauterbach-trace32-pystart` with RCL enabled, then flashes (SFLASH/HSM/FBL/App via the project CMM) and starts both cores over one MASTER RCL connection. Live flash status, fast-fail attach detection + retry, fatal-startup capture, app-core breakpoints + variable read/write + call stack (PC/LR + `sYmbol.NAME`, 2-frame), graceful pre-launch cleanup, **keep-open by default** with proper `SYStem.Down`+`QUIT` power-off on `--shutdown`/failure. Needs `pip install lauterbach-trace32-pystart lauterbach-trace32-rcl` (+ optional `pywin32`). CLI: `--attach` (no-reflash status/read/write against an already-open session - PREFERRED for status checks), `--shutdown`, `--connect-only`, `--no-start`, `--set-break SYM`, `--read VAR`, `--write VAR=VAL`, `--stack`, `--stack-frames N`, `--do-app CMM` (run a compiled Debug Test Case on the app core), `--do-timeout S`, `--variant` |
| `t32py_config.py` | Reads `LT_*`/`T32PY_*` env vars; resolves repo root, build dir, `t32marm.exe` / system dir, `t32api64.dll` path (shared by both paths) |
| `t32py_client.py` | (Legacy attach path) `Trace32Client` - ctypes binding of `t32api64.dll` per the manual: connect/cmd/run_practice/eval_get/get_symbol/write_breakpoint/set_breakpoint/go/get_state/read_variable/write_variable. Event-driven polling, `simulate=True` for hardware-free dry runs |
| `t32py_start.py` | (Legacy) Launch `t32marm.exe -c <config> -s <startup>` if not already running; waits for the RCL port via a real TCP-connect poll |
| `t32py_make_rcl_config.py` | (Legacy) Copy a project `config.t32` and append an RCL block if missing (never edits the original) |
| `t32py_report.py` | `SessionRecorder` - per-step timing, console + JSON report |
| `t32py_run.py` | (Legacy attach path) CLI orchestrator: one connect→op→disconnect session per invocation; ops: `connect`, `breakpoint`, `read`, `write`, `eval`, `practice`; `--simulate` for a no-hardware dry run |
| `t32py_selftest.py` | Hardware-free validation of config resolution, the full simulated client call surface, report round-trip, and RCL-config generation |

## Usage

### Quick start (attach to an already-running, RCL-enabled TRACE32 instance)

```powershell
$env:LT_VARIANT = '<your-variant-name>'
cd <repoRoot>\.github\scripts\debug_lauterbach_py

# Read a variable
python t32py_run.py --op read --variable <YourVariable>

# Break on a function, run to it, read a variable while halted
python t32py_run.py --op breakpoint --function <YourFunction> --variable <YourVariable>

# Write a variable (NUMERIC ONLY - see gotcha below) and read it back
python t32py_run.py --op write --variable <YourVariable> --value 9

# Evaluate any TRACE32 function/expression
python t32py_run.py --op eval --expression "SOFTWARE.VERSION()"

# Run an arbitrary PRACTICE script and get its result message
python t32py_run.py --op practice --script "<path-or-alias>.cmm"
```

### Launching TRACE32 yourself first (higher risk on AMP - see prerequisite above)

```powershell
python t32py_make_rcl_config.py --src <path-to-project-config.t32> --dst rcl_config.t32
python t32py_run.py --op read --variable <YourVariable> --start --config-file rcl_config.t32
```

### No-hardware validation

```powershell
python t32py_selftest.py --variant <your-variant-name>
python t32py_run.py --op breakpoint --function Foo --variable Bar --simulate
```

## Gotchas (carried over from `debug_traveo_lauterbach` - still apply here)

1. **Write syntax**: `Var.Set <var>=9` - numeric literal, **no spaces around `=`**. Symbolic enum
   names or spaces silently fail the read-back. `t32py_client.write_variable()` already follows
   this; do not change it to accept spaces/symbolic names without re-verifying.
2. **RCL vs IC**: `RCL=NETASSIST`/`PORT=` is the Remote API used by this skill and `t32rem`; `IC`
   (InterCom) is a *different* setting used between TRACE32 instances in an AMP session. Setting
   only `IC=NETASSIST` will not make this skill connect.
3. **Cyclic overwrite**: read a variable back *before* `Go` if you need to prove a write, since a
   cyclic main-function may reassign it every cycle.
4. **Default breakpoints after flash**: the project's breakpoint macro typically arms a few
   safety/error-hook functions on the app core; `set_breakpoint()` already deletes any existing
   breakpoint on the same symbol first but does **not** clear unrelated default breakpoints -
   call `client.delete_all_breakpoints()` explicitly if you need a clean slate (the CLI's
   `--op breakpoint` does this automatically).
5. **AMP master/slave routing**: `T32_Attach`/RCL talks to **one** TRACE32 instance/window. On an
   AMP setup, make sure the RCL-enabled config/port belongs to the **application-core slave**
   session (the one holding your symbols), not the master.

## Extending to PYRCL (optional, not implemented here)

If you later want the modern `lauterbach.trace32.rcl` package instead of ctypes: locate the wheel
under `<T32_SYS>/demo/api/python/rcl/dist`, `pip install` it, then replace the body of
`Trace32Client.connect()`/`cmd()`/etc. with `lauterbach.trace32.rcl.connect(node=..., port=...)`
and `dbg.cmd(...)`/`dbg.fnc.eval(...)` calls - the manual documents PYRCL is a native
reimplementation of the same RCL protocol, so the config-file (`RCL=`) prerequisite is identical.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `T32_Attach(...) failed` | RCL not enabled on this TRACE32 session, or wrong port | Verify the session's config has `RCL=NETASSIST`/`PORT=<n>`; use `t32py_make_rcl_config.py` |
| `t32marm.exe not found` | Auto-detection failed | Set `T32PY_EXE` explicitly |
| `T32_Ping()` never succeeds (TimeoutError) | Wrong node/port, or firewall | Check `T32PY_NODE`/`T32PY_PORT`; confirm the port from the loaded config |
| `TRACE32 error message: ...` from `cmd()` | Command failed on target (manual's error type 2) | Message text from `T32_GetMessage` is included in the exception |
| Write didn't change the value | Used spaces + enum name | Use `Var.Set VAR=VALUE`, numeric, no spaces (already enforced by `write_variable`) |
| RCL port never accepts connections after `--start` | RCL config doesn't compose with the AMP startup script (unverified combination) | Bench-test the merged config standalone first; fall back to `debug_traveo_lauterbach` for AMP GUI automation |
| `variant is not set` error | `LT_VARIANT` not set | `$env:LT_VARIANT = '<your-variant-name>'` before running any script |

## Source

Based on Lauterbach's official manual **"Controlling TRACE32 via Python 3"** (`app_python.pdf`,
Release 02.2026) - the "TRACE32 Legacy Approach" chapter (pages 8-20), covering:
`T32_Config`/`T32_Init`/`T32_Attach`/`T32_Ping`/`T32_Exit`, `T32_Cmd`, `T32_GetPracticeState`,
`T32_GetMessage`, `T32_EvalGet`/`T32_EvalGetString`, `T32_GetSymbol`, `T32_WriteBreakpoint`,
`T32_Go`, `T32_GetState`, `T32_ReadVariableValue`.
