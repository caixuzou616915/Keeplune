---
name: debug-test-cases
description: >-
  Debugger-neutral on-target test-case standard (DTC, `*.dtc.json`) for Traveo II ECUs. One
  spec compiles to BOTH a GHS Multi playback `.rc` and a Lauterbach TRACE32 `.cmm`, both
  scripts write the same `DTC|...` log markers, and one evaluator scores either log into a
  test-report-style `.md`/`.html`. Use this skill whenever you write, validate, compile, run
  or evaluate on-target debug test cases for a code change: proving a deployed change is in the
  flashed image (deploy-check), breakpoint / read / write / forced-value checks, or turning
  "debug this change" into a repeatable script for either probe. Also use it when a debug
  agent asks "what should I test?" for a change.
metadata:
  author: "SGP UX SW AI Community"
  version: "1.0.0"
---

# Debug Test Cases (DTC) — one format for GHS Multi and Lauterbach

A **DTC spec** (`<suite>.dtc.json`) describes *what* to check on target in debugger-neutral
terms. `scripts/dtc_tool.py` turns it into *how* for each probe and scores the result:

```
 Code change ──► Debug Test Cases agent ──► <suite>.dtc.json  (+ pending report)
                                               │ validate / deploy-check / compile
                          ┌────────────────────┴────────────────────┐
                    ghs/<TC>.rc                                t32/<TC>.cmm
            run_debug_rc.ps1 / multi -p                t32py_pystart.py --do-app
                    <TC>_out.txt  ── same DTC|… markers ──  <TC>_out.txt
                          └────────────────────┬────────────────────┘
                                   evaluate ──► results.json ──► report (.md + .html)
```

Script location (project level first, user level as fallback):
`.github/skills/debug-test-cases/scripts/dtc_tool.py` or
`~/.copilot/skills/debug-test-cases/scripts/dtc_tool.py`. Stdlib only (Python 3.8+).
A complete worked spec is in `references/example.dtc.json`.

## 1. Spec format (`dtc_version` "1.0")

```jsonc
{
  "dtc_version": "1.0",
  "suite": {
    "id": "DTC-<Module>-<short>",        // required, used in file names
    "title": "...",                       // required
    "change_ref": "DGC-1234 / Code Deploy Report ...",   // required - what change is tested
    "module": "AmmSM",
    "variant": "tviib_e4m_aravalli_s3p",  // overrides the bench preset's variant
    "build_type": "Debug",
    "changed_files": ["pkg/.../ammsm1c1.c"],  // repo-relative; used by deploy-check
    "preconditions": ["CANoe running with KL15 ON", "..."]
  },
  "bench": { "preset": "A" },             // GHS bench preset A | B | C (see §4); optional
                                          // overrides: ghs_core_prefix, ghs_preamble[],
                                          // ghs_read_style (mprintf|print),
                                          // ghs_write_style (assign|set|print)
  "symbols": {                            // optional per-symbol metadata
    "AmmSM__enCurrentMode": {
      "file": "ammsm1c1.c",               // file-local static -> GHS "file.c"#sym, T32 \module\sym
      "ghs": "AmmSM__enCurrentMode",      // explicit expression override per debugger
      "t32": "AmmSM__enCurrentMode",
      "enum": {"Ready": 20, "ProjectionOn": 40}   // names usable in values/expectations
    }
  },
  "deploy_check": { "symbols": ["AmmSM_vMainFunction"] },  // default: every symbol in steps
  "test_cases": [
    {
      "id": "DTC-01",                     // [A-Za-z0-9_-], unique
      "title": "...",
      "type": "deployment|functional|regression|negative|boundary|robustness",
      "technique": "Boundary Value Analysis | Equivalence Partitioning | State Transition | Decision Table | Error Guessing",
      "trace": ["SRS-2201", "ammsm1c1.c:AmmSM_vMainFunction"],
      "purpose": "one paragraph: what behaviour is confirmed and why",
      "start": "runtime",                 // runtime (default) | boot
      "settle_ms": 10000,                 // runtime start: let the system run before step 1
      "steps": [ { "action": "...", ... } ]
    }
  ]
}
```

### Start state (identical on both probes)

Every test case starts with the **application core halted**:

| `start` | GHS Multi | TRACE32 |
|---|---|---|
| `runtime` (default) | `VERIFY` → `target gc` → wait `settle_ms` → `halt` | ensure running → wait `settle_ms` → `Break` |
| `boot` | `VERIFY` only (halted at `Startup_Init`; NOINIT RAM still holds the previous run) | launch with `t32py_pystart.py --no-start --do-app` (cores still halted after flashing) |

Every test case ends with the core **running** again (`target gc` / `Go`); breakpoints set by
the test are removed (TRACE32 `Break.Delete`; GHS: each `.rc` is a separate MULTI session).

### Step actions

`what` (optional) overrides the auto-generated "What to do" text of any step.

