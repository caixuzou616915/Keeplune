"""
Jira Sub-ticket Creator - Creates analysis, implementation, test, or other sub-tickets.

Usage:
    python jira_create_subtask.py <PARENT_TICKET_ID> [OPTIONS]

Examples:
    # Create an analysis sub-ticket
    python jira_create_subtask.py DGC-4327 --type analysis

    # Create with explicit root cause and fix description
    python jira_create_subtask.py DGC-4327 --type implementation \\
        --root-cause "Null pointer dereference in eyebpos1c1.c line 42" \\
        --fix-description "Add null check before dereferencing pointer"

    # Fill from an AI-analysis JSON file (see --analysis-json below)
    python jira_create_subtask.py DGC-4327 --type analysis --analysis-json result.json

    # Dry-run: print the payload without actually creating the ticket
    python jira_create_subtask.py DGC-4327 --type test --dry-run

Configuration:
    Uses the same .env file as all JIRA tools (same directory):
        JIRA_BASE_URL=https://ix.jira.automotive.cloud
        JIRA_EMAIL=your.email@company.com
        JIRA_API_TOKEN=your_api_token_here

    Or for Jira Data Center/Server:
        JIRA_BASE_URL=https://jira.internal.company.com
        JIRA_PAT=your_personal_access_token

Contact: Zhao Jianbo
Supported by: UX SW AI Community

Analysis JSON format (used with --analysis-json):
    {
        "symptom":          "Short problem description",
        "reproduction_steps": "Step A → Step B → Step C",
        "expected_behavior": "...",
        "actual_behavior":  "...",
        "affected_module":  "pkg/em_s3p_hud/...",
        "key_clues":        "signal names, variable names, etc.",
        "root_cause":       "Detailed root cause explanation",
        "impact_scope":     "Other affected features / none",
        "fix_description":  "How to fix the issue",
        "code_changes":     "Files and line numbers to change",
        "verification":     "How to verify the fix"
    }
    Any subset of fields is accepted; missing fields are shown as TBD.
"""

import sys
import os
import json
import argparse
import textwrap

import jira_utils


# ---------------------------------------------------------------------------
# Ticket type definitions
# ---------------------------------------------------------------------------
TICKET_TYPES = ("analysis", "implementation", "test", "other")

TICKET_TYPE_CONFIG = {
    "analysis": {
        "summary_prefix": "[Analysis]",
        "default_issuetype": "Analysis Subtask",
    },
    "implementation": {
        "summary_prefix": "[Implementation]",
        "default_issuetype": "Implementation Subtask",
    },
    "test": {
        "summary_prefix": "[Test]",
        "default_issuetype": "Test Subtask",
    },
    "other": {
        "summary_prefix": "[Sub-task]",
        "default_issuetype": "Admin Subtask",
    },
}


# Use jira_utils for config and headers
def get_config():
    """Read Jira connection config from environment / .env file."""
    return jira_utils.get_config()


# ---------------------------------------------------------------------------
# Fetch parent ticket info
# ---------------------------------------------------------------------------
def fetch_parent(base_url, email, token, pat, issue_key):
    """Fetch minimal fields from the parent ticket."""
    issue = jira_utils.fetch_issue(
        base_url, email, token, pat, issue_key,
        extra_fields=["status", "priority", "issuetype", "components"]
    )
    f = issue.get("fields", {})
    project = f.get("project", {})
    # Extract project key - fallback to parsing from issue_key if needed
    project_key = project.get("key", issue_key.split("-")[0])
    return {
        "key": issue.get("key", issue_key),
        "summary": f.get("summary", ""),
        "project_key": project_key,
        "project_name": project.get("name", ""),
    }


# ---------------------------------------------------------------------------
# Description builders (Jira wiki markup for Data Center / Server)
# ---------------------------------------------------------------------------
def _tbd(value, default="TBD"):
    """Return value if non-empty, otherwise default."""
    return value.strip() if value and value.strip() else default


