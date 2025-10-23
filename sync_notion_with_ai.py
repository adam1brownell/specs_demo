import json
import os
import re
import requests
from openai import OpenAI

# Environment variables
NOTION_API_KEY = os.environ["NOTION_API_KEY"]
TRM_OPEN_AI_KEY = os.environ["TRM_OPEN_AI_KEY"]
EVENT_PATH = os.environ["GITHUB_EVENT_PATH"]
PR_DATABASE_ID = os.environ.get("NOTION_PR_DATABASE_ID")  # Optional: for tracking PRs

# API setup
BASE = "https://api.notion.com/v1"
NOTION_HDRS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

openai_client = OpenAI(api_key=TRM_OPEN_AI_KEY)

PAGE_ID_RE = re.compile(r"(?:notion\.so|notion\.site)/[^\s#?]*?([0-9a-fA-F]{32})")

# Load prefix-to-page mapping from config file
def load_page_mapping():
    with open("page_mapping.json", "r") as f:
        return json.load(f)


def load_pr():
    """Load PR information from GitHub event."""
    with open(EVENT_PATH, "r") as f:
        ev = json.load(f)
    pr = ev["pull_request"]
    return {
        "title": pr["title"],
        "body": pr.get("body") or "",
        "url": pr["html_url"],
        "number": pr["number"],
        "repo": ev["repository"]["full_name"],
        "author": pr["user"]["login"],
        "branch": pr["head"]["ref"],
        "created_at": pr["created_at"],
        "updated_at": pr["updated_at"],
    }


def extract_prefix_from_branch(branch: str) -> str:
    """
    Extract prefix from branch name.
    Examples:
      - "feat/hello_world" -> "feat"
      - "bug/fix-login" -> "bug"
      - "main" -> None
    """
    # Match pattern: prefix/anything
    match = re.match(r"^([a-zA-Z0-9_-]+)/", branch)
    if match:
        return match.group(1).lower()
    return None


def get_page_id_for_prefix(prefix: str, mapping: dict) -> str:
    """Get the Notion page ID for a given prefix, or use default."""
    if prefix and prefix in mapping:
        return mapping[prefix]
    elif "default" in mapping:
        print(f"Using default page for prefix: {prefix}")
        return mapping["default"]
    else:
        raise ValueError(
            f"No mapping found for prefix '{prefix}' and no default page configured."
        )


def format_page_id(page_id: str) -> str:
    """
    Format page ID to Notion's expected format (8-4-4-4-12).
    If already formatted, return as is.
    """
    # Remove any existing hyphens
    clean_id = page_id.replace("-", "").lower()
    if len(clean_id) != 32:
        raise ValueError(f"Invalid page ID length: {page_id}")
    return f"{clean_id[0:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:32]}"


def get_notion_page_content(page_id: str) -> str:
    """
    Retrieve all block content from a Notion page.
    Returns the content as formatted text.
    """
    blocks = []
    has_more = True
    start_cursor = None

    while has_more:
        url = f"{BASE}/blocks/{page_id}/children"
        params = {"page_size": 100}
        if start_cursor:
            params["start_cursor"] = start_cursor

        r = requests.get(url, headers=NOTION_HDRS, params=params)
        r.raise_for_status()
        data = r.json()

        blocks.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    # Convert blocks to text
    content_parts = []
    for block in blocks:
        block_type = block.get("type")
        if not block_type:
            continue

        block_data = block.get(block_type, {})
        rich_text = block_data.get("rich_text", [])
        
        if rich_text:
            text = "".join([rt.get("plain_text", "") for rt in rich_text])
            if block_type == "heading_1":
                content_parts.append(f"# {text}")
            elif block_type == "heading_2":
                content_parts.append(f"## {text}")
            elif block_type == "heading_3":
                content_parts.append(f"### {text}")
            elif block_type == "bulleted_list_item":
                content_parts.append(f"• {text}")
            elif block_type == "numbered_list_item":
                content_parts.append(f"1. {text}")
            else:
                content_parts.append(text)

    return "\n".join(content_parts)


def synthesize_with_openai(existing_content: str, pr_info: dict) -> str:
    """
    Use OpenAI to synthesize the existing Notion page content with the PR body.
    Returns the synthesized content in markdown format.
    """
    prompt = f"""You are helping to update a technical specification document in Notion based on a GitHub Pull Request.

EXISTING NOTION PAGE CONTENT:
{existing_content if existing_content.strip() else "(Page is currently empty)"}

PULL REQUEST INFORMATION:
- Title: {pr_info['title']}
- Branch: {pr_info['branch']}
- Author: {pr_info['author']}
- PR #{pr_info['number']}: {pr_info['url']}

PR DESCRIPTION:
{pr_info['body'] if pr_info['body'].strip() else "(No description provided)"}

TASK:
Synthesize and update the Notion page content by intelligently merging the PR information with the existing content. 

Guidelines:
Integrate the PR updates appropriately:
   - Update relevant sections if the PR modifies existing components
   - Add new sections for new components
   - Maintain the overall document structure and flow
3. Include a "Recent Updates" or "Change Log" section that mentions this PR
4. Use clear markdown formatting with proper headings, lists, and emphasis
5. Be concise but comprehensive
6. Don't duplicate information unnecessarily
7. Link to the PR in the main body of the page if it would provide useful context

Return ONLY the updated page content in Notionmarkdown format"""

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are a technical documentation assistant that helps maintain specification documents.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=4000,
    )

    return response.choices[0].message.content


