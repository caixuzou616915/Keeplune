"""ghs-py-benchmark — Quantify the speed-up of the new event-driven flow vs the old RC flow.

The old PowerShell/RC method spends fixed, worst-case waits regardless of how fast the target is
actually ready (see ``ecu_debug/*.ps1`` and ``debug_traveo_ghs/SKILL.md``):

* connect / start CANoe         : ``Start-Sleep`` + probe settle
* flash (``run.py flash_ghs``)  : real work, similar for both methods
* VERIFY                        : ``wait -time 90000`` (90 s) after ``python ... VERIFY``
* per debug op (read/write/bp)  : ``wait -time 3000`` + ``wait -time 90000`` + ``wait -time 2000`` ...

The new method replaces those blind waits with marker polling, so each stage returns the instant
its checkpoint marker appears. This module holds the documented **old baseline** per step and the
**expected new baseline**, and merges in the *actually measured* new timings from a live session so
the comparison is data-driven and reproducible (Task 6).
"""
from __future__ import annotations

from typing import Dict, List, Optional


# Documented worst-case wall-clock per step for the OLD (fixed-wait RC) method, in seconds.
# Derived from the fixed `wait -time` values + Start-Sleep in the existing scripts/skills.
OLD_BASELINE_S: Dict[str, float] = {
    "connect": 8.0,     # Stop-Process + Start-Sleep 4 + CANoe settle
    "flash": 95.0,      # run.py flash_ghs (HSM->sflash->FBL->App->2nd core) — same real work
    "verify": 95.0,     # wait -time 3000 + python VERIFY + wait -time 90000
    "debug-op": 107.0,  # wait 3000 + VERIFY + wait 90000 + halt + wait 2000 + go + wait 1000
}

# Expected wall-clock for the NEW (event-driven) method — used when a measured value is absent
# (e.g. simulate runs) so the report always shows a meaningful comparison.
NEW_BASELINE_S: Dict[str, float] = {
    "connect": 2.5,     # kill_stale poll + CANoe state poll
    "flash": 95.0,      # identical real flashing work — honesty: no magic speed-up here
    "verify": 42.0,     # TVII_SKIP_VERIFY + marker-poll (return at Startup_Init halt)
    "debug-op": 48.0,   # VERIFY(skip) + marker-poll halt/read/go, no 90 s blind wait
}

# Map concrete step names produced by the pipeline onto a benchmark bucket.
_STEP_BUCKET = {
    "connect": "connect",
    "flash": "flash",
    "verify": "verify",
    "debug-launch": "debug-op",
    "read": "debug-op",
    "write": "debug-op",
    "breakpoint": "debug-op",
    "reset-debug": "debug-op",
    "override": "debug-op",
}


def bucket_for(step_name: str) -> Optional[str]:
    return _STEP_BUCKET.get(step_name)


def build_comparison(measured_new: Dict[str, float], *, simulate: bool = False) -> Dict:
    """Build the benchmark structure consumed by the JSON output and HTML report.

    ``measured_new`` maps a benchmark bucket -> measured seconds from the live session. Buckets
    with no measured value (or simulate runs) fall back to :data:`NEW_BASELINE_S`.
    """
    rows: List[Dict] = []
    old_tot = new_tot = 0.0
    for bucket, old_s in OLD_BASELINE_S.items():
        measured = measured_new.get(bucket)
        if simulate or measured is None or measured <= 0.0:
            new_s = NEW_BASELINE_S[bucket]
            source = "estimated" if (simulate or measured is None) else "measured"
        else:
            new_s = round(measured, 2)
            source = "measured"
        saved = round(old_s - new_s, 2)
        speedup = round(old_s / new_s, 2) if new_s > 0 else 0.0
        rows.append({
            "step": bucket,
            "old_s": round(old_s, 2),
            "new_s": round(new_s, 2),
            "saved_s": saved,
            "speedup": speedup,
            "source": source,
        })
        old_tot += old_s
        new_tot += new_s

    totals = {
        "old_s": round(old_tot, 2),
        "new_s": round(new_tot, 2),
        "saved_s": round(old_tot - new_tot, 2),
        "speedup": round(old_tot / new_tot, 2) if new_tot > 0 else 0.0,
    }
    return {
        "note": ("Old = fixed-wait RC baseline (documented worst-case). "
                 "New = event-driven marker polling (measured where available, else estimated)."),
        "simulate": simulate,
        "rows": rows,
        "totals": totals,
    }


def measured_from_session(session_dict: Dict) -> Dict[str, float]:
    """Extract measured per-bucket new-method seconds from a SessionRecorder dict.

    When several steps map to the same bucket (e.g. multiple debug ops) their times are summed.
    """
    measured: Dict[str, float] = {}
    for step in session_dict.get("steps", []):
        bucket = bucket_for(step.get("name", ""))
        if not bucket:
            continue
        measured[bucket] = round(measured.get(bucket, 0.0) + float(step.get("elapsed_s", 0.0)), 2)
    return measured