def build_analysis_description(parent, analysis):
    """Build Jira wiki markup description for an analysis sub-ticket."""
    a = analysis  # shorthand

    lines = [
        "h2. Root Cause Analysis",
        "",
        f"*Parent Ticket:* [{parent['key']}] {parent['summary']}",
        "",
        "----",
        "",
        "h3. Problem Summary",
        _tbd(a.get("symptom", "")),
        "",
        "h3. Reproduction Steps",
        _tbd(a.get("reproduction_steps", "")),
        "",
        "h3. Expected Behavior",
        _tbd(a.get("expected_behavior", "")),
        "",
        "h3. Actual Behavior",
        _tbd(a.get("actual_behavior", "")),
        "",
        "h3. Affected Module",
        _tbd(a.get("affected_module", "")),
        "",
        "h3. Key Clues",
        _tbd(a.get("key_clues", "")),
        "",
        "----",
        "",
        "h3. Root Cause",
        _tbd(a.get("root_cause", "")),
        "",
        "h3. Impact Scope",
        _tbd(a.get("impact_scope", "")),
        "",
        "----",
        "",
        "h3. Additional Notes",
        _tbd(a.get("notes", ""), default=""),
    ]
    return "\n".join(lines).rstrip()


def build_implementation_description(parent, analysis):
    """Build Jira wiki markup description for an implementation sub-ticket."""
    a = analysis

    lines = [
        "h2. Implementation Details",
        "",
        f"*Parent Ticket:* [{parent['key']}] {parent['summary']}",
        "",
        "----",
        "",
        "h3. Root Cause Summary",
        _tbd(a.get("root_cause", "")),
        "",
        "h3. Fix Description",
        _tbd(a.get("fix_description", "")),
        "",
        "h3. Code Changes",
        _tbd(a.get("code_changes", "")),
        "",
        "h3. Affected Module",
        _tbd(a.get("affected_module", "")),
        "",
        "h3. Impact Scope",
        _tbd(a.get("impact_scope", "")),
        "",
        "h3. Verification",
        _tbd(a.get("verification", "")),
        "",
        "h3. Additional Notes",
        _tbd(a.get("notes", ""), default=""),
    ]
    return "\n".join(lines).rstrip()


def build_test_description(parent, analysis):
    """Build Jira wiki markup description for a test sub-ticket."""
    a = analysis

    lines = [
        "h2. Test Plan",
        "",
        f"*Parent Ticket:* [{parent['key']}] {parent['summary']}",
        "",
        "----",
        "",
        "h3. Test Scope",
        _tbd(a.get("test_scope", a.get("fix_description", ""))),
        "",
        "h3. Affected Module",
        _tbd(a.get("affected_module", "")),
        "",
        "h3. Reproduction Steps",
        _tbd(a.get("reproduction_steps", "")),
        "",
        "h3. Expected Behavior After Fix",
        _tbd(a.get("expected_behavior", "")),
        "",
        "h3. Test Cases",
        _tbd(a.get("test_cases", "")),
        "",
        "h3. Verification Steps",
        _tbd(a.get("verification", "")),
        "",
        "h3. Additional Notes",
        _tbd(a.get("notes", ""), default=""),
    ]
    return "\n".join(lines).rstrip()


def build_other_description(parent, analysis):
    """Build Jira wiki markup description for a generic sub-ticket."""
    a = analysis

    lines = [
        "h2. Sub-task Details",
        "",
        f"*Parent Ticket:* [{parent['key']}] {parent['summary']}",
        "",
        "----",
        "",
    ]
    if a.get("symptom"):
        lines += ["h3. Problem Summary", a["symptom"], ""]
    if a.get("root_cause"):
        lines += ["h3. Root Cause", a["root_cause"], ""]
    if a.get("fix_description"):
        lines += ["h3. Fix / Action", a["fix_description"], ""]
    if a.get("notes"):
        lines += ["h3. Additional Notes", a["notes"], ""]
    return "\n".join(lines).rstrip()


