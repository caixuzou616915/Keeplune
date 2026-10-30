#!/usr/bin/env python3
"""dtc_tool - Debug Test Case (DTC) toolchain for on-target Traveo II debugging.

One debugger-neutral test-case spec (``*.dtc.json``) -> runnable scripts for BOTH probes:

  * GHS Multi playback ``.rc``   (run with ``run_debug_rc.ps1`` / Profile C ``multi -p``)
  * Lauterbach TRACE32 ``.cmm``  (run on the app core with ``t32py_pystart.py --do-app``)

Every generated script writes the same machine-readable marker lines
(``DTC|<tc>|<step>|<KIND>|...``) into its log, so ONE evaluator scores the run no matter
which probe executed it, and ONE report (test-report skill structure) comes out of it.

Subcommands (stdlib only, Python 3.8+):

  validate      SPEC                          schema + state-machine checks
  deploy-check  SPEC --build-dir DIR [--repo] offline proof the change is in the build
  compile       SPEC --out DIR [--target ghs|t32|all] [--bench A|B|C]
  evaluate      SPEC --logs LOG [LOG ...] --target ghs|t32 [--out results.json]
  report        SPEC [--results results.json] --out-md X.md [--out-html X.html]

See ../SKILL.md for the full format description.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DTC_VERSION = "1.0"

ICON_PASS = "\u2705"
ICON_PARTIAL = "\u26a0\ufe0f"
ICON_FAIL = "\u274c"
ICON_INFO = "\u2139\ufe0f"
ICON_PENDING = "\u23f3"

ACTIONS = ("run", "halt", "wait", "wait_halt", "break", "read", "write", "stimulus", "note")
BREAK_MODES = ("halt", "log", "force")
VALUE_OPS = ("==", "!=", "<", "<=", ">", ">=", "in", "range", "bits_set", "bits_clear",
             "changed", "unchanged")
BREAK_OPS = ("hit", "not_hit", "count")
TC_TYPES = ("deployment", "functional", "regression", "negative", "boundary", "robustness")

# GHS bench presets. {variant} is substituted at compile time. Paths in the preamble are
# relative to build/<variant>.<type>/ because MULTI is always started from there.
GHS_BENCHES: Dict[str, Dict[str, Any]] = {
    "A": {  # S3P meta-repo, application-core bench (run_debug_rc.ps1 default)
        "variant": "tviib_e4m_aravalli_s3p",
        "core_prefix": "m4",
        "preamble": [
            "wait -time 3000",
            "python -b -f ../../app/variants/{variant}/debug/ghs/tvii_debug_4mbe.py VERIFY",
            "wait -time 2000",
            "alias m4 route cm4",
        ],
        "read_style": "mprintf",
        "write_style": "print",
    },
    "B": {  # VS20 / tviic_6m_endprod triple-core bench
        "variant": "tviic_6m_endprod",
        "core_prefix": "m7_0",
        "preamble": [
            "wait -time 3000",
            "python -b -f ../../app/variants/{variant}/debug/tvii_debug_6mb.py VERIFY",
            "wait -time 2000",
        ],
        "read_style": "mprintf",
        "write_style": "assign",
    },
    "C": {  # Aravalli standalone ECU (Profile C) - mprintf with variable args hangs there
        "variant": "tviib_e4m_aravalli_s3p_db",
        "core_prefix": "m4",
        "preamble": [
            "wait -time 3000",
            "python -b -f ../../app/variants/{variant}/debug/ghs/tvii_debug_4mbe.py VERIFY",
            "wait -time 2000",
            "alias m4 route cm4",
        ],
        "read_style": "print",
        "write_style": "assign",
    },
}
GHS_VERIFY_BUDGET_S = 100  # VERIFY (skip-verify ~40 s, full ~95 s) + launch overhead


class SpecError(Exception):
    pass


# --------------------------------------------------------------------------------------
#  Spec loading / helpers
# --------------------------------------------------------------------------------------
def load_spec(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise SpecError(f"spec not found: {p}")
    try:
        spec = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise SpecError(f"{p}: invalid JSON: {e}") from e
    spec["_path"] = str(p.resolve())
    return spec


def symbols_of(spec: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return spec.get("symbols") or {}


def parse_number(text: str) -> Optional[int]:
    t = text.strip().rstrip(".")  # TRACE32 decimal output ends with '.'
    if re.fullmatch(r"[-+]?0[xX][0-9a-fA-F]+", t):
        return int(t, 16)
    if re.fullmatch(r"[-+]?\d+", t):
        return int(t, 10)
    return None


def enum_value(spec: Dict[str, Any], symbol: str, value: Any) -> Any:
    """Map an enum NAME to its number using symbols.<sym>.enum; numbers pass through."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        enum = (symbols_of(spec).get(symbol) or {}).get("enum") or {}
        if value in enum:
            return enum[value]
        parsed = parse_number(value)
        if parsed is not None:
            return parsed
    return value


def enum_name(spec: Dict[str, Any], symbol: str, value: Any) -> Optional[str]:
    enum = (symbols_of(spec).get(symbol) or {}).get("enum") or {}
    for name, num in enum.items():
        if num == value:
            return name
    return None


def sym_expr(spec: Dict[str, Any], symbol: str, target: str) -> str:
    """Debugger expression for a symbol. File-local statics need file/module qualification."""
    info = symbols_of(spec).get(symbol) or {}
    if info.get(target):
        return str(info[target])  # explicit per-debugger override wins
    src = info.get("file")
    if not src:
        return symbol
    if target == "ghs":
        return f'"{src}"#{symbol}'
    return f"\\{Path(src).stem}\\{symbol}"


