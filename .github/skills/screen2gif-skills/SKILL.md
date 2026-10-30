---
name: screen2gif-skills
description: "Use when you need to record the Windows screen and export it as a speed-up GIF, MP4, or WebM: launch the Screen2Gif desktop app (Tkinter GUI) or drive the equivalent CLI to capture screenshots at a configurable frequency (e.g. every 500ms) and compress playback into a shorter output (e.g. play a 60s recording back in 20s, or at a fixed Nx speed multiplier)."
argument-hint: "Describe the capture/export need, e.g. 'record my screen for 60s at 500ms interval and export a 20s GIF', 'launch the GUI recorder', 'record until I stop it and speed it up 3x', 'export as MP4 instead of GIF'."
metadata:
  author: "Zhao Jianbo"
  version: "1.2.0"
---

# Screen2Gif Skill

## Overview

Screen2Gif is a small, dependency-light Python tool (Pillow only for GIF
export) that captures full-screen screenshots at a fixed interval and
assembles them into a `.gif`, `.mp4`, or `.webm` file — the format is chosen
by the output file's extension. Playback can be sped up either by an
explicit multiplier (e.g. `2x`) or by a target playback duration (e.g.
"compress this 60s recording into a 20s GIF"). It ships as both a Tkinter
desktop app and an equivalent CLI, sharing the same `recorder.py` /
`frame_prep.py` / `gif_writer.py` / `video_writer.py` core.

MP4/WebM export is optional (requires `imageio`+`imageio-ffmpeg`, see
Prerequisites) and solves two GIF limitations directly: much smaller file
sizes for the same content (real video compression instead of GIF's
palette-based encoding), and native seek/scrub support — GIFs always play
linearly from the start with no player-provided seek bar, while MP4/WebM
play in any video player/browser with a normal scrubbable timeline.

## When to Use

- Recording a short screen capture and exporting it as a shareable GIF.
- Configuring the capture frequency (screenshot interval in milliseconds).
- On multi-monitor setups, picking which screen to record (a single monitor
  or all monitors combined) instead of always capturing the primary display.
- Speeding up playback: either a fixed multiplier (`--speed 2.0`) or a
  target output duration (`--target-duration 20` to compress a 1-minute
  recording into 20 seconds).
- Previewing captured frames and trimming to a start/end time range before
  exporting (GUI only: `Trim / Preview...` dialog).
- Re-exporting the same recording with different speed/width/trim settings
  without re-recording (GUI: `Stop Recording` then `Export` repeatedly).
- Headless/scripted capture where a GUI isn't available (use `cli.py`).
- Exporting to MP4 or WebM instead of GIF, when you want a smaller file
  and/or a player with a seek/scrub bar (GUI: **Format** dropdown; CLI: give
  `-o` a `.mp4`/`.webm` path). Requires the optional `imageio`/
  `imageio-ffmpeg` dependency.

## Implementation Files

Location: [`.github/skills/screen2gif-skills/scripts/`](../../skills/screen2gif-skills/scripts/)

- `recorder.py` — `ScreenRecorder`: background-thread screen capture on a
  fixed interval, saving PNG frames to a temp directory. Accepts an optional
  `bbox`/`all_screens` pair (see `monitors.py`) to target a single monitor or
  all monitors combined instead of just the primary display.
- `monitors.py` — `list_monitors()` / `resolve_monitor_selection()`: enumerates
  physical monitors (Win32 `EnumDisplayMonitors` via `ctypes`, no extra
  dependency) and resolves a `--monitor` value (`all`, `primary`, or an index)
  to an `ImageGrab.grab()` bbox/all_screens pair. Calls
  `dpi_awareness.ensure_dpi_awareness()` before enumerating so monitor
  rectangles are true physical pixels (see below).
