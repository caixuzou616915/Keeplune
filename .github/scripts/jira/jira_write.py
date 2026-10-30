"""
Jira Write - Add comments and update fields on existing tickets.

Provides unified interface to modify tickets: add comments, update fields, change status.
Supports multiple update modes: replace, append, set.

Usage:
    # Add a comment
    python jira_write.py JDM-6798 --comment "Fix validated in test environment"
    
    # Update field (set value)
    python jira_write.py JDM-6798 --field status --value "In Progress"
    
    # Update description (append)
    python jira_write.py JDM-6798 --field description --append "\n\nAdditional notes"
    
    # Update field (replace text)
    python jira_write.py JDM-6798 --field description --replace "old text" "new text"
    
    # Multiple operations
    python jira_write.py JDM-6798 \\
        --comment "Status update" \\
        --field status --value "In Progress" \\
        --field labels --append "urgent"

Configuration:
    Create .env file in the same directory with:
        JIRA_BASE_URL=https://ix.jira.automotive.cloud
        JIRA_EMAIL=your.email@company.com
        JIRA_API_TOKEN=your_api_token_here
    
    Or set as environment variables.

Contact: Zhao Jianbo
Supported by: UX SW AI Community
"""

import sys
import os
import json
import argparse
import re

import jira_utils


# ---------------------------------------------------------------------------
# Field Updates
# ---------------------------------------------------------------------------
def update_field(base_url, email, token, pat, issue_key, field_name, new_value):
    """
    Update a single field on an issue.
    
    Args:
        issue_key: Issue key (e.g., "JDM-6798")
        field_name: Field name (summary, description, status, assignee, labels, etc.)
        new_value: New value for the field
    """
    url = f"{base_url}/rest/api/2/issue/{issue_key}"
    headers = jira_utils.build_headers(email, token, pat)

    data = {
        "fields": {
            field_name: new_value
        }
    }

    jira_utils.make_request(url, method="PUT", headers=headers, data=data)
    print(f"✓ Updated {issue_key} field '{field_name}'", file=sys.stderr)


def append_to_field(base_url, email, token, pat, issue_key, field_name, text_to_append):
    """
    Append text to an existing field (useful for description, comments, labels).
    
    Args:
        issue_key: Issue key
        field_name: Field name
        text_to_append: Text to append
    """
    # Fetch current value
    issue = jira_utils.fetch_issue(base_url, email, token, pat, issue_key)
    current_value = issue.get("fields", {}).get(field_name, "")

    if isinstance(current_value, list):
        # For list fields (labels, components), append as new item
        if isinstance(text_to_append, str):
            current_value.append(text_to_append)
    else:
        # For text fields, concatenate
        current_value = f"{current_value}{text_to_append}"

    update_field(base_url, email, token, pat, issue_key, field_name, current_value)


def replace_in_field(base_url, email, token, pat, issue_key, field_name, old_text, new_text):
    """
    Replace text within a field.
    
    Args:
        issue_key: Issue key
        field_name: Field name
        old_text: Text to find and replace
        new_text: Replacement text
    """
    # Fetch current value
    issue = jira_utils.fetch_issue(base_url, email, token, pat, issue_key)
    current_value = issue.get("fields", {}).get(field_name, "")

    if not isinstance(current_value, str):
        print(f"Error: Field '{field_name}' is not a text field", file=sys.stderr)
        sys.exit(1)

    if old_text not in current_value:
        print(f"Warning: Text '{old_text}' not found in field '{field_name}'", file=sys.stderr)
        return

    updated_value = current_value.replace(old_text, new_text)
    update_field(base_url, email, token, pat, issue_key, field_name, updated_value)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------
