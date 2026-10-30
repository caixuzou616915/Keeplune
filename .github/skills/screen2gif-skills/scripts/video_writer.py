"""Assembles captured PNG frames into an MP4 or WebM video, with optional speed-up.

Unlike the GIF exporter, this requires the optional ``imageio`` + ``imageio-ffmpeg``
packages (``pip install imageio imageio-ffmpeg``). ``imageio-ffmpeg`` bundles its
own ffmpeg binary, so no separate ffmpeg install is needed.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from frame_prep import load_and_resize, resolve_playback, select_frame_files

SUPPORTED_VIDEO_EXTENSIONS = (".mp4", ".webm")

# ffmpeg encoder settings per container. CRF-based, no explicit target bitrate,
# which gives good quality/size for screen-capture content (mostly static UI).
_CODEC_SETTINGS = {
    ".mp4": {
        "codec": "libx264",
        "pixelformat": "yuv420p",
        "output_params": ["-preset", "medium", "-crf", "23"],
    },
    ".webm": {
        "codec": "libvpx-vp9",
        "pixelformat": "yuv420p",
        "output_params": ["-b:v", "0", "-crf", "32"],
    },
}


def build_video(
    frames_dir: str,
    output_path: str,
    capture_interval_ms: int,
    speed_factor: float = 1.0,
    resize_width: Optional[int] = None,
    frame_range: Optional[tuple[int, int]] = None,
    drop_frames: bool = False,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Build an MP4/WebM video from the PNG frames found in ``frames_dir``.

    The output container/codec is chosen from ``output_path``'s extension
    (``.mp4`` or ``.webm``). All other arguments have the same meaning as in
    ``gif_writer.build_gif``: unlike a GIF's per-frame duration tag, the video
    is encoded at a single constant frame rate derived from the (possibly
    sped-up/decimated) frame timing.

    Raises:
        ImportError: if ``imageio``/``imageio-ffmpeg`` aren't installed.
        ValueError: for an unsupported output extension or invalid frame data.
    """
    ext = os.path.splitext(output_path)[1].lower()
    if ext not in SUPPORTED_VIDEO_EXTENSIONS:
        raise ValueError(
            f"Unsupported video extension: {ext!r} (use one of {SUPPORTED_VIDEO_EXTENSIONS})"
        )

    try:
        import imageio.v2 as imageio
        import imageio_ffmpeg  # noqa: F401 - presence check only; imageio uses it as a plugin.
    except ImportError as exc:
        raise ImportError(
            "Video export requires the 'imageio' and 'imageio-ffmpeg' packages. "
            "Install them with: pip install imageio imageio-ffmpeg"
        ) from exc

    import numpy as np

    frame_files = select_frame_files(frames_dir, frame_range)
    frame_files, frame_duration_ms = resolve_playback(frame_files, capture_interval_ms, speed_factor, drop_frames)
    fps = 1000.0 / frame_duration_ms

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    total = len(frame_files)
    codec_settings = _CODEC_SETTINGS[ext]
    # macro_block_size=1: we already guarantee even width/height below (required
    # for yuv420p), so skip imageio's extra 16-multiple auto-resize/warning.
    with imageio.get_writer(output_path, fps=fps, macro_block_size=1, **codec_settings) as writer:
        for index, file_path in enumerate(frame_files):
            image = load_and_resize(file_path, resize_width)
            # libx264/libvpx-vp9 with yuv420p require even width/height.
            width, height = image.size
            even_width, even_height = width - (width % 2), height - (height % 2)
            if (even_width, even_height) != (width, height):
                image = image.resize((max(2, even_width), max(2, even_height)))
            writer.append_data(np.asarray(image))
            if progress_callback:
                progress_callback(index + 1, total)

    return output_path
