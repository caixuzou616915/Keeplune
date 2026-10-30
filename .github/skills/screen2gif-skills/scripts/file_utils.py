"""Cross-platform helper to open a file with the OS default application."""

from __future__ import annotations

import os
import subprocess
import sys


def open_with_default_app(path: str) -> None:
    """Open ``path`` using the operating system's default associated application."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
