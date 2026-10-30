"""ghs-py-config — Shared configuration for the Python (event-driven) Traveo flash/debug flow.

Mirrors the existing PowerShell ``ecu_debug/config.ps1`` layout but as a single, importable
Python module. All paths are resolvable from environment variables / CLI overrides so the same
code works on Bench A (``tviib_e4m_aravalli_s3p_db``) and Bench B (``tviic_6m_endprod``).

This module is *pure data + tiny helpers* — it never launches a process, so it is safe to import
from any step script or from the report/benchmark tooling.

Why Python (not .ps1): the whole solution is Python-first; this replaces ``config.ps1`` verbatim
in intent. No shell is required to read configuration.
"""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional


# --------------------------------------------------------------------------------------------------
# Bench presets — mirror the two known benches documented in debug_traveo_ghs/SKILL.md.
# A caller may override any field via environment variables (TVPY_*) or BenchConfig kwargs.
# --------------------------------------------------------------------------------------------------
@dataclass
class BenchConfig:
    """Everything needed to flash/debug one physical bench.

    All fields have safe defaults for Bench A (the primary arav_s3p bench). Override per bench
    through :func:`load_config` or environment variables — nothing here is hard-wired at runtime.
    """

    # --- Identity -------------------------------------------------------------------------------
    bench: str = "A"                       # "A" or "B"
    variant: str = "tviib_e4m_aravalli_s3p_db.Debug"
    chip: str = "CYT2B93CAS"
    app_core: str = "cm4"                  # app core name
    core_prefix: str = "m4"                # alias used to route commands to the app core

    # --- Tool paths -----------------------------------------------------------------------------
    git_bash: str = r"C:\Program Files\Git\bin\bash.exe"
    project_root: str = r"C:\Project\JB\s3p\sw.sys.tv2.meta-repo-ux"

    # --- GHS license / probe --------------------------------------------------------------------
    ghs_lm_host: str = "@ls-ghs-sg-1.int.automotive-wan.com"
    ghs_lm_which: str = "ghs"
    ghs_path_prefix: str = "/d/.conan/short/dc601f/1:/d/.conan/short/dc601f/1/_ide"

    # --- Debug RC / python-driver paths (relative to build dir, as the RC scripts expect) -------
    multi_rc: str = "../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/multi.rc"
    debug_rc: str = "../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.rc"
    verify_py: str = "../../app/variants/tviib_e4m_aravalli_s3p_db/debug/ghs/tvii_debug_4mbe.py"

    # --- CANoe ----------------------------------------------------------------------------------
    canoe_start_script: str = ""           # optional Start-CANoe.ps1 at project root
    canoe_kl15_env: str = "IGN_ACC"        # CANoe env var raised to 1 for KL15 ON

    # --- Behaviour knobs ------------------------------------------------------------------------
    # NOTE (confirmed 2026-07-27 on bench A / tviib_e4m_aravalli_s3p): TVII_SKIP_VERIFY is NOT
    # referenced anywhere in the project's tvii_debug_4mbe.py driver -- exporting it is a no-op.
    # `verify -all` always runs its full incoherency scan (can emit >90k INCOHERENT lines and take
    # >120s on this bench/build). Do not rely on skip_verify to bound VERIFY time; size the
    # ceilings below for the *real* worst case instead.
    skip_verify: bool = True               # kept for forward-compat; currently has no effect
    # Hard safety ceilings (seconds). These are *fail-safe* upper bounds, NOT normal waits — the
    # event-driven runner returns the instant a marker appears, long before these elapse.
    ceiling_connect_s: float = 45.0
    ceiling_flash_s: float = 300.0
    ceiling_verify_s: float = 300.0
    ceiling_op_s: float = 300.0             # VERIFY (embedded) + op; VERIFY alone observed >150s
    # How often to poll the -R log for markers (seconds). Small = responsive, cheap (file tail).
    poll_interval_s: float = 0.10

    def build_dir(self) -> str:
        """Absolute build directory (``<root>/build/<variant>``)."""
        return str(Path(self.project_root) / "build" / self.variant)

    def bash_project_root(self) -> str:
        """POSIX-style project root for Git-bash ``cd`` (``C:\\x`` -> ``/c/x``)."""
        return _to_bash_path(self.project_root)

    def bash_build_dir(self) -> str:
        return _to_bash_path(self.build_dir())

    def env_exports(self) -> str:
        """The ``export ...`` prefix used before every Git-bash Multi invocation."""
        return (
            f"export GHS_LMHOST='{self.ghs_lm_host}'; "
            f"export GHS_LMWHICH='{self.ghs_lm_which}'; "
            f"export PATH='{self.ghs_path_prefix}:$PATH'"
            + ("; export TVII_SKIP_VERIFY=1" if self.skip_verify else "")
        )

    def to_dict(self) -> Dict:
        return asdict(self)


# Preset overrides for Bench B (triple-core tviic_6m_endprod). Only the deltas from Bench A.
_BENCH_B_OVERRIDES: Dict[str, object] = {
    "bench": "B",
    "variant": "tviic_6m_endprod.Debug",
    "chip": "CYT4DN",
    "app_core": "cm7_0",
    "core_prefix": "m7_0",
    "multi_rc": "../../app/variants/tviic_6m_endprod/debug/multi.rc",
    "debug_rc": "../../app/variants/tviic_6m_endprod/debug/tvii_debug_6mb.rc",
    "verify_py": "../../app/variants/tviic_6m_endprod/debug/tvii_debug_6mb.py",
    "ghs_path_prefix": "/d/.conan/short/bceabf/1:/d/.conan/short/bceabf/1/_ide",
}


def _to_bash_path(win_path: str) -> str:
    """``D:\\Work\\x`` -> ``/d/Work/x`` (Git-bash / MSYS path)."""
    p = win_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        p = "/" + p[0].lower() + p[2:]
    return p


def load_config(bench: str = "A", **overrides) -> BenchConfig:
    """Build a :class:`BenchConfig`, applying (in order) bench preset, environment, kwargs.

    Environment variables (all optional): ``TVPY_PROJECT_ROOT``, ``TVPY_VARIANT``,
    ``TVPY_GIT_BASH``, ``TVPY_GHS_PATH_PREFIX``, ``TVPY_CANOE_START``, ``TVPY_SKIP_VERIFY``.
    """
    cfg = BenchConfig()
    if str(bench).upper() == "B":
        for k, v in _BENCH_B_OVERRIDES.items():
            setattr(cfg, k, v)

    env_map = {
        "TVPY_PROJECT_ROOT": "project_root",
        "TVPY_VARIANT": "variant",
        "TVPY_GIT_BASH": "git_bash",
        "TVPY_GHS_PATH_PREFIX": "ghs_path_prefix",
        "TVPY_CANOE_START": "canoe_start_script",
    }
    for env_key, field_name in env_map.items():
        if os.environ.get(env_key):
            setattr(cfg, field_name, os.environ[env_key])
    if os.environ.get("TVPY_SKIP_VERIFY") is not None:
        cfg.skip_verify = os.environ["TVPY_SKIP_VERIFY"] not in ("0", "false", "False", "")

    for k, v in overrides.items():
        if v is not None and hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


def host_info() -> Dict[str, str]:
    """Static host facts recorded in every session's metadata block."""
    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
    }
