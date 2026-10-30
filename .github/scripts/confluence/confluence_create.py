"""
Confluence Create - Create new Confluence pages.

Supports creating a page under a parent page or directly under a space homepage.
Optionally add labels and set a page template.

Usage:
    # Create a page under a parent page
    python confluence_create.py \\
        --space DEV \\
        --parent-id 123456789 \\
        --title "My New Page" \\
        --body "<p>Initial content.</p>"

    # Create a page under a parent page with body from a file
    python confluence_create.py \\
        --space DEV \\
        --parent-id 123456789 \\
        --title "My New Page" \\
        --body-file content.html

    # Create under root of a space (no parent)
    python confluence_create.py \\
        --space DEV \\
        --title "Top-level Page" \\
        --body "<p>Hello world</p>"

    # Create with labels
    python confluence_create.py \\
        --space DEV \\
        --parent-id 123456789 \\
        --title "Labelled Page" \\
        --body "<p>Content</p>" \\
        --labels release draft

Output:
    Created page JSON to stdout. Confirmation messages to stderr.

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

import confluence_utils


# ---------------------------------------------------------------------------
# Create operations
# ---------------------------------------------------------------------------
def create_page(
    base_url,
    email,
    token,
    pat,
    space_key,
    title,
    body_html,
    parent_id=None,
    labels=None,
):
    """
    Create a new Confluence page.

    Args:
        space_key:  Target space key (e.g. 'DEV')
        title:      Page title
        body_html:  Page body in XHTML storage format
        parent_id:  Numeric ID of the parent page (None = space homepage)
        labels:     Optional list of label strings to attach

    Returns:
        dict: Newly created page object from the API
    """
    # If no parent given, use the space homepage
    if not parent_id:
        space_info = confluence_utils.get_space_homepage(base_url, email, token, pat, space_key)
        homepage = space_info.get("homepage", {})
        parent_id = homepage.get("id")
        if not parent_id:
            print(
                f"Error: Could not find homepage for space '{space_key}'. "
                "Provide an explicit --parent-id.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(
            f"  Using space homepage (ID: {parent_id}) as parent.",
            file=sys.stderr,
        )

    data = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "ancestors": [{"id": str(parent_id)}],
        "body": {
            "storage": {
                "value": body_html,
                "representation": "storage",
            }
        },
    }

    url = f"{base_url}/rest/api/content"
    headers = confluence_utils.build_headers(email, token, pat)
    result = confluence_utils.make_request(url, method="POST", headers=headers, data=data)

    new_id = result.get("id", "")
    page_url = f"{base_url}/pages/viewpage.action?pageId={new_id}"
    print(
        f"✓ Created page '{title}' in space '{space_key}' "
        f"(ID: {new_id}) — {page_url}",
        file=sys.stderr,
    )

    # Attach labels if requested
    if labels:
        label_url = f"{base_url}/rest/api/content/{new_id}/label"
        label_data = [{"prefix": "global", "name": lbl} for lbl in labels]
        confluence_utils.make_request(
            label_url, method="POST", headers=headers, data=label_data
        )
        print(f"  Labels added: {', '.join(labels)}", file=sys.stderr)

    return result


def create_page_from_template(
    base_url,
    email,
    token,
    pat,
    space_key,
    title,
    template_id,
    parent_id=None,
):
    """
    Create a new page by copying the body of an existing template page.

    Args:
        space_key:   Target space key
        title:       New page title
        template_id: Numeric ID of the page to use as a template
        parent_id:   Optional parent page ID

    Returns:
        dict: Newly created page object
    """
    template_page = confluence_utils.fetch_page(
        base_url, email, token, pat, template_id, expand="body.storage"
    )
    body_html = template_page.get("body", {}).get("storage", {}).get("value", "")
    print(
        f"  Cloning body from template page '{template_page.get('title', template_id)}'.",
        file=sys.stderr,
    )
    return create_page(
        base_url, email, token, pat,
        space_key, title, body_html, parent_id=parent_id
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser():
    p = argparse.ArgumentParser(
        description="Create new Confluence pages.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--space", required=True, help="Confluence space key (e.g. DEV)")
    p.add_argument("--title", required=True, help="Title of the new page")
    p.add_argument("--parent-id", help="Numeric ID of the parent page")

    body_grp = p.add_mutually_exclusive_group()
    body_grp.add_argument(
        "--body", default="",
        help="Page body in XHTML storage format (default: empty page)"
    )
    body_grp.add_argument(
        "--body-file",
        help="Path to an HTML file containing the page body"
    )
    body_grp.add_argument(
        "--template-id",
        help="Page ID to clone as the body template"
    )

    p.add_argument(
        "--labels", nargs="+", metavar="LABEL",
        help="One or more labels to attach to the new page"
    )
    return p


def main():
    parser = _build_parser()
    args = parser.parse_args()

    base_url, email, token, pat = confluence_utils.get_config()

    # Resolve body source
    if args.template_id:
        result = create_page_from_template(
            base_url, email, token, pat,
            args.space,
            args.title,
            args.template_id,
            parent_id=args.parent_id,
        )
    else:
        body_html = args.body
        if args.body_file:
            if not os.path.isfile(args.body_file):
                print(f"Error: File not found: {args.body_file}", file=sys.stderr)
                sys.exit(1)
            with open(args.body_file, "r", encoding="utf-8") as fh:
                body_html = fh.read()

        result = create_page(
            base_url, email, token, pat,
            args.space,
            args.title,
            body_html,
            parent_id=args.parent_id,
            labels=args.labels,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
