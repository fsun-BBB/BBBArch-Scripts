# -*- coding: utf-8 -*-
"""Revert File Size to KB (rename column + update values), delete old table."""
import json, urllib.request, urllib.error

TOKEN_PATH = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt"
MANIFEST = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\0_HOLDING_TYLER\_kitchen_audit_manifest.json"
DB = "3a3d917d-ca75-81f7-8e23-f779ce6fe15f"
OLD_TABLE = "3a3d917d-ca75-80ef-81d7-f795b4adf42f"
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


# 1. Find current size column name, rename it to "File Size (KB)"
schema = req("GET", "%s/databases/%s" % (BASE, DB))["properties"]
size_col = next(n for n in schema if "size" in n.lower())
print("current size column:", size_col)
if size_col != "File Size (KB)":
    req("PATCH", "%s/databases/%s" % (BASE, DB),
        {"properties": {size_col: {"name": "File Size (KB)"}}})
    print("renamed -> File Size (KB)")

# 2. Update every row's number to the KB value (matched by title)
manifest = {it["family_name"]: it.get("file_size_kb") for it in json.load(open(MANIFEST, encoding="utf-8"))}
rows, cursor = [], None
while True:
    payload = {"page_size": 100}
    if cursor:
        payload["start_cursor"] = cursor
    d = req("POST", "%s/databases/%s/query" % (BASE, DB), payload)
    rows += d["results"]
    if not d.get("has_more"):
        break
    cursor = d["next_cursor"]
updated = 0
for p in rows:
    ta = p["properties"].get("Family Name", {}).get("title", [])
    if not ta:
        continue
    name = ta[0]["plain_text"]
    if name in manifest:
        req("PATCH", "%s/pages/%s" % (BASE, p["id"]),
            {"properties": {"File Size (KB)": {"number": manifest[name]}}})
        updated += 1
print("rows updated to KB:", updated)

# 3. Delete the old simple table block entirely
req("DELETE", "%s/blocks/%s" % (BASE, OLD_TABLE))
print("old simple table deleted")
