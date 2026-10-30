#!/usr/bin/env python3
"""
Doxygen Template Setup and Rename Tool

Usage:
    python setup_and_rename_dox.py <module_path>
        Download template, extract to <module_path>/doc/, rename swmod_*.dox -> <module>_*.dox

    python setup_and_rename_dox.py rename <dox_folder>
        Rename swmod_*.dox -> <module>_*.dox in an existing dox folder

Examples:
    python setup_and_rename_dox.py d:/MetaUX1/pkg/em_s3p_hud/s3pcommon/tmrctl
    python setup_and_rename_dox.py rename d:/MetaUX1/pkg/em_s3p_hud/systemctl/fsv/doc/dox
"""

import re
import sys
import shutil
import zipfile
import urllib.request
from pathlib import Path
from urllib.error import URLError, HTTPError

TEMPLATE_URL = (
    "https://github-ix.int.automotive-wan.com/uidp4364/designdoc_doxygen"
    "/raw/idd_vw_abte3_tplt/template/doc.zip"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def module_name_from_dox(dox_path: Path) -> str:
    """Walk up past any 'doc'/'dox' folders to find the real module name."""
    cur = dox_path.resolve().parent
    while cur.name.lower() in ("doc", "dox") and cur != cur.parent:
        cur = cur.parent
    return cur.name.lower()


def download(url: str, dest: Path) -> None:
    """Download url to dest with progress."""
    print(f"Downloading template...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        with open(dest, "wb") as f:
            while chunk := resp.read(65536):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done * 100 // total}%  ({done:,}/{total:,} bytes)", end="", flush=True)
    print(f"\r  Done: {done:,} bytes{' ' * 30}")


def extract(zip_path: Path, module_path: Path) -> Path:
    """
    Extract zip to module_path. The zip contains a top-level 'doc/' folder.
    Flattens any nested doc/doc structure. Returns the dox/ folder path.
    """
    print(f"Extracting template...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        print(f"  {len(zf.namelist())} files in archive")
        zf.extractall(module_path)

    # Fix nested doc/doc structure if present
    nested = module_path / "doc" / "doc"
    if nested.is_dir():
        dest = module_path / "doc"
        for item in list(nested.iterdir()):
            target = dest / item.name
            if not target.exists():
                shutil.move(str(item), str(target))
        try:
            nested.rmdir()
        except OSError:
            pass

    dox = module_path / "doc" / "dox"
    if not dox.exists():
        raise FileNotFoundError(f"dox folder not found after extraction: {dox}")
    return dox


def rename_swmod(dox_path: Path, module: str) -> None:
    """Rename all swmod_X_*.dox -> <module>_X_*.dox."""
    pattern = re.compile(r"^swmod_(\d+)_(.+\.dox)$", re.IGNORECASE)
    renamed = skipped = errors = 0

    for f in sorted(dox_path.iterdir()):
        if not (f.is_file() and f.suffix == ".dox"):
            continue
        m = pattern.match(f.name)
        if not m:
            continue
        new_path = dox_path / f"{module}_{m.group(1)}_{m.group(2)}"
        if new_path.exists():
            print(f"  SKIP  {f.name}")
            skipped += 1
            continue
        try:
            f.rename(new_path)
            print(f"  {f.name}  →  {new_path.name}")
            renamed += 1
        except Exception as e:
            print(f"  ERROR {f.name}: {e}")
            errors += 1

    print(f"\nResult: {renamed} renamed, {skipped} skipped, {errors} errors")


def patch_doxyfile(module_path: Path, module: str) -> None:
    """Patch Doxyfile after template setup:
      - PROJECT_NAME: "SWMOD" → capitalized module name
      - INPUT: remove ../adapt if no adapt/ folder exists at module level
      - INPUT: rename dox/swmod_N_ → dox/<module>_N_
      - FILTER_PATTERNS: comment out to avoid .fidl parse errors
    """
    doxyfile = module_path / "doc" / "Doxyfile"
    if not doxyfile.exists():
        print(f"  SKIP  Doxyfile not found at {doxyfile}")
        return

    content = doxyfile.read_text(encoding="utf-8")
    original = content

    # 1. PROJECT_NAME: "SWMOD" → "<Module>" (capitalize first letter)
    display_name = module[0].upper() + module[1:]
    content = re.sub(
        r'(PROJECT_NAME\s*=\s*)"SWMOD"',
        rf'\1"{display_name}"',
        content,
    )

    # 2. INPUT: remove ../adapt if no adapt/ folder exists at module level
    adapt_path = module_path / "adapt"
    if not adapt_path.is_dir():
        content = re.sub(r"\.\./adapt\s+", "", content)

    # 3. INPUT: rename dox/swmod_N_ → dox/<module>_N_
    content = re.sub(r"(dox/)swmod_", rf"\g<1>{module}_", content)

    # 4. Comment out FILTER_PATTERNS (causes errors with .fidl extension)
    content = re.sub(
        r"^(FILTER_PATTERNS\b)",
        r"#\1",
        content,
        flags=re.MULTILINE,
    )

    if content == original:
        print("  Doxyfile: already up to date, no changes")
        return

    doxyfile.write_text(content, encoding="utf-8")
    print("  Doxyfile patched:")
    orig_lines, new_lines = original.splitlines(), content.splitlines()
    for i, (a, b) in enumerate(zip(orig_lines, new_lines)):
        if a != b:
            print(f"    Line {i + 1}: {a.strip()!r:50s} → {b.strip()!r}")
    if len(new_lines) != len(orig_lines):
        print(f"    (line count: {len(orig_lines)} → {len(new_lines)})")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_full(module_path: Path) -> None:
    """Download template, extract, and rename."""
    module = module_path.name.lower()
    zip_path = module_path / "template.zip"

    print(f"Module : {module}")
    print(f"Path   : {module_path}")
    print(f"URL    : {TEMPLATE_URL}\n")

    try:
        download(TEMPLATE_URL, zip_path)
    except (HTTPError, URLError, OSError) as e:
        print(f"ERROR: Download failed — {e}")
        sys.exit(1)

    try:
        dox_path = extract(zip_path, module_path)
        print(f"  Extracted to: {dox_path}")
    except (zipfile.BadZipFile, FileNotFoundError, OSError) as e:
        print(f"ERROR: Extraction failed — {e}")
        sys.exit(1)
    finally:
        zip_path.unlink(missing_ok=True)

    print(f"\nRenaming swmod_*.dox → {module}_*.dox ...")
    rename_swmod(dox_path, module)

    print("\nPatching Doxyfile ...")
    patch_doxyfile(module_path, module)


def cmd_rename(dox_path: Path) -> None:
    """Rename swmod_*.dox in an existing dox folder."""
    if not dox_path.is_dir():
        print(f"ERROR: Folder not found: {dox_path}")
        sys.exit(1)
    module = module_name_from_dox(dox_path)
    module_path = dox_path.parent.parent  # dox_path is module/doc/dox/
    print(f"Module : {module}")
    print(f"Folder : {dox_path}")
    print(f"\nRenaming swmod_*.dox → {module}_*.dox ...")
    rename_swmod(dox_path, module)

    print("\nPatching Doxyfile ...")
    patch_doxyfile(module_path, module)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    if args[0].lower() == "rename":
        if len(args) < 2:
            print("Usage: python setup_and_rename_dox.py rename <dox_folder>")
            sys.exit(1)
        cmd_rename(Path(args[1]).resolve())
    else:
        cmd_full(Path(args[0]).resolve())


if __name__ == "__main__":
    main()
