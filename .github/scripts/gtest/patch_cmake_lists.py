#!/usr/bin/env python3
"""
GTF CMakeLists.txt Include Path Updater
========================================

PURPOSE:
--------
Automatically scans source files, test files, mock files, and stub files to find all
#include directives, then searches the project for those headers and updates the
variant-specific CMakeLists.txt with missing include paths. This prevents compilation
errors due to missing header file paths in the GTF test build configuration.

Author: Zhao Jianbo
Supported by: UX SW AI Community

WHEN TO USE:
------------
- BEFORE building GTF tests for the first time (recommended)
- After adding new test files, mock files, or stub files
- When compilation fails with "header not found" errors
- After updating module dependencies
- When switching between modules or build variants

WHAT IT DOES:
-------------
1. Locates the source file and its test/gtest folder structure
2. Extracts all #include statements from:
   - Source file (e.g., vsgen1c1.c)
   - Test files (unittest_*_test.cpp)
   - Mock files (mock_*_pf.hpp/cpp)
   - Stub files (*_stub.h)
3. Searches project for each header file with priority order:
   - Priority folders (common_ext, etc.)
   - pkg/ directory
   - app/ directory
   - Module-specific directories
4. Calculates relative paths from variant CMakeLists.txt to header locations
5. Updates target_include_directories() in CMakeLists.txt with new paths
6. Adds comments showing which headers each path provides
7. Reports headers that cannot be found

OUTPUT:
-------
- Updates: [Module]/test/gtest/prj/unittest_[module]_[variant]/CMakeLists.txt
- Adds PRIVATE include paths with auto-generated comments
- Reports: Found headers, missing headers, paths added
- Optional: Removes #include statements for unfound headers (with --remove-unfound)

COMMAND-LINE OPTIONS:
---------------------
<source_file>       Source file name (e.g., vsgen1c1.c)
--project-root      Project root directory (default: current directory)
--variant           Build variant name (default: pf)
--remove-unfound    Remove #include lines for headers that cannot be found

USAGE EXAMPLES:
---------------

1. Basic Usage (Recommended before first build):
   cd C:\Projects\s3p_arav
   python patch_cmake_lists.py vsgen1c1.c
   
   Output:
   - Scans all test/mock/stub files for includes
   - Finds header locations in project
   - Updates CMakeLists.txt with new paths
   - Reports summary of changes

2. Specify Different Variant:
   python patch_cmake_lists.py usmngsm1c1.c --variant pf
   
   Output:
   - Updates unittest_usmngsm_pf/CMakeLists.txt

3. Remove Unfound Includes:
   python patch_cmake_lists.py vsgen1c1.c --remove-unfound
   
   Output:
   - Updates CMakeLists.txt with found headers
   - Removes #include lines for headers that cannot be found
   - Prevents compilation warnings for missing headers

4. Custom Project Root:
   python patch_cmake_lists.py module.c --project-root /path/to/project

INTEGRATION WITH GTF WORKFLOW:
-------------------------------
This tool is part of the GTF test preparation workflow:

Step 1: Generate preprocessed clean file (optional, recommended)
   python gen_standard_c.py [source_file.c] --execute --clean

Step 2: Update CMakeLists.txt with include paths (THIS TOOL)
   python patch_cmake_lists.py [source_file.c]

Step 3: Build and run GTF tests
   run_module_gtest.bat [source_file.c]

BENEFITS:
---------
- ✅ Prevents "header not found" compilation errors
- ✅ Saves time locating and calculating header paths manually
- ✅ Documents which headers require each include path (comments)
- ✅ Maintains consistent relative path format
- ✅ Handles nested header paths correctly
- ✅ Prioritizes common header locations (common_ext)
- ✅ Avoids duplicate paths

PRIORITY SEARCH ORDER:
----------------------
Headers are searched in this order:
1. app/pkg/em_s3p_hud/s3phudcommon/s3phuddef (priority)
2. pkg/em_s3p_hud/s3phudcommon/s3phuddef (priority)
3. pkg/ directory (general)
4. app/ directory (general)
5. Module-specific directories

TYPICAL OUTPUT EXAMPLE:
-----------------------
[INFO] Starting GTF Include Path Update
[INFO] Source File: vsgen1c1.c
[OK] Found source file: pkg/em_s3p_hud/videoctl/vsgen/core/vsgen1c1.c
[OK] Found module root: pkg/em_s3p_hud/videoctl/vsgen
[OK] Found test harness: pkg/em_s3p_hud/videoctl/vsgen/test/gtest
[OK] Found 45 unique header includes

[INFO] Searching for header file paths in project...
  Searching for: Std_Types.h -> Found: app/pkg/.../common_ext
  Searching for: vidcond1c1.h -> Found: pkg/em_s3p_hud/videoctl/vidcond/core
  ...

[OK] Added 12 new include paths to CMakeLists.txt
  + app/pkg/.../common_ext (for: Std_Types.h, Rte_Type.h, Platform_Types.h)
  + pkg/em_s3p_hud/videoctl/vidcond/core (for: vidcond1c1.h)

[OK] GTF Include Path Update Complete!

NOTES FOR AI AGENTS:
--------------------
- Always run this tool BEFORE attempting to build GTF tests
- If compilation errors persist, run with --remove-unfound to clean up
- The tool automatically calculates relative paths from CMakeLists.txt location
- Check the generated comments in CMakeLists.txt to verify correct paths
- Re-run after adding new mock or stub files to update paths
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional

# ============================================================================
# CONFIGURATION: Priority Search Folders
# ============================================================================
# Headers will be searched in these folders first (in order) before searching
# in other project locations. Paths are relative to project root.
PRIORITY_SEARCH_FOLDERS = [
    "app/pkg/em_s3p_hud/s3phudcommon/s3phuddef",
    "pkg/em_s3p_hud/s3phudcommon/s3phuddef",
]

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg: str):
    print(f"{Colors.GREEN}[OK] {msg}{Colors.RESET}")

def print_info(msg: str):
    print(f"{Colors.CYAN}[INFO] {msg}{Colors.RESET}")

def print_warn(msg: str):
    print(f"{Colors.YELLOW}[WARN] {msg}{Colors.RESET}")

def print_error(msg: str):
    print(f"{Colors.RED}[ERROR] {msg}{Colors.RESET}")

def find_source_file(source_file: str, project_root: Path) -> Optional[Path]:
    """Find the source file in the project."""
    print_info(f"Searching for source file: {source_file}")
    
    # Search in common directories, excluding build/bin folders
    search_paths = ['pkg', 'app']
    
    for search_path in search_paths:
        search_dir = project_root / search_path
        if not search_dir.exists():
            continue
            
        for file_path in search_dir.rglob(source_file):
            # Skip build and bin directories
            if 'build' in file_path.parts or 'bin' in file_path.parts:
                continue
            return file_path
    
    return None

def find_module_root(source_file_path: Path) -> Optional[Tuple[Path, Path]]:
    """Find module root and gtest path by searching up from source file."""
    print_info("Locating module root and test harness...")
    
    current_dir = source_file_path.parent
    max_levels = 5
    
    for _ in range(max_levels):
        # Check current level for test/gtest
        test_gtest = current_dir / "test" / "gtest"
        if test_gtest.exists() and test_gtest.is_dir():
            return current_dir, test_gtest
        
        # Check parent level for test/gtest
        parent_dir = current_dir.parent
        parent_test_gtest = parent_dir / "test" / "gtest"
        if parent_test_gtest.exists() and parent_test_gtest.is_dir():
            return parent_dir, parent_test_gtest
        
        current_dir = parent_dir
        
        # Stop at project root
        if current_dir.parent == current_dir:
            break
    
    return None

def extract_includes(file_path: Path) -> Set[str]:
    """Extract #include statements from a file."""
    includes = set()
    include_pattern = re.compile(r'^\s*#\s*include\s+[<"]([^>"]+)[>"]')
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                match = include_pattern.match(line)
                if match:
                    header = match.group(1)
                    # Skip system headers
                    if not any(header.startswith(sys_hdr) for sys_hdr in 
                              ['std', 'cstdint', 'cstdio', 'cstring', 'iostream', 
                               'vector', 'map', 'memory', 'algorithm', 'gtest', 'gmock']):
                        includes.add(header)
    except Exception as e:
        print_warn(f"Could not read {file_path}: {e}")
    
    return includes

