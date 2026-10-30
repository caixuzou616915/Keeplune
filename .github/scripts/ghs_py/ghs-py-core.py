"""ghs-py-core — Event-driven engine that drives GHS Multi without arbitrary waits.

The existing PowerShell/RC flow proceeds with fixed ``wait -time 3000/20000/90000`` delays: the
script always idles for the *worst-case* time even when the target is ready in a fraction of it,
and it cannot react to an error until the whole delay elapses. This module removes those blind
waits.

**Technique.** Every RC we generate emits unique sentinel markers (``>>>TVPY:TAG<<<``) via
``mprintf`` at each logical checkpoint. Multi streams its output to the ``-R`` log; this engine
*tails that log* and returns the instant the expected marker appears — and kills Multi the instant
a *fatal* marker appears (fast-fail, no blind retry). The only time-based value left is a generous
**safety ceiling** that should never be reached on a healthy bench.

Reusable building blocks (composable per Task 2):

* :class:`MultiRunner` — launch Multi with a marker-instrumented RC and wait *on events*.
* :func:`kill_stale`, :func:`is_running` — process-state helpers (replace ``Start-Sleep``).
* :func:`ensure_canoe` — verify CANoe measurement is running with KL15 ON (win32com).
* RC builders (:func:`rc_marker`, :func:`build_rc`).

Standard library only, plus optional ``win32com`` (CANoe) imported lazily.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ---- load hyphenated sibling modules (filenames use the mandated ghs-py- prefix) -------------
_HERE = Path(__file__).resolve().parent


def load_sibling(short_name: str):
    """Import ``ghs-py-<short_name>.py`` from this folder despite the hyphens in the name."""
    path = _HERE / f"ghs-py-{short_name}.py"
    spec = importlib.util.spec_from_file_location(f"ghs_py_{short_name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # register so dataclass annotations resolve
    spec.loader.exec_module(mod)
    return mod


output = load_sibling("output")

MARKER_PREFIX = ">>>TVPY:"
MARKER_SUFFIX = "<<<"

# Log lines that look alarming but are documented-benign on Traveo II (see debug_traveo_ghs SKILL).
BENIGN_SUBSTRINGS: Tuple[str, ...] = (
    "INCOHERENT",
    "just_did_rom_to_ram_copy failed",
    "Error: General Error",
)

# Fatal substrings — surface immediately and fast-fail (kill Multi, no blind retry).
FATAL_SUBSTRINGS: Tuple[str, ...] = (
    "No match",
    "Cannot set a software breakpoint",
    "Unexpected ack",
    "Could not detect a flash device",
    "Memory write failed",
    "Cannot write",
    "trg_run() failed",
    "SWD protocol error",
    "Green Hills Probe error",
    "Traceback (most recent call last)",
    "command not found",
    "thrown away owing to command failure",
    "ERROR: Read command not successful",
)
# NOTE: deliberately NOT added here: "Cannot set a hardware breakpoint" (a dead-stripped/no-address
# symbol is sometimes the INTENDED, positive result of a test proving a function is uncalled/dead
# code — see UC-01 call-sequence Batch E's negative check), "Resume failed" / "Unable to read
# register" (documented benign/self-recovering transients on the audi_fid_sdv bench when they occur
# as part of the same SWD error-89 burst, e.g. WBT-003 2026-08-18). Callers whose test purpose is to
# arm-and-expect-failure on a specific symbol should catch that case explicitly rather than relying
# on this generic fatal list.

# Transient probe/USB glitches that justify a *single* retry (documented in the GHS skill).
TRANSIENT_SUBSTRINGS: Tuple[str, ...] = (
    "Could not detect a flash device",
    "Memory write failed at 0x100000aa",
    "already connected",
)


# --------------------------------------------------------------------------------------------------
# Process helpers (event/state based — no fixed sleeps)
# --------------------------------------------------------------------------------------------------
def is_running(*names: str) -> bool:
    """True if any named image is currently running (Windows ``tasklist``)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        ).stdout.lower()
    except Exception:
        return False
    return any(n.lower() in out for n in names)