def expected_of(spec: Dict[str, Any], step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if step.get("expect"):
        return step["expect"]
    if step.get("action") == "write" and step.get("readback", True):
        return {"op": "==", "value": step.get("value")}
    return None


def step_label(step: Dict[str, Any]) -> str:
    """Auto 'What to do' text when the author did not write one."""
    a = step.get("action")
    if a == "run":
        return "Resume the application core"
    if a == "halt":
        return "Halt the application core"
    if a == "wait":
        return f"Let the system run for {step.get('ms')} ms"
    if a == "wait_halt":
        return f"Wait up to {step.get('timeout_ms')} ms for the core to halt"
    if a == "break":
        mode = step.get("mode", "halt")
        if mode == "force":
            sets = ", ".join(f"{k}={v}" for k, v in (step.get("set") or {}).items())
            return f"Force {sets} every time `{step.get('function')}` runs"
        if mode == "log":
            return f"Count calls of `{step.get('function')}` (log and continue)"
        return f"Stop at `{step.get('function')}`"
    if a == "read":
        return f"Read `{step.get('symbol')}`"
    if a == "write":
        return f"Write `{step.get('symbol')}` = {step.get('value')}"
    if a == "stimulus":
        return f"Apply stimulus via {step.get('via', 'manual')}: {step.get('detail', '')}"
    if a == "note":
        return step.get("text", "Note")
    return str(a)


def expectation_text(spec: Dict[str, Any], step: Dict[str, Any]) -> str:
    exp = expected_of(spec, step)
    if not exp:
        return "None"
    op = exp.get("op")
    sym = step.get("symbol") or step.get("function") or ""
    if op == "hit":
        return f"`{sym}` is reached at least once"
    if op == "not_hit":
        return f"`{sym}` is NOT reached"
    if op == "count":
        lo, hi = exp.get("min"), exp.get("max")
        return f"`{sym}` hit count in [{lo if lo is not None else 0}, {hi if hi is not None else 'inf'}]"
    if op == "in":
        return f"`{sym}` in {exp.get('values')}"
    if op == "range":
        return f"`{sym}` in [{exp.get('min')}, {exp.get('max')}]"
    if op in ("bits_set", "bits_clear"):
        return f"`{sym}` {op.replace('_', ' ')} mask {exp.get('mask')}"
    if op in ("changed", "unchanged"):
        return f"`{sym}` {op} vs. previous read"
    return f"`{sym}` {op} {exp.get('value')}"


# --------------------------------------------------------------------------------------
#  validate
# --------------------------------------------------------------------------------------
def validate(spec: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if str(spec.get("dtc_version", "")) != DTC_VERSION:
        errors.append(f'dtc_version must be "{DTC_VERSION}"')
    suite = spec.get("suite") or {}
    for key in ("id", "title", "change_ref"):
        if not suite.get(key):
            errors.append(f"suite.{key} is required")
    if not suite.get("changed_files"):
        warnings.append("suite.changed_files is empty - deploy-check cannot prove the change is built")
    bench = (spec.get("bench") or {}).get("preset", "A")
    if bench not in GHS_BENCHES:
        errors.append(f"bench.preset must be one of {sorted(GHS_BENCHES)}")

    tcs = spec.get("test_cases") or []
    if not tcs:
        errors.append("test_cases is empty")
    seen = set()
    for i, tc in enumerate(tcs):
        tid = tc.get("id")
        if not tid or not re.fullmatch(r"[A-Za-z0-9_\-]+", str(tid)):
            errors.append(f"test_cases[{i}].id missing or not [A-Za-z0-9_-]")
        elif tid in seen:
            errors.append(f"test_cases[{i}].id duplicate: {tid}")
        seen.add(tid)
        where = f"{tid or f'test_cases[{i}]'}"
        if not tc.get("title"):
            errors.append(f"{where}: title is required")
        if not tc.get("purpose"):
            warnings.append(f"{where}: purpose is empty")
        if not tc.get("trace"):
            warnings.append(f"{where}: trace is empty (link requirement / changed function)")
        if tc.get("type") and tc["type"] not in TC_TYPES:
            errors.append(f"{where}: type must be one of {TC_TYPES}")
        start = tc.get("start", "runtime")
        if start not in ("runtime", "boot"):
            errors.append(f"{where}: start must be 'runtime' or 'boot'")
        if start == "boot":
            warnings.append(f"{where}: start=boot -> TRACE32 must be launched with "
                            "t32py_pystart.py --no-start --do-app (cores still halted after flash)")
        steps = tc.get("steps") or []
        if not steps:
            errors.append(f"{where}: steps is empty")
        has_expect = False
        state = "halted"  # every test case starts with the app core halted (see SKILL.md)
        breaks_halting = False
        for j, st in enumerate(steps, 1):
            sw = f"{where} step {j}"
            a = st.get("action")
            if a not in ACTIONS:
                errors.append(f"{sw}: action must be one of {ACTIONS}")
                continue
            if expected_of(spec, st):
                has_expect = True
            if a == "run":
                if state == "running":
                    errors.append(f"{sw}: run while already running")
                state = "running"
            elif a == "halt":
                if state == "halted":
                    errors.append(f"{sw}: halt while already halted (GHS hangs on this)")
                state = "halted"
            elif a == "wait":
                if not isinstance(st.get("ms"), int) or st["ms"] <= 0:
                    errors.append(f"{sw}: wait needs integer ms > 0")
                if state == "halted":
                    warnings.append(f"{sw}: wait while halted - did you forget 'run'?")
            elif a == "wait_halt":
                if not isinstance(st.get("timeout_ms"), int) or st["timeout_ms"] <= 0:
                    errors.append(f"{sw}: wait_halt needs integer timeout_ms > 0")
                if state != "running":
                    errors.append(f"{sw}: wait_halt needs a running core")
                if not breaks_halting:
                    warnings.append(f"{sw}: wait_halt without a prior break mode=halt")
                state = "halted"
            elif a == "break":
                if not st.get("function"):
                    errors.append(f"{sw}: break needs function")
                mode = st.get("mode", "halt")
                if mode not in BREAK_MODES:
                    errors.append(f"{sw}: break mode must be one of {BREAK_MODES}")
                if mode == "force" and not st.get("set"):
                    errors.append(f"{sw}: break mode=force needs set {{symbol: value}}")
                if mode == "halt":
                    breaks_halting = True
                if state != "halted":
                    errors.append(f"{sw}: arm breakpoints while halted (GHS: 'hardbrk: not allowed')")
                exp = st.get("expect")
                if exp and exp.get("op") not in BREAK_OPS:
                    errors.append(f"{sw}: break expect.op must be one of {BREAK_OPS}")
            elif a in ("read", "write"):
                if not st.get("symbol"):
                    errors.append(f"{sw}: {a} needs symbol")
                if a == "write" and "value" not in st:
                    errors.append(f"{sw}: write needs value")
                if state != "halted" and not st.get("live"):
                    errors.append(f"{sw}: {a} on a running core - add 'halt' first or set live: true")
                exp = st.get("expect")
                if exp:
                    op = exp.get("op")
                    if op not in VALUE_OPS:
                        errors.append(f"{sw}: expect.op must be one of {VALUE_OPS}")
                    elif op == "in" and not isinstance(exp.get("values"), list):
                        errors.append(f"{sw}: op 'in' needs values: [...]")
                    elif op == "range" and ("min" not in exp or "max" not in exp):
                        errors.append(f"{sw}: op 'range' needs min and max")
                    elif op in ("bits_set", "bits_clear") and "mask" not in exp:
                        errors.append(f"{sw}: op '{op}' needs mask")
                    elif op in ("==", "!=", "<", "<=", ">", ">=") and "value" not in exp:
                        errors.append(f"{sw}: op '{op}' needs value")
            elif a == "stimulus":
                if not st.get("detail"):
                    errors.append(f"{sw}: stimulus needs detail")
                if state != "running":
                    warnings.append(f"{sw}: stimulus while halted - ECU will not react until 'run'")
        if steps and not has_expect:
            warnings.append(f"{where}: no step has an expectation - result will be INFO only")
    return errors, warnings


# --------------------------------------------------------------------------------------
#  compile - GHS .rc and TRACE32 .cmm renderers (shared marker grammar)
# --------------------------------------------------------------------------------------
def ghs_bench(spec: Dict[str, Any], override: Optional[str]) -> Dict[str, Any]:
    b = dict(spec.get("bench") or {})
    preset = override or b.get("preset", "A")
    base = dict(GHS_BENCHES.get(preset, GHS_BENCHES["A"]))
    for key in ("core_prefix", "preamble", "read_style", "write_style"):
        if b.get(f"ghs_{key}") is not None:
            base[key] = b[f"ghs_{key}"]
    base["variant"] = (spec.get("suite") or {}).get("variant") or base["variant"]
    base["preset"] = preset
    return base


def ghs_step(spec, tc_id, n, st, bench) -> List[str]:
    p = bench["core_prefix"]
    a = st["action"]
    mk = f"DTC|{tc_id}|{n}"
    if a == "note":
        return [f"; NOTE: {st.get('text', '')}"]
    out = [f'{p} mprintf("{mk}|STEP|{a}\\n")']
    if a == "run":
        out.append("target gc")
    elif a == "halt":
        out += [f"{p} halt", f"wait -stop -time {int(st.get('timeout_ms', 5000))}"]
    elif a == "wait":
        out.append(f"wait -time {int(st['ms'])}")
    elif a == "wait_halt":
        out += [f"wait -stop -time {int(st['timeout_ms'])}", f'{p} mprintf("{mk}|WAIT_HALT|\\n")']
    elif a == "break":
        fn = st["function"]
        mode = st.get("mode", "halt")
        if mode == "halt":
            out.append(f'{p} hardbrk {fn} {{ mprintf("{mk}|HIT\\n") }}')
        elif mode == "log":
            out.append(f'{p} hardbrk rolling {fn} {{ mprintf("{mk}|HIT\\n") }}')
        else:
            assigns = "; ".join(
                f"{sym_expr(spec, s, 'ghs')} = {enum_value(spec, s, v)}"
                for s, v in st["set"].items())
            out.append(f'{p} hardbrk rolling {fn} {{ {assigns}; mprintf("{mk}|HIT\\n") }}')
    elif a in ("read", "write"):
        sym = st["symbol"]
        e = sym_expr(spec, sym, "ghs")
        if a == "write":
            val = enum_value(spec, sym, st["value"])
            style = bench["write_style"]
            if style == "set":
                out.append(f"{p} set {e} = {val}")
            elif style == "print":
                out.append(f"{p} print ({e} = {val})")
            else:
                out.append(f"{p} {e} = {val}")
        kind = "READ" if a == "read" else "WRITE"
        if bench["read_style"] == "print":
            out += [f'{p} mprintf("{mk}|{kind}|{sym}|\\n")', f"{p} print {e}"]
        else:
            out.append(f'{p} mprintf("{mk}|{kind}|{sym}|%d\\n", {e})')
    elif a == "stimulus":
        out += [f'{p} mprintf("{mk}|STIMULUS|{st.get("via", "manual")}\\n")',
                f"wait -time {int(st.get('window_ms', 5000))}"]
    return out


def t32_step(spec, tc_id, n, st) -> List[str]:
    a = st["action"]
    mk = f"DTC|{tc_id}|{n}"
    if a == "note":
        return [f"; NOTE: {st.get('text', '')}"]
    out = [f'PRINT "{mk}|STEP|{a}"']
    if a == "run":
        out.append("Go")
    elif a == "halt":
        out += ["Break", f"WAIT !STATE.RUN() {int(st.get('timeout_ms', 5000))}.ms"]
    elif a == "wait":
        out.append(f"WAIT {int(st['ms'])}.ms")
    elif a == "wait_halt":
        out += [f"WAIT !STATE.RUN() {int(st['timeout_ms'])}.ms",
                f'PRINT "{mk}|WAIT_HALT|",STATE.RUN()',
                "IF STATE.RUN()", "(", "  Break", "  WAIT !STATE.RUN() 2000.ms", ")"]
    elif a == "break":
        fn = st["function"]
        mode = st.get("mode", "halt")
        hit = f'/CMD "PRINT ""{mk}|HIT"""'
        if mode == "halt":
            out.append(f"Break.Set {fn} {hit}")
        elif mode == "log":
            out.append(f"Break.Set {fn} {hit} /RESUME")
        else:
            cmds = " ".join(
                f'/CMD "Var.Set {sym_expr(spec, s, "t32")}={enum_value(spec, s, v)}"'
                for s, v in st["set"].items())
            out.append(f"Break.Set {fn} {cmds} {hit} /RESUME")
    elif a in ("read", "write"):
        sym = st["symbol"]
        e = sym_expr(spec, sym, "t32")
        if a == "write":
            out.append(f"Var.Set {e}={enum_value(spec, sym, st['value'])}")
        kind = "READ" if a == "read" else "WRITE"
        out.append(f'PRINT "{mk}|{kind}|{sym}|",Var.VALUE({e})')
    elif a == "stimulus":
        out += [f'PRINT "{mk}|STIMULUS|{st.get("via", "manual")}"',
                f"WAIT {int(st.get('window_ms', 5000))}.ms"]
    return out


def tc_duration_s(tc: Dict[str, Any]) -> int:
    total_ms = int(tc.get("settle_ms", 10000)) if tc.get("start", "runtime") == "runtime" else 0
    for st in tc.get("steps") or []:
        if st.get("action") == "halt":
            total_ms += int(st.get("timeout_ms", 5000))
        else:
            total_ms += int(st.get("ms") or st.get("timeout_ms") or st.get("window_ms") or 0)
    return total_ms // 1000


def render_ghs(spec, tc, bench) -> str:
    tid = tc["id"]
    p = bench["core_prefix"]
    lines = [
        f"; DTC {tid} - {tc.get('title', '')}",
        f"; suite {spec['suite']['id']} | change {spec['suite'].get('change_ref', '')}",
        f"; GHS bench preset {bench['preset']} ({bench['variant']}), core prefix {p}",
        "; GENERATED by dtc_tool.py - edit the .dtc.json, not this file.",
        "; Rules baked in: no 'halt' on a halted core, 'wait -stop -time' (never -breakortime),",
        "; rolling breakpoints without '; go'.",
    ]
    lines += [ln.format(variant=bench["variant"]) for ln in bench["preamble"]]
    lines.append(f'{p} mprintf("DTC|{tid}|BEGIN|ghs\\n")')
    state = "halted"  # after VERIFY the cores are halted
    if tc.get("start", "runtime") == "runtime":
        settle = int(tc.get("settle_ms", 10000))
        lines += ["target gc", f"wait -time {settle}", f"{p} halt", "wait -stop -time 5000"]
    for n, st in enumerate(tc["steps"], 1):
        lines += ghs_step(spec, tid, n, st, bench)
        if st["action"] == "run":
            state = "running"
        elif st["action"] in ("halt", "wait_halt"):
            state = "halted"
    if state == "halted":
        lines += ["target gc", "wait -time 500"]  # leave the ECU running
    lines += [
        f'{p} mprintf("DTC|{tid}|END\\n")',
        'mprintf(">>>TVPY:DTC_DONE<<<\\n")',
        'mprintf("RESULT END\\n")',
        "wait -time 1000",
        "quit",
    ]
    return "\n".join(lines) + "\n"


def render_t32(spec, tc, log_path: Path) -> str:
    tid = tc["id"]
    lines = [
        f"; DTC {tid} - {tc.get('title', '')}",
        f"; suite {spec['suite']['id']} | change {spec['suite'].get('change_ref', '')}",
        "; GENERATED by dtc_tool.py - edit the .dtc.json, not this file.",
        "; Runs on the APPLICATION core instance (AMP slave / CM4 PowerView):",
        ";   python t32py_pystart.py --attach --do-app <this.cmm>",
        f'AREA.OPEN "{log_path.as_posix()}" /Create',
        "ON ERROR GOTO dtc_abort",
        f'PRINT "DTC|{tid}|BEGIN|t32"',
    ]
    if tc.get("start", "runtime") == "runtime":
        settle = int(tc.get("settle_ms", 10000))
        lines += ["IF !STATE.RUN()", "(", "  Go", ")", f"WAIT {settle}.ms",
                  "Break", "WAIT !STATE.RUN() 5000.ms"]
    set_breaks: List[str] = []
    for n, st in enumerate(tc["steps"], 1):
        lines += t32_step(spec, tid, n, st)
        if st["action"] == "break":
            set_breaks.append(st["function"])
    for fn in dict.fromkeys(set_breaks):
        lines.append(f"Break.Delete {fn}")
    lines += [
        "IF !STATE.RUN()", "(", "  Go", ")",  # leave the ECU running
        f'PRINT "DTC|{tid}|END"',
        "AREA.CLOSE",
        "ENDDO",
        "dtc_abort:",
        f'PRINT "DTC|{tid}|ABORT"',
        "AREA.CLOSE",
        "ENDDO",
    ]
    return "\n".join(lines) + "\n"


def compile_spec(spec, out_dir: Path, target: str, bench_override: Optional[str]) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    bench = ghs_bench(spec, bench_override)
    manifest: Dict[str, Any] = {
        "dtc_version": DTC_VERSION,
        "suite": spec["suite"]["id"],
        "spec": spec["_path"],
        "generated": datetime.now().isoformat(timespec="seconds"),
        "ghs_bench": bench["preset"],
        "test_cases": [],
    }
    for tc in spec["test_cases"]:
        tid = tc["id"]
        entry: Dict[str, Any] = {"id": tid, "title": tc.get("title", ""), "start": tc.get("start", "runtime")}
        dur = tc_duration_s(tc)
        if target in ("ghs", "all"):
            rc = out_dir / "ghs" / f"{tid}.rc"
            rc.parent.mkdir(parents=True, exist_ok=True)
            rc.write_text(render_ghs(spec, tc, bench), encoding="ascii", errors="replace")
            entry["ghs"] = {
                "rc": str(rc.resolve()),
                "log": f"{tid}_out.txt (in build/<variant>.<type>/, written by -R)",
                "success_marker": "RESULT END",
                "timeout_s": GHS_VERIFY_BUDGET_S + dur + 30,
            }
        if target in ("t32", "all"):
            log = (out_dir / "t32" / f"{tid}_out.txt").resolve()
            cmm = out_dir / "t32" / f"{tid}.cmm"
            cmm.parent.mkdir(parents=True, exist_ok=True)
            cmm.write_text(render_t32(spec, tc, log), encoding="ascii", errors="replace")
            entry["t32"] = {
                "cmm": str(cmm.resolve()),
                "log": str(log),
                "end_markers": [f"DTC|{tid}|END", f"DTC|{tid}|ABORT"],
                "timeout_s": dur + 60,
                "launch": "--no-start" if tc.get("start") == "boot" else "--attach",
            }
        manifest["test_cases"].append(entry)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------------------
#  evaluate
# --------------------------------------------------------------------------------------
MARKER_RE = re.compile(r"DTC\|([A-Za-z0-9_\-]+)\|(.*)$")
# Command echoes (a playback log may echo the script line itself) must never be scored.
ECHO_RE = re.compile(r'mprintf\(|hardbrk|Break\.Set|PRINT\s+"|(^|\s)print\s')


def extract_value(text: str) -> Any:
    t = text.strip().strip('"')
    if "=" in t:  # "sym = 40" style
        t = t.rsplit("=", 1)[1].strip()
    num = parse_number(t)
    if num is not None:
        return num
    m = re.search(r"\((-?\d+)\)", t)  # "ProjectionOn (40)"
    if m:
        return int(m.group(1))
    tok = t.split()[0] if t.split() else t
    num = parse_number(tok)
    return num if num is not None else tok


def parse_logs(paths: List[str]) -> Dict[str, Dict[str, Any]]:
    """-> {tc: {'begin', 'end', 'abort', 'target', 'steps': {n: {...}}}}"""
    runs: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        pending_read: Optional[Tuple[str, int, str, str]] = None  # print-style: value on next line
        for raw in lines:
            line = raw.strip()
            if not line or ECHO_RE.search(line):
                continue
            m = MARKER_RE.search(line.strip('"'))
            if not m:
                if pending_read:
                    tc, n, kind, sym = pending_read
                    runs[tc]["steps"].setdefault(n, {}).setdefault("values", []).append(
                        (kind, sym, extract_value(line)))
                    pending_read = None
                continue
            pending_read = None
            tc, rest = m.group(1), m.group(2)
            run = runs.setdefault(tc, {"begin": False, "end": False, "abort": False, "steps": {}})
            parts = [x.strip() for x in rest.split("|")]
            head = parts[0]
            if head == "BEGIN":
                run["begin"] = True
                run["target"] = parts[1] if len(parts) > 1 else ""
                continue
            if head == "END":
                run["end"] = True
                continue
            if head == "ABORT":
                run["abort"] = True
                continue
            if not head.isdigit() or len(parts) < 2:
                continue
            n = int(head)
            kind = parts[1]
            st = run["steps"].setdefault(n, {})
            if kind == "STEP":
                st["reached"] = True
            elif kind == "HIT":
                st["hits"] = st.get("hits", 0) + 1
            elif kind == "WAIT_HALT":
                st["wait_halt"] = parts[2] if len(parts) > 2 else ""
            elif kind == "STIMULUS":
                st["stimulus"] = True
            elif kind in ("READ", "WRITE") and len(parts) >= 3:
                sym = parts[2]
                val_txt = "|".join(parts[3:]).strip() if len(parts) > 3 else ""
                if val_txt:
                    st.setdefault("values", []).append((kind, sym, extract_value(val_txt)))
                else:
                    pending_read = (tc, n, kind, sym)
    return runs


def compare(op: str, actual: Any, exp: Dict[str, Any], spec, sym: str, previous: Any) -> bool:
    def ev(v):
        return enum_value(spec, sym, v)
    a = ev(actual)
    if op == "==":
        return a == ev(exp["value"])
    if op == "!=":
        return a != ev(exp["value"])
    if op in ("<", "<=", ">", ">="):
        b = ev(exp["value"])
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return False
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    if op == "in":
        return a in [ev(v) for v in exp["values"]]
    if op == "range":
        return isinstance(a, (int, float)) and ev(exp["min"]) <= a <= ev(exp["max"])
    if op in ("bits_set", "bits_clear"):
        mask = ev(exp["mask"])
        if not isinstance(a, int) or not isinstance(mask, int):
            return False
        return (a & mask) == mask if op == "bits_set" else (a & mask) == 0
    if op == "changed":
        return previous is not None and a != previous
    if op == "unchanged":
        return previous is not None and a == previous
    return False


def show(spec, sym: str, value: Any) -> str:
    name = enum_name(spec, sym, value)
    return f"{value} ({name})" if name else str(value)


def evaluate(spec: Dict[str, Any], runs: Dict[str, Dict[str, Any]], target: str) -> Dict[str, Any]:
    results: Dict[str, Any] = {"suite": spec["suite"]["id"], "target": target,
                               "evaluated": datetime.now().isoformat(timespec="seconds"),
                               "test_cases": []}
    for tc in spec["test_cases"]:
        tid = tc["id"]
        run = runs.get(tid)
        tc_res: Dict[str, Any] = {"id": tid, "steps": []}
        if not run or not run.get("begin"):
            tc_res["status"] = f"{ICON_FAIL} BLOCKED (no log for {tid})"
            tc_res["summary"] = "Test case did not start - no DTC|BEGIN marker in the log(s)."
            tc_res["steps"] = [{"step": n, "result": f"{ICON_FAIL} not executed"}
                               for n in range(1, len(tc["steps"]) + 1)]
            results["test_cases"].append(tc_res)
            continue
        completed = run["end"] and not run["abort"]
        n_pass = n_fail = n_expect = 0
        last_value: Dict[str, Any] = {}
        first_fail = ""
        for n, st in enumerate(tc["steps"], 1):
            data = run["steps"].get(n, {})
            exp = expected_of(spec, st)
            a = st["action"]
            if a == "note":
                tc_res["steps"].append({"step": n, "result": f"{ICON_INFO} note"})
                continue
            if not data.get("reached"):
                res = f"{ICON_FAIL} not reached" + ("" if completed else " (run aborted)")
                if exp:
                    n_expect += 1
                    n_fail += 1
                    first_fail = first_fail or f"step {n} not reached"
                tc_res["steps"].append({"step": n, "result": res})
                continue
            if a in ("read", "write"):
                sym = st["symbol"]
                vals = [v for _k, s, v in data.get("values", []) if s == sym]
                if not vals:
                    res, ok = f"{ICON_FAIL} no value logged", False
                else:
                    actual = vals[-1]
                    if exp:
                        ok = compare(exp["op"], actual, exp, spec, sym, last_value.get(sym))
                        res = f"{ICON_PASS if ok else ICON_FAIL} {sym} = {show(spec, sym, actual)}"
                    else:
                        ok = True
                        res = f"{ICON_INFO} {sym} = {show(spec, sym, actual)}"
                    last_value[sym] = enum_value(spec, sym, actual)
                if exp:
                    n_expect += 1
                    n_pass += int(ok)
                    n_fail += int(not ok)
                    if not ok:
                        first_fail = first_fail or f"step {n}: {res[2:].strip()}"
            elif a == "break":
                hits = data.get("hits", 0)
                if exp:
                    op = exp["op"]
                    if op == "hit":
                        ok = hits >= 1
                    elif op == "not_hit":
                        ok = hits == 0
                    else:
                        lo = exp.get("min", 0)
                        hi = exp.get("max")
                        ok = hits >= lo and (hi is None or hits <= hi)
                    n_expect += 1
                    n_pass += int(ok)
                    n_fail += int(not ok)
                    res = f"{ICON_PASS if ok else ICON_FAIL} {st['function']} hit {hits}x"
                    if not ok:
                        first_fail = first_fail or f"step {n}: {res[2:].strip()}"
                else:
                    res = f"{ICON_INFO} armed; hit {hits}x"
            elif a == "wait_halt":
                res = f"{ICON_INFO} wait done"
                if str(data.get("wait_halt", "")).upper().startswith("TRUE"):  # T32: still running
                    res = f"{ICON_PARTIAL} core did not halt within timeout (forced halt)"
            elif a == "stimulus":
                res = f"{ICON_INFO} stimulus window opened ({st.get('via', 'manual')})"
            else:
                res = f"{ICON_INFO} done"
            tc_res["steps"].append({"step": n, "result": res})

        if not completed:
            status = f"{ICON_FAIL} BLOCKED (run {'aborted' if run['abort'] else 'did not finish'})"
            summary = f"Run stopped before DTC|END. {first_fail or 'Check the debugger log for the error.'}"
        elif n_fail:
            status = f"{ICON_FAIL} FAIL ({n_fail}/{n_expect} checks failed)"
            summary = f"First failure: {first_fail}."
        elif n_expect:
            status = f"{ICON_PASS} PASS ({n_pass}/{n_expect} checks)"
            summary = "All expectations met on target."
        else:
            status = f"{ICON_INFO} INFO (no expectations)"
            summary = "Executed; values recorded for information only."
        tc_res["status"] = status
        tc_res["summary"] = summary
        results["test_cases"].append(tc_res)
    return results


# --------------------------------------------------------------------------------------
#  report (test-report skill canonical structure)
# --------------------------------------------------------------------------------------
_PURE_MARKER_RE = re.compile(r'^\S*\s*(mprintf\("DTC\|[^"]*"\)|PRINT "DTC\|[^"]*"(,STATE\.RUN\(\))?)$')
_MARKER_PREFIX_RE = re.compile(r"DTC\|[A-Za-z0-9_\-]+\|\d+\|")


def _readable(lines: List[str]) -> str:
    """Human 'How to do exactly' text: drop marker-only/control-flow lines, shorten markers and
    replace '|' (which would break Markdown tables)."""
    keep = [ln for ln in lines
            if not _PURE_MARKER_RE.match(ln.strip())
            and not re.match(r"^\s*(\(|\)|IF\s)|^\s{2}", ln)]
    text = " ; ".join(keep)
    text = _MARKER_PREFIX_RE.sub("", text).replace("|", ":")
    return text or "-"


def how_text(spec, tc, n, st, target: Optional[str], bench) -> str:
    if st["action"] == "note":
        return "-"
    ghs = _readable(ghs_step(spec, tc["id"], n, st, bench)[1:])
    t32 = _readable(t32_step(spec, tc["id"], n, st)[1:])
    if target == "ghs":
        return f"`{ghs}`"
    if target == "t32":
        return f"`{t32}`"
    return f"GHS: `{ghs}` / T32: `{t32}`"


def build_report_spec(spec, results: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    target = (results or {}).get("target")
    bench = ghs_bench(spec, None)
    suite = spec["suite"]
    res_by_tc = {t["id"]: t for t in (results or {}).get("test_cases", [])}
    probe = {"ghs": "GHS Multi", "t32": "Lauterbach TRACE32"}.get(target or "", "GHS Multi / Lauterbach TRACE32")
    files = ", ".join(f"`{f}`" for f in suite.get("changed_files") or []) or "n/a"
    rep: Dict[str, Any] = {
        "module": {
            "name": suite.get("module") or suite["id"],
            "description": f"`{suite['id']}` - {suite.get('title', '')} "
                           f"(change: {suite.get('change_ref', '')}; files: {files})",
            "method": f"On-target ({probe}) - generated from `{Path(spec['_path']).name}` by dtc_tool.py "
                      "(breakpoints, variable read/write, forced values).",
        },
        "test_cases": [],
    }
    for tc in spec["test_cases"]:
        r = res_by_tc.get(tc["id"])
        r_steps = {s["step"]: s for s in (r or {}).get("steps", [])}
        steps = []
        for n, st in enumerate(tc["steps"], 1):
            steps.append({
                "step": n,
                "what": st.get("what") or step_label(st),
                "how": how_text(spec, tc, n, st, target, bench),
                "expectation": expectation_text(spec, st),
                "result": (r_steps.get(n) or {}).get("result") or f"{ICON_PENDING} pending",
            })
        trace = tc.get("trace") or []
        rep["test_cases"].append({
            "id": tc["id"],
            "title": tc.get("title", ""),
            "status": (r or {}).get("status", f"{ICON_PENDING} pending"),
            "description": tc.get("purpose", ""),
            "traceability": ", ".join(trace) if trace else "n/a",
            "scripts": f"`ghs/{tc['id']}.rc` (GHS Multi) / `t32/{tc['id']}.cmm` (TRACE32)",
            "steps": steps,
            "summary": (r or {}).get("summary", "Not yet executed."),
        })
    return rep


def find_test_report_generator() -> Optional[Path]:
    here = Path(__file__).resolve()
    for skills_root in (here.parents[2], Path.home() / ".copilot" / "skills"):
        cand = skills_root / "test-report" / "scripts" / "generate_test_report.py"
        if cand.exists():
            return cand
    return None


def fallback_md(rep: Dict[str, Any]) -> str:
    m = rep["module"]
    out = [f"# {m['name']} Use Case Testing", "", f"**Module**: {m['description']}",
           f"**Method**: {m['method']}", "", "---", "", "## Summary", "",
           "| # | Test Case | Result / Status |", "|---|-----------|------------------|"]
    for tc in rep["test_cases"]:
        out.append(f"| {tc['id']} | {tc['title']} | {tc['status']} |")
    for tc in rep["test_cases"]:
        out += ["", f"### {tc['id']} \u2014 {tc['title']}", "",
                f"**Description / Purpose**: {tc['description']}", "",
                f"**Traceability**: {tc['traceability']}", "", f"**Test Script(s)**: {tc['scripts']}", "",
                "| # | What to do | How to do exactly | Expectation | Result |",
                "|---|-----------|--------------------|--------------|--------|"]
        for s in tc["steps"]:
            out.append(f"| {s['step']} | {s['what']} | {s['how']} | {s['expectation']} | {s['result']} |")
        out += ["", f"> **Summary**: {tc['summary']}"]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------
#  deploy-check (offline: is the changed code really inside the image we test?)
# --------------------------------------------------------------------------------------
def deploy_check(spec, build_dir: Path, repo: Path) -> Tuple[bool, List[Tuple[str, str, str]]]:
    rows: List[Tuple[str, str, str]] = []
    ok = True
    images = [p for pat in ("*.abs", "*.elf") for p in build_dir.rglob(pat) if "CMakeFiles" not in p.parts]
    if not images:
        return False, [("image", ICON_FAIL, f"no .abs/.elf under {build_dir} - build first")]
    image = max(images, key=lambda p: p.stat().st_mtime)
    img_t = image.stat().st_mtime
    rows.append(("image", ICON_INFO, f"{image} ({datetime.fromtimestamp(img_t):%Y-%m-%d %H:%M:%S})"))

    for f in (spec.get("suite") or {}).get("changed_files") or []:
        src = Path(f) if Path(f).is_absolute() else repo / f
        if not src.exists():
            ok = False
            rows.append((f, ICON_FAIL, "changed file not found"))
        elif src.stat().st_mtime > img_t:
            ok = False
            rows.append((f, ICON_FAIL, "source is NEWER than the image - rebuild + reflash before testing"))
        else:
            rows.append((f, ICON_PASS, "image built after the last change"))

    wanted = list((spec.get("deploy_check") or {}).get("symbols") or [])
    if not wanted:
        for tc in spec.get("test_cases") or []:
            for st in tc.get("steps") or []:
                for key in ("function", "symbol"):
                    if st.get(key):
                        wanted.append(st[key])
                wanted += list((st.get("set") or {}).keys())
    wanted = list(dict.fromkeys(wanted))
    maps = [p for p in build_dir.rglob("*.map") if "CMakeFiles" not in p.parts]
    if wanted and not maps:
        rows.append(("symbols", ICON_PARTIAL, "no .map file found - symbol presence not checked"))
    elif wanted:
        found = {s: False for s in wanted}
        pats = {s: re.compile(r"(?<![A-Za-z0-9_])" + re.escape(s) + r"(?![A-Za-z0-9_])") for s in wanted}
        for mp in maps:
            with open(mp, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    for s, rx in pats.items():
                        if not found[s] and rx.search(line):
                            found[s] = True
            if all(found.values()):
                break
        for s, hit in found.items():
            if hit:
                rows.append((s, ICON_PASS, "symbol linked (found in .map)"))
            elif (symbols_of(spec).get(s) or {}).get("file"):
                rows.append((s, ICON_PARTIAL, "file-local static not in .map (normal) - verify on target"))
            else:
                ok = False
                rows.append((s, ICON_FAIL, "NOT in .map - change not built / symbol renamed / inlined"))
    return ok, rows


# --------------------------------------------------------------------------------------
#  CLI
# --------------------------------------------------------------------------------------
def _print_validation(errors: List[str], warnings: List[str]) -> None:
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"validate: {len(errors)} error(s), {len(warnings)} warning(s)")


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help="schema + state-machine checks")
    p.add_argument("spec")

    p = sub.add_parser("deploy-check", help="offline check that the change is in the built image")
    p.add_argument("spec")
    p.add_argument("--build-dir", required=True, help="build/<variant>.<Debug|Release>")
    p.add_argument("--repo", default=".", help="repo root for suite.changed_files (default cwd)")

    p = sub.add_parser("compile", help="emit GHS .rc and/or TRACE32 .cmm per test case")
    p.add_argument("spec")
    p.add_argument("--out", required=True)
    p.add_argument("--target", choices=["ghs", "t32", "all"], default="all")
    p.add_argument("--bench", choices=sorted(GHS_BENCHES), default=None, help="override bench.preset")

    p = sub.add_parser("evaluate", help="score debugger log(s) against the spec")
    p.add_argument("spec")
    p.add_argument("--logs", nargs="+", required=True)
    p.add_argument("--target", choices=["ghs", "t32"], required=True)
    p.add_argument("--out", default=None, help="results JSON (default: print only)")

    p = sub.add_parser("report", help="write the use-case test report (.md [+ .html])")
    p.add_argument("spec")
    p.add_argument("--results", default=None, help="results JSON from evaluate (omit = all pending)")
    p.add_argument("--out-md", required=True)
    p.add_argument("--out-html", default=None)

    args = ap.parse_args(argv)
    try:
        spec = load_spec(args.spec)
    except SpecError as e:
        print(f"ERROR {e}")
        return 2

    errors, warnings = validate(spec)
    if args.cmd == "validate":
        _print_validation(errors, warnings)
        return 1 if errors else 0
    if errors and args.cmd in ("compile", "evaluate", "report"):
        _print_validation(errors, warnings)
        print("Fix the spec first.")
        return 1

    if args.cmd == "deploy-check":
        ok, rows = deploy_check(spec, Path(args.build_dir), Path(args.repo))
        print("| Item | Status | Detail |\n|------|--------|--------|")
        for item, icon, detail in rows:
            print(f"| {item} | {icon} | {detail} |")
        print(f"deploy-check: {'OK' if ok else 'NOT DEPLOYED / UNPROVEN'}")
        return 0 if ok else 1

    if args.cmd == "compile":
        man = compile_spec(spec, Path(args.out), args.target, args.bench)
        for w in warnings:
            print(f"WARN  {w}")
        for tc in man["test_cases"]:
            parts = [tc["id"]]
            if "ghs" in tc:
                parts.append(f"GHS {tc['ghs']['rc']} (timeout {tc['ghs']['timeout_s']}s)")
            if "t32" in tc:
                parts.append(f"T32 {tc['t32']['cmm']} (timeout {tc['t32']['timeout_s']}s, {tc['t32']['launch']})")
            print(" | ".join(parts))
        print(f"compile: {len(man['test_cases'])} test case(s) -> {Path(args.out) / 'manifest.json'}")
        return 0

    if args.cmd == "evaluate":
        missing = [lg for lg in args.logs if not Path(lg).exists()]
        if missing:
            print(f"ERROR log(s) not found: {missing}")
            return 2
        res = evaluate(spec, parse_logs(args.logs), args.target)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        print("| # | Test Case | Result |\n|---|-----------|--------|")
        title = {t["id"]: t.get("title", "") for t in spec["test_cases"]}
        for t in res["test_cases"]:
            print(f"| {t['id']} | {title[t['id']]} | {t['status']} |")
        failed = [t for t in res["test_cases"] if not t["status"].startswith((ICON_PASS, ICON_INFO))]
        return 1 if failed else 0

    if args.cmd == "report":
        results = None
        if args.results:
            results = json.loads(Path(args.results).read_text(encoding="utf-8"))
        rep = build_report_spec(spec, results)
        out_md = Path(args.out_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        gen = find_test_report_generator()
        if gen:
            mod_spec = importlib.util.spec_from_file_location("generate_test_report", gen)
            mod = importlib.util.module_from_spec(mod_spec)
            mod_spec.loader.exec_module(mod)  # type: ignore[union-attr]
            out_md.write_text(mod.render_md(rep), encoding="utf-8")
            if args.out_html:
                Path(args.out_html).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out_html).write_text(mod.render_html(rep), encoding="utf-8")
        else:
            out_md.write_text(fallback_md(rep), encoding="utf-8")
            if args.out_html:
                print("WARN  test-report skill not installed - .html not written (only .md)")
        out_md.with_suffix(".report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False),
                                                      encoding="utf-8")
        print(f"report: {out_md}" + (f" + {args.out_html}" if args.out_html and gen else ""))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
