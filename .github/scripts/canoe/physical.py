"""
physical.py
===========
OSI Layer 1 (Physical): CAN/CANFD bus statistics and error injection.

PURPOSE
-------
Reads per-channel bus load, error counts and message counters from CANoe's
Networks COM collection.  Injects CAN error frames via the PythonBridge
CAPL helper node to test ECU robustness.

BUS STATISTICS METRICS
----------------------
  bus_load_pct    current bus utilisation (0.0–100.0 %)
  peak_load_pct   peak load since measurement start
  error_count     total CAN error frame count
  overload_count  CAN overload frame count
  tx_messages     messages transmitted
  rx_messages     messages received

ERROR TYPES  (ErrorType class constants)
----------------------------------------
  BIT_ERROR=1  STUFF_ERROR=2  CRC_ERROR=3
  FORM_ERROR=4  ACK_ERROR=5  BUS_OFF=6

MULTI-AGENT ROLE
----------------
Used by a **bus health / robustness agent** to:
  - Assert bus load stays within spec during a test sequence
  - Inject errors and verify the ECU recovers
  - Confirm zero new errors appeared after a test step

DEPENDENCIES
------------
- canoe_com.CANoeConnection (measurement must be running)
- network_layer.list_network_nodes() used by get_all_statistics()
- PythonBridge SysVar namespace (for inject_error only)
  Run ``python -m canoe physical capl`` for the CAPL snippet
- No additional Python packages required

PUBLIC API  (conn = CANoeConnection)
----------
  get_channel_statistics(conn, network_name, channel_index=1) -> Dict
  get_all_statistics(conn)                                    -> List[Dict]
  inject_error(conn, channel, error_type=ErrorType.BIT_ERROR) -> None
  print_capl_error_injector()                                 -> None

Class ErrorType:
  BIT_ERROR, STUFF_ERROR, CRC_ERROR, FORM_ERROR, ACK_ERROR, BUS_OFF
"""

from __future__ import annotations
from typing import Any, Dict, List

from .canoe_com import CANoeConnection, CANoeError


# ---------------------------------------------------------------------------
# Bus statistics
# ---------------------------------------------------------------------------

def get_channel_statistics(
    conn: CANoeConnection,
    network_name: str,
    channel_index: int = 1,
) -> Dict[str, Any]:
    """
    Read bus load and error statistics for a CAN/CAN FD channel.

    Args:
        network_name:  Network name as shown in CANoe topology (e.g. "CAN").
        channel_index: 1-based channel index.

    Returns:
        Dict with keys: network, channel, bus_load_pct, peak_load_pct,
        error_count, overload_count, tx_messages, rx_messages.
    """
    try:
        net  = conn.networks.Item(network_name)
        chan = net.Channels.Item(channel_index)
        stats = chan.Statistics
        return {
            "network":        network_name,
            "channel":        channel_index,
            "bus_load_pct":   _safe_stat(stats, "BusLoad"),
            "peak_load_pct":  _safe_stat(stats, "PeakLoad"),
            "error_count":    _safe_stat(stats, "ErrorCount"),
            "overload_count": _safe_stat(stats, "OverloadCount"),
            "tx_messages":    _safe_stat(stats, "TxMessages"),
            "rx_messages":    _safe_stat(stats, "RxMessages"),
        }
    except CANoeError:
        raise
    except Exception as exc:
        raise CANoeError(
            f"Cannot read statistics for network '{network_name}' "
            f"channel {channel_index}: {exc}"
        ) from exc


def get_all_statistics(conn: CANoeConnection) -> List[Dict[str, Any]]:
    """
    Read statistics for every network/channel pair available in CANoe.

    Returns:
        List of channel-statistics dicts.
    """
    from .network_layer import list_network_nodes

    results = []
    for net_info in list_network_nodes(conn):
        n = net_info["name"]
        ch_count = net_info.get("channel_count") or 1
        for ch in range(1, (ch_count or 1) + 1):
            try:
                results.append(get_channel_statistics(conn, n, ch))
            except CANoeError:
                pass
    return results


# ---------------------------------------------------------------------------
# Error injection via CAPL bridge
# ---------------------------------------------------------------------------

class ErrorType:
    """Error type codes for the CAPL bridge error injector."""
    BIT_ERROR       = 1
    STUFF_ERROR     = 2
    CRC_ERROR       = 3
    FORM_ERROR      = 4
    ACK_ERROR       = 5
    BUS_OFF         = 6


def inject_error(
    conn: CANoeConnection,
    channel: int,
    error_type: int = ErrorType.BIT_ERROR,
) -> None:
    """
    Inject a CAN error on the specified channel via the CAPL bridge.

    Requires the PythonBridge SysVar namespace with:
        ErrorType    (int)
        ErrorChannel (int)
        ErrorTrigger (int)

    Args:
        channel:    CAN channel number (1-based).
        error_type: One of the ErrorType constants.
    """
    if not conn.is_running:
        raise CANoeError("Measurement is not running — cannot inject errors.")

    from .signals import write_sysvar, read_sysvar

    try:
        write_sysvar(conn, "PythonBridge", "ErrorChannel", channel)
        write_sysvar(conn, "PythonBridge", "ErrorType",    error_type)
        cur = int(read_sysvar(conn, "PythonBridge", "ErrorTrigger"))
        write_sysvar(conn, "PythonBridge", "ErrorTrigger", 0 if cur else 1)
    except CANoeError:
        raise
    except Exception as exc:
        raise CANoeError(f"Error injection failed: {exc}") from exc


CAPL_ERROR_INJECTOR_TEMPLATE = """\
/*
 * PythonErrorInjector section for PythonFrameHelper.can
 * Extend the existing PythonBridge namespace with:
 *   ErrorType    (int)
 *   ErrorChannel (int)
 *   ErrorTrigger (int)
 */
on sysvar_update PythonBridge::ErrorTrigger
{
    int errType = @PythonBridge::ErrorType;
    // CANoe's triggerError() CAPL function:
    // triggerError(channel, errorType, 1 /*single shot*/);
    // Error type mapping: 1=bit, 2=stuff, 3=crc, 4=form, 5=ack
    triggerError(@PythonBridge::ErrorChannel, errType, 1);
}
"""


def print_capl_error_injector() -> None:
    """Print the CAPL snippet needed for error injection support."""
    print(CAPL_ERROR_INJECTOR_TEMPLATE)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_stat(stats_obj, attr: str):
    try:
        return getattr(stats_obj, attr)
    except Exception:
        return None
