---
name: ghs-py-flash-debug
description: >-
  Fast, event-driven, Python-only flash & debug for the Traveo II ECU via GHS Multi. Mirrors the
  existing RC/PowerShell workflow (connect -> flash -> verify -> debug) but replaces every fixed
  `wait -time`/`Start-Sleep` with sentinel-marker polling, adds fast-fail error handling, and emits
  three consistent reports (console + JSON + a canonical fixed-structure HTML report) plus an
  old-vs-new benchmark.
  Use when: the user chooses the "new Python" debug path; flashing/bringing the target to a running
  state; reading/writing runtime variables; setting a print-and-continue breakpoint; and whenever a
  detailed, auditable per-step debug report is required.
argument-hint: 'e.g.: run (bring to running), read AmmSM__enCurrentMode, write g_WdgM_SE_Status=1, break on Mcu_PerformReset, add --flash to flash first, --simulate for a no-hardware dry run'
---

# Traveo II — Python (event-driven) Flash & Debug

## Overview

This skill drives the **new, Python-first** flash/debug path. It follows the *same* workflow and
gotchas as the reference `debug_traveo_ghs` / `traveo-flash` skills (single self-contained Multi
session per operation, `hardbrk rolling` for flash breakpoints, `m4`/`m7_0` core prefix, benign
`INCOHERENT` filtering) but is implemented entirely in Python and is **event-driven**: it never
idles on an arbitrary delay.

All logic lives under `.github/scripts/ghs_py/` (files prefixed `ghs-py-`). It does **not**
modify any existing skill or script.

> This is the alternative to the current RC/PowerShell path. The `traveo_build_debug` agent
> (Profile A) asks the user which path to use; select this skill only when the user chose the
> **new Python** method.

## Key difference vs the current method — no blind waits

The current RC flow uses fixed waits (`wait -time 3000`, `wait -time 90000`, `Start-Sleep 4`). This
skill instruments every RC checkpoint with a unique sentinel marker `>>>TVPY:TAG<<<` (`mprintf`
literal), tails the Multi `-R` log, and proceeds the instant the marker appears. Fatal markers
(`No match`, `Unexpected ack`, `Could not detect a flash device`, `SWD protocol error`, …) trigger
an immediate kill of Multi — **fast-fail, no blind retry loop**. Only a generous *safety ceiling*
remains, which a healthy bench never reaches.

> **Not a separate GUI-free API.** This skill still launches the identical
> `multi -nosplash -servertimeout N debug.ghsmc -R log.txt -p script.rc` process as the current
> RC/PowerShell flow — GHS Multi's only automation model is RC-script-in/log-text-out, there is no
> other API this codebase talks to. The improvement here is *how* the log is consumed (tailed at a
> short poll interval, fatal/done markers react instantly) instead of *what* is launched.

## Prerequisites

> **CANoe must be running with KL15 ON before any flash/debug** (SWD bus otherwise returns
> `Unexpected ack b000`). The `connect` step verifies/raises this via CANoe COM.

- GHS Multi probe connected; `debug.ghsmc` present in `build/<variant>/`.
- Git bash at `C:\Program Files\Git\bin\bash.exe`.
- `pywin32` installed (CANoe COM) — `.github/scripts/requirements.txt`.

## Composable steps (each independently invokable)

| Step | Script | Purpose |
|------|--------|---------|
| connect | `ghs-py-connect.py` | Clear stale `multi`/`mpserv`; ensure CANoe running + KL15 ON (polled, not slept) |
| flash | `ghs-py-flash.py` | `run.py flash_ghs`; stream-based fast-fail; one retry only for a documented transient probe glitch |
| verify | `ghs-py-verify.py` | VERIFY connect + symbol load; returns at the `Startup_Init` halt via marker (no 90 s wait) |
| debug-launch | `ghs-py-debug-launch.py` | `run` / `read` / `write` / `breakpoint` in one self-contained Multi session |
| report | `ghs-py-report.py` | Emit console + JSON + canonical HTML + benchmark |
| run-rc | `ghs-py-run-rc.py` | Drive an EXISTING, already-written ad-hoc `.rc` file (e.g. a one-off `UC0*`/`RT-*`/`WBT-*` test script) event-drivenly instead of a bare `bash run_X.sh` wrapper — see below |

### Driving an existing ad-hoc `.rc` file event-drivenly (`ghs-py-run-rc.py`)

Ad-hoc, one-off test scripts (the `UC0*_*.rc`/`RT-*.rc`/`WBT-*.rc` files under
`build/audi_fid_sdv.Debug/`) are typically written directly, with their own `run_X.sh` bash
wrapper that just does `multi -nosplash -servertimeout N debug.ghsmc -R log -p script.rc`. That
wrapper **blocks on the whole OS process** — even once the log already shows the run finished (or
hit a fatal error), the caller keeps waiting until `multi` itself exits or the server timeout
elapses. Use `ghs-py-run-rc.py` instead whenever you want the SAME already-written `.rc` file to
react the instant its own `>>>TVPY:<tag><<<` markers appear:

