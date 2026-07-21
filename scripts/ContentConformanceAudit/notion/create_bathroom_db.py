# -*- coding: utf-8 -*-
"""Create the 'Bathroom Nested Family Audit' database (same schema as the
kitchen one, incl. Types) on the same page. Prints its id."""
import json, urllib.request, urllib.error

TOKEN_PATH = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt"
PAGE_ID = "3a3d917dca7580a1b4f7c9f04b0d48c6"
BASE = "https://api.notion.com/v1"
API_VERSION = "2022-06-28"
TOKEN = open(TOKEN_PATH).read().strip()


def req(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer %s" % TOKEN, "Notion-Version": API_VERSION,
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise Exception("HTTP %s: %s" % (e.code, e.read().decode()))


schema = {
    "parent": {"type": "page_id", "page_id": PAGE_ID},
    "is_inline": True,
    "title": [{"type": "text", "text": {"content": "Bathroom Nested Family Audit"}}],
    "properties": {
        "Family Name": {"title": {}},
        "File Size (KB)": {"number": {"format": "number"}},
        "Proposed Name": {"rich_text": {}},
        "Revit Category": {"multi_select": {}},
        "File Location": {"rich_text": {}},
        "Status": {"select": {"options": [
            {"name": "Audited", "color": "blue"},
            {"name": "Guardian Passed", "color": "green"},
            {"name": "Manually Cleaned", "color": "orange"},
        ]}},
        "Parent Family": {"multi_select": {}},
        "Child Families": {"multi_select": {}},
        "Types": {"multi_select": {}},
    },
}
d = req("POST", "%s/databases" % BASE, schema)
print("BATHROOM_DATABASE_ID:", d["id"])
