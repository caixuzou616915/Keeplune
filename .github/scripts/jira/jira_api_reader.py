"""
Jira API Reader - Fetches Jira ticket info via REST API.

Usage:
    python jira_api_reader.py <TICKET_ID>
    python jira_api_reader.py JZC-22658
    python jira_api_reader.py JZC-22658 --fields summary,description,status

Configuration:
    Create a file '.env' in the same directory with:
        JIRA_BASE_URL=https://ix.jira.automotive.cloud
        JIRA_EMAIL=your.email@company.com
        JIRA_API_TOKEN=your_api_token_here

    Or set these as environment variables.

Output:
    JSON object with ticket fields to stdout.

Note: This tool has been superseded by jira_read.py which provides unified API + Excel reading.
      This file is kept for backward compatibility only.

Contact: Zhao Jianbo
Supported by: UX SW AI Community
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.error
import base64
import ssl


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _load_dotenv(env_path):
    """Load key=value pairs from a .env file (no third-party dependency)."""
    if not os.path.isfile(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def get_config():
    """Read Jira connection config from environment / .env file."""
    # Try .env in same directory as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    _load_dotenv(os.path.join(script_dir, ".env"))

    base_url = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")
    pat = os.environ.get("JIRA_PAT", "")

    if not base_url:
        print("Error: JIRA_BASE_URL not set. Configure .env or environment variable.", file=sys.stderr)
        sys.exit(1)
    if pat:
        # Personal Access Token (Jira Data Center / Server)
        return base_url, "", "", pat
    if not token:
        print("Error: Set JIRA_PAT (Data Center) or JIRA_EMAIL+JIRA_API_TOKEN (Cloud).",
              file=sys.stderr)
        sys.exit(1)
    if not email:
        print("Error: JIRA_EMAIL required when using JIRA_API_TOKEN (Cloud auth).",
              file=sys.stderr)
        sys.exit(1)

    return base_url, email, token, ""


# ---------------------------------------------------------------------------
# Jira REST API
# ---------------------------------------------------------------------------
def fetch_issue(base_url, email, token, pat, issue_key, extra_fields=None):
    """Fetch a Jira issue via REST API v2 and return a normalized dict."""
    # Build URL — request specific fields to reduce payload
    default_fields = [
        "summary", "description", "status", "priority", "issuetype",
        "assignee", "reporter", "created", "updated", "resolution",
        "labels", "components", "fixVersions", "versions",
        "comment", "environment",
    ]
    if extra_fields:
        default_fields = list(set(default_fields + extra_fields))

    fields_param = ",".join(default_fields)
    url = f"{base_url}/rest/api/2/issue/{issue_key}?fields={fields_param}"

    # Build auth header
    if pat:
        # Personal Access Token — Bearer auth (Jira Data Center / Server)
        headers = {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/json",
        }
    else:
        # API Token — Basic auth (Jira Cloud)
        credentials = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # Create SSL context (allow corporate CA certificates)
    ctx = ssl.create_default_context()
    # If corporate proxy/CA issues, uncomment next line (NOT recommended for production):
    # ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        if e.code == 401:
            print(f"Error: Authentication failed (401). Check JIRA_EMAIL and JIRA_API_TOKEN.", file=sys.stderr)
        elif e.code == 403:
            print(f"Error: Access forbidden (403). Your account may lack permission for {issue_key}.", file=sys.stderr)
        elif e.code == 404:
            print(f"Error: Issue {issue_key} not found (404).", file=sys.stderr)
        else:
            print(f"Error: HTTP {e.code} — {body[:500]}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: Cannot connect to {base_url} — {e.reason}", file=sys.stderr)
        sys.exit(1)

    return _normalize(data, issue_key)


def _normalize(data, issue_key):
    """Convert Jira REST API response to a flat dict (same shape as Excel reader output)."""
    fields = data.get("fields", {})
    result = {"key": data.get("key", issue_key)}

    # Simple text fields
    result["summary"] = fields.get("summary", "")
    result["description"] = fields.get("description", "") or ""
    result["environment"] = fields.get("environment", "") or ""

    # Nested object fields → extract display name
    status = fields.get("status")
    result["status"] = status.get("name", "") if isinstance(status, dict) else ""

    priority = fields.get("priority")
    result["priority"] = priority.get("name", "") if isinstance(priority, dict) else ""

    issue_type = fields.get("issuetype")
    result["issue_type"] = issue_type.get("name", "") if isinstance(issue_type, dict) else ""

    assignee = fields.get("assignee")
    result["assignee"] = assignee.get("displayName", "") if isinstance(assignee, dict) else ""

    reporter = fields.get("reporter")
    result["reporter"] = reporter.get("displayName", "") if isinstance(reporter, dict) else ""

    resolution = fields.get("resolution")
    result["resolution"] = resolution.get("name", "") if isinstance(resolution, dict) else ""

    # Date fields
    result["created"] = fields.get("created", "")
    result["updated"] = fields.get("updated", "")

    # Array fields
    labels = fields.get("labels")
    result["labels"] = ", ".join(labels) if isinstance(labels, list) else ""

    components = fields.get("components")
    if isinstance(components, list):
        result["components"] = ", ".join(c.get("name", "") for c in components if isinstance(c, dict))
    else:
        result["components"] = ""

    fix_versions = fields.get("fixVersions")
    if isinstance(fix_versions, list):
        result["fix_versions"] = ", ".join(v.get("name", "") for v in fix_versions if isinstance(v, dict))
    else:
        result["fix_versions"] = ""

    affects_versions = fields.get("versions")
    if isinstance(affects_versions, list):
        result["affects_versions"] = ", ".join(v.get("name", "") for v in affects_versions if isinstance(v, dict))
    else:
        result["affects_versions"] = ""

    # Comments — concatenate the latest N comments
    comment_block = fields.get("comment", {})
    comments_list = comment_block.get("comments", []) if isinstance(comment_block, dict) else []
    if comments_list:
        formatted = []
        for c in comments_list[-10:]:  # last 10 comments
            author = c.get("author", {}).get("displayName", "Unknown")
            created = c.get("created", "")[:10]
            body = c.get("body", "")
            formatted.append(f"[{created} {author}] {body}")
        result["comments"] = "\n---\n".join(formatted)
    else:
        result["comments"] = ""

    # Remove empty values for cleaner output
    result = {k: v for k, v in result.items() if v}

    result["_source"] = "jira_api"
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Fetch Jira ticket via REST API")
    parser.add_argument("ticket_id", help="Jira ticket ID (e.g., JZC-22658)")
    parser.add_argument("--fields", default=None,
                        help="Comma-separated extra Jira field names to fetch")
    args = parser.parse_args()

    extra = args.fields.split(",") if args.fields else None
    base_url, email, token, pat = get_config()
    result = fetch_issue(base_url, email, token, pat, args.ticket_id, extra)

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
