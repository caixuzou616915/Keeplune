#!/usr/bin/env python3
r"""
Compile Command Processor for C Source Files
=============================================

This script processes compile_commands.json to extract and modify compilation commands
for C source files. It can generate preprocessor commands to expand all includes into
a single file, and compilation commands to build the preprocessed output.

Features:
---------
1. Extract compilation commands from compile_commands.json
2. Generate preprocessor commands (-E flag) to create expanded source files
3. Generate compilation commands for preprocessed files
4. Execute commands automatically or save them to batch files

Author: Zhao Jianbo
Supported by: UX SW AI Community

Command-Line Arguments:
-----------------------
<source_filename>       The C source file to process (e.g., module.c or module)
                        .c extension is optional and will be added if missing

Options:
--------
--json <path>          Path to compile_commands.json file
                       Default: build/compile_commands.json

--output <path>        Save modified compile_commands.json to specified file
                       (Optional - for debugging purposes)

--execute              Execute the preprocessor command from gen.bat
                       Creates <filename>_new.tmp in the same directory as source file

--compile              Generate compilation command for the preprocessed file
                       Creates compile.bat with command to build <filename>_new.tmp.o

--clean                Clean the preprocessed file by removing #line directives and empty lines
                       Creates <filename>_clean.tmp in the same directory as source file
                       Must be used after --execute or ensure <filename>_new.tmp exists

--all                  Execute both preprocessing and compilation automatically
                       Equivalent to: --execute --compile (and auto-runs both)

Usage Examples:
---------------

1. Basic Usage - Generate preprocessor command only:
   $ python gen_standard_c.py usmngsm1c1.c
   
   Output:
   - gen.bat: Contains preprocessor command with -E flag
   - Run manually: .\gen.bat
   - Creates: usmngsm1c1_new.tmp (in source file directory)

2. Execute preprocessing automatically:
   $ python gen_standard_c.py usmngsm1c1.c --execute
   
   Output:
   - Runs gen.bat automatically
   - Creates: pkg/em_s3p_hud/usermng/usmngsm/core/usmngsm1c1_new.tmp

3. Generate both preprocessor and compilation commands:
   $ python gen_standard_c.py usmngsm1c1.c --compile
   
   Output:
   - gen.bat: Preprocessor command
   - compile.bat: Compilation command for usmngsm1c1_new.tmp.o
   - Run manually: .\gen.bat then .\compile.bat

4. Full workflow - Preprocess and compile automatically:
   $ python gen_standard_c.py usmngsm1c1.c --all
   
   Output:
   - Executes gen.bat (creates usmngsm1c1_new.tmp)
   - Executes compile.bat (creates usmngsm1c1_new.tmp.o)

5. Clean preprocessed file (remove #line directives and empty lines):
   $ python gen_standard_c.py usmngsm1c1.c --execute --clean
   
   Output:
   - Executes gen.bat (creates usmngsm1c1_new.tmp)
   - Cleans file (creates usmngsm1c1_clean.tmp)
   - Removes all #line directives
   - Removes all empty lines

6. Custom compile_commands.json path:
   $ python gen_standard_c.py module.c --json custom/path/compile_commands.json

7. Save modified compile_commands.json:
   $ python gen_standard_c.py module.c --output modified_commands.json

Workflow Details:
-----------------
Step 1: Preprocessing (gen.bat)
   - Reads original compilation command from compile_commands.json
   - Replaces: -o <file>.o -c  →  -E
   - Adds output redirection: > <source_directory>/<filename>_new.tmp
   - Expands all #include directives and macros into single file

Step 2: Cleaning (Optional, --clean flag)
   - Reads the preprocessed *_new.tmp file line by line
   - Removes all lines starting with #line directives
   - Removes all empty lines (whitespace only)
   - Creates <filename>_clean.tmp with only actual source code
   - Useful for code analysis and review without preprocessor noise

Step 3: Compilation (compile.bat)
   - Uses original compilation flags from compile_commands.json
   - Replaces source file: <filename>.c  →  <filename>_new.tmp
   - Generates object file: <filename>_new.tmp.o
   - Uses same compiler settings as original build

Generated Files:
----------------
gen.bat             - Preprocessor command (Windows batch file)
compile.bat         - Compilation command (Windows batch file)
<filename>_new.tmp    - Preprocessed source file (in source directory)
<filename>_clean.tmp  - Cleaned preprocessed file (no #line or empty lines)
<filename>_new.tmp.o  - Compiled object file (if compilation executed)

Notes:
------
- The script searches for the source file in compile_commands.json by filename
- Preprocessed files (*_new.tmp) are created in the same directory as the source
- Both relative and absolute paths are supported for source files
- Batch files are created in the current working directory

Example Output Structure:
--------------------------
Before:
  pkg/em_s3p_hud/usermng/usmngsm/core/usmngsm1c1.c

After --execute:
  pkg/em_s3p_hud/usermng/usmngsm/core/usmngsm1c1.c
  pkg/em_s3p_hud/usermng/usmngsm/core/usmngsm1c1_new.tmp  (preprocessed)

After --execute --clean:
  pkg/em_s3p_hud/usermng/usmngsm/core/usmngsm1c1.c
  pkg/em_s3p_hud/usermng/usmngsm/core/usmngsm1c1_new.tmp  (preprocessed)
  pkg/em_s3p_hud/usermng/usmngsm/core/usmngsm1c1_clean.tmp  (cleaned)

After --all:
  pkg/em_s3p_hud/usermng/usmngsm/core/usmngsm1c1.c
  pkg/em_s3p_hud/usermng/usmngsm/core/usmngsm1c1_new.tmp  (preprocessed)
  pkg/em_s3p_hud/usermng/usmngsm/core/usmngsm1c1_new.tmp.o  (object file)

"""