def collect_source_files(gtest_path: Path) -> List[Path]:
    """Collect all test, mock, and stub files."""
    source_files = []
    
    # Test files
    tests_path = gtest_path / "tests"
    if tests_path.exists():
        test_files = list(tests_path.glob("unittest_*_test.cpp"))
        source_files.extend(test_files)
        print_info(f"Found {len(test_files)} test file(s)")
    
    # Mock files
    mocks_path = gtest_path / "prj" / "tfr" / "mocks"
    if mocks_path.exists():
        mock_files = list(mocks_path.glob("*.[ch]pp")) + list(mocks_path.glob("*.[ch]"))
        source_files.extend(mock_files)
        print_info(f"Found {len(mock_files)} mock file(s)")
    
    # Stub files
    stubs_path = gtest_path / "prj" / "tfr" / "stub"
    if stubs_path.exists():
        stub_files = list(stubs_path.glob("*.[ch]pp")) + list(stubs_path.glob("*.[ch]"))
        source_files.extend(stub_files)
        print_info(f"Found {len(stub_files)} stub file(s)")
    
    return source_files

def find_header_path(header: str, project_root: Path, module_path: Path) -> Optional[Path]:
    """Find the directory path for a header file."""
    header_name = os.path.basename(header)
    
    def search_in_path(search_path: Path) -> Optional[Path]:
        """Helper function to search for header in a given path."""
        if not search_path.exists():
            return None
            
        for file_path in search_path.rglob(header_name):
            # Skip build and bin directories
            if 'build' in file_path.parts or 'bin' in file_path.parts:
                continue
            
            # For nested headers, verify the path structure matches
            if '/' in header or '\\' in header:
                header_parts = header.replace('\\', '/').split('/')
                file_parts = file_path.as_posix().split('/')
                
                # Check if the end of the path matches
                if len(file_parts) >= len(header_parts):
                    match = True
                    for i in range(len(header_parts)):
                        if file_parts[-(len(header_parts)-i)] != header_parts[i]:
                            match = False
                            break
                    if match:
                        # Return the directory containing the start of the include path
                        include_start_idx = len(file_parts) - len(header_parts)
                        return Path(*file_parts[:include_start_idx])
            else:
                # Simple header, return parent directory
                return file_path.parent
        return None
    
    # Search in priority folders first (in order)
    for priority_folder in PRIORITY_SEARCH_FOLDERS:
        priority_path = project_root / priority_folder
        result = search_in_path(priority_path)
        if result:
            return result
    
    # Search in common locations
    search_paths = [
        project_root / "pkg",
        project_root / "app",
        module_path
    ]
    
    # Then search in general search paths
    for search_path in search_paths:
        result = search_in_path(search_path)
        if result:
            return result
    
    return None