```powershell
python .github\scripts\ghs_py\ghs-py-run-rc.py --rc UC01_seq_batchA.rc
python .github\scripts\ghs_py\ghs-py-run-rc.py --rc UC02_phaseB_v2.rc --wait-tags VERIFY_DONE DONE --ceiling 180
```

It auto-detects the marker(s) to wait for from the `.rc` file itself (the last `mprintf(">>>TVPY:
<tag><<<")` found, normally `DONE`) if `--wait-tags` is omitted, kills stale `multi`/`mpserv`
first, and returns the instant the last wait-tag OR a fatal marker is seen — with a real exit code
(0 = done, 1 = fatal, 2 = timeout) and the log tail printed inline, so a calling agent never has to
guess or poll a stale file separately. It reuses the exact `_launch()`/`_fatal_in()`
subclass pattern already established for this bench (no `-rc` includes; whitelists the known
self-recovering SWD-89 transient family) on top of `ghs-py-core.py`'s `FATAL_SUBSTRINGS`.

## Usage

### One command (orchestrator)

```powershell
cd .github\scripts\ghs_py

# Bring the (already-flashed) target to a running state — DEBUG ONLY (no flash, no build):
python ghs-py-run.py --op run

# Flash first, then read variables:
python ghs-py-run.py --flash --op read --variables AmmSM__enCurrentMode g_WdgM_SE_Status

# Write a runtime variable (halt at Startup_Init by default; use --halt-on FUNC for a runtime halt):
python ghs-py-run.py --op write --variable g_WdgM_SE_Status --value 1

# Break on a function and capture ARM arg registers ($r0=1st arg, $r1=2nd, $lr=return):
python ghs-py-run.py --op breakpoint --function Mcu_PerformReset --regs '$r0' '$r1' '$lr'

# Bench B (tviic_6m_endprod, triple-core, m7_0 prefix):
python ghs-py-run.py --bench B --op run
```

### No-hardware dry run (still produces real reports)

```powershell
python ghs-py-run.py --op breakpoint --function Mcu_PerformReset --simulate
python ghs-py-selftest.py     # 36 validation checks
```

## Reports (three consistent outputs from one data source)

Every session produces, from the *same* `SessionRecorder` data:

1. **Console log** — human-readable step timeline, breakpoints, values, benchmark.
2. **JSON** (`ai_output/ghs_py/<name>.json`) — machine-readable; sections: `metadata`,
   `summary`, `steps`, `breakpoints`, `inspections`, `errors`, `benchmark`, `config`.
3. **HTML** (`<name>.html`) — the **canonical, fixed-structure** report. Sections, order, headings
   and styling are constant across runs (only the data changes): 1 Metadata · 2 Summary · 3
   Timeline · 4 Breakpoints · 5 Inspected values · 6 Errors & handling · 7 Benchmark (old vs new)
   · 8 Environment. Rendered by `ghs-py-html-report.py` from one constant template — do **not**
   improvise a different layout.

Each record captures per-step timing, breakpoints (file/function/line/address/hit/values),
inspected register/memory/variable values, and every error plus how it was handled.

## Benchmark (old vs new)

`ghs-py-benchmark.py` holds the documented worst-case timings for the old fixed-wait RC method and
the expected event-driven timings, and merges in the *measured* per-step times of the live session.
The comparison appears in both the JSON and the HTML report with per-stage and total speed-up.

## Error handling (fast-fail)

| Symptom | Handling |
|---------|----------|
| Fatal marker in `-R` log (`No match`, `Unexpected ack`, `SWD protocol error`, `Cannot write`, `thrown away owing to command failure`, `ERROR: Read command not successful`, …) | Kill Multi immediately; record error + FAIL; stop the chain |
| Transient probe glitch on flash (`Could not detect a flash device`, `already connected`) | Clean holders + **one** retry, then give up |
| Safety ceiling reached waiting for a marker | Kill Multi; record timeout with log tail; FAIL |
| CANoe not running / KL15 off | `connect` fails fast with a clear action message |
| `mprintf` with variable args | Never used — values are captured with plain `print` fenced by markers |

**Bench-specific fatal exceptions**: some benches (e.g. `audi_fid_sdv`) have documented, genuinely
self-recovering transients that would otherwise false-positive as fatal (`SWD protocol error`,
`trg_run() failed`, `Unexpected ack`, `Green Hills Probe error`) — subclass `MultiRunner` and
override `_fatal_in()` to whitelist those before delegating to `super()._fatal_in()` (see repo
memory for the exact working pattern). Do **not** add "Cannot set a hardware breakpoint" to any
fatal list — arming a symbol with no linked address is sometimes the *intended, positive* result of
a test proving a function is dead/uncalled code, not a script error.

## Notes / conventions (inherited from the reference skill)

- Software breakpoints are impossible in flash — always `hardbrk rolling FUNC`.
- HW BP stops at function entry before the prologue — read ARM arg registers `$r0..$r3`, not named
  params.
- Static/file-local vars need file-qualified expressions (`"file.c"#var`) — pass that as the read
  expression.
- Benign `INCOHERENT` / `just_did_rom_to_ram_copy failed` / `Error: General Error` lines are filtered.
