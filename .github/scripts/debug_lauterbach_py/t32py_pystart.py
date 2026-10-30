#!/usr/bin/env python3
"""t32py_pystart - Launch + flash + AMP-start a TRACE32 session from Python (pystart + RCL).

This is the WORKING, bench-verified alternative to the legacy ctypes/attach path
(``t32py_client.py``). Instead of attaching to an already-running, RCL-enabled TRACE32
session (which this project's ``run.py ... debug_trace32`` launch never provides - see the
SKILL.md "Status" note), this module **launches TRACE32 itself** using
``lauterbach-trace32-pystart`` with the RCL interface enabled. pystart builds its own config
with RCL turned on, so there is a live Remote-API listener to drive - which is exactly what
makes the AMP master/slave flash+start flow work headlessly.

Bench-verified 2026-08-07 on ``tviib_e4m_aravalli_s3p`` (CYT2BL7CAE, LA-3770 USB): flashes the
SFLASH/HSM/FBL/App image set via the project's own CMM script, starts BOTH the CM0+ (master)
and CM4 (application) cores, streams live flash/attach status, and demonstrates app-core
breakpoints + variable read/write (e.g. AmmSM_vMainFunction / AmmSM__enReqMode).

Requires:
    pip install lauterbach-trace32-pystart lauterbach-trace32-rcl
    pip install pywin32        # optional - only for the fatal-dialog window scan

Prerequisite (per lauterbach-trace32 / traveo-flash skills): CANoe running with KL15 ON and the
Lauterbach probe connected with target power ON, BEFORE running - otherwise SYStem.Up cannot
attach and the target stays "system down".

Config is resolved from the same ``LT_*``/``T32PY_*`` env vars as the rest of this skill (see
``t32py_config.py``), so nothing is hardcoded to one machine/checkout:

    LT_VARIANT            (required)  build variant, e.g. tviib_e4m_aravalli_s3p
    LT_VARIANT_CONFIG     (Debug)     build config suffix
    LT_REPO_ROOT          (auto)      repo root (auto-discovered from run.py + econ_config.sh)
    T32PY_SYSTEM_PATH     (auto)      TRACE32 system dir (parent of bin/windows64); auto from
                                      a running/searched t32marm.exe via t32py_config
    T32PY_CMM             (auto)      flash/AMP-attach CMM; auto-discovered by trying, in order:
                                      (1) app/variants/<variant>/source/Lauterbach_scripts/*.cmm
                                          (also honors LT_STARTUP_SCRIPT if set - see
                                          t32py_config.resolved_startup_script())
                                      (2) app/variants/<variant>/debug/Lauterbach/*.cmm (older
                                          project layout) - see _discover_cmm()
    T32PY_PORT            (20000)     RCL port
    T32PY_INTERCOM_PORT   (unset)     InterCom port; leave UNSET for the CMM's own
                                      TargetSystem.NewInstance AMP spawn (adding an explicit
                                      IntercomInterface caused "InterCom name M4 already exists")
    T32PY_SLAVE_ALIAS     (M4)        AMP InterCom alias of the application-core slave instance

CLI:
    python t32py_pystart.py                 # full flow: launch -> flash -> start both cores; KEEP OPEN
    python t32py_pystart.py --shutdown       # same, but proper SYStem.Down + QUIT power-off at the end
    python t32py_pystart.py --connect-only   # launch + connect + report status, then shut down
    python t32py_pystart.py --no-start       # launch + flash, but don't Go the cores
    python t32py_pystart.py --variant <v>    # override LT_VARIANT
    python t32py_pystart.py --set-break AmmSM_vMainFunction --read AmmSM__enReqMode --write AmmSM__enReqMode=2
    python t32py_pystart.py --set-break IllumSM_vMainFunction --stack --read IllumSM__enReqMode
    python t32py_pystart.py --attach --read SysCtlSM__enCurrentState   # NO reflash - attach to an
                                             # already-running (keep-open) session for a quick,
                                             # fully headless status/variable check. PREFERRED over
                                             # screenshot-based verification whenever a session is
                                             # already up - see SKILL.md.
    python t32py_pystart.py --attach --do-app out/t32/DTC-01.cmm --do-app out/t32/DTC-02.cmm
                                             # run Debug Test Case (.cmm compiled by the
                                             # debug-test-cases skill's dtc_tool.py) on the app
                                             # core and wait for its DTC|<id>|END/ABORT marker.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import lauterbach.trace32.pystart as pystart
import lauterbach.trace32.rcl as t32api

from t32py_config import load_config, ConfigError

# ─────────────────────────────────────────────────────────
#  Tunables (generic - safe defaults; override the *paths* via env, not these)
# ─────────────────────────────────────────────────────────
RCL_SPAWN_DELAY         = 3     # s after start() before we begin polling the RCL port
RCL_TIMEOUT             = 45    # s to wait for the RCL port to open (USB/PODBUS attach is slow)
RCL_CONNECT_RETRIES     = 8     # extra RCL connect retries
RCL_CONNECT_RETRY_DELAY = 5     # s between connect retries
RCL_CMD_TIMEOUT         = 180   # per-command RCL timeout (default 60s too short for AMP attach)
CMM_SCRIPT_TIMEOUT      = 900   # max s for the full flash/AMP-attach CMM script
FLASH_PROGRESS_INTERVAL = 5     # s between live status reports during flashing
SYSTEM_UP_GRACE         = 30    # s to allow the MASTER core to attach before failing fast
POST_CONNECT_SETTLE     = 12    # s to let debug HW settle after the RCL port opens, before flashing
FLASH_ATTACH_RETRIES    = 1     # auto reset+rerun attempts on an intermittent attach miss
SLAVE_READY_TIMEOUT     = 30    # s to wait for the AMP slave to become InterCom-responsive
STACK_CAPTURE_TIMEOUT   = 30    # s to wait for the app core to actually halt (e.g. breakpoint hit)
STACK_CAPTURE_POLL      = 1.0   # s between Frame.List retries while waiting for a halt
STACK_MAX_FRAMES        = 20    # default max call-stack frames reported by --stack
SLAVE_READY_SETTLE      = 1     # s settle after the slave first answers a ping

# Default post-flash breakpoints the CMM arms on the app core; deleting them + Go lets the
# application actually run. Override via T32PY_SLAVE_BREAKPOINTS (comma-separated) if needed.
DEFAULT_SLAVE_BREAKPOINTS = [
    "Det_ASR40_ReportError",
    "Startup_Init",
    "ErrorHook",
    "Mcu_PerformReset",
]

# Meaning of dbg.get_state() (TRACE32 T32_GetState).
T32_STATE_LABELS = {
    0: "system down",
    1: "system halted (no-debug)",
    2: "stopped (halted at breakpoint/debug)",
    3: "running",
}
T32_MSG_ERROR_BIT = 0x2  # bit set in get_message().type for an ERROR (vs. info/status)

# Fatal TRACE32 startup problems that appear in the t32marm console output BEFORE RCL is up
# (so dbg.get_message() can never see them) - captured via the pystart logger stream below.
_FATAL_KEYWORDS = ("fatal error", "already used by other gui", "podbus", "device already",
                   "no connection", "unexpected", "cannot open")

T32_PROCESS_NAMES = ("t32marm", "t32marm64", "t32mppc", "t32mtc", "t32rem",
                     "t32start", "t32mciserver", "t32tcpusb", "t32usbfa")

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("t32py_pystart")


# ─────────────────────────────────────────────────────────
#  Runtime configuration (resolved from env / t32py_config - nothing hardcoded)
# ─────────────────────────────────────────────────────────
class RuntimeConfig:
    """Resolved, machine-specific values for one run."""
    def __init__(self, variant: str | None = None):
        cfg = load_config(variant=variant) if variant else load_config()
        self.variant = cfg.variant
        self.repo_root = str(cfg.repo_root)
        self.rcl_port = int(os.environ.get("T32PY_PORT", str(cfg.port)))
        ic = os.environ.get("T32PY_INTERCOM_PORT")
        self.intercom_port = int(ic) if ic else None
        self.slave_alias = os.environ.get("T32PY_SLAVE_ALIAS", "M4")
        bps = os.environ.get("T32PY_SLAVE_BREAKPOINTS")
        self.slave_breakpoints = [b.strip() for b in bps.split(",") if b.strip()] if bps \
            else list(DEFAULT_SLAVE_BREAKPOINTS)

        # TRACE32 system dir (parent of bin/windows64).
        self.system_path = os.environ.get("T32PY_SYSTEM_PATH") or str(cfg.t32_sys_dir())

        # App ELF (.abs) with debug symbols, for read/write of app variables from the master
        # (symbols-only load; the CM0+ master shares the memory bus with the CM4 app core).
        self.abs_file = str(cfg.resolved_abs_file())

        # Flash/AMP-attach CMM script: env override, else auto-discovered - see _discover_cmm()
        # for the two folder conventions this checks (projects differ).
        self.cmm_script = os.environ.get("T32PY_CMM") or self._discover_cmm(cfg)

        # TRACE32's working dir must be exactly 2 segments below repo root, because the CMM
        # uses paths like "../../build/..." and "../../app/variants/common/...".
        self.cmm_cwd = str(Path(self.repo_root) / "app" / "variants")

    def _discover_cmm(self, cfg) -> str:
        # Project layouts observed on the bench differ: tviib_e4m_aravalli_s3p uses
        # app/variants/<variant>/debug/Lauterbach/, while tviib_2m_aravalli_s3p (and the
        # debug_traveo_lauterbach GUI skill's own convention) uses
        # app/variants/<variant>/source/Lauterbach_scripts/. Try t32py_config's own resolver
        # first (source/Lauterbach_scripts - also honors LT_STARTUP_SCRIPT), then fall back to
        # the debug/Lauterbach layout, before giving up.
        resolved = cfg.resolved_startup_script()
        if resolved is not None:
            return str(resolved)

        d = Path(self.repo_root) / "app" / "variants" / self.variant / "debug" / "Lauterbach"
        if not d.is_dir():
            raise ConfigError(
                f"CMM script not found under app/variants/{self.variant}/source/Lauterbach_scripts/ "
                f"nor {d}. Set T32PY_CMM to the flash/AMP-attach .cmm script.")
        hits = sorted(p for p in d.glob("*.cmm") if p.is_file())
        if not hits:
            raise ConfigError(f"No *.cmm under {d}. Set T32PY_CMM explicitly.")
        # Prefer a name containing 'flash' if there are several.
        flash = [p for p in hits if "flash" in p.name.lower()]
        return str((flash or hits)[0])


CFG: RuntimeConfig  # populated by main()


# ─────────────────────────────────────────────────────────
#  Fatal-startup capture (the one class dbg.get_message() can never see)
# ─────────────────────────────────────────────────────────
class _FatalLogCatcher(logging.Handler):
    """Capture t32marm console output (via pystart loggers) so startup fatals like the PODBUS
    "device already used by other GUI" dialog - which happen before RCL exists - are visible."""
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []
        self.fatal_lines: list[str] = []

    def emit(self, record):
        try:
            text = record.getMessage()
        except Exception:
            return
        self.lines.append(text)
        low = text.lower()
        if any(k in low for k in _FATAL_KEYWORDS):
            self.fatal_lines.append(text.strip())


def _detect_fatal_dialog_windows() -> list:
    """Scan visible top-level windows for a TRACE32/PODBUS fatal-error dialog (the modal
    startup dialog that blocks t32marm before its RCL port opens). Needs pywin32; [] if absent."""
    try:
        import win32gui  # type: ignore
    except Exception:
        return []
    found: list[str] = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd) or ""
            low = title.lower()
            if any(k in low for k in _FATAL_KEYWORDS) or ("trace32" in low and "error" in low):
                found.append(title)

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return found


def _dismiss_welcome_dialog_windows() -> int:
    """Dismiss any "Welcome to TRACE32!" onboarding modal currently on-screen (MASTER or the
    AMP-spawned SLAVE alike). Bench-verified 2026-08-12: this dialog reappears on EVERY fresh
    instance launch - even with its own "Show this dialog at start" checkbox already unchecked,
    since each launch gets a fresh temp profile/config dir.

    IMPORTANT CORRECTION (2026-08-12, same day): earlier notes here claimed this dialog was
    "purely visual" and didn't block anything - THAT WAS WRONG. It genuinely blocks TRACE32's own
    command/message processing, which in turn blocks RCL calls (`dbg.get_message()`/`dbg.fnc()`)
    made from the main thread - a live run stalled for 100+ seconds with the main polling loop
    stuck on an RCL call, and only resumed the instant the dialog was dismissed externally. (The
    earlier "proof" that it didn't block anything was flawed: that test always dismissed the
    dialog via PowerShell BEFORE querying state, so it never actually tested with the dialog
    still up.) Because of this, dismissal MUST happen on a background thread independent of the
    main RCL polling loop (see `_welcome_dialog_watcher`) - calling this only *after* a blocking
    RCL call in the same loop iteration is unreachable if that call is what's stuck.

    Needs pywin32; no-op if absent. ESC via a WScript.Shell AppActivate+SendKeys is the only
    dismissal method proven reliable (WM_CLOSE-by-window-title and simulated mouse clicks on its
    visible X were both tried and found unreliable). CoInitialize/CoUninitialize are required
    here because this is called from a background thread (daemon watcher) that never otherwise
    initializes COM - without it, `win32com.client.Dispatch` can silently misbehave (AppActivate/
    SendKeys appearing to succeed but not actually reaching the window) - this was bench-observed
    as the reason the very first version of this function (called only from the main thread,
    which already has COM initialized implicitly) worked inconsistently once moved to a thread."""
    try:
        import pythoncom  # type: ignore
        import win32gui  # type: ignore
        import win32com.client  # type: ignore
    except Exception:
        return 0
    pythoncom.CoInitialize()
    try:
        matches: list[tuple[int, int]] = []  # (hwnd, pid)

        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd) or ""
                if "welcome to trace32" in title.lower():
                    _, pid = win32gui.GetWindowThreadProcessId(hwnd)
                    matches.append((hwnd, pid))

        try:
            win32gui.EnumWindows(_cb, None)
        except Exception:
            return 0
        if not matches:
            return 0
        shell = win32com.client.Dispatch("WScript.Shell")
        dismissed = 0
        for _hwnd, pid in matches:
            try:
                if not shell.AppActivate(pid):
                    time.sleep(0.3)
                    shell.AppActivate(pid)
                time.sleep(0.3)
                shell.SendKeys("{ESC}")
                time.sleep(0.5)
                dismissed += 1
                log.info("Dismissed 'Welcome to TRACE32!' dialog on PID %s", pid)
            except Exception:
                pass
        return dismissed
    finally:
        pythoncom.CoUninitialize()


# ─────────────────────────────────────────────────────────
#  Process cleanup / proper power-off
# ─────────────────────────────────────────────────────────
def _list_t32_pids():
    """Return [(pid, name)] for every live TRACE32 host process."""
    pids = []
    result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, check=False)
    for line in result.stdout.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) < 2:
            continue
        name = parts[0].rsplit(".exe", 1)[0].lower()
        if name in T32_PROCESS_NAMES:
            try:
                pids.append((int(parts[1]), parts[0]))
            except ValueError:
                pass
    return pids


def _force_kill_trace32():
    """Force-kill lingering TRACE32 processes, poll until gone, then let the USB driver settle.
    A stuck t32marm (e.g. blocked on a fatal dialog) is the usual cause of "device already used"
    on the next launch. NOTE: force-kill frees the process but NOT the PODBUS driver's device
    lock - only a graceful SYStem.Down/QUIT does that. This is the last-resort cleaner."""
    existing = _list_t32_pids()
    if existing:
        log.warning("Found %d stale TRACE32 process(es): %s - killing them.",
                    len(existing), ", ".join(f"{n}(PID {p})" for p, n in existing))
    for proc in T32_PROCESS_NAMES:
        subprocess.run(["taskkill", "/F", "/IM", f"{proc}.exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if not existing:
        return
    for _ in range(20):  # up to ~10s
        remaining = _list_t32_pids()
        if not remaining:
            break
        time.sleep(0.5)
    else:
        log.error("TRACE32 processes still alive after kill: %s - USB may remain locked.", remaining)
    log.info("Waiting for USB PODBUS device to be released...")
    time.sleep(10)


def _reset_podbus_usb() -> bool:
    """Reset the Lauterbach PODBUS USB device via Windows PnP - the software equivalent of a
    physical power-cycle. This is the ONLY way to clear a STUCK "device already used by other
    GUI" driver lock when there is no live TRACE32 instance left to QUIT (a prior force-kill
    freed the process but not the driver's device claim). Tries `pnputil /restart-device`
    first, then Disable/Enable-PnpDevice. Both usually need admin; returns True only if a
    device was actually restarted. If it returns False, a physical probe power-cycle is needed."""
    ps = r'''
$dev = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -match 'VID_0897&PID_0004' -or $_.FriendlyName -match 'PODBUS|Lauterbach' }
if (-not $dev) { Write-Output 'NO_DEVICE'; exit 0 }
$ok = $false
foreach ($d in $dev) {
    try { & pnputil /restart-device "$($d.InstanceId)" 2>$null; if ($LASTEXITCODE -eq 0) { $ok = $true; continue } } catch {}
    try { Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop; Start-Sleep -Milliseconds 800;
          Enable-PnpDevice  -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop; $ok = $true } catch {}
}
if ($ok) { Write-Output 'RESET_OK' } else { Write-Output 'RESET_FAILED' }
'''
    log.info("Attempting to reset the Lauterbach PODBUS USB device (software power-cycle)...")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=40).stdout.strip()
    except Exception as e:  # noqa: BLE001
        log.warning("PODBUS USB reset could not run (%s).", e)
        return False
    if "RESET_OK" in out:
        log.info("PODBUS USB device reset OK - waiting for it to re-enumerate...")
        time.sleep(6)
        return True
    if "NO_DEVICE" in out:
        log.warning("No Lauterbach PODBUS USB device found to reset.")
    else:
        log.warning("PODBUS USB reset did not succeed (likely needs admin rights): %s", out or "(no output)")
    return False


def _graceful_pre_launch_cleanup():
    """Cleanly release the probe BEFORE launching. If a previous run left TRACE32 running (the
    default now KEEPS it open), the next launch must NOT just force-kill it - force-kill frees
    the process but leaves the PODBUS driver's USB lock stuck, so the fresh instance then fails
    with "device already used by other GUI". Instead: if an instance is alive AND its RCL port
    is reachable, connect and QUIT it properly (SYStem.Down + QUIT releases the lock); only
    force-kill as a fallback for an instance that is already wedged (e.g. stuck on a modal
    dialog with no RCL)."""
    existing = _list_t32_pids()
    if not existing:
        return
    log.info("Existing TRACE32 instance(s) found: %s - attempting graceful RCL shutdown first...",
             ", ".join(f"{n}(PID {p})" for p, n in existing))
    import socket
    try:
        with socket.create_connection(("localhost", CFG.rcl_port), timeout=2):
            pass  # RCL port is open - a clean QUIT is possible
    except OSError:
        log.warning("No RCL port on %s (instance wedged / no Remote API) - force-killing.",
                    CFG.rcl_port)
        _force_kill_trace32()
        return
    try:
        dbg = t32api.connect(node="localhost", port=CFG.rcl_port, timeout=15)
        graceful_shutdown(dbg, None)   # SYStem.Down + QUIT, then force-kills any survivor
    except Exception as e:  # noqa: BLE001
        log.warning("Graceful pre-launch shutdown failed (%s) - force-killing.", e)
        _force_kill_trace32()


def graceful_shutdown(dbg, powerview, rcl_timeout: int = 15):
    """PROPER power-off - the reliable way to release the USB PODBUS device. Sends
    (InterCom <slave> SYStem.Down, SYStem.Down, InterCom <slave> QUIT, QUIT) over RCL FIRST so
    the driver actually releases its device lock (force-kill alone does not), then force-kills
    only survivors. Runs in a daemon thread so a hung RCL connection cannot block forever."""
    alias = CFG.slave_alias
    if dbg is not None:
        done = threading.Event()

        def _worker():
            for cmd in (f"InterCom {alias} SYStem.Down", "SYStem.Down",
                        f"InterCom {alias} QUIT", "QUIT"):
                try:
                    dbg.cmd(cmd)
                except Exception:
                    pass  # QUIT tears down the socket; a hung connection may raise - expected
            done.set()

        log.info("Graceful shutdown: SYStem.Down (slave+master) + QUIT via RCL...")
        threading.Thread(target=_worker, daemon=True).start()
        if done.wait(rcl_timeout):
            log.info("Graceful RCL shutdown commands sent (USB released via SYStem.Down).")
        else:
            log.warning("Graceful shutdown did not complete within %ss (RCL likely hung) - "
                        "force-killing survivors.", rcl_timeout)
        try:
            dbg.disconnect()
        except Exception:
            pass

    for _ in range(20):  # up to ~10s for QUIT to close instances
        if not _list_t32_pids():
            log.info("TRACE32 exited cleanly; USB PODBUS device released properly.")
            return
        time.sleep(0.5)
    log.warning("TRACE32 still alive after graceful QUIT - force-killing survivor(s) as fallback.")
    _force_kill_trace32()


# ─────────────────────────────────────────────────────────
#  Launch + connect
# ─────────────────────────────────────────────────────────
def launch_trace32() -> pystart.PowerView:
    log.info("Configuring TRACE32 PowerView (variant=%s)...", CFG.variant)
    log.info("Ensuring any existing TRACE32 is cleanly shut down before launch...")
    _graceful_pre_launch_cleanup()
    pystart.defaults.system_path = CFG.system_path

    powerview = pystart.PowerView(pystart.USBConnection(), "t32marm")
    # A fresh, unique id per run avoids a stale OS-level lock tied to a fixed id string.
    unique = str(int(time.time()))
    powerview.title = f"TRACE32 PowerView - {CFG.variant} ({unique})"
    powerview.id = f"T32_{CFG.variant}_{unique}"
    # RCL must be enabled explicitly, else connect() gets "connection actively refused".
    powerview.add_interface(pystart.RCLInterface(port=CFG.rcl_port))
    # Only add an explicit InterComInterface if the user asked for one. The CMM's own
    # TargetSystem.NewInstance handles AMP; forcing IntercomInterface here caused
    # "InterCom name M4 already exists" and broke the slave spawn.
    if CFG.intercom_port is not None:
        powerview.add_interface(pystart.IntercomInterface(port=CFG.intercom_port))

    log.info("Starting TRACE32 PowerView...")
    catcher = _FatalLogCatcher()
    pystart_logger = logging.getLogger("lauterbach.trace32.pystart")
    prev_level = pystart_logger.level
    pystart_logger.setLevel(logging.DEBUG)
    pystart_logger.addHandler(catcher)

    # delay= (not timeout=) because the conan TRACE32 build may predate pystart's automatic
    # ready-event detection; we actively poll the RCL port instead of a blind sleep.
    powerview.start(delay=RCL_SPAWN_DELAY)
    port_open = _wait_for_rcl_port("localhost", CFG.rcl_port, RCL_TIMEOUT)

    try:
        if not port_open:
            proc = getattr(powerview, "_process", None)
            exit_code = proc.poll() if proc is not None else None
            fatal = catcher.fatal_lines or _detect_fatal_dialog_windows()
            if fatal:
                raise RuntimeError(
                    "TRACE32 failed to start - fatal error detected:\n  - "
                    + "\n  - ".join(dict.fromkeys(fatal))
                    + ("\nThis is the PODBUS 'device already used' lock: force-killing t32marm "
                       "frees the process but NOT the driver's device lock. A stale/leftover "
                       "instance held the probe. It has been cleaned; re-run to retry."
                       if any("already used" in f.lower() or "podbus" in f.lower() for f in fatal)
                       else ""))
            if exit_code is not None:
                raise RuntimeError(f"TRACE32 exited during startup with code {exit_code} "
                                   "(no RCL port). Check the probe/USB connection.")
            log.warning("RCL port %s not open after %ss and no fatal detected - proceeding; "
                        "connect_rcl() will retry.", CFG.rcl_port, RCL_TIMEOUT)
    finally:
        pystart_logger.removeHandler(catcher)
        pystart_logger.setLevel(prev_level)
    return powerview


def _wait_for_rcl_port(host: str, port: int, timeout: float) -> bool:
    """Poll until the RCL TCP port accepts a connection (PowerView up + Remote API listening)."""
    import socket
    start = time.perf_counter()
    last_report = 0.0
    while True:
        elapsed = time.perf_counter() - start
        try:
            with socket.create_connection((host, port), timeout=2):
                log.info("TRACE32 RCL port %s is open - PowerView ready after %ds.", port, int(elapsed))
                return True
        except OSError:
            pass
        if elapsed >= timeout:
            return False
        if elapsed - last_report >= 3:
            log.info("Waiting for TRACE32 to come up (RCL port %s)... %ds", port, int(elapsed))
            last_report = elapsed
        time.sleep(0.5)


def connect_rcl() -> t32api.Debugger:
    log.info("Connecting pyrcl on localhost:%s...", CFG.rcl_port)
    last_error = None
    for attempt in range(1 + RCL_CONNECT_RETRIES):
        try:
            dbg = t32api.connect(node="localhost", port=CFG.rcl_port, timeout=RCL_CMD_TIMEOUT)
            log.info("Connected to TRACE32. Software build: %s", dbg.fnc.software_build())
            return dbg
        except Exception as e:  # noqa: BLE001
            last_error = e
            log.warning("RCL connect attempt %d/%d failed: %s (retrying in %ss)",
                        attempt + 1, 1 + RCL_CONNECT_RETRIES, e, RCL_CONNECT_RETRY_DELAY)
            time.sleep(RCL_CONNECT_RETRY_DELAY)
    raise RuntimeError(f"Could not connect RCL on localhost:{CFG.rcl_port} after retries: {last_error}")


# ─────────────────────────────────────────────────────────
#  Status helpers - poll live state instead of idle-waiting
# ─────────────────────────────────────────────────────────
def _as_int(value) -> int:
    """Normalize an RCL return (bytes/bytearray little-endian, or int/str) to a plain int."""
    if isinstance(value, (bytes, bytearray)):
        return int.from_bytes(value, byteorder="little")
    return int(value)


def describe_state(dbg: t32api.Debugger) -> str:
    try:
        code = _as_int(dbg.get_state())
    except Exception as e:  # noqa: BLE001
        return f"unknown ({e})"
    return f"{T32_STATE_LABELS.get(code, 'unknown')} (code={code})"


def report_status(dbg: t32api.Debugger, context: str = "") -> str:
    state = describe_state(dbg)
    try:
        msg = dbg.get_message()
        msg_text = (msg.text or "").strip()
        is_error = bool(msg.type & T32_MSG_ERROR_BIT)
    except Exception:  # noqa: BLE001
        msg_text, is_error = "", False
    tag = f"[{context}] " if context else ""
    if msg_text:
        (log.error if is_error else log.info)("%sstatus: %s | TRACE32: %s", tag, state, msg_text)
    else:
        log.info("%sstatus: %s", tag, state)
    return state


def _check_errors(dbg: t32api.Debugger, context: str = ""):
    message = dbg.get_message()
    if message.text and message.type != 0:
        raise RuntimeError(f"TRACE32 error during [{context}]: {message.text} (type={message.type})")


# ─────────────────────────────────────────────────────────
#  Flash + AMP-attach (runs the project's own CMM with live progress)
# ─────────────────────────────────────────────────────────
class TargetAttachError(RuntimeError):
    """Raised when the debugger cannot bring the target core up (stuck 'system down')."""


def _welcome_dialog_watcher(stop_event: threading.Event, poll_s: float = 2.0):
    """Background loop that dismisses the 'Welcome to TRACE32!' dialog independently of the main
    RCL polling loop.

    WHY THIS RUNS ON A SEPARATE THREAD (bench-verified 2026-08-12): this dialog does NOT just sit
    there cosmetically - it BLOCKS TRACE32's own command/message processing, which in turn blocks
    RCL calls like dbg.get_message()/dbg.fnc() made from the SAME thread that would otherwise call
    _dismiss_welcome_dialog_windows(). Calling the dismiss check only *after* those blocking calls
    (as a plain step inside `_run_cmm_with_progress`'s loop) never runs, because the loop is
    already stuck on the RCL call from the same iteration - the dismiss step is unreachable. A
    dedicated thread keeps checking/dismissing independently of whatever the main thread is
    blocked on, so a SLAVE1 welcome dialog spawned mid-CMM (via TargetSystem.NewInstance) gets
    cleared before it can wedge the polling loop.
    """
    while not stop_event.is_set():
        try:
            _dismiss_welcome_dialog_windows()
        except Exception:
            pass
        stop_event.wait(poll_s)


def run_init_script(dbg: t32api.Debugger):
    """Run the project's flash/AMP-attach CMM (reset -> erase -> program SFLASH/HSM/FBL/App ->
    spawn + attach the CM4 slave). WARNING: this ERASES and REPROGRAMS flash."""
    log.info("Setting TRACE32 working directory: %s", CFG.cmm_cwd)
    dbg.cmd(f'CD "{CFG.cmm_cwd}"')

    log.info("Letting debug hardware settle for %ss before flashing...", POST_CONNECT_SETTLE)
    time.sleep(POST_CONNECT_SETTLE)
    _dismiss_welcome_dialog_windows()

    stop_watcher = threading.Event()
    watcher = threading.Thread(target=_welcome_dialog_watcher, args=(stop_watcher,), daemon=True)
    watcher.start()
    try:
        for attempt in range(1 + FLASH_ATTACH_RETRIES):
            try:
                _run_cmm_with_progress(dbg)
                return
            except TargetAttachError as e:
                if attempt >= FLASH_ATTACH_RETRIES:
                    raise RuntimeError(
                        f"{e}. The debugger could not bring the core up after "
                        f"{1 + FLASH_ATTACH_RETRIES} attempt(s) - check the target is POWERED and "
                        "KL15/ignition is ON in CANoe, and the probe is connected. No flashing done."
                    ) from None
                log.warning("%s - resetting and retrying flash (attempt %d/%d)...",
                            e, attempt + 2, 1 + FLASH_ATTACH_RETRIES)
                try:
                    dbg.cmd("SYStem.Down")
                    dbg.cmd(f"InterCom {CFG.slave_alias} SYStem.Down")
                except Exception:
                    pass
                time.sleep(POST_CONNECT_SETTLE)
    finally:
        stop_watcher.set()
        watcher.join(timeout=3)


def _run_cmm_with_progress(dbg: t32api.Debugger):
    """DO the CMM non-blocking and poll PRACTICE.SD() to completion, streaming live status and
    failing fast if the MASTER never leaves 'system down' (attach failed)."""
    log.info("Running project flash/AMP-attach CMM script: %s", CFG.cmm_script)
    stack_depth_pre = _as_int(dbg.fnc("PRACTICE.SD()"))
    dbg.cmd(f"DO {CFG.cmm_script}")
    start = time.perf_counter()
    last_report = 0.0
    while True:
        stack_depth = _as_int(dbg.fnc("PRACTICE.SD()"))
        if stack_depth < stack_depth_pre:
            raise RuntimeError("PRACTICE stack depth error during flash script")
        if stack_depth == stack_depth_pre:
            break  # finished

        msg = dbg.get_message()
        if msg.text and (msg.type & T32_MSG_ERROR_BIT):
            raise RuntimeError(f"TRACE32 error during flash: {msg.text.strip()}")

        elapsed = time.perf_counter() - start
        if elapsed > SYSTEM_UP_GRACE and _as_int(dbg.get_state()) == 0:
            raise TargetAttachError(
                f"Target did not attach: MASTER core still 'system down' after {int(elapsed)}s "
                f"(TRACE32: {(msg.text or '').strip() or 'no message'})")

        if elapsed - last_report >= FLASH_PROGRESS_INTERVAL:
            text = (msg.text or "").strip()
            log.info("[flash %3ds] state=%s%s", int(elapsed), describe_state(dbg),
                     f" | TRACE32: {text}" if text else " | working...")
            last_report = elapsed
            # NOTE: dialog dismissal for a mid-CMM SLAVE1 spawn is handled by the background
            # `_welcome_dialog_watcher` thread (see run_init_script) - NOT here. This point is
            # only ever reached after dbg.get_message() above already succeeded, i.e. AFTER the
            # dialog (if any) has already been dismissed - a same-thread call here would be a
            # no-op at best and unreachable at worst if a dialog appears mid-call.

        if elapsed > CMM_SCRIPT_TIMEOUT:
            raise TimeoutError(f"Flash script did not finish within {CMM_SCRIPT_TIMEOUT}s")
        time.sleep(0.2)

    _check_errors(dbg, "CMM init script")
    log.info("Init/flash script completed in %ds. Target state: %s",
             int(time.perf_counter() - start), describe_state(dbg))


# ─────────────────────────────────────────────────────────
#  AMP slave (application core) helpers + start
# ─────────────────────────────────────────────────────────
def slave_cmd(dbg: t32api.Debugger, command: str):
    dbg.cmd(f"InterCom {CFG.slave_alias} {command}")


def slave_present(dbg: t32api.Debugger) -> bool:
    return bool(dbg.fnc(f"INTERCOM.PING({CFG.slave_alias})"))


def wait_slave_ready(dbg: t32api.Debugger, timeout: float = SLAVE_READY_TIMEOUT) -> None:
    """Wait until the AMP slave is RESPONSIVE to InterCom (not just present) + settle, so the
    subsequent InterCom commands don't hit 'no response from InterCom'."""
    start = time.perf_counter()
    while True:
        if slave_present(dbg):
            time.sleep(SLAVE_READY_SETTLE)
            if slave_present(dbg):
                log.info("CM4 SLAVE1 (%s) is attached and responsive to InterCom.", CFG.slave_alias)
                return
        if time.perf_counter() - start > timeout:
            raise RuntimeError(
                f"CM4 SLAVE1 ({CFG.slave_alias}) not responsive to InterCom within {timeout}s. "
                "Check the CMM output / CANoe KL15 / target power.")
        time.sleep(0.5)


