"""
diagnostics.py
==============
OSI Layer 4 (Transport): UDS / ISO-TP / DoIP diagnostic services.

PURPOSE
-------
Sends UDS requests to ECUs and parses responses using CANoe's built-in
DiagnosticDevices COM collection.  Supports CAN/ISO-TP and Ethernet/DoIP
transport depending on the diagnostic device configuration in the CANoe project.

MULTI-AGENT ROLE
----------------
Used by a **diagnostic verification agent** that checks ECU health after
stimulation: read active session, read/write DIDs, read/clear DTCs, ECU reset.
The device name (e.g. "MyECU") is read from canoe_agent.json
(key: diagnostic_devices[0]).

DEPENDENCIES
------------
- canoe_com.CANoeConnection (measurement must be running)
- DiagnosticDevices configured in CANoe with a valid CDD/PDX/ODX description
- canoe_agent.json for DoIP addressing (falls back to built-in defaults)
- No additional Python packages required

UDS SERVICE IDs (common)
------------------------
  0x10  DiagnosticSessionControl    0x11  ECUReset
  0x14  ClearDiagnosticInformation  0x19  ReadDTCInformation
  0x22  ReadDataByIdentifier        0x27  SecurityAccess
  0x2E  WriteDataByIdentifier

PUBLIC API  (conn = CANoeConnection)
----------
  list_diagnostic_devices(conn)                           -> List[str]
  send_uds_request(conn, device, service_id, ...)         -> Dict
  read_dtcs(conn, device, status_mask=0xFF)               -> Dict
  clear_dtcs(conn, device)                                -> Dict
  read_data_by_id(conn, device, did)                      -> Dict
  write_data_by_id(conn, device, did, value)              -> Dict
  ecu_reset(conn, device, reset_type=0x01)                -> Dict
  session_control(conn, device, session=0x01)             -> Dict
  doip_entity_info(workspace_root=None)                   -> Dict
"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional

from .canoe_com import CANoeConnection, CANoeError


# ---------------------------------------------------------------------------
# Device discovery
# ---------------------------------------------------------------------------

def list_diagnostic_devices(conn: CANoeConnection) -> List[str]:
    """Return the names of all diagnostic devices in the current configuration."""
    try:
        devs = conn.app.DiagnosticDevices
        return [devs.Item(i).Name for i in range(1, devs.Count + 1)]
    except Exception as exc:
        raise CANoeError(f"Cannot list DiagnosticDevices: {exc}") from exc


# ---------------------------------------------------------------------------
# Generic service request
# ---------------------------------------------------------------------------

def send_uds_request(
    conn: CANoeConnection,
    device_name: str,
    service_id: int,
    sub_function: Optional[int] = None,
    data: Optional[bytes] = None,
    timeout_s: float = 5.0,
) -> Dict[str, Any]:
    """
    Send a raw UDS service request to a diagnostic device and wait for response.

    Args:
        device_name:  Name of the DiagnosticDevice in CANoe (see `python -m canoe diag list`).
        service_id:   UDS service byte (e.g. 0x22).
        sub_function: Optional sub-function / parameter byte.
        data:         Optional additional payload bytes.
        timeout_s:    Response wait timeout in seconds.

    Returns:
        Dict with keys:
          - service_id  (int)
          - positive    (bool)
          - response_id (int)
          - data        (bytes)
          - raw         (str hex)
    """
    if not conn.is_running:
        raise CANoeError("Measurement is not running — cannot send diagnostic request.")

    try:
        dev = conn.app.DiagnosticDevices.Item(device_name)
    except Exception as exc:
        raise CANoeError(
            f"DiagnosticDevice '{device_name}' not found.  "
            f"Available: {list_diagnostic_devices(conn)}.  Detail: {exc}"
        ) from exc

    # Build the raw byte sequence
    payload = bytes([service_id])
    if sub_function is not None:
        payload += bytes([sub_function])
    if data:
        payload += bytes(data)

    try:
        request = dev.CreateRequest()
        request.SetBytes(payload)
        response = request.SendAndWaitForResponse(int(timeout_s * 1000))

        resp_bytes = bytes(response.GetBytes())
        pos_sid = service_id | 0x40

        return {
            "service_id":  service_id,
            "positive":    len(resp_bytes) > 0 and resp_bytes[0] == pos_sid,
            "response_id": resp_bytes[0] if resp_bytes else None,
            "data":        resp_bytes[1:] if len(resp_bytes) > 1 else b"",
            "raw":         resp_bytes.hex(),
        }
    except Exception as exc:
        raise CANoeError(f"Diagnostic request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Convenience wrappers for common UDS services
# ---------------------------------------------------------------------------

def read_dtcs(
    conn: CANoeConnection,
    device_name: str,
    status_mask: int = 0xFF,
) -> Dict[str, Any]:
    """
    Read DTC information (UDS 0x19, sub-function 0x02 — reportDTCByStatusMask).

    Args:
        device_name: Diagnostic device name.
        status_mask: DTC status mask byte (default 0xFF = all).

    Returns:
        Response dict from send_uds_request.
    """
    return send_uds_request(
        conn, device_name,
        service_id=0x19,
        sub_function=0x02,
        data=bytes([status_mask]),
    )


def clear_dtcs(conn: CANoeConnection, device_name: str) -> Dict[str, Any]:
    """
    Clear all DTCs (UDS 0x14, group-of-DTC = 0xFFFFFF).
    """
    return send_uds_request(
        conn, device_name,
        service_id=0x14,
        data=bytes([0xFF, 0xFF, 0xFF]),
    )


def read_data_by_id(
    conn: CANoeConnection,
    device_name: str,
    did: int,
) -> Dict[str, Any]:
    """
    Read a data identifier (UDS 0x22 ReadDataByIdentifier).

    Args:
        device_name: Diagnostic device name.
        did:         2-byte data identifier (e.g. 0xF186 for ActiveSession).

    Returns:
        Response dict; .data contains the DID value bytes.
    """
    return send_uds_request(
        conn, device_name,
        service_id=0x22,
        data=did.to_bytes(2, "big"),
    )


def write_data_by_id(
    conn: CANoeConnection,
    device_name: str,
    did: int,
    value: bytes,
) -> Dict[str, Any]:
    """
    Write a data identifier (UDS 0x2E WriteDataByIdentifier).
    """
    return send_uds_request(
        conn, device_name,
        service_id=0x2E,
        data=did.to_bytes(2, "big") + bytes(value),
    )


def ecu_reset(
    conn: CANoeConnection,
    device_name: str,
    reset_type: int = 0x01,
) -> Dict[str, Any]:
    """
    ECU Reset (UDS 0x11).

    Args:
        reset_type: 0x01=hardReset, 0x02=keyOffOnReset, 0x03=softReset.
    """
    return send_uds_request(
        conn, device_name,
        service_id=0x11,
        sub_function=reset_type,
    )


def session_control(
    conn: CANoeConnection,
    device_name: str,
    session: int = 0x01,
) -> Dict[str, Any]:
    """
    DiagnosticSessionControl (UDS 0x10).

    Args:
        session: 0x01=default, 0x02=programming, 0x03=extended.
    """
    return send_uds_request(
        conn, device_name,
        service_id=0x10,
        sub_function=session,
    )


# ---------------------------------------------------------------------------
# DoIP helpers
# ---------------------------------------------------------------------------

DOIP_PORT = 13400

def doip_entity_info(workspace_root: Optional[str] = None) -> Dict[str, Any]:
    """
    Return DoIP addressing for this workspace.
    Reads from canoe_agent.json if available, otherwise returns
    the static defaults from canoe_agent.json.
    """
    import os
    from .discover import load_config
    config = load_config()
    doip = config.get("doip", {})
    return {
        "tester_ipv6":   doip.get("tester_ipv6",  ""),
        "target_ipv6":   doip.get("target_ipv6",  ""),
        "tester_port":   doip.get("tester_port",  0),
        "target_port":   doip.get("target_port",  0),
        "doip_udp_port": DOIP_PORT,
        "source":        "canoe_agent.json" if doip else "built-in default",
    }
