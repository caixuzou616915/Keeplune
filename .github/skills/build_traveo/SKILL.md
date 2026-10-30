---
name: build_traveo
description: >-
  Discover and run the project's root-level build scripts for the S3P / Traveo II meta-repo:
  list all available variants from `zz_build_[variant].sh`, identify which variants also have
  a release script `zz_release_build_[variant].sh`, and pick the correct script (Debug vs
  Release) for a requested variant + build type. Use when: the user asks "what variants can I
  build", "build <variant>", "release build <variant>", or before invoking any flash/debug flow
  that needs a fresh build first.
argument-hint: 'e.g.: list build variants; build tviib_e4m_aravalli_s3p; release build tviib_e4m_aravalli_s3p v01.02.00'
---

# Traveo II / S3P — Root Build Script Discovery & Selection

Project root: wherever `run.py` and `econ_config.sh` live (the workspace root of the meta-repo
currently open). All `zz_build_*.sh` and `zz_release_build_*.sh` scripts live directly in that
project root, are bash scripts (run via Git Bash, NOT plain PowerShell), and internally call
`python run.py <variant>.<Debug|Release> <action>`.

**Every project/repo has its own set of variants** — never assume or hardcode a variant list
from a previous project or session. Always (re-)run the discovery commands below against the
current project root first.

## 1. Discover available variants (Debug build scripts)

List every `zz_build_[variant].sh` in the project root and derive the variant name by
stripping the `zz_build_` prefix and `.sh` suffix:

```powershell
Get-ChildItem -Path '<project_root>' -Filter 'zz_build_*.sh' |
  ForEach-Object { $_.BaseName -replace '^zz_build_', '' } |
  Sort-Object
```

Each resulting name is a valid `<variant>` value usable with `run.py <variant>.<Debug|Release> ...`.

Variant names commonly follow a `<base_variant>[_flu|_fbl|_second|_w_hmi|...]` pattern, where
the suffix (if present) selects a sub-component build (bootloader, secondary core, HMI overlay,
etc.) rather than a physically different ECU/target. Don't assume this pattern is exhaustive or
that every base variant has every suffix — the discovery listing is the only source of truth;
derive any grouping/notes from what's actually present, not from a fixed suffix list.

## 2. Discover release-capable variants

Release scripts follow `zz_release_build_[variant].sh` and typically only exist for a subset of
variants (the ones that actually ship as a release build):

```powershell
Get-ChildItem -Path '<project_root>' -Filter 'zz_release_build_*.sh' |
  ForEach-Object { $_.BaseName -replace '^zz_release_build_', '' } |
  Sort-Object
```

Any variant name that appears in step 1 but NOT in this step's listing is Debug-only —
requesting a "release build" for it should be reported as unavailable rather than guessed or
substituted with a similarly-named variant.

## 3. Script selection logic

**Enforcement: the root `zz_build_*.sh` / `zz_release_build_*.sh` script is the ONLY supported
entry point for a build. Never call `python run.py <variant>.<Debug|Release> build` directly as
a substitute or fallback** — the root script sources `econ_config.sh` and runs required
post-build steps (memrpt, flashfile packaging) that a bare `run.py` invocation skips.

Given a requested `<variant>` and optional `build_type` (`debug` default, or `release`):

```
release_script = "zz_release_build_<variant>.sh"
debug_script   = "zz_build_<variant>.sh"

if build_type == "release":
    if release_script exists in project root:
        use release_script
    else:
        ERROR: "No release script for <variant>; only Debug is available via " + debug_script
else:
    if debug_script exists in project root:
        use debug_script
    else:
        ERROR: "Unknown variant '<variant>' — not found in zz_build_*.sh listing (see step 1)"
```

If script selection hits either `ERROR` case above, **do not fall back to `run.py` directly**.
Stop and present the user with the exact discovery listing from step 1 (and step 2 for release
requests) so they can pick a valid variant/build-type combination.

Key differences between the two script families (confirmed by reading a sample of each in this
repo — verify against the actual script content if a project's convention differs):
- `zz_build_<variant>.sh` → typically `python run.py <variant>.Debug ...`, output under `build/<variant>.Debug/`.
- `zz_release_build_<variant>.sh` → typically `python run.py <variant>.Release ...`, output under
  `build/<variant>.Release/`, and may take an optional **positional software-version argument**
  in the form `vMM.mm.pp` (e.g. `v01.02.00`); if omitted it commonly defaults to `v00.00.00`. It
  may also stamp git-SHA/dirty-flag info into a generated header (project-specific).
- Both flavors typically produce flashable artifacts under `bin/flashfiles/<variant>/`.
- Do not assume these details are universal — grep the target script for `run.py`, the
  `build_type`/`variant` variable assignments, and any `$1`/positional-argument usage if the
  behavior needs to be confirmed for a specific project.

## 4. Running the selected script

All `zz_*.sh` scripts are bash and MUST be run through Git Bash (not native PowerShell/cmd).
Replace `<project_root>` and `<variant>` with the actual values discovered above:

```powershell
& "C:\Program Files\Git\bin\bash.exe" -c "cd <project_root_as_bash_path> && source econ_config.sh && ./zz_build_<variant>.sh 2>&1 | tee /tmp/build.log"
```

Release build with an explicit version (example from this repo):

```powershell
& "C:\Program Files\Git\bin\bash.exe" -c "cd /c/Project/JB/s3p/sw.sys.tv2.meta-repo-ux && source econ_config.sh && ./zz_release_build_tviib_e4m_aravalli_s3p.sh v01.02.00 2>&1 | tee /tmp/release_build.log"
```

`econ_config.sh` reads stdin — never wrap it inside a multi-line heredoc; always a single-line
`-c "... && ..."` chain (same constraint as documented in the `debug_traveo_ghs` skill).

## Error Handling

| Symptom | Cause / Fix |
|---|---|
| `ERROR: script not found` | Variant name typo — re-run step 1's `Get-ChildItem` listing, show it to the user, and ask them to pick the exact spelling. Do NOT fall back to `run.py` directly |
| Requested "release" for a variant not in step 2's list | No release script exists — offer Debug (`zz_build_<variant>.sh`) as the alternative and confirm with the user before switching; still never call `run.py` directly |
| `Invalid software version format` | Release scripts require `vMM.mm.pp` (e.g. `v01.02.00`), not `1.2.0` or `v1.2.0` |
| `realpath: command not found` | Wrong bash — must be `C:\Program Files\Git\bin\bash.exe`, not WSL/msys bash |
| Build succeeds but flash uses stale binaries | Confirm the correct `build/<variant>.<Debug|Release>/` folder timestamp matches the just-completed build before handing off to the `debug_traveo_ghs` flash flow |
