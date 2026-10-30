"""
Confluence Read - Read and search Confluence pages.

Supports fetching a single page by ID, searching by title/space/CQL,
listing child pages, and retrieving page history/comments.

Usage:
    # Fetch page by ID
    python confluence_read.py --page-id 123456789

    # Search by title in a space
    python confluence_read.py --space DEV --title "Release Notes"

    # Full CQL search
    python confluence_read.py --cql 'space=DEV AND label=release'

    # List children of a page
    python confluence_read.py --page-id 123456789 --children

    # Get comments on a page
    python confluence_read.py --page-id 123456789 --comments

    # Output plain text body (strip HTML tags)
    python confluence_read.py --page-id 123456789 --text

Output:
    JSON object (or plain text with --text) printed to stdout.

Configuration:
    Create .env file in the same directory with:
        CONFLUENCE_BASE_URL=https://your-domain.atlassian.net/wiki
        CONFLUENCE_PAT=your_personal_access_token_here
    OR (Cloud):
        CONFLUENCE_EMAIL=your.email@company.com
        CONFLUENCE_API_TOKEN=your_api_token_here

Contact: UX SW AI Community
"""

import sys
import os
import json
import argparse
import re
import urllib.parse

import confluence_utils


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------
def _strip_html(html):
    """Remove HTML tags and decode common entities, returning plain text."""
    text = re.sub(r"<[^>]+>", " ", html)
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)
    # Collapse whitespace
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------
def read_page(base_url, email, token, pat, page_id, as_text=False):
    """
    Fetch a single page by ID and return its content.

    Args:
        page_id: Confluence page numeric ID (string or int)
        as_text: If True, return plain text instead of raw storage format

    Returns:
        dict with keys: id, title, space, version, body, url
    """
    page = confluence_utils.fetch_page(
        base_url, email, token, pat, page_id,
        expand="body.storage,version,space,ancestors,metadata.labels"
    )

    body_html = page.get("body", {}).get("storage", {}).get("value", "")
    space_key = page.get("space", {}).get("key", "")
    version_number = page.get("version", {}).get("number", 0)
    labels = [
        lbl["name"]
        for lbl in page.get("metadata", {}).get("labels", {}).get("results", [])
    ]
    ancestors = [
        {"id": a["id"], "title": a["title"]}
        for a in page.get("ancestors", [])
    ]
    page_url = f"{base_url}/pages/viewpage.action?pageId={page_id}"

    result = {
        "id": page.get("id"),
        "title": page.get("title"),
        "space": space_key,
        "version": version_number,
        "labels": labels,
        "ancestors": ancestors,
        "url": page_url,
        "body": _strip_html(body_html) if as_text else body_html,
    }
    return result


def search_pages(base_url, email, token, pat, space=None, title=None, cql=None, limit=25):
    """
    Search for pages using CQL or space+title shorthand.

    Args:
        space: Space key filter (optional)
        title: Title substring filter (optional)
        cql:   Raw CQL query (overrides space/title if provided)
        limit: Max results to return

    Returns:
        list of dicts: [{id, title, space, url}, ...]
    """
    if not cql:
        parts = ['type=page']
        if space:
            parts.append(f'space="{space}"')
        if title:
            parts.append(f'title~"{title}"')
        cql = " AND ".join(parts)

    response = confluence_utils.search_pages(
        base_url, email, token, pat, cql, limit=limit
    )
    results = []
    for item in response.get("results", []):
        results.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "space": item.get("space", {}).get("key", ""),
            "url": f"{base_url}/pages/viewpage.action?pageId={item.get('id')}",
        })
    return results


def read_children(base_url, email, token, pat, page_id):
    """
    List direct child pages of a given page.

    Returns:
        list of dicts: [{id, title, url}, ...]
    """
    response = confluence_utils.get_page_children(
        base_url, email, token, pat, page_id
    )
    results = []
    for item in response.get("results", []):
        results.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "url": f"{base_url}/pages/viewpage.action?pageId={item.get('id')}",
        })
    return results


def read_comments(base_url, email, token, pat, page_id):
    """
    Get all comments attached to a page.

    Returns:
        list of dicts: [{id, author, created, body}, ...]
    """
    import urllib.parse
    params = urllib.parse.urlencode({"expand": "body.view,version,history", "limit": 200})
    url = f"{base_url}/rest/api/content/{page_id}/child/comment?{params}"
    headers = confluence_utils.build_headers(email, token, pat)
    response = confluence_utils.make_request(url, method="GET", headers=headers)

    results = []
    for item in response.get("results", []):
        results.append({
            "id": item.get("id"),
            "author": item.get("history", {}).get("createdBy", {}).get("displayName", ""),
            "created": item.get("history", {}).get("createdDate", ""),
            "body": _strip_html(
                item.get("body", {}).get("view", {}).get("value", "")
            ),
        })
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser():
    p = argparse.ArgumentParser(
        description="Read and search Confluence pages.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--page-id", help="Numeric Confluence page ID")
    p.add_argument("--space", help="Space key for search (e.g. DEV)")
    p.add_argument("--title", help="Page title (substring) for search")
    p.add_argument("--cql", help="Raw CQL query string")
    p.add_argument("--children", action="store_true", help="List child pages of --page-id")
    p.add_argument("--comments", action="store_true", help="Get comments on --page-id")
    p.add_argument("--text", action="store_true", help="Output plain text body (strips HTML)")
    p.add_argument("--limit", type=int, default=25, help="Max search results (default: 25)")
    return p


def main():
    parser = _build_parser()
    args = parser.parse_args()

    base_url, email, token, pat = confluence_utils.get_config()

    # ---- Page mode ----
    if args.page_id:
        if args.children:
            result = read_children(base_url, email, token, pat, args.page_id)
        elif args.comments:
            result = read_comments(base_url, email, token, pat, args.page_id)
        else:
            result = read_page(base_url, email, token, pat, args.page_id, as_text=args.text)
            if args.text:
                print(result["body"])
                return
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # ---- Search mode ----
    if args.space or args.title or args.cql:
        result = search_pages(
            base_url, email, token, pat,
            space=args.space,
            title=args.title,
            cql=args.cql,
            limit=args.limit,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
