"""
discover.py — Auto-detect project configuration and write canoe_agent.json.

Run once per CANoe project (CANoe must be open with the .cfg loaded):
    python -m canoe discover

canoe_agent.json is written next to the .cfg file inside the CANoe project
folder — NOT inside the .github/scripts folder.  This makes the tooling fully
portable: copy .github/ to any workspace once; each CANoe project keeps its
own config alongside its .cfg.  Switching the open .cfg in CANoe automatically
activates the matching config — no manual path changes needed.

Detects:
  - All DBC files (recursive scan from the project root)
  - Diagnostic devices (from live CANoe COM)
  - SysVar namespaces (from live CANoe COM)
  - DoIP / IPv6 addresses (grep CAPL node files)
  - NM SysVar name (pattern match against known candidates)
"""

from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


_HERE = Path(__file__).parent

# Package-level fallback config (used when CANoe is not running, e.g. offline DBC queries)
_FALLBACK_CONFIG_PATH = _HERE / "canoe_agent.json"

# Keep the old name as an alias for any external code that imported it directly
CONFIG_PATH = _FALLBACK_CONFIG_PATH


def get_active_config_path() -> Path:
    """
    Return the path to canoe_agent.json for the **currently loaded** CANoe project.

    Resolution order:
      1. <CANoe_cfg_dir>/canoe_agent.json  — project-local config (preferred)
      2. _FALLBACK_CONFIG_PATH             — package-bundled fallback

    This means switching the open .cfg in CANoe automatically selects the
    correct config — no manual path changes needed.
    """
    try:
        import win32com.client
        app = win32com.client.Dispatch("CANoe.Application")
        cfg_full_name = app.Configuration.FullName
        if cfg_full_name:
            candidate = Path(cfg_full_name).parent / "canoe_agent.json"
            if candidate.exists():
                return candidate
    except Exception:
        pass
    return _FALLBACK_CONFIG_PATH

# IPv6 address pattern
_IPV6_RE = re.compile(
    r'["\']'
    r'([0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{0,4}){2,7})'
    r'["\']'
)

# Known NM SysVar candidates (namespace, variable) — tried in order
_NM_CANDIDATES = [
    ("NM",          "NM_State"),
    ("NM",          "CurrentState"),
    ("CANoe::NM",   "NMState"),
    ("NM_Gateway",  "State"),
]

