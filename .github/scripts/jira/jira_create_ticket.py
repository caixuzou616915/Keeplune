"""
Jira Create Ticket - Create new standalone Jira tickets.

Create main tickets (Bug, Story, Task, etc.) directly in Jira.
For sub-tickets with approval gates, use jira_create_subtask.py instead.

Usage:
    # Create a simple bug
    python jira_create_ticket.py \\
        --project DGC \\
        --summary "Display flickering on startup" \\
        --type Bug \\
        --priority High
    
    # Create with description
    python jira_create_ticket.py \\
        --project DGC \\
        --summary "Implement new feature" \\
        --type Story \\
        --description "Add dark mode support to HUD display" \\
        --assignee username
    
    # Create with components and labels
    python jira_create_ticket.py \\
        --project DGC \\
        --summary "Performance issue" \\
        --type Bug \\
        --components "HUD,Graphics" \\
        --labels "performance,urgent" \\
        --priority Critical
    
    # Dry run (preview without creating)
    python jira_create_ticket.py \\
        --project DGC \\
        --summary "Test ticket" \\
        --type Task \\
        --dry-run

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
import textwrap

import jira_utils


# ---------------------------------------------------------------------------
# Ticket Creation
# ---------------------------------------------------------------------------
def create_ticket(
    base_url, email, token, pat,
    project_key, summary, issue_type, description=None,
    priority=None, assignee=None, components=None, labels=None,
    environment=None, dry_run=False
):
    """
    Create a new Jira ticket.
    
    Args:
        project_key: Project key (e.g., "DGC")
        summary: Ticket summary
        issue_type: Issue type (Bug, Story, Task, Epic, etc.)
        description: Optional description
        priority: Optional priority (Critical, High, Medium, Low)
        assignee: Optional assignee username
        components: Optional comma-separated component names
        labels: Optional comma-separated labels
        environment: Optional environment field
        dry_run: If True, print payload without creating
    
    Returns:
        dict: Created ticket response
    """
    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }

    if description:
        fields["description"] = description

    if priority:
        fields["priority"] = {"name": priority}

    if assignee:
        fields["assignee"] = {"name": assignee}

    if components:
        component_list = [{"name": c.strip()} for c in components.split(",")]
        fields["components"] = component_list

    if labels:
        label_list = [l.strip() for l in labels.split(",")]
        fields["labels"] = label_list

    if environment:
        fields["environment"] = environment

    payload = {"fields": fields}

    # Dry run
    if dry_run:
        print("=== DRY RUN — Payload that would be sent to Jira ===")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return payload

    # Create in Jira
    print("Creating ticket in Jira...", file=sys.stderr)
    url = f"{base_url}/rest/api/2/issue"
    headers = jira_utils.build_headers(email, token, pat)

    response = jira_utils.make_request(url, method="POST", headers=headers, data=payload)

    created_key = response.get("key", "")
    created_url = response.get("self", "")

    return {
        "key": created_key,
        "url": f"{base_url}/browse/{created_key}",
        "self": created_url,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Create a new standalone Jira ticket",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              Create a bug:
                python jira_create_ticket.py \\
                  --project DGC --summary "Display issue" \\
                  --type Bug --priority High
              
              Create with all details:
                python jira_create_ticket.py \\
                  --project DGC \\
                  --summary "New HUD feature" \\
                  --type Story \\
                  --description "Implement dark mode support" \\
                  --priority Medium \\
                  --components "HUD,Graphics" \\
                  --labels "feature,ui"
              
              Dry run (preview):
                python jira_create_ticket.py \\
                  --project DGC --summary "Test" \\
                  --type Task --dry-run
        """)
    )

    parser.add_argument("--project", required=True, help="Project key (e.g., DGC)")
    parser.add_argument("--summary", required=True, help="Ticket summary (issue title)")
    parser.add_argument("--type", dest="issue_type", required=True,
                        help="Issue type: Bug, Story, Task, Epic, etc.")
    parser.add_argument("--description", default=None, help="Detailed description")
    parser.add_argument("--priority", default=None,
                        help="Priority: Critical, High, Medium, Low")
    parser.add_argument("--assignee", default=None, help="Assignee username")
    parser.add_argument("--components", default=None,
                        help="Comma-separated component names")
    parser.add_argument("--labels", default=None,
                        help="Comma-separated labels")
    parser.add_argument("--environment", default=None,
                        help="Environment field (free text)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print payload without creating")

    args = parser.parse_args()

    # Get config
    base_url, email, token, pat = jira_utils.get_config()

    # Create ticket
    result = create_ticket(
        base_url, email, token, pat,
        project_key=args.project,
        summary=args.summary,
        issue_type=args.issue_type,
        description=args.description,
        priority=args.priority,
        assignee=args.assignee,
        components=args.components,
        labels=args.labels,
        environment=args.environment,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        return

    # Print result
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n✓ Created: {base_url}/browse/{result['key']}", file=sys.stderr)


if __name__ == "__main__":
    main()