import json
import sys
import re
import os
import subprocess


def process_compile_command(source_filename, json_file_path="build/compile_commands.json"):
    """
    Read compile_commands.json, find the source file, and modify the command.
    
    Args:
        source_filename (str): The .c source file name to search for
        json_file_path (str): Path to the compile_commands.json file
    
    Returns:
        tuple: (success: bool, modified_commands: list or None, modified_command: str or None, 
                original_command: str or None, preprocessed_file_path: str or None)
    """
    
    if not re.match(r'^[\w./\-]+$', source_filename):
        raise ValueError(f"Unsafe filename: {source_filename}")

    # Check if JSON file exists
    if not os.path.exists(json_file_path):
        print(f"Error: compile_commands.json not found at {json_file_path}")
        print("Hint: use --json to specify the correct path.")
        sys.exit(1)
    
    # Ensure source filename is normalized
    if not source_filename.endswith('.c'):
        source_filename += '.c'
    
    try:
        # Read the JSON file
        with open(json_file_path, 'r', encoding='utf-8') as f:
            compile_commands = json.load(f)
        
        # Search for the source file
        found = False
        for entry in compile_commands:
            file_path = entry.get('file', '')
            
            # Normalize path separators for comparison (convert backslashes to forward slashes)
            normalized_file_path = file_path.replace('\\', '/')
            normalized_source = source_filename.replace('\\', '/')
            
            # Check if the source filename matches (handle both full path and just filename)
            # Also try matching just the filename part
            source_basename = os.path.basename(source_filename)
            if (normalized_source in normalized_file_path or 
                normalized_file_path.endswith(normalized_source) or
                normalized_file_path.endswith(source_basename)):
                found = True
                command = entry.get('command', '')
                
                print(f"Found: {file_path}")
                print(f"\nOriginal command:")
                print(command)
                
                # Replace "-o *.o -c" with "-E"
                # Pattern: -o <anything>.o -c
                modified_command = re.sub(r'-o\s+\S+\.o\s+-c', '-E', command)
                
                # Add output redirection to filename_new.tmp in the same folder as source
                source_dir = os.path.dirname(file_path)
                source_base = os.path.basename(file_path)
                base_name = source_base.rsplit('.', 1)[0] if '.' in source_base else source_base
                output_filename = os.path.join(source_dir, f"{base_name}_new.tmp")
                modified_command = f"{modified_command} > {output_filename}"
                
                print(f"\nModified command:")
                print(modified_command)
                
                # Save command to gen.bat file
                batch_file = "gen.bat"
                with open(batch_file, 'w', encoding='utf-8') as f:
                    f.write(f"@echo off\n")
                    f.write(f"{modified_command}\n")
                print(f"\nCommand saved to: {batch_file}")
                
                # Update the entry
                entry['command'] = modified_command
                
                # Return the modified commands, batch filename, original command, and preprocessed file path
                return True, compile_commands, batch_file, command, output_filename
        
        if not found:
            print(f"Error: Source file '{source_filename}' not found in {json_file_path}")
            return False, None, None, None, None
    
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON file: {e}")
        return False, None, None, None, None
    except Exception as e:
        print(f"Error: {e}")
        return False, None, None, None, None


