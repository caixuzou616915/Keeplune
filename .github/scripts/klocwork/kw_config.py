#!/usr/bin/env python3
"""
Klocwork Toolkit shared configuration loader
=============================================
Every script in this toolkit (kw_export.py, kw_update.py) optionally reads
non-secret defaults from `klocwork_config.json`, kept in this same
directory, so the server URL/username don't have to be repeated on every
command line, and so the ai_output/ artifacts folder is always anchored to
the repository root regardless of the current working directory the
script happens to be invoked from.

SECURITY: never put an ltoken/password value in this file. It is a plain
JSON file meant to be committed to the repo - authentication must keep
using ~/.klocwork/ltoken (or $KLOCWORK_LTOKEN), or the --ltoken/--user CLI
flags for a one-off override; never a secret stored here.

Recognised keys (all optional - omit or leave ""/[] to fall back to the
script's built-in default):
  "url"           - default --url value, e.g.
                    "https://server:8096/My_Project"
  "user"          - default --user value (only meaningful together with a
                    manually supplied --ltoken)
  "ai_output_dir" - override for where kw_export.py writes its default
                    output (absolute path, or relative to the repo root).
                    Default: "<repo_root>/ai_output/klocwork"
  "severity"      - default --severity value for kw_export.py, e.g. "1-3"
                    (used only when --severity is not passed on the CLI)
  "ruleset"       - default --ruleset value(s) for kw_export.py: either a
                    JSON list (e.g. ["MISRA C 2012", "CERT C Rules"]) or a
                    single comma-separated string. Maps to the Klocwork
                    `taxonomy:` query facet. Used only when --ruleset is
                    not passed on the CLI.
  "max_warnings_per_file" - default --max-per-file value for kw_export.py:
                    when an export returns more than this many warnings, the
                    output is automatically split into multiple numbered
                    files (each holding at most this many warnings) instead
                    of one large file. Used only when --max-per-file is not
                    passed on the CLI. Leave 0/""/absent to fall back to the
                    script's built-in default (1000).
"""
import json
import os

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILENAME = "klocwork_config.json"
CONFIG_PATH = os.path.join(_THIS_DIR, CONFIG_FILENAME)


def load_config(path=None):
    """Read the JSON config file, returning {} if missing/invalid/empty.
    Never raises - a bad or absent config file should degrade to built-in
    defaults, not crash the CLI."""
    path = path or CONFIG_PATH
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        print("WARNING: could not read %s (%s) - using built-in defaults" % (path, exc))
        return {}
    if not isinstance(data, dict):
        print("WARNING: %s does not contain a JSON object - using built-in defaults" % path)
        return {}
    return data


def find_repo_root(start_path=None):
    """Walk upward from start_path (default: this file's directory) looking
    for a `.git` directory (the repo root marker), so ai_output/ lands in
    the project root no matter what the caller's current working directory
    is. Falls back to 3 parents up (matches this file's fixed
    <root>/.github/scripts/klocwork/ location) if no `.git` is found,
    e.g. a shallow/exported checkout without a .git folder."""
    d = os.path.abspath(start_path or _THIS_DIR)
    while True:
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))


def default_ai_output_dir(config=None):
    """Resolve the default ai_output/klocwork directory, anchored to the
    repo root (not the current working directory), honouring an optional
    "ai_output_dir" override in the config file."""
    config = config if config is not None else load_config()
    override = config.get("ai_output_dir")
    if override:
        return override if os.path.isabs(override) else os.path.join(find_repo_root(), override)
    return os.path.join(find_repo_root(), "ai_output", "klocwork")


def get(config, key, fallback=None):
    """Small helper: return config[key] unless it's missing/empty, in which
    case return fallback."""
    value = config.get(key)
    return value if value not in (None, "") else fallback


def get_int(config, key, fallback=None):
    """Small helper for a config value that should be an int (e.g.
    "max_warnings_per_file"). Returns `fallback` if the key is missing,
    empty, zero, or not parseable as an int - never raises."""
    value = config.get(key)
    if not value:
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        print("WARNING: config key '%s' is not a valid integer (%r) - using default" % (key, value))
        return fallback
    return parsed if parsed > 0 else fallback


def get_list(config, key, fallback=None):
    """Small helper for a config value that may be given as either a JSON
    list or a single comma-separated string (e.g. "ruleset"). Returns a
    list with surrounding whitespace stripped from each item and empty
    items dropped. Returns `fallback` (default []) if the key is
    missing/empty."""
    fallback = [] if fallback is None else fallback
    value = config.get(key)
    if not value:
        return fallback
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = list(value)
    return [str(item).strip() for item in items if str(item).strip()]
