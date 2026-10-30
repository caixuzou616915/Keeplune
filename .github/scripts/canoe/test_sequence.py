"""
test_sequence.py
================
Generic, reusable stimulus-sequence runner for CANoe SysVar + bus-readback
verification.

PURPOSE
-------
Most test cases described in plain language -- "increment brightness by 1%
every second for 20s", "hold EyeBox position at 500 for 10s then release",
"sweep 0-100% in 10% steps" -- are just a parametrized ramp or a short list
of (value, hold_time) steps against ONE SysVar, with an optional bus-signal
readback check per step.

Rather than generating a new bespoke .py file per test case, this module
provides two generic, parametrized primitives that cover the vast majority
of stimulus test cases:

  run_ramp(...)     -- linear start->end sweep with fixed step/interval
  run_sequence(...) -- arbitrary explicit list of steps (value + hold_s)

Both are driven from the CLI:
  python -m canoe sequence ramp --namespace <NS> --variable <VAR> \\
      --start 0 --end 5120 --step 256 --interval 1.0 \\
      [--verify-message <Msg> --verify-signal <Sig>]
  python -m canoe sequence run-spec <spec.json>

...or imported directly for more complex one-off orchestration. A throwaway
script is still fine for genuinely custom multi-signal logic (see the
Live Verification Method), but it should import and reuse these primitives
rather than reimplementing the write/sleep/read loop from scratch every
time -- avoids duplicate near-identical sweep scripts accumulating per
test case.

PUBLIC API (conn = CANoeConnection)
----------
  run_ramp(conn, namespace, variable, start, end, step, interval_s,
           verify_message=None, verify_signal=None,
           verify_network="CAN", verify_channel=1, tolerance=0) -> Dict
  run_sequence(conn, namespace, variable, steps,
           verify_message=None, verify_signal=None,
           verify_network="CAN", verify_channel=1, tolerance=0) -> Dict
  write_report(result, out_dir, name) -> Dict[str, str]   # {"json": path, "html": path}

Both runner functions return a dict:
  {
    "namespace": ..., "variable": ...,
    "verify": {...} | None,
    "started_utc": "YYYY-MM-DD HH:MM:SS UTC",
    "finished_utc": "YYYY-MM-DD HH:MM:SS UTC",
    "steps": [ {"index", "value_written", "t_utc", "sysvar_readback",
                "bus_readback", "pass"}, ... ],
    "overall_pass": bool | None,   # None if no verify signal configured
  }
"""

from __future__ import annotations
import datetime
import json
import os
import time
from typing import Any, Dict, List, Optional

