"""
Confluence Utilities - Shared functions for all Confluence tools.

Provides:
  - Configuration loading (.env parsing)
  - HTTP headers building (Basic auth, Bearer token)
  - SSL context setup
  - Common request/response handling
  - Error handling helpers

Supports both Confluence Cloud (email + API token) and Data Center/Server (PAT).

Contact: UX SW AI Community
"""

import sys
import os
import json
import urllib.request
import urllib.error
import urllib.parse
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
    Read Confluence connection config from environment or .env file.
    Supports both Confluence Cloud (email + API token) and Data Center (PAT).

    Returns:
        tuple: (base_url, email, token, pat)
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    _load_dotenv(os.path.join(script_dir, ".env"))

    base_url = os.environ.get("CONFLUENCE_BASE_URL", "https://central.confluence.automotive.cloud").rstrip("/")
    email = os.environ.get("CONFLUENCE_EMAIL", "")
    token = os.environ.get("CONFLUENCE_API_TOKEN", "")
    pat = os.environ.get("CONFLUENCE_PAT", "")

    # Data Center / Server: Personal Access Token
    if pat:
        return base_url, "", "", pat

    # Cloud: Email + API Token
    if not token:
        print(
            "Error: Set CONFLUENCE_PAT (Data Center) or "
            "CONFLUENCE_EMAIL+CONFLUENCE_API_TOKEN (Cloud).",
            file=sys.stderr,
        )
        sys.exit(1)
    if not email:
        print(
            "Error: CONFLUENCE_EMAIL required when using CONFLUENCE_API_TOKEN (Cloud auth).",
            file=sys.stderr,
        )
        sys.exit(1)

    return base_url, email, token, ""


# ---------------------------------------------------------------------------
# Headers & SSL
# ---------------------------------------------------------------------------
def build_headers(email, token, pat, content_type="application/json"):
    """Build HTTP headers for Confluence REST API requests."""
    headers = {
        "Accept": "application/json",
        "Content-Type": content_type,
    }

    if pat:
        headers["Authorization"] = f"Bearer {pat}"
    else:
        credentials = base64.b64encode(
            f"{email}:{token}".encode("utf-8")
        ).decode("ascii")
        headers["Authorization"] = f"Basic {credentials}"

    return headers


def get_ssl_context():
    """Return a standard SSL context for HTTPS requests."""
    return ssl.create_default_context()


# ---------------------------------------------------------------------------
# HTTP Request / Response
# ---------------------------------------------------------------------------
def make_request(url, method="GET", headers=None, data=None, timeout=30):
    """
    Make an HTTP request and return the parsed JSON response.

    Args:
        url:     Full URL to request
        method:  HTTP method (GET, POST, PUT, DELETE)
        headers: Dict of HTTP headers
        data:    Dict to JSON-encode as request body (ignored for GET/DELETE)
        timeout: Request timeout in seconds

    Returns:
        dict: Parsed JSON response (empty dict for 204 No Content)

    Raises:
        SystemExit: On HTTP error or network issue
    """
    if headers is None:
        headers = {}

    body = None
    if data is not None and method not in ("GET", "DELETE"):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(
            req, context=get_ssl_context(), timeout=timeout
        ) as resp:
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


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------
def fetch_page(base_url, email, token, pat, page_id, expand="body.storage,version,space,ancestors"):
    """
    Fetch a Confluence page by its numeric ID.

    Args:
        page_id: Numeric Confluence page ID
        expand:  Comma-separated list of properties to expand

    Returns:
        dict: Full page object from the REST API
    """
    params = urllib.parse.urlencode({"expand": expand})
    url = f"{base_url}/rest/api/content/{page_id}?{params}"
    headers = build_headers(email, token, pat)
    return make_request(url, method="GET", headers=headers)


def search_pages(base_url, email, token, pat, cql, limit=25, start=0):
    """
    Search pages using Confluence Query Language (CQL).

    Args:
        cql:   CQL query string, e.g. 'space=DEV AND title~"Release Notes"'
        limit: Max results per page (1-50)
        start: Pagination offset

    Returns:
        dict: Search results object { results, start, limit, size, totalSize }
    """
    params = urllib.parse.urlencode({"cql": cql, "limit": limit, "start": start})
    url = f"{base_url}/rest/api/content/search?{params}"
    headers = build_headers(email, token, pat)
    return make_request(url, method="GET", headers=headers)


def get_page_children(base_url, email, token, pat, page_id, limit=50, start=0):
    """
    Get direct child pages of a given page.

    Args:
        page_id: Parent page numeric ID
        limit:   Max results
        start:   Pagination offset

    Returns:
        dict: Results object
    """
    params = urllib.parse.urlencode({"limit": limit, "start": start})
    url = f"{base_url}/rest/api/content/{page_id}/child/page?{params}"
    headers = build_headers(email, token, pat)
    return make_request(url, method="GET", headers=headers)


def get_space_homepage(base_url, email, token, pat, space_key):
    """
    Retrieve the homepage of a space.

    Args:
        space_key: Confluence space key (e.g. 'DEV', 'TEAM')

    Returns:
        dict: Space object including homepageId
    """
    params = urllib.parse.urlencode({"expand": "homepage"})
    url = f"{base_url}/rest/api/space/{space_key}?{params}"
    headers = build_headers(email, token, pat)
    return make_request(url, method="GET", headers=headers)