def add_comment(base_url, email, token, pat, issue_key, comment_text):
    """
    Add a comment to an issue.
    
    Args:
        issue_key: Issue key
        comment_text: Comment text (supports Jira wiki markup)
    """
    url = f"{base_url}/rest/api/2/issue/{issue_key}/comment"
    headers = jira_utils.build_headers(email, token, pat)

    data = {"body": comment_text}

    response = jira_utils.make_request(url, method="POST", headers=headers, data=data)
    comment_id = response.get("id", "")
    print(f"✓ Added comment to {issue_key} (ID: {comment_id})", file=sys.stderr)


# ---------------------------------------------------------------------------
# Transitions (Status Change)
# ---------------------------------------------------------------------------
def get_transitions(base_url, email, token, pat, issue_key):
    """Get available transitions (status changes) for an issue."""
    url = f"{base_url}/rest/api/2/issue/{issue_key}/transitions"
    headers = jira_utils.build_headers(email, token, pat)
    response = jira_utils.make_request(url, method="GET", headers=headers)
    return response.get("transitions", [])


def transition_issue(base_url, email, token, pat, issue_key, transition_name):
    """
    Transition an issue to a new status.
    
    Args:
        issue_key: Issue key
        transition_name: Name of the transition (e.g., "In Progress", "Done")
    """
    transitions = get_transitions(base_url, email, token, pat, issue_key)

    transition_id = None
    for trans in transitions:
        if trans.get("name") == transition_name:
            transition_id = trans.get("id")
            break

    if not transition_id:
        available = [t.get("name") for t in transitions]
        print(f"Error: Transition '{transition_name}' not available", file=sys.stderr)
        print(f"Available transitions: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    url = f"{base_url}/rest/api/2/issue/{issue_key}/transitions"
    headers = jira_utils.build_headers(email, token, pat)
    data = {"transition": {"id": transition_id}}

    jira_utils.make_request(url, method="POST", headers=headers, data=data)
    print(f"✓ Transitioned {issue_key} to '{transition_name}'", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Add comments and update fields on Jira tickets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  Add a comment:
    python jira_write.py JDM-6798 --comment "Fix validated"
  
  Update field:
    python jira_write.py JDM-6798 --field status --value "In Progress"
  
  Append to field:
    python jira_write.py JDM-6798 --field description --append "\n\nMore info"
  
  Replace in field:
    python jira_write.py JDM-6798 --field description --replace "fix it" "implement fix"
  
  Transition status:
    python jira_write.py JDM-6798 --transition "In Progress"
        """
    )

    parser.add_argument("issue_key", help="Jira issue key (e.g., JDM-6798)")
    parser.add_argument("--comment", default=None, help="Add a comment")
    parser.add_argument("--field", default=None, help="Field name to update")
    parser.add_argument("--value", default=None, help="New field value (use with --field)")
    parser.add_argument("--append", default=None, help="Append text to field")
    parser.add_argument(
        "--replace", nargs=2, metavar=("OLD", "NEW"),
        help="Replace OLD text with NEW in field"
    )
    parser.add_argument("--transition", default=None, help="Transition to new status (e.g., 'In Progress')")

    args = parser.parse_args()

    # Validate arguments
    if not args.comment and not args.field and not args.transition:
        parser.print_help()
        sys.exit(1)

    if args.field and not (args.value or args.append or args.replace):
        print("Error: --field requires --value, --append, or --replace", file=sys.stderr)
        sys.exit(1)

    # Get config
    base_url, email, token, pat = jira_utils.get_config()

    # Execute operations
    try:
        if args.comment:
            add_comment(base_url, email, token, pat, args.issue_key, args.comment)

        if args.field:
            if args.value:
                update_field(base_url, email, token, pat, args.issue_key, args.field, args.value)
            elif args.append:
                append_to_field(base_url, email, token, pat, args.issue_key, args.field, args.append)
            elif args.replace:
                old, new = args.replace
                replace_in_field(base_url, email, token, pat, args.issue_key, args.field, old, new)

        if args.transition:
            transition_issue(base_url, email, token, pat, args.issue_key, args.transition)

        print(f"\n✓ All operations completed for {args.issue_key}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
