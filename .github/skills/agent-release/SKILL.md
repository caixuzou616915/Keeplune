---
name: agent-release
description: >
  Release workflow for this UX AI agent catalogue repo. Verifies a clean `uxai sync` install
  (agents, skills, scripts, mcp-servers, rules) into a scratch directory and diffs it against
  the source repo, generates a short-bullet changelog file at changelog/<version>.md summarizing
  changes since the last release tag, and creates + pushes an annotated release tag (format
  vNN.NN.NN, e.g. v01.01.08) on `main` after optionally merging in a source branch. Use when:
  the user asks to "release", "cut a release", "tag a release", "publish a new version",
  "generate the changelog", or "release <branch> to main". Used by the `uxai-deploy` agent's
  release workflow.
metadata:
  author: "GitHub Copilot"
  version: "1.0.0"
---

# Agent Release

## Overview

Produces a versioned, verified release of this catalogue repo: confirms the release source
(branch to merge into `main`, or `main` as-is), proves the resulting `.github/` tree still
installs cleanly via `uxai sync` (catching layout/catalog bugs like the klocwork
skills->scripts relocation incident before they reach a tagged release), writes a short
changelog, and tags + pushes `main`. Optionally hands off to the project-branch deploy
workflow afterward.

## Prerequisites

- `uxai` CLI available on PATH (`uxai --version`).
- Clean or known working-tree state — check `git status` before starting; do not silently
  commit unrelated in-progress changes as part of a release commit.
- A scratch directory for install verification, default `d:/temp` (create a dedicated
  subfolder under it, e.g. `d:/temp/uxai_release_check`, never reuse it for anything else so a
  stale prior run can't produce a false "match").

## Workflow

### Step 1 — Determine release source and version

Ask the user (skip whichever is already given):
1. **Which branch to merge into `main`** for this release — or "none"/"main" to release
   `main` as-is with no merge.
2. **Release version number**, format `vNN.NN.NN` (e.g. `v01.01.08`). Validate against
   `^v\d{2}\.\d{2}\.\d{2}$`; if the user supplies a different shape, show them the expected
   format and ask them to confirm before proceeding rather than silently reformatting it.

Find the previous release tag (for changelog diffing and to confirm this version doesn't
already exist):
```powershell
git fetch --all --prune --tags
git tag --list "v*" --sort=-version:refname | Select-Object -First 5
```
If the requested version tag already exists, stop and ask the user to pick a different one —
never overwrite/move an existing tag without explicit confirmation of that exact destructive
operation.

### Step 2 — Merge source branch into main (optional)

Skip entirely if the user chose "main"/"none" in Step 1. Otherwise:
```powershell
git checkout main
git pull origin main
git merge --no-ff origin/<branch> -m "Merge <branch> into main for release <version>"
```
Apply the same conflict-handling rules as the `uxai-deploy` project-branch workflow: on
conflict, run `git status` / `git diff --name-only --diff-filter=U`, report the conflicting
files, `git merge --abort`, and stop — never force-resolve. Do not push yet.

### Step 3 — Generate the changelog

List commits since the previous tag (or full history if there is no previous tag):
```powershell
git log <prev-tag>..HEAD --oneline --no-merges
```
Summarize into short bullet points — one line per notable change, grouped by area
(agents / skills / scripts / catalog / docs) only if that helps readability. No prose
paragraphs, no restating the full commit body. Skip noise (merge commits, unrelated WIP).

Create `changelog/` at the repo root if it doesn't exist, and write `changelog/<version>.md`:
```markdown
# <version> — <YYYY-MM-DD>

- Short bullet point 1
- Short bullet point 2
```

### Step 4 — Pre-release install verification (mandatory gate before tagging)

This step exists specifically to catch catalog/layout bugs before they ship in a tagged
release (e.g. a resource declared in `catalog.yaml` but physically relocated, which silently
breaks `uxai sync` for every consumer — see the klocwork scripts-relocation incident).

```powershell
$verifyDir = "d:/temp/uxai_release_check"
Remove-Item -Recurse -Force $verifyDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $verifyDir | Out-Null
uxai --repo . sync --tool github-copilot --target $verifyDir
```

Read the sync output first: any `Script not found in catalogue` (or equivalent "not found")
line is an automatic **fail** — stop and report it, do not proceed to tagging.

Then diff file lists per resource category between the source repo and the verify directory:
```powershell
foreach ($cat in "agents", "skills", "scripts", "mcp-servers", "rules") {
    $src = Get-ChildItem ".github/$cat" -Recurse -File -ErrorAction SilentlyContinue |
        ForEach-Object { $_.FullName.Substring((Resolve-Path ".github/$cat").Path.Length) }
    $dst = Get-ChildItem "$verifyDir/.github/$cat" -Recurse -File -ErrorAction SilentlyContinue |
        ForEach-Object { $_.FullName.Substring((Resolve-Path "$verifyDir/.github/$cat").Path.Length) }
    Write-Host "--- $cat ---"
    Compare-Object $src $dst
}
```
An empty `Compare-Object` result for a category means it matches exactly. Any `<=` (source
only, missing from install) or `=>` (unexpectedly appeared) entries must be explained — a
`<=` on a file that isn't actually catalog-registered (e.g. deliberately project-scoped, or
deprecated) is fine; anything else blocks the release until fixed.

Clean up the scratch folder once verification is done (pass or fail):
```powershell
Remove-Item -Recurse -Force $verifyDir -ErrorAction SilentlyContinue
```

If verification fails, stop here, report the gap to the user, and do not tag.

### Step 5 — Create & push the release tag

Confirm before this step (hard-to-reverse, shared): "Create and push tag `<version>` on
`main` now?"

```powershell
git add changelog/<version>.md
git commit -m "Release <version>: add changelog"
git tag -a <version> -m "Release <version>"
git push origin main
git push origin <version>
```

### Step 6 — Offer project deploy

After the tag is pushed, ask: "Deploy `<version>` to project branches now?"
- **Yes** → hand off to the `uxai-deploy` agent's existing project-branch-sync workflow
  (merge `main` into every `projects/*` branch, confirm per-branch before pushing).
- **No** → stop here.

## Final Summary (always report)

- Release version + tag ref
- Changelog file path
- Verification result (pass, with per-category match; or fail + exact diff)
- Whether project deploy ran, and its per-branch outcome if so

## Resources

- `changelog/<version>.md` — one file per release, created by this workflow.
- `uxai` CLI (`--repo`, `--target`, `--tool github-copilot`) — used for install verification.