def kill_stale(*names: str, settle_ceiling_s: float = 5.0, poll_s: float = 0.1) -> None:
    """Kill stale debugger/probe holders, then *poll* until they are gone (bounded by a ceiling).

    Replaces ``Stop-Process ...; Start-Sleep 4`` — we wait exactly as long as the OS needs, and
    no longer.
    """
    for n in names:
        subprocess.run(["taskkill", "/F", "/IM", n], capture_output=True, text=True)
    if not names:
        return
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < settle_ceiling_s:
        if not is_running(*names):
            return
        time.sleep(poll_s)


# --------------------------------------------------------------------------------------------------
# CANoe prerequisite (KL15 ON) — condition-based, not a blind sleep
# --------------------------------------------------------------------------------------------------
def ensure_canoe(cfg, step, *, simulate: bool = False) -> Tuple[bool, str]:
    """Ensure CANoe measurement is running (so KL15/SWD is available). Returns (ok, detail).

    In simulate mode this is a no-op success. On a real bench it uses the CANoe COM automation
    model (same mechanism as pyconti ``libtst/canoe.py``) and *polls* ``Measurement.Running``
    rather than sleeping a fixed time.
    """
    if simulate:
        step.event("note", "simulate: CANoe assumed running with KL15 ON")
        return True, "simulated CANoe running (KL15 ON)"
    try:
        import win32com.client  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, f"win32com unavailable ({exc}); start CANoe manually with KL15 ON"

    try:
        app = win32com.client.Dispatch("CANoe.Application")
    except Exception as exc:
        return False, f"CANoe not reachable via COM ({exc})"

    if not app.Measurement.Running:
        step.event("cmd", "CANoe Measurement.Start()")
        app.Measurement.Start()
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 20.0:
            if app.Measurement.Running:
                break
            time.sleep(0.2)
    if not app.Measurement.Running:
        return False, "CANoe measurement did not start (press F9 / check license)"

    # Raise KL15 (IGN_ACC) if the env var exists — ignore if the config doesn't model it.
    try:
        var = app.Environment.GetVariable(cfg.canoe_kl15_env)
        if var.Value != 1:
            var.Value = 1
            step.event("cmd", f"CANoe env {cfg.canoe_kl15_env}=1 (KL15 ON)")
    except Exception:
        pass
    return True, "CANoe measurement running, KL15 ON"


# --------------------------------------------------------------------------------------------------
# RC generation with sentinel markers
# --------------------------------------------------------------------------------------------------
def rc_marker(tag: str, prefix: str = "") -> str:
    """An RC line that prints a unique sentinel the engine can poll for."""
    p = (prefix + " ") if prefix else ""
    return f'{p}mprintf("{MARKER_PREFIX}{tag}{MARKER_SUFFIX}\\n")'


def build_rc(lines: Sequence[str]) -> str:
    """Join RC lines with a trailing newline (Multi requires LF-terminated playback files)."""
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------------
# The event-driven Multi runner
# --------------------------------------------------------------------------------------------------
class MultiResult:
    def __init__(self, ok: bool, matched: List[str], fatal_line: str = "",
                 timed_out: bool = False, log_tail: str = ""):
        self.ok = ok
        self.matched = matched
        self.fatal_line = fatal_line
        self.timed_out = timed_out
        self.log_tail = log_tail