DESCRIPTION_BUILDERS = {
    "analysis": build_analysis_description,
    "implementation": build_implementation_description,
    "test": build_test_description,
    "other": build_other_description,
}


# ---------------------------------------------------------------------------
# Build Jira issue payload
# ---------------------------------------------------------------------------
def build_payload(parent, ticket_type, summary_override, description, issuetype, assignee):
    """Build the POST body for creating a Jira sub-ticket."""
    cfg = TICKET_TYPE_CONFIG[ticket_type]
    prefix = cfg["summary_prefix"]
    effective_issuetype = issuetype or cfg["default_issuetype"]

    if summary_override:
        summary = summary_override
    else:
        parent_summary = parent["summary"]
        # Trim to keep total summary under 255 chars
        max_parent_len = 255 - len(prefix) - 2  # 2 = space + padding
        if len(parent_summary) > max_parent_len:
            parent_summary = parent_summary[:max_parent_len - 3] + "..."
        summary = f"{prefix} {parent_summary}"

    fields = {
        "project": {"key": parent["project_key"]},
        "summary": summary,
        "description": description,
        "issuetype": {"name": effective_issuetype},
    }

    # For Sub-task types, set the parent field
    if "subtask" in effective_issuetype.lower() or effective_issuetype.lower() == "sub-task":
        fields["parent"] = {"key": parent["key"]}

    if assignee:
        fields["assignee"] = {"name": assignee}

    return {"fields": fields}


# ---------------------------------------------------------------------------
# Create the issue in Jira
# ---------------------------------------------------------------------------
def create_issue(base_url, email, token, pat, payload):
    """POST to Jira API to create a new issue. Returns the created issue key."""
    url = f"{base_url}/rest/api/2/issue"
    headers = jira_utils.build_headers(email, token, pat)
    
    try:
        data = jira_utils.make_request(url, method="POST", headers=headers, data=payload)
    except SystemExit:
        # Catch and provide helpful error messages for common issues
        print("\nCommon solutions:", file=sys.stderr)
        print("  - The issue type may not be available in this project", file=sys.stderr)
        print("  - 'Sub-task' may need to be enabled in the project scheme", file=sys.stderr)
        print("  - Try --issuetype 'Task' or --issuetype 'Story'", file=sys.stderr)
        sys.exit(1)
    
    return data.get("key", ""), data.get("self", "")


