"""ghs-py-debug-launch — Composable step 4: bring the target up and run debug operations.

This is the event-driven replacement for ``Start-Debug.ps1`` / ``Read-Variable.ps1`` /
``Write-Variable.ps1``. It runs **one** self-contained Multi session (VERIFY + operation + quit),
because a GHS Multi ``-p`` session detaches on ``quit`` — so the connect and the operation must
share the session (exactly as the proven RC scripts do).

Every checkpoint is a sentinel marker polled by :class:`MultiRunner`, so there is **no**
``wait -time 3000/90000`` idling. Values are captured between unique ``RDBEG``/``RDEND`` markers
using plain ``print`` (never ``mprintf`` with variable args — that hangs in playback, per the GHS
skill).

Supported operations (``op``):
    run         — VERIFY then ``target gc`` (bring system to running state)
    read        — read one or more variables (at the Startup_Init halt, or after ``halt_on`` BP)
    write       — write a value to a variable, verifying before/after
    breakpoint  — ``hardbrk rolling FUNC`` + ``target gc`` + read ARM arg registers on hit
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

_HERE = Path(__file__).resolve().parent


def _load(short: str):
    path = _HERE / f"ghs-py-{short}.py"
    spec = importlib.util.spec_from_file_location(f"ghs_py_{short}", path)
    mod = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
    sys.modules[spec.name] = mod                          # register for dataclass resolution
    spec.loader.exec_module(mod)                          # type: ignore[union-attr]
    return mod


core = _load("core")
output = _load("output")


# --------------------------------------------------------------------------------------------------
# RC building blocks
# --------------------------------------------------------------------------------------------------
def _verify_prefix(cfg) -> List[str]:
    p = cfg.core_prefix
    return [
        f"python -b -f {cfg.verify_py} VERIFY",
        f"alias {p} route {cfg.app_core}",
        core.rc_marker("VERIFY_DONE", p),
    ]


def _capture(cfg, idx: int, expr: str) -> List[str]:
    """RC lines that fence a ``print EXPR`` between unique markers for reliable value capture."""
    p = cfg.core_prefix
    return [core.rc_marker(f"RDBEG_{idx}", p), f"{p} print {expr}", core.rc_marker(f"RDEND_{idx}", p)]


def _parse_captures(log_text: str, count: int) -> Dict[int, str]:
    """Extract the value printed between each RDBEG_i / RDEND_i marker pair."""
    values: Dict[int, str] = {}
    for idx in range(count):
        beg = f"{core.MARKER_PREFIX}RDBEG_{idx}{core.MARKER_SUFFIX}"
        end = f"{core.MARKER_PREFIX}RDEND_{idx}{core.MARKER_SUFFIX}"
        # NOTE (2026-07-28 bug fix): Multi echoes each RC command as a `// m4 ...` comment line
        # immediately before executing it -- and that echo literally embeds the marker text
        # (e.g. `// m4 mprintf(">>>TVPY:RDBEG_0<<<\n")`), which also contains the raw marker
        # substring. A plain .find() can therefore match this comment-echo instead of the real
        # runtime marker line. Use rfind() to anchor on the LAST occurrence of each marker (the
        # true runtime one, since the comment-echo for a given command always precedes its own
        # real output/marker).
        b, e = log_text.rfind(beg), log_text.rfind(end)
        if b < 0 or e < 0 or e < b:
            values[idx] = "?"
            continue
        chunk = log_text[b + len(beg):e]
        # Also drop RC-echo/comment lines (`//...`) and `>>>...<<<` route wrapper noise --
        # only genuine printed output (e.g. "0x00000000" or "EXPR = value") should remain.
        lines = [ln.strip() for ln in chunk.splitlines()
                 if ln.strip() and not any(x in ln for x in core.BENIGN_SUBSTRINGS)
                 and core.MARKER_PREFIX not in ln
                 and not ln.strip().startswith("//")]
        raw = lines[-1] if lines else "?"
        # `print` output is often "EXPR = value" — keep the RHS when present.
        m = re.search(r"=\s*(.+)$", raw)
        values[idx] = (m.group(1).strip() if m else raw)
    return values


def _read_full_log(cfg, log_name: str) -> str:
    path = Path(cfg.build_dir()) / log_name
    if not path.exists():
        return ""
    return path.read_text(encoding="ascii", errors="replace")


# --------------------------------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------------------------------
def _op_run(cfg, rec, runner, step, *, simulate: bool) -> bool:
    p = cfg.core_prefix
    rc = core.build_rc(_verify_prefix(cfg) + [
        "target gc",
        core.rc_marker("RUNNING", p),
        "quit",
    ])
    sim = None
    if simulate:
        sim = [
            (0.1, "VERIFY: halted at Startup_Init"),
            (0.05, f"{core.MARKER_PREFIX}VERIFY_DONE{core.MARKER_SUFFIX}"),
            (0.1, "target gc: all cores running"),
            (0.05, f"{core.MARKER_PREFIX}RUNNING{core.MARKER_SUFFIX}"),
        ]
    res = runner.run(step, rc, wait_tags=["VERIFY_DONE", "RUNNING"], ceiling_s=cfg.ceiling_op_s,
                     rc_name="tvpy_run.rc", log_name="tvpy_run_out.txt", sim_timeline=sim)
    if res.ok:
        rec.end_step(output.PASS, detail="system running (all cores released via target gc)")
        return True
    return _fail(rec, step, res, "run")


def _op_read(cfg, rec, runner, step, *, variables: List[str], halt_on: Optional[str],
             simulate: bool) -> bool:
    p = cfg.core_prefix
    lines = list(_verify_prefix(cfg))
    if halt_on:
        rec.add_breakpoint(output.Breakpoint(function=halt_on, kind="hardbrk rolling"))
        lines += [f"{p} hardbrk rolling {halt_on}", "target gc", "wait -stop -time 60000",
                  core.rc_marker("HALTED", p)]
    for i, v in enumerate(variables):
        lines += _capture(cfg, i, v)
    lines += [core.rc_marker("READ_DONE", p), "quit"]
    rc = core.build_rc(lines)

    sim = None
    if simulate:
        sim = [(0.1, "VERIFY: halted at Startup_Init"),
               (0.05, f"{core.MARKER_PREFIX}VERIFY_DONE{core.MARKER_SUFFIX}")]
        if halt_on:
            sim += [(0.1, f"halted at {halt_on}"),
                    (0.05, f"{core.MARKER_PREFIX}HALTED{core.MARKER_SUFFIX}")]
        for i, v in enumerate(variables):
            sim += [(0.02, f"{core.MARKER_PREFIX}RDBEG_{i}{core.MARKER_SUFFIX}"),
                    (0.02, f"{v} = 0x{(i + 1) * 17:X}"),
                    (0.02, f"{core.MARKER_PREFIX}RDEND_{i}{core.MARKER_SUFFIX}")]
        sim += [(0.03, f"{core.MARKER_PREFIX}READ_DONE{core.MARKER_SUFFIX}")]

    wait_tags = ["VERIFY_DONE"] + (["HALTED"] if halt_on else []) + ["READ_DONE"]
    res = runner.run(step, rc, wait_tags=wait_tags, ceiling_s=cfg.ceiling_op_s,
                     rc_name="tvpy_read.rc", log_name="tvpy_read_out.txt", sim_timeline=sim)
    if not res.ok:
        return _fail(rec, step, res, "read")

    log_text = _read_full_log(cfg, "tvpy_read_out.txt")
    values = _parse_captures(log_text, len(variables))
    for i, v in enumerate(variables):
        rec.add_inspection(output.Inspection(name=v, scope="variable", expr=v,
                                              value=values.get(i, "?")))
        step.event("value", f"{v} = {values.get(i, '?')}")
    if halt_on:
        for b in rec.breakpoints:
            if b.function == halt_on:
                b.hit = True
                b.hit_count += 1
    detail = "; ".join(f"{v}={values.get(i, '?')}" for i, v in enumerate(variables))
    rec.end_step(output.PASS, detail=f"read {len(variables)} var(s): {detail}")
    return True


def _op_write(cfg, rec, runner, step, *, variable: str, value: str, halt_on: Optional[str],
              simulate: bool) -> bool:
    p = cfg.core_prefix
    lines = list(_verify_prefix(cfg))
    if halt_on:
        rec.add_breakpoint(output.Breakpoint(function=halt_on, kind="hardbrk rolling"))
        lines += [f"{p} hardbrk rolling {halt_on}", "target gc", "wait -stop -time 60000",
                  core.rc_marker("HALTED", p)]
    lines += _capture(cfg, 0, variable)                    # before
    lines += [f"{p} set {variable} = {value}"]
    lines += _capture(cfg, 1, variable)                    # after
    lines += [core.rc_marker("WRITE_DONE", p), "quit"]
    rc = core.build_rc(lines)

    sim = None
    if simulate:
        sim = [(0.1, f"{core.MARKER_PREFIX}VERIFY_DONE{core.MARKER_SUFFIX}")]
        if halt_on:
            sim += [(0.05, f"{core.MARKER_PREFIX}HALTED{core.MARKER_SUFFIX}")]
        sim += [
            (0.02, f"{core.MARKER_PREFIX}RDBEG_0{core.MARKER_SUFFIX}"),
            (0.02, f"{variable} = 0x0"),
            (0.02, f"{core.MARKER_PREFIX}RDEND_0{core.MARKER_SUFFIX}"),
            (0.02, f"{core.MARKER_PREFIX}RDBEG_1{core.MARKER_SUFFIX}"),
            (0.02, f"{variable} = {value}"),
            (0.02, f"{core.MARKER_PREFIX}RDEND_1{core.MARKER_SUFFIX}"),
            (0.03, f"{core.MARKER_PREFIX}WRITE_DONE{core.MARKER_SUFFIX}"),
        ]
    wait_tags = ["VERIFY_DONE"] + (["HALTED"] if halt_on else []) + ["WRITE_DONE"]
    res = runner.run(step, rc, wait_tags=wait_tags, ceiling_s=cfg.ceiling_op_s,
                     rc_name="tvpy_write.rc", log_name="tvpy_write_out.txt", sim_timeline=sim)
    if not res.ok:
        return _fail(rec, step, res, "write")

    log_text = _read_full_log(cfg, "tvpy_write_out.txt")
    vals = _parse_captures(log_text, 2)
    before, after = vals.get(0, "?"), vals.get(1, "?")
    rec.add_inspection(output.Inspection(name=f"{variable} (before)", scope="variable",
                                         expr=variable, value=before))
    rec.add_inspection(output.Inspection(name=f"{variable} (after)", scope="variable",
                                         expr=variable, value=after))
    step.event("value", f"{variable}: {before} -> {after} (wrote {value})")
    rec.end_step(output.PASS, detail=f"{variable}: {before} -> {after} (requested {value})")
    return True


def _op_sweep(cfg, rec, runner, step, *, variables: List[str], halt_on: str,
             n_steps: int, hold_s: float, appmode_settle_s: float,
             on_appmode_ready: Optional[Callable[[], None]],
             on_step_ready: Optional[Callable[[int], None]],
             simulate: bool) -> bool:
    """One self-contained Multi session covering an ENTIRE multi-level sweep.

    Unlike ``read``/``write``/``breakpoint`` (one VERIFY per call -- and VERIFY forces a full MCU
    reset, see backlight_debug_sweep.md point 22), this op does exactly ONE VERIFY, then keeps the
    target free-running across all ``n_steps`` catches, so external state (e.g. an App-Mode CAN
    sequence, or a series of brightness commands) injected by the caller between catches is NOT
    wiped out by a subsequent reset.

    Design (fixed 2026-07-28 -- see backlight_debug_sweep.md point 28 for the bug this replaces):
    VERIFY -> ``target gc`` (free-run) -> APPMODE_READY marker (caller injects preconditions here,
    e.g. an App-Mode sequence + the first level) -> settle wait (REAL, target running) -> for
    i in 0..n_steps-1: arm ``hardbrk rolling`` -> ``wait -stop`` (catch the settled value for the
    level committed during the *previous* hold) -> STEP_i_HALT marker -> print each variable ->
    STEP_i_READY marker (caller injects the NEXT level here, while the core is halted -- a halted
    core does not tick the watchdog, so this is safe) -> ``delete`` (disarm the breakpoint so the
    core can actually run free instead of instantly re-halting on the very next call of this
    high-frequency RTE function) -> ``target gc`` (resume) -> REAL ``wait -time hold_s`` (the
    SigCtl ramp gets genuine wall-clock time to converge toward the newly committed level while
    the CPU is actually executing) -> loop back to re-arm for the next catch -> SWEEP_DONE -> quit.

    IMPORTANT (root cause of the original bug): a rolling ``hardbrk`` on a function called on
    (almost) every RTE cycle makes the CPU halt again the INSTANT it is resumed -- a hardware
    breakpoint stops the core the moment the address is hit, regardless of whether the RC script
    orders ``wait -time`` before or after ``target gc``. So any hold placed while the breakpoint is
    still armed elapses with the CPU effectively halted (at most ~1 RTE cycle of real progress),
    which is why the old design only ever observed tiny per-catch deltas or a stale/zero value. The
    breakpoint MUST be deleted for the hold window and re-armed only immediately before the next
    catch.

    ``on_appmode_ready``/``on_step_ready`` are invoked (via ``MultiRunner.run``'s ``on_marker``
    hook) the instant the corresponding marker appears in the log -- i.e. while Multi is genuinely
    paused/running at that point in the session, not after the whole session ends.
    """
    p = cfg.core_prefix
    if n_steps < 1:
        raise ValueError("n_steps must be >= 1")
    rec.add_breakpoint(output.Breakpoint(function=halt_on, kind="hardbrk rolling"))

    lines = list(_verify_prefix(cfg))
    lines += ["target gc", core.rc_marker("APPMODE_READY", p),
              f"wait -time {int(appmode_settle_s * 1000)}"]
    for i in range(n_steps):
        lines += [f"{p} hardbrk rolling {halt_on}", f"{p} wait -stop -time 60000",
                  core.rc_marker(f"STEP_{i}_HALT", p)]
        for vi, v in enumerate(variables):
            lines += _capture(cfg, i * len(variables) + vi, v)
        lines += [core.rc_marker(f"STEP_{i}_READY", p)]
        if i < n_steps - 1:
            # NOTE (2026-07-28 bug fix, 2nd iteration): plain "{p} delete" fails with
            # "Unknown name "delete" in expression." and bare "delete" (no core route) fails
            # with "Process running, can't find "delete"." -- neither is valid GHS Multi syntax
            # here. The proven working form (confirmed via pyconti/libtst/multi.py's COM-level
            # `dw.RunCmd("hardbrk delete = *", ...)`) is `hardbrk delete = *`, routed through the
            # same core alias used to ARM the breakpoint (`{p} hardbrk rolling FUNC`). This bug
            # previously caused the whole sweep to hang forever after STEP_0 (recoverable only via
            # the 900s safety ceiling force-killing Multi).
            lines += [f"{p} hardbrk delete = *", f"{p} target gc",
                      f"{p} wait -time {int(hold_s * 1000)}"]
    lines += [core.rc_marker("SWEEP_DONE", p), "quit"]
    rc = core.build_rc(lines)

    sim = None
    if simulate:
        sim = [(0.1, f"{core.MARKER_PREFIX}VERIFY_DONE{core.MARKER_SUFFIX}"),
               (0.05, f"{core.MARKER_PREFIX}APPMODE_READY{core.MARKER_SUFFIX}")]
        for i in range(n_steps):
            sim.append((0.05, f"{core.MARKER_PREFIX}STEP_{i}_HALT{core.MARKER_SUFFIX}"))
            for vi, v in enumerate(variables):
                idx = i * len(variables) + vi
                sim += [(0.02, f"{core.MARKER_PREFIX}RDBEG_{idx}{core.MARKER_SUFFIX}"),
                        (0.02, f"{v} = 0x{(i + 1) * 17:X}"),
                        (0.02, f"{core.MARKER_PREFIX}RDEND_{idx}{core.MARKER_SUFFIX}")]
            sim.append((0.02, f"{core.MARKER_PREFIX}STEP_{i}_READY{core.MARKER_SUFFIX}"))
        sim.append((0.03, f"{core.MARKER_PREFIX}SWEEP_DONE{core.MARKER_SUFFIX}"))

    wait_tags = (["VERIFY_DONE", "APPMODE_READY"]
                 + [f"STEP_{i}_HALT" for i in range(n_steps)]
                 + [f"STEP_{i}_READY" for i in range(n_steps)]
                 + ["SWEEP_DONE"])

    step_ready_re = re.compile(r"^STEP_(\d+)_READY$")

    def _on_marker(tag: str) -> None:
        if tag == "APPMODE_READY" and on_appmode_ready is not None:
            on_appmode_ready()
            return
        m = step_ready_re.match(tag)
        if m and on_step_ready is not None:
            on_step_ready(int(m.group(1)))

    res = runner.run(step, rc, wait_tags=wait_tags, ceiling_s=cfg.ceiling_op_s,
                     rc_name="tvpy_sweep.rc", log_name="tvpy_sweep_out.txt", sim_timeline=sim,
                     on_marker=_on_marker)
    if not res.ok:
        return _fail(rec, step, res, "sweep")

    log_text = _read_full_log(cfg, "tvpy_sweep_out.txt")
    n_vars = len(variables)
    values = _parse_captures(log_text, n_steps * n_vars)
    per_step: List[Dict[str, str]] = []
    for i in range(n_steps):
        row = {v: values.get(i * n_vars + vi, "?") for vi, v in enumerate(variables)}
        per_step.append(row)
        rec.add_inspection(output.Inspection(name=f"step{i}", scope="sweep-step",
                                             expr=f"step {i}", value=str(row)))
        step.event("value", f"step {i}: {row}")
    for b in rec.breakpoints:
        if b.function == halt_on:
            b.hit = True
            b.hit_count = n_steps
    rec.end_step(output.PASS, detail=f"sweep {n_steps} step(s) captured")
    return True


def _op_breakpoint(cfg, rec, runner, step, *, function: str, regs: List[str],
                   simulate: bool) -> bool:
    p = cfg.core_prefix
    bp = output.Breakpoint(function=function, kind="hardbrk rolling")
    rec.add_breakpoint(bp)
    lines = list(_verify_prefix(cfg))
    lines += [f"{p} hardbrk rolling {function}", "target gc", "wait -stop -time 60000",
              core.rc_marker("BP_HIT", p)]
    for i, r in enumerate(regs):
        lines += _capture(cfg, i, r)
    lines += [core.rc_marker("BP_DONE", p), "quit"]
    rc = core.build_rc(lines)

    sim = None
    if simulate:
        sim = [(0.1, f"{core.MARKER_PREFIX}VERIFY_DONE{core.MARKER_SUFFIX}"),
               (0.1, f"hardbrk hit at {function}"),
               (0.05, f"{core.MARKER_PREFIX}BP_HIT{core.MARKER_SUFFIX}")]
        for i, r in enumerate(regs):
            sim += [(0.02, f"{core.MARKER_PREFIX}RDBEG_{i}{core.MARKER_SUFFIX}"),
                    (0.02, f"{r} = 0x{0x1000 + i * 4:X}"),
                    (0.02, f"{core.MARKER_PREFIX}RDEND_{i}{core.MARKER_SUFFIX}")]
        sim += [(0.03, f"{core.MARKER_PREFIX}BP_DONE{core.MARKER_SUFFIX}")]

    res = runner.run(step, rc, wait_tags=["VERIFY_DONE", "BP_HIT", "BP_DONE"],
                     ceiling_s=cfg.ceiling_op_s, rc_name="tvpy_bp.rc",
                     log_name="tvpy_bp_out.txt", sim_timeline=sim)
    if not res.ok:
        return _fail(rec, step, res, "breakpoint")

    bp.hit = True
    bp.hit_count = 1
    log_text = _read_full_log(cfg, "tvpy_bp_out.txt")
    vals = _parse_captures(log_text, len(regs))
    for i, r in enumerate(regs):
        bp.values[r] = vals.get(i, "?")
        rec.add_inspection(output.Inspection(name=r, scope="register", expr=r,
                                             value=vals.get(i, "?")))
        step.event("value", f"{r} = {vals.get(i, '?')}")
    rec.end_step(output.PASS, detail=f"BP {function} hit; "
                 + ", ".join(f"{r}={vals.get(i, '?')}" for i, r in enumerate(regs)))
    return True


def _fail(rec, step, res, op: str) -> bool:
    if res.fatal_line:
        rec.add_error(output.ErrorRecord(step=step.name, message=res.fatal_line,
                                         marker=res.fatal_line, handled=False,
                                         action="killed Multi (fast-fail)"))
        rec.end_step(output.FAIL, detail=f"{op} fatal", error=res.fatal_line)
    else:
        rec.add_error(output.ErrorRecord(step=step.name, message="safety ceiling hit",
                                         handled=False, action="killed Multi; check probe/BP name"))
        rec.end_step(output.FAIL, detail=f"{op} timed out (safety ceiling)",
                     error=res.log_tail[-200:])
    return False


# --------------------------------------------------------------------------------------------------
# Public entry
# --------------------------------------------------------------------------------------------------
def step_debug(cfg, rec, runner, *, op: str = "run", variables: Optional[List[str]] = None,
               variable: str = "", value: str = "", function: str = "",
               regs: Optional[List[str]] = None, halt_on: Optional[str] = None,
               n_steps: int = 1, hold_s: float = 10.0, appmode_settle_s: float = 20.0,
               on_appmode_ready: Optional[Callable[[], None]] = None,
               on_step_ready: Optional[Callable[[int], None]] = None,
               simulate: bool = False) -> bool:
    """Run one debug operation as a single self-contained Multi session."""
    step = rec.begin_step(op if op != "run" else "debug-launch")
    step.event("note", f"debug op '{op}' on {cfg.app_core} (skip_verify={cfg.skip_verify})")
    try:
        if op == "run":
            return _op_run(cfg, rec, runner, step, simulate=simulate)
        if op == "read":
            return _op_read(cfg, rec, runner, step, variables=variables or [],
                            halt_on=halt_on, simulate=simulate)
        if op == "write":
            return _op_write(cfg, rec, runner, step, variable=variable, value=value,
                             halt_on=halt_on, simulate=simulate)
        if op == "breakpoint":
            return _op_breakpoint(cfg, rec, runner, step, function=function,
                                  regs=regs or ["$r0", "$r1", "$lr"], simulate=simulate)
        if op == "sweep":
            if not halt_on:
                rec.end_step(output.FAIL, error="op 'sweep' requires --halt-on")
                return False
            return _op_sweep(cfg, rec, runner, step, variables=variables or ["$r0"],
                             halt_on=halt_on, n_steps=n_steps, hold_s=hold_s,
                             appmode_settle_s=appmode_settle_s,
                             on_appmode_ready=on_appmode_ready, on_step_ready=on_step_ready,
                             simulate=simulate)
        rec.end_step(output.FAIL, error=f"unknown op '{op}'")
        return False
    except Exception as exc:
        rec.add_error(output.ErrorRecord(step=step.name, message=str(exc), handled=False,
                                         action="abort"))
        rec.end_step(output.FAIL, error=str(exc))
        return False


def main(argv) -> int:
    report = _load("report")
    config = _load("config")
    import argparse
    ap = argparse.ArgumentParser(description="Ghs-py debug-launch step")
    ap.add_argument("--bench", default="A")
    ap.add_argument("--op", choices=["run", "read", "write", "breakpoint"], default="run")
    ap.add_argument("--variables", nargs="*", default=[])
    ap.add_argument("--variable", default="")
    ap.add_argument("--value", default="")
    ap.add_argument("--function", default="")
    ap.add_argument("--regs", nargs="*", default=["$r0", "$r1", "$lr"])
    ap.add_argument("--halt-on", dest="halt_on", default=None)
    ap.add_argument("--simulate", action="store_true")
    args = ap.parse_args(argv)

    cfg = config.load_config(bench=args.bench)
    rec = report.build_recorder(cfg, task=f"debug:{args.op}", simulate=args.simulate)
    runner = core.MultiRunner(cfg, simulate=args.simulate)
    ok = step_debug(cfg, rec, runner, op=args.op, variables=args.variables,
                    variable=args.variable, value=args.value, function=args.function,
                    regs=args.regs, halt_on=args.halt_on, simulate=args.simulate)
    report.emit(rec, base_name="")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
