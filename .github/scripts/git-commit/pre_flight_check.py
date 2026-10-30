#!/usr/bin/env python3
"""
Pre-Flight Check for GitCommit Agent

Checks the current PC and OS user ID against restricted lists. If either is
restricted, the user must provide a nonempty attribution UID that is not itself
listed as restricted. The supplied UID is not checked against OS accounts and
is never used to authenticate or change the active user.

Exit codes:
    0: No restriction matched, or an acceptable attribution UID was provided
    1: A required attribution UID was empty or also restricted
  2: Configuration file not found or parsing error
"""

import json
import os
import sys
import platform
from pathlib import Path


def get_current_pc_name():
    """Get the current PC/machine name."""
    return platform.node().upper()


def get_current_user_id():
    """Get the current OS user ID."""
    return os.getenv('USERNAME', os.getenv('USER', 'UNKNOWN')).lower()


def get_user_full_name(user_id):
    """Get full name for a user ID (cross-platform)."""
    system = platform.system()

    if system == 'Windows':
        try:
            import subprocess
            # Try PowerShell first (more reliable on modern Windows)
            ps_cmd = f"(Get-LocalUser -Name '{user_id}' -ErrorAction SilentlyContinue | Select-Object FullName).FullName"
            result = subprocess.run(
                ['powershell', '-Command', ps_cmd],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                full_name = result.stdout.strip()
                if full_name:
                    return full_name
        except Exception:
            pass  # Fall back to wmic or None

        # Fallback to wmic if PowerShell fails
        try:
            import subprocess
            result = subprocess.run(
                ['wmic', 'useraccount', f"where name='{user_id}'", 'get', 'fullname'],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Parse wmic output (format: "FullName\n<name>\n")
            lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            if len(lines) >= 2:
                return lines[1]
        except Exception:
            pass  # Fall back to returning None

    elif system in ['Linux', 'Darwin']:
        try:
            import subprocess
            result = subprocess.run(
                ['getent', 'passwd', user_id],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Format: uid:x:1000:1000:Full Name:/home/uid:/bin/bash
                parts = result.stdout.strip().split(':')
                if len(parts) >= 5:
                    return parts[4]  # Return full name field
        except Exception:
            pass  # Fall back to returning None

    return None


def load_config(config_path):
    """Load the remote_pc_exclusion.json configuration file."""
    if not os.path.exists(config_path):
        print(f"[ERROR] Configuration file not found: {config_path}")
        return None

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON config: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        return None


def run_pre_flight_check(config_path=None, override_user=None):
    """
        Check current PC/user restrictions and collect a non-authenticating attribution UID.

    Args:
      config_path: Path to remote_pc_exclusion.json (auto-detect if None)
            override_user: Attribution UID supplied non-interactively when restricted

    Returns:
      0: Check passed, proceed with commit
            1: Required attribution UID was missing or listed as restricted
      2: Configuration error
    """

    # Default config path
    if config_path is None:
        # Try to find config relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, 'remote_pc_exclusion.json')

    # Load configuration
    config = load_config(config_path)
    if config is None:
        return 2

    # Get current system info
    current_pc = get_current_pc_name()
    current_user = get_current_user_id()
    user_full_name = get_user_full_name(current_user)

    # Check if user full name is in the config's user_name_map
    user_name_map = config.get('user_name_map', {})
    if not user_full_name and current_user in user_name_map:
        user_full_name = user_name_map[current_user]

    print(f"[INFO] Current PC Name: {current_pc}")
    print(f"[INFO] Current User ID: {current_user}")
    if user_full_name:
        print(f"[INFO] Current User Name: {user_full_name}")

    # Extract restricted PCs and users from new format
    restricted_pcs = [pc.upper() for pc in config.get('restricted_pcs', [])]
    restricted_users = [user.lower() for user in config.get('restricted_users', [])]

    # Check if current PC or user is restricted (case-insensitive)
    pc_restricted = current_pc.upper() in restricted_pcs
    user_restricted = current_user.lower() in restricted_users

    if user_restricted or pc_restricted:
        print("\n[WARNING] Current PC or OS user ID is restricted.")
        if pc_restricted:
            print(f"  - PC name '{current_pc}' is in the restricted list")
        if user_restricted:
            print(f"  - User ID '{current_user}' is in the restricted list")
        print("\nThe attribution UID is recorded only; it is not used to log in or authenticate.")

        if override_user is not None:
            attribution_user = override_user.strip()
            print(f"\n[INFO] Using supplied attribution UID: {attribution_user}")
        else:
            attribution_user = input("\nEnter your UID for commit attribution (or press Enter to cancel): ").strip()

        if not attribution_user:
            print("\n[ERROR] Commit cancelled: an attribution UID is required when restricted.")
            return 1

        if attribution_user.lower() in restricted_users:
            print(f"\n[ERROR] Commit blocked: Attribution UID '{attribution_user}' is also in the restricted list.")
            return 1

        print(f"\n[OK] Restriction check passed; recording attribution UID: {attribution_user}")
        print("[INFO] The supplied UID was not verified against OS accounts and will not be used to authenticate.")
        print(f"[USER_INFO] id={attribution_user} name=UNKNOWN")
        return 0

    # No restrictions matched - proceed normally
    print("\n[OK] Pre-Flight Check passed. Safe to commit.")
    print(f"[INFO] Proceeding with commit as user: {current_user}")
    if user_full_name:
        print(f"[INFO] User name: {user_full_name}")
    # Output user info in parseable format for downstream tools
    print(f"[USER_INFO] id={current_user} name={user_full_name if user_full_name else 'UNKNOWN'}")
    return 0


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Pre-Flight Check for GitCommit Agent'
    )
    parser.add_argument(
        'config_path',
        nargs='?',
        default=None,
        help='Path to remote_pc_exclusion.json (auto-detect if not provided)'
    )
    parser.add_argument(
        '--override-user',
        type=str,
        default=None,
        help='Attribution UID to record when the current PC or OS user is restricted; not verified or authenticated'
    )

    args = parser.parse_args()

    exit_code = run_pre_flight_check(args.config_path, args.override_user)
    sys.exit(exit_code)