def markdown_to_notion_blocks(markdown: str) -> list:
    """
    Convert markdown text to Notion block format.
    This is a simplified converter - you may want to enhance it for complex markdown.
    """
    blocks = []
    lines = markdown.split("\n")
    
    for line in lines:
        line = line.rstrip()
        
        if not line:
            continue
            
        # Heading 1
        if line.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                }
            })
        # Heading 2
        elif line.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": line[3:]}}]
                }
            })
        # Heading 3
        elif line.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": line[4:]}}]
                }
            })
        # Bulleted list
        elif line.startswith("- ") or line.startswith("• "):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                }
            })
        # Numbered list
        elif re.match(r"^\d+\.\s", line):
            content = re.sub(r"^\d+\.\s", "", line)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            })
        # Regular paragraph
        else:
            # Handle bold **text** and italic *text* (simplified)
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line}}]
                }
            })
    
    return blocks


def delete_all_blocks(page_id: str):
    """Delete all existing blocks from a Notion page."""
    # Get all blocks
    r = requests.get(f"{BASE}/blocks/{page_id}/children", headers=NOTION_HDRS)
    r.raise_for_status()
    blocks = r.json().get("results", [])
    
    # Delete each block
    for block in blocks:
        block_id = block["id"]
        requests.delete(f"{BASE}/blocks/{block_id}", headers=NOTION_HDRS)


def update_notion_page(page_id: str, new_blocks: list):
    """
    Replace the content of a Notion page with new blocks.
    """
    # Delete existing content
    print(f"Clearing existing content from page {page_id}...")
    delete_all_blocks(page_id)
    
    # Add new content in batches (Notion has a 100 block limit per request)
    print(f"Adding {len(new_blocks)} new blocks...")
    batch_size = 100
    for i in range(0, len(new_blocks), batch_size):
        batch = new_blocks[i:i + batch_size]
        r = requests.patch(
            f"{BASE}/blocks/{page_id}/children",
            headers=NOTION_HDRS,
            json={"children": batch}
        )
        r.raise_for_status()
    
    print("✅ Notion page updated successfully!")


def add_pr_to_database(database_id: str, pr_info: dict, prefix: str):
    """
    Add a new row to the Notion database tracking all PRs.
    
    The database should have these properties:
    - Title (title)
    - Author (rich_text)
    - Date (date)
    - Prefix (select or rich_text)
    - Link (url)
    """
    # Parse the date from ISO format
    created_date = pr_info["created_at"].split("T")[0]  # Get just the date part (YYYY-MM-DD)
    
    properties = {
        "Title": {
            "title": [
                {
                    "type": "text",
                    "text": {"content": pr_info["title"]}
                }
            ]
        },
        "Author": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": pr_info["author"]}
                }
            ]
        },
        "Date": {
            "date": {
                "start": created_date
            }
        },
        "Prefix": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": prefix or "none"}
                }
            ]
        },
        "Link": {
            "url": pr_info["url"]
        }
    }
    
    payload = {
        "parent": {"database_id": database_id},
        "properties": properties
    }
    
    r = requests.post(f"{BASE}/pages", headers=NOTION_HDRS, json=payload)
    r.raise_for_status()
    
    print(f"✅ Added PR to database: {pr_info['title']}")
    return r.json()["id"]


def check_pr_exists_in_database(database_id: str, pr_url: str) -> bool:
    """
    Check if a PR already exists in the database by URL.
    Returns True if it exists, False otherwise.
    """
    payload = {
        "filter": {
            "property": "Link",
            "url": {"equals": pr_url}
        },
        "page_size": 1
    }
    
    r = requests.post(f"{BASE}/databases/{database_id}/query", headers=NOTION_HDRS, json=payload)
    r.raise_for_status()
    
    results = r.json().get("results", [])
    return len(results) > 0


def main():
    print("Starting Notion sync with AI synthesis...")
    
    # Load configuration
    page_mapping = load_page_mapping()
    print(f"Loaded page mapping with {len(page_mapping)} entries")
    
    # Load PR information
    pr_info = load_pr()
    print(f"Processing PR #{pr_info['number']}: {pr_info['title']}")
    print(f"Branch: {pr_info['branch']}")
    
    # Extract prefix from branch name and get target page ID
    prefix = extract_prefix_from_branch(pr_info['branch'])
    print(f"Extracted prefix from branch: {prefix or '(none)'}")
    
    page_id = get_page_id_for_prefix(prefix, page_mapping)
    page_id = format_page_id(page_id)
    print(f"Target Notion page: {page_id}")
    
    # Get existing page content
    print("Fetching existing Notion page content...")
    existing_content = get_notion_page_content(page_id)
    print(f"Retrieved {len(existing_content)} characters of existing content")
    
    # Synthesize with OpenAI
    print("Synthesizing content with OpenAI...")
    synthesized_content = synthesize_with_openai(existing_content, pr_info)
    print(f"Generated {len(synthesized_content)} characters of new content")
    
    # Convert to Notion blocks
    print("Converting markdown to Notion blocks...")
    new_blocks = markdown_to_notion_blocks(synthesized_content)
    
    # Update Notion page
    update_notion_page(page_id, new_blocks)
    
    # Add PR to tracking database (if configured)
    if PR_DATABASE_ID:
        print("Checking PR tracking database...")
        if check_pr_exists_in_database(PR_DATABASE_ID, pr_info["url"]):
            print(f"ℹ️  PR #{pr_info['number']} already exists in database, skipping...")
        else:
            add_pr_to_database(PR_DATABASE_ID, pr_info, prefix)
    else:
        print("ℹ️  No PR database configured (NOTION_PR_DATABASE_ID not set)")
    
    print(f"🎉 Successfully updated Notion page for PR #{pr_info['number']}")


if __name__ == "__main__":
    main()

