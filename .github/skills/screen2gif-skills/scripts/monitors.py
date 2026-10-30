"""Multi-monitor enumeration helpers.

Lets the recorder target a single physical monitor (instead of always
capturing the primary display) with no extra dependency: monitor rectangles
are read via the Win32 ``EnumDisplayMonitors`` API through ``ctypes`` on
Windows. Other platforms fall back to a single "entire screen" entry, since
Pillow's ``ImageGrab`` cannot enumerate individual monitors outside Windows.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class MonitorInfo:
    """A single physical monitor's bounding rectangle, in virtual-screen coordinates."""

    index: int
    name: str
    left: int
    top: int
    right: int
    bottom: int
    is_primary: bool

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    def label(self) -> str:
        primary = " (primary)" if self.is_primary else ""
        return f"[{self.index}] {self.name} {self.width}x{self.height}{primary}"


def list_monitors() -> list[MonitorInfo]:
    """Return every physical monitor, in stable OS enumeration order."""
    if sys.platform == "win32":
        monitors = _list_monitors_windows()
        if monitors:
            return monitors
    return [MonitorInfo(index=0, name="Entire screen", left=0, top=0, right=0, bottom=0, is_primary=True)]


def _list_monitors_windows() -> list[MonitorInfo]:
    import ctypes
    from ctypes import wintypes

    from dpi_awareness import ensure_dpi_awareness

    # Must happen before GetMonitorInfoW/EnumDisplayMonitors below, otherwise
    # a DPI-unaware process gets scaled (virtualized) monitor rectangles that
    # don't match the physical pixels ImageGrab.grab() actually captures --
    # see dpi_awareness.py for the full explanation.
    ensure_dpi_awareness()

    user32 = ctypes.windll.user32
    MONITORINFOF_PRIMARY = 0x1

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    monitors: list[MonitorInfo] = []
    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(RECT), ctypes.c_double
    )

    def _callback(hmonitor, hdc, lprect, lparam):  # noqa: ANN001 - fixed Win32 callback signature
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            rect = info.rcMonitor
            monitors.append(
                MonitorInfo(
                    index=len(monitors),
                    name=info.szDevice or f"Monitor {len(monitors)}",
                    left=rect.left,
                    top=rect.top,
                    right=rect.right,
                    bottom=rect.bottom,
                    is_primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                )
            )
        return 1

    callback = MonitorEnumProc(_callback)
    user32.EnumDisplayMonitors(0, 0, callback, 0)
    return monitors


def resolve_monitor_selection(
    monitor: str | None, monitors: list[MonitorInfo] | None = None
) -> tuple[tuple[int, int, int, int] | None, bool]:
    """Resolve a ``--monitor`` value to an ``ImageGrab.grab()`` bbox/all_screens pair.

    Args:
        monitor: ``None`` (legacy default: whatever ``ImageGrab.grab()`` alone
            captures, i.e. the primary monitor), ``"all"`` (every monitor
            combined into one wide image), ``"primary"``, or a monitor index
            as a string (see ``list_monitors()``).
        monitors: Pre-fetched monitor list (avoids re-enumerating); fetched
            lazily if omitted.

    Returns:
        ``(bbox, all_screens)`` ready to pass straight to
        ``PIL.ImageGrab.grab(bbox=bbox, all_screens=all_screens)``.
    """
    if monitor is None:
        return None, False

    normalized = monitor.strip().lower()
    if normalized == "all":
        return None, True

    monitors = monitors if monitors is not None else list_monitors()
    if not monitors:
        raise ValueError("No monitors were detected.")

    if normalized == "primary":
        for candidate in monitors:
            if candidate.is_primary:
                return candidate.bbox, True
        return monitors[0].bbox, True

    try:
        idx = int(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid --monitor value: {monitor!r} (use 'all', 'primary', or an index)") from exc
    if idx < 0 or idx >= len(monitors):
        raise ValueError(f"Monitor index {idx} out of range (0..{len(monitors) - 1})")
    return monitors[idx].bbox, True