- `dpi_awareness.py` — `ensure_dpi_awareness()`: makes the process Windows
  per-monitor DPI aware, once, before any monitor enumeration or capture.
  Without this, a DPI-unaware process gets *virtualized* (scaled) monitor
  rectangles from `GetMonitorInfoW` on any monitor whose scaling differs
  from the OS's assumed baseline, while `ImageGrab.grab()` still captures
  real physical pixels — so a bbox built from the virtualized rectangle only
  covers the top-left fraction of that monitor. This was the root cause of
  a real bug: recording the primary monitor came out "not full screen" while
  a secondary monitor (with matching/100% scaling) recorded fine. Called
  from `monitors.py` and eagerly at the top of `main.py`/`cli.py`; safe to
  call more than once or after Tk has already touched DPI settings.
- `frame_prep.py` — shared helpers used by both exporters: `select_frame_files()`
  (globs/validates captured PNGs, applies `frame_range`), `resolve_playback()`
  (computes per-frame duration and, if `drop_frames=True`, decimates the frame
  list by an integer stride), and `load_and_resize()` (opens a frame and
  downscales it via `resize_width`). Keeps the GIF and video exporters from
  drifting apart.
- `gif_writer.py` — `build_gif()`: assembles the PNG frames into a `.gif`,
  computing per-frame duration as `capture_interval_ms / speed_factor`.
  Supports an optional `frame_range=(start_index, end_index)` to trim to a
  sub-range of captured frames, and an optional `drop_frames=True` to actually
  discard frames (not just shorten their display time) so the file size
  shrinks when speeding up.
- `video_writer.py` — `build_video()`: same options as `build_gif()` (speed,
  trim, resize, drop_frames) but encodes to `.mp4` (H.264/`libx264`) or
  `.webm` (VP9/`libvpx-vp9`) via `imageio`+`imageio-ffmpeg`. Lazily imports
  `imageio`, so this is only required if you actually export a video; raises
  a clear `ImportError` with the install command if the optional dependency
  is missing. `SUPPORTED_VIDEO_EXTENSIONS = (".mp4", ".webm")`.
- `file_utils.py` — `open_with_default_app()`: cross-platform "open this
  file with the OS default viewer" helper (Windows/macOS/Linux).
- `main.py` — Tkinter GUI app wiring the above together (Start/Stop
  Recording, `Trim / Preview...`, a **Format** dropdown (GIF/MP4/WebM),
  Export/Open File buttons, and a "Monitor to record" dropdown populated
  from `list_monitors()`). The `TrimDialog` class lets you scrub through
  captured frames and pick a start/end time range, opened automatically
  after stopping a recording. Export dispatches to `build_video()` or
  `build_gif()` depending on the selected format.
- `cli.py` — command-line equivalent, no GUI required (no trim UI; trim
  before recording by choosing `--duration`, or edit the output afterward).
  Output format is inferred from the `-o` extension (`.gif`/`.mp4`/`.webm`);
  an unsupported extension fails fast with a clear error before recording
  starts.
- `requirements.txt` — `Pillow` is required. `imageio`+`imageio-ffmpeg` are
  optional, only needed for `.mp4`/`.webm` export; `imageio-ffmpeg` bundles
  its own ffmpeg binary so no system ffmpeg install is required.

## Prerequisites

- Python 3.10+ (uses `X | None` type hints).
- `pip install -r requirements.txt` (installs Pillow; `tkinter` ships with
  standard Python on Windows).
- For MP4/WebM export only: `pip install imageio imageio-ffmpeg` (also in
  `requirements.txt`, commented as optional). No separate ffmpeg install is
  needed — `imageio-ffmpeg` bundles its own binary. If this dependency is
  missing, exporting to `.mp4`/`.webm` fails with a clear `ImportError`
  message telling you to install it; GIF export is unaffected.
- Windows is the primary target (uses `os.startfile` to open output files),
  but the core recorder/writer/CLI work cross-platform via `PIL.ImageGrab`.
- **Playing WebM files**: modern browsers (Chrome, Edge, Firefox) and VLC
  play `.webm` natively by double-click/drag-in. Windows' built-in Movies &
  TV app does not support WebM out of the box — install the free "Web Media
  Extensions" package from the Microsoft Store if you want native Explorer
  thumbnail/preview support, or just use a browser/VLC. MP4 has no such
  caveat (plays everywhere), so prefer MP4 if playback compatibility matters
  more than the extra compression WebM offers.

