"""t32py_config - Shared configuration for the Python (TRACE32 Remote API) Lauterbach flow.

Based on Lauterbach's official manual "Controlling TRACE32 via Python 3" (app_python.pdf,
Release 02.2026). Mirrors the existing ``debug_traveo_lauterbach/config.ps1`` layout (same
``LT_*`` variant/window env vars) so both skills can target the same project, and adds the
``T32PY_*`` variables needed for the TRACE32 Remote API (RCL) connection itself.

This module is pure config + discovery - it never talks to TRACE32.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ConfigError(RuntimeError):
    pass


@dataclass
class T32PyConfig:
    variant: str
    variant_config: str = "Debug"
    repo_root: Optional[str] = None
    startup_script: Optional[str] = None
    abs_file: Optional[str] = None
    t32_exe: Optional[str] = None
    dll_path: Optional[str] = None

    # --- TRACE32 Remote API (RCL) connection -----------------------------------------------
    node: str = "localhost"
    port: int = 20000
    packlen: int = 1024
    # T32_DEV device id used by T32_Attach. 1 = TRACE32 debugger / instruction set simulator.
    device: int = 1

    # --- event-driven polling (no blind sleeps; small poll tick + a fail-safe ceiling) ------
    poll_interval_s: float = 0.2
    connect_ceiling_s: float = 20.0
    practice_ceiling_s: float = 120.0
    halt_ceiling_s: float = 30.0

    @property
    def variant_label(self) -> str:
        return f"{self.variant}.{self.variant_config}"

    def build_dir(self) -> Path:
        return Path(self.repo_root) / "build" / self.variant_label

    def resolved_abs_file(self) -> Path:
        if self.abs_file:
            p = Path(self.abs_file)
            return p if p.is_absolute() else Path(self.repo_root) / p
        return self.build_dir() / "bin" / f"{self.variant}.abs"

    def resolved_startup_script(self) -> Optional[Path]:
        if self.startup_script:
            p = Path(self.startup_script)
            return p if p.is_absolute() else Path(self.repo_root) / p
        scripts_dir = Path(self.repo_root) / "app" / "variants" / self.variant / "source" / "Lauterbach_scripts"
        if not scripts_dir.is_dir():
            return None
        hits = sorted(p for p in scripts_dir.glob("*.cmm") if p.is_file())
        return hits[0] if hits else None

    def resolved_t32_exe(self) -> Path:
        if self.t32_exe:
            return Path(self.t32_exe)
        found = _find_running_t32marm_exe()
        if found:
            return found
        found = _search_t32marm_exe()
        if found:
            return found
        raise ConfigError(
            "t32marm.exe not found. Start a debug session once, set T32PY_EXE explicitly, "
            "or check D:/C:/E:/.conan/short/*/1/bin/windows64/."
        )

    def t32_sys_dir(self) -> Path:
        """The '...\\1' system dir (parent of bin\\windows64), needed as P4_SYS by build actions."""
        exe = self.resolved_t32_exe()
        return exe.parent.parent.parent

    def t32_dll_path(self) -> Path:
        """Locate t32api64.dll.

        NOTE (bench-verified 2026-08-05): in this project's conan-packaged TRACE32
        distribution, t32api64.dll is NOT shipped next to t32marm.exe (bin\\windows64) -
        that folder only has hostmci/libusb/t32cadi/etc. The Remote API DLL instead lives
        under the vendor demo tree, e.g. ``demo\\api\\python\\legacy\\t32api64.dll`` or
        ``demo\\api\\capi\\dll\\t32api64.dll``. Search bin\\windows64 first (in case a future
        install does ship it there), then fall back to the demo subfolders relative to the
        '...\\1' system dir before giving up.
        """
        if self.dll_path:
            return Path(self.dll_path)
        if self.t32_exe:
            # Explicit override: honor a DLL sitting next to a user-specified exe first.
            candidate = Path(self.t32_exe).parent / "t32api64.dll"
            if candidate.is_file():
                return candidate
        exe = self.resolved_t32_exe()
        candidate = exe.parent / "t32api64.dll"
        if candidate.is_file():
            return candidate
        sys_dir = exe.parent.parent.parent
        for rel in (
            "demo/api/python/legacy/t32api64.dll",
            "demo/api/capi/dll/t32api64.dll",
        ):
            candidate = sys_dir / rel
            if candidate.is_file():
                return candidate
        raise ConfigError(
            f"t32api64.dll not found next to {exe} nor under "
            f"{sys_dir}/demo/api/(python/legacy|capi/dll)/. Set T32PY_DLL explicitly."
        )


def _find_repo_root(start: Path) -> Path:
    d = start
    while True:
        if (d / "run.py").exists() and (d / "econ_config.sh").exists():
            return d
        if d.parent == d:
            raise ConfigError(f"Repo root not found (expected run.py + econ_config.sh above {start})")
        d = d.parent


def _find_running_t32marm_exe() -> Optional[Path]:
    """Prefer the path of an already-running t32marm process (Windows only)."""
    try:
        out = subprocess.check_output(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-Process t32marm -ErrorAction SilentlyContinue | "
                "Select-Object -First 1 -ExpandProperty Path)",
            ],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        ).strip()
        return Path(out) if out else None
    except Exception:
        return None


def _search_t32marm_exe() -> Optional[Path]:
    for drive in ("D", "C", "E"):
        root = Path(f"{drive}:/.conan/short")
        if not root.is_dir():
            continue
        try:
            for child in sorted(root.iterdir()):
                cand = child / "1" / "bin" / "windows64" / "t32marm.exe"
                if cand.exists():
                    return cand
        except OSError:
            continue
    return None


def load_config(**overrides) -> T32PyConfig:
    """Build a :class:`T32PyConfig` from ``LT_*``/``T32PY_*`` env vars, then apply ``overrides``.

    Required: ``LT_VARIANT`` (or pass ``variant=`` explicitly).
    """
    variant = overrides.pop("variant", None) or os.environ.get("LT_VARIANT")
    if not variant:
        raise ConfigError(
            "variant is not set. Pass variant=... or set $env:LT_VARIANT before running these "
            "scripts (see debug_traveo_lauterbach/SKILL.md and debug_lauterbach_py/SKILL.md)."
        )

    here = Path(__file__).resolve()
    repo_root = os.environ.get("LT_REPO_ROOT") or str(_find_repo_root(here))

    cfg = T32PyConfig(
        variant=variant,
        variant_config=os.environ.get("LT_VARIANT_CONFIG", "Debug"),
        repo_root=repo_root,
        startup_script=os.environ.get("LT_STARTUP_SCRIPT"),
        abs_file=os.environ.get("LT_ABS_FILE"),
        t32_exe=os.environ.get("T32PY_EXE"),
        dll_path=os.environ.get("T32PY_DLL"),
        node=os.environ.get("T32PY_NODE", "localhost"),
        port=int(os.environ.get("T32PY_PORT", "20000")),
        packlen=int(os.environ.get("T32PY_PACKLEN", "1024")),
        device=int(os.environ.get("T32PY_DEVICE", "1")),
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg
