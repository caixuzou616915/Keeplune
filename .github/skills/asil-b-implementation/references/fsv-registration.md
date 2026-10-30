# Registering a New Module's Safe State with FSV

Step-by-step guide for wiring a new (or existing) module's safe-state(s) into
the central FSV supervisor, based on the real `VsMon`/`VsGen`/`AmmSM`/`DispCtl`
registrations in [app/pkg/em_s3p_hud/systemctl/fsv/adapt/fsv1ca.c](../../../../app/pkg/em_s3p_hud/systemctl/fsv/adapt/fsv1ca.c)
and [fsv1ca.h](../../../../app/pkg/em_s3p_hud/systemctl/fsv/adapt/fsv1ca.h).

Everything here is guarded by one project feature-switch macro per module,
named `S3P_nPrjCfg_<Module>FsvSupervise` (e.g. `S3P_nPrjCfg_VSMonFsvSupervise`).
Add that macro to the project config before starting, and wrap every
addition below in `#if (S3P_nPrjCfg_<Module>FsvSupervise == STD_ON) ... #endif`
exactly like the existing entries — this lets a project drop a module's FSV
supervision entirely without touching FSV's core code.

## 1. Add the module's own enums (in the module's core header, e.g. `vsmon1c2.h`)

A module defines its *own* small enums, independent from FSV's global ones:

- Safe-state index enum for the module's local SST table, e.g.
  `VsMon_nenSstNormalOptIdx`, terminated with a `...MaxCount` sentinel used to
  size `VsMon__stLocalSstReqStatus[]`.
- A local timer-ID enum for `FsTmrCtl` (e.g. `VsMon__nenFsTIDNormOptTrans`,
  `...MaxCount`), used with `FSTMRCTL_DEFINE_TIMERS(<Module>_LocalSst,
  <Module>__nenFsTIDMaxCount, <Module>__nPeriodMs)`.
- A GUID for each safe state, built with
  `FSV_u32DefineModSafeStateGuid(<Module>_nModuleId, <Module>_nenModuleInternalScope, <idx>)`
  (mirrors how `fsv1ca.h` builds `FSV_nenSstNormalStartGuid` etc. for FSV's
  own safe states).

## 2. Add the module's local SST status table (in the module's `c2` file)

```c
VsMon_tstLocalSstReqStatus VsMon__stLocalSstReqStatus[VsMon_nenSstIdxMaxCount] =
{
    {
        .astSstStatusTable =
        {
            .u32SafeStateGuid = VsMon_nenSstNormalOptGuid,
            .u8RequestStatus = FSV_SST_STATUS_PASSIVE,
            .u8CurrentStatus = FSV_SST_STATUS_PENDING,
            .u8RollingCounter = 0U
        },
        .u8TimerIdx = VsMon__nenFsTIDNormOptTrans,
        .u16TimeoutMs = 10000U
    }
    /* one entry per safe state this module owns */
};
```

Implement (or reuse the existing pattern for) `<Module>_vInitSafeStateSm`,
`<Module>_vReqSafeStateTransitionSm`, `<Module>_vPreProcessSstReq`, and the
four `PASSIVE/PENDING/ACTIVE/ERROR` handlers, following section 7 of
[SKILL.md](../SKILL.md).

## 3. Register in FSV's central tables (`fsv1ca.c`/`fsv1ca.h`, all `#if`-guarded)

FSV needs to know how to *read* the module's safe-state status via RTE, and
how to *request* a safe-state change on the module. Three enums plus three
tables, always kept in the same relative order across all six:

### 3a. Timer ID enum (`FSV_tenSwcTimerId` in `fsv1ca.h`)
Add one entry per safe state this module registers with FSV, guarded by the
module's feature switch:
```c
#if(S3P_nPrjCfg_VSMonFsvSupervise == STD_ON)
    FSV__nenSwcTmrVsMonNormOpt,
#endif
```

