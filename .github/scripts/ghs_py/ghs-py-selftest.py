"""ghs-py-selftest — Validation harness (no hardware) for the ghs-py flash/debug suite.

Runs every composable step and the full pipeline in ``--simulate`` mode, then asserts that:

* each step reports PASS,
* values are captured between the RDBEG/RDEND markers (read/write/breakpoint),
* the JSON is well-formed and contains the mandatory sections,
* the canonical HTML report is produced with all fixed section headings,
* the old-vs-new benchmark is present with a total speed-up.

This is how the suite is proven "working, not scaffolding" on a machine without the ECU/probe.
Exit code 0 = all checks passed.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
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
verify = _load("verify")
debug_launch = _load("debug-launch")
html_report = _load("html-report")

_checks = []


def check(name: str, cond: bool, extra: str = "") -> None:
    _checks.append((name, cond, extra))
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {extra}" if extra and not cond else ""))


def run() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tvpy_selftest_"))
    # Point the simulated build dir at a temp location so we never touch a real project tree.
    cfg = config.load_config(bench="A", project_root=str(tmp))
    print(f"[selftest] simulated project root: {tmp}")
    print(f"[selftest] simulated build dir   : {cfg.build_dir()}")

    # --- individual steps -----------------------------------------------------------------------
    print("\n[selftest] connect step")
    rec = report.build_recorder(cfg, task="selftest:connect", simulate=True)
    check("connect PASS", connect.step_connect(cfg, rec, simulate=True))

    print("[selftest] flash step")
    rec = report.build_recorder(cfg, task="selftest:flash", simulate=True)
    check("flash PASS", flash.step_flash(cfg, rec, simulate=True))

    print("[selftest] verify step")
    rec = report.build_recorder(cfg, task="selftest:verify", simulate=True)
    runner = core.MultiRunner(cfg, simulate=True)
    check("verify PASS", verify.step_verify(cfg, rec, runner, simulate=True))

    print("[selftest] debug read step")
    rec = report.build_recorder(cfg, task="selftest:read", simulate=True)
    runner = core.MultiRunner(cfg, simulate=True)
    ok = debug_launch.step_debug(cfg, rec, runner, op="read",
                                 variables=["AmmSM__enCurrentMode", "g_WdgM_SE_Status"],
                                 simulate=True)
    check("read PASS", ok)
    check("read captured 2 values", len(rec.inspections) == 2,
          f"got {len(rec.inspections)}")
    check("read value parsed (not '?')",
          all(i.value not in ("?", "") for i in rec.inspections),
          str([i.value for i in rec.inspections]))

    print("[selftest] debug write step")
    rec = report.build_recorder(cfg, task="selftest:write", simulate=True)
    runner = core.MultiRunner(cfg, simulate=True)
    ok = debug_launch.step_debug(cfg, rec, runner, op="write",
                                 variable="g_WdgM_SE_Status", value="1", simulate=True)
    check("write PASS", ok)
    check("write before+after captured", len(rec.inspections) == 2)

    print("[selftest] debug breakpoint step")
    rec = report.build_recorder(cfg, task="selftest:bp", simulate=True)
    runner = core.MultiRunner(cfg, simulate=True)
    ok = debug_launch.step_debug(cfg, rec, runner, op="breakpoint",
                                 function="Mcu_PerformReset", regs=["$r0", "$r1", "$lr"],
                                 simulate=True)
    check("breakpoint PASS", ok)
    check("breakpoint hit recorded", any(b.hit for b in rec.breakpoints))
    check("breakpoint captured 3 regs",
          any(len(b.values) == 3 for b in rec.breakpoints))

    # --- full pipeline via orchestrator ---------------------------------------------------------
    print("\n[selftest] full pipeline (connect -> flash -> read) + artifacts")
    run_mod = _load("run")
    args = run_mod.build_parser().parse_args([
        "--flash", "--op", "read",
        "--variables", "AmmSM__enCurrentMode", "g_WdgM_SE_Status",
        "--simulate", "--out-dir", str(tmp / "out"), "--name", "selftest_pipeline",
        "--project-root", str(tmp), "--quiet",
    ])
    rc = run_mod.run_pipeline(args)
    check("pipeline exit 0", rc == 0)

    json_path = tmp / "out" / "selftest_pipeline.json"
    html_path = tmp / "out" / "selftest_pipeline.html"
    check("JSON artifact exists", json_path.exists())
    check("HTML artifact exists", html_path.exists())

    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        check("JSON overall PASS", data["summary"]["overall"] == "PASS",
              data["summary"]["overall"])
        for sect in ("metadata", "summary", "steps", "breakpoints", "inspections",
                     "errors", "benchmark", "config"):
            check(f"JSON has '{sect}'", sect in data)
        check("benchmark has totals+speedup",
              data["benchmark"].get("totals", {}).get("speedup", 0) > 0)
        check("pipeline ran flash step",
              any(s["name"] == "flash" for s in data["steps"]))

    if html_path.exists():
        htmltext = html_path.read_text(encoding="utf-8")
        for heading in ("1. Session Metadata", "2. Summary / Overview",
                        "3. Step-by-Step Timeline", "4. Breakpoints",
                        "5. Inspected Register", "6. Errors &amp; Handling",
                        "7. Benchmark", "8. Environment"):
            check(f"HTML section '{heading}'", heading in htmltext)
        check("HTML canonical template tag",
              f"canonical template v{html_report.TEMPLATE_VERSION}" in htmltext)

    # --- fatal fast-fail path -------------------------------------------------------------------
    print("\n[selftest] fatal marker fast-fail")
    rec = report.build_recorder(cfg, task="selftest:fatal", simulate=True)
    runner = core.MultiRunner(cfg, simulate=True)
    step = rec.begin_step("verify")
    res = runner.run(step, "x\n", wait_tags=["NEVER"], ceiling_s=5.0,
                     rc_name="tvpy_fatal.rc", log_name="tvpy_fatal_out.txt",
                     sim_timeline=[(0.05, "No match")])
    rec.end_step("FAIL" if not res.ok else "PASS")
    check("fatal marker -> not ok", not res.ok)
    check("fatal line captured", res.fatal_line == "No match", res.fatal_line)

    # --- summary --------------------------------------------------------------------------------
    passed = sum(1 for _, c, _ in _checks if c)
    total = len(_checks)
    print(f"\n[selftest] {passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(run())