_NM_ENVVAR_CANDIDATES = [
    "NM_State",
    "NM_BusState",
]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_discover(workspace_root: Optional[str] = None) -> Dict[str, Any]:
    """
    Auto-detect project configuration and write canoe_agent.json.

    Args:
        workspace_root: Absolute path to the CANoe project root folder.
                        When omitted (or None), the root is derived automatically
                        from the path of the .cfg file loaded in the running
                        CANoe instance — no user input required.

    Returns:
        The discovered config dict.
    """
    print("Scanning workspace...")

    config: Dict[str, Any] = {}

    # 2. CANoe live data first — we need config_path to derive root when not given
    live = _query_canoe_live()
    config["diagnostic_devices"]  = live.get("diagnostic_devices", [])
    config["sysvar_namespaces"]    = live.get("sysvar_namespaces", [])

    # Resolve workspace root
    if workspace_root:
        root = Path(workspace_root)
    elif live.get("config_path"):
        # Derive from the directory that contains the .cfg file
        root = Path(live["config_path"]).parent
        _ok(f"Project root auto-detected from CANoe  →  {root}")
    else:
        raise RuntimeError(
            "Could not auto-detect project root: CANoe is not running or no .cfg is loaded.\n"
            "Either open CANoe with your project, or pass the path explicitly:\n"
            "  python -m canoe discover \"C:\\path\\to\\project\""
        )

    # 1. DBC files
    dbc_files, dbc_dirs = _find_dbc_files(root)
    config["dbc_files"] = [str(Path(f).relative_to(root)).replace("\\", "/") for f in dbc_files]
    config["dbc_dirs"]  = [str(d).replace("\\", "/") for d in dbc_dirs]
    _ok(f"Found {len(dbc_files)} DBC files  →  {', '.join(str(d) for d in dbc_dirs) or 'root'}")

    # (live data already fetched above)
    if live.get("config_path"):
        config["canoe_config_path"] = live["config_path"]
    config["project_root"] = str(root)
    if config["diagnostic_devices"]:
        _ok(f"Found {len(config['diagnostic_devices'])} diagnostic ECUs  →  {', '.join(config['diagnostic_devices'])}")
    else:
        _warn("No diagnostic devices found (CANoe not running or no CDD/ODX loaded)")
    if config["sysvar_namespaces"]:
        _ok(f"Found {len(config['sysvar_namespaces'])} SysVar namespaces")
    else:
        _warn("No SysVar namespaces found")

    # 3. DoIP / Ethernet addressing from CAPL files
    doip = _find_doip_addresses(root)
    if doip:
        config["doip"] = doip
        _ok(f"Detected DoIP addresses  →  {doip.get('tester_ipv6','?')} → {doip.get('target_ipv6','?')}")
    else:
        _warn("DoIP addresses not detected (no IPv6 literals found in CAPL nodes)")

    # 4. NM SysVar
    nm = _detect_nm_sysvar(live.get("sysvar_namespaces", []))
    if nm:
        config["nm_sysvar"] = nm
        _ok(f"Detected NM SysVar  →  {nm['namespace']}::{nm['variable']}")
    else:
        _warn("NM SysVar not auto-detected — update 'nm_sysvar' in canoe_agent.json manually if needed")

    # 5. Write config next to the .cfg file (project-local)
    config_out = root / "canoe_agent.json"
    with open(config_out, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    _ok(f"Wrote canoe_agent.json")

    print()
    print(f"Config saved to: {config_out}")
    print("Each CANoe project keeps its own canoe_agent.json next to its .cfg file.")
    print("Switching projects in CANoe automatically activates the matching config.")
    print("Run 'python -m canoe status' to verify the connection.")
    return config


# ---------------------------------------------------------------------------
# Step 1: DBC discovery
# ---------------------------------------------------------------------------

def _find_dbc_files(root: Path):
    """Recursively find all .dbc files, excluding the tools folder itself."""
    ignore_dirs = {".github", "__pycache__", ".git", "node_modules"}
    found: List[Path] = []

    for p in root.rglob("*.dbc"):
        parts = set(p.relative_to(root).parts)
        if parts & ignore_dirs:
            continue
        found.append(p)

    # Derive unique parent dirs relative to root
    dirs = sorted({p.parent.relative_to(root) for p in found})
    return found, dirs


# ---------------------------------------------------------------------------
# Step 2: Live CANoe queries
# ---------------------------------------------------------------------------

def _query_canoe_live() -> Dict[str, Any]:
    """Connect to CANoe and read diagnostic devices + SysVar namespaces."""
    result: Dict[str, Any] = {
        "diagnostic_devices": [],
        "sysvar_namespaces":  [],
        "config_path":        None,
    }
    try:
        import win32com.client
        app = win32com.client.Dispatch("CANoe.Application")

        # Config path
        try:
            result["config_path"] = app.Configuration.FullName
        except Exception:
            pass

        # Diagnostic devices
        try:
            devs = app.DiagnosticDevices
            result["diagnostic_devices"] = [
                devs.Item(i).Name for i in range(1, devs.Count + 1)
            ]
        except Exception:
            pass

        # SysVar namespaces (top-level only)
        try:
            ns_col = app.System.Namespaces
            result["sysvar_namespaces"] = [
                ns_col.Item(i).Name for i in range(1, ns_col.Count + 1)
            ]
        except Exception:
            pass

    except ImportError:
        _warn("pywin32 not installed — skipping live CANoe queries")
    except Exception as exc:
        _warn(f"Could not connect to CANoe ({exc}) — skipping live queries")

    return result


# ---------------------------------------------------------------------------
# Step 3: DoIP address detection
# ---------------------------------------------------------------------------

def _find_doip_addresses(root: Path) -> Optional[Dict[str, Any]]:
    """
    Search CAPL (.can, .cin) files for IPv6 address literals.
    Returns the first tester/target pair found.
    """
    capl_files: List[Path] = []
    for ext in ("*.can", "*.cin"):
        capl_files.extend(root.rglob(ext))

    addresses: List[str] = []
    for capl in capl_files:
        try:
            text = capl.read_text(encoding="latin-1", errors="ignore")
            for match in _IPV6_RE.finditer(text):
                addr = match.group(1)
                # Keep only unicast IPv6 (not multicast FF../link-local FE80)
                upper = addr.upper()
                if (
                    ":" in addr
                    and addr.count(":") >= 4
                    and not upper.startswith("FF")
                    and not upper.startswith("FE80")
                    and addr not in addresses
                ):
                    addresses.append(addr)
        except Exception:
            continue

    # Look for tester/target port patterns near the addresses
    ports: List[int] = []
    for capl in capl_files:
        try:
            text = capl.read_text(encoding="latin-1", errors="ignore")
            for m in re.finditer(r'0x([0-9A-Fa-f]{4})\s*;?\s*/\*.*?[Pp]ort', text):
                ports.append(int(m.group(1), 16))
            for m in re.finditer(r'[Pp]ort\s*=\s*0x([0-9A-Fa-f]{4})', text):
                ports.append(int(m.group(1), 16))
        except Exception:
            continue

    if len(addresses) >= 2:
        result: Dict[str, Any] = {
            "tester_ipv6": addresses[0],
            "target_ipv6": addresses[1],
        }
        if len(ports) >= 2:
            result["tester_port"] = ports[0]
            result["target_port"] = ports[1]
        return result
    elif len(addresses) == 1:
        return {"tester_ipv6": addresses[0], "target_ipv6": None}

    return None


# ---------------------------------------------------------------------------
# Step 4: NM SysVar detection
# ---------------------------------------------------------------------------

def _detect_nm_sysvar(namespaces: List[str]) -> Optional[Dict[str, str]]:
    """
    Match discovered SysVar namespaces against known NM patterns.
    Returns the first matching (namespace, variable) pair.
    """
    ns_lower = {n.lower(): n for n in namespaces}

    for ns_candidate, var in _NM_CANDIDATES:
        # Check if the namespace (or a variant) exists
        key = ns_candidate.lower().split("::")[-1]
        for lower_ns, real_ns in ns_lower.items():
            if key in lower_ns and "nm" in lower_ns:
                return {"namespace": real_ns, "variable": var}

    return None


# ---------------------------------------------------------------------------
# Config loader (used by other modules at runtime)
# ---------------------------------------------------------------------------

def load_config() -> Dict[str, Any]:
    """
    Load canoe_agent.json for the currently active CANoe project.

    Calls get_active_config_path() so that switching the open .cfg in CANoe
    automatically loads the matching config — no manual path changes needed.
    Returns an empty dict if no config file exists yet.
    """
    path = get_active_config_path()
    if path.exists():
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(msg: str) -> None:
    print(f"  \u2713 {msg}")


def _warn(msg: str) -> None:
    print(f"  ! {msg}")
