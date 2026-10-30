#!/usr/bin/env python3
# ==========================================================================
# (c) 2026  Continental
# --------------------------------------------------------------------------
# Project : Continental I2C Tool Code
# File    : i2c_cli.py  (.github/scripts/aardvark-i2c)
# --------------------------------------------------------------------------
# Headless command line front-end for the Total Phase Aardvark I2C adapter.
#
# This script is meant to be invoked directly from a shell (or by an AI
# agent / automation script) without requiring the Tkinter GUI in
# script/i2c_tools.py. Every invocation opens the Aardvark device, performs
# a single I2C transaction, prints a machine readable JSON result on stdout
# and closes the device again.
#
# Examples:
#   python i2c_cli.py list
#   python i2c_cli.py write   --target mon  --data "01 02 03"
#   python i2c_cli.py read    --target mon  --length 4
#   python i2c_cli.py write-read --target mon --data "01" --length 4
#   python i2c_cli.py reg-read  --target ser --reg 0x0105 --length 4 --reg-size 2
#   python i2c_cli.py reg-write --target ser --reg 0x10 --data "AA BB"
# ==========================================================================

from __future__ import division, with_statement, print_function

import argparse
import json
import os
import sys
from array import array

# Make sure aardvark_py (located next to this script) can always be imported,
# regardless of the current working directory the caller invokes us from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aardvark_py import (  # noqa: E402
    aa_open,
    aa_close,
    aa_find_devices_ext,
    aa_configure,
    aa_i2c_pullup,
    aa_target_power,
    aa_i2c_bitrate,
    aa_i2c_write,
    aa_i2c_read,
    aa_i2c_write_read,
    aa_status_string,
    AA_CONFIG_GPIO_I2C,
    AA_I2C_PULLUP_BOTH,
    AA_TARGET_POWER_BOTH,
    AA_I2C_NO_FLAGS,
    AA_PORT_NOT_FREE,
)

# ==========================================================================
# CONSTANTS
# ==========================================================================
DEFAULT_BITRATE_KHZ = 400

# Named address presets, matching the constants used by the GUI tool
# (see script/i2c_tools.py).
TARGET_PRESETS = {
    "mon": 0x1C,    # SLAVER_ADDR      - Monitor MCU
    "touch": 0x1D,  # TOUCH_SLAVER_ADDR - Touch MCU
    "ser": 0x40,    # SER_ADDR         - Serializer
    "des": 0x28,    # DES_ADDR         - Deserializer
}


# ==========================================================================
# HELPERS
# ==========================================================================
def _parse_int(value):
    """Parse a decimal or 0x-prefixed hex integer string."""
    return int(value, 16) if value.lower().startswith("0x") else int(value)


def _parse_hex_bytes(text):
    """Parse a whitespace separated hex byte string, e.g. '01 02 0A' -> array('B', [...])."""
    if text is None:
        return array("B", [])
    cleaned = text.replace(",", " ").split()
    try:
        return array("B", [int(b, 16) for b in cleaned])
    except ValueError as exc:
        raise ValueError("Invalid hex byte data: %r (%s)" % (text, exc))


def _bytes_to_hex(data):
    return " ".join("%02X" % b for b in data)


def _resolve_addr(args):
    if args.addr is not None:
        return _parse_int(args.addr)
    if args.target is not None:
        return TARGET_PRESETS[args.target]
    raise ValueError("Either --addr or --target must be specified")


def _result(ok, **fields):
    out = {"ok": ok}
    out.update(fields)
    print(json.dumps(out))
    return 0 if ok else 1


def _error(message, **fields):
    return _result(False, error=message, **fields)