def slave_cmd_checked(dbg: t32api.Debugger, command: str, retries: int = 2) -> None:
    """Send an InterCom command and retry on the transient 'no response from InterCom'."""
    for attempt in range(1 + retries):
        slave_cmd(dbg, command)
        msg = dbg.get_message()
        text = (msg.text or "").strip()
        if "no response from InterCom" in text:
            log.warning("InterCom '%s' got 'no response' (attempt %d/%d) - waiting + retrying...",
                        command, attempt + 1, 1 + retries)
            wait_slave_ready(dbg)
            continue
        if text and (msg.type & T32_MSG_ERROR_BIT):
            raise RuntimeError(f"TRACE32 error on InterCom '{command}': {text}")
        return
    raise RuntimeError(f"InterCom '{command}' kept returning 'no response from InterCom'.")


def finish_startup(dbg: t32api.Debugger):
    """Confirm the slave attached, delete default post-flash breakpoints, and Go both cores."""
    if not slave_present(dbg):
        raise RuntimeError(
            f"CM4 SLAVE1 ({CFG.slave_alias}) did not attach - INTERCOM.PING is FALSE. "
            "Check the CMM output / CANoe KL15 / target power.")
    wait_slave_ready(dbg)

    log.info("Deleting default post-flash breakpoints on the CM4 slave...")
    for symbol in CFG.slave_breakpoints:
        slave_cmd_checked(dbg, f"Break.Delete {symbol}")

    log.info("Issuing Go on the CM4 slave (application core)...")
    slave_cmd_checked(dbg, "Go")
    log.info("CM4 application core is running.")

    # The CMM's own SYStem.Up already brings the MASTER (CM0+) to a running state during the
    # flash script (bench-verified 2026-08-12: STATE.RUN()/SYStem.UP() both TRUE right after the
    # CMM completes) - issuing another `Go` on an already-running master errors with
    # ('target running', ...), which _check_errors would otherwise treat as fatal. Only Go it if
    # it isn't already running.
    if _as_int(dbg.get_state()) == 3:
        log.info("MASTER core (CM0+) is already running (brought up by the CMM's SYStem.Up).")
    else:
        log.info("Issuing Go on the MASTER core (CM0+)...")
        dbg.cmd("Go")
        _check_errors(dbg, "Go (master)")
        log.info("MASTER core (CM0+) is running.")

    report_status(dbg, "startup complete")