| Action | Fields | GHS Multi (`<p>` = core prefix) | Lauterbach TRACE32 (app core) | Precondition |
|---|---|---|---|---|
| `run` | – | `target gc` | `Go` | halted |
| `halt` | `timeout_ms`=5000 | `<p> halt` + `wait -stop -time N` | `Break` + `WAIT !STATE.RUN() N.ms` | running |
| `wait` | `ms` | `wait -time ms` | `WAIT ms.ms` | running (warning if halted) |
| `wait_halt` | `timeout_ms` | `wait -stop -time N` | `WAIT !STATE.RUN() N.ms` (+ forced `Break` if still running) | running, after a `break` mode `halt` |
| `break` mode `halt` | `function` | `<p> hardbrk FN { log HIT }` | `Break.Set FN /CMD "PRINT …HIT"` | halted |
| `break` mode `log` | `function` | `<p> hardbrk rolling FN { log HIT }` | `Break.Set FN /CMD "PRINT …HIT" /RESUME` | halted |
| `break` mode `force` | `function`, `set {sym: val}` | `<p> hardbrk rolling FN { sym = val; …; log HIT }` | `Break.Set FN /CMD "Var.Set sym=val" … /RESUME` | halted |
| `read` | `symbol`, `expect`?, `live`? | `<p> mprintf("…%d\n", sym)` or `<p> print sym` | `PRINT "…",Var.VALUE(sym)` | halted (or `live: true`) |
| `write` | `symbol`, `value`, `readback`=true | `<p> sym = val` / `set` / `print (sym = val)` + read-back | `Var.Set sym=val` + read-back | halted (or `live: true`) |
| `stimulus` | `via` (canoe/manual), `detail`, `window_ms`=5000 | logs `STIMULUS` then waits `window_ms` | same | running |
| `note` | `text` | comment only | comment only | – |

`write` automatically expects the read-back to equal the written value (disable with
`"readback": false`). Enum names in `value`/`set`/`expect` are converted with `symbols.<sym>.enum`.

### Expectations (`expect`)

| On | `op` | Extra fields | Passes when |
|---|---|---|---|
| `read`/`write` | `==` `!=` `<` `<=` `>` `>=` | `value` | numeric/enum comparison holds |
| | `in` | `values: [...]` | value is one of them |
| | `range` | `min`, `max` | `min <= value <= max` |
| | `bits_set` / `bits_clear` | `mask` | all mask bits set / clear |
| | `changed` / `unchanged` | – | differs from / equals the previous read of the same symbol in this test case |
| `break` | `hit` / `not_hit` | – | ≥1 hit / 0 hits |
| | `count` | `min`, `max` (optional) | hit count within bounds |

A test case **PASSes** only if every expectation passes and the script reached `END`.
Status vocabulary (same as the `test-report` skill): ✅ PASS · ❌ FAIL · ❌ BLOCKED (not
started / aborted / timed out) · ⚠️ PARTIAL · ℹ️ INFO (no expectations) · ⏳ pending.

### Log marker grammar (written by both probes)

```
DTC|<tc>|BEGIN|ghs|t32        DTC|<tc>|<n>|STEP|<action>      DTC|<tc>|<n>|HIT
DTC|<tc>|<n>|READ|<sym>|<v>   DTC|<tc>|<n>|WRITE|<sym>|<v>    DTC|<tc>|<n>|WAIT_HALT|<state>
DTC|<tc>|<n>|STIMULUS|<via>   DTC|<tc>|END                    DTC|<tc>|ABORT
```

Values may be decimal (`40`), hex (`0x28`), TRACE32 decimal (`40.`), `sym = 40`, or an enum
name — the evaluator normalises all of them. Echoed command lines are ignored.

## 2. Writing good debug test cases for a change

1. **DTC-00/01 is always a deployment test**: `break` mode `halt` on the changed function,
   `run`, `wait_halt`, expect `hit`. It proves the flashed image executes the changed code
   before any behaviour is judged. Run `deploy-check` before it (offline, see §3).
2. **One behaviour per test case**, derived from the change: the new/changed condition, each
   new threshold (Boundary Value Analysis: below / at / above), each new state transition, and
   the error/fallback path (`negative`).
3. **At least one regression test** for behaviour the change must NOT alter (`unchanged`,
   `!=`, `not_hit`).
4. **Stimulate through the code's own inputs**: `break` mode `force` on the function that
   consumes the input (rolling breakpoint rewrite, no reflash) or `stimulus` via CANoe.
   Never weaken a safety mechanism to make a test pass.
5. **Keep timing in mind**: `log`/`force` breakpoints halt the core briefly at every hit —
   keep those windows short and do not assert on timing inside them.
6. **Read only on a halted core** unless the variable is known to be readable at runtime
   (`live: true`).
7. Put every requirement / function the test covers into `trace`; the report uses it.

## 3. Commands

