"""ghs-py-output — Structured session recorder + console/JSON reporting engine.

This is the *single source of truth* for everything a flash/debug session produces. Every step
script records into a :class:`SessionRecorder`; the recorder then renders three consistent views:

* a human-readable **console log** (:meth:`SessionRecorder.render_console`)
* a machine-readable **JSON** document (:meth:`SessionRecorder.to_json`)
* the same ``dict`` that drives the canonical **HTML report** and the **benchmark** module

It captures — per Task 4 — the exact ordered steps, breakpoints (file/function/line/hit),
per-step and total timing, inspected register/memory/variable values, pass/fail + errors and how
they were handled, plus arbitrary diagnostic detail.

Pure standard library — safe to import anywhere, no hardware required.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "1.0.0"

# Status constants (kept as plain strings so JSON stays trivially diffable).
PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
RUNNING = "RUNNING"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------------------------------
@dataclass
class Event:
    """A single timestamped diagnostic line inside a step (marker seen, command sent, note)."""
    ts: str
    elapsed_s: float
    kind: str          # "marker" | "cmd" | "note" | "error" | "value"
    text: str


@dataclass
class Inspection:
    """A register / memory / variable value read at some point in the session."""
    name: str
    scope: str         # "register" | "variable" | "memory" | "struct"
    expr: str
    value: str
    step: str = ""
    ts: str = field(default_factory=_now_iso)
    raw: str = ""


@dataclass
class Breakpoint:
    """A breakpoint request + its outcome (file/function/line/address/hit)."""
    function: str
    file: str = ""
    line: Optional[int] = None
    address: str = ""
    kind: str = "hardbrk rolling"
    hit: bool = False
    hit_count: int = 0
    values: Dict[str, str] = field(default_factory=dict)   # e.g. {"$r0": "0x30A0"}


@dataclass
class ErrorRecord:
    """An error the session encountered and how it was handled (fast-fail / retry / ignored)."""
    step: str
    message: str
    marker: str = ""
    handled: bool = False
    action: str = ""


@dataclass
class Step:
    """One composable stage: connect / flash / verify / debug-launch / <op> / report."""
    name: str
    status: str = RUNNING
    started_iso: str = ""
    ended_iso: str = ""
    elapsed_s: float = 0.0
    detail: str = ""
    events: List[Event] = field(default_factory=list)
    error: str = ""
    _t0: float = field(default=0.0, repr=False)

    def start(self) -> "Step":
        self._t0 = time.perf_counter()
        self.started_iso = _now_iso()
        self.status = RUNNING
        return self

    def event(self, kind: str, text: str) -> None:
        self.events.append(Event(_now_iso(), round(time.perf_counter() - self._t0, 3), kind, text))

    def finish(self, status: str, detail: str = "", error: str = "") -> "Step":
        self.elapsed_s = round(time.perf_counter() - self._t0, 3)
        self.ended_iso = _now_iso()
        self.status = status
        if detail:
            self.detail = detail
        if error:
            self.error = error
        return self


# --------------------------------------------------------------------------------------------------
# Recorder
# --------------------------------------------------------------------------------------------------
class SessionRecorder:
    """Collects everything about one flash/debug run and renders console/JSON output."""

    def __init__(self, *, method: str, config: Dict[str, Any], host: Dict[str, str],
                 task: str = "", device: str = "GHS Multi", simulate: bool = False):
        self.schema_version = SCHEMA_VERSION
        self.method = method            # "new-python" | "current-rc"
        self.device = device
        self.simulate = simulate
        self.task = task
        self.config = config
        self.host = host
        self.started_iso = _now_iso()
        self.ended_iso = ""
        self._t0 = time.perf_counter()
        self.total_elapsed_s = 0.0
        self.steps: List[Step] = []
        self.breakpoints: List[Breakpoint] = []
        self.inspections: List[Inspection] = []
        self.errors: List[ErrorRecord] = []
        self.benchmark: Dict[str, Any] = {}
        self._active: Optional[Step] = None

    # -- step lifecycle --------------------------------------------------------------------------
    def begin_step(self, name: str) -> Step:
        step = Step(name=name).start()
        self.steps.append(step)
        self._active = step
        return step

    @property
    def active(self) -> Optional[Step]:
        return self._active

    def end_step(self, status: str, detail: str = "", error: str = "") -> Step:
        assert self._active is not None, "end_step() called with no active step"
        step = self._active.finish(status, detail, error)
        self._active = None
        return step

    # -- diagnostics -----------------------------------------------------------------------------
    def add_breakpoint(self, bp: Breakpoint) -> None:
        self.breakpoints.append(bp)

    def add_inspection(self, insp: Inspection) -> None:
        if not insp.step and self._active:
            insp.step = self._active.name
        self.inspections.append(insp)

    def add_error(self, err: ErrorRecord) -> None:
        self.errors.append(err)

    # -- finalisation ----------------------------------------------------------------------------
    def finalize(self) -> None:
        self.total_elapsed_s = round(time.perf_counter() - self._t0, 3)
        self.ended_iso = _now_iso()

    @property
    def overall(self) -> str:
        if any(s.status == FAIL for s in self.steps):
            return FAIL
        if self.steps and all(s.status in (PASS, SKIP) for s in self.steps):
            return PASS
        return RUNNING

    # -- serialization ---------------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "metadata": {
                "task": self.task,
                "method": self.method,
                "device": self.device,
                "simulate": self.simulate,
                "target_variant": self.config.get("variant", ""),
                "bench": self.config.get("bench", ""),
                "chip": self.config.get("chip", ""),
                "app_core": self.config.get("app_core", ""),
                "started": self.started_iso,
                "ended": self.ended_iso,
                "host": self.host,
            },
            "summary": {
                "overall": self.overall,
                "total_elapsed_s": self.total_elapsed_s,
                "steps_total": len(self.steps),
                "steps_passed": sum(1 for s in self.steps if s.status == PASS),
                "steps_failed": sum(1 for s in self.steps if s.status == FAIL),
                "steps_skipped": sum(1 for s in self.steps if s.status == SKIP),
                "breakpoints_total": len(self.breakpoints),
                "breakpoints_hit": sum(1 for b in self.breakpoints if b.hit),
                "errors_total": len(self.errors),
                "errors_handled": sum(1 for e in self.errors if e.handled),
            },
            "steps": [
                {k: v for k, v in asdict(s).items() if not k.startswith("_")}
                for s in self.steps
            ],
            "breakpoints": [asdict(b) for b in self.breakpoints],
            "inspections": [asdict(i) for i in self.inspections],
            "errors": [asdict(e) for e in self.errors],
            "benchmark": self.benchmark,
            "config": self.config,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def write_json(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    # -- console renderer ------------------------------------------------------------------------
    def render_console(self, color: bool = True) -> str:
        c = _Palette(color)
        d = self.to_dict()
        meta, summ = d["metadata"], d["summary"]
        L: List[str] = []
        bar = "=" * 78
        L.append(c.head(bar))
        L.append(c.head(f" GHS-PY FLASH/DEBUG SESSION — {meta['method'].upper()}"
                        f"{'  [SIMULATE]' if meta['simulate'] else ''}"))
        L.append(c.head(bar))
        L.append(f" Task     : {meta['task'] or '(debug session)'}")
        L.append(f" Target   : {meta['target_variant']}  (bench {meta['bench']}, "
                 f"{meta['chip']}, core {meta['app_core']})")
        L.append(f" Device   : {meta['device']}")
        L.append(f" Started  : {meta['started']}")
        L.append(f" Host     : {meta['host'].get('hostname','?')}  "
                 f"({meta['host'].get('os','?')}, py{meta['host'].get('python','?')})")
        L.append("")
        # Overview
        ov = summ["overall"]
        L.append(c.head(" OVERVIEW"))
        L.append(f"   Result           : {c.status(ov)}")
        L.append(f"   Total elapsed    : {summ['total_elapsed_s']:.3f}s")
        L.append(f"   Steps            : {summ['steps_passed']}/{summ['steps_total']} passed"
                 f"  ({summ['steps_failed']} failed, {summ['steps_skipped']} skipped)")
        L.append(f"   Breakpoints hit  : {summ['breakpoints_hit']}/{summ['breakpoints_total']}")
        L.append(f"   Errors           : {summ['errors_total']} "
                 f"({summ['errors_handled']} handled)")
        L.append("")
        # Timeline
        L.append(c.head(" STEP-BY-STEP TIMELINE"))
        L.append(f"   {'#':<3}{'Step':<18}{'Status':<9}{'Elapsed':>10}   Detail")
        L.append(f"   {'-'*3}{'-'*18}{'-'*9}{'-'*10:>10}   {'-'*30}")
        for i, s in enumerate(d["steps"], 1):
            L.append(f"   {i:<3}{s['name']:<18}{c.status(s['status']):<9}"
                     f"{s['elapsed_s']:>9.3f}s   {s['detail']}")
            if s["error"]:
                L.append(f"       {c.err('! ' + s['error'])}")
        L.append("")
        # Breakpoints
        if self.breakpoints:
            L.append(c.head(" BREAKPOINTS"))
            L.append(f"   {'Function':<34}{'File':<16}{'Line':>5} {'Hit':>4}  Values")
            for b in d["breakpoints"]:
                vals = ", ".join(f"{k}={v}" for k, v in b["values"].items())
                line = b["line"] if b["line"] is not None else "-"
                L.append(f"   {b['function'][:33]:<34}{(b['file'] or '-')[:15]:<16}"
                         f"{str(line):>5} {('YES' if b['hit'] else 'no'):>4}  {vals}")
            L.append("")
        # Inspections
        if self.inspections:
            L.append(c.head(" INSPECTED VALUES (registers / memory / variables)"))
            L.append(f"   {'Name':<30}{'Scope':<11}{'Value':<20}Step")
            for it in d["inspections"]:
                L.append(f"   {it['name'][:29]:<30}{it['scope']:<11}"
                         f"{it['value'][:19]:<20}{it['step']}")
            L.append("")
        # Errors
        if self.errors:
            L.append(c.head(" ERRORS & HANDLING"))
            for e in d["errors"]:
                tag = c.ok("handled") if e["handled"] else c.err("UNHANDLED")
                L.append(f"   [{e['step']}] {e['message']}  -> {tag}: {e['action']}")
            L.append("")
        # Benchmark
        if self.benchmark:
            L.append(c.head(" BENCHMARK (old current-rc vs new python)"))
            for row in self.benchmark.get("rows", []):
                L.append(f"   {row['step']:<18}old {row['old_s']:>8.2f}s   "
                         f"new {row['new_s']:>8.2f}s   x{row['speedup']:.2f}  "
                         f"(-{row['saved_s']:.2f}s)")
            tot = self.benchmark.get("totals", {})
            if tot:
                L.append(f"   {'TOTAL':<18}old {tot['old_s']:>8.2f}s   "
                         f"new {tot['new_s']:>8.2f}s   x{tot['speedup']:.2f}  "
                         f"(-{tot['saved_s']:.2f}s)")
            L.append("")
        L.append(c.head(bar))
        return "\n".join(L)


# --------------------------------------------------------------------------------------------------
# Tiny ANSI palette (degrades to plain text)
# --------------------------------------------------------------------------------------------------
class _Palette:
    def __init__(self, enabled: bool):
        self.on = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.on else text

    def head(self, t: str) -> str:  return self._wrap("1;36", t)
    def ok(self, t: str) -> str:    return self._wrap("1;32", t)
    def err(self, t: str) -> str:   return self._wrap("1;31", t)

    def status(self, s: str) -> str:
        if s == PASS:    return self._wrap("1;32", s)
        if s == FAIL:    return self._wrap("1;31", s)
        if s == SKIP:    return self._wrap("1;33", s)
        return self._wrap("1;34", s)
