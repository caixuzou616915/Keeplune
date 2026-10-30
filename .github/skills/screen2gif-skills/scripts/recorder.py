"""Screen capture engine.

Captures full-screen screenshots at a fixed interval on a background thread
and stores each frame as a PNG file inside a temporary directory. The frames
are later assembled into a GIF by ``gif_writer.build_gif``.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time

from PIL import ImageGrab


class ScreenRecorder:
    """Captures the screen on a timer until stopped."""

    def __init__(
        self,
        interval_ms: int,
        bbox: tuple[int, int, int, int] | None = None,
        all_screens: bool = False,
    ):
        """Create a recorder.

        Args:
            interval_ms: Milliseconds between captured frames.
            bbox: Region to capture, in virtual-screen coordinates (see
                ``monitors.MonitorInfo.bbox``). ``None`` captures the whole
                screen (primary monitor only, unless ``all_screens=True``).
            all_screens: Capture every monitor combined instead of just the
                primary one. Required (Windows-only) when targeting a
                non-primary monitor's ``bbox``, since its coordinates may be
                negative relative to the primary display.
        """
        if interval_ms <= 0:
            raise ValueError("interval_ms must be positive")
        self.interval_ms = interval_ms
        self.bbox = bbox
        self.all_screens = all_screens
        self.frames_dir = tempfile.mkdtemp(prefix="screen2gif_")
        self.frame_count = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_time: float | None = None
        self._end_time: float | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._start_time = time.perf_counter()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        if self._end_time is None:
            self._end_time = time.perf_counter()

    def cleanup(self) -> None:
        shutil.rmtree(self.frames_dir, ignore_errors=True)

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        end = self._end_time if self._end_time is not None else time.perf_counter()
        return end - self._start_time

    def _run(self) -> None:
        interval = self.interval_ms / 1000.0
        next_tick = time.perf_counter()
        while not self._stop_event.is_set():
            try:
                image = ImageGrab.grab(bbox=self.bbox, all_screens=self.all_screens)
                path = os.path.join(self.frames_dir, f"frame_{self.frame_count:06d}.png")
                image.save(path)
                self.frame_count += 1
            except Exception:
                # Skip a failed frame (e.g. transient grab error) and keep going.
                pass
            next_tick += interval
            remaining = next_tick - time.perf_counter()
            if remaining > 0:
                self._stop_event.wait(remaining)
            else:
                next_tick = time.perf_counter()
        self._end_time = time.perf_counter()