# ─────────────────────────────────────────────────────────
#  Interactive debug ops on the app core (breakpoints / read / write)
# ─────────────────────────────────────────────────────────
def _load_app_symbols_on_master(dbg: t32api.Debugger):
    """Load the app ELF's SYMBOLS ONLY (no code, no registers) into the MASTER instance so app
    symbols resolve for variable read/write. The CM0+ master shares the physical memory bus with
    the CM4 app core, so reading/writing a resolved app-variable address works from the master.
    Breakpoints that must halt CM4 execution are still set on the app core via InterCom."""
    log.info("Loading app symbols on master for variable access: %s", CFG.abs_file)
    dbg.cmd(f'Data.LOAD.Elf "{CFG.abs_file}" /NoCODE /NoRegister /NoClear')


def _slave_print_capture(dbg: t32api.Debugger, print_stmts: list[str]) -> list[str]:
    """Run one or more ``PRINT "...",<expr>`` statements on the CM4 slave (via InterCom) with
    their output redirected to a scratch file via ``AREA.OPEN "<file>" /Create`` (the only valid
    single-argument form on this TRACE32 build - see module notes), then read the file back.
    ``PRINT`` is a genuine text-stream command (unlike the GUI-window ``Frame`` command), so its
    output reliably flows through AREA redirection."""
    tmp = Path(tempfile.gettempdir()) / f"t32py_print_{CFG.variant}_{int(time.time() * 1000)}.txt"
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass
    try:
        slave_cmd_checked(dbg, f'AREA.OPEN "{tmp.as_posix()}" /Create')
        for stmt in print_stmts:
            slave_cmd_checked(dbg, stmt)
    finally:
        try:
            slave_cmd(dbg, "AREA.CLOSE")
        except Exception:  # noqa: BLE001
            pass
    for _ in range(10):  # allow the AREA file write to flush to disk
        if tmp.exists() and tmp.stat().st_size > 0:
            break
        time.sleep(0.2)
    if not tmp.exists():
        return []
    lines = [ln.rstrip() for ln in tmp.read_text(errors="replace").splitlines() if ln.strip()]
    try:
        tmp.unlink()
    except OSError:
        pass
    return lines


