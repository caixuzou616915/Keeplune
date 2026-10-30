---
name: enterprise-architect
description: "EA automation for design export, code comparison, and traceability analysis. Orchestrates model exports, compares design vs. code, generates documentation, manages round-trip workflows, and produces comprehensive traceability reports for automotive embedded software."
applies-to: 
  - "**/*.py"  # Python tools in .github/scripts/ea/
  - "**/SwMod_*.md"  # Generated design documentation
  - "**/ea_diagram_to_code.py"
  - "**/compare_design_code.py"
  - "**/export_module_functions.py"
  - "**/export_module_diagrams.py"
  - "**/export_traceability.py"
  - "**/export_arch_design.py"
  - "**/import_code_to_diagrams.py"
  - "**/ea_import_diagrams_from_xml.py"
  - "**/report_missing_traceability.py"
metadata:
  author: "Zhao Jianbo"
  version: "2.1.0"
---

# Enterprise Architect (EA) Automation Skill

Orchestrate Enterprise Architect workflows for automotive embedded software: design export, code comparison, documentation generation, and round-trip synchronization between EA models and C implementations.

## Overview

This skill covers the full EA automation toolkit for:
- Exporting design function specifications from EA packages
- Comparing EA design with actual C source code implementations
- Generating activity diagrams and design documentation
- Analyzing traceability links between design elements
- Round-trip workflows: EA ↔ XML ↔ C code ↔ EA
- Producing deviation reports and compliance artifacts

**Key Understanding:** The toolkit bridges **Enterprise Architect design models** (EA packages, classes, operations, activity diagrams) with **C source code** (functions, parameters, types) using AUTOSAR-style C macros and SMK/ASPICE practices.

