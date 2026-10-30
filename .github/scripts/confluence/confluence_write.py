"""
Confluence Write - Edit existing Confluence pages and add comments.

Supports updating a page's title and/or body content (full replace, append,
or regex-based find-and-replace), adding inline comments, and managing labels.

Usage:
    # Replace full page body (storage format / XHTML)
    python confluence_write.py --page-id 123456789 --body "<p>New content</p>"

    # Replace full page body from a file
    python confluence_write.py --page-id 123456789 --body-file updated_body.html

    # Append HTML content to the end of the page
    python confluence_write.py --page-id 123456789 --append "<p>Extra paragraph</p>"

    # Find and replace text inside the page body
    python confluence_write.py --page-id 123456789 --replace "old text" "new text"

    # Update the page title
    python confluence_write.py --page-id 123456789 --title "New Title"

    # Add a page comment
    python confluence_write.py --page-id 123456789 --comment "Reviewed and approved."

    # Add a label to the page
    python confluence_write.py --page-id 123456789 --add-label my-label

    # Remove a label from the page
    python confluence_write.py --page-id 123456789 --remove-label old-label

    # Combined: update title and append body content
    python confluence_write.py --page-id 123456789 --title "Updated" --append "<p>Note</p>"

Output:
    Confirmation messages to stderr; updated page JSON to stdout.

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

import confluence_utils


# ---------------------------------------------------------------------------
# Page update
# ---------------------------------------------------------------------------
def _get_current_page(base_url, email, token, pat, page_id):
    """Fetch current page to retrieve its version number and body."""
    return confluence_utils.fetch_page(
        base_url, email, token, pat, page_id,
        expand="body.storage,version,space,title"
    )


def update_page(base_url, email, token, pat, page_id, new_title=None, new_body=None):
    """
    Update a Confluence page's title and/or body content.

    The caller must supply the current page's version number (retrieved
    automatically). Confluence requires it to prevent conflicting edits.

    Args:
        page_id:   Numeric page ID
        new_title: New title string (None = keep existing)
        new_body:  New body in XHTML storage format (None = keep existing)

    Returns:
        dict: Updated page object from the API
    """
    page = _get_current_page(base_url, email, token, pat, page_id)

    title = new_title or page.get("title", "")
    body = new_body if new_body is not None else (
        page.get("body", {}).get("storage", {}).get("value", "")
    )
    current_version = page.get("version", {}).get("number", 1)
    space_key = page.get("space", {}).get("key", "")

    data = {
        "id": str(page_id),
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "version": {"number": current_version + 1},
        "body": {
            "storage": {
                "value": body,
                "representation": "storage",
            }
        },
    }

    url = f"{base_url}/rest/api/content/{page_id}"
    headers = confluence_utils.build_headers(email, token, pat)
    result = confluence_utils.make_request(url, method="PUT", headers=headers, data=data)
    print(f"✓ Updated page {page_id}: '{title}' (version {current_version + 1})", file=sys.stderr)
    return result


def append_to_page(base_url, email, token, pat, page_id, html_to_append):
    """
    Append HTML content to the end of an existing page body.

    Args:
        page_id:        Numeric page ID
        html_to_append: Valid XHTML/storage-format snippet to append

    Returns:
        dict: Updated page object
    """
    page = _get_current_page(base_url, email, token, pat, page_id)
    current_body = page.get("body", {}).get("storage", {}).get("value", "")
    new_body = current_body + "\n" + html_to_append
    return update_page(base_url, email, token, pat, page_id, new_body=new_body)


def find_replace_in_page(base_url, email, token, pat, page_id, old_text, new_text, regex=False):
    """
    Find and replace text inside a page body.

    Args:
        page_id:  Numeric page ID
        old_text: Text (or regex pattern) to search for
        new_text: Replacement text
        regex:    If True, treat old_text as a regex pattern

    Returns:
        dict: Updated page object, or None if no match found
    """
    page = _get_current_page(base_url, email, token, pat, page_id)
    current_body = page.get("body", {}).get("storage", {}).get("value", "")

    if regex:
        updated_body, count = re.subn(old_text, new_text, current_body)
    else:
        count = current_body.count(old_text)
        updated_body = current_body.replace(old_text, new_text)

    if count == 0:
        print(
            f"Warning: Text '{old_text}' not found in page {page_id}. No changes made.",
            file=sys.stderr,
        )
        return None

    print(f"✓ Replacing {count} occurrence(s) of '{old_text}' in page {page_id}", file=sys.stderr)
    return update_page(base_url, email, token, pat, page_id, new_body=updated_body)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------
def add_comment(base_url, email, token, pat, page_id, comment_text):
    """
    Add a plain-text comment to a Confluence page.

    Args:
        page_id:      Numeric page ID
        comment_text: Comment body (plain text, stored as XHTML paragraph)

    Returns:
        dict: Created comment object
    """
    url = f"{base_url}/rest/api/content/{page_id}/child/comment"
    headers = confluence_utils.build_headers(email, token, pat)

    # Wrap plain text in a paragraph to satisfy storage format requirements
    safe_text = comment_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    data = {
        "type": "comment",
        "container": {"id": str(page_id), "type": "page"},
        "body": {
            "storage": {
                "value": f"<p>{safe_text}</p>",
                "representation": "storage",
            }
        },
    }

    result = confluence_utils.make_request(url, method="POST", headers=headers, data=data)
    print(f"✓ Added comment to page {page_id} (comment ID: {result.get('id', '')})", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
def add_label(base_url, email, token, pat, page_id, label):
    """Add a label to a Confluence page."""
    url = f"{base_url}/rest/api/content/{page_id}/label"
    headers = confluence_utils.build_headers(email, token, pat)
    data = [{"prefix": "global", "name": label}]
    result = confluence_utils.make_request(url, method="POST", headers=headers, data=data)
    print(f"✓ Added label '{label}' to page {page_id}", file=sys.stderr)
    return result


def remove_label(base_url, email, token, pat, page_id, label):
    """Remove a label from a Confluence page."""
    import urllib.parse
    url = f"{base_url}/rest/api/content/{page_id}/label/{urllib.parse.quote(label)}"
    headers = confluence_utils.build_headers(email, token, pat)
    confluence_utils.make_request(url, method="DELETE", headers=headers)
    print(f"✓ Removed label '{label}' from page {page_id}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser():
    p = argparse.ArgumentParser(
        description="Edit existing Confluence pages and add comments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--page-id", required=True, help="Numeric Confluence page ID (required)")
    body_grp = p.add_mutually_exclusive_group()
    body_grp.add_argument("--body", help="New full page body (XHTML storage format)")
    body_grp.add_argument("--body-file", help="File containing new page body")
    body_grp.add_argument("--append", dest="append_html", help="HTML to append to page body")
    p.add_argument("--replace", nargs=2, metavar=("OLD", "NEW"), help="Find and replace text")
    p.add_argument("--regex", action="store_true", help="Treat --replace OLD as a regex pattern")
    p.add_argument("--title", help="New page title")
    p.add_argument("--comment", help="Comment text to add to the page")
    p.add_argument("--add-label", dest="add_label", help="Label to add to the page")
    p.add_argument("--remove-label", dest="remove_label", help="Label to remove from the page")
    return p


def main():
    parser = _build_parser()
    args = parser.parse_args()

    base_url, email, token, pat = confluence_utils.get_config()
    page_id = args.page_id

    # Full body replacement from file
    if args.body_file:
        if not os.path.isfile(args.body_file):
            print(f"Error: File not found: {args.body_file}", file=sys.stderr)
            sys.exit(1)
        with open(args.body_file, "r", encoding="utf-8") as fh:
            args.body = fh.read()

    # Apply body changes
    if args.body is not None:
        result = update_page(base_url, email, token, pat, page_id,
                              new_title=args.title, new_body=args.body)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.title and not args.append_html and not args.replace:
        result = update_page(base_url, email, token, pat, page_id, new_title=args.title)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.append_html:
        result = append_to_page(base_url, email, token, pat, page_id, args.append_html)
        if args.title:
            result = update_page(base_url, email, token, pat, page_id, new_title=args.title)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.replace:
        old_text, new_text = args.replace
        result = find_replace_in_page(base_url, email, token, pat, page_id,
                                      old_text, new_text, regex=args.regex)
        if result:
            if args.title:
                result = update_page(base_url, email, token, pat, page_id, new_title=args.title)
            print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.comment:
        add_comment(base_url, email, token, pat, page_id, args.comment)

    if args.add_label:
        add_label(base_url, email, token, pat, page_id, args.add_label)

    if args.remove_label:
        remove_label(base_url, email, token, pat, page_id, args.remove_label)

    # Print usage if nothing was done
    if not any([
        args.body, args.body_file, args.append_html,
        args.replace, args.title, args.comment,
        args.add_label, args.remove_label,
    ]):
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