from .canoe_com import CANoeConnection
from .signals import write_sysvar, read_sysvar, read_bus_signal


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _normalize(value: Any) -> Any:
    """Whole-number floats (e.g. from argparse type=float) must be sent as
    Python int, not float -- CANoe COM rejects assigning a float to an
    integer-typed SysVar with a generic COM exception."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _trigger_edge(conn: CANoeConnection, namespace: str, variable: str, settle_s: float = 0.1) -> None:
    """
    Force a real 0->1 edge on an edge-triggered CAPL SysVar (e.g. a
    'SysVar_Read_<DID>' diagnostic-request trigger). Many CAPL diagnostic
    testers use `on sysvar X { if (@this) {...} }` handlers that only fire on
    an actual VALUE CHANGE -- if a previous run already left the trigger at 1
    (never reset), writing 1 again is a silent no-op. Always reset to 0 first
    (with a short settle) if it's already non-zero, then write 1.
    """
    cur = read_sysvar(conn, namespace, variable)
    if cur:
        write_sysvar(conn, namespace, variable, 0)
        time.sleep(settle_s)
    write_sysvar(conn, namespace, variable, 1)


def _decode_did_value(data: Any, mode: str) -> Optional[int]:
    """Decode CAPL diagnostic response bytes with a configurable strategy.

    Supported modes:
      - uint16_be: first 2 bytes as big-endian uint16 (default)
      - uint16_le: first 2 bytes as little-endian uint16
      - uint8_0: first byte only
      - uint8_1: second byte only
    """
    if not data:
        return None
    raw = bytes(data)

    if mode == "uint16_be":
        if len(raw) < 2:
            return None
        return int.from_bytes(raw[:2], "big")
    if mode == "uint16_le":
        if len(raw) < 2:
            return None
        return int.from_bytes(raw[:2], "little")
    if mode == "uint8_0":
        if len(raw) < 1:
            return None
        return int(raw[0])
    if mode == "uint8_1":
        if len(raw) < 2:
            return None
        return int(raw[1])
    raise ValueError(f"Unsupported DID decode mode: {mode}")


def _run_steps(
    conn: CANoeConnection,
    namespace: str,
    variable: str,
    value_hold_pairs: List[tuple],
    verify_message: Optional[str],
    verify_signal: Optional[str],
    verify_network: str,
    verify_channel: int,
    tolerance: float,
    verify_did: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    verify_cfg = None
    if verify_message and verify_signal:
        verify_cfg = {
            "message": verify_message, "signal": verify_signal,
            "network": verify_network, "channel": verify_channel,
        }

    started = _utc_now()
    steps_out: List[Dict[str, Any]] = []

    # Re-initiate supplier session if DID verification is configured
    if verify_did:
        # Clear RX buffer
        write_sysvar(conn, "DIAGNOSTICS", "Sysvar_DIAG_ClearRxData", 1)
        time.sleep(0.1)
        # Set session to Supplier (0x60) and trigger the request
        write_sysvar(conn, "DIAGNOSTICS", "SysVar_SessionMode", 0x60)
        time.sleep(0.1)
        _trigger_edge(conn, "DIAGNOSTICS", "SysVar_SessionMode_Request")
        time.sleep(0.5)  # wait for session change to complete

    for i, item in enumerate(value_hold_pairs):
        value, hold_s = item[0], item[1]
        step_meta = item[2] if len(item) > 2 else {}
        value = _normalize(value)
        
        # Re-initiate supplier session before each step if DID verification is enabled
        if verify_did and i > 0 and i % 3 == 0:  # Re-init at start of each 3-step cycle
            write_sysvar(conn, "DIAGNOSTICS", "Sysvar_DIAG_ClearRxData", 1)
            time.sleep(0.1)
            write_sysvar(conn, "DIAGNOSTICS", "SysVar_SessionMode", 0x60)
            time.sleep(0.1)
            _trigger_edge(conn, "DIAGNOSTICS", "SysVar_SessionMode_Request")
            time.sleep(0.5)
        
        write_sysvar(conn, namespace, variable, value)
        time.sleep(max(hold_s, 0.15))  # includes settle time for the write itself

        sysvar_readback = read_sysvar(conn, namespace, variable)
        bus_readback = None
        bus_pass = None
        if verify_cfg:
            bus_readback = read_bus_signal(
                conn, verify_message, verify_signal,
                network=verify_network, channel=verify_channel,
            )
            bus_pass = abs(bus_readback - value) <= tolerance

        did_readback = None
        did_readback_raw_hex = None
        did_expected = None
        did_pass = None
        if verify_did:
            _trigger_edge(conn, verify_did["trigger_namespace"], verify_did["trigger_variable"])
            time.sleep(verify_did.get("wait_s", 0.3))  # allow the UDS request/response round-trip
            raw = read_sysvar(conn, verify_did["data_namespace"], verify_did["data_variable"])
            did_readback_raw_hex = bytes(raw).hex() if raw else None

            decode_mode = verify_did.get("decode", "uint16_be")
            did_readback = _decode_did_value(raw, decode_mode)

            # Expected DID value precedence:
            # 1) per-step explicit did_expected
            # 2) map from written value in verify_did["expected_by_value"]
            # 3) fallback to written value itself (legacy behavior)
            if "did_expected" in step_meta:
                did_expected = _normalize(step_meta.get("did_expected"))
            else:
                expected_by_value = verify_did.get("expected_by_value") or {}
                did_expected = expected_by_value.get(str(value), value)
                did_expected = _normalize(did_expected)

            did_pass = did_readback is not None and abs(did_readback - did_expected) <= tolerance

        # Combined step verdict: AND of whichever checks are configured; None if none configured.
        checks = [p for p in (bus_pass, did_pass) if p is not None]
        step_pass = all(checks) if checks else None

        steps_out.append({
            "index": i,
            "value_written": value,
            "hold_s": hold_s,
            "t_utc": _utc_now(),
            "sysvar_readback": sysvar_readback,
            "bus_readback": bus_readback,
            "bus_pass": bus_pass,
            "did_readback": did_readback,
            "did_readback_raw": did_readback_raw_hex,
            "did_expected": did_expected,
            "did_pass": did_pass,
            "pass": step_pass,
        })

    finished = _utc_now()
    checks_configured = verify_cfg is not None or verify_did is not None
    overall_pass = all(s["pass"] for s in steps_out) if checks_configured else None

    return {
        "namespace": namespace,
        "variable": variable,
        "verify": verify_cfg,
        "verify_did": verify_did,
        "started_utc": started,
        "finished_utc": finished,
        "steps": steps_out,
        "overall_pass": overall_pass,
    }


def run_ramp(
    conn: CANoeConnection,
    namespace: str,
    variable: str,
    start: float,
    end: float,
    step: float,
    interval_s: float,
    verify_message: Optional[str] = None,
    verify_signal: Optional[str] = None,
    verify_network: str = "CAN",
    verify_channel: int = 1,
    tolerance: float = 0,
    verify_did_trigger_ns: Optional[str] = None,
    verify_did_trigger_var: Optional[str] = None,
    verify_did_data_ns: Optional[str] = None,
    verify_did_data_var: Optional[str] = None,
    verify_did_wait_s: float = 0.3,
    verify_did_decode: str = "uint16_be",
    verify_did_expected_by_value: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Linear ramp of one SysVar from `start` to `end` (inclusive) in steps of
    `step`, holding each value for `interval_s` seconds, optionally verifying
    each step against a bus signal readback and/or a real UDS DID round-trip
    via this project's CAPL diagnostic tester (edge-trigger a
    'SysVar_Read_<X>' sysvar, then read the decoded response from a
    'SysVar_Data_<X>' sysvar) -- use this when there's no CANoe
    DiagnosticDevices/CDD configured, which is the common case for CAPL-only
    diagnostic testers.
    """
    if step == 0:
        raise ValueError("step must be non-zero")
    values: List[float] = []
    v = start
    ascending = step > 0
    while (v <= end) if ascending else (v >= end):
        values.append(v)
        v += step
    pairs = [(v, interval_s) for v in values]
    verify_did = None
    if verify_did_trigger_ns and verify_did_trigger_var and verify_did_data_ns and verify_did_data_var:
        verify_did = {
            "trigger_namespace": verify_did_trigger_ns, "trigger_variable": verify_did_trigger_var,
            "data_namespace": verify_did_data_ns, "data_variable": verify_did_data_var,
            "wait_s": verify_did_wait_s,
            "decode": verify_did_decode,
            "expected_by_value": verify_did_expected_by_value or {},
        }
    return _run_steps(conn, namespace, variable, pairs,
                       verify_message, verify_signal, verify_network, verify_channel, tolerance,
                       verify_did=verify_did)