**⭐ NEW:** Start with [`ea_diagram_to_code.py`](#quick-start-single-command-c-generation) for single-command diagram-to-code generation.

---

## Tool Suite

All EA tools are located in `.github/scripts/ea/`.

| Script | Purpose | Requires EA? | Location | Use Case |
|--------|---------|--------------|----------|----------|
| **`ea_diagram_to_code.py`** ⭐ | **Orchestrate C generation from EA diagrams** | ❌ No | `.github/scripts/ea/` | **PRIMARY ENTRY POINT:** Single-command C code generation with auto-detection |
| `compare_design_code.py` | Compare design vs. code, produce deviation reports | Optional (uses `--from-doc` mode) | `.github/scripts/ea/` | Verify code matches design specifications |
| `export_module_functions.py` | Extract EA function lists to Markdown | ✅ Yes (32-bit) | `.github/scripts/ea/` | Export design baseline for comparison |
| `export_module_diagrams.py` | Render activity diagrams and generate C code | ❌ No | `.github/scripts/ea/` | Generate implementation from design |
| `export_traceability.py` | Export full traceability to JSON | ✅ Yes (32-bit) | `.github/scripts/ea/` | Map design links and relationships |
| `export_arch_design.py markdown` | Export architecture design to **Markdown** (one `.md` per `SwSys_/SwSubSys_/SwMod_` package: breadcrumb, notes, sub-packages, elements, diagrams) | ✅ Yes (32-bit) | `.github/scripts/ea/` | Export high-level design structure for human review |
| `export_arch_design.py json` | Export architecture-design **traceability info to JSON** (GUID, tagged values, `TableTracedTo` links), mirroring the MDD/TraceIT "SwArchDesignExpToTraceIt" format | ✅ Yes (32-bit) | `.github/scripts/ea/` | Feed traceability tooling downstream of EA |
| `export_sequence_diagrams.py` | Export every EA `Diagram.Type=="Sequence"` diagram to PlantUML (`.puml`) | ✅ Yes (32-bit) | `.github/scripts/ea/` | Export sequence/interaction diagrams for review or documentation |
| `ea_connect.py` | Shared COM-connection + model-walking helper (not run directly) | ✅ Yes (32-bit) | `.github/scripts/ea/` | Imported by `export_arch_design.py`/`export_sequence_diagrams.py` |
| `import_code_to_diagrams.py` | Parse C code into activity diagram XML | ❌ No | `.github/scripts/ea/` | Convert implementation back to design |
| `ea_import_diagrams_from_xml.py` | Import XML diagrams into EA | ✅ Yes (32-bit) | `.github/scripts/ea/` | Push design changes to EA model |
| `report_missing_traceability.py` | Analyze traceability JSON and flag gaps | ❌ No | `.github/scripts/ea/` | Verify traceability coverage |
| `xml_to_c.py` | Generate C code from activity diagram XML (used by orchestration) | ❌ No | `.github/scripts/ea/` | Imported by `ea_diagram_to_code.py` for flow graph parsing |

---

## Quick Start: Single-Command C Generation

Use **`ea_diagram_to_code.py`** to generate C source files from EA diagrams in one command. This is the primary entry point for all EA→C workflows.

```bash
# Auto-detect everything (searches input/ and ai_output/)
python .github/scripts/ea/ea_diagram_to_code.py touchsm

# Preview without writing (dry run)
python .github/scripts/ea/ea_diagram_to_code.py touchsm --dry-run --verbose

# Custom output location
python .github/scripts/ea/ea_diagram_to_code.py touchsm --output ai_output/touchsm/generated_c --force
```

**How it works (Orchestration Flow):**
```
┌─────────────────────────────────────────────────────────────┐
│ ea_diagram_to_code.py [MODULE_NAME]                         │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
   1. Search    2. Auto-detect  3. Normalize
   input/       target folder    module name
   ai_output/      (adapt/core)
        │            │            │
        └────────────┼────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼ (if XMI found)         ▼ (if diagrams found)
   ┌─────────────────┐      ┌──────────────────┐
   │ Integrated in    │      │ xml_to_c.py      │
   │ → Generate      │      │ → Generate C     │
   │   from XMI      │      │   from XML       │
   └────────┬────────┘      └────────┬─────────┘
            │                        │
            ▼                        ▼
   ┌─────────────────────────────────────────┐
   │ ai_output/<module>/
   │   generated_c/
   │     SwMod_<Name>.h  (.h header)
   │     SwMod_<Name>.c  (.c implementation)
   │   SwMod_<Name>_ms.xml  (intermediate XMI)
   └─────────────────────────────────────────┘
```

1. Searches for XMI (`*_ms.xml`) and SwDetailedDesignDiagram XML files
2. Auto-detects target folder (adapt vs core) based on input source
3. Integrates XMI parsing and C generation logic; uses `xml_to_c.py` for flow graph processing
4. Consolidates and merges output files

**Parameters:**

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `MODULE_NAME` | positional | Module identifier (no SwMod_ prefix) | `touchsm`, `desctl` |
| `--xmi FILE` | optional | Explicit XMI file (auto-detected if omitted) | `--xmi ai_output/touchsm/SwMod_TouchSM_ms.xml` |
| `--diagrams DIR` | optional | Diagram XML directory (auto-detected if omitted) | `--diagrams input/touchsm/` |
| `--output DIR` | optional | Force output directory | `--output ai_output/touchsm/generated_c` |
| `--input-dir DIR` | optional | Base input directory | `--input-dir input/` |
| `--dry-run` | flag | Preview only, don't write | |
| `--force` | flag | Overwrite without prompting | |
| `--verbose` | flag | Print detailed diagnostics | |

---

## Core Concepts

### EA Package Structure

EA projects use a hierarchical package naming convention:

| Level | Prefix | Example | Purpose |
|-------|--------|---------|---------|
| System | `SwSys_` | `SwSys_S3PHUD` | Top-level system definition |
| Subsystem | `SwSubSys_` | `SwSubSys_TouchCtl` | Functional grouping (platform-level) |
| Module | `SwMod_` | `SwMod_TouchSM` | Implementation unit (typically one EA package = one C module) |

Each **module** contains one or more **classes** (typically named `<ModuleName>_API`, `<ModuleName>_Core`, etc.).  
Each **class** maps to a **C source file** via the EA tagged value `SourceFile` (e.g., `touchsm1c1.c`).  
Each **operation** in an EA class maps to a **C function**.

### AUTOSAR Memory-Class Macros

C code uses AUTOSAR memory class macros. The tools normalize these automatically for comparison:

| Macro | Normalised Form |
|-------|-----------------|
| `FUNC(RetType)` | `RetType` |
| `FUNC(RetType, MemClass)` | `RetType` |
| `P2VAR(T, _, _)` | `T*` |
| `P2CONST(T, _, _)` | `const T*` |
| `CONSTP2VAR(T, _, _)` | `T* const` |
| `CONSTP2CONST(T, _, _)` | `const T* const` |

**Important:** Pointer spacing is normalized to no spaces: `T * ` → `T*`.

### Design Function List Format

The `export_module_functions.py` tool produces Markdown files like `doc/SwMod_TouchSM_Functions.md`:

```markdown
### TouchSM_API

| # | Function | Return Type | Parameters | Trace ID | Implements | Description |
|---|----------|-------------|------------|----------|-----------|-------------|
| 1 | TouchSM_vInit | void | (none) | EA_GUID_123 | - | Initialize state machine |
| 2 | TouchSM_vMain | void | [in] u8 Status | EA_GUID_456 | - | Main cyclic function |
```

These files serve as the **design baseline** for `compare_design_code.py`.

---

## Installation & Configuration

### Install Dependencies

```bash
# All tools (dotenv support):
pip install -r .github/scripts/ea/requirements.txt

# 32-bit Python (for EA COM tools):
.venv32\Scripts\pip.exe install pywin32
& ".venv32\python.exe" -m pip install pywin32-postinstall.py -install
```

**Tools requiring 32-bit Python + pywin32:**
- `export_module_functions.py`
- `export_traceability.py`
- `export_arch_design.py`
- `export_sequence_diagrams.py`
- `ea_import_diagrams_from_xml.py`

**Tools working with any Python:**
- `ea_diagram_to_code.py` ⭐ (primary orchestration tool — uses any Python)
- `compare_design_code.py` (--from-doc mode)
- `export_module_diagrams.py`
- `import_code_to_diagrams.py`
- XMI parsing and C generation (integrated into orchestration)
- `xml_to_c.py` (called by orchestration)
- `report_missing_traceability.py`

See [`requirements.txt`](.github/scripts/ea/requirements.txt) for complete details.

### Consolidation Note

**As of v2.1:** `xmi_to_c.py` has been merged into `ea_diagram_to_code.py` for a unified all-in-one tool. No more subprocess calls—all XMI parsing and C code generation is now integrated directly.

### .env File Setup

Create `.github/scripts/ea/.env` with:

```ini
# Enterprise Architect project
EA_PROJECT=D:\Temp\S3P-HUD_Test.eap
EA_PROJECT_PASSWORD=

# Output directories
EA_OUTPUT_DIR=./output
EA_DOC_DIR=./doc

# Source code base directory
EA_SOURCE_DIR=./input

# Python environment (for EA tools requiring COM)
EA_PYTHON_32BIT=.\.venv32\python.exe
```

**Best Practices:**
- Keep `.env` **out of version control** (add to `.gitignore`)
- Commit `.env.template` instead (safe reference)
- Each developer/CI environment gets its own `.env`

### Python Environment Strategy

| Interpreter | When to use |
|---|---|
| `& ".venv32\python.exe"` | Tools that require EA COM: `export_module_functions`, `export_traceability`, `export_arch_design` (markdown/json subcommands), `export_sequence_diagrams`, `ea_import_diagrams_from_xml` |
| `python` (system/any venv) | File-only tools: `compare_design_code --from-doc`, `export_module_diagrams`, `import_code_to_diagrams`, `report_missing_traceability` |

**Why 32-bit?** EA COM requires 32-bit Python + pywin32 for the Windows COM interface.

---

## Deviation Categories

When comparing design vs. code, the tools report these categories:

| Category | Meaning |
|----------|---------|
| `MISSING_IN_CODE` | Function specified in design but not found in C source |
| `EXTRA_IN_CODE` | Function found in C source but not in design |
| `RETURN_TYPE` | Return type differs (after AUTOSAR normalization) |
| `PARAM_COUNT` | Number of parameters differs |
| `PARAM_TYPE[N]` | Parameter N type differs (normalized) |
| `PARAM_NAME[N]` | Parameter N name differs (only with `--strict-names`) |

**Important Notes:**
- Deviations on long AUTOSAR DCM types with `...` are usually EA data quality issues (EA truncates long type names in tagged values).
- Functions suffixed `_Test` or `_test` in C are intentional test stubs and may show as `EXTRA_IN_CODE` — this is expected.

---

## Common Workflows

### Workflow 0: Generate C Code from Diagrams (⭐ RECOMMENDED STARTING POINT)

The fastest way to generate C code from EA diagrams in one command. Generates to `ai_output/<module>/generated_c/`.

```bash
# Simple: auto-detect everything
python .github/scripts/ea/ea_diagram_to_code.py SwMod_TouchSM

# With diagnostics
python .github/scripts/ea/ea_diagram_to_code.py SwMod_TouchSM --verbose

# Preview before writing
python .github/scripts/ea/ea_diagram_to_code.py SwMod_TouchSM --dry-run --verbose

# Generate without confirmation
python .github/scripts/ea/ea_diagram_to_code.py SwMod_TouchSM --force
```

**Result:** C header and source files generated to `ai_output/<module>/generated_c/` (auto-detected).

For detailed information on architecture and consolidated tools, see:
- [CONSOLIDATION_SUMMARY.md](../../CONSOLIDATION_SUMMARY.md) — How tools were reorganized
- [.github/scripts/ea/README.md](.github/scripts/ea/README.md) — Detailed tool reference

---

### Workflow 1: Design vs. Code Comparison (No EA Required)

Compare EA design specifications with actual C source code.

```bash
# Prerequisite: doc/<ModuleName>_Functions.md must exist
# (export once if stale: export_module_functions.py)

# NOTE: Create the output directory first (the tool does not auto-create it)
New-Item -ItemType Directory -Force ai_output/reports | Out-Null
python .github/scripts/ea/compare_design_code.py SwMod_TouchSM touchsm1c1.c \
    --class TouchSM_API \
    --src-dir input/touchsm/core \
    --from-doc SwMod_TouchSM \
    --output ai_output/reports/SwMod_TouchSM_deviations.md
```

**Output:** Markdown table listing per-function deviations and clean functions.

---

### Workflow 2: Export Design Function Lists

Export EA module structure and specifications to Markdown.

```bash
# Single module
& ".venv32\python.exe" .github/scripts/ea/export_module_functions.py SwMod_TouchSM

# All modules under a subsystem
& ".venv32\python.exe" .github/scripts/ea/export_module_functions.py \
    --scope SwSubSys_TouchCtl

# All modules under Platform
& ".venv32\python.exe" .github/scripts/ea/export_module_functions.py \
    --scope Platform
```

**Output:** `doc/<ModuleName>_Functions.md` — function tables with Trace IDs.

---

### Workflow 3: Export & Render Activity Diagrams

Render activity diagrams from `SwDetailedDesignDiagram` XML and optionally generate C code.

```bash
# WARNING: export_module_diagrams.py currently has a broken import (xmi_to_c module missing).
# Use ea_diagram_to_code.py instead:
python .github/scripts/ea/ea_diagram_to_code.py touchsm --output ai_output/touchsm/generated_c --force

# The following are currently broken due to missing xmi_to_c dependency:
# python .github/scripts/ea/export_module_diagrams.py SwMod_TouchSM
# python .github/scripts/ea/export_module_diagrams.py SwMod_TouchSM --no-code
# python .github/scripts/ea/export_module_diagrams.py --all
```

**Output:**
- `doc/<ModuleName>_diagrams.md` — numbered flow tables per function
- `ai_output/generated_c/<ModuleName>.h` / `.c` — generated C source (unless `--no-code`)

---

### Workflow 4: Parse C Code to Diagram XML

Convert C source functions into activity flow graphs and generate `SwDetailedDesignDiagram` XML.

```bash
# Single C file
python .github/scripts/ea/import_code_to_diagrams.py ai_output/generated_c/SwMod_TouchSM.c

# Whole directory
python .github/scripts/ea/import_code_to_diagrams.py ai_output/generated_c/

# Specific functions only
python .github/scripts/ea/import_code_to_diagrams.py file.c \
    --functions TouchSM_vInit,TouchSM_vMain

# Dry run (preview changes)
python .github/scripts/ea/import_code_to_diagrams.py file.c --dry-run
```

**Output:** `SwDetailedDesignDiagram*.xml` files + change report.

---

### Workflow 5: Export Traceability

Export complete traceability: incoming/outgoing links and operation tags to JSON.

```bash
# Single module
& ".venv32\python.exe" .github/scripts/ea/export_traceability.py SwMod_TouchSM

# Single subsystem
& ".venv32\python.exe" .github/scripts/ea/export_traceability.py SwSubSys_TouchCtl

# All modules under Platform
& ".venv32\python.exe" .github/scripts/ea/export_traceability.py \
    --level module --scope Platform

# All levels combined
& ".venv32\python.exe" .github/scripts/ea/export_traceability.py \
    --level all --scope Platform
```

**Output:** `ai_output/traceability/<PackageName>_traceability.json`

---

### Workflow 5b: Export Architecture Design (Markdown/JSON) and Sequence Diagrams (PlantUML)

`export_arch_design.py` has two subcommands sharing one connection layer:
`markdown` (human-readable design docs) and `json` (SwArchDesign traceability
export, GUID/tagged-values/`TableTracedTo` links). `export_arch_design.py
markdown` and `export_sequence_diagrams.py` share the same `--scope SUBSTR`
convention for choosing what to export — `SUBSTR` is matched against the
package's full breadcrumb path (itself or any ancestor), so scoping to a
subsystem also picks up its nested modules, and scoping to a system/platform
package picks up everything under that subtree. Omit `--scope` to export
everything. `export_arch_design.py json` has its own `--level`/`--prefix`/
`--filter`/`--scope`/`--recurse` options (different `--scope` semantics —
path-segment match, not breadcrumb substring); run `export_arch_design.py
json --help` for details.

```bash
# Export all Markdown design docs in the model
& ".venv32\python.exe" .github/scripts/ea/export_arch_design.py markdown

# Export one sub-system (+ its modules)
& ".venv32\python.exe" .github/scripts/ea/export_arch_design.py markdown --scope SwSubSys_TouchCtl

# Export a whole system/platform subtree
& ".venv32\python.exe" .github/scripts/ea/export_arch_design.py markdown --scope Platform

# JSON traceability export
& ".venv32\python.exe" .github/scripts/ea/export_arch_design.py json --level subsystem --scope Platform

# Same scoping for sequence diagrams
& ".venv32\python.exe" .github/scripts/ea/export_sequence_diagrams.py
& ".venv32\python.exe" .github/scripts/ea/export_sequence_diagrams.py --scope SwSubSys_TouchCtl
& ".venv32\python.exe" .github/scripts/ea/export_sequence_diagrams.py --scope Platform
```

**Output:** `ai_output/arch_design/*.md`, `ai_output/arch_design/<platform|project>/*.json`, and `ai_output/arch_design/diagrams/*.puml`.

**EA COM instability / resumable export:** EA's COM automation server can
crash the whole process silently and unpredictably partway through a
full-model sequence-diagram export (no traceback — just process exit).
`export_sequence_diagrams.py` writes
`ai_output/arch_design/diagrams/_export_manifest.json` incrementally so
re-running the *same* command resumes instead of restarting (pass `--fresh`
to force a full re-export). For a full unattended run, use the retry-loop
driver, which keeps re-invoking the script until everything is exported or
progress stalls:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .github/scripts/ea/run_export_until_done.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .github/scripts/ea/run_export_until_done.ps1 --scope SwSubSys_TouchCtl
```

See `.github/scripts/ea/README.md` for full details and AI-calling guidance
(single-instance-only, UTF-16LE log redirection, etc.).

---

### Workflow 6: Report Missing Traceability

Analyze traceability JSON and flag elements missing required trace links.

```bash
python .github/scripts/ea/report_missing_traceability.py \
    --output ai_output/missing_traceability.csv
```

**Output:** `ai_output/missing_traceability.csv` — elements with missing traces.

---

### Workflow 7: Full Round-Trip (Design ↔ Code)

Complete bidirectional synchronization: Export design → Generate C → Edit C → Re-import to XML → Push to EA.

```bash
# Step 1: Export function lists (design baseline)
& ".venv32\python.exe" .github/scripts/ea/export_module_functions.py SwMod_TouchSM

# Step 2: Generate activity diagrams XML
& ".venv32\python.exe" src/main.py SwMod_TouchSM

# Step 3: Render diagrams to Markdown + generate C code
python .github/scripts/ea/export_module_diagrams.py SwMod_TouchSM

# Step 4: (User edits the C code in ai_output/generated_c/SwMod_TouchSM.c)

# Step 5: Re-parse C back to diagram XML
python .github/scripts/ea/import_code_to_diagrams.py ai_output/generated_c/SwMod_TouchSM.c

# Step 6: Push XML changes into EA
& ".venv32\python.exe" .github/scripts/ea/ea_import_diagrams_from_xml.py SwMod_TouchSM
```

---

### Workflow 8: Bulk Export + Comparison

Export all functions for a platform, then compare each module.

```bash
# Step 1: Export all function lists
& ".venv32\python.exe" .github/scripts/ea/export_module_functions.py --scope Platform

# Step 2: Compare each module (no EA needed after this)
for module in SwMod_TouchSM SwMod_SysCtl SwMod_IllumBA; do
  python .github/scripts/ea/compare_design_code.py $module \
      --src-dir input/$module/core \
      --from-doc $module \
      --output ai_output/reports/${module}_deviations.md
done

# Step 3: Review all reports
ls ai_output/reports/*_deviations.md
```

---

## Key Tips & Constraints

### SourceFile Tag Typos

If EA has a typo in the `SourceFile` tagged value (e.g., `toushsm1c1.c` instead of `touchsm1c1.c`), use `--class <ClassName>` to bypass source-file matching:

```bash
python .github/scripts/ea/compare_design_code.py SwMod_TouchSM touchsm1c1.c \
    --class TouchSM_API  # Directly specify the EA class name
```

### Using `--from-doc` Without EA

For design vs. code comparison without running EA:

```bash
# Reads existing doc/<ModuleName>_Functions.md (no EA connection)
python .github/scripts/ea/compare_design_code.py SwMod_TouchSM touchsm1c1.c \
    --src-dir input/touchsm/core \
    --from-doc SwMod_TouchSM
```

This is useful for:
- CI/CD pipelines (EA not available)
- Local comparison after stale export
- Lightweight change verification

### Test Stub Functions

Functions with `_Test` or `_test` suffix in C code are intentional test-only additions and typically show as `EXTRA_IN_CODE`. This is expected and not a real deviation.

### Type Normalization Details

Long AUTOSAR DCM types (e.g., `Dcm_DspDataServiceType` with `...` in EA) often show `PARAM_TYPE` deviations. These are usually **EA data quality issues** where EA truncates the type name in the tagged value. They are not real code deviations.

---

## Troubleshooting

| Issue | Root Cause | Solution |
|-------|-----------|----------|
| "No module matching..." | Module name format or spelling | Confirm `SwMod_*`, use `--filter` to disambiguate |
| "SourceFile not found" | EA has typo in `SourceFile` tag | Use `--class <ClassName>` to bypass file matching |
| "PARAM_TYPE differs" on DCM types with `...` | EA truncates long type names | This is a data quality issue in EA; check EA model directly |
| "EA not responding" when running export | EA not open or project not loaded | Open EA, load the project, ensure 32-bit Python with pywin32 |
| "function name not found" | C parser missed the function | Check if function uses unusual formatting or ifdef guards |
| Missing design functions in export | EA class not properly linked to module | Verify `SourceFile` tagged value and class inclusion in package |

---

## File Organization

```
.github/
  scripts/
    ea/                                ← CONSOLIDATED EA TOOLS LOCATION (v2.0+)
      .env                             ← Configuration (not committed)
      .env.template                    ← Template (commit this)
      __init__.py
      
      ✅ GENERATION ORCHESTRATION:
      ea_diagram_to_code.py            ← PRIMARY ENTRY POINT ⭐
      
      ✅ GENERATION ENGINES:
      xml_to_c.py                      ← Flow graph parsing (imported by orchestration)
      (XMI parsing integrated into ea_diagram_to_code.py)
      
      ✅ DESIGN EXPORT:
      export_module_functions.py       ← Export EA function lists
      export_module_diagrams.py        ← Export & render diagrams
      export_traceability.py           ← Export traceability links
      export_arch_design.py            ← Export architecture (markdown/json subcommands, --scope all/subsystem/platform)
      export_sequence_diagrams.py      ← Export sequence diagrams (PlantUML, --scope all/subsystem/platform)
      ea_connect.py                    ← Shared COM-connection helper (not run directly)
      run_export_until_done.ps1        ← Retry driver for sequence-diagram export (EA COM instability)
      diagnostics/                     ← One-off read-only exploration scripts (not part of normal workflow)
      
      ✅ COMPARISON & ANALYSIS:
      compare_design_code.py           ← Design vs. code deviations
      report_missing_traceability.py   ← Traceability gaps
      
      ✅ ROUND-TRIP:
      import_code_to_diagrams.py       ← Parse C → XML diagrams
      ea_import_diagrams_from_xml.py   ← Import XML → EA
      
      ✅ UTILITIES:
      parse_ms_diagram.py              ← Diagnostic utility
      _probe_colors.py                 ← Debugging utility
      _probe_ea_activity.py            ← Debugging utility
      
      ✅ DOCUMENTATION:
      README.md                        ← Detailed tool reference
      SETUP_GUIDE.md                   ← Environment setup
      CONFIG_STRATEGY.md               ← Configuration patterns
      requirements.txt                 ← Python dependencies
      
  agents/
    EnterpriseArc.agent.md           ← Workflow orchestrator
  skills/
    enterprise-architect/
      SKILL.md                       ← THIS FILE

config/
  settings.py                        ← Legacy configuration (use .env in .github/scripts/ea/ instead)

doc/
  SwMod_*_Functions.md               ← Markdown exports from EA
  SwMod_*_diagrams.md
  CONSOLIDATION_SUMMARY.md           ← Tools migration (v2.0)

ai_output/
  generated_c/                       ← Generated C source files
  traceability/                      ← JSON traceability exports
  arch_design/                       ← Markdown docs + JSON, both from export_arch_design.py (markdown/json subcommands)
    diagrams/                       ← PlantUML sequence diagrams (export_sequence_diagrams.py)
      _export_manifest.json         ← Resume checkpoint (diagram_id -> exported filename)
  reports/                           ← Deviation reports and analysis

src/
  main.py                            ← Legacy (retained for reference)
```

---

## Quick Start

1. **Set up environment:**
   ```bash
   cp .github/scripts/ea/.env.template .github/scripts/ea/.env
   # Edit .env with your EA_PROJECT path
   ```

2. **Export design functions (one-time baseline):**
   ```bash
   & ".venv32\python.exe" .github/scripts/ea/export_module_functions.py SwMod_TouchSM
   ```

3. **Compare design vs. code (no EA needed after step 2):**
   ```bash
   python .github/scripts/ea/compare_design_code.py SwMod_TouchSM touchsm1c1.c \
       --src-dir input/touchsm/core \
       --from-doc SwMod_TouchSM
   ```

4. **Check traceability:**
   ```bash
   & ".venv32\python.exe" .github/scripts/ea/export_traceability.py SwMod_TouchSM
   python .github/scripts/ea/report_missing_traceability.py
   ```

---

## Related Resources

- `.github/agents/EnterpriseArc.agent.md` — Workflow orchestration and multi-step tasks
- `.github/scripts/ea/README.md` — Detailed per-tool reference and CLI help
- `.github/scripts/ea/CONFIG_STRATEGY.md` — Configuration best practices

