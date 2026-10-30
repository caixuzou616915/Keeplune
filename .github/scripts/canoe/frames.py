"""
frames.py
=========
OSI Layer 2 (Data Link): CAN / CAN FD frame send and receive monitoring.

PURPOSE
-------
Transmits raw CAN/CANFD frames and monitors received frames using a lightweight
CAPL bridge node.  Provides the lowest-level bus access available from Python.

SEND (write path):
  Python writes payload into PythonBridge SysVars, then toggles
  PythonBridge::FrameTrigger.  The CAPL node calls output() on the toggle.

MONITOR (read path):
  The CAPL node writes every received frame into PythonBridge::LastRxFrame*
  SysVars.  Python polls those vars to read captured frames.

MULTI-AGENT ROLE
----------------
Used by a **low-level stimulation agent** when no higher-level SysVar/EnvVar
exists for a signal.  Also used by a **traffic monitoring agent** to capture
and log bus traffic during a test sequence.

DEPENDENCIES
------------
- canoe_com.CANoeConnection (measurement must be running)
- PythonBridge SysVar namespace in CANoe (via CAPL helper node)
  Run ``python -m canoe frame capl`` to print the CAPL template
- No additional Python packages required

PUBLIC API  (conn = CANoeConnection)
----------
  send_frame(conn, channel, arb_id, data, is_canfd=False) -> None
  last_received_frame(conn)                               -> Optional[Dict]
  poll_frames(conn, duration_s, poll_interval_s)          -> List[Dict]
  print_capl_helper()                                     -> None

Constant:
  CAPL_HELPER_TEMPLATE  (str)  -- CAPL source for the PythonBridge node
"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional

from .canoe_com import CANoeConnection, CANoeError

# SysVar paths used for the CAPL bridge
_NS = "PythonBridge"
_VAR_CHANNEL  = "FrameChannel"
_VAR_ID       = "FrameID"
_VAR_IS_CANFD = "FrameIsCANFD"
_VAR_DLC      = "FrameDLC"
_VAR_DATA     = "FrameData"
_VAR_TRIGGER  = "FrameTrigger"
_VAR_RX_DATA  = "LastRxFrameData"
_VAR_RX_ID    = "LastRxFrameID"
_VAR_RX_CH    = "LastRxFrameChannel"
_VAR_RX_TS    = "LastRxFrameTimestamp"


def send_frame(
    conn: CANoeConnection,
    channel: int,
    arb_id: int,
    data: bytes,
    is_canfd: bool = False,
) -> None:
    """
    Transmit a CAN or CAN FD frame via the CAPL bridge node.

    Args:
        channel:   CAN channel number (1-based, as configured in CANoe).
        arb_id:    Arbitration ID (11-bit or 29-bit; add 0x80000000 for extended).
        data:      Payload bytes (max 8 for CAN, max 64 for CAN FD).
        is_canfd:  True to use CAN FD framing (BRS enabled by CAPL node).

    Raises:
        CANoeError: If measurement is not running or the bridge namespace
                    is missing (CAPL node not loaded).
    """
    if not conn.is_running:
        raise CANoeError("Measurement is not running — cannot send frames.")

    max_dlc = 64 if is_canfd else 8
    if len(data) > max_dlc:
        raise ValueError(
            f"Payload too long: {len(data)} bytes (max {max_dlc} for "
            f"{'CAN FD' if is_canfd else 'CAN'})"
        )

    from .signals import write_sysvar, read_sysvar

    try:
        write_sysvar(conn, _NS, _VAR_CHANNEL,  channel)
        write_sysvar(conn, _NS, _VAR_ID,       arb_id)
        write_sysvar(conn, _NS, _VAR_IS_CANFD, 1 if is_canfd else 0)
        write_sysvar(conn, _NS, _VAR_DLC,      len(data))
        write_sysvar(conn, _NS, _VAR_DATA,     bytes(data))
        # Toggle trigger: read current, flip it
        cur = int(read_sysvar(conn, _NS, _VAR_TRIGGER))
        write_sysvar(conn, _NS, _VAR_TRIGGER, 0 if cur else 1)
    except CANoeError:
        raise
    except Exception as exc:
        raise CANoeError(f"Frame send failed: {exc}") from exc


def last_received_frame(conn: CANoeConnection) -> Optional[Dict[str, Any]]:
    """
    Return the most recently captured frame written by the CAPL bridge node.

    Returns:
        Dict with keys: channel, id, timestamp_ms, data (bytes),
        or None if no frame has been captured yet.
    """
    from .signals import read_sysvar

    try:
        ts  = read_sysvar(conn, _NS, _VAR_RX_TS)
        if ts is None or ts == 0:
            return None
        return {
            "channel":      int(read_sysvar(conn, _NS, _VAR_RX_CH)),
            "id":           int(read_sysvar(conn, _NS, _VAR_RX_ID)),
            "timestamp_ms": float(ts),
            "data":         bytes(read_sysvar(conn, _NS, _VAR_RX_DATA) or b""),
        }
    except CANoeError:
        return None


def poll_frames(
    conn: CANoeConnection,
    duration_s: float = 1.0,
    poll_interval_s: float = 0.05,
) -> List[Dict[str, Any]]:
    """
    Poll the CAPL bridge RX SysVar for new frames over a given window.

    This is a best-effort monitor — individual frames may be missed if
    they arrive faster than the poll interval.  Use CANoe's built-in
    Trace/Logging for deterministic capture.

    Args:
        duration_s:      How long to poll (seconds).
        poll_interval_s: Sleep between polls (seconds).

    Returns:
        List of frame dicts captured during the window.
    """
    frames: List[Dict[str, Any]] = []
    seen_ts: Optional[float] = None
    deadline = time.monotonic() + duration_s

    while time.monotonic() < deadline:
        frame = last_received_frame(conn)
        if frame and frame["timestamp_ms"] != seen_ts:
            seen_ts = frame["timestamp_ms"]
            frames.append(frame)
        time.sleep(poll_interval_s)

    return frames


# ---------------------------------------------------------------------------
# CAPL helper node template (printed when user requests setup info)
# ---------------------------------------------------------------------------

CAPL_HELPER_TEMPLATE = """\
/*
 * PythonFrameHelper.can
 * Auto-generated CAPL node for Python <-> CANoe frame bridge.
 * Add this node to your CANoe configuration.
 *
 * SysVar namespace required: PythonBridge
 *   FrameChannel  (int)
 *   FrameID       (int)
 *   FrameIsCANFD  (int)
 *   FrameDLC      (int)
 *   FrameData     (data[64])
 *   FrameTrigger  (int)
 *   LastRxFrameID       (int)
 *   LastRxFrameChannel  (int)
 *   LastRxFrameTimestamp(float)
 *   LastRxFrameData     (data[64])
 */
variables { }

on sysvar_update PythonBridge::FrameTrigger
{
    message * txMsg;
    int dlc, ch, canfd;

    ch    = @PythonBridge::FrameChannel;
    dlc   = @PythonBridge::FrameDLC;
    canfd = @PythonBridge::FrameIsCANFD;

    txMsg.id  = @PythonBridge::FrameID;
    txMsg.dlc = dlc;
    sysGetVariableData(sysvar::PythonBridge::FrameData, txMsg.byte(0), dlc);

    if (canfd) {
        txMsg.MsgChannel = ch;
        output(txMsg);          // CAN FD output
    } else {
        txMsg.MsgChannel = ch;
        output(txMsg);          // CAN output
    }
}

on message *
{
    byte buf[64];
    @PythonBridge::LastRxFrameID        = this.id;
    @PythonBridge::LastRxFrameChannel   = this.MsgChannel;
    @PythonBridge::LastRxFrameTimestamp = timeNowFloat();
    sysSetVariableData(sysvar::PythonBridge::LastRxFrameData, this.byte(0), this.dlc);
}
"""


def print_capl_helper() -> None:
    """Print the CAPL helper node source that must be added to CANoe."""
    print(CAPL_HELPER_TEMPLATE)