def _slave_halted(dbg: t32api.Debugger) -> bool:
    """True if the CM4 app core is currently halted (STATE.RUN() == FALSE), False if running."""
    lines = _slave_print_capture(dbg, ['PRINT "STATE=",STATE.RUN()'])
    text = lines[0] if lines else ""
    return "FALSE" in text.upper()


def get_call_stack(dbg: t32api.Debugger, max_frames: int = STACK_MAX_FRAMES,
                    timeout: float = STACK_CAPTURE_TIMEOUT) -> list[str]:
    """Capture the CM4 app-core call stack (current function + immediate caller) over the
    existing InterCom(<slave_alias>) connection.

    Bench-verified findings (2026-08-07) that shaped this implementation:
      - ``AREA.OPEN <name> "<file>" /Create`` (name + file together) is a SYNTAX ERROR on this
        TRACE32 build ("no more arguments expected") - only ``AREA.OPEN "<file>" /Create``
        (unnamed file-redirect area) is valid.
      - ``Frame.List`` / bare ``Frame`` are GUI *window* commands - they never flow through
        AREA text redirection (file always comes back empty), so they cannot be used headlessly.
      - The high-level ``FRAME.COUNT()`` / ``FRAME.FUNCTION(n)`` / ``FRAME.ADDRESS(n)`` /
        ``ADDRESS.FUNCTION(addr)`` PRACTICE functions do **not exist** on this TRACE32 build
        ("no function ... exists") - likely no HLL stack-unwind feature/license here.
      - What **does** work (all confirmed via ``PRINT "...",<expr>`` redirected through
        ``AREA.OPEN``): ``Register(PC)``, ``Register(LR)``, ``Register(SP)`` for the raw
        register values, and ``sYmbol.NAME(P:<addr>)`` to resolve an address to a function
        name. This gives a genuine (if shallow: current frame + immediate caller, not a full
        multi-level unwind - this build has no generic frame-walker) call stack: PC resolves
        the currently-executing function, LR resolves its caller.
    Retries for ``timeout`` seconds if the app core hasn't halted yet (e.g. the breakpoint has
    not been hit), using ``STATE.RUN()`` to detect halted vs. still running.
    """
    start = time.perf_counter()
    while not _slave_halted(dbg):
        if time.perf_counter() - start > timeout:
            raise RuntimeError(
                f"Call stack unavailable after {timeout}s - the app core is still running "
                "(breakpoint not hit yet / core not halted).")
        time.sleep(STACK_CAPTURE_POLL)

    regs = _slave_print_capture(dbg, [
        'PRINT "PC=",Register(PC)',
        'PRINT "LR=",Register(LR)',
        'PRINT "SP=",Register(SP)',
    ])
    values = {}
    for line in regs:
        if "=" in line:
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip()

    frames: list[str] = []
    pc, lr, sp = values.get("PC"), values.get("LR"), values.get("SP")
    if sp:
        frames.append(f"SP=0x{sp}")
    if pc:
        sym = _slave_print_capture(dbg, [f'PRINT "SYM=",sYmbol.NAME(P:0x{pc})'])
        name = sym[0].split("=", 1)[1].strip() if sym and "=" in sym[0] else "<unresolved>"
        frames.append(f"#0 (current) PC=0x{pc}  {name}")
    if lr:
        sym = _slave_print_capture(dbg, [f'PRINT "SYM=",sYmbol.NAME(P:0x{lr})'])
        name = sym[0].split("=", 1)[1].strip() if sym and "=" in sym[0] else "<unresolved>"
        frames.append(f"#1 (caller)  LR=0x{lr}  {name}")

    if not frames:
        raise RuntimeError("Could not read PC/LR/SP registers from the app core.")
    return frames[:max_frames] if max_frames else frames