def link_issue(base_url, email, token, pat, child_key, parent_key, link_type="is caused by"):
    """Create an issue link between child and parent."""
    url = f"{base_url}/rest/api/2/issueLink"
    headers = jira_utils.build_headers(email, token, pat)
    payload = {
        "type": {"name": link_type},
        "inwardIssue": {"key": child_key},
        "outwardIssue": {"key": parent_key},
    }
    
    try:
        jira_utils.make_request(url, method="POST", headers=headers, data=payload)
    except SystemExit:
        # Link failure is non-fatal; warn only
        print(f"Warning: Could not create issue link between {child_key} and {parent_key}",
              file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Create a Jira sub-ticket (analysis / implementation / test / other)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Analysis JSON fields (--analysis-json):
              symptom, reproduction_steps, expected_behavior, actual_behavior,
              affected_module, key_clues, root_cause, impact_scope,
              fix_description, code_changes, verification, test_scope,
              test_cases, notes
        """),
    )
    parser.add_argument("parent_ticket", help="Parent Jira ticket ID (e.g., DGC-4327)")
    parser.add_argument(
        "--type", dest="ticket_type", choices=TICKET_TYPES, default="test",
        help="Sub-ticket type: analysis, implementation, test, or other (default: test)",
    )
    parser.add_argument("--summary", default=None,
                        help="Override the auto-generated summary")
    parser.add_argument("--description", default=None,
                        help="Plain text to append as 'Additional Notes' in the description")
    parser.add_argument("--analysis-json", default=None, metavar="FILE",
                        help="Path to a JSON file with analysis results (auto-fills all fields)")
    parser.add_argument("--root-cause", default=None,
                        help="Root cause text (overrides root_cause field in JSON)")
    parser.add_argument("--fix-description", default=None,
                        help="Fix description text (overrides fix_description field in JSON)")
    parser.add_argument("--affected-module", default=None,
                        help="Affected module path (overrides affected_module field in JSON)")
    parser.add_argument("--issuetype", default=None,
                        help="Jira issue type name (default: Sub-task). "
                             "Use 'Task' or 'Story' if Sub-task is not available in the project.")
    parser.add_argument("--assignee", default=None,
                        help="Assignee username (Jira Server) or account ID (Jira Cloud)")
    parser.add_argument("--link-type", default="is caused by",
                        help="Issue link type when not using Sub-task (default: 'is caused by')")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the payload JSON without creating the ticket")
    args = parser.parse_args()

    # --- Load analysis data ---
    analysis = {}
    if args.analysis_json:
        path = args.analysis_json
        if not os.path.isfile(path):
            print(f"Error: Analysis JSON file not found: {path}", file=sys.stderr)
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            try:
                analysis = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in {path}: {e}", file=sys.stderr)
                sys.exit(1)

    # CLI arguments override JSON values
    if args.root_cause:
        analysis["root_cause"] = args.root_cause
    if args.fix_description:
        analysis["fix_description"] = args.fix_description
    if args.affected_module:
        analysis["affected_module"] = args.affected_module
    if args.description:
        analysis["notes"] = args.description

    # --- Config ---
    base_url, email, token, pat = get_config()

    # --- Fetch parent ticket ---
    if not args.dry_run:
        print(f"Fetching parent ticket {args.parent_ticket}...", file=sys.stderr)
    parent = fetch_parent(base_url, email, token, pat, args.parent_ticket) if not args.dry_run else {
        "key": args.parent_ticket,
        "summary": "(dry-run — parent not fetched)",
        "project_key": args.parent_ticket.split("-")[0],
        "project_name": "",
    }

    # --- Build description ---
    builder = DESCRIPTION_BUILDERS[args.ticket_type]
    description = builder(parent, analysis)

    # --- Build payload ---
    payload = build_payload(
        parent=parent,
        ticket_type=args.ticket_type,
        summary_override=args.summary,
        description=description,
        issuetype=args.issuetype,
        assignee=args.assignee,
    )

    # --- Dry run ---
    if args.dry_run:
        print("=== DRY RUN — Payload that would be sent to Jira ===")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("\n=== Description Preview ===")
        print(description)
        return

    # --- Create issue ---
    print(f"Creating {args.ticket_type} sub-ticket for {args.parent_ticket}...", file=sys.stderr)
    created_key, created_url = create_issue(base_url, email, token, pat, payload)

    # --- Link to parent if not a subtask type (subtasks already have parent set via parent field) ---
    effective_issuetype = args.issuetype or TICKET_TYPE_CONFIG[args.ticket_type]["default_issuetype"]
    if "subtask" not in effective_issuetype.lower() and effective_issuetype.lower() != "sub-task":
        print(f"Linking {created_key} → {args.parent_ticket} ({args.link_type})...",
              file=sys.stderr)
        link_issue(base_url, email, token, pat, created_key, args.parent_ticket, args.link_type)

    # --- Output result ---
    result = {
        "created_key": created_key,
        "url": f"{base_url}/browse/{created_key}",
        "type": args.ticket_type,
        "parent": args.parent_ticket,
        "summary": payload["fields"]["summary"],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nCreated: {base_url}/browse/{created_key}", file=sys.stderr)


if __name__ == "__main__":
    main()
