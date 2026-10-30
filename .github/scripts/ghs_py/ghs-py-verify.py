"""ghs-py-verify — Composable step 3: connect the probe + load symbols (VERIFY), event-driven.

Replaces the old ``wait -time 3000`` + ``python ... VERIFY`` + ``wait -time 90000`` sequence. The
``python ... VERIFY`` command already blocks inside Multi until the core halts at ``Startup_Init``;
we drop *both* surrounding fixed waits and instead emit a ``VERIFY_DONE`` marker right after it and
poll for that marker — so the step returns the instant the target is halted-and-ready, not 90 s
later. ``TVII_SKIP_VERIFY=1`` (config default) skips the slow HSM-ROM ``verify -all`` (~40 s vs 95 s)
while still connecting and arming breakpoints.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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

# Breakpoints the debug .py auto-arms after VERIFY (documented in debug_traveo_ghs SKILL).
_PREARMED = ("Startup_Init", "ErrorHook", "Mcu_PerformReset")


def build_verify_rc(cfg) -> str:
    p = cfg.core_prefix
    return core.build_rc([
        f"python -b -f {cfg.verify_py} VERIFY",
        f"alias {p} route {cfg.app_core}",
        core.rc_marker("VERIFY_DONE", p),
        "quit",
    ])


def _sim_timeline(cfg):
    return [
        (0.1, "VERIFY: connecting probe"),
        (0.1, "INCOHERENT ... (benign HSM dump)"),
        (0.1, "VERIFY: symbols downloaded"),
        (0.1, "halted at Startup_Init"),
        (0.05, f"{core.MARKER_PREFIX}VERIFY_DONE{core.MARKER_SUFFIX}"),
    ]


def step_verify(cfg, rec, runner, *, simulate: bool = False) -> bool:
    """Connect + load symbols + halt at Startup_Init. Returns True on success."""
    step = rec.begin_step("verify")
    step.event("note", f"VERIFY (skip_verify={cfg.skip_verify}) on {cfg.app_core}")
    for fn in _PREARMED:
        rec.add_breakpoint(output.Breakpoint(function=fn, kind="pre-armed hardbrk rolling",
                                              hit=(fn == "Startup_Init")))

    res = runner.run(step, build_verify_rc(cfg), wait_tags=["VERIFY_DONE"],
                     ceiling_s=cfg.ceiling_verify_s, rc_name="tvpy_verify.rc",
                     log_name="tvpy_verify_out.txt",
                     sim_timeline=_sim_timeline(cfg) if simulate else None)

    if res.ok:
        rec.end_step(output.PASS, detail="probe connected, symbols loaded, halted at Startup_Init")
        return True

    if res.fatal_line:
        rec.add_error(output.ErrorRecord(step="verify", message=res.fatal_line, marker=res.fatal_line,
                                         handled=False, action="killed Multi (fast-fail)"))
        rec.end_step(output.FAIL, detail="VERIFY fatal", error=res.fatal_line)
    else:
        rec.add_error(output.ErrorRecord(step="verify", message="safety ceiling hit", handled=False,
                                         action="killed Multi; check probe/CANoe"))
        rec.end_step(output.FAIL, detail="VERIFY timed out (safety ceiling)",
                     error=res.log_tail[-200:])
    return False


def main(argv) -> int:
    report = _load("report")
    config = _load("config")
    import argparse
    ap = argparse.ArgumentParser(description="Ghs-py VERIFY step (connect + symbols)")
    ap.add_argument("--bench", default="A")
    ap.add_argument("--simulate", action="store_true")
    args = ap.parse_args(argv)

    cfg = config.load_config(bench=args.bench)
    rec = report.build_recorder(cfg, task="verify", simulate=args.simulate)
    runner = core.MultiRunner(cfg, simulate=args.simulate)
    ok = step_verify(cfg, rec, runner, simulate=args.simulate)
    report.emit(rec, base_name="")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
