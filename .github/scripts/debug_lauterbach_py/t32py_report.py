"""t32py_report - minimal session recorder + JSON/console report for debug_lauterbach_py.

Mirrors the reporting convention used by ghs_py (console + JSON to ai_output/), scoped down
(no HTML/benchmark) since this skill's operations are direct TRACE32 API calls, not a
log-tailing flash pipeline.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class StepRecord:
    name: str
    ok: bool
    detail: str = ""
    duration_s: float = 0.0


@dataclass
class SessionRecorder:
    op: str
    variant: str
    simulate: bool = False
    started_at: float = field(default_factory=time.time)
    steps: List[StepRecord] = field(default_factory=list)
    result: Optional[Any] = None
    error: Optional[str] = None

    def step(self, name: str):
        return _StepTimer(self, name)

    def to_dict(self) -> Dict:
        return {
            "op": self.op,
            "variant": self.variant,
            "simulate": self.simulate,
            "started_at": self.started_at,
            "duration_s": round(time.time() - self.started_at, 3),
            "steps": [s.__dict__ for s in self.steps],
            "result": self.result,
            "error": self.error,
            "ok": self.error is None,
        }

    def print_console(self) -> None:
        print(f"[t32py] op={self.op} variant={self.variant} simulate={self.simulate}")
        for s in self.steps:
            status = "OK" if s.ok else "FAIL"
            print(f"  [{status}] {s.name} ({s.duration_s:.3f}s) {s.detail}")
        if self.error:
            print(f"[t32py] ERROR: {self.error}")
        else:
            print(f"[t32py] result: {self.result}")

    def write_json(self, out_dir: Path, name: Optional[str] = None) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = name or f"t32py_{self.op}_{int(self.started_at)}.json"
        out_path = out_dir / fname
        out_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return out_path


class _StepTimer:
    def __init__(self, recorder: SessionRecorder, name: str):
        self.recorder = recorder
        self.name = name
        self._t0 = 0.0

    def __enter__(self):
        self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb):
        duration = time.monotonic() - self._t0
        if exc is not None:
            self.recorder.steps.append(StepRecord(self.name, ok=False, detail=str(exc), duration_s=duration))
            self.recorder.error = f"{self.name}: {exc}"
            return False  # re-raise
        self.recorder.steps.append(StepRecord(self.name, ok=True, duration_s=duration))
        return False
