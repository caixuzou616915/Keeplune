"""ghs-py-run — Orchestrator: chain connect -> [flash] -> debug -> report (event-driven).

Composes the individual steps into one pipeline while keeping each independently invokable. Design
rules that mirror the ``traveo_build_debug`` agent's Profile A (S3P meta-repo) behaviour:

* **Debug-only by default** — this orchestrator NEVER builds. Flashing happens only when
  ``--flash`` is passed explicitly (build is a separate concern handled outside these scripts).
* Every stage is event-driven (marker polling); a failed stage fast-fails and stops the chain.
* Always ends by emitting the three consistent outputs (console + JSON + canonical HTML) and the
  old-vs-new benchmark.

Examples::

    # Bring the (already-flashed) target to a running state, full report:
    python ghs-py-run.py --op run --simulate

    # Flash then read two variables:
    python ghs-py-run.py --flash --op read --variables AmmSM__enCurrentMode g_WdgM_SE_Status

    # Break on a function and capture ARM arg registers:
    python ghs-py-run.py --op breakpoint --function Mcu_PerformReset --regs '$r0' '$r1' '$lr'
"""
from __future__ import annotations

import argparse
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
config = _load("config")
report = _load("report")
connect = _load("connect")
flash = _load("flash")
debug_launch = _load("debug-launch")


def run_pipeline(args) -> int:
    cfg = config.load_config(
        bench=args.bench,
        variant=args.variant,
        project_root=args.project_root,
        skip_verify=(None if args.skip_verify is None else args.skip_verify),
        multi_rc=args.multi_rc,
        debug_rc=args.debug_rc,
        verify_py=args.verify_py,
        ceiling_op_s=args.ceiling_op,
    )
    task = f"debug:{args.op}" + (" (+flash)" if args.flash else "")
    rec = report.build_recorder(cfg, method="new-python", task=task,
                                device=args.device, simulate=args.simulate)
    runner = core.MultiRunner(cfg, simulate=args.simulate)

    ok = True
    # 1) connect
    if ok and "connect" in args.steps:
        ok = connect.step_connect(cfg, rec, simulate=args.simulate)
    # 2) flash (opt-in only — debug-only by default)
    if ok and args.flash and "flash" in args.steps:
        ok = flash.step_flash(cfg, rec, simulate=args.simulate)
    # 3) debug (VERIFY is embedded inside this self-contained Multi session)
    if ok and "debug" in args.steps:
        ok = debug_launch.step_debug(
            cfg, rec, runner, op=args.op, variables=args.variables, variable=args.variable,
            value=args.value, function=args.function, regs=args.regs, halt_on=args.halt_on,
            n_steps=args.n_steps, hold_s=args.hold_s, appmode_settle_s=args.appmode_settle_s,
            simulate=args.simulate)
    else:
        for name in ("connect", "flash", "debug"):
            if name not in args.steps:
                pass

    # 4) report (always) — console + JSON + canonical HTML + benchmark
    artifacts = report.emit(rec, out_dir=args.out_dir, base_name=args.name or "",
                            print_console=not args.quiet)
    if args.quiet:
        print(artifacts["json"])
        print(artifacts["html"])
    return 0 if rec.overall == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench", default="A", choices=["A", "B"], help="bench preset (default A)")
    ap.add_argument("--variant", default=None, help="override build variant")
    ap.add_argument("--project-root", dest="project_root", default=None)
    ap.add_argument("--multi-rc", dest="multi_rc", default=None,
                    help="override path (relative to build dir) to multi.rc, if it lives under a "
                         "differently-named app/variants/<...>/debug/ghs folder than the bench preset")
    ap.add_argument("--debug-rc", dest="debug_rc", default=None,
                    help="override path (relative to build dir) to the tvii_debug_*.rc driver")
    ap.add_argument("--verify-py", dest="verify_py", default=None,
                    help="override path (relative to build dir) to the tvii_debug_*.py VERIFY script")
    ap.add_argument("--ceiling-op", dest="ceiling_op", type=float, default=None,
                    help="override the safety-ceiling (seconds) for the debug op wait (default: config, 120s)")
    ap.add_argument("--device", default="GHS Multi")
    ap.add_argument("--op", default="run", choices=["run", "read", "write", "breakpoint", "sweep"],
                    help="debug operation (default: run = bring to running state)")
    ap.add_argument("--flash", action="store_true",
                    help="also flash before debugging (OFF by default — debug-only)")
    ap.add_argument("--steps", nargs="*", default=["connect", "flash", "debug"],
                    help="subset of stages to run")
    ap.add_argument("--variables", nargs="*", default=[])
    ap.add_argument("--variable", default="")
    ap.add_argument("--value", default="")
    ap.add_argument("--function", default="")
    ap.add_argument("--regs", nargs="*", default=["$r0", "$r1", "$lr"])
    ap.add_argument("--halt-on", dest="halt_on", default=None)
    ap.add_argument("--n-steps", dest="n_steps", type=int, default=1,
                    help="op=sweep: number of catch/print/resume steps in the single session")
    ap.add_argument("--hold-s", dest="hold_s", type=float, default=10.0,
                    help="op=sweep: seconds to hold each step (halted) before resuming")
    ap.add_argument("--appmode-settle-s", dest="appmode_settle_s", type=float, default=20.0,
                    help="op=sweep: seconds of free-run after VERIFY before arming the breakpoint, "
                         "to let an externally-injected precondition sequence land")
    ap.add_argument("--skip-verify", dest="skip_verify", type=lambda s: s not in ("0", "false"),
                    default=None, help="override TVII_SKIP_VERIFY (default: config)")
    ap.add_argument("--simulate", action="store_true",
                    help="no-hardware dry run that still exercises the full event pipeline + reports")
    ap.add_argument("--out-dir", dest="out_dir", default=None)
    ap.add_argument("--name", default=None, help="base name for the output artifacts")
    ap.add_argument("--quiet", action="store_true")
    return ap


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    return run_pipeline(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