def run_debug_ops(dbg: t32api.Debugger, set_break, read, write, stack: bool = False,
                   stack_frames: int = STACK_MAX_FRAMES):
    """Demonstrate/apply breakpoints + call stack + variable read/write after cores are started."""
    # 1) Breakpoints on the app core (CM4 SLAVE1) via InterCom.
    for sym in set_break:
        log.info("Setting breakpoint on app core (%s): Break.Set %s", CFG.slave_alias, sym)
        slave_cmd_checked(dbg, f"Break.Set {sym}")
        log.info("Breakpoint set at %s (app core). It halts CM4 when execution reaches %s.", sym, sym)

    # 2) Call stack, once the app core halts (e.g. at the breakpoint just armed above).
    if stack:
        log.info("Waiting up to %ss for the app core to halt so the call stack can be read...",
                 STACK_CAPTURE_TIMEOUT)
        try:
            frames = get_call_stack(dbg, max_frames=stack_frames)
            log.info("Call stack (%d frame(s), app core %s):", len(frames), CFG.slave_alias)
            for line in frames:
                log.info("  %s", line)
        except Exception as e:  # noqa: BLE001
            log.error("Call stack capture failed: %s", e)

    # 3) Reads/writes need the app symbols resolvable on the master.
    if read or write:
        _load_app_symbols_on_master(dbg)

    for var in read:
        try:
            val = dbg.fnc(f"Var.VALUE({var})")
            log.info("READ  %s = %s", var, val)
        except Exception as e:  # noqa: BLE001
            log.error("READ  %s failed: %s", var, e)

    for wr in write:
        if "=" not in wr:
            log.error("--write expects VAR=VAL, got %r", wr)
            continue
        var, val = (s.strip() for s in wr.split("=", 1))
        try:
            # Numeric literal, no spaces around '=' (symbolic/spaced values silently fail).
            dbg.cmd(f"Var.Set {var}={val}")
            back = dbg.fnc(f"Var.VALUE({var})")
            log.info("WRITE %s=%s -> read back %s", var, val, back)
        except Exception as e:  # noqa: BLE001
            log.error("WRITE %s=%s failed: %s", var, val, e)


