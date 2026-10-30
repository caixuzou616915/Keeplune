---
name: asil-b-implementation
description: >-
  Implements and reviews ASIL B safety patterns in AUTOSAR C modules for the
  S3P HUD / Traveo II (T2G) codebase: double-inverse safety-variable storage,
  check-before-set/check-before-read integrity guards, the FSV
  (Fail-Safe Verification) safe-state (SST) state machine (S3P project only)
  and central registration tables, and time-plausibility / FFI checks. Use
  this skill whenever creating a new ASIL B / safety-relevant module,
  hardening an existing QM module to ASIL B, reviewing C code for ASIL B
  compliance, wiring a module's safe state into FSV, or the user mentions
  ASIL B, FSV, safe state, SST, double-inverse, FFI, or safety variable in
  this repo — even if they don't use those exact words (e.g. "add a safety
  check to this variable", "register this module with FSV").
metadata:
  author: "UX China"
  version: "1.0.0"
  tags: [c, autosar, t2g, asil-b, functional-safety, fsv, s3p-hud]
---

# ASIL B Implementation Skill

Captures the recurring ASIL B implementation conventions actually used in this
repo's S3P HUD modules (`vsmon`, `vsgen`, `fsv`), so new/modified modules stay
consistent with the existing safety architecture instead of reinventing it.

**Reference implementations** (read these when in doubt — they are the
ground truth, this skill only summarizes them):
- [pkg/em_s3p_hud/systemctl/fsv/core/fsv1c3.h](pkg/em_s3p_hud/systemctl/fsv/core/fsv1c3.h) — double-inverse macros, safe-time-partition, GUID helpers
- [pkg/em_s3p_hud/systemctl/fsv/core/fsv1c1.c](pkg/em_s3p_hud/systemctl/fsv/core/fsv1c1.c), [fsv1c2.c](pkg/em_s3p_hud/systemctl/fsv/core/fsv1c2.c) — central FSV engine
- [app/pkg/em_s3p_hud/systemctl/fsv/adapt/fsv1ca.c](app/pkg/em_s3p_hud/systemctl/fsv/adapt/fsv1ca.c) / [fsv1ca.h](app/pkg/em_s3p_hud/systemctl/fsv/adapt/fsv1ca.h) / [fsv1ci.h](app/pkg/em_s3p_hud/systemctl/fsv/adapt/fsv1ci.h) — project-level registration tables
- [pkg/em_s3p_hud/videoctl/vsmon/core/vsmon1c1.c](pkg/em_s3p_hud/videoctl/vsmon/core/vsmon1c1.c) — MainFunction, setter functions, adapt hooks
- [pkg/em_s3p_hud/videoctl/vsmon/core/vsmon1c2.c](pkg/em_s3p_hud/videoctl/vsmon/core/vsmon1c2.c) / [vsmon1c2.h](pkg/em_s3p_hud/videoctl/vsmon/core/vsmon1c2.h) — safe-state state machine, time plausibility
- [pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1.c](pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1.c) / [vsgen1c2.c](pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c2.c) — a second module implementing the same patterns

See [references/fsv-registration.md](references/fsv-registration.md) for the full
step-by-step "how do I register a new module's safe state with FSV" walkthrough
— read that file whenever the task is actually adding a module to FSV, rather
than trying to reconstruct it from the summary in section 4 below. Note: the
SST state machine / FSV registration in section 4 applies only to the S3P
project.

## Why this matters

These are hand patterns, not a code-gen framework: there is no compiler
enforcement tying a variable to its inverse copy, or a setter function to its
checker. Consistency only holds if every new safety variable/module follows
the same shape as the existing ones. Deviating (e.g. writing a safety
variable directly instead of through its setter, or returning early from a
MainFunction) silently reopens a bit-flip / control-flow-corruption gap the
existing pattern was built to close.

---

## 1. Double-inverse storage for safety-critical variables

Every RAM variable whose corruption (e.g. a single bit-flip from EMI/soft
error) could lead to unsafe behavior is stored twice: once normally, once
bit-inverted. A mismatch between `VARIABLE` and `~VARIABLE##Inv` proves memory
corruption occurred.