def compile_preprocessed_file(original_command, preprocessed_file_path):
    """
    Compile the preprocessed file using the original compilation command.
    
    Args:
        original_command (str): The original compilation command
        preprocessed_file_path (str): Path to the preprocessed *_new.tmp file
    
    Returns:
        tuple: (success: bool, batch_file: str or None)
    """
    try:
        # Extract the original source file path from the command
        # The source file is typically the last argument before any output redirection
        original_file_match = re.search(r'(\S+\.c)(?:\s|$)', original_command)
        if not original_file_match:
            print("Error: Could not find source file in original command")
            return False, None
        
        original_file = original_file_match.group(1)
        
        # Create compilation command for the preprocessed file
        # Start with the original command (before -E modification)
        compile_command = original_command.replace(original_file, preprocessed_file_path)
        
        # Generate output object file name based on preprocessed file
        source_dir = os.path.dirname(preprocessed_file_path)
        source_base = os.path.basename(preprocessed_file_path)
        base_name = source_base.rsplit('.', 1)[0] if '.' in source_base else source_base
        output_obj = os.path.join(source_dir, f"{base_name}.o")
        
        # Ensure we have -o <output>.o -c in the command
        if '-o' not in compile_command:
            compile_command = f"{compile_command} -o {output_obj} -c"
        
        print(f"\nCompilation command for preprocessed file:")
        print(compile_command)
        
        # Save command to compile.bat file
        batch_file = "compile.bat"
        with open(batch_file, 'w', encoding='utf-8') as f:
            f.write(f"@echo off\n")
            f.write(f"{compile_command}\n")
        print(f"\nCompilation command saved to: {batch_file}")
        
        return True, batch_file
        
    except Exception as e:
        print(f"Error creating compilation command: {e}")
        return False, None


def clean_preprocessed_file(preprocessed_file_path):
    """
    Clean up the preprocessed file by removing #line directives and empty lines.
    
    Args:
        preprocessed_file_path (str): Path to the preprocessed *_new.tmp file
    
    Returns:
        tuple: (success: bool, cleaned_file_path: str or None)
    """
    try:
        if not os.path.exists(preprocessed_file_path):
            print(f"Error: Preprocessed file not found: {preprocessed_file_path}")
            return False, None
        
        # Generate cleaned file path
        source_dir = os.path.dirname(preprocessed_file_path)
        source_base = os.path.basename(preprocessed_file_path)
        base_name = source_base.rsplit('.', 1)[0] if '.' in source_base else source_base
        
        # Remove "_new" suffix if present and add "_clean"
        if base_name.endswith('_new'):
            base_name = base_name[:-4]  # Remove "_new"
        cleaned_file_path = os.path.join(source_dir, f"{base_name}_clean.tmp")
        
        print(f"\nCleaning preprocessed file...")
        print(f"Input:  {preprocessed_file_path}")
        print(f"Output: {cleaned_file_path}")
        
        # Read and clean the file
        lines_read = 0
        lines_written = 0
        lines_skipped_line_directive = 0
        lines_skipped_empty = 0
        
        with open(preprocessed_file_path, 'r', encoding='utf-8', errors='ignore') as infile:
            with open(cleaned_file_path, 'w', encoding='utf-8') as outfile:
                for line in infile:
                    lines_read += 1
                    
                    # Skip lines starting with #line
                    if line.lstrip().startswith('#line'):
                        lines_skipped_line_directive += 1
                        continue
                    
                    # Skip empty lines (lines with only whitespace)
                    if not line.strip():
                        lines_skipped_empty += 1
                        continue
                    
                    # Write the line to cleaned file
                    outfile.write(line)
                    lines_written += 1
        
        print(f"\nCleaning completed:")
        print(f"  Lines read:               {lines_read:,}")
        print(f"  Lines written:            {lines_written:,}")
        print(f"  Lines skipped (#line):    {lines_skipped_line_directive:,}")
        print(f"  Lines skipped (empty):    {lines_skipped_empty:,}")
        print(f"\nCleaned file saved to: {cleaned_file_path}")
        
        return True, cleaned_file_path
        
    except Exception as e:
        print(f"Error cleaning preprocessed file: {e}")
        return False, None


