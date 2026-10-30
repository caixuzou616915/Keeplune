"""
dbc_reader.py
=============
Offline DBC / CAN database parser for signal and message discovery.

PURPOSE
-------
Loads all DBC files listed in canoe_agent.json (key: dbc_files) and provides
signal/message lookup without requiring CANoe to be running.  Uses the
cantools library which handles standard DBC, CAN FD, and extended attributes
(BA_DEF_, SG_MUL_VAL_).

MULTI-AGENT ROLE
----------------
Used by a **signal discovery subagent** invoked before a test sequence to
resolve human-readable names (e.g. "EngineSpeed") to exact DBC names, bit
positions, scaling factors and value ranges.  This prevents test agents from
guessing signal names incorrectly.

Typical orchestration pattern:
  1. Orchestrator asks dbc_reader to find signal "EngineSpeed"
  2. dbc_reader returns exact name + message ID + factor/offset
  3. Orchestrator passes exact name to signals.read_sysvar() or write_sysvar()

DEPENDENCIES
------------
- cantools >= 39.4.0  (pip install cantools)
- canoe_agent.json at workspace root (dbc_files key)
  Falls back to scanning DBC/ and Ethernet/DBC/ if JSON absent
- Does NOT require CANoe to be running

PUBLIC API
----------
Class DBCReader(workspace_root, extra_paths=None):
  load(dbc_path)                  -> None
  list_messages()                 -> List[Dict]  # name/id/dlc/signals
  get_message(name_or_id)         -> Optional[Dict]
  find_signals(pattern)           -> List[Dict]  # substring search
  get_signal(signal_name)         -> Optional[Dict]  # exact match
  decode_frame(frame_id, data)    -> Optional[Dict]  # raw bytes -> values
  loaded_files  (property)        -> List[str]
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import cantools
    _CANTOOLS_AVAILABLE = True
except ImportError:
    _CANTOOLS_AVAILABLE = False


# Default DBC search paths relative to the workspace root
_DEFAULT_DBC_DIRS = [
    "DBC",
    "Ethernet/DBC",
]


class DBCReader:
    """
    Loads one or more DBC files and provides signal/message lookup.

    Args:
        workspace_root: Absolute path to the workspace root folder.
        extra_paths:    Additional DBC file paths to load.
    """

    def __init__(
        self,
        workspace_root: str,
        extra_paths: Optional[List[str]] = None,
    ) -> None:
        if not _CANTOOLS_AVAILABLE:
            raise ImportError(
                "cantools is required for DBC parsing.  "
                "Run: pip install cantools"
            )
        self._root = Path(workspace_root)
        self._db = cantools.database.Database()
        self._loaded: List[str] = []
        self._load_default_dbcs(extra_paths or [])

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_default_dbcs(self, extra: List[str]) -> None:
        from .discover import load_config
        config = load_config()

        paths: List[Path] = []
        if config.get("dbc_files"):
            # Explicit file list takes highest priority
            for rel in config["dbc_files"]:
                p = self._root / rel
                if p.exists():
                    paths.append(p)
        elif config.get("dbc_dirs"):
            # Scan listed directories recursively
            for rel in config["dbc_dirs"]:
                d = self._root / rel
                if d.is_dir():
                    paths.extend(d.rglob("*.dbc"))
        else:
            # Fallback: scan default dirs
            for d in _DEFAULT_DBC_DIRS:
                dbc_dir = self._root / d
                if dbc_dir.is_dir():
                    paths.extend(dbc_dir.glob("*.dbc"))

        for p in extra:
            paths.append(Path(p))
        for p in paths:
            self.load(str(p))

    def load(self, dbc_path: str) -> None:
        """Load an additional DBC file into the database."""
        import io, contextlib, sys
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                self._db.add_dbc_file(dbc_path)
            self._loaded.append(dbc_path)
        except Exception as exc:
            # Non-fatal: log to stderr so JSON stdout stays clean
            print(f"[DBCReader] Warning: could not load '{dbc_path}': {exc}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Message queries
    # ------------------------------------------------------------------

    def list_messages(self) -> List[Dict[str, Any]]:
        """Return summary info for every message in the loaded databases."""
        return [
            {
                "name":     msg.name,
                "id":       hex(msg.frame_id),
                "dlc":      msg.length,
                "is_fd":    msg.is_fd,
                "senders":  list(msg.senders),
                "signals":  [s.name for s in msg.signals],
            }
            for msg in self._db.messages
        ]

    def get_message(self, name_or_id) -> Optional[Dict[str, Any]]:
        """
        Look up a message by name or numeric/hex ID.

        Args:
            name_or_id: Message name string, or int/hex-string frame ID.

        Returns:
            Message info dict, or None if not found.
        """
        try:
            if isinstance(name_or_id, str) and not name_or_id.startswith("0x"):
                msg = self._db.get_message_by_name(name_or_id)
            else:
                fid = int(name_or_id, 16) if isinstance(name_or_id, str) else int(name_or_id)
                msg = self._db.get_message_by_frame_id(fid)
        except Exception:
            return None
        return _msg_to_dict(msg)

    # ------------------------------------------------------------------
    # Signal queries
    # ------------------------------------------------------------------

    def find_signals(self, pattern: str) -> List[Dict[str, Any]]:
        """
        Search for signals whose name contains the given substring (case-insensitive).

        Returns:
            List of signal info dicts including parent message name and ID.
        """
        pattern_lc = pattern.lower()
        results = []
        for msg in self._db.messages:
            for sig in msg.signals:
                if pattern_lc in sig.name.lower():
                    d = _sig_to_dict(sig)
                    d["message_name"] = msg.name
                    d["message_id"]   = hex(msg.frame_id)
                    results.append(d)
        return results

    def get_signal(self, signal_name: str) -> Optional[Dict[str, Any]]:
        """
        Return full metadata for a signal by exact name.

        Returns None if not found.
        """
        for msg in self._db.messages:
            for sig in msg.signals:
                if sig.name == signal_name:
                    d = _sig_to_dict(sig)
                    d["message_name"] = msg.name
                    d["message_id"]   = hex(msg.frame_id)
                    return d
        return None

    def decode_frame(
        self,
        frame_id: int,
        data: bytes,
    ) -> Optional[Dict[str, Any]]:
        """
        Decode raw CAN frame bytes into named signal values.

        Args:
            frame_id: Arbitration ID.
            data:     Raw payload bytes.

        Returns:
            Dict mapping signal name → physical value, or None.
        """
        try:
            msg = self._db.get_message_by_frame_id(frame_id)
            return msg.decode(data, decode_choices=False)
        except Exception:
            return None

    @property
    def loaded_files(self) -> List[str]:
        """Paths of all successfully loaded DBC files."""
        return list(self._loaded)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _msg_to_dict(msg) -> Dict[str, Any]:
    return {
        "name":     msg.name,
        "id":       hex(msg.frame_id),
        "dlc":      msg.length,
        "is_fd":    msg.is_fd,
        "cycle_ms": getattr(msg, "cycle_time", None),
        "senders":  list(msg.senders),
        "signals":  [_sig_to_dict(s) for s in msg.signals],
    }


def _sig_to_dict(sig) -> Dict[str, Any]:
    return {
        "name":       sig.name,
        "start_bit":  sig.start,
        "length":     sig.length,
        "byte_order": "big_endian" if sig.byte_order == "big_endian" else "little_endian",
        "is_signed":  sig.is_signed,
        "factor":     sig.scale,
        "offset":     sig.offset,
        "min":        sig.minimum,
        "max":        sig.maximum,
        "unit":       sig.unit,
        "comment":    sig.comment,
    }
