---
name: debug_traveo_lauterbach
description: >-
  Flash, debug, set breakpoints, and read/write runtime variables on a Traveo II
  (or similar multi-core AMP) target using Lauterbach TRACE32 (t32marm) instead
  of GHS Multi. Use when: the bench uses a Lauterbach probe (LA-3770 /
  CombiProbe / uTrace); opening the AMP master/slave PowerView; setting a
  breakpoint on an app-core function; reading or writing a runtime
  variable/enum; getting the call stack of a halted core; recovering when only
  a single blank PowerView opens. PROJECT-AGNOSTIC: the variant name, chip
  name and core/window titles are inputs the calling agent must supply (via
  environment variables) - they are never hardcoded. A fully worked example
  for one bench-verified project (variant `tviib_2m_aravalli_s3p`, chip
  `CYT2B93CAS`) is included at the end for reference.
argument-hint: 'Variant + action, e.g.: variant=tviib_2m_aravalli_s3p flash | breakpoint <func> | read <var> | write <var>=<value> | callstack'
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# Lauterbach TRACE32 for Traveo II / multi-core AMP targets

## Overview

Flashes and debugs a Traveo II (or similar multi-core AMP) target using Lauterbach TRACE32
(`t32marm`) instead of GHS Multi: opens the AMP master/slave PowerView, sets breakpoints on an
app-core function, reads/writes runtime variables, and dumps the call stack of a halted core.
This skill is **generic across projects/variants**. It does not hardcode any
variant name, chip name, or window title - those are project-specific inputs
that the calling agent (or user) must provide, typically as environment
variables consumed by `config.ps1`. See "Target parameters" below.

> **PREFER `debug_lauterbach_py` FOR STATUS CHECKS.** This skill drives TRACE32 by GUI keystroke
> automation and verifies state via **screenshots** - inherently slower and less reliable than a
> programmatic check. Whenever `lauterbach-trace32-pystart`/`-rcl` are available (see
> `debug_lauterbach_py/SKILL.md`), use `python t32py_pystart.py --attach --read <VAR>` (no
> reflash, no screenshot) to check "is it still running?" / read a variable. Reserve this skill's
> screenshot-based GUI automation for when the Python/RCL path genuinely isn't usable on this
> machine, or for operations it doesn't cover (e.g. visually inspecting `Frame.view` call-stack
> windows beyond the 2-frame PC/LR the Python path reports).

## Prerequisites

> **PREREQUISITE:** the target's power/wake input (e.g. CANoe KL15) is ON, and the
> Lauterbach probe (LA-3770 / CombiProbe / uTrace) is connected to the target's debug
> header with **target power ON**. Without power the debugger opens but cannot attach
> to the cores.

### Target Parameters (must be supplied per project)

Set these once per shell session **before** running any script in this
skill's `scripts/` folder (all scripts dot-source `config.ps1`, which reads
them):

| Variable | Required? | Meaning | Example (see "Worked example" below) |
|----------|-----------|---------|----------------------------------------|
| `LT_VARIANT` | **Yes** | Build variant name (folder under `app/variants/`, and the `build/<variant>.<config>` name) | `tviib_2m_aravalli_s3p` |
| `LT_VARIANT_CONFIG` | No (default `Debug`) | Build config suffix | `Debug` |
| `LT_MASTER_TITLE` | No (default `*MASTER*`) | Wildcard match for the master-core PowerView window title | `TRACE32 for ARM - CYT2B93CAS-CM0+ - MASTER` |
| `LT_SLAVE_TITLE` | No (default `*SLAVE*`) | Wildcard match for the application-core PowerView window title | `TRACE32 for ARM -CYT2B93CAS-CM4 - SLAVE1` |
| `LT_STARTUP_SCRIPT` | No (auto-discovered) | Path to the PRACTICE startup/flash `.cmm` script. Auto-discovery picks the single `*.cmm` directly under `app/variants/<LT_VARIANT>/source/Lauterbach_scripts/` (not inside its `actions` subfolder) | `app/variants/tviib_2m_aravalli_s3p/source/Lauterbach_scripts/cyt2bl_flash_2M.cmm` |
| `LT_ABS_FILE` | No (derived) | Path to the app ELF (`.abs`). Default: `build/<LT_VARIANT>.<LT_VARIANT_CONFIG>/bin/<LT_VARIANT>.abs` | `build/tviib_2m_aravalli_s3p.Debug/bin/tviib_2m_aravalli_s3p.abs` |

