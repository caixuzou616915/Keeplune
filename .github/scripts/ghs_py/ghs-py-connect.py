"""ghs-py-connect — Composable step 1: bring the bench to a flash/debug-ready state.

Replaces the ``Start-CANoe.ps1`` + ``Stop-DebugProcesses`` (``Start-Sleep 4``) preamble with an
event/condition-based version:

* kill stale ``multi``/``mpserv`` holders and *poll* until they are actually gone (no fixed sleep),
* ensure CANoe measurement is running with KL15 ON (poll ``Measurement.Running``, not a delay).

Can be invoked on its own (``python ghs-py-connect.py``) or chained by the orchestrator.
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


def step_connect(cfg, rec, *, simulate: bool = False) -> bool:
    """Ensure a clean, powered, flash-ready bench. Records into ``rec``. Returns True on success."""
    step = rec.begin_step("connect")
    try:
        if simulate:
            step.event("note", "simulate: skip real taskkill of multi/mpserv")
        else:
            step.event("cmd", "kill stale multi/mpserv holders")
            core.kill_stale("multi.exe", "mpserv.exe", settle_ceiling_s=cfg.ceiling_connect_s,
                            poll_s=cfg.poll_interval_s)
            step.event("note", "probe holders clear")

        ok, detail = core.ensure_canoe(cfg, step, simulate=simulate)
        if not ok:
            rec.add_error(output.ErrorRecord(
                step="connect", message=detail, handled=False,
                action="abort — start CANoe with KL15 ON before retrying"))
            rec.end_step(output.FAIL, detail=detail, error=detail)
            return False

        rec.end_step(output.PASS, detail=detail)
        return True
    except Exception as exc:  # fast-fail, surface immediately
        rec.add_error(output.ErrorRecord(step="connect", message=str(exc), handled=False,
                                         action="abort"))
        rec.end_step(output.FAIL, error=str(exc))
        return False


def main(argv) -> int:
    report = _load("report")
    config = _load("config")
    import argparse
    ap = argparse.ArgumentParser(description="Ghs-py connect step (CANoe/KL15 + probe cleanup)")
    ap.add_argument("--bench", default="A")
    ap.add_argument("--simulate", action="store_true")
    args = ap.parse_args(argv)

    cfg = config.load_config(bench=args.bench)
    rec = report.build_recorder(cfg, task="connect", simulate=args.simulate)
    ok = step_connect(cfg, rec, simulate=args.simulate)
    report.emit(rec, base_name="")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