# ─────────────────────────────────────────────────────────
#  Debug Test Case (DTC) scripts on the app core
# ─────────────────────────────────────────────────────────
_DTC_END_RE = re.compile(r"DTC\|[A-Za-z0-9_\-]+\|END\b")
_DTC_ABORT_RE = re.compile(r"DTC\|[A-Za-z0-9_\-]+\|ABORT\b")


def run_app_cmm(dbg: t32api.Debugger, cmm: str, timeout: float) -> int:
    """DO a dtc_tool.py-compiled ``.cmm`` on the CM4 app core (via InterCom) and wait for its
    ``DTC|<id>|END`` / ``DTC|<id>|ABORT`` marker in the AREA log the script itself opens.

    Polling the log file (instead of trusting InterCom to block) works whether the remote ``DO``
    returns immediately or only after the script ends. Returns 0 = END seen, 4 = ABORT seen,
    5 = timeout (the remote PRACTICE script is then stopped with ``END``)."""
    cmm_path = Path(cmm).resolve()
    if not cmm_path.exists():
        log.error("--do-app: script not found: %s", cmm_path)
        return 4
    m = re.search(r'AREA\.OPEN\s+"([^"]+)"', cmm_path.read_text(errors="replace"))
    if not m:
        log.error("--do-app: %s has no AREA.OPEN \"<log>\" line - compile it with dtc_tool.py", cmm_path)
        return 4
    log_path = Path(m.group(1))
    try:
        log_path.unlink()
    except FileNotFoundError:
        pass

    wait_slave_ready(dbg)
    log.info("DTC: DO %s on app core (%s); log %s; timeout %ss", cmm_path.name, CFG.slave_alias,
             log_path, int(timeout))
    slave_cmd_checked(dbg, f'DO "{cmm_path.as_posix()}"')

    start = time.perf_counter()
    rc = 5
    while time.perf_counter() - start < timeout:
        if log_path.exists():
            text = log_path.read_text(errors="replace")
            if _DTC_ABORT_RE.search(text):
                rc = 4
                break
            if _DTC_END_RE.search(text):
                rc = 0
                break
        time.sleep(1.0)
    if rc == 5:
        log.error("DTC: %s did not finish within %ss - stopping the PRACTICE script.",
                  cmm_path.name, int(timeout))
        for cmd in ("END", "AREA.CLOSE"):
            try:
                slave_cmd(dbg, cmd)
            except Exception:  # noqa: BLE001
                pass
    for line in (log_path.read_text(errors="replace").splitlines() if log_path.exists() else []):
        if line.strip():
            log.info("  %s", line.rstrip())
    log.info("DTC: %s -> %s (%.0fs)", cmm_path.name, {0: "END", 4: "ABORT", 5: "TIMEOUT"}[rc],
             time.perf_counter() - start)
    return rc