## Command Usage

### GUI

```powershell
python .github\skills\screen2gif-skills\scripts\main.py
```

Set capture interval (ms), choose speed multiplier or target playback
duration, and pick a monitor from the **Monitor to record** dropdown
(defaults to the primary display; choose "All screens (combined)" to
capture every monitor side by side). Click **Start Recording** → **Stop
Recording**. A **Preview & Trim** dialog opens automatically after stopping:
scrub through captured frames with the slider, set the Start/End (s) fields
(or use "Set = preview" to capture the current scrub position), then **OK**.
Pick a **Format** (GIF/MP4/WebM) — changing it updates the output file's
extension automatically — then click **Export** to save. You can reopen the
trim dialog anytime via **Trim / Preview...**, and tweak format/speed/
width/trim and click **Export** again to re-export the same recording
without capturing again. **Open File** opens the last saved file.

### CLI

```powershell
python .github\skills\screen2gif-skills\scripts\cli.py [options]
```

| Goal | Command |
|------|---------|
| Record until Ctrl+C, 500ms interval, 1x speed | `cli.py --interval-ms 500 -o demo.gif` |
| Record exactly 60s, compress playback to 20s | `cli.py --duration 60 --target-duration 20 -o demo.gif` |
| Record until Ctrl+C, play back at 2x speed | `cli.py --speed 2.0 -o demo.gif` |
| List detected monitors (index + resolution) | `cli.py --list-monitors` |
| Record only monitor 1 (multi-monitor setups) | `cli.py --monitor 1 -o demo.gif` |
| Record every monitor combined | `cli.py --monitor all -o demo.gif` |
| Export MP4 instead of GIF | `cli.py --duration 30 -o demo.mp4` |
| Export WebM instead of GIF | `cli.py --duration 30 -o demo.webm` |
| Open the output automatically when done | add `--open` |
| Keep original resolution (skip downscale) | `--width 0` |
| Shrink the file size when speeding up (drops frames) | add `--reduce-size` |

Key options:

| Option | Meaning | Default |
|--------|---------|---------|
| `--interval-ms N` | Capture one frame every N ms | `1000` |
| `--duration S` | Auto-stop after S seconds (omit to record until Ctrl+C) | none |
| `--monitor {all,primary,N}` | Which screen(s) to record; `N` is an index from `--list-monitors` | primary monitor |
| `--list-monitors` | Print detected monitors (index, resolution, primary flag) and exit | off |
| `--speed X` | Playback speed multiplier (mutually exclusive with `--target-duration`) | `1.0` |
| `--target-duration S` | Desired GIF playback length in seconds (mutually exclusive with `--speed`) | none |
| `--reduce-size` | Drop frames (instead of only shortening display time) when speeding up, so the file actually shrinks | off |
| `--width N` | Downscale output frames to width N px (`0` = keep original) | `1920` |
| `-o/--output PATH` | Output path; extension picks the format: `.gif`, `.mp4`, or `.webm` | `Pictures\screen2gif\screen2gif_<timestamp>.webm` |
| `--open` | Open the output with the OS default viewer once saved | off |

Run `python cli.py -h` for the full option list. The GUI has an equivalent
"Reduce file size by dropping frames" checkbox under **Playback speed-up**,
and a **Format** dropdown (GIF/MP4/WebM) next to the output path.

MP4/WebM export needs the optional `imageio`+`imageio-ffmpeg` dependency
(see Prerequisites); an unsupported output extension (anything other than
`.gif`/`.mp4`/`.webm`) is rejected immediately, before any recording starts.

## Notes

- Speed factor when using `--target-duration`: `speed_factor = recorded_seconds / target_duration`.
- Minimum GIF frame duration is clamped to 20ms (`gif_writer.MIN_FRAME_DURATION_MS`)
  since most viewers won't render faster ticks reliably.
