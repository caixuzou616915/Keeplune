"""
network_layer.py
================
OSI Layer 3 (Network): AUTOSAR NM state machine and Ethernet/IP/UDP.

PURPOSE
-------
Monitors Network Management (NM) state transitions and provides Ethernet
addressing information.  NM state is exposed by CAPL nodes via SysVars or
EnvVars.  Detection order: canoe_agent.json → built-in candidate list.

NM STATE MACHINE (AUTOSAR)
--------------------------
  1  BusSleepMode          2  PrepareBusSleepMode
  3  ReadySleepMode        4  NormalOperationMode
  5  RepeatMessageMode

MULTI-AGENT ROLE
----------------
Used by a **network health agent** to verify the bus woke up correctly after
KL15 ON, and that all nodes reached NormalOperationMode before a test
sequence begins.  An orchestrator can gate test steps on NM state.

DEPENDENCIES
------------
- canoe_com.CANoeConnection
- signals.py (read_sysvar / read_envvar)
- canoe_agent.json for NM SysVar name and DoIP addressing
- socket (stdlib) for raw UDP outside CANoe simulation
- No additional Python packages required

PUBLIC API  (conn = CANoeConnection)
----------
  get_nm_state(conn, channel_hint="")      -> Dict  # source/namespace/variable/raw_value/state_name
  list_network_nodes(conn)                 -> List[Dict]  # name/channel_count
  ethernet_addressing_info(workspace_root) -> Dict
  send_udp_outside_canoe(dest_ipv6, dest_port, payload, ...) -> None
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from .canoe_com import CANoeConnection, CANoeError


# ---------------------------------------------------------------------------
# NM state helpers
# ---------------------------------------------------------------------------

# Standard AUTOSAR NM state codes
_NM_STATES = {
    0: "Uninit",
    1: "BusSleepMode",
    2: "PrepareBusSleepMode",
    3: "ReadySleepMode",
    4: "NormalOperationMode",
    5: "RepeatMessageMode",
    6: "SynchronisedMode",
}

# Known SysVar / EnvVar names for NM state in this workspace
# (adjust if your CANoe config uses different names)
_NM_SYSVAR_CANDIDATES = [
    ("NM",         "NM_State"),
    ("NM",         "CurrentState"),
    ("CANoe::NM",  "NMState"),
]

_NM_ENVVAR_CANDIDATES = [
    "NM_State",
    "NM_BusState",
]


def get_nm_state(conn: CANoeConnection, channel_hint: str = "") -> Dict[str, Any]:
    """
    Read the current NM state.
    Checks canoe_agent.json first, then falls back to scanning known patterns.
    """
    import os
    from .signals import read_sysvar, read_envvar
    from .discover import load_config

    config = load_config()

    # Build candidate list: config entry first, then built-in patterns
    sysvar_candidates = list(_NM_SYSVAR_CANDIDATES)
    if config.get("nm_sysvar"):
        nm = config["nm_sysvar"]
        sysvar_candidates.insert(0, (nm["namespace"], nm["variable"]))

    for ns, var in sysvar_candidates:
        if channel_hint and channel_hint.upper() not in (ns + var).upper():
            continue
        try:
            val = read_sysvar(conn, ns, var)
            return {
                "source":     "sysvar",
                "namespace":  ns,
                "variable":   var,
                "raw_value":  val,
                "state_name": _NM_STATES.get(int(val), f"unknown({val})"),
            }
        except CANoeError:
            pass

    for var in _NM_ENVVAR_CANDIDATES:
        if channel_hint and channel_hint.upper() not in var.upper():
            continue
        try:
            val = read_envvar(conn, var)
            return {
                "source":     "envvar",
                "namespace":  None,
                "variable":   var,
                "raw_value":  val,
                "state_name": _NM_STATES.get(int(val), f"unknown({val})"),
            }
        except CANoeError:
            pass

    raise CANoeError(
        "NM state variable not found.  "
        "Set 'nm_sysvar' in canoe_agent.json (namespace + variable), "
        "or run 'python -m canoe signal sysvar namespaces' to find the correct namespace."
    )


def list_network_nodes(conn: CANoeConnection) -> List[Dict[str, Any]]:
    """
    Enumerate all networks and their channel counts via the COM Networks collection.

    Returns:
        List of dicts with keys: name, channel_count.
    """
    result = []
    try:
        nets = conn.networks
        for i in range(1, nets.Count + 1):
            net = nets.Item(i)
            try:
                ch_count = net.Channels.Count
            except Exception:
                ch_count = None
            result.append({"name": net.Name, "channel_count": ch_count})
    except Exception as exc:
        raise CANoeError(f"Cannot enumerate networks: {exc}") from exc
    return result


# ---------------------------------------------------------------------------
# Ethernet / IP addressing info
# ---------------------------------------------------------------------------

def ethernet_addressing_info(workspace_root: Optional[str] = None) -> Dict[str, Any]:
    """
    Return the IPv6/UDP addressing for the Ethernet test setup.
    Reads from canoe_agent.json when available.
    """
    import os
    from .discover import load_config
    config = load_config()
    doip = config.get("doip", {})
    return {
        "tester_ipv6_addr": doip.get("tester_ipv6", ""),
        "target_ipv6_addr": doip.get("target_ipv6", ""),
        "tester_udp_port":  doip.get("tester_port",  0),
        "target_udp_port":  doip.get("target_port",  0),
        "mtu_bytes":        1472,
        "source":           "canoe_agent.json" if doip else "built-in default",
    }


def send_udp_outside_canoe(
    dest_ipv6: str,
    dest_port: int,
    payload: bytes,
    src_ipv6: str = "",
    src_port: int = 0,
) -> None:
    """
    Send a UDP datagram directly from Python (bypasses CANoe simulation).

    Useful for stimulating the real or virtual network interface that CANoe
    is capturing, or for testing hardware-in-the-loop setups.

    Args:
        dest_ipv6: Destination IPv6 address string.
        dest_port: Destination UDP port.
        payload:   Raw bytes to send.
        src_ipv6:  Source IPv6 address (bind address).
        src_port:  Source UDP port.
    """
    import socket

    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    try:
        sock.bind((src_ipv6, src_port))
        sock.sendto(bytes(payload), (dest_ipv6, dest_port))
    except OSError as exc:
        raise CANoeError(f"UDP send failed: {exc}") from exc
    finally:
        sock.close()