def extract_module_name(source_file: str) -> str:
    """Extract module name from source file name.
    
    Examples:
    - vsgen1c1.c -> vsgen
    - touchq1c1.c -> touchq
    - usmngsm1c1.c -> usmngsm
    """
    # Remove .c or .cpp extension
    name = source_file.replace('.c', '').replace('.cpp', '')
    
    # Remove trailing numbers (e.g., 1c1 -> '')
    # Match pattern like [0-9]c[0-9] at the end
    match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*?)(?:\d+c\d+)?$', name)
    if match:
        return match.group(1)
    return name

def find_module_header_dirs(module_name: str, project_root: Path) -> List[Path]:
    """Find directories with header files in both app/pkg and pkg module paths.
    
    For a module named 'vsgen', searches for:
    - app/pkg/em_s3p_hud/videoctl/vsgen/*/[includes .h files]
    - pkg/em_s3p_hud/videoctl/vsgen/*/[includes .h files]
    
    Returns a list of directory paths that contain .h files.
    """
    header_dirs = []
    
    # Two standard locations for modules
    module_search_prefixes = [
        project_root / "app" / "pkg",
        project_root / "pkg"
    ]
    
    for prefix in module_search_prefixes:
        if not prefix.exists():
            continue
        
        # Search for folders matching the pattern: */module_name or */...module_name/...
        # We search recursively for folders that match the module name
        for folder in prefix.rglob("*"):
            if not folder.is_dir():
                continue
            
            folder_name = folder.name
            
            # Check if this folder name matches the module name or contains module structure
            # e.g., vsgen1c1.c -> look for "vsgen" folder
            if module_name in folder_name or folder_name == module_name:
                # Found a matching folder, now search for directories with .h files
                for subdir in folder.rglob("*"):
                    if not subdir.is_dir():
                        continue
                    
                    # Skip test and build directories
                    if any(skip in subdir.parts for skip in ['test', 'build', 'bin', '.git']):
                        continue
                    
                    # Check if this directory contains .h files
                    h_files = list(subdir.glob("*.h"))
                    if h_files:
                        # Normalize path relative to project root
                        try:
                            rel_path = subdir.relative_to(project_root)
                            if rel_path not in header_dirs:
                                header_dirs.append(subdir)
                                print_info(f"  Found header directory in module: {rel_path} ({len(h_files)} headers)")
                        except ValueError:
                            pass
    
    return header_dirs