### 3b. Software-module index enum (`FSV__tenSwModuleIfIndex` in `fsv1ca.h`)
One entry for the *module as a whole* (not per safe state):
```c
#if (S3P_nPrjCfg_VSMonFsvSupervise == STD_ON)
    FSV__nenSwModVsMon,
#endif // VSMonFsvSupervise
```

### 3c. Safe-state index enum (`FSV__tenSstIdx`-style enum in `fsv1ca.h`)
One entry per safe state, must stay in the exact same order as the safe-state
table in 3d:
```c
#if (S3P_nPrjCfg_VSMonFsvSupervise == STD_ON)
    FSV__nenSstIdxVsMonNormOpt,
#endif
```

### 3d. `FSV__astSafeStateTable[]` entry (`fsv1ca.c`)
Tells FSV how to *read* this safe state via RTE, which module owns it, which
timer tracks its transition timeout, and the timeout value:
```c
#if (S3P_nPrjCfg_VSMonFsvSupervise == STD_ON)
    {
        .u32SafeStateGuid = VsMon_nenSstNormalOptGuid,
        .pfGetSafeState = Rte_Read_RP_VsMon_SstNormOpt_stSstStatus,
        .enSwModuleIfIndex = FSV__nenSwModVsMon,
        .enTimerID = FSV__nenSwcTmrVsMonNormOpt,
        .u16SstReqTimeoutMs = FSV_nTimerTimeoutMs,
    },
#endif
```

### 3e. `FSV__astSWModuleIfTable[]` entry (`fsv1ca.c`)
Tells FSV how to *request* a safe-state change on this module via RTE (must
be at the same index as the module's entry in `FSV__tenSwModuleIfIndex`):
```c
#if (S3P_nPrjCfg_VSMonFsvSupervise == STD_ON)
    { Rte_Call_RP_VsMon_SafeStateReq_VsMon_enRequestSafeState},
#endif // VSMonFsvSupervise
```

### 3f. `FSV__astErrorMonitoringTable[]` entries (`fsv1ca.c`)
Declares the escalation graph: if `<safe state X>` goes to ERROR, FSV
requests `<safe state Y>` next. Every safe state that can go to ERROR must
have an outgoing edge, and every chain must terminate at
`FSV__nenSstIdxFsvSysReset` (the only safe state that triggers an actual MCU
reset) — this is checked at review time, not by the compiler:
```c
{ .u8MonitorSafeStateIndex = FSV__nenSstIdxVsMonNormOpt, .u8EscalationSafeStateIndex = FSV__nenSstIdxVidConDVcReset },
```
After adding entries, update the corresponding `FSV_nNumberOfSstErrorEntry`
component macro in `fsv1ca.h` (e.g. add a `FSV_n<Module>_Entries` guarded by
the same feature switch and fold it into the sum) — the table's size is
statically asserted against this macro:
```c
_Static_assert(FSV_SizeOfArray(FSV__astErrorMonitoringTable) == FSV_nNumberOfSstErrorEntry,
               "FSV__astErrorMonitoringTable size incorrect!");
```
A stale count here is a compile-time failure, so this is a good sanity check
that the registration was done consistently.

## 4. Wire the module's core `.c` file into the adapt layer's includes

`fsv1ca.c` must `#include` the new module's header (guarded by the same
switch) so the RTE call/read symbols resolve:
```c
#if (S3P_nPrjCfg_VSMonFsvSupervise == STD_ON)
#include "vsmon1c2.h"
#endif
```

## 5. Cross-check before finishing

- Every enum/table pair in step 3 uses the exact same `#if` condition and the
  same relative ordering (module index N in 3b ↔ entry N in 3e; safe-state
  index M in 3c ↔ entry M in 3d).
- Every safe state that can enter ERROR (section 7 of the main skill) has a
  monitoring-table edge (3f), and every edge chain eventually reaches
  `FSV__nenSstIdxFsvSysReset`.
- `FSV_nNumberOfSstErrorEntry` (and the `_Static_assert` it feeds) matches the
  actual number of entries added in 3f.
- The module's own local SST table (step 2) and its FSV-facing safe-state
  table entry (3d) reference the *same* GUID.
