---
name: aardvark-i2c
description: "Use when sending or receiving raw I2C messages via a Total Phase Aardvark adapter: write/read raw bytes, atomic write-read transactions, register read/write (1 or 2 byte register address), and device enumeration. Use for VW FID cluster I2C bring-up, monitor/touch MCU register access, serializer/deserializer register access, and any headless/AI-driven I2C automation."
argument-hint: "Describe the I2C operation, e.g. 'read 4 bytes from the monitor MCU', 'write register 0x0105 on the serializer', 'list attached Aardvark devices'."
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# Aardvark I2C Skill

## Overview

Headless CLI for talking to the I2C bus through a Total Phase Aardvark
adapter. Every invocation opens the device, performs exactly one I2C
transaction, prints a single JSON result, and closes the device again —
safe to call repeatedly from an agent loop.

## When to Use

Use this skill whenever you need to talk to the I2C bus through a Total Phase
Aardvark adapter:

- Enumerate attached Aardvark devices and their free/in-use status
- Write raw bytes to an I2C slave address
- Read raw bytes from an I2C slave address
- Perform an atomic write-then-read transaction (no STOP condition in between)
- Read or write a register by address (1-byte or 2-byte register width) — e.g.
  monitor/touch MCU registers, serializer/deserializer registers
- Any automation/AI-driven I2C bring-up or verification task

## Implementation Files

Location: [`.github/scripts/aardvark-i2c/`](../../scripts/aardvark-i2c/)

- `i2c_cli.py` — the CLI entry point (stdlib only, no extra pip deps)
- `aardvark_py.py` — vendor (Total Phase) ctypes wrapper around the Aardvark API
- `aardvark.dll` — vendor driver library the wrapper loads via ctypes

## Prerequisites

- Total Phase Aardvark USB adapter physically connected
- Aardvark USB driver installed (see repo root `run_first_time.bat` /
  `README.md` for the one-time driver install steps)
- Python 3.9+ (no extra `pip install` needed — only stdlib is used)

## Command Usage

Run from the workspace root:

```powershell
python .github\scripts\aardvark-i2c\i2c_cli.py <command> [options]
```

| Goal | Command |
|------|---------|
| List attached devices | `i2c_cli.py list` |
| Write raw bytes | `i2c_cli.py write --target mon --data "01 02 03"` |
| Read raw bytes | `i2c_cli.py read --target mon --length 4` |
| Atomic write-read | `i2c_cli.py write-read --target mon --data "01" --length 4` |
| Read a register | `i2c_cli.py reg-read --target ser --reg 0x0105 --length 4 --reg-size 2` |
| Write a register | `i2c_cli.py reg-write --target ser --reg 0x10 --data "AA BB"` |

Run `python .github\scripts\aardvark-i2c\i2c_cli.py <command> -h` for the
full option list of any subcommand.

### Named address presets (`--target`)

| Preset | Address | Meaning |
|--------|---------|---------|
| `mon`   | `0x1C` | Monitor MCU (`SLAVER_ADDR` in the GUI tool) |
| `touch` | `0x1D` | Touch MCU (`TOUCH_SLAVER_ADDR`) |
| `ser`   | `0x40` | Serializer (`SER_ADDR`) |
| `des`   | `0x28` | Deserializer (`DES_ADDR`) |

Use `--addr 0xNN` instead of `--target` for any other address (mutually
exclusive with `--target`).

### Common options

- `--port <N>` — select a specific Aardvark port. If omitted, the first free
  device found via `list` is used automatically.
- `--bitrate <kHz>` — I2C bitrate, default `400`.
- `--reg-size 1|2` — register address width in bytes for `reg-read`/`reg-write`
  (default `1`).

## Outputs

Every command prints exactly one JSON object on stdout:

```json
{"ok": true, "port": 0, "addr": 28, "bitrate_khz": 400, "bytes_read": 4, "data": "01 02 03 04"}
```

On failure, `"ok"` is `false` and an `"error"` field describes the problem
(e.g. no free device, wrong slave address / wiring, partial write). Parse
`ok` first before trusting other fields.

## Workflow

### Step 1 — Confirm hardware is visible

Run `python .github\scripts\aardvark-i2c\i2c_cli.py list`. If `count` is `0`,
ask the user to check the USB connection / driver install before proceeding.

### Step 2 — Pick the target

Pick the right `--target` preset (or `--addr`) for the device being talked to.

### Step 3 — Choose the right command

For simple stimulation, use `write`. For simple polling, use `read`.

### Step 4 — Prefer register helpers for register-style protocols

For register-style protocols (write register address, then read back data,
as used by the monitor/touch/serializer/deserializer chips in this repo),
prefer `reg-read` / `reg-write` — they handle the register-address framing
for you (1 or 2 bytes, MSB-first).

### Step 5 — Fall back to write-read only for custom framing

Use `write-read` only for custom framing that doesn't fit the register
read/write pattern (e.g. a command byte followed by a read).

## Notes

- Each call opens and closes the Aardvark handle — there is no persistent
  session between calls. If you need many transactions in a tight sequence,
  batch them into one call site with `--data` rather than looping many
  separate CLI invocations (each open/close adds latency).
- If two Aardvark devices are attached (e.g. one for monitor, one for
  touch), use `--port` explicitly to target the correct one.

## Resources

- [`i2c_cli.py`](../../scripts/aardvark-i2c/i2c_cli.py) — CLI entry point.
- [`aardvark_py.py`](../../scripts/aardvark-i2c/aardvark_py.py) — vendor ctypes wrapper.
- [`aardvark.dll`](../../scripts/aardvark-i2c/aardvark.dll) — vendor driver library.