def execute_command(batch_file, working_dir=None):
    """
    Execute a batch file using subprocess.
    
    Args:
        batch_file (str): The batch file to execute
        working_dir (str): Working directory for command execution (default: current directory)
    
    Returns:
        bool: True if successful, False otherwise
    """
    print(f"\n{'='*80}")
    print(f"Executing: {batch_file}")
    print(f"{'='*80}\n")
    
    try:
        if working_dir is None:
            working_dir = '.'
        
        # Convert batch_file to absolute path to avoid path resolution issues
        # This ensures the batch file path is correct regardless of working directory
        if not os.path.isabs(batch_file):
            batch_file = os.path.abspath(batch_file)
        
        # Detect if we're running in bash/WSL environment
        # Check for SHELL environment variable or if 'bash' is in the SHELL path
        shell_env = os.environ.get('SHELL', '')
        is_bash = 'bash' in shell_env.lower() or 'sh' in shell_env.lower()
        
        # Execute batch file - use cmd.exe for bash environments
        if is_bash or os.name != 'nt':
            # Running in bash/WSL/Linux - need to use cmd.exe to run .bat files
            # Use absolute path with cmd.exe
            cmd = ['cmd.exe', '/c', batch_file]
            result = subprocess.run(cmd, cwd=working_dir)
        else:
            # Running in native Windows (PowerShell/cmd)
            result = subprocess.run(['cmd.exe', '/c', batch_file], shell=False, cwd=working_dir)
        
        if result.returncode == 0:
            print(f"\n{'='*80}")
            print("Command executed successfully!")
            print(f"Return code: {result.returncode}")
            print(f"{'='*80}")
            return True
        else:
            print(f"\n{'='*80}")
            print(f"Command failed with exit code: {result.returncode}")
            print(f"{'='*80}")
            return False
    except Exception as e:
        print(f"\nError executing command: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python gen_standard_c.py <source_filename> [options]")
        print("Example: python gen_standard_c.py module.c")
        print("\nOptions:")
        print("  --json <path>     Specify custom path to compile_commands.json (default: build/compile_commands.json)")
        print("  --build-dir <path> Specify build directory (appends /compile_commands.json) (e.g., build/tviib_e4m_aravalli_s3p_db.Debug)")
        print("  --output <path>   Save modified JSON to a file")
        print("  --execute         Execute the preprocessor command")
        print("  --compile         Compile the preprocessed file")
        print("  --clean           Clean the preprocessed file (remove #line directives and empty lines)")
        print("  --all             Execute preprocessor and compile the result")
        sys.exit(1)
    
    source_filename = sys.argv[1]
    json_file_path = "build/compile_commands.json"
    output_file = None
    execute = False
    compile_preprocessed = False
    clean_file = False
    do_all = False
    
    # Parse additional arguments
    for i in range(2, len(sys.argv)):
        if sys.argv[i] == "--json" and i + 1 < len(sys.argv):
            json_file_path = sys.argv[i + 1]
        elif sys.argv[i] == "--build-dir" and i + 1 < len(sys.argv):
            build_dir = sys.argv[i + 1]
            json_file_path = os.path.join(build_dir, "compile_commands.json")
        elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
        elif sys.argv[i] == "--execute":
            execute = True
        elif sys.argv[i] == "--compile":
            compile_preprocessed = True
        elif sys.argv[i] == "--clean":
            clean_file = True
        elif sys.argv[i] == "--all":
            do_all = True
            execute = True
            compile_preprocessed = True
    
    # Process the command
    success, result, modified_cmd, original_cmd, preprocessed_path = process_compile_command(source_filename, json_file_path)
    
    if success and result:
        # Execute the preprocessor command if requested
        if execute:
            execute_command(modified_cmd, working_dir=os.path.dirname(json_file_path) or '.')
        
        # Clean the preprocessed file if requested
        if clean_file and preprocessed_path:
            clean_success, cleaned_path = clean_preprocessed_file(preprocessed_path)
            if not clean_success:
                print("\nWarning: Failed to clean preprocessed file")
        
        # Compile the preprocessed file if requested
        if compile_preprocessed and original_cmd and preprocessed_path:
            compile_success, compile_batch = compile_preprocessed_file(original_cmd, preprocessed_path)
            if compile_success and compile_batch:
                if do_all or execute:  # Only auto-execute if --all or --execute was specified
                    execute_command(compile_batch, working_dir='.')
        
        # Save to file if requested
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
            print(f"\nModified JSON saved to: {output_file}")
    elif not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
