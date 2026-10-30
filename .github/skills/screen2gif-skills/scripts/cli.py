"""Screen2Gif command-line interface.

Record the screen at a fixed frequency and export the captures as a speed-up
GIF, MP4, or WebM, all from the terminal (no GUI required). The output format
is chosen from the -o extension (.gif, .mp4, or .webm).

Examples:
    # Record until Ctrl+C, capture every 500ms, default 1x speed
    python cli.py --interval-ms 500 -o demo.gif

    # Record exactly 60s, then compress playback down to 20s
    python cli.py --duration 60 --target-duration 20 -o demo.gif

    # Record until Ctrl+C, play back at 2x speed, open the result when done
    python cli.py --speed 2.0 -o demo.gif --open

    # Export a WebM video instead of a GIF (requires imageio + imageio-ffmpeg)
    python cli.py --duration 30 -o demo.webm
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

from dpi_awareness import ensure_dpi_awareness

# Must happen before any monitor enumeration/screen capture so monitor
# rectangles are reported in true physical pixels -- see dpi_awareness.py.
ensure_dpi_awareness()

from gif_writer import build_gif
from monitors import list_monitors, resolve_monitor_selection
from recorder import ScreenRecorder
from video_writer import SUPPORTED_VIDEO_EXTENSIONS, build_video

DEFAULT_INTERVAL_MS = 1000
DEFAULT_WIDTH = 1920
STATUS_POLL_SECONDS = 0.2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record the screen and export it as a GIF.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-o", "--output", default=None, help="Output path (default: screen2gif_<timestamp>.webm); extension picks the format: .gif, .mp4, or .webm"
    )
    parser.add_argument(
        "--interval-ms", type=int, default=DEFAULT_INTERVAL_MS, help="Capture one frame every N milliseconds"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Record for this many seconds, then stop automatically (default: record until Ctrl+C)",
    )
    parser.add_argument(
        "--width", type=int, default=DEFAULT_WIDTH, help="Resize frames to this width in pixels (0 = keep original)"
    )
    parser.add_argument(
        "--monitor",
        default=None,
        help=(
            "Which screen to record on multi-monitor setups: 'all' (every monitor combined), "
            "'primary', or a monitor index from --list-monitors. Default: primary monitor only."
        ),
    )
    parser.add_argument(
        "--list-monitors", action="store_true", help="List detected monitors with their index and resolution, then exit"
    )

    speed_group = parser.add_mutually_exclusive_group()
    speed_group.add_argument(
        "--speed", type=float, default=None, help="Playback speed multiplier, e.g. 2.0 = twice as fast as recorded"
    )
    speed_group.add_argument(
        "--target-duration",
        type=float,
        default=None,
        help="Desired playback duration in seconds, e.g. 20 to compress a 60s recording into 20s",
    )

    parser.add_argument("--open", action="store_true", help="Open the resulting GIF with the OS default viewer")
    parser.add_argument(
        "--reduce-size",
        action="store_true",
        help=(
            "When speeding up (--speed/--target-duration), drop frames instead of only "
            "shortening each frame's display time. Makes the GIF actually smaller/shorter "
            "at the cost of choppier motion (skipped frames between kept ones)."
        ),
    )
    return parser.parse_args(argv)


def default_output_path() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.path.expanduser("~"), "Pictures", "screen2gif")
    return os.path.join(output_dir, f"screen2gif_{timestamp}.webm")


def resolve_speed_factor(args: argparse.Namespace, recorded_seconds: float) -> float:
    if args.target_duration is not None:
        if args.target_duration <= 0:
            raise ValueError("--target-duration must be positive")
        if recorded_seconds <= 0:
            return 1.0
        return max(recorded_seconds / args.target_duration, 1e-6)

    speed = args.speed if args.speed is not None else 1.0
    if speed <= 0:
        raise ValueError("--speed must be positive")
    return speed


def _record(recorder: ScreenRecorder, duration: float | None) -> None:
    recorder.start()
    try:
        if duration is not None:
            end_time = time.time() + duration
            while time.time() < end_time:
                remaining = end_time - time.time()
                print(f"\rRecording... {recorder.frame_count} frames, {remaining:0.1f}s left   ", end="", flush=True)
                time.sleep(STATUS_POLL_SECONDS)
        else:
            print("Recording... press Ctrl+C to stop.")
            while True:
                print(
                    f"\rRecording... {recorder.elapsed_seconds:0.1f}s, {recorder.frame_count} frames   ",
                    end="",
                    flush=True,
                )
                time.sleep(STATUS_POLL_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()
        print()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.list_monitors:
        for monitor in list_monitors():
            print(monitor.label())
        return 0

    output_path = args.output or default_output_path()
    resize_width = args.width if args.width and args.width > 0 else None

    output_ext = os.path.splitext(output_path)[1].lower()
    if output_ext not in (".gif", *SUPPORTED_VIDEO_EXTENSIONS):
        print(
            f"Error: unsupported output extension {output_ext!r} (use .gif, {', '.join(SUPPORTED_VIDEO_EXTENSIONS)})",
            file=sys.stderr,
        )
        return 2

    if args.interval_ms <= 0:
        print("Error: --interval-ms must be positive", file=sys.stderr)
        return 2

    try:
        bbox, all_screens = resolve_monitor_selection(args.monitor)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    recorder = ScreenRecorder(args.interval_ms, bbox=bbox, all_screens=all_screens)
    print(f"Capture interval: {args.interval_ms}ms, monitor: {args.monitor or 'primary (default)'}")
    _record(recorder, args.duration)

    recorded_seconds = recorder.elapsed_seconds
    frame_count = recorder.frame_count
    if frame_count == 0:
        print("No frames were captured; nothing to export.", file=sys.stderr)
        recorder.cleanup()
        return 1

    try:
        speed_factor = resolve_speed_factor(args, recorded_seconds)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        recorder.cleanup()
        return 2

    is_video = output_ext in SUPPORTED_VIDEO_EXTENSIONS
    export_fn = build_video if is_video else build_gif
    print(
        f"Captured {frame_count} frames over {recorded_seconds:0.1f}s. "
        f"Building {'video' if is_video else 'GIF'} ({output_ext or '.gif'}) at {speed_factor:.2f}x speed..."
    )

    def on_progress(current: int, total: int) -> None:
        print(f"\rExporting... {current}/{total} frames", end="", flush=True)

    try:
        export_fn(
            frames_dir=recorder.frames_dir,
            output_path=output_path,
            capture_interval_ms=args.interval_ms,
            speed_factor=speed_factor,
            resize_width=resize_width,
            drop_frames=args.reduce_size,
            progress_callback=on_progress,
        )
    except ImportError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 2
    finally:
        recorder.cleanup()

    print(f"\nSaved {'video' if is_video else 'GIF'}: {output_path}")

    if args.open:
        from file_utils import open_with_default_app

        open_with_default_app(output_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