class MultiRunner:
    """Runs one marker-instrumented RC against GHS Multi and waits *on markers*, not on time."""

    def __init__(self, cfg, *, simulate: bool = False, log_cb: Optional[Callable[[str], None]] = None):
        self.cfg = cfg
        self.simulate = simulate
        self.log_cb = log_cb or (lambda s: None)

    # -- public API ------------------------------------------------------------------------------
    def run(self, step, rc_body: str, *, wait_tags: Sequence[str], ceiling_s: float,
            rc_name: str = "tvpy.rc", log_name: str = "tvpy_out.txt",
            sim_timeline: Optional[Sequence[Tuple[float, str]]] = None,
            on_marker: Optional[Callable[[str], None]] = None) -> MultiResult:
        """Write ``rc_body``, launch Multi, and return when *all* ``wait_tags`` are seen.

        ``sim_timeline`` (simulate only) is a list of ``(delay_s, log_text)`` the fake target emits
        so the polling loop is exercised end-to-end without hardware.

        ``on_marker``, if given, is called synchronously (with the tag text) the moment each new
        wanted marker appears in the log -- e.g. so a caller can inject an external action (a CANoe
        signal write) while the target is still halted at that exact point in a multi-step session,
        without waiting for the whole ``run()`` call to return. Exceptions raised by the callback
        propagate to the caller (Multi is still cleaned up via the ``finally`` below).
        """
        build_dir = Path(self.cfg.build_dir())
        rc_path = build_dir / rc_name
        log_path = build_dir / log_name

        if self.simulate:
            build_dir.mkdir(parents=True, exist_ok=True)
        rc_path.write_text(rc_body, encoding="ascii")
        step.event("cmd", f"wrote RC {rc_path.name} ({len(rc_body.splitlines())} lines)")
        if log_path.exists():
            try:
                log_path.unlink()
            except OSError:
                pass

        launcher_log = log_path.with_name(log_path.stem + "_launcher.txt")
        proc = self._launch(rc_path, log_path, sim_timeline, launcher_log)
        try:
            return self._wait_on_markers(step, log_path, wait_tags, ceiling_s,
                                         proc=proc, launcher_log=launcher_log, on_marker=on_marker)
        finally:
            self._cleanup(proc)

    # -- launch ----------------------------------------------------------------------------------
    def _launch(self, rc_path: Path, log_path: Path, sim_timeline, launcher_log: Optional[Path] = None):
        if self.simulate:
            timeline = list(sim_timeline or [(0.05, MARKER_PREFIX + "SIM<<<")])
            t = threading.Thread(target=self._fake_target, args=(log_path, timeline), daemon=True)
            t.start()
            return t

        env = self.cfg.env_exports()
        # NOTE (2026-07-28 bug fix): the trailing "echo <marker>" MUST be quoted -- the marker
        # literally contains ">>>" and "<<<" (MARKER_PREFIX/SUFFIX). Unquoted, bash parses ">>>"
        # as redirection operators and raises "syntax error near unexpected token '>'", which
        # kills the ENTIRE `-c` command line (bash parses the whole line before running ANY of
        # it) -- so `multi` never launches at all. This previously caused a silent, total hang:
        # no -R log, no multi/bash process, nothing until the safety ceiling (300s) finally hit.
        bash_cmd = (
            f"{env}; cd {self.cfg.bash_build_dir()}; "
            f"multi -nosplash -servertimeout 60 debug.ghsmc "
            f"-rc {self.cfg.multi_rc} -rc {self.cfg.debug_rc} "
            f"-R {log_path.name} -p {rc_path.name}; echo \"{MARKER_PREFIX}MULTI_EXIT{MARKER_SUFFIX}\""
        )
        # NOTE: launcher stdout/stderr are captured to <log>_launcher.txt (NOT DEVNULL) so a bash/
        # multi launch failure (bad path, missing license env, immediate crash) is diagnosable
        # instead of silently waiting out the full safety ceiling with zero visible cause.
        launcher_fh = open(launcher_log, "w", encoding="utf-8", errors="replace") if launcher_log else subprocess.DEVNULL
        return subprocess.Popen(
            [self.cfg.git_bash, "-c", bash_cmd],
            stdout=launcher_fh, stderr=subprocess.STDOUT,
        )

    def _fake_target(self, log_path: Path, timeline: Sequence[Tuple[float, str]]) -> None:
        """Simulate the target streaming lines to the -R log over a compressed timeline."""
        with log_path.open("a", encoding="ascii") as fh:
            for delay, text in timeline:
                time.sleep(max(0.0, delay))
                fh.write(text + "\n")
                fh.flush()

    # -- event loop ------------------------------------------------------------------------------
    def _wait_on_markers(self, step, log_path: Path, wait_tags: Sequence[str],
                         ceiling_s: float, *, proc=None,
                         launcher_log: Optional[Path] = None,
                         on_marker: Optional[Callable[[str], None]] = None) -> MultiResult:
        wanted = list(wait_tags)
        seen: List[str] = []
        pos = 0
        t0 = time.perf_counter()
        poll = self.cfg.poll_interval_s
        early_death_checked = False

        while True:
            elapsed = time.perf_counter() - t0
            if elapsed > ceiling_s:
                tail = self._tail(log_path)
                step.event("error", f"safety ceiling {ceiling_s:.0f}s hit waiting for {wanted}")
                return MultiResult(False, seen, timed_out=True, log_tail=tail)

            # Fast-fail: if the bash launcher process already exited AND the -R log never even
            # appeared/grew, the Multi launch itself failed (bad path/env/license) -- surface the
            # captured launcher output immediately instead of silently burning the full ceiling.
            if (not self.simulate and proc is not None and not seen and not log_path.exists()
                    and elapsed > 3.0):
                rc = proc.poll()
                if rc is not None and not early_death_checked:
                    early_death_checked = True
                    launcher_text = ""
                    if launcher_log is not None and launcher_log.exists():
                        try:
                            launcher_text = launcher_log.read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            pass
                    step.event("error", f"bash launcher exited early (rc={rc}) with no -R log; "
                                        f"launcher output: {launcher_text[-2000:]}")
                    return MultiResult(False, seen, fatal_line=f"launcher exited rc={rc}",
                                       log_tail=launcher_text[-2000:])

            if log_path.exists():
                data = log_path.read_text(encoding="ascii", errors="replace")
                chunk, pos = data[pos:], len(data)
                for raw in chunk.splitlines():
                    line = raw.strip()
                    if not line:
                        continue
                    self.log_cb(line)
                    fatal = self._fatal_in(line)
                    if fatal:
                        step.event("error", f"fatal marker: {line}")
                        return MultiResult(False, seen, fatal_line=line,
                                           log_tail=self._tail(log_path))
                    tag = self._tag_in(line)
                    if tag and tag in wanted and tag not in seen:
                        seen.append(tag)
                        step.event("marker", tag)
                        if on_marker is not None:
                            on_marker(tag)
                        if all(w in seen for w in wanted):
                            return MultiResult(True, seen, log_tail=self._tail(log_path))
            time.sleep(poll)

    # -- helpers ---------------------------------------------------------------------------------
    @staticmethod
    def _tag_in(line: str) -> Optional[str]:
        i = line.find(MARKER_PREFIX)
        if i < 0:
            return None
        j = line.find(MARKER_SUFFIX, i)
        if j < 0:
            return None
        return line[i + len(MARKER_PREFIX):j]

    @staticmethod
    def _fatal_in(line: str) -> Optional[str]:
        if any(b in line for b in BENIGN_SUBSTRINGS):
            return None
        for f in FATAL_SUBSTRINGS:
            if f in line:
                return f
        return None

    @staticmethod
    def _tail(log_path: Path, n: int = 40) -> str:
        if not log_path.exists():
            return ""
        lines = [l for l in log_path.read_text(encoding="ascii", errors="replace").splitlines()
                 if not any(b in l for b in BENIGN_SUBSTRINGS)]
        return "\n".join(lines[-n:])

    def _cleanup(self, proc) -> None:
        if self.simulate:
            return
        try:
            if proc and proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
        kill_stale("multi.exe", "mpserv.exe", settle_ceiling_s=3.0)


def is_transient(fatal_line: str) -> bool:
    """True if a fatal line is a known transient probe/USB glitch worth exactly one retry."""
    return any(t in fatal_line for t in TRANSIENT_SUBSTRINGS)