Declare + init (from `fsv1c3.h`, mirrored per-module in e.g. `vsmon1c2.h`):

```c
#define FSV__vDeclareSafetyVar(TYPE,VARIABLE)          TYPE VARIABLE; TYPE VARIABLE##Inv
#define FSV__vDeclareAndSetSafetyVar(TYPE,VARIABLE,VAL) TYPE VARIABLE = (VAL); TYPE VARIABLE##Inv = (TYPE)(~(VAL))
#define FSV__vSetSafetyVar(TYPE,VARIABLE,VAL)          VARIABLE = VAL; VARIABLE##Inv = (TYPE)(~(VAL))
#define FSV__vCheckSafetyVar(TYPE,VARIABLE) \
    if(0U != (TYPE)~(VARIABLE^VARIABLE##Inv)) {FSV__vTriggerMcuReset(FSV_nenSstSysResetIdx, (uint8)FSV__nDoubleInverseStorageErr);}
```

Module-local variant used by `vsmon`/`vsgen` (same idea, `do { } while(0)`
guarded, resets via a spin-wait for the watchdog instead of calling FSV
directly — use this style for a module's *own* private safety variables that
don't need to go through FSV's reset path):

```c
#define VsMon__vDeclareSafetyVar(TYPE, VARIABLE, VAL) \
    TYPE VARIABLE = (VAL); \
    TYPE VARIABLE##Inv = (TYPE)(~(VAL))

#define VsMon__vCheckSafetyVar(TYPE, VARIABLE) \
    do { if(0U != (TYPE)~(VARIABLE^VARIABLE##Inv)) { Sys_EnterCriticalSection(); while(1); } } while(0)

#define VsMon__vSetSafetyVar(TYPE, VARIABLE, VAL) \
    do { VARIABLE = VAL; VARIABLE##Inv = (TYPE)(~(VAL)); } while(0)
```

Declaring a safety variable (module-scope, from `vsmon1c1.c`):

```c
VsMon__vDeclareSafetyVar(VsMon_tenOpMode, VsMon__enOpMode, VsMon_nenOpModeOff);
VsMon__vDeclareSafetyVar(boolean, VsMon__boInitialized, FALSE);
```

**Rule:** any variable that gates a safety decision (mode, safe-state status,
error-latch flag, init flag, round-robin/timeout counters used to reach a
safety verdict) gets this treatment. Purely diagnostic/statistics data does
not need it.

## 2. CHECK-before-SET on every write

Never assign to a safety variable directly. Always go through a private
setter that checks integrity first, then updates both copies atomically:

```c
static void VsMon__vSetOpMode(VsMon_tenOpMode enValue)
{
    VsMon__vCheckSafetyVar(VsMon_tenOpMode, VsMon__enOpMode);
    VsMon__vSetSafetyVar(VsMon_tenOpMode, VsMon__enOpMode, enValue);
}
```

One such `static void <Module>__vSet<Field>(...)` exists per safety variable
(see the block of setters in `vsmon1c1.c` around
`VsMon__vSetOpMode/SstStatus/ErrorLatched/RoundRobinIdx/HwSyncStatus/
SyncTimeoutCnt/Initialized`). Public API functions and `_vInit`/`_vMainFunction`
call these setters — they never touch `VARIABLE`/`VARIABLE##Inv` themselves.

## 3. CHECK-before-READ before using a safety variable

Before branching on a safety variable's value, verify it first:

```c
VsMon__vCheckSafetyVar(boolean, VsMon__boInitialized);
if (VsMon__boInitialized == FALSE)
{
    ...
}
```

This is distinct from #2: a variable can be read-checked many times between
writes (e.g. once per MainFunction cycle) even though it's only set rarely.

## 4. Safe-state (SST) state machine *(S3P project only)*

> This pattern (and its FSV central registration in
> [references/fsv-registration.md](references/fsv-registration.md)) is
> specific to the S3P project's FSV supervision architecture — it does not
> apply to other projects built on this codebase.

