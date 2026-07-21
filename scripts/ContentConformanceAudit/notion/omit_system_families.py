# -*- coding: utf-8 -*-
"""Archive the 5 system/annotation family rows and scrub their names out of
every remaining row's Parent Family / Child Families multi-selects."""
import json, urllib.request, urllib.error

TOKEN_PATH = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt"
DB = "3a3d917d-ca75-81f7-8e23-f779ce6fe15f"
BASE = "https://api.notion.com/v1"
API_VERSION = "2022-06-28"
TOKEN = open(TOKEN_PATH).read().strip()

EXCLUDED = {
    "Section Tail - Upgrade",
    "Outlet Annotation-Label",
    "Symbol - Outlet",
    "Outlet Annotation-Label_Single",
    "ADA Clearance Lines",
}


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

archived = scrubbed = 0
for p in rows:
    ta = p["properties"].get("Family Name", {}).get("title", [])
    if not ta:
        continue
    name = ta[0]["plain_text"]
    if name in EXCLUDED:
        req("PATCH", "%s/pages/%s" % (BASE, p["id"]), {"archived": True})
        archived += 1
        continue
    props = {}
    for col in ("Parent Family", "Child Families"):
        opts = p["properties"].get(col, {}).get("multi_select", [])
        kept = [{"name": o["name"]} for o in opts if o["name"] not in EXCLUDED]
        if len(kept) != len(opts):
            props[col] = {"multi_select": kept}
    if props:
        req("PATCH", "%s/pages/%s" % (BASE, p["id"]), {"properties": props})
        scrubbed += 1

print("archived rows: %d | rows scrubbed of excluded names: %d" % (archived, scrubbed))
