"""
signals.py
==========
OSI Layer 7 (Application): SysVar and Environment Variable read/write.

PURPOSE
-------
The primary interface for stimulating and observing ECU behaviour at the
signal level.  Two data sources are supported:

  1. System Variables (SysVars) -- app.System.Namespaces
       Namespace paths mirror the SysVar panel in CANoe, e.g.:
         namespace="MyNamespace", variable="MySignal"
       SysVars can be linked to DBC signals via Signal Links, giving
       real-time physical values.

  2. Environment Variables (EnvVars) -- app.Environment.GetVariable()
       Defined in DBC files with the "EV_" keyword.
       Used by CAPL nodes to drive message content.

  3. Bus signals (direct DBC readback) -- app.GetBus(network).GetSignal()
       Reads a DBC signal's current value straight off the bus, with NO
       SysVar link, NO CAPL node, and NO Test Setup required. Verified
       live against CANoe 11.0. This is the easiest way to read feedback
       signals transmitted by the ECU (e.g. *_Tx messages) that have no
       SysVar namespace defined for them.

MULTI-AGENT ROLE
----------------
This is the **stimulation and readback layer**.  A test agent writes a
stimulus value, then reads the same or a feedback signal to verify the ECU
reacted correctly.  Works on any CANoe project without modification.

DEPENDENCIES
------------
- canoe_com.CANoeConnection (connected; measurement must be running for writes)
- No additional Python packages required

PUBLIC API  (all functions take conn: CANoeConnection as first argument)
----------
SysVar functions:
  list_namespaces(conn)                           -> List[str]
  list_sysvars(conn, namespace)                   -> List[Dict]  # name/value/type
  read_sysvar(conn, namespace, variable)          -> Any
  write_sysvar(conn, namespace, variable, value)  -> None

EnvVar functions:
  list_envvars(conn)              -- raises CANoeError (not enumerable via COM)
  read_envvar(conn, variable)     -> Any
  write_envvar(conn, variable, value) -> None

Bus signal functions:
  read_bus_signal(conn, message, signal,
                  network="CAN", channel=1)      -> Any  # physical value
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from .canoe_com import CANoeConnection, CANoeError


# ---------------------------------------------------------------------------
# SysVar helpers
# ---------------------------------------------------------------------------

def list_namespaces(conn: CANoeConnection) -> List[str]:
    """Return all top-level SysVar namespace names."""
    ns_collection = conn.system.Namespaces
    result = []
    for i in range(1, ns_collection.Count + 1):
        result.append(ns_collection.Item(i).Name)
    return result


def list_sysvars(conn: CANoeConnection, namespace: str) -> List[Dict[str, Any]]:
    """
    List all variables in a SysVar namespace.

    Args:
        namespace: Namespace name as shown in CANoe (e.g. "MyNamespace").
                   Use "::" separator for nested namespaces.

    Returns:
        List of dicts with keys: name, value, type.
    """
    ns = _resolve_namespace(conn, namespace)
    result = []
    for i in range(1, ns.Variables.Count + 1):
        var = ns.Variables.Item(i)
        result.append({
            "name": var.Name,
            "value": _safe_value(var),
            "type": _var_type_str(var),
        })
    return result


def read_sysvar(conn: CANoeConnection, namespace: str, variable: str) -> Any:
    """
    Read the current value of a SysVar.

    Args:
        namespace: E.g. "MyNamespace" or "Parent::Child" for nested namespaces.
        variable:  Variable name within that namespace.

    Returns:
        The current value (int, float, str, or bytes).
    """
    ns = _resolve_namespace(conn, namespace)
    try:
        return ns.Variables.Item(variable).Value
    except Exception as exc:
        raise CANoeError(
            f"Cannot read SysVar '{namespace}::{variable}': {exc}"
        ) from exc


def write_sysvar(
    conn: CANoeConnection, namespace: str, variable: str, value: Any
) -> None:
    """
    Write a value to a SysVar.

    Args:
        namespace: E.g. "MyNamespace" or "Parent::Child" for nested namespaces.
        variable:  Variable name within that namespace.
        value:     New value to set.
    """
    ns = _resolve_namespace(conn, namespace)
    try:
        ns.Variables.Item(variable).Value = value
    except Exception as exc:
        raise CANoeError(
            f"Cannot write SysVar '{namespace}::{variable}' = {value!r}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Environment Variable helpers (DBC-defined)
# ---------------------------------------------------------------------------

def list_envvars(conn: CANoeConnection) -> List[Dict[str, Any]]:
    """Return all environment variables defined in the loaded DBC files."""
    # CANoe COM does not expose a Variables collection on Environment.
    # EnvVars must be accessed individually via GetVariable().
    # Return a message directing users to use read_envvar() with a known name.
    raise CANoeError(
        "CANoe COM does not expose an enumerable EnvVar collection. "
        "Use 'signal envvar read <name>' with a known variable name instead."
    )


def read_envvar(conn: CANoeConnection, variable: str) -> Any:
    """
    Read an environment variable value.

    Args:
        variable: Flat variable name as defined in the DBC (e.g. "MyEnvVar").

    Returns:
        Current value.
    """
    try:
        return conn.environment.GetVariable(variable).Value
    except Exception as exc:
        raise CANoeError(f"Cannot read EnvVar '{variable}': {exc}") from exc


def write_envvar(conn: CANoeConnection, variable: str, value: Any) -> None:
    """
    Write an environment variable.

    Args:
        variable: Flat variable name.
        value:    New value.
    """
    try:
        conn.environment.GetVariable(variable).Value = value
    except Exception as exc:
        raise CANoeError(
            f"Cannot write EnvVar '{variable}' = {value!r}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Bus signal helpers (direct DBC readback, no SysVar/CAPL node required)
# ---------------------------------------------------------------------------

def read_bus_signal(
    conn: CANoeConnection,
    message: str,
    signal: str,
    network: str = "CAN",
    channel: int = 1,
) -> Any:
    """
    Read a DBC signal's current physical value directly off the bus via
    Application.GetBus(network).GetSignal(channel, message, signal).

    This requires only that the message/signal exist in a loaded DBC and
    that the bus has seen at least one frame (otherwise returns the DBC
    default, typically 0). No SysVar link, CAPL node, or Test Setup is
    needed — useful for reading ECU-transmitted (Tx) feedback signals that
    have no SysVar namespace defined.

    Args:
        message: DBC message name, e.g. "Msg_IlluminationCtl_Tx".
        signal:  DBC signal name, e.g. "Sig_IllumReqTargetUserLevelCh1".
        network: Bus/network name as shown in CANoe (default "CAN").
        channel: Channel number on that network (default 1).

    Returns:
        The signal's current physical value (float or int).
    """
    try:
        bus = conn.app.GetBus(network)
        sig = bus.GetSignal(channel, message, signal)
        return sig.Value
    except Exception as exc:
        raise CANoeError(
            f"Cannot read bus signal '{message}.{signal}' on {network} channel "
            f"{channel}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_namespace(conn: CANoeConnection, namespace: str):
    """
    Walk the namespace hierarchy separated by '::'.

    E.g. "Parent::Child" → Namespaces["Parent"].Namespaces["Child"]
    """
    parts = namespace.split("::")
    current = conn.system.Namespaces
    for part in parts[:-1]:
        try:
            current = current.Item(part).Namespaces
        except Exception as exc:
            raise CANoeError(
                f"Namespace segment '{part}' not found in '{namespace}': {exc}"
            ) from exc
    try:
        return current.Item(parts[-1])
    except Exception as exc:
        raise CANoeError(
            f"Namespace '{parts[-1]}' not found in '{namespace}': {exc}"
        ) from exc


def _safe_value(var) -> Any:
    try:
        return var.Value
    except Exception:
        return None


def _var_type_str(var) -> str:
    """Map COM type integer to a human-readable label."""
    _TYPE_MAP = {0: "integer", 1: "float", 2: "string", 3: "data"}
    try:
        return _TYPE_MAP.get(var.Type, f"unknown({var.Type})")
    except Exception:
        return "unknown"