Each supervised module keeps a small table of safe-state entries
(`VsMon_tstLocalSstReqStatus`, one per registered safe state) with:
`u32SafeStateGuid`, `u8RequestStatus`, `u8CurrentStatus`, `u8RollingCounter`,
`u8TimerIdx`, `u16TimeoutMs`. `u8CurrentStatus` cycles through
`FSV_SST_STATUS_PASSIVE / PENDING / ACTIVE / ERROR`:

```c
switch (u8CurrentSafeState)
{
    case FSV_SST_STATUS_PASSIVE: VsMon__vProcessPassiveSafeState(u8SafeStateIdx); break;
    case FSV_SST_STATUS_ACTIVE:  VsMon__vProcessActiveSafeState(u8SafeStateIdx);  break;
    case FSV_SST_STATUS_PENDING: VsMon__vProcessPendingSafeState(u8SafeStateIdx); break;
    case FSV_SST_STATUS_ERROR:   VsMon__vProcessErrorSafeState(u8SafeStateIdx);   break;
    default: /* DET: VSMON_E_INVALID_SST_TRANSITION */ break;
}
```

- **PASSIVE**: confirms the state, no transition logic.
- **PENDING**: transitional; times out via the module's per-entry
  `FsTmrCtl` timer if the transition doesn't complete.
- **ACTIVE**: evaluates the module's own safety condition (its checked
  `boError`/mode flags) each cycle; drops to ERROR if violated. This is the
  switch-per-`u8SafeStateIdx` block a new module customizes.
- **ERROR**: sticky — "no automatic recovery is available from this state"
  (only cleared through the module's explicit recovery/reset path).

`u8RollingCounter` and RTE sync (`Rte_Write`/`SYN_..._vSetSstVideoSafetyMon`)
let the central FSV module and other ECUs detect a frozen/dead reporting task
even if the status value itself looks fine. `VsMon_vReqSafeStateTransitionSm`
runs the dispatcher once per cycle and then decrements all local SST timers
via `FsTmrCtl_vAllTimerCountDown`.

For the concrete registration steps (GUID, timer ID, module index, safe-state
index enums, and the three central FSV tables), see
[references/fsv-registration.md](references/fsv-registration.md).

## 5. Time plausibility / FFI checks

To satisfy Freedom-From-Interference between the (QM) OS/RTE timing and a
safety-relevant cyclic function, compare a free-running HW timer delta
against the expected cycle time, with a double-inverse debounce counter so a
few isolated timing glitches don't immediately escalate:

```c
typedef struct {
    uint16 au16HwTimeStamp[VSMON__nTimestampBufferSize]; /* current/previous HW ticks */
    VsMon__vDeclareSafetyVar(uint8, u8DebounceCounter);  /* counts consecutive violations */
} VsMon_tstTimePlausibilityChk;
```

Pattern (see `FSV__vProcTimePlausibilityChk` doc in `fsv1c3.h` and
`VsMon__stTimePlausible` in `vsmon1c2.c`): take timestamp(n), compute
delta vs timestamp(n-1), convert to ms, compare against the expected cyclic
interval +/- tolerance; on the first call skip the check (no previous
timestamp yet); on violation increment the debounce counter (checked/set via
the safety setter) and only escalate (MCU reset / safe state) once the
debounce threshold is reached; always push timestamp(n) into timestamp(n-1)
for the next cycle. Wrap the check itself in
`FSV__vEnterSafeTimePartition()` / `FSV__vExitSafeTimePartition()` (interrupts
disabled) so the compare-and-update is atomic.

---

## Applying this skill

**When creating a new ASIL B module**, follow this order (mirrors what the
existing modules do):
1. Identify which runtime variables actually gate a safety decision → declare
   them with the double-inverse macro, add one setter each with
   check-then-set.
2. Add a check-before-read before every branch on a safety variable's value.
3. If the module needs FSV supervision *(S3P project only)*, follow
   [references/fsv-registration.md](references/fsv-registration.md).
4. If the module has its own cyclic timing safety requirement, add a time
   plausibility check per section 5.

**When reviewing existing ASIL B code**, check for violations of the rules
above: raw writes to a safety variable bypassing its setter, missing
check-before-read before a safety-variable branch, and (S3P projects only)
safe states left in ERROR with no reachable recovery path.