```powershell
$dtc = ".github\skills\debug-test-cases\scripts\dtc_tool.py"   # or ~/.copilot/skills/...

python $dtc validate   ai_output\dtc\<suite>\<suite>.dtc.json
python $dtc deploy-check ai_output\dtc\<suite>\<suite>.dtc.json --build-dir build\<variant>.Debug --repo .
python $dtc compile    ai_output\dtc\<suite>\<suite>.dtc.json --out build\<variant>.Debug\dtc\<suite> [--target ghs|t32|all] [--bench A|B|C]
python $dtc report     ai_output\dtc\<suite>\<suite>.dtc.json --out-md ai_output\dtc\<suite>\<suite>_UseCaseTesting.md --out-html ai_output\dtc\<suite>\<suite>_UseCaseTesting.html
#   (no --results -> every Result cell is "⏳ pending" - the authored test plan)
python $dtc evaluate   <spec> --logs <log> [<log> ...] --target ghs|t32 --out ai_output\dtc\<suite>\results_<target>.json
python $dtc report     <spec> --results ai_output\dtc\<suite>\results_<target>.json --out-md ... --out-html ...
```

`compile` writes `ghs/<TC>.rc`, `t32/<TC>.cmm` and `manifest.json` (per test case: script
paths, log path, success/end markers, recommended `timeout_s`, TRACE32 launch mode).
Compile into `build/<variant>.<type>/dtc/<suite>/` so GHS paths stay relative to the build dir.
Exit codes: `validate`/`compile` 1 = spec errors; `deploy-check` 1 = change not provably in the
image; `evaluate` 1 = at least one test case not PASS/INFO.

### Running the compiled scripts

Prerequisite for both: **CANoe running with KL15 ON**, variant flashed with the image that
passed `deploy-check`.

**GHS Multi** (one MULTI session per test case):

```powershell
# Bench A / S3P meta-repo (generic runner: skip-verify, fail-fast, time-boxed)
.github\scripts\debug_traveo_ghs\run_debug_rc.ps1 -Rc dtc/<suite>/ghs/DTC-01.rc `
    -Out DTC-01_out.txt -SuccessMarker 'RESULT END' -TimeoutSec <manifest timeout_s>
# -Rc is relative to build\<variant>.Debug and goes through git bash: use FORWARD slashes.
# log: build\<variant>.Debug\DTC-01_out.txt
```

Bench B / Profile C: launch MULTI the way the `debug_traveo_ghs` skill / the
`traveo_build_debug` Profile C section describe (`multi … debug.ghsmc -R <TC>_out.txt -p <rc>`),
and poll the `-R` log for `RESULT END` (or `>>>TVPY:DTC_DONE<<<`).

**Lauterbach TRACE32** (all test cases in the same session):

```powershell
cd .github\scripts\debug_lauterbach_py
$env:LT_VARIANT = '<variant>'
python t32py_pystart.py --attach --do-app <out>\t32\DTC-01.cmm --do-app <out>\t32\DTC-02.cmm --do-timeout <max timeout_s>
#   no session open yet -> drop --attach (launch + flash + start, then run the scripts)
#   start=boot test cases -> python t32py_pystart.py --no-start --do-app <...>.cmm
# log: <out>\t32\<TC>_out.txt   (exit 4 = a script aborted / timed out; session stays open)
```

GUI fallback (`debug_traveo_lauterbach`): run `DO "<path>/DTC-01.cmm"` in the **CM4 / slave**
PowerView (e.g. via `Send-Trace32Command.ps1`) and wait for `DTC|DTC-01|END` in the log file.

## 4. GHS bench presets

| Preset | Project / variant | Core prefix | VERIFY script | Read style | Write style |
|---|---|---|---|---|---|
| `A` | S3P meta-repo, `tviib_e4m_aravalli_s3p` | `m4` (`alias m4 route cm4`) | `debug/ghs/tvii_debug_4mbe.py` | `mprintf` | `print (sym = v)` |
| `B` | VS20, `tviic_6m_endprod` | `m7_0` | `debug/tvii_debug_6mb.py` | `mprintf` | `sym = v` |
| `C` | Aravalli standalone, `tviib_e4m_aravalli_s3p_db` | `m4` (`alias m4 route cm4`) | `debug/ghs/tvii_debug_4mbe.py` | `print` (mprintf with args hangs there) | `sym = v` |

TRACE32 needs no preset: the `.cmm` always runs on the app-core (slave) instance.

## 5. Known limits — say so in the report if they bite

- **TRACE32 `Break.Set … /CMD … /RESUME`** (log/force breakpoints) and the static-symbol form
  `\module\sym` are standard PRACTICE syntax but were not yet bench-verified on this TRACE32
  build. If a script ABORTs on them, add `"t32": "<expression>"` to the symbol (check with
  `sYmbol.Browse *name*`) or split the test into halting `break` + `write` + `run` steps.
- GHS reads use `mprintf("%d")` (presets A/B) — enum names are not printed; add `enum` to the
  symbol to get readable results.
- `deploy-check` proves *the build* contains the change. Only the deployment test case
  (breakpoint on the changed function hits) proves *the flashed ECU* runs it.
- File-local statics usually do not appear in the `.map` file; `deploy-check` reports them as ⚠️,
  not ❌.