**Before starting any task, the calling agent must determine `LT_VARIANT`**
(and, if the defaults don't match, the window-title patterns) for the current
project - e.g. by asking the user, checking `app/variants/*` for the intended
target, or reading the repo's own build docs. Do not assume the worked-example
values apply to a different project/chip.

Cores/windows are always **master + one or more slaves** in this AMP model:
- **MASTER** → typically the boot/safety core (e.g. Cortex-M0+/HSM side).
- **SLAVE1 (application core)** → the core that runs the application software
  and holds the symbols you actually want to read/write/break on (e.g.
  Cortex-M4/M7). **Send every application command to this window.**

## Environment (auto-detected, not project-specific)

| Item | How it's found |
|------|-----------------|
| TRACE32 exe (`t32marm.exe`) | Preferred: path of an already-running `t32marm` process. Otherwise searched under `D:\.conan\short\*\bin\windows64\t32marm.exe` (and `C:`, `E:`) - conan short-path hash varies per machine/checkout and is never hardcoded. |
| `P4_SYS` (system dir) | Derived from the detected `t32marm.exe` path (its `...\1` parent dir). |
| Repo root | Walked up from the script location until `run.py` + `econ_config.sh` are found. |
| Git bash | `C:\Program Files\Git\bin\bash.exe` (fixed path, not project-specific). |

## Workflow

### Verified facts & gotchas (learned on the bench - apply the general pattern; re-verify chip-specific specifics like exact command syntax on your own target before trusting them)

1. **Two ways to launch, one reliable for master/slave:**
   - `run.py <variant>.<config> debug_trace32` starts TRACE32 **detached** and returns
     immediately. Sometimes it only shows a single generic **`TRACE32 PowerView`**
     window (AMP setup did not complete).
   - **Launching `t32marm.exe -s <startup>.cmm bin\<variant>.abs` directly from the
     build dir reliably opens BOTH the MASTER and application-core SLAVE windows.**
     Prefer this (`Start-Trace32.ps1` does exactly this).

1a. **Wait for the AMP handshake to fully settle - window titles appear before it's
    actually ready (bench-observed 2026-07-15).** MASTER/SLAVE window titles can
    show up within ~12s, but the underlying flash + master→slave handoff can take
    noticeably longer. Sending breakpoint/`Go` commands too early has produced
    both a misleading "stuck at the old default breakpoint" false alarm and a
    genuine "target system down" error on different runs. `Start-Trace32.ps1`
    defaults to a **60s** settle wait after launch for this reason - don't shorten
    it without re-verifying on the bench, and don't chain follow-up commands
    (`Set-Breakpoint.ps1` etc.) immediately after a shorter/custom wait.

2. **`t32rem.exe` will NOT work by default** on an AMP master/slave session. It needs
   the receiving TRACE32 to have the remote API enabled (`RCL=NETASSIST`, a `PORT=`).
   The normal AMP debug launch does **not** enable it, so `t32rem` returns
   `error initializing TRACE32`. A separate config file that enables `RCL` (built for
   a single-instance flash-only flow) was bench-tested against one project's AMP
   launch and loaded a generic, wrong-architecture session instead of composing with
   the AMP startup script - **do not assume this combination works on your
   project/chip without bench-testing it first.** Prefer driving the GUI by
   **window focus + keystrokes** (below) unless you've verified an RCL-enabled
   config that composes correctly with your AMP startup script.

3. **GUI automation (no remote API): send ONE command at a time.** Multi-line
   clipboard pastes get concatenated into a single command line and fail (e.g.
   `symbol not found`). For each command: focus the application-core slave by
   **PID** (`AppActivate`), then `ESC → Ctrl+A → Backspace` to clear the command
   line, paste one command, press Enter. See `scripts/Send-Trace32Command.ps1`.

3a. **A minimized TRACE32 window silently drops every keystroke - bench-verified
    2026-07-15.** If a window (master or slave) ends up minimized, Windows
    reports its `GetWindowRect` position as `(-32000, -32000)` (the standard
    minimized sentinel) and the TRACE32 status bar shows a red **"command
    locked"** message. In this state, `Send-OneCommand`'s keystrokes go nowhere
    - no error, just a window that looks unchanged/blank on the next
    screenshot, and breakpoint/Go commands that silently never take effect
    (the target stays at whatever state it was already in, e.g. the old
    default breakpoint). `config.ps1`'s `Restore-Trace32WindowIfMinimized`
    (called automatically by `Send-OneCommand` and `Capture-Trace32.ps1`)
    detects this position and calls `ShowWindow(SW_RESTORE)` to fix it before
    proceeding. If a capture/command still looks wrong after this, check for
    a genuinely blank window (AMP not settled yet) vs. this minimized case
    specifically.

4. **Do NOT send `InterCom <core> ...` into a lone `TRACE32 PowerView`.** If the
   slave was not created, `InterCom <core>` closes/kills that session. Only use
   `InterCom` from a real MASTER that already has the slave present (that is what
   the startup/breakpoint `.cmm` scripts rely on).

5. **A "run lauterbach flash" build-system action needs `P4_SYS`.** Running it via
   `run.py` fails with `t32marm.exe not found` unless `P4_SYS` points at the
   TRACE32 system dir, e.g. `export P4_SYS="D:\.conan\short\<hash>\1"`.

6. **Default breakpoints after flash are normal.** The project's breakpoint macro
   typically arms a handful of safety/error-hook functions (e.g. an init routine,
   an error hook, a DET/error-report function, a reset function) on the
   application core. After flashing the core stops at one of these. **Delete them
   and `Go`** to let the software run and reach an application breakpoint.

   **Clear-then-verify, as its own step (bench-verified 2026-07-15):** deleting
   the defaults and setting the new breakpoint+`Go` in the same batch/settle
   window can look like a hang - a call stack captured right after can still
   show the core halted at the OLD default breakpoint (e.g.
   `Startup_Init()/_RESET()`), which reads as "the core never released from
   reset" but is actually just the deletion not having settled yet. **Do not
   conclude the core/target is stuck from a single capture.** Always: (1) send
   `Break.Delete /ALL` + `Break.List` as their own settled step first and
   confirm the list is empty (screenshot if unsure), THEN (2) `Break.Set
   <symbol> /Program` + `Go` as a second step. `Set-Breakpoint.ps1` does this
   two-step sequence automatically unless `-KeepDefaults` is passed.

7. **Breakpoint commands (application-core slave):**
   - Set: `Break.Set <symbol> /Program`
   - Enable all: `Break.Enable /ALL` · Enable one: `Break.Enable <symbol>`
   - Delete all: `Break.Delete /ALL` · Delete one: `Break.Delete <symbol>`
   - List: `Break.List`
   - Run: `Go` · Wait for halt: `WAIT !STATE.RUN() <n>.s`

8. **Read a variable:**
   - Enum, symbolic: `Var.View %E <var>` (opens a window showing the symbolic value)
   - Numeric to AREA/log: `PRINT "x = " Var.VALUE(<var>)`
   - File-static still resolves by bare name once ELF symbols are loaded.

9. **Write a variable — CRITICAL SYNTAX:**
   - ✅ `Var.Set <var>=9` — **no spaces around `=`, numeric literal** → works.
   - ❌ `Var.Set <var> = <EnumName>` — spaces + symbolic enum name **silently
     fails** (read-back stays unchanged).
   - Convert enum names to their numeric value before writing.

10. **Cyclic overwrite.** A cyclic main-function may reassign its state var every
    cycle. To prove a write, keep the core **halted at the breakpoint** and read
    back **before** `Go`. A "write persists after Go" expectation is only valid if
    you also set the request/conditions that would otherwise change it back.

11. **Call stack / frame - verified working method:** `Frame.view /Caller /Locals`
    opens a floating window and reliably shows the real call chain with locals,
    e.g. (illustrative, from the worked example's `VidCtlSM_vMainFunction`):
    ```
    -000 VidCtlSM_vMainFunction()
    -001 Os_Entry_Task_ASW_Mid()
       . Rte_CurrentEvent = 1080
       . Rte_ShutdownFlag = 0
            VidCtlSM_vMainFunction();
    -002 Os_DispatchECC(asm)
    --- end of frame
    ```
    Capture it with `Capture-Trace32.ps1` (screenshot) - this is the reliable,
    working method. Issue `WinPOS ...` **before** the window command if embedding
    it in a fixed layout script.

11a. **Call stack - headless/scriptable via `FRAME.NAME()`/`FRAME.OFFSET()`:
    disproven on at least one bench.** On the worked-example target/TRACE32
    version these are **not** valid PRACTICE functions - `FRAME.NAME(0.)` errors
    with `no function 'FRAME.NAME' exists`. `Frame.List` is also not a valid
    command there (`unknown command`). Treat any headless/text-dump call-stack
    method as **unverified until bench-tested on your own target** - default to
    `Frame.view /Caller /Locals` + screenshot (gotcha #11).

12. **Kill everything:**
    `Stop-Process -Name t32marm,t32marm64,t32rem,t32start,t32mciserver,t32tcpusb -Force`.

13. **`t32rem` CAN work for a flash-only (single master, no AMP slave yet) flow**
    when the launch config enables `RCL=NETASSIST`/`PORT=<n>` - e.g.
    `t32rem localhost port=20000 "IC ALL QUIT"`. This has been proven on
    flash-only CI flows in more than one project. It has **not** been proven to
    work once an AMP master+slave session is up - re-verify on your own bench
    before relying on `t32rem` in that scenario; default to GUI keystroke
    automation instead (see `Send-Trace32Command.ps1`).

14. **`IC` (InterCom) ≠ `RCL` (remote control).** `IC=NETASSIST` in an AMP config
    lets TRACE32 instances talk to each other (what `InterCom <core> ...` inside a
    `.cmm` script uses); `RCL` (used by the external `t32rem.exe`) is a separate
    setting. Having `IC=NETASSIST` set does **not** make `t32rem` work from an
    external process - you need `RCL=NETASSIST`/`PORT=<n>` on the session's own
    config for that.

15. **Script output files go to `ai_output/debug/` under the repo root by
    default.** `Capture-Trace32.ps1` writes relative `-OutFile` screenshots there
    (auto-created); `Get-CallStack.ps1`, `Read-Variable.ps1 -Capture`, and
    `Write-Variable.ps1 -Capture` delegate to it. Pass an absolute path to save
    elsewhere.

16. **"Welcome to TRACE32!" modal appears on EVERY fresh launch - auto-handled since
    2026-08-12, don't re-diagnose it as a hardware/CPU problem.** It reappears even with its
    own "Show this dialog at start" checkbox already unchecked, because each launch gets a
    fresh temp profile/config dir. It is a PURELY VISUAL overlay - the underlying PRACTICE/flash
    script keeps running underneath it (proven via the native `run.py <variant>.<config>
    debug_trace32` action succeeding while it was still on-screen). The real risk is indirect:
    while it owns focus, a `Send-OneCommand` keystroke sequence sent at the same moment can be
    swallowed/misdirected, which previously produced a misleading "syntax error" on the very
    next real command - it looked like a genuine `SYStem.CPU`/device-support failure but wasn't.
    `Start-Trace32.ps1` and `Send-OneCommand` (via `config.ps1`'s `Dismiss-Trace32WelcomeDialog`)
    now dismiss it automatically via ESC (AppActivate+SendKeys) before every command - this is
    the ONLY dismissal method proven reliable; WM_CLOSE-by-window-title and a simulated mouse
    click on its visible X button were both tried and found unreliable (the mouse click even
    mis-landed and toggled the checkbox back ON, due to a DPI/logical-vs-physical coordinate
    mismatch between a `PrintWindow` screenshot's pixels and real screen coordinates). If you
    still see a "syntax error" or a stuck/`target reset` state after this fix, re-verify with a
    fresh screenshot before assuming it's the same old issue - it likely means something else.

## Implementation Files

All under `.github/scripts/debug_traveo_lauterbach/` (PowerShell 5.1). Dot-source
`config.ps1` first (every other script does this automatically) - and make
sure `LT_VARIANT` (and any other needed `LT_*` variables) is set in the
environment first.

| Script | Purpose |
|--------|---------|
| `config.ps1` | Reads `LT_*` env vars, detects project root, TRACE32 exe/`P4_SYS`, build dir; window helpers; one-command-at-a-time sender |
| `Start-Trace32.ps1` | Open MASTER + application-core SLAVE by launching `t32marm -s <startup>.cmm` |
| `Send-Trace32Command.ps1` | Send one or more commands to the application-core slave (focus-by-PID, one at a time) |
| `Set-Breakpoint.ps1` | Delete defaults, set+enable a breakpoint, `Go`, wait for hit |
| `Read-Variable.ps1` | Read a variable/enum from the application-core slave |
| `Write-Variable.ps1` | Write a numeric value (`Var.Set VAR=VALUE`) and read back |
| `Get-CallStack.ps1` | Open `Frame.view /Caller /Locals` and screenshot it (see gotcha #11a for why this isn't a headless text dump) |
| `Stop-Trace32.ps1` | Close all TRACE32 processes gracefully (`WM_CLOSE`). `-Force` skips straight to `TerminateProcess` |
| `Capture-Trace32.ps1` | Screenshot the application-core slave window for verification |

## Usage

### Quick start

```powershell
# 0. Tell the scripts which project/variant to target - REQUIRED, no default.
#    Replace with YOUR project's variant name (and window titles if the
#    generic '*MASTER*'/'*SLAVE*' wildcards don't uniquely match).
$env:LT_VARIANT      = '<your-variant-name>'
# $env:LT_MASTER_TITLE = '<wildcard matching your master window title>'   # optional
# $env:LT_SLAVE_TITLE  = '<wildcard matching your app-core window title>' # optional

cd <repoRoot>\.github\scripts\debug_traveo_lauterbach

# 1. Open master + slave (flashes via the discovered/auto-detected startup script)
.\Start-Trace32.ps1

# 2. Remove default breakpoints, break on an app function, run to it
.\Set-Breakpoint.ps1 -Symbol <YourFunction>

# 3. Read a variable
.\Read-Variable.ps1 -Variable <YourVariable>

# 4. Write a variable (numeric literal!) and read back
.\Write-Variable.ps1 -Variable <YourVariable> -Value 9

# 5. Dump the call stack (frame chain) while halted
.\Get-CallStack.ps1

# 6. Screenshot for evidence
.\Capture-Trace32.ps1 -OutFile bp_evidence.png

# 7. Tear down
.\Stop-Trace32.ps1
```

---

## Manual command recipes (paste into the application-core SLAVE command line)

**Break at an app function and read a state enum:**
```cmm
Break.Delete /ALL
Break.Set <YourFunction> /Program
Break.Enable /ALL
Go
WAIT !STATE.RUN() 20.s
Var.View %E <YourVariable>
PRINT "value = " Var.VALUE(<YourVariable>)
```

**Write then read back (while halted):**
```cmm
PRINT "Before = " Var.VALUE(<YourVariable>)
Var.Set <YourVariable>=9
Var.View %E <YourVariable>
PRINT "After = " Var.VALUE(<YourVariable>)
```

**Remove the post-flash default breakpoints and just run** (replace with your
project's actual default-armed symbols):
```cmm
Break.Delete <DefaultBp1>
Break.Delete <DefaultBp2>
Break.Delete <DefaultBp3>
Go
```

**Dump the call stack while halted (verified - screenshot method):**
```cmm
Frame.view /Caller /Locals
```
Opens a floating window with the real call chain + locals per frame (see
gotcha #11 for a captured example). Capture it with `Get-CallStack.ps1` or
manually with `Capture-Trace32.ps1`. See gotcha #11a - do not assume a
headless/text-dump method exists without bench-testing it on your own target.

---

## Outputs

Most capabilities report their result as a PowerShell console readout (variable value,
breakpoint-hit status) captured from the TRACE32 command line via `Send-Trace32Command.ps1`.
Visual evidence (call stack, breakpoint state) is written as a screenshot to `ai_output/debug/`
under the repo root by default (`Capture-Trace32.ps1`, and any `-Capture` switch on
`Get-CallStack.ps1` / `Read-Variable.ps1` / `Write-Variable.ps1`) - pass an absolute `-OutFile`
path to save elsewhere.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Only one blank `TRACE32 PowerView`, no MASTER/SLAVE | AMP setup did not complete via the detached launch | Kill all, relaunch with `Start-Trace32.ps1` (direct `t32marm -s <startup>.cmm`) |
| `t32rem` → `error initializing TRACE32` | Remote API not enabled on this session | Drive the GUI by focus+keystrokes; only rely on an RCL-enabled config after bench-testing it composes with your AMP startup script |
| `t32marm.exe not found` (a "run lauterbach" build action) | `P4_SYS` unset/wrong | `export P4_SYS="D:\.conan\short\<hash>\1"` before the action |
| Stops at a DET/error-hook function after flash | Default armed breakpoint (normal) | Delete defaults, `Go` |
| Write didn't change the value | Used spaces + enum name in `Var.Set` | Use `Var.Set VAR=VALUE`, numeric, no spaces |
| Value reverts right after `Go` | Cyclic main-function overwrote it | Read back while halted, before `Go` |
| Session closes when sending a command | Sent `InterCom <core> ...` to a lone PowerView | Only use `InterCom` from a real MASTER with the slave present |
| Cannot attach / `Unexpected ack` | Target power/wake-up input off | Power the target on, retry |
| `Frame` window not scriptable as text | `FRAME.NAME()`/`Frame.List` may not exist on your TRACE32/target | Use `Frame.view /Caller /Locals` + screenshot; verify a headless method on your own bench before assuming one exists |
| `IC=NETASSIST` set but `t32rem` still fails | `IC` (InterCom) ≠ `RCL` (remote API) | Add `RCL=NETASSIST`/`PORT=<n>` to the config used for the master, then re-verify it composes with your AMP startup script |
| `LT_VARIANT is not set` error from `config.ps1` | Required env var not set | `$env:LT_VARIANT = '<your-variant-name>'` before running any script |

---

## Worked example (bench-verified project - for reference only)

This is a concrete, previously bench-verified configuration. **It is an
example, not a default** - a different project/chip will have a different
variant name, chip name and window titles.

| Setting | Value |
|---------|-------|
| Variant | `tviib_2m_aravalli_s3p` (Traveo II B-E, chip `CYT2B93CAS`, 2M) |
| Master window title | `TRACE32 for ARM - CYT2B93CAS-CM0+ - MASTER` (CM0+ = BootROM/HSM side) |
| Slave window title | `TRACE32 for ARM -CYT2B93CAS-CM4 - SLAVE1` (CM4 = application core, note: no space after "ARM -") |
| Startup script | `app/variants/tviib_2m_aravalli_s3p/source/Lauterbach_scripts/cyt2bl_flash_2M.cmm` |
| Breakpoint macro | `app/variants/tviib_2m_aravalli_s3p/source/Lauterbach_scripts/actions/breakpoint.cmm` |
| AMP config | `app/variants/tviib_2m_aravalli_s3p/source/Lauterbach_scripts/actions/config_amp.t32` |
| App ELF | `build/tviib_2m_aravalli_s3p.Debug/bin/tviib_2m_aravalli_s3p.abs` |
| Example symbol path | `\\tviib_2m_aravalli_s3p\vidctlsm1c1\VidCtlSM_vMainFunction` |
| Default armed breakpoints after flash | `Startup_Init`, `ErrorHook`, `Det_ASR40_ReportError`, `Mcu_PerformReset` |

To reproduce this exact example:
```powershell
$env:LT_VARIANT      = 'tviib_2m_aravalli_s3p'
$env:LT_MASTER_TITLE = 'TRACE32 for ARM - CYT2B93CAS-CM0+ - MASTER'
$env:LT_SLAVE_TITLE  = 'TRACE32 for ARM -CYT2B93CAS-CM4 - SLAVE1'
cd <repoRoot>\.github\scripts\debug_traveo_lauterbach
.\Start-Trace32.ps1
.\Set-Breakpoint.ps1 -Symbol VidCtlSM_vMainFunction
.\Read-Variable.ps1  -Variable VidCtlSM__enCurrOpMode
.\Write-Variable.ps1 -Variable VidCtlSM__enCurrOpMode -Value 9
```