def get_current_includes(cmake_file: Path) -> Set[str]:
    """Extract current include paths from CMakeLists.txt."""
    current_includes = set()
    
    try:
        with open(cmake_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find all include_directories blocks
        include_pattern = re.compile(r'include_directories\s*\([^)]+\)', re.DOTALL)
        matches = include_pattern.findall(content)
        
        for match in matches:
            # Extract paths from the block
            path_pattern = re.compile(r'"([^"]+)"')
            paths = path_pattern.findall(match)
            
            for path in paths:
                if path and 'include_directories' not in path:
                    current_includes.add(path)
        
        # Also find target_include_directories blocks
        # Match until we find ) on its own line (with optional whitespace)
        # Use [\s\S] to match any character including newlines, non-greedy, until \n)
        target_include_pattern = re.compile(r'target_include_directories\s*\(([\s\S]*?)\n\)', re.MULTILINE)
        target_matches = target_include_pattern.findall(content)
        
        for match in target_matches:
            # Extract paths from the block (skip PRIVATE/PUBLIC/INTERFACE keywords)
            # Match patterns like: "${CMAKE_CURRENT_SOURCE_DIR}/path" or "${MUT_LOCATION}/path"
            path_pattern = re.compile(r'"([^"]+)"')
            paths = path_pattern.findall(match)
            
            for path in paths:
                if path and 'target_include_directories' not in path and path.upper() not in ['PRIVATE', 'PUBLIC', 'INTERFACE']:
                    current_includes.add(path)
    
    except Exception as e:
        print_warn(f"Could not read CMakeLists.txt: {e}")
    
    return current_includes

def update_cmake_file(cmake_file: Path, new_paths: List[str], project_root: Path, path_to_headers: dict = None) -> bool:
    """Add new include paths to CMakeLists.txt with header file comments."""
    if not new_paths:
        return False
    
    if path_to_headers is None:
        path_to_headers = {}
    
    try:
        with open(cmake_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find target_include_directories block
        target_pattern = re.compile(r'(target_include_directories\s*\([^)]+\))', re.DOTALL)
        matches = list(target_pattern.finditer(content))
        
        if matches:
            last_match = matches[-1]
            # Find the closing parenthesis
            closing_pos = last_match.end() - 1  # Position before the closing )
            
            # Build new include entries with calculated relative paths
            cmake_dir = cmake_file.parent
            new_includes = ''
            
            for path in new_paths:
                # Convert path string to Path object relative to project root
                target_path = project_root / path
                
                # Calculate relative path from CMAKE_CURRENT_SOURCE_DIR to target
                try:
                    rel_path = os.path.relpath(target_path, cmake_dir)
                    # Normalize path separators to forward slashes for CMake
                    rel_path = rel_path.replace('\\', '/')
                    
                    # Build comment with header list
                    comment = "# Auto-generated"
                    if path in path_to_headers and path_to_headers[path]:
                        headers_list = ", ".join(sorted(path_to_headers[path]))
                        comment += f" for {headers_list}"
                    
                    new_includes += f'\n    PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}/{rel_path}"  {comment}'
                except ValueError:
                    # If paths are on different drives (Windows), use absolute path
                    abs_path = target_path.as_posix()
                    
                    # Build comment with header list
                    comment = "# Auto-generated"
                    if path in path_to_headers and path_to_headers[path]:
                        headers_list = ", ".join(sorted(path_to_headers[path]))
                        comment += f" for {headers_list}"
                    
                    new_includes += f'\n    PRIVATE "{abs_path}"  {comment}'
                    print_warn(f"Using absolute path for {path} (different drive)")
            
            # Insert before the closing parenthesis
            updated_content = content[:closing_pos] + new_includes + '\n' + content[closing_pos:]
            
            with open(cmake_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(updated_content)
            
            return True
        else:
            print_warn("Could not find target_include_directories block")
            print_info("Please add these paths manually to target_include_directories:")
            cmake_dir = cmake_file.parent
            for path in new_paths:
                target_path = project_root / path
                try:
                    rel_path = os.path.relpath(target_path, cmake_dir).replace('\\', '/')
                    print(f'    PRIVATE "${{CMAKE_CURRENT_SOURCE_DIR}}/{rel_path}"')
                except ValueError:
                    abs_path = target_path.as_posix()
                    print(f'    PRIVATE "{abs_path}"')
            return False
    
    except Exception as e:
        print_error(f"Failed to update CMakeLists.txt: {e}")
        return False

def remove_unfound_includes(source_files: List[Path], unfound_headers: Set[str], project_root: Path):
    """Remove include statements for unfound headers."""
    print_warn("\nRemoving unfound includes from source files...")
    
    for header in unfound_headers:
        header_escaped = re.escape(header)
        include_pattern = re.compile(rf'^\s*#\s*include\s+[<"]{header_escaped}[>"]\s*$', re.MULTILINE)
        
        for file_path in source_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if include_pattern.search(content):
                    updated_content = include_pattern.sub('', content)
                    
                    with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                        f.write(updated_content)
                    
                    rel_path = file_path.relative_to(project_root)
                    print_success(f"Removed include from: {rel_path}")
            except Exception as e:
                print_error(f"Failed to update {file_path}: {e}")

def main():
    parser = argparse.ArgumentParser(
        description='Update GTF CMakeLists.txt with missing include paths',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python update_gtest_includes.py vsgen1c1.c
  python update_gtest_includes.py usmngsm1c1.c --remove-unfound
        """
    )
    parser.add_argument('source_file', help='Source file name (e.g., vsgen1c1.c)')
    parser.add_argument('--project-root', type=Path, default=Path.cwd(),
                       help='Project root directory (default: current directory)')
    parser.add_argument('--remove-unfound', action='store_true',
                       help='Remove includes for headers that cannot be found')
    parser.add_argument('--variant', default='pf',
                       help='Build variant name (default: pf)')
    
    args = parser.parse_args()
    
    print_info("Starting GTF Include Path Update")
    print_info(f"Source File: {args.source_file}")
    print_info(f"Project Root: {args.project_root}")
    print()
    
    # Step 1: Find source file
    source_file_path = find_source_file(args.source_file, args.project_root)
    if not source_file_path:
        print_error(f"Source file not found: {args.source_file}")
        print_info(f"Searched in: {args.project_root}")
        return 1
    
    print_success(f"Found source file: {source_file_path}")
    
    # Step 2: Find module root and gtest path
    result = find_module_root(source_file_path)
    if not result:
        print_error(f"Could not find test/gtest folder for: {args.source_file}")
        print_info(f"Searched up from: {source_file_path.parent}")
        print_info("\nMake sure the module has a test/gtest folder structure.")
        return 1
    
    module_path, gtest_path = result
    print_success(f"Found module root: {module_path}")
    print_success(f"Found test harness: {gtest_path}")
    print()
    
    # Step 3: Find CMakeLists.txt
    # Try new pattern first (created by gtf_framework_gen.sh): prj/{variant}/CMakeLists.txt
    cmake_files = list((gtest_path / "prj").glob(f"{args.variant}/CMakeLists.txt"))
    
    # Fall back to old pattern if not found: prj/unittest_*_{variant}/CMakeLists.txt
    if not cmake_files:
        cmake_files = list((gtest_path / "prj").glob(f"unittest_*_{args.variant}/CMakeLists.txt"))
    
    if not cmake_files:
        print_error(f"No CMakeLists.txt found for variant '{args.variant}'")
        print_info(f"Searched in: {gtest_path / 'prj'}")
        print_info(f"  Pattern 1 (new): {args.variant}/CMakeLists.txt")
        print_info(f"  Pattern 2 (old): unittest_*_{args.variant}/CMakeLists.txt")
        return 1
    
    cmake_file = cmake_files[0]
    print_info(f"Found CMakeLists.txt: {cmake_file}")
    print()
    
    # Step 4: Extract includes from source file
    print_info("Extracting includes from source file...")
    source_includes = extract_includes(source_file_path)
    print_success(f"Found {len(source_includes)} includes in source file")
    print()
    
    # Step 5: Collect test source files
    print_info("Collecting test source files...")
    source_files = collect_source_files(gtest_path)
    
    if not source_files:
        print_warn("No test source files found to process")
    else:
        print()
    
    # Step 6: Extract includes from test files
    print_info("Extracting include statements from test/mock/stub files...")
    all_includes = set()
    include_usage = {}  # Track which files use which headers
    
    # Add source file includes
    all_includes.update(source_includes)
    for inc in source_includes:
        include_usage[inc] = [source_file_path]
    
    # Add test/mock/stub includes
    for file_path in source_files:
        includes = extract_includes(file_path)
        all_includes.update(includes)
        for inc in includes:
            if inc not in include_usage:
                include_usage[inc] = []
            include_usage[inc].append(file_path)
    
    print_success(f"Found {len(all_includes)} unique header includes")
    print_info(f"  From source file: {len(source_includes)}")
    print_info(f"  From test files: {len(all_includes - source_includes)}")
    print()
    
    # Step 7: Get current includes
    current_includes = get_current_includes(cmake_file)
    print_info(f"Current CMakeLists.txt has {len(current_includes)} include directories")
    # Debug: show first few includes
    if current_includes and False:  # Set to True for debugging
        print_info("Sample existing includes:")
        for inc in list(current_includes)[:5]:
            print(f"    {inc}")
    print()
    
    # Step 8: Search for module-specific header directories
    print_info("Searching for header files in module directories...")
    module_name = extract_module_name(args.source_file)
    module_header_dirs = find_module_header_dirs(module_name, args.project_root)
    
    if module_header_dirs:
        print_success(f"Found {len(module_header_dirs)} directories with headers in module '{module_name}'")
        for hdr_dir in module_header_dirs:
            try:
                rel_path = hdr_dir.relative_to(args.project_root).as_posix()
                print_info(f"  - {rel_path}")
            except ValueError:
                print_info(f"  - {hdr_dir.as_posix()}")
    else:
        print_info(f"No additional header directories found in module '{module_name}'")
    print()
    
    # Step 9: Add module header directories to new_include_paths if not already present
    module_header_paths = set()
    for hdr_dir in module_header_dirs:
        try:
            rel_path = hdr_dir.relative_to(args.project_root).as_posix()
        except ValueError:
            rel_path = hdr_dir.as_posix()
        
        # Check if this path is already in CMakeLists.txt
        cmake_dir = cmake_file.parent
        target_path = args.project_root / rel_path
        
        try:
            calculated_rel_path = os.path.relpath(target_path, cmake_dir).replace('\\', '/')
        except ValueError:
            calculated_rel_path = target_path.as_posix()
        
        already_exists = False
        for existing in current_includes:
            if '${CMAKE_CURRENT_SOURCE_DIR}' in existing:
                existing_rel = existing.replace('${CMAKE_CURRENT_SOURCE_DIR}/', '').replace('${CMAKE_CURRENT_SOURCE_DIR}', '')
            elif '${MUT_LOCATION}' in existing:
                continue
            else:
                existing_rel = existing
            
            norm_existing = existing_rel.strip('/').strip('\\').replace('\\', '/')
            norm_calculated = calculated_rel_path.strip('/').strip('\\').replace('\\', '/')
            
            if norm_existing == norm_calculated:
                already_exists = True
                break
        
        if not already_exists:
            module_header_paths.add(rel_path)
    
    print_info(f"Module header paths to add: {len(module_header_paths)}")
    print()
    
    # Step 10: Search for headers and determine new paths
    print_info("Searching for header file paths in project...")
    found_headers = {}
    not_found_headers = []
    new_include_paths = []
    processed_paths = set()
    path_to_headers = {}  # Map include paths to the headers they provide
    
    for header in sorted(all_includes):
        print(f"  Searching for: {header}", end=' ')
        
        header_dir = find_header_path(header, args.project_root, module_path)
        
        if header_dir:
            # Convert to relative path from project root
            try:
                rel_path = header_dir.relative_to(args.project_root).as_posix()
            except ValueError:
                rel_path = header_dir.as_posix()
            
            print(f"{Colors.GREEN}-> Found: {rel_path}{Colors.RESET}")
            
            # Check if already in CMakeLists.txt
            # Calculate what the relative path would be from CMAKE_CURRENT_SOURCE_DIR
            cmake_dir = cmake_file.parent
            target_path = args.project_root / rel_path
            
            try:
                calculated_rel_path = os.path.relpath(target_path, cmake_dir).replace('\\', '/')
            except ValueError:
                calculated_rel_path = target_path.as_posix()
            
            already_exists = False
            for existing in current_includes:
                # Extract path from ${CMAKE_CURRENT_SOURCE_DIR}/path or ${MUT_LOCATION}/path
                if '${CMAKE_CURRENT_SOURCE_DIR}' in existing:
                    existing_rel = existing.replace('${CMAKE_CURRENT_SOURCE_DIR}/', '').replace('${CMAKE_CURRENT_SOURCE_DIR}', '')
                elif '${MUT_LOCATION}' in existing:
                    # Skip MUT_LOCATION variable paths
                    continue
                else:
                    existing_rel = existing
                
                # Normalize both paths for comparison (remove leading/trailing slashes, normalize separators)
                norm_existing = existing_rel.strip('/').strip('\\').replace('\\', '/')
                norm_calculated = calculated_rel_path.strip('/').strip('\\').replace('\\', '/')
                
                if norm_existing == norm_calculated:
                    already_exists = True
                    break
            
            if not already_exists and rel_path not in processed_paths:
                new_include_paths.append(rel_path)
                processed_paths.add(rel_path)
                print_success(f"  -> Will add to CMakeLists.txt")
            
            # Track which headers need this path
            if rel_path not in path_to_headers:
                path_to_headers[rel_path] = []
            if header not in path_to_headers[rel_path]:
                path_to_headers[rel_path].append(header)
            
            if already_exists:
                print_info(f"  -> Already in CMakeLists.txt")
            
            found_headers[header] = header_dir
        else:
            print(f"{Colors.RED}-> NOT FOUND{Colors.RESET}")
            not_found_headers.append(header)
    
    print()
    
    # Add module header paths to the final list
    for mod_hdr_path in module_header_paths:
        if mod_hdr_path not in processed_paths:
            new_include_paths.append(mod_hdr_path)
            processed_paths.add(mod_hdr_path)
            if mod_hdr_path not in path_to_headers:
                path_to_headers[mod_hdr_path] = []
            print_success(f"  + [Module] {mod_hdr_path}")
    
    print()
    print_info("Search Results:")
    print_info(f"  Found: {len(found_headers)} headers")
    print_info(f"  Not Found: {len(not_found_headers)} headers")
    print_info(f"  Module header paths: {len(module_header_paths)}")
    print_info(f"  New Paths to Add: {len(new_include_paths)}")
    print()
    
    # Step 11: Update CMakeLists.txt
    if new_include_paths:
        print_info("Updating CMakeLists.txt with new include paths...")
        if update_cmake_file(cmake_file, new_include_paths, args.project_root, path_to_headers):
            print_success(f"Added {len(new_include_paths)} new include paths to CMakeLists.txt")
            for path in new_include_paths:
                headers = ", ".join(sorted(path_to_headers.get(path, [])))
                print(f"{Colors.GREEN}  + {path} (for: {headers}){Colors.RESET}")
        print()
    else:
        print_success("No new include paths needed - CMakeLists.txt is up to date")
        print()
    
    # Step 12: Handle not found headers
    if not_found_headers:
        print_warn("The following headers could not be found in the project:")
        for header in not_found_headers:
            print(f"{Colors.RED}  [NOT FOUND] {header}{Colors.RESET}")
            print(f"{Colors.CYAN}    Used in:{Colors.RESET}")
            for file_path in include_usage[header]:
                rel_path = file_path.relative_to(args.project_root)
                print(f"      - {rel_path}")
        
        if args.remove_unfound:
            remove_unfound_includes(source_files, set(not_found_headers), args.project_root)
        else:
            print()
            print_info("To automatically remove these includes, run with --remove-unfound flag")
        print()
    
    # Summary
    print_success("GTF Include Path Update Complete!")
    print()
    print_info("Summary:")
    print_info(f"  Total headers processed: {len(all_includes)}")
    print_info(f"  Headers found: {len(found_headers)}")
    print_info(f"  Headers not found: {len(not_found_headers)}")
    print_info(f"  New paths added: {len(new_include_paths)}")
    print()
    
    if new_include_paths or not_found_headers:
        print_info("Next Steps:")
        if new_include_paths:
            print_info("  1. Review the updated CMakeLists.txt")
            print_info("  2. Rebuild the test project")
        if not_found_headers:
            print_info("  3. Fix or remove missing header references")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