- Frames are written to a temp directory (`tempfile.mkdtemp(prefix="screen2gif_")`)
  and cleaned up after export (GUI keeps them until a new recording starts,
  so you can re-export with different settings first).
- **Speed/target-duration only changes per-frame timing, not file size, unless
  `--reduce-size`/`drop_frames` is used.** Re-exporting the *same* recorded
  frames at a different `--speed` or `--target-duration` normally keeps every
  captured frame and its pixel data identical — only the small per-frame delay
  tag changes. If a 1-minute export and a 5-minute export come out the same
  size, that's why. Pass `--reduce-size` (CLI) / check "Reduce file size by
  dropping frames" (GUI) to actually discard frames — keeping roughly
  1-out-of-every-`round(speed_factor)` frames — which shrinks the file
  proportionally to the speed-up (bench-verified: a 4x speed-up with dynamic
  on-screen motion dropped a 29-frame/802KB GIF to 7 frames/35KB). Trade-offs:
  - Motion looks choppier/jumpier since skipped frames are simply discarded,
    not blended — fast or brief on-screen changes between kept frames can be
    lost entirely (e.g. a quick tooltip flash).
  - The requested speed/target-duration is only approximate (rounded to an
    integer frame stride), though a small residual duration adjustment keeps
    it close.
  - No benefit for near-static screens: if consecutive captured frames are
    (near-)identical, Pillow's GIF `optimize` already encodes duplicates
    almost for free, so dropping frames won't shrink the file much. The size
    win is real for content that visibly changes between captures (cursor
    movement, scrolling, video, animations).
  - To shrink files with smoother motion preserved instead, prefer a shorter
    `--duration`, a larger `--interval-ms`, trimming (GUI `Trim / Preview...`
    or `frame_range`), or a smaller `--width`.
- Monitor enumeration (`monitors.list_monitors`) is Windows-only via
  `ctypes`; on other platforms it reports a single "Entire screen" entry and
  `--monitor` only supports `all`/`primary` (equivalent) since Pillow's
  `ImageGrab` can't enumerate individual monitors outside Windows.
- **If a recorded monitor comes out cropped/"not full screen"** (typically
  the primary monitor, on a system with per-monitor DPI scaling), this is a
  Windows DPI-virtualization issue, not a bbox-math bug — see
  `dpi_awareness.py` above. It's fixed automatically by calling
  `ensure_dpi_awareness()` before enumeration; if it ever regresses, check
  `cli.py --list-monitors` output against the monitor's actual native
  resolution (Windows Display Settings) — a mismatch there means DPI
  awareness isn't taking effect (e.g. another part of the process set an
  incompatible awareness mode first via an embedded manifest).
- **Why MP4/WebM are smaller than GIF for the same recording**: GIF is
  limited to a 256-color palette per frame and (in this tool) full-frame
  encoding; MP4 (`libx264`)/WebM (`libvpx-vp9`) use real inter-frame video
  compression (motion estimation, full color depth), so the same captured
  frames typically produce a dramatically smaller file — this is generally a
  better fix for "the file is too big" than frame-dropping, and doesn't make
  motion choppier.
- **Why MP4/WebM support seeking and GIF doesn't**: GIF has no container-level
  timeline/index for a player to seek into — it's just a looped sequence of
  frames, so browsers/viewers can only play it from the start. MP4/WebM are
  real video containers with a seekable timeline, so any video player or
  browser `<video>` tag gets a normal scrub bar for free.
- `build_video()` forces even frame width/height (required for `yuv420p`) and
  passes `macro_block_size=1` to `imageio.get_writer()` to avoid an extra
  16-px-multiple auto-resize (the even-dimension rounding is already
  sufficient); MP4 uses `-preset medium -crf 23`, WebM uses `-b:v 0 -crf 32`.
- `--reduce-size`/`drop_frames` and `frame_range`/trim work identically for
  video export as for GIF export (`frame_prep.py` is shared), so the same
  file-size and choppiness trade-offs described above apply to MP4/WebM too.
