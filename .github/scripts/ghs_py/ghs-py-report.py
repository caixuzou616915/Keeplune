"""ghs-py-report — Reporting step: turn a recorded session into console + JSON + HTML.

This is the composable *report* stage. It is the single place that:

* attaches the old-vs-new benchmark (from measured step timings),
* writes the machine-readable JSON,
* renders the canonical HTML report,
* prints the human-readable console log.

It can be used two ways:

* **chained** — the orchestrator/steps call :func:`build_recorder`, run stages, then :func:`emit`.
* **standalone** — ``python ghs-py-report.py <session.json> [out_dir]`` re-renders the HTML from
  an existing JSON (handy for regenerating a report without re-running hardware).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import importlib.util

_HERE = Path(__file__).resolve().parent


def _load(short: str):
    path = _HERE / f"ghs-py-{short}.py"
    spec = importlib.util.spec_from_file_location(f"ghs_py_{short}", path)
    mod = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
    sys.modules[spec.name] = mod                          # register for dataclass resolution
    spec.loader.exec_module(mod)                          # type: ignore[union-attr]
    return mod


output = _load("output")
html_report = _load("html-report")
benchmark = _load("benchmark")
config = _load("config")


DEFAULT_OUT_DIR = _HERE.parent.parent.parent / "ai_output" / "ghs_py"


def build_recorder(cfg, *, method: str = "new-python", task: str = "",
                   device: str = "GHS Multi", simulate: bool = False):
    """Create a :class:`SessionRecorder` wired to the given config."""
    return output.SessionRecorder(
        method=method,
        config=cfg.to_dict(),
        host=config.host_info(),
        task=task,
        device=device,
        simulate=simulate,
    )


def attach_benchmark(rec) -> None:
    """Compute + attach the old-vs-new benchmark from the session's measured timings."""
    session = rec.to_dict()
    measured = benchmark.measured_from_session(session)
    rec.benchmark = benchmark.build_comparison(measured, simulate=rec.simulate)


def emit(rec, *, out_dir: Optional[Path] = None, base_name: str = "",
         print_console: bool = True, color: bool = True) -> Dict[str, str]:
    """Finalize the session and write JSON + HTML; optionally print the console log.

    Returns a dict of artifact paths.
    """
    rec.finalize()
    attach_benchmark(rec)

    out_dir = Path(out_dir) if out_dir else Path(DEFAULT_OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not base_name:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = rec.config.get("variant", "session").replace(".", "_")
        base_name = f"ghs-py_{tag}_{stamp}"

    session = rec.to_dict()
    json_path = out_dir / f"{base_name}.json"
    html_path = out_dir / f"{base_name}.html"
    json_path.write_text(json.dumps(session, indent=2, default=str), encoding="utf-8")
    html_report.write(session, html_path)

    if print_console:
        print(rec.render_console(color=color))
        print(f"\n[report] JSON : {json_path}")
        print(f"[report] HTML : {html_path}")

    return {"json": str(json_path), "html": str(html_path)}


def regenerate_from_json(json_path: str, out_dir: Optional[str] = None) -> Dict[str, str]:
    """Standalone: rebuild the HTML report (and echo console) from an existing session JSON."""
    session = json.loads(Path(json_path).read_text(encoding="utf-8"))
    out = Path(out_dir) if out_dir else Path(json_path).parent
    out.mkdir(parents=True, exist_ok=True)
    base = Path(json_path).stem
    html_path = out / f"{base}.html"
    html_report.write(session, html_path)
    print(f"[report] regenerated HTML : {html_path}")
    return {"html": str(html_path)}


def main(argv) -> int:
    if not argv:
        print("usage: python ghs-py-report.py <session.json> [out_dir]", file=sys.stderr)
        return 2
    regenerate_from_json(argv[0], argv[1] if len(argv) > 1 else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
