"""ghs-py-flash — Composable step 2: flash the ECU via ``run.py flash_ghs``.

Mirrors ``Flash-ECU.ps1`` (the verified working flash path) but reacts to the flash tool's *output
stream* instead of blindly waiting: it reads ``run.py flash_ghs`` line-by-line, surfaces a fatal
error the instant it appears (fast-fail, killing the process), and retries **once** only for the
documented transient probe/USB glitch — never a blind retry loop.

Real flashing work is inherently ~equal for both methods; the win here is *fast-fail* and *no idle
tail wait* after completion.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
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

# Progress markers emitted by the flash tool — logged as timeline events (not waited on).
_PROGRESS = ("HSM", "sflash", "FBL", "endprod", "second", "programmed", "flash_ghs", "verify")
_SUCCESS = ("flash_ghs: done", "Flashing done", "All images written", "SUCCESS")


def _bash_flash_cmd(cfg) -> str:
    return (f"cd {cfg.bash_project_root()} && source econ_config.sh && "
            f"./run.py {cfg.variant} flash_ghs 2>&1")


def _sim_flash_lines(cfg):
    return [
        (0.05, "[flash] source econ_config.sh"),
        (0.05, "[flash] HSM SHE ext entry ... programmed"),
        (0.05, "[flash] sflash dual bank ... programmed"),
        (0.05, "[flash] FBL ... programmed"),
        (0.05, f"[flash] App {cfg.variant} endprod ... programmed"),
        (0.05, "[flash] second core ... programmed"),
        (0.03, "flash_ghs: done"),
    ]


def _run_once(cfg, rec, step, *, simulate: bool):
    """One flash attempt. Returns (ok, fatal_line)."""
    if simulate:
        for delay, line in _sim_flash_lines(cfg):
            time.sleep(delay)
            _consume(rec, step, line)
        return True, ""

    proc = subprocess.Popen(
        [cfg.git_bash, "-c", _bash_flash_cmd(cfg)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    fatal = ""
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip()
            if not line:
                continue
            f = _consume(rec, step, line)
            if f:
                fatal = f
                try:
                    proc.terminate()
                except Exception:
                    pass
                break
    finally:
        rc = proc.wait()
    if fatal:
        return False, fatal
    if rc != 0:
        return False, f"run.py flash_ghs exit={rc}"
    return True, ""


def _consume(rec, step, line: str):
    """Log a flash line; return a fatal substring if the line is fatal, else ''."""
    if any(b in line for b in core.BENIGN_SUBSTRINGS):
        return ""
    for fatal in core.FATAL_SUBSTRINGS:
        if fatal in line:
            step.event("error", line)
            return fatal
    if any(p.lower() in line.lower() for p in _PROGRESS):
        step.event("note", line)
    return ""


def step_flash(cfg, rec, *, simulate: bool = False) -> bool:
    """Flash all binaries. Returns True on success. Records into ``rec``."""
    step = rec.begin_step("flash")
    step.event("cmd", _bash_flash_cmd(cfg) if not simulate else "simulate flash_ghs")

    ok, fatal = _run_once(cfg, rec, step, simulate=simulate)
    if not ok and core.is_transient(fatal):
        # Exactly one retry for a documented transient probe glitch — then give up (no blind loop).
        rec.add_error(output.ErrorRecord(
            step="flash", message=fatal, handled=True,
            action="transient probe glitch — killed holders, single retry"))
        step.event("note", "transient glitch -> cleanup + single retry")
        core.kill_stale("multi.exe", "mpserv.exe", settle_ceiling_s=cfg.ceiling_connect_s)
        ok, fatal = _run_once(cfg, rec, step, simulate=simulate)

    if not ok:
        rec.add_error(output.ErrorRecord(
            step="flash", message=fatal or "flash failed", handled=False,
            action="abort — check GHS probe USB + ECU power (KL15)"))
        rec.end_step(output.FAIL, detail="flash failed", error=fatal)
        return False

    rec.end_step(output.PASS, detail="HSM->sflash->FBL->App->2nd core written")
    return True


def main(argv) -> int:
    report = _load("report")
    config = _load("config")
    import argparse
    ap = argparse.ArgumentParser(description="Ghs-py flash step (run.py flash_ghs)")
    ap.add_argument("--bench", default="A")
    ap.add_argument("--variant", default=None)
    ap.add_argument("--simulate", action="store_true")
    args = ap.parse_args(argv)

    cfg = config.load_config(bench=args.bench, variant=args.variant)
    rec = report.build_recorder(cfg, task="flash", simulate=args.simulate)
    ok = step_flash(cfg, rec, simulate=args.simulate)
    report.emit(rec, base_name="")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
