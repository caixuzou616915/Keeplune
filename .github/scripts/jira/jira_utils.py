"""
Jira Utilities - Shared functions for all Jira tools.

Provides:
  - Configuration loading (.env parsing)
  - HTTP headers building (Basic auth, Bearer token)
  - SSL context setup
  - Common request/response handling
  - Error handling helpers

Contact: Zhao Jianbo
Supported by: UX SW AI Community
"""

import sys
import os
import json
import urllib.request
import urllib.error
import base64
import ssl


# ---------------------------------------------------------------------------
# Configuration Loading
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
    """
    Read Jira connection config from environment or .env file.
    Supports both Jira Cloud (email + API token) and Data Center (PAT).
    
    Returns:
        tuple: (base_url, email, token, pat)
    """
    # Try .env in same directory as calling script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    _load_dotenv(os.path.join(script_dir, ".env"))

    base_url = os.environ.get("JIRA_BASE_URL", "https://ix.jira.automotive.cloud").rstrip("/")
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")
    pat = os.environ.get("JIRA_PAT", "")

    # Data Center / Server: Personal Access Token
    if pat:
        return base_url, "", "", pat

    # Cloud: Email + API Token
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
# Headers & SSL
# ---------------------------------------------------------------------------
def build_headers(email, token, pat, content_type="application/json"):
    """Build HTTP headers for Jira API requests."""
    headers = {
        "Accept": "application/json",
        "Content-Type": content_type,
    }

    if pat:
        headers["Authorization"] = f"Bearer {pat}"
    else:
        credentials = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {credentials}"

    return headers


def get_ssl_context():
    """Return a standard SSL context for HTTPS requests."""
    return ssl.create_default_context()


# ---------------------------------------------------------------------------
# HTTP Request/Response
# ---------------------------------------------------------------------------
def make_request(url, method="GET", headers=None, data=None, timeout=30):
    """
    Make an HTTP request and return parsed JSON response.
    
    Args:
        url: Full URL to request
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
        headers: Dict of HTTP headers
        data: Dict to JSON-encode as request body
        timeout: Request timeout in seconds
    
    Returns:
        dict: Parsed JSON response
        
    Raises:
        SystemExit: On HTTP error or network issue
    """
    if headers is None:
        headers = {}

    body = None
    if data:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, context=get_ssl_context(), timeout=timeout) as resp:
            response_body = resp.read().decode("utf-8")
            if response_body.strip():
                return json.loads(response_body)
            return {}

    except urllib.error.HTTPError as e:
        body_str = e.read().decode("utf-8", errors="replace") if e.fp else ""
        print(f"Error: HTTP {e.code} — {body_str[:600]}", file=sys.stderr)
        sys.exit(1)

    except urllib.error.URLError as e:
        print(f"Error: Cannot connect to {url} — {e.reason}", file=sys.stderr)
        sys.exit(1)


def fetch_issue(base_url, email, token, pat, issue_key, extra_fields=None):
    """
    Fetch a Jira issue via REST API v2.
    
    Args:
        base_url: Jira base URL
        email: Jira email (Cloud auth)
        token: Jira API token (Cloud auth)
        pat: Personal Access Token (Data Center auth)
        issue_key: Issue key (e.g., "JDM-6798")
        extra_fields: Optional list of additional fields to fetch
    
    Returns:
        dict: Issue data with 'key', 'fields', etc.
    """
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
    headers = build_headers(email, token, pat)

    return make_request(url, method="GET", headers=headers)


# ---------------------------------------------------------------------------
# Error Messages
# ---------------------------------------------------------------------------
def format_http_error(code, body_str):
    """Format HTTP error message with context."""
    if code == 400:
        return f"Bad request (400) — {body_str[:300]}"
    elif code == 401:
        return "Authentication failed (401). Check JIRA_PAT / credentials."
    elif code == 403:
        return "Permission denied (403). Your account lacks required permissions."
    elif code == 404:
        return f"Not found (404) — Issue or endpoint does not exist"
    else:
        return f"HTTP {code} — {body_str[:300]}"
