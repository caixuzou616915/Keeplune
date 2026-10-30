---
name: canoe-interface
description: "Use when interfacing with CANoe simulation: read/write signals, SysVars, EnvVars, send CAN/CANFD frames, run UDS diagnostics, check NM state, inject bus errors, search DBC databases, start/stop measurement. Covers OSI L1 physical, L2 data-link, L3 network, L4 transport, L7 application. Use for CANoe automation, ECU testing, cluster stimulation, telltale verification, bus health checks."
argument-hint: "Describe what you want to do in CANoe, e.g. 'read EngineSpeed', 'send a CAN frame', 'read DTCs from MyECU'"
metadata:
  author: "Kwang Guan Hong"
  version: "1.0.0"
---

# CANoe Interface Skill

## When to Use

Invoke this skill whenever you need to:
- Read or write signals, SysVars, or EnvVars in a running CANoe measurement
- Read any DBC signal's live value directly off the bus, with no SysVar link
  or CAPL node required (useful for ECU-transmitted feedback signals that have
  no SysVar defined)
- Send or monitor CAN / CAN FD frames
- Run UDS diagnostics (read DTCs, read/write DIDs, ECU reset)
- Check AUTOSAR NM network state
- Read bus statistics or inject CAN errors for robustness testing
- Search DBC databases for signal names, IDs, or scaling factors (offline)
- Start, stop, or check the status of a CANoe measurement

## Architecture

All tools live in [`.github/scripts/canoe/`](../../scripts/canoe/) and are invoked via:

```powershell
$env:PYTHONPATH = ".github\scripts"; python -m canoe <command>
```

Output is always JSON. `python -m canoe --help` (and `<command> --help`) is
self-documenting via argparse -- there is no separate CLI reference doc to
keep in sync, since every project using this tooling may have different
signals/namespaces anyway (see the project-specific companion-skill
pattern below).

### Module Map (OSI layers)

| Module | OSI Layer | Role |
|--------|-----------|------|
| [`canoe_com.py`](../../scripts/canoe/canoe_com.py) | — | COM connection, measurement control |
| [`signals.py`](../../scripts/canoe/signals.py) | L7 Application | SysVar / EnvVar read-write |
| [`frames.py`](../../scripts/canoe/frames.py) | L2 Data Link | Raw CAN/CANFD frame send/receive |
| [`diagnostics.py`](../../scripts/canoe/diagnostics.py) | L4 Transport | UDS / ISO-TP / DoIP |
| [`network_layer.py`](../../scripts/canoe/network_layer.py) | L3 Network | NM state, Ethernet/IP |
| [`physical.py`](../../scripts/canoe/physical.py) | L1 Physical | Bus statistics, error injection |
| [`dbc_reader.py`](../../scripts/canoe/dbc_reader.py) | — (offline) | DBC signal/message lookup |
| [`test_sequence.py`](../../scripts/canoe/test_sequence.py) | — | Generic ramp/sequence test runner + JSON+HTML reports |
| [`skill_gen.py`](../../scripts/canoe/skill_gen.py) | — | Auto-generates the project-specific signal catalog skill |

## Multi-Agent Setup

This skill is designed for use in a **multi-agent pipeline**:

```
Orchestrator agent
  ├── Signal discovery subagent   →  dbc_reader.py  (offline, no CANoe needed)
  ├── Stimulation subagent        →  signals.py / frames.py
  ├── Verification subagent       →  signals.py (readback DEV_ signals)
  ├── Diagnostic subagent         →  diagnostics.py
  └── Bus health subagent         →  physical.py / network_layer.py
```

Each subagent receives a `CANoeConnection` object from `canoe_com.py` and operates independently on its layer.

## Configuration

Project-specific settings are stored in `canoe_agent.json` **next to the CANoe project's `.cfg` file** (not inside `.github/`) — e.g. `D:\Tool\CAN\canoe_agent.json` for this workspace. Switching the open `.cfg` in CANoe automatically activates the matching config. Let the `discover` command fill it in automatically (see step 1 below); only edit it by hand for a field it couldn't auto-detect.

## Procedure

### 1. First-time setup

```powershell
# Install dependencies
pip install -r .github\scripts\requirements.txt
```

Then, with **CANoe open** and your project `.cfg` loaded, run:

```powershell
$env:PYTHONPATH = ".github\scripts"
python -m canoe discover
python -m canoe skill generate
```

`discover` writes `canoe_agent.json` next to the loaded `.cfg`. `skill
generate` then (re)writes `.github/skills/canoe-project-signals/SKILL.md`
from a live scan of the DBC files + SysVar namespace tree — always
overwritten, never hand-edited, so this tooling is immediately useful on a
brand-new project with zero manual authoring. A hand-curated companion
skill (like `s3p-can-signals`), if one exists for the loaded project, still
takes priority over the auto-generated catalog.

No path needed. The command reads the project root directly from the running CANoe instance and auto-detects everything:
- DBC file locations (recursive scan from the given path)
- Diagnostic ECU device names (live CANoe COM query)
- SysVar namespaces (live CANoe COM query)
- DoIP IPv6 addresses and ports (scanned from CAPL `.can`/`.cin` files)
- NM SysVar namespace and variable (pattern match against known names)

The command prints what it found (or warns if something could not be auto-detected).  
For anything it couldn't detect, open `canoe_agent.json` and fill in just that field.

### 2. Verify connection

```powershell
$env:PYTHONPATH = ".github\scripts"; python -m canoe status
```

Expected: `{ "connected": true, "running": true/false, "config_path": "..." }`

### 3. Start measurement (if not running)

```powershell
python -m canoe measurement start
```

### 4. Discover signals before using them

Search DBC files first to find the exact signal name for your project:

```powershell
# Search by keyword (use terms relevant to your project)
python -m canoe dbc find "Speed"
python -m canoe dbc find "Ignition"

# Get full metadata for a specific signal
python -m canoe dbc signal "<SignalName>"

# List all loaded DBC files
python -m canoe dbc files
```

### 5. Find the right SysVar namespace

```powershell
# List all namespaces
python -m canoe signal sysvar namespaces

# List variables in a namespace
python -m canoe signal sysvar list "<Namespace>"
```

### 6. Stimulate and read back

```powershell
# Write a SysVar (replace namespace and variable with values from step 5)
python -m canoe signal sysvar write "<Namespace>" "<Variable>" <value>

# Read back
python -m canoe signal sysvar read "<Namespace>" "<Variable>"

# Write a DBC EnvVar (name comes from dbc find)
python -m canoe signal envvar write "<EnvVarName>" <value>

# Read a signal that has no SysVar link at all (e.g. an ECU Tx/feedback
# signal) directly off the bus — no CAPL node or Test Setup needed
python -m canoe signal bus read "<MessageName>" "<SignalName>"
```

### 7. Simulate a button press (momentary EnvVar toggle)

```powershell
python -m canoe signal envvar write "<ButtonEnvVar>" 1
Start-Sleep -Milliseconds 200
python -m canoe signal envvar write "<ButtonEnvVar>" 0
```

### 8. Read diagnostics

```powershell
# Replace "MyECU" with the device name from canoe_agent.json > diagnostic_devices
python -m canoe diag dtc read <DeviceName>
python -m canoe diag did read <DeviceName> 0xF186
```

### 9. Check bus health

```powershell
python -m canoe physical stats
python -m canoe nm state
```

## Live Verification Method (standard way to verify multi-step / timed behavior)

For anything beyond a single write+read (sweeps, ramps, staged sequences,
"hold value X for N seconds then check", etc.), do **not** issue many
separate `python -m canoe ...` CLI calls in a loop from PowerShell — each
one pays a fresh COM-connect cost and doesn't compose with sleeps/holds.

### Preferred: the generic `sequence` subcommand (no new file needed)

[`test_sequence.py`](../../scripts/canoe/test_sequence.py) implements two
reusable, parametrized primitives that cover the large majority of
stimulus/verification test cases, exposed directly via the CLI:

```powershell
# Linear ramp: e.g. "increment brightness by 1% every second for 20s"
python -m canoe sequence ramp --namespace "<NS>" --variable "<VAR>" `
  --start 256 --end 5120 --step 256 --interval 1.0 `
  --verify-message "<Msg>" --verify-signal "<Sig>" `
  --report-dir "ai_output/<test_name>" --report-name "<run_name>"

# Arbitrary non-linear step list, described as a JSON spec file
python -m canoe sequence run-spec my_test_spec.json
```

`run-spec` JSON shape (ramp form shown; alternatively provide an explicit
`"steps": [{"value":, "hold_s":}, ...]` list instead of start/end/step):

```json
{
  "namespace": "MESSAGES::Msg_IlluminationCtl_Rx::SYSVARS",
  "variable": "Sig_IllumUserLevelCh1",
  "start": 256, "end": 5120, "step": 256, "interval": 1.0,
  "verify_message": "Msg_IlluminationCtl_Rx", "verify_signal": "Sig_IllumUserLevelCh1"
}
```

Both write a `steps[]` array (value written, UTC timestamp, SysVar readback,
bus readback, per-step pass) plus an `overall_pass` verdict, and **always**
write a JSON+HTML report to disk under `ai_output/` — across every project,
no exceptions. `--report-dir`/`--report-name` only override the destination
and file name; omitting them still produces a report using a timestamped
default name, it never skips writing one.

### Verification: bus signal vs. real UDS DID round-trip

`--verify-message`/`--verify-signal` (above) checks the value **CANoe
itself put on the bus** — proves the stimulus transmitted correctly, but
NOT that the ECU received/applied it. If this project has no CANoe
`DiagnosticDevices` (no CDD/PDX attached — check with `python -m canoe diag
list`; if it errors, there's no CDD), look for a CAPL-only UDS tester
exposed via SysVars instead (an `on sysvar X { if(@this) SendDiagData(...)
}` pattern triggering a real `22 <DID>` request, with the response decoded
into a sibling `..._Data_*`-style SysVar). If one exists, use the
**stronger** DID-based check instead of/alongside the bus check:

```powershell
python -m canoe sequence ramp --namespace "<NS>" --variable "<VAR>" `
  --start 0 --end 100 --step 10 --interval 1.0 `
  --verify-did-trigger-ns "<TriggerNamespace>" --verify-did-trigger-var "<SysVar_Read_X>" `
  --verify-did-data-ns "<DataNamespace>" --verify-did-data-var "<SysVar_Data_X>"
```

This forces a real 0->1 edge on the trigger SysVar every step (many CAPL
diagnostic testers only fire `on sysvar` handlers on an actual value
change — a stale `1` left over from a previous run is a silent no-op),
waits `--verify-did-wait` seconds (default 0.3s) for the round-trip, then
decodes the last 2 bytes of the data SysVar as a big-endian uint16. Steps
report `did_readback`/`did_readback_raw`/`did_pass` alongside the bus
fields; `overall_pass` is the AND of whichever checks are configured.

### Diagnostic session control + arbitrary UDS request testing

For test cases about the diagnostic session itself (cycling
Default/Extended/Supplier/etc.) or an arbitrary raw UDS request not tied to
one specific signal's dedicated DID SysVar pair, use `diag-session-cycle`
(same reusable runner, not a new script):

```powershell
python -m canoe sequence diag-session-cycle `
  --sessions "Default:1,Extended:3,Supplier:0x60" `
  --request 22 F1 86 `
  --report-dir "ai_output/<test_name>" --report-name "<run_name>"
```

Implemented by `test_sequence.run_diag_session_cycle()`: writes
`DIAGNOSTICS::SysVar_SessionMode` + edge-triggers
`DIAGNOSTICS::SysVar_SessionMode_Request` per session (sends
`10 <session>`), then writes `DIAGNOSTICS::Sysvar_DIAG_txData` + edge-
triggers `DIAGNOSTICS::Sysvar_DIAG_Send` for the generic request,
reading the response from `DIAGNOSTICS::Sysvar_DIAG_rxData` (works for ANY
service/DID, not just ones with a dedicated SysVar pair). Note: reading a
`data`-type SysVar via COM returns SIGNED bytes (-128..127) — mask with
`& 0xFF` before building a Python `bytes()` from it (handled internally by
this runner; apply the same fix in any custom script reading a `data`-type
SysVar).

**Do not create a new bespoke `.py` file per test case.** If a test needs
logic `run_ramp`/`run_sequence`/`run_diag_session_cycle` can't express
(multi-signal coordination, conditional branching), write a throwaway
script that *imports and reuses* them as building blocks — still delete
it afterward, don't commit it. This is the same Live Verification Method as
before, just built on shared primitives instead of copy-pasted loops.

**Do not use CANoe Test Setup / CAPL Test Module COM automation
(`TestEnvironments`/`TestModules`) to run verification** — it required a
manual GUI step to add each `.can` file and is not usable for unattended
agent runs on this CANoe version. That automation path has been removed
from the CLI. `.can` Test Module files may still exist as reference/manual
test case documentation, but the agent always verifies live via the method
above.

## How to find signal names for your project

Signal names vary by project. The workflow is always:

1. Run `python -m canoe dbc find "<keyword>"` to search
2. Use the returned `name` field as the signal/EnvVar name
3. Use `python -m canoe signal sysvar namespaces` to find the matching SysVar namespace
4. Read or write using the exact names found above

Common keywords to try: `Speed`, `Ignition`, `Key`, `View`, `Brake`, `Door`, `Light`