def find_devices():
    """Return a list of dicts describing every attached Aardvark device."""
    num, ports, unique_ids = aa_find_devices_ext(16, 16)
    devices = []
    for i in range(num):
        port = ports[i]
        unique_id = unique_ids[i]
        in_use = bool(port & AA_PORT_NOT_FREE)
        port = port & ~AA_PORT_NOT_FREE
        devices.append({
            "port": port,
            "in_use": in_use,
            "serial": "%04d-%06d" % (unique_id // 1000000, unique_id % 1000000),
        })
    return devices


def open_device(port, bitrate_khz):
    """Open (and configure) an Aardvark device.

    If `port` is None, the first free device is used automatically.
    Returns (handle, port, actual_bitrate). Raises RuntimeError on failure.
    """
    if port is None:
        devices = find_devices()
        free_devices = [d for d in devices if not d["in_use"]]
        if not free_devices:
            raise RuntimeError("No free Aardvark device found. Devices seen: %s" % devices)
        port = free_devices[0]["port"]

    handle = aa_open(port)
    if handle <= 0:
        raise RuntimeError("Unable to open Aardvark device on port %d (error code %d)" % (port, handle))

    aa_configure(handle, AA_CONFIG_GPIO_I2C)
    aa_i2c_pullup(handle, AA_I2C_PULLUP_BOTH)
    aa_target_power(handle, AA_TARGET_POWER_BOTH)
    actual_bitrate = aa_i2c_bitrate(handle, bitrate_khz)

    return handle, port, actual_bitrate


# ==========================================================================
# COMMANDS
# ==========================================================================
def cmd_list(args):
    devices = find_devices()
    return _result(True, devices=devices, count=len(devices))


def cmd_write(args):
    addr = _resolve_addr(args)
    data_out = _parse_hex_bytes(args.data)
    if len(data_out) == 0:
        return _error("No data given (--data)")

    try:
        handle, port, bitrate = open_device(args.port, args.bitrate)
    except RuntimeError as exc:
        return _error(str(exc))

    try:
        count = aa_i2c_write(handle, addr, AA_I2C_NO_FLAGS, data_out)
        if count < 0:
            return _error(aa_status_string(count), port=port, addr=addr)
        if count != len(data_out):
            return _error(
                "Only wrote %d of %d bytes (check slave address / wiring)" % (count, len(data_out)),
                port=port, addr=addr,
            )
        return _result(True, port=port, addr=addr, bitrate_khz=bitrate,
                        bytes_written=count, data_sent=_bytes_to_hex(data_out))
    finally:
        aa_close(handle)


def cmd_read(args):
    addr = _resolve_addr(args)
    if args.length <= 0:
        return _error("--length must be a positive integer")

    try:
        handle, port, bitrate = open_device(args.port, args.bitrate)
    except RuntimeError as exc:
        return _error(str(exc))

    try:
        count, data_in = aa_i2c_read(handle, addr, AA_I2C_NO_FLAGS, args.length)
        if count < 0:
            return _error(aa_status_string(count), port=port, addr=addr)
        if count == 0:
            return _error("No bytes read (check slave address / wiring)", port=port, addr=addr)
        return _result(True, port=port, addr=addr, bitrate_khz=bitrate,
                        bytes_read=count, data=_bytes_to_hex(data_in))
    finally:
        aa_close(handle)


def cmd_write_read(args):
    addr = _resolve_addr(args)
    data_out = _parse_hex_bytes(args.data)
    if len(data_out) == 0:
        return _error("No data given (--data)")
    if args.length <= 0:
        return _error("--length must be a positive integer")

    try:
        handle, port, bitrate = open_device(args.port, args.bitrate)
    except RuntimeError as exc:
        return _error(str(exc))

    try:
        status, num_written, data_in, num_read = aa_i2c_write_read(
            handle, addr, AA_I2C_NO_FLAGS, data_out, args.length)
        if num_written <= 0 or num_written != len(data_out):
            return _error(
                "Write failed or partial (%d of %d bytes)" % (max(num_written, 0), len(data_out)),
                port=port, addr=addr,
            )
        if num_read != args.length:
            return _error(
                "Read %d of %d expected bytes" % (num_read, args.length),
                port=port, addr=addr, data=_bytes_to_hex(data_in),
            )
        return _result(True, port=port, addr=addr, bitrate_khz=bitrate,
                        data_sent=_bytes_to_hex(data_out), bytes_read=num_read,
                        data=_bytes_to_hex(data_in))
    finally:
        aa_close(handle)


def cmd_reg_read(args):
    addr = _resolve_addr(args)
    reg = _parse_int(args.reg)
    if args.length <= 0:
        return _error("--length must be a positive integer")

    if args.reg_size == 1:
        data_out = array("B", [reg & 0xFF])
    else:
        data_out = array("B", [(reg >> 8) & 0xFF, reg & 0xFF])

    try:
        handle, port, bitrate = open_device(args.port, args.bitrate)
    except RuntimeError as exc:
        return _error(str(exc))

    try:
        status, num_written, data_in, num_read = aa_i2c_write_read(
            handle, addr, AA_I2C_NO_FLAGS, data_out, args.length)
        if num_written <= 0 or num_written != len(data_out):
            return _error(
                "Failed to write register address (%d of %d bytes)" % (max(num_written, 0), len(data_out)),
                port=port, addr=addr, reg=reg,
            )
        if num_read != args.length:
            return _error(
                "Read %d of %d expected bytes" % (num_read, args.length),
                port=port, addr=addr, reg=reg, data=_bytes_to_hex(data_in),
            )
        return _result(True, port=port, addr=addr, bitrate_khz=bitrate, reg=hex(reg),
                        bytes_read=num_read, data=_bytes_to_hex(data_in))
    finally:
        aa_close(handle)


def cmd_reg_write(args):
    addr = _resolve_addr(args)
    reg = _parse_int(args.reg)
    reg_bytes = [reg & 0xFF] if args.reg_size == 1 else [(reg >> 8) & 0xFF, reg & 0xFF]
    data_out = array("B", reg_bytes + list(_parse_hex_bytes(args.data)))

    try:
        handle, port, bitrate = open_device(args.port, args.bitrate)
    except RuntimeError as exc:
        return _error(str(exc))

    try:
        count = aa_i2c_write(handle, addr, AA_I2C_NO_FLAGS, data_out)
        if count < 0:
            return _error(aa_status_string(count), port=port, addr=addr, reg=hex(reg))
        if count != len(data_out):
            return _error(
                "Only wrote %d of %d bytes (check slave address / wiring)" % (count, len(data_out)),
                port=port, addr=addr, reg=hex(reg),
            )
        return _result(True, port=port, addr=addr, bitrate_khz=bitrate, reg=hex(reg),
                        bytes_written=count, data_sent=_bytes_to_hex(data_out))
    finally:
        aa_close(handle)


# ==========================================================================
# ARGUMENT PARSING
# ==========================================================================
def _add_common_args(parser):
    parser.add_argument("--port", type=int, default=None,
                         help="Aardvark port number (default: auto-detect first free device)")
    parser.add_argument("--bitrate", type=int, default=DEFAULT_BITRATE_KHZ,
                         help="I2C bitrate in kHz (default: %d)" % DEFAULT_BITRATE_KHZ)
    addr_group = parser.add_mutually_exclusive_group(required=True)
    addr_group.add_argument("--addr", type=str, default=None,
                             help="I2C slave address, decimal or 0x-hex (e.g. 0x40)")
    addr_group.add_argument("--target", type=str, choices=sorted(TARGET_PRESETS),
                             default=None,
                             help="Named address preset: " +
                             ", ".join("%s=0x%02X" % (k, v) for k, v in TARGET_PRESETS.items()))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="i2c_cli.py",
        description="Headless CLI for sending/receiving I2C messages via a Total Phase Aardvark adapter. "
                    "Every command prints one JSON object on stdout.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List attached Aardvark devices")
    p_list.set_defaults(func=cmd_list)

    p_write = sub.add_parser("write", help="Write raw bytes to an I2C slave")
    _add_common_args(p_write)
    p_write.add_argument("--data", required=True, help="Hex bytes to send, e.g. \"01 02 03\"")
    p_write.set_defaults(func=cmd_write)

    p_read = sub.add_parser("read", help="Read raw bytes from an I2C slave")
    _add_common_args(p_read)
    p_read.add_argument("--length", type=int, required=True, help="Number of bytes to read")
    p_read.set_defaults(func=cmd_read)

    p_wr = sub.add_parser("write-read", help="Atomic write then read (no stop condition in between)")
    _add_common_args(p_wr)
    p_wr.add_argument("--data", required=True, help="Hex bytes to send, e.g. \"01\"")
    p_wr.add_argument("--length", type=int, required=True, help="Number of bytes to read back")
    p_wr.set_defaults(func=cmd_write_read)

    p_regr = sub.add_parser("reg-read", help="Write a register address then read its value(s)")
    _add_common_args(p_regr)
    p_regr.add_argument("--reg", required=True, help="Register address, decimal or 0x-hex")
    p_regr.add_argument("--reg-size", type=int, choices=(1, 2), default=1,
                         help="Register address width in bytes (default: 1)")
    p_regr.add_argument("--length", type=int, required=True, help="Number of bytes to read")
    p_regr.set_defaults(func=cmd_reg_read)

    p_regw = sub.add_parser("reg-write", help="Write a register address followed by data bytes")
    _add_common_args(p_regw)
    p_regw.add_argument("--reg", required=True, help="Register address, decimal or 0x-hex")
    p_regw.add_argument("--reg-size", type=int, choices=(1, 2), default=1,
                         help="Register address width in bytes (default: 1)")
    p_regw.add_argument("--data", required=True, help="Hex bytes to write after the register address")
    p_regw.set_defaults(func=cmd_reg_write)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        return _error(str(exc))
    except Exception as exc:  # pragma: no cover - safety net for unexpected hardware errors
        return _error("Unexpected error: %s" % exc)


if __name__ == "__main__":
    sys.exit(main())
