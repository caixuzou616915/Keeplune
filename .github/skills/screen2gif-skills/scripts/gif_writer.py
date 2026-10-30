"""Assembles captured PNG frames into a single GIF, with optional speed-up."""

from __future__ import annotations

import os
from typing import Callable, Optional

from PIL import Image

from frame_prep import load_and_resize, resolve_playback, select_frame_files

MIN_FRAME_DURATION_MS = 20  # GIF timing is limited to ~10ms ticks; most viewers need >=20ms.


def build_gif(
    frames_dir: str,
    output_path: str,
    capture_interval_ms: int,
    speed_factor: float = 1.0,
    resize_width: Optional[int] = None,
    frame_range: Optional[tuple[int, int]] = None,
    drop_frames: bool = False,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Build a GIF from the PNG frames found in ``frames_dir``.

    Args:
        frames_dir: Directory containing ``frame_*.png`` files in capture order.
        output_path: Destination ``.gif`` file path.
        capture_interval_ms: Milliseconds between captured frames.
        speed_factor: Playback speed multiplier (2.0 = twice as fast as recorded).
        resize_width: Optional width (px) to downscale frames to (keeps aspect ratio).
        frame_range: Optional ``(start_index, end_index)`` (both inclusive, 0-based)
            to trim to a sub-range of the captured frames instead of using all of them.
        drop_frames: When ``True`` and ``speed_factor`` > 1, actually discard frames
            (keep 1 out of every ``round(speed_factor)`` frames) instead of only
            shortening each frame's display time. This is the only way to make a
            faster/shorter GIF physically smaller: the default timing-only speed-up
            re-encodes every captured frame regardless of ``speed_factor``, so a
            "1 minute" and a "5 minute" export of the same recording end up the same
            size. Dropping frames trades smoothness (skipped motion between kept
            frames) for a file size that shrinks roughly proportionally to
            ``speed_factor``.
        progress_callback: Optional callback(current_index, total_count).

    Returns:
        The output_path that was written.
    """
    frame_files = select_frame_files(frames_dir, frame_range)
    frame_files, frame_duration_ms = resolve_playback(frame_files, capture_interval_ms, speed_factor, drop_frames)

    total = len(frame_files)
    images: list[Image.Image] = []
    for index, file_path in enumerate(frame_files):
        image = load_and_resize(file_path, resize_width)
        images.append(image)
        if progress_callback:
            progress_callback(index + 1, total)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    images[0].save(
        output_path,
        save_all=True,
        append_images=images[1:],
        duration=frame_duration_ms,
        loop=0,
        optimize=True,
    )
    return output_path
