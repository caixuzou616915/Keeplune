"""Screen2Gif: a small Tkinter desktop app to record the screen and export a GIF.

Features:
- Configurable capture frequency (screenshot interval in milliseconds).
- Configurable playback speed-up: either a direct multiplier (e.g. 3x) or a
  target playback duration (e.g. "play my 60s recording back in 20s").
- Optional output width to keep the resulting GIF file size reasonable.

Run with:  python main.py
"""

from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from dpi_awareness import ensure_dpi_awareness

# Must happen before any monitor enumeration/screen capture (and before the
# Tk root is created) so monitor rectangles are reported in true physical
# pixels -- see dpi_awareness.py. Safe to call again from monitors.py.
ensure_dpi_awareness()

from file_utils import open_with_default_app
from gif_writer import build_gif
from monitors import list_monitors, resolve_monitor_selection
from recorder import ScreenRecorder
from video_writer import build_video

DEFAULT_INTERVAL_MS = 1000
DEFAULT_OUTPUT_WIDTH = 1920
PREVIEW_MAX_SIZE = (480, 270)

FORMAT_EXTENSIONS = {"GIF": ".gif", "MP4": ".mp4", "WebM": ".webm"}
FORMAT_FILETYPES = {
    "GIF": [("GIF image", "*.gif")],
    "MP4": [("MP4 video", "*.mp4")],
    "WebM": [("WebM video", "*.webm")],
}


class TrimDialog(tk.Toplevel):
    """Modal dialog to preview captured frames and pick a start/end trim range."""

    def __init__(
        self,
        parent: tk.Misc,
        frames_dir: str,
        frame_count: int,
        interval_ms: int,
        initial_start: float = 0.0,
        initial_end: float | None = None,
    ):
        super().__init__(parent)
        self.title("Preview & Trim")
        self.resizable(False, False)
        self.frames_dir = frames_dir
        self.frame_count = frame_count
        self.interval_ms = interval_ms
        self.total_duration = (frame_count - 1) * interval_ms / 1000.0 if frame_count > 1 else 0.0
        self.result: tuple[float, float] | None = None
        self._photo: ImageTk.PhotoImage | None = None

        self.start_var = tk.StringVar(value=f"{initial_start:0.1f}")
        self.end_var = tk.StringVar(value=f"{(initial_end if initial_end is not None else self.total_duration):0.1f}")
        self.preview_index = 0

        self._build_widgets()
        self._show_frame(0)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _frame_path(self, index: int) -> str:
        index = max(0, min(index, self.frame_count - 1))
        return os.path.join(self.frames_dir, f"frame_{index:06d}.png")

    def _build_widgets(self) -> None:
        pad = {"padx": 8, "pady": 6}

        self.preview_label = ttk.Label(self)
        self.preview_label.grid(row=0, column=0, columnspan=3, **pad)

        ttk.Label(self, text="Scrub preview:").grid(row=1, column=0, sticky="w", **pad)
        self.scrub_scale = ttk.Scale(
            self,
            from_=0,
            to=max(self.frame_count - 1, 0),
            orient="horizontal",
            command=self._on_scrub,
            length=360,
        )
        self.scrub_scale.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(self, text="Start (s):").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.start_var, width=10).grid(row=2, column=1, sticky="w", **pad)
        ttk.Button(self, text="Set = preview", command=self._set_start_from_preview).grid(row=2, column=2, **pad)

        ttk.Label(self, text="End (s):").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.end_var, width=10).grid(row=3, column=1, sticky="w", **pad)
        ttk.Button(self, text="Set = preview", command=self._set_end_from_preview).grid(row=3, column=2, **pad)

        ttk.Label(self, text=f"Full recording length: {self.total_duration:0.1f}s").grid(
            row=4, column=0, columnspan=3, sticky="w", padx=8
        )

        buttons = ttk.Frame(self)
        buttons.grid(row=5, column=0, columnspan=3, pady=(4, 8))
        ttk.Button(buttons, text="Use Full Recording", command=self._use_full).grid(row=0, column=0, padx=6)
        ttk.Button(buttons, text="OK", command=self._on_ok).grid(row=0, column=1, padx=6)
        ttk.Button(buttons, text="Cancel", command=self._on_cancel).grid(row=0, column=2, padx=6)

    def _on_scrub(self, value: str) -> None:
        self.preview_index = int(float(value))
        self._show_frame(self.preview_index)

    def _show_frame(self, index: int) -> None:
        try:
            with Image.open(self._frame_path(index)) as opened:
                image = opened.copy()
            image.thumbnail(PREVIEW_MAX_SIZE)
            self._photo = ImageTk.PhotoImage(image)
            self.preview_label.configure(image=self._photo)
        except OSError:
            pass

    def _index_to_seconds(self, index: int) -> float:
        return index * self.interval_ms / 1000.0

    def _set_start_from_preview(self) -> None:
        self.start_var.set(f"{self._index_to_seconds(self.preview_index):0.1f}")

    def _set_end_from_preview(self) -> None:
        self.end_var.set(f"{self._index_to_seconds(self.preview_index):0.1f}")

    def _use_full(self) -> None:
        self.start_var.set("0.0")
        self.end_var.set(f"{self.total_duration:0.1f}")

    def _on_ok(self) -> None:
        try:
            start = float(self.start_var.get())
            end = float(self.end_var.get())
        except ValueError:
            messagebox.showerror("Invalid range", "Start/End must be numbers.", parent=self)
            return
        if start < 0 or end > self.total_duration + 1e-6 or start >= end:
            messagebox.showerror(
                "Invalid range",
                f"Start must be >= 0, End must be <= {self.total_duration:0.1f}s, and Start < End.",
                parent=self,
            )
            return
        self.result = (start, end)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