def run_dtc_scripts(dbg: t32api.Debugger, scripts: list[str], timeout: float) -> int:
    worst = 0
    for cmm in scripts:
        worst = max(worst, run_app_cmm(dbg, cmm, timeout))
    return worst


# ─────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────
def main(argv=None) -> int:
    global CFG
    parser = argparse.ArgumentParser(description="Launch + flash + AMP-start TRACE32 via pystart/RCL.")
    parser.add_argument("--variant", help="Build variant (overrides $LT_VARIANT).")
    parser.add_argument("--attach", action="store_true",
                        help="Attach to an ALREADY-RUNNING TRACE32/RCL session on localhost:"
                             "$T32PY_PORT (default 20000) instead of launching/flashing. Use this "
                             "for a lightweight, no-reflash status check or read/write/breakpoint "
                             "op after a previous keep-open run (the default) - see the "
                             "'Programmatic status checks (preferred over screenshots)' section in "
                             "SKILL.md. Leaves TRACE32 running; does not power off.")
    parser.add_argument("--connect-only", action="store_true",
                        help="Launch + connect + report status, then shut down (no flashing).")
    parser.add_argument("--no-start", action="store_true",
                        help="Launch + flash, but do not Go the cores.")
    parser.add_argument("--shutdown", action="store_true",
                        help="On success, perform a proper SYStem.Down + QUIT power-off instead of "
                             "leaving TRACE32 open. DEFAULT is to KEEP the session open (detached) "
                             "so you can debug (breakpoints, read/write). The next launch cleanly "
                             "QUITs any left-open instance first, so the USB device is still released "
                             "properly. --connect-only always shuts down.")
    parser.add_argument("--set-break", metavar="SYM", action="append", default=[],
                        help="After start, set a breakpoint on the app core at SYM (repeatable).")
    parser.add_argument("--read", metavar="VAR", action="append", default=[],
                        help="After start, read app variable/expression VAR (repeatable).")
    parser.add_argument("--write", metavar="VAR=VAL", action="append", default=[],
                        help="After start, write VAL to app variable VAR then read it back (repeatable).")
    parser.add_argument("--stack", action="store_true",
                        help="After setting breakpoints, wait for the app core to halt and report "
                             "its call stack (Frame.List over the existing InterCom connection).")
    parser.add_argument("--stack-frames", type=int, default=STACK_MAX_FRAMES, metavar="N",
                        help=f"Max call-stack frames to report (default {STACK_MAX_FRAMES}).")
    parser.add_argument("--do-app", metavar="CMM", action="append", default=[],
                        help="After start/attach, run a Debug Test Case .cmm (compiled by the "
                             "debug-test-cases skill's dtc_tool.py) on the app core and wait for "
                             "its DTC END/ABORT marker (repeatable, runs in order). Exit code 4 if "
                             "any script aborted or timed out; the session is still kept open.")
    parser.add_argument("--do-timeout", type=float, default=300.0, metavar="S",
                        help="Per-script timeout for --do-app in seconds (default 300; use the "
                             "timeout_s from the dtc manifest.json).")
    args = parser.parse_args(argv)

    try:
        CFG = RuntimeConfig(variant=args.variant)
    except ConfigError as e:
        log.error("Config error: %s", e)
        return 3

    powerview = None
    dbg = None
    exit_code = 0
    dtc_rc = 0  # Debug Test Case outcome; a failed test must not trigger a power-off

    if args.attach:
        # No launch/flash - just connect to whatever's already listening on the RCL port (e.g.
        # a session left open by a previous default keep-open run). Fully separate from the
        # launch/flash try/except/finally below so its error handling and "keep-open" messaging
        # don't get mixed up with the flash flow's semantics.
        try:
            dbg = connect_rcl()
            report_status(dbg, "attach")
            if args.set_break or args.read or args.write or args.stack:
                run_debug_ops(dbg, args.set_break, args.read, args.write, args.stack, args.stack_frames)
            if args.do_app:
                return 4 if run_dtc_scripts(dbg, args.do_app, args.do_timeout) else 0
            return 0
        except Exception as e:  # noqa: BLE001
            log.error("Fatal error: %s", e)
            return 2
        finally:
            if dbg:
                try:
                    dbg.disconnect()
                except Exception:
                    pass

    try:
        try:
            powerview = launch_trace32()
        except RuntimeError as e:
            # A STUCK PODBUS "device already used" lock can survive with no live instance to
            # QUIT (a prior force-kill freed the process but not the driver claim). Reset the
            # USB device (software power-cycle) and retry the launch ONCE before giving up.
            if ("already used" in str(e).lower() or "podbus" in str(e).lower()) and _reset_podbus_usb():
                log.info("Retrying launch after PODBUS USB reset...")
                powerview = launch_trace32()
            else:
                raise
        dbg = connect_rcl()
        if args.connect_only:
            report_status(dbg, "connect-only")
        else:
            run_init_script(dbg)          # WARNING: erases + reprograms flash
            if not args.no_start:
                finish_startup(dbg)
            else:
                report_status(dbg, "flash complete (cores not started)")
            # Optional interactive debug ops on the app core (breakpoints / call stack / read / write).
            if args.set_break or args.read or args.write or args.stack:
                run_debug_ops(dbg, args.set_break, args.read, args.write, args.stack, args.stack_frames)
            if args.do_app:
                dtc_rc = run_dtc_scripts(dbg, args.do_app, args.do_timeout)
        exit_code = 0
    except Exception as e:  # noqa: BLE001
        log.error("Fatal error: %s", e)
        exit_code = 2
    finally:
        # DEFAULT is to KEEP the session open (detached) so you can debug. Only shut down on
        # --connect-only, on --shutdown, or on any failure. Leaving it open is safe because the
        # NEXT launch's pre-launch cleanup gracefully QUITs it (releasing the PODBUS lock);
        # only a force-kill would strand the lock.
        keep_open = (exit_code == 0 and not args.connect_only and not args.shutdown)
        if keep_open:
            if dbg:
                try:
                    dbg.disconnect()
                    log.info("RCL automation link disconnected (TRACE32 keeps running).")
                except Exception:
                    pass
            log.info("Done - TRACE32 left running with both cores started (default keep-open). "
                     "Re-run to reflash (it cleanly QUITs this instance first), pass --shutdown "
                     "to power off now, or close the GUI (X) yourself.")
        else:
            # --connect-only / --shutdown / any failure: power off PROPERLY (SYStem.Down + QUIT)
            # so the PODBUS driver releases the USB device (force-kill alone does NOT).
            log.info("Performing proper TRACE32 power-off (SYStem.Down + QUIT)...")
            graceful_shutdown(dbg, powerview)
            log.info("TRACE32 shut down; USB device released.")
    if exit_code == 0 and dtc_rc:
        return 4
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