def run_sequence(
    conn: CANoeConnection,
    namespace: str,
    variable: str,
    steps: List[Dict[str, Any]],
    verify_message: Optional[str] = None,
    verify_signal: Optional[str] = None,
    verify_network: str = "CAN",
    verify_channel: int = 1,
    tolerance: float = 0,
    verify_did_trigger_ns: Optional[str] = None,
    verify_did_trigger_var: Optional[str] = None,
    verify_did_data_ns: Optional[str] = None,
    verify_did_data_var: Optional[str] = None,
    verify_did_wait_s: float = 0.3,
    verify_did_decode: str = "uint16_be",
    verify_did_expected_by_value: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Arbitrary explicit sequence: `steps` is a list of {"value": ..., "hold_s": ...} dicts.
    Use this for non-linear step lists that `run_ramp` can't express. Same
    optional bus/DID verification as `run_ramp`.
    """
    pairs = [(s["value"], s.get("hold_s", 1.0), s) for s in steps]
    verify_did = None
    if verify_did_trigger_ns and verify_did_trigger_var and verify_did_data_ns and verify_did_data_var:
        verify_did = {
            "trigger_namespace": verify_did_trigger_ns, "trigger_variable": verify_did_trigger_var,
            "data_namespace": verify_did_data_ns, "data_variable": verify_did_data_var,
            "wait_s": verify_did_wait_s,
            "decode": verify_did_decode,
            "expected_by_value": verify_did_expected_by_value or {},
        }
    return _run_steps(conn, namespace, variable, pairs,
                       verify_message, verify_signal, verify_network, verify_channel, tolerance,
                       verify_did=verify_did)


def write_report(result: Dict[str, Any], out_dir: str, name: str) -> Dict[str, str]:
    """Write both a JSON and a simple HTML report for any test_sequence result
    (run_ramp / run_sequence / run_diag_session_cycle). The HTML table columns
    are generated dynamically from the union of keys across all steps, so
    this works for any step-dict shape, not just the ramp/sequence bus+DID
    fields."""
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, f"{name}.json")
    html_path = os.path.join(out_dir, f"{name}.html")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    steps = result.get("steps", [])
    # Raw positive/negative booleans are confusing side-by-side -- the
    # computed 'uds_response' text column (added by run_diag_session_cycle)
    # already conveys the same information clearly, so hide the raw pair
    # from the human-readable HTML table (they still remain in the JSON).
    HIDDEN_COLUMNS = {"positive", "negative"}
    BOOL_ICON = {True: "\u2713", False: "\u2717"}

    columns: List[str] = []
    for s in steps:
        for k in s.keys():
            if k not in columns and k not in HIDDEN_COLUMNS:
                columns.append(k)

    def _format_cell(col: str, value: Any) -> str:
        if col == "pass":
            css = "pass-true" if value else "pass-false"
            label = "\u2713 PASS" if value else "\u2717 FAIL"
            return f'<td class="{css}">{label}</td>'
        if isinstance(value, bool):
            return f"<td>{BOOL_ICON[value]}</td>"
        if value is None:
            return "<td>\u2013</td>"
        return f"<td>{value}</td>"

    header = "".join(f"<th>{c}</th>" for c in columns)
    rows = "\n".join(
        "<tr>" + "".join(_format_cell(c, s.get(c)) for c in columns) + "</tr>"
        for s in steps
    )
    verify_note = ""
    if result.get("verify"):
        verify_note = (f"reading back the bus signal <code>{result['verify']['message']}."
                       f"{result['verify']['signal']}</code> ")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{name}</title>
<style>
body {{ font-family: sans-serif; }}
table {{ border-collapse: collapse; }}
td, th {{ border: 1px solid #ccc; padding: 4px 8px; }}
.pass-true {{ color: green; }} .pass-false {{ color: red; }}
</style></head><body>
<h1>{name}</h1>
<h2>Methodology / Steps Performed</h2>
<p>{verify_note}Run window: {result.get('started_utc')} to {result.get('finished_utc')}.</p>
<h2>Overall result: {result.get('overall_pass')}</h2>
<table>
<tr>{header}</tr>
{rows}
</table>
</body></html>"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return {"json": json_path, "html": html_path}


# ---------------------------------------------------------------------------
# Generic diagnostic session-cycle + arbitrary-UDS-request test
# ---------------------------------------------------------------------------

def run_diag_session_cycle(
    conn: CANoeConnection,
    sessions: List[Dict[str, Any]],
    request_bytes: bytes,
    session_ns: str = "DIAGNOSTICS",
    session_mode_var: str = "SysVar_SessionMode",
    session_request_var: str = "SysVar_SessionMode_Request",
    status_var: str = "SysVar_Status",
    tx_ns: str = "DIAGNOSTICS",
    tx_var: str = "Sysvar_DIAG_txData",
    send_var: str = "Sysvar_DIAG_Send",
    rx_ns: str = "DIAGNOSTICS",
    rx_var: str = "Sysvar_DIAG_rxData",
    session_wait_s: float = 1.0,
    request_wait_s: float = 1.0,
) -> Dict[str, Any]:
    """
    Generic, reusable diagnostic test: cycle through a list of UDS diagnostic
    sessions (e.g. Default/Extended/Supplier), and after each session change
    send the SAME arbitrary raw UDS request (e.g. a ReadDataByIdentifier
    `22 <DID_hi> <DID_lo>`), capturing the response each time.

    Works via this project's generic CAPL diagnostic tester SysVars (NOT tied
    to any specific DID's dedicated SysVar pair):
      - Session control: write `session_mode_var` then edge-trigger
        `session_request_var` (sends `10 <session>`).
      - Generic request: write `tx_var` (raw bytes) then edge-trigger
        `send_var`; response lands in `rx_var`.

    Args:
        sessions: list of {"name": str, "value": int} dicts, e.g.
            [{"name": "Default", "value": 1}, {"name": "Extended", "value": 3},
             {"name": "Supplier", "value": 0x60}]
        request_bytes: raw UDS request bytes sent after each session change.

    Returns a dict with the same shape as run_ramp/run_sequence
    ({"started_utc", "finished_utc", "steps", "overall_pass"}), so it can be
    persisted with the same `write_report()`.
    """
    started = _utc_now()
    steps_out: List[Dict[str, Any]] = []

    for entry in sessions:
        name, value = entry["name"], entry["value"]
        step: Dict[str, Any] = {"session_name": name, "session_value": value}

        write_sysvar(conn, session_ns, session_mode_var, value)
        _trigger_edge(conn, session_ns, session_request_var)
        time.sleep(session_wait_s)
        step["session_status"] = read_sysvar(conn, session_ns, status_var)
        step["session_mode_readback"] = read_sysvar(conn, session_ns, session_mode_var)

        write_sysvar(conn, rx_ns, rx_var, b"")
        time.sleep(0.1)
        write_sysvar(conn, tx_ns, tx_var, bytes(request_bytes))
        _trigger_edge(conn, tx_ns, send_var)
        time.sleep(request_wait_s)

        rx = read_sysvar(conn, rx_ns, rx_var)
        rx_bytes = bytes(b & 0xFF for b in rx) if rx else b""
        step["request_hex"] = bytes(request_bytes).hex()
        step["response_hex"] = rx_bytes.hex() if rx_bytes else None
        step["positive"] = bool(rx_bytes) and rx_bytes[0] == (request_bytes[0] | 0x40)
        step["negative"] = bool(rx_bytes) and rx_bytes[0] == 0x7F
        # Single, human-readable summary of positive/negative/no-response --
        # shown in the report instead of the raw positive/negative booleans.
        if step["positive"]:
            step["uds_response"] = "POSITIVE - ECU accepted the request"
        elif step["negative"]:
            step["uds_response"] = "NEGATIVE - ECU rejected the request"
        else:
            step["uds_response"] = "NO RESPONSE - request timed out"
        step["pass"] = step["positive"]
        step["t_utc"] = _utc_now()
        steps_out.append(step)

    finished = _utc_now()
    return {
        "sessions": sessions,
        "request_hex": bytes(request_bytes).hex(),
        "started_utc": started,
        "finished_utc": finished,
        "steps": steps_out,
        "overall_pass": all(s["pass"] for s in steps_out) if steps_out else None,
    }


# ---------------------------------------------------------------------------
# Write test spec to test_cases/ folder
# ---------------------------------------------------------------------------

def write_test_spec(spec_dict: Dict[str, Any], filename: str) -> str:
    """
    Write a test specification dict to test_cases/<filename>.json.
    
    Creates test_cases/ folder if it doesn't exist.
    
    Args:
        spec_dict: the test spec dict (with keys: namespace, variable, steps, etc.)
        filename: output filename (without path, e.g. "my_test.json")
    
    Returns:
        Full path to the written spec file.
    """
    test_cases_dir = os.path.join(os.getcwd(), "test_cases")
    os.makedirs(test_cases_dir, exist_ok=True)
    
    spec_path = os.path.join(test_cases_dir, filename)
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec_dict, f, indent=2)
    
    return spec_path