class Screen2GifApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Screen2Gif")
        self.root.columnconfigure(0, weight=1)

        self.recorder: ScreenRecorder | None = None
        self._ui_queue: "queue.Queue[tuple]" = queue.Queue()
        self._tick_job = None
        self.last_output_path: str | None = None
        self._export_in_progress = False
        self.trim_start_s = 0.0
        self.trim_end_s: float | None = None

        self._build_widgets()
        self._lock_min_window_size()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _lock_min_window_size(self) -> None:
        """Keep the window resizable but never smaller than its content.

        Moving the window to a monitor with a different DPI makes Windows
        rescale the window frame while Tk keeps the widget pixel sizes, which
        used to shrink/clip the window (and it was non-resizable, so it could
        not be expanded). Enforce a minimum size and restore it on shrink.
        """
        self.root.update_idletasks()
        self._min_w = self.root.winfo_reqwidth()
        self._min_h = self.root.winfo_reqheight()
        self.root.minsize(self._min_w, self._min_h)
        self.root.resizable(True, True)
        self.root.bind("<Configure>", self._on_root_configure)

    def _on_root_configure(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        if event.width < self._min_w or event.height < self._min_h:
            self.root.after_idle(self._restore_min_size)

    def _restore_min_size(self) -> None:
        width = max(self.root.winfo_width(), self._min_w)
        height = max(self.root.winfo_height(), self._min_h)
        if (width, height) != (self.root.winfo_width(), self.root.winfo_height()):
            self.root.geometry(f"{width}x{height}")

    # ------------------------------------------------------------------ UI
    def _build_widgets(self) -> None:
        pad = {"padx": 8, "pady": 6}

        settings = ttk.LabelFrame(self.root, text="Capture settings")
        settings.grid(row=0, column=0, sticky="ew", **pad)

        ttk.Label(settings, text="Capture every (ms):").grid(row=0, column=0, sticky="w", **pad)
        self.interval_var = tk.StringVar(value=str(DEFAULT_INTERVAL_MS))
        ttk.Entry(settings, textvariable=self.interval_var, width=10).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(settings, text="Output width px (blank = original):").grid(row=1, column=0, sticky="w", **pad)
        self.width_var = tk.StringVar(value=str(DEFAULT_OUTPUT_WIDTH))
        ttk.Entry(settings, textvariable=self.width_var, width=10).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(settings, text="Monitor to record:").grid(row=2, column=0, sticky="w", **pad)
        self.monitors = list_monitors()
        monitor_choices = ["All screens (combined)"] + [monitor.label() for monitor in self.monitors]
        self.monitor_var = tk.StringVar(value=monitor_choices[1] if len(monitor_choices) > 1 else monitor_choices[0])
        self.monitor_combo = ttk.Combobox(
            settings, textvariable=self.monitor_var, values=monitor_choices, state="readonly", width=32
        )
        self.monitor_combo.grid(row=2, column=1, sticky="w", **pad)

        speed = ttk.LabelFrame(self.root, text="Playback speed-up")
        speed.grid(row=1, column=0, sticky="ew", **pad)

        self.speed_mode = tk.StringVar(value="multiplier")
        ttk.Radiobutton(
            speed, text="Speed multiplier (x)", variable=self.speed_mode, value="multiplier"
        ).grid(row=0, column=0, sticky="w", **pad)
        self.multiplier_var = tk.StringVar(value="1.0")
        ttk.Entry(speed, textvariable=self.multiplier_var, width=10).grid(row=0, column=1, sticky="w", **pad)

        ttk.Radiobutton(
            speed, text="Target playback duration (s)", variable=self.speed_mode, value="duration"
        ).grid(row=1, column=0, sticky="w", **pad)
        self.target_duration_var = tk.StringVar(value="20")
        ttk.Entry(speed, textvariable=self.target_duration_var, width=10).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(speed, text="e.g. play a 60s recording back in 20s").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8
        )

        self.reduce_size_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            speed,
            text="Reduce file size by dropping frames (choppier motion)",
            variable=self.reduce_size_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        output = ttk.LabelFrame(self.root, text="Output")
        output.grid(row=2, column=0, sticky="ew", **pad)

        ttk.Label(output, text="Format:").grid(row=0, column=0, sticky="w", **pad)
        self.format_var = tk.StringVar(value="WebM")
        self.format_combo = ttk.Combobox(
            output, textvariable=self.format_var, values=list(FORMAT_EXTENSIONS), state="readonly", width=8
        )
        self.format_combo.grid(row=0, column=1, sticky="w", **pad)
        self.format_combo.bind("<<ComboboxSelected>>", self._on_format_changed)

        self.output_var = tk.StringVar(value=self._default_output_path())
        ttk.Entry(output, textvariable=self.output_var, width=45).grid(row=1, column=0, columnspan=2, sticky="w", **pad)
        ttk.Button(output, text="Browse...", command=self._browse_output).grid(row=1, column=2, **pad)

        controls = ttk.Frame(self.root)
        controls.grid(row=3, column=0, sticky="ew", **pad)

        self.start_button = ttk.Button(controls, text="Start Recording", command=self._on_start)
        self.start_button.grid(row=0, column=0, padx=8)
        self.stop_button = ttk.Button(controls, text="Stop Recording", command=self._on_stop, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=8)
        self.trim_button = ttk.Button(controls, text="Trim / Preview...", command=self._open_trim_dialog, state="disabled")
        self.trim_button.grid(row=0, column=2, padx=8)
        self.export_button = ttk.Button(controls, text="Export", command=self._on_export, state="disabled")
        self.export_button.grid(row=0, column=3, padx=8)
        self.open_button = ttk.Button(controls, text="Open File", command=self._on_open_output, state="disabled")
        self.open_button.grid(row=0, column=4, padx=8)

        ttk.Label(
            self.root,
            text="Tip: after stopping, tweak format/speed-up/width above and click Export again to re-export.",
            foreground="#555555",
        ).grid(row=4, column=0, sticky="w", padx=8)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(self.root, textvariable=self.status_var).grid(row=5, column=0, sticky="w", padx=8)

        self.progress = ttk.Progressbar(self.root, orient="horizontal", mode="determinate", length=380)
        self.progress.grid(row=6, column=0, sticky="ew", padx=8, pady=(0, 8))

    def _default_output_path(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(os.path.expanduser("~"), "Pictures", "screen2gif")
        ext = FORMAT_EXTENSIONS.get(getattr(self, "format_var", None) and self.format_var.get(), ".webm")
        return os.path.join(output_dir, f"screen2gif_{timestamp}{ext}")

    def _on_format_changed(self, _event=None) -> None:
        ext = FORMAT_EXTENSIONS[self.format_var.get()]
        current = self.output_var.get().strip()
        if current:
            self.output_var.set(os.path.splitext(current)[0] + ext)

    def _browse_output(self) -> None:
        fmt = self.format_var.get()
        path = filedialog.asksaveasfilename(
            defaultextension=FORMAT_EXTENSIONS[fmt],
            filetypes=FORMAT_FILETYPES[fmt],
            initialfile=os.path.basename(self.output_var.get()),
        )
        if path:
            self.output_var.set(path)

    def _on_open_output(self) -> None:
        path = self.last_output_path
        if not path or not os.path.exists(path):
            messagebox.showwarning("No GIF yet", "Record and save a GIF first.")
            return
        try:
            open_with_default_app(path)
        except OSError as exc:
            messagebox.showerror("Failed to open file", str(exc))

    # --------------------------------------------------------------- logic
    def _read_interval_ms(self) -> int:
        value = int(self.interval_var.get())
        if value <= 0:
            raise ValueError("Capture interval must be a positive integer.")
        return value

    def _read_width(self) -> int | None:
        text = self.width_var.get().strip()
        if not text:
            return None
        value = int(text)
        if value <= 0:
            raise ValueError("Output width must be a positive integer.")
        return value

    def _read_monitor_target(self) -> tuple[tuple[int, int, int, int] | None, bool]:
        """Resolve the selected combobox entry to an ImageGrab bbox/all_screens pair."""
        selection = self.monitor_var.get()
        if selection.startswith("All screens"):
            return resolve_monitor_selection("all", self.monitors)
        for monitor in self.monitors:
            if monitor.label() == selection:
                return resolve_monitor_selection(str(monitor.index), self.monitors)
        return resolve_monitor_selection(None, self.monitors)

    def _on_start(self) -> None:
        if self.recorder is not None and not self.recorder.is_running:
            if not messagebox.askyesno(
                "Discard previous recording?",
                "Starting a new recording will discard the previously captured frames "
                "(export them first if you still need them). Continue?",
            ):
                return
            self.recorder.cleanup()
            self.recorder = None

        try:
            interval_ms = self._read_interval_ms()
        except ValueError as exc:
            messagebox.showerror("Invalid setting", str(exc))
            return

        bbox, all_screens = self._read_monitor_target()
        self.recorder = ScreenRecorder(interval_ms, bbox=bbox, all_screens=all_screens)
        self.recorder.start()
        self.trim_start_s = 0.0
        self.trim_end_s = None
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.trim_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self._tick_status()

    def _tick_status(self) -> None:
        if self.recorder is not None and self.recorder.is_running:
            elapsed = self.recorder.elapsed_seconds
            self.status_var.set(f"Recording... {elapsed:0.1f}s, {self.recorder.frame_count} frames")
            self._tick_job = self.root.after(200, self._tick_status)

    def _on_stop(self) -> None:
        if self.recorder is None:
            return
        if self._tick_job is not None:
            self.root.after_cancel(self._tick_job)
            self._tick_job = None

        self.recorder.stop()
        recorded_seconds = self.recorder.elapsed_seconds
        frame_count = self.recorder.frame_count

        self.stop_button.configure(state="disabled")
        self.start_button.configure(state="normal")

        if frame_count == 0:
            messagebox.showwarning("Nothing captured", "No frames were captured. Try a shorter interval.")
            self.recorder.cleanup()
            self.recorder = None
            self.status_var.set("Idle")
            return

        self.export_button.configure(state="normal")
        self.trim_button.configure(state="normal")
        self.trim_start_s = 0.0
        self.trim_end_s = (frame_count - 1) * self.recorder.interval_ms / 1000.0 if frame_count > 1 else 0.0
        self.status_var.set(
            f"Stopped: {frame_count} frames, {recorded_seconds:0.1f}s recorded. "
            "Adjust speed-up/width above, then click Export (can export more than once)."
        )
        self._open_trim_dialog()

    def _open_trim_dialog(self) -> None:
        if self.recorder is None or self.recorder.frame_count == 0:
            return
        frame_count = self.recorder.frame_count
        interval_ms = self.recorder.interval_ms
        full_duration = (frame_count - 1) * interval_ms / 1000.0 if frame_count > 1 else 0.0
        initial_end = self.trim_end_s if self.trim_end_s is not None else full_duration

        dialog = TrimDialog(
            self.root,
            self.recorder.frames_dir,
            frame_count,
            interval_ms,
            initial_start=self.trim_start_s,
            initial_end=initial_end,
        )
        self.root.wait_window(dialog)
        if dialog.result is not None:
            self.trim_start_s, self.trim_end_s = dialog.result
            self.status_var.set(
                f"Trim set: {self.trim_start_s:0.1f}s - {self.trim_end_s:0.1f}s. "
                "Click Export to save with this range."
            )

    def _on_export(self) -> None:
        if self._export_in_progress:
            return
        if self.recorder is None or self.recorder.frame_count == 0:
            messagebox.showwarning("Nothing to export", "Record something first.")
            return

        frame_count = self.recorder.frame_count
        interval_ms = self.recorder.interval_ms
        frames_dir = self.recorder.frames_dir
        full_duration = (frame_count - 1) * interval_ms / 1000.0 if frame_count > 1 else 0.0

        start_s = max(0.0, min(self.trim_start_s, full_duration))
        end_s = self.trim_end_s if self.trim_end_s is not None else full_duration
        end_s = max(start_s, min(end_s, full_duration))

        start_index = max(0, min(int(round(start_s * 1000.0 / interval_ms)), frame_count - 1))
        end_index = max(start_index, min(int(round(end_s * 1000.0 / interval_ms)), frame_count - 1))
        trimmed_seconds = (end_index - start_index) * interval_ms / 1000.0
        exported_frame_count = end_index - start_index + 1

        try:
            speed_factor = self._resolve_speed_factor(trimmed_seconds)
            output_width = self._read_width()
        except ValueError as exc:
            messagebox.showerror("Invalid setting", str(exc))
            return

        output_path = self.output_var.get().strip() or self._default_output_path()
        is_video = self.format_var.get() != "GIF"
        export_fn = build_video if is_video else build_gif

        self._export_in_progress = True
        self.export_button.configure(state="disabled")
        self.status_var.set(
            f"Building {'video' if is_video else 'GIF'} from {exported_frame_count} frames "
            f"(trim {start_s:0.1f}s-{end_s:0.1f}s)..."
        )
        self.progress.configure(maximum=exported_frame_count, value=0)

        def worker() -> None:
            try:
                export_fn(
                    frames_dir=frames_dir,
                    output_path=output_path,
                    capture_interval_ms=interval_ms,
                    speed_factor=speed_factor,
                    resize_width=output_width,
                    frame_range=(start_index, end_index),
                    drop_frames=self.reduce_size_var.get(),
                    progress_callback=lambda cur, total: self._ui_queue.put(("progress", cur, total)),
                )
                self._ui_queue.put(("done", output_path))
            except Exception as exc:  # noqa: BLE001 - surface any error to the UI
                self._ui_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, self._poll_ui_queue)

    def _resolve_speed_factor(self, recorded_seconds: float) -> float:
        if self.speed_mode.get() == "multiplier":
            factor = float(self.multiplier_var.get())
            if factor <= 0:
                raise ValueError("Speed multiplier must be positive.")
            return factor

        target = float(self.target_duration_var.get())
        if target <= 0:
            raise ValueError("Target playback duration must be positive.")
        if recorded_seconds <= 0:
            return 1.0
        return max(recorded_seconds / target, 1e-6)

    def _poll_ui_queue(self) -> None:
        try:
            while True:
                message = self._ui_queue.get_nowait()
                kind = message[0]
                if kind == "progress":
                    _, current, total = message
                    self.progress.configure(maximum=total, value=current)
                    self.status_var.set(f"Building output... {current}/{total} frames")
                elif kind == "done":
                    _, output_path = message
                    self.progress.configure(value=self.progress["maximum"])
                    self.status_var.set(
                        f"Saved: {output_path}. You can change settings and export again, "
                        "or start a new recording."
                    )
                    self.last_output_path = output_path
                    self._export_in_progress = False
                    self.open_button.configure(state="normal")
                    self.export_button.configure(state="normal")
                    self.output_var.set(self._default_output_path())
                    messagebox.showinfo("Saved", f"File saved to:\n{output_path}")
                elif kind == "error":
                    _, error_text = message
                    self._export_in_progress = False
                    self.export_button.configure(state="normal")
                    self.status_var.set("Error")
                    messagebox.showerror("Export failed", error_text)
        except queue.Empty:
            pass

        if self._export_in_progress:
            self.root.after(100, self._poll_ui_queue)

    def _on_close(self) -> None:
        if self.recorder is not None:
            self.recorder.stop()
            self.recorder.cleanup()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    Screen2GifApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
