"""Shared frame-selection helpers used by both the GIF and video exporters.

Keeps the "which captured PNGs go into the output, and how long does each one
display for" logic in one place so ``gif_writer.build_gif`` and
``video_writer.build_video`` can't drift apart.
"""

from __future__ import annotations

import glob
import os
from typing import Optional

from PIL import Image

MIN_FRAME_DURATION_MS = 20  # GIF timing is limited to ~10ms ticks; most viewers need >=20ms.


def select_frame_files(frames_dir: str, frame_range: Optional[tuple[int, int]] = None) -> list[str]:
    """Return the ordered list of captured frame files, optionally trimmed to a range."""
    frame_files = sorted(glob.glob(os.path.join(frames_dir, "frame_*.png")))
    if not frame_files:
        raise ValueError("No frames were captured; nothing to convert.")

    if frame_range is not None:
        start_index, end_index = frame_range
        if start_index < 0 or end_index < start_index or end_index >= len(frame_files):
            raise ValueError("frame_range is out of bounds for the captured frames.")
        frame_files = frame_files[start_index : end_index + 1]

    return frame_files


def resolve_playback(
    frame_files: list[str],
    capture_interval_ms: int,
    speed_factor: float,
    drop_frames: bool,
) -> tuple[list[str], int]:
    """Apply speed-up (and optional frame-dropping) to a frame list.

    Returns ``(frame_files, frame_duration_ms)`` where ``frame_duration_ms`` is
    the constant per-frame display time to use for every remaining frame.
    """
    if speed_factor <= 0:
        raise ValueError("speed_factor must be positive")

    if drop_frames and speed_factor > 1:
        # Drop most of the speed-up into fewer encoded frames (smaller file), then
        # apply any small leftover speed-up via frame duration so the requested
        # speed/target-duration is still hit accurately.
        stride = max(1, int(speed_factor))
        residual_speed = speed_factor / stride
        frame_files = frame_files[::stride]
        frame_duration_ms = max(MIN_FRAME_DURATION_MS, round(capture_interval_ms / residual_speed))
    else:
        frame_duration_ms = max(MIN_FRAME_DURATION_MS, round(capture_interval_ms / speed_factor))

    return frame_files, frame_duration_ms


def load_and_resize(file_path: str, resize_width: Optional[int]) -> Image.Image:
    """Open one captured PNG as RGB, optionally downscaled to ``resize_width``."""
    with Image.open(file_path) as opened:
        image = opened.convert("RGB")
    if resize_width and image.width > resize_width:
        ratio = resize_width / float(image.width)
        new_size = (resize_width, max(1, round(image.height * ratio)))
        image = image.resize(new_size, Image.LANCZOS)
    return image
