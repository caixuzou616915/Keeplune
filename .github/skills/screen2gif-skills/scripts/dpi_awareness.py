"""Best-effort Windows per-monitor DPI awareness.

Root cause this fixes: on Windows, if the process is *not* marked
DPI-aware, APIs that report monitor rectangles (``GetMonitorInfoW``,
``EnumDisplayMonitors``) return DPI-*virtualized* (scaled) coordinates
instead of true physical-pixel coordinates for any monitor whose scaling
differs from the process's assumed 96-DPI baseline. ``PIL.ImageGrab.grab()``
still captures raw physical pixels regardless of process DPI awareness, so a
capture ``bbox`` built from those virtualized rectangles only covers the
top-left *fraction* of a scaled monitor -- this is the actual cause of a
recording looking "not full screen" on a monitor with DPI scaling other than
100%, while an unscaled (100%) monitor captures correctly.

Calling this before any monitor enumeration or screen capture makes
Windows report true physical-pixel monitor rectangles unconditionally, so
the capture bbox always matches what ``ImageGrab.grab()`` actually grabs.
"""

from __future__ import annotations

import sys

_enabled = False


def ensure_dpi_awareness() -> None:
    """Set per-monitor DPI awareness for this process, once. No-op off Windows.

    Safe to call multiple times (including from multiple modules) and safe
    if awareness was already set elsewhere (e.g. by Tk, or a previous call):
    failures are swallowed since we only need *some* non-unaware mode active
    before the first monitor-rectangle query.
    """
    global _enabled
    if _enabled or sys.platform != "win32":
        return
    _enabled = True

    import ctypes

    # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Windows 10 1703+): best option,
    # correctly handles mixed-DPI multi-monitor setups.
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass

    # PROCESS_PER_MONITOR_DPI_AWARE (Windows 8.1+).
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass

    # Fallback: system DPI aware only (Vista+). Better than nothing on very
    # old Windows, though mixed-DPI multi-monitor setups may still be off.
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass
