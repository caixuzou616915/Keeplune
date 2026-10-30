---
name: s3p-sits-run
description: >-
  Documents how to run the Robot Framework test suites (BVT / S3P SITS) on a connected
  hardware bench, and how to generate post-run reports (requirement specification tables
  and MTS traceability data). Use when: running, executing, re-running, or debugging a
  Robot Framework test case/suite; invoking the test runner; generating a specification
  report or traceability data.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# S3P SITS Test Execution Skill

## Overview
This skill documents how to **run** the Robot Framework test suites in this repository (BVT / S3P SITS) on a connected hardware bench, and how to **generate post-run reports** (requirement specification tables and MTS traceability data) from the results. Use it whenever the user asks to run, execute, re-run, or debug a Robot Framework test case/suite, asks how to invoke the test runner, or asks to generate a specification report or traceability data.

This skill is about **execution and reporting**. For writing/generating new `.robot` test cases, use `s3p-sits-documentation-compliance`, `s3p-sits-design-techniques`, and the module-specific skills instead.

## Prerequisites
- Hardware bench connected (S3P PCB/HUD ECU, harness, CAN interface, power supply).
- **CANoe measurement must be running** before the test starts (the suite setup performs UDS supplier-session entry over CAN and will fail/hang if CAN traffic is not flowing).
- A local Python virtual environment with Robot Framework and the project's Python dependencies installed, located at `.venv` in the repo root.
- A machine-specific variable file (see [Variable File](#variable-file) below), typically at `C:/ProgramData/robot_properties*.py`.

## Project Test Entry Points
Top-level suites live directly under `tests/` and each imports the module-specific `*_ITS_pf.robot` / `*_ITS_prj.robot` resource files plus `resources/vars_bvt.robot` and `resources/keys_bvt_*.robot`. Pick the suite that matches the target variant:

| Suite file | Variant / Target |
|---|---|
| [tests/bvt_aravalli_s3p.robot](../../../tests/bvt_aravalli_s3p.robot) | Aravalli S3P (tviib_e4m_aravalli_s3p) |
| [tests/bvt_aravalli.robot](../../../tests/bvt_aravalli.robot) | Aravalli (generic) |
| [tests/bvt_aravalli_hud.robot](../../../tests/bvt_aravalli_hud.robot) | Aravalli HUD |
| [tests/bvt_aravalli_db.robot](../../../tests/bvt_aravalli_db.robot) | Aravalli DB |
| [tests/bvt_1m_aravalli.robot](../../../tests/bvt_1m_aravalli.robot) | 1M Aravalli |
| [tests/bvt_DDR.robot](../../../tests/bvt_DDR.robot) | DDR |
| [tests/bvt_endprod.robot](../../../tests/bvt_endprod.robot) | End product |

Each suite file has the exact PyCharm/CLI invocation documented in its own header comment (top of file) — always check that first if in doubt.

## Argument Files
Robot's `-A <file>` flag loads shared CLI arguments (Python paths, output dir, log level, tag links) so they don't need to be repeated on the command line:

- [bvt_aravalli_s3p_robot.txt](../../../bvt_aravalli_s3p_robot.txt) — used with `bvt_aravalli_s3p.robot`
- [bvt_robot.txt](../../../bvt_robot.txt) — used with the other generic `bvt_*.robot` suites

They set `--pythonpath python`, `--pythonpath resources`, `--outputdir results`, `--loglevel`, `--noncritical`/`--skiponfailure`, and `--tagstatlink` entries. Match the argument file name to the suite being run (naming convention: `<suite_basename>_robot.txt`).

## Variable File
Pass `--variablefile "<path>/robot_properties*.py"` — this file configures the bench (CAN tool, COM ports, power supply device, tool paths, variant). A template is checked in at [templates/robot_properties.py](../../../templates/robot_properties.py); the real file lives outside the repo (commonly `C:/ProgramData/robot_properties.py` or a bench-specific name like `robot_properties_isb3.py`). Ask the user for the correct path if unknown — do not invent one.

## Running Tests

### 1. Run a full suite
```powershell
& ".\.venv\Scripts\python.exe" -u -m robot -A bvt_aravalli_s3p_robot.txt `
  --variablefile "C:/ProgramData/robot_properties_isb3.py" `
  -r bvt_tviib_e4m_aravalli_s3p_report.html `
  -l bvt_tviib_e4m_aravalli_s3p_log.html `
  -o bvt_tviib_e4m_aravalli_s3p_output.xml `
  --variable SysInfo_Variant_A:tviib_e4m_aravalli_s3p `
  tests/bvt_aravalli_s3p.robot
```

### 2. Run a single test case
Add `--test "<Exact Test Case Name>"` (matches the `*** Test Cases ***` name in the suite, not the module keyword name):
```powershell
& ".\.venv\Scripts\python.exe" -u -m robot -A bvt_aravalli_s3p_robot.txt `
  --test "BVT Illumination Backlight Cyclic Toggle" `
  --xunit junitRobot.xml `
  --variablefile "C:/ProgramData/robot_properties_isb3.py" `
  -r bvt_tviib_e4m_aravalli_s3p_report.html `
  -l bvt_tviib_e4m_aravalli_s3p_log.html `
  -o bvt_tviib_e4m_aravalli_s3p_output.xml `
  --variable SysInfo_Variant_A:tviib_e4m_aravalli_s3p `
  --variable "ArtifactsPathList:D:\Jenkins_UX\ws\ux\41_RBT_aravalli_s3p_hud/flashfiles" `
  tests/bvt_aravalli_s3p.robot
```
- `--test` may be repeated to select multiple test cases.
- Use `--suite "<Name>"` instead to run every test case in a specific module suite/section.
- Use `--include <tag>` / `--exclude <tag>` to filter by `[Tags]` (e.g. `critical`, `illumination`, `regression`).

### 3. Clean stale bytecode before running (recommended)
Run this once before invoking `robot` if Python resource/library files changed, to avoid stale `.pyc` caching issues:
```powershell
Get-ChildItem -Path 'python' -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
```

### 4. List available test cases without running them
```powershell
& ".\.venv\Scripts\python.exe" -u -m robot --dryrun -A bvt_aravalli_s3p_robot.txt `
  --variablefile "C:/ProgramData/robot_properties_isb3.py" `
  --variable SysInfo_Variant_A:tviib_e4m_aravalli_s3p `
  tests/bvt_aravalli_s3p.robot
```

## Key CLI Flags Reference
| Flag | Purpose |
|---|---|
| `-A <file>` | Load shared arguments (pythonpath, outputdir, loglevel, tagstatlink) |
| `--variablefile <path>` | Bench-specific configuration (tools, COM ports, CAN tool) |
| `--variable NAME:VALUE` | One-off variable override, e.g. `SysInfo_Variant_A`, `ArtifactsPathList` |
| `--test "<name>"` | Run one exact test case (repeatable) |
| `--suite "<name>"` | Run all test cases in a suite/section |
| `--include <tag>` / `--exclude <tag>` | Filter by `[Tags]` |
| `-r/-l/-o` | Report / Log / Output XML file names |
| `--xunit <file>` | JUnit-style XML for CI ingestion |
| `--dryrun` | Validate/list tests without executing keywords |
| `--loglevel TRACE:TRACE` | Verbose console + file logging (already set via `-A` file) |

## Reading Results
All outputs are written to [results/](../../../results/):
- `*_report.html` — pass/fail summary with tag statistics
- `*_log.html` — detailed keyword-by-keyword execution log (open this first to debug a failure)
- `*_output.xml` — machine-readable Robot output (used to regenerate reports, e.g. `rebot`)
- `junitRobot.xml` — JUnit XML (only produced when `--xunit` is passed)

## Common Failure Patterns & Fixes
- **`Multiple keywords with name 'X' found`** — Robot Framework normalizes keyword names (case/space-insensitive), so a scenario keyword in `tests/S3P_<Module>/*_ITS_pf.robot` can collide with a same-named keyword in `resources/S3P_<Module>/*_pf.robot`. Fix by renaming one of the two keywords to be unambiguous, or by using the fully-qualified `resource_file.Keyword Name` form.
- **`TypeError: can only concatenate str (not "int") to str"` in a `FOR ... IN RANGE` loop** — a `${variable}` argument passed via `[Arguments]` is a string even if it looks numeric; convert with `Evaluate    int($var) + 1` before using it as a loop bound.
- **Suite hangs at `Set Tester present and enter Supplier Session`** — CANoe measurement is not running or CAN channel is not connected; start CANoe first.
- **`ArtifactsPathList` errors** — only required by test cases that flash/copy binaries (e.g. `Get Binary File`); omit or point it to a valid artifact folder when not flashing.

## Generating a Specification Report
[ITS_Specification_Report_Gen.py](../../../python/ReportPostProcessing/ITS_Specification_Report_Gen.py) appends a "Keyword Metadata Table" to an existing `*_report.html` — one row per test keyword, with its `Req_ID`, `Documentation`, `Input`, `Expected Result`, `FSM`, `Variant` (parsed from the `#...[Field]` documentation blocks in the `.robot` files), plus a PASS/FAIL/NOT_RUN status column colored from the run's `output.xml`.

Run it **after** a test execution, pointing at the same suite/output/report files used for that run:
```powershell
& ".\.venv\Scripts\python.exe" .\python\ReportPostProcessing\ITS_Specification_Report_Gen.py `
  --test_exec .\tests\bvt_aravalli_s3p.robot `
  --path_test_spec .\tests `
  --output_xml .\results\bvt_tviib_e4m_aravalli_s3p_output.xml `
  --report .\results\bvt_tviib_e4m_aravalli_s3p_report.html `
  --verbose
```
| Arg | Purpose |
|---|---|
| `--test_exec` | The `.robot` suite file that was executed (used to discover which keywords/test cases were called) |
| `--path_test_spec` | Root folder to search for keyword definitions (usually `tests`) |
| `--output_xml` | The `-o` output XML produced by that run (source of PASS/FAIL statuses) |
| `--report` | The `-r` report HTML produced by that run; the table is appended in place |
| `--verbose` | Print extracted keywords/metadata/status to the console for debugging |

Notes:
- If a top-level test case name in `--test_exec` itself carries a `#...[Documentation]` block (self-contained metadata), that test case name is used as the "keyword" instead of its nested step keywords — see `extract_keywords_from_test_file` in the script.
- Safe to re-run, but it **appends** a new table each time — re-running on an already-processed report duplicates the table.

## Generating Traceability Data (MTS trace_data.xml)
[ITS_TraceData_Gen.py](../../../python/ReportPostProcessing/ITS_TraceData_Gen.py) scans every `.robot` file under `tests/` whose filename matches `.*_(its|s3p)_[^\W_]+\.robot$` (e.g. `s3p_illumination_ITS_pf.robot`), extracts `Req_ID` / `FSM` / `Variant` from each test case's `#...[Field]` documentation block, and renders one `<filename>_trace_data.xml` per input file into `results/` via a Jinja2 template.

Run it from the script's own folder (it uses relative paths `../../tests` and `../../results`):
```powershell
cd python\ReportPostProcessing
..\..\.venv\Scripts\python.exe .\ITS_TraceData_Gen.py
```

**Known prerequisite — currently missing in this checkout:** the script loads `templates/generate_templates/trace_data.xml`, a Jinja2 template for the MTS `FILE`/`TID`/`C`/`Link` XML schema (structurally similar to the format produced by [.github/scripts/gtest/generate_trace_data.py](../../scripts/gtest/generate_trace_data.py) for GTest modules). That template file/folder does not exist in this repo checkout — running the script as-is fails with:
```
jinja2.exceptions.TemplateNotFound: trace_data.xml
```
Before relying on this feature, obtain/place the MTS trace-data Jinja2 template at `templates/generate_templates/trace_data.xml` — ask the project/MTS toolchain owner if unsure where it comes from. Do not fabricate this template; the ASPICE traceability tooling expects an exact schema.

Once the template is in place, output files are named `<original_filename>_trace_data.xml` (e.g. `s3p_illumination_ITS_pf.robot_trace_data.xml`) in [results/](../../../results/). Test cases documented with a `#[Manual]` or `#[TODO]` prefix are still parsed (see `cfg_tag_unexecutedtestblock`).

## Related Skills
- `s3p-sits-strategy-planning` — scoping and requirement analysis before writing tests
- `s3p-sits-documentation-compliance` — documentation block format for test cases
- `robot-framework-integration` — Robot Framework file/keyword structure conventions
- Module skills (`s3p-eyebox-module`, `s3p-illumination-module`, etc.) — module-specific keywords/DIDs
