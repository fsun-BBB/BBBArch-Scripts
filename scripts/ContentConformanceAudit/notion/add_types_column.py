# -*- coding: utf-8 -*-
"""Add a 'Types' multi_select column to the Kitchen audit DB and backfill it
from the kitchen manifest (matched by Family Name)."""
import json, urllib.request, urllib.error

TOKEN_PATH = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt"
MANIFEST = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\0_HOLDING_TYLER\_kitchen_audit_manifest.json"
DB = "3a3d917d-ca75-81f7-8e23-f779ce6fe15f"
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


def ms(names):
    seen, out = set(), []
    for n in names or []:
        n = (n or "").replace(",", ";").strip()[:100]
        if n and n not in seen:
            seen.add(n)
            out.append({"name": n})
    return out


# 1. add the column if missing
schema = req("GET", "%s/databases/%s" % (BASE, DB))["properties"]
if not any("type" in n.lower() for n in schema):
    req("PATCH", "%s/databases/%s" % (BASE, DB), {"properties": {"Types": {"multi_select": {}}}})
    print("added 'Types' multi_select column")
else:
    print("Types column already present")

# 2. backfill from manifest
types_by_name = {it["family_name"]: it.get("types") or [] for it in json.load(open(MANIFEST, encoding="utf-8"))}
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

filled = 0
for p in rows:
    ta = p["properties"].get("Family Name", {}).get("title", [])
    if not ta:
        continue
    name = ta[0]["plain_text"]
    ts = types_by_name.get(name)
    if ts:
        req("PATCH", "%s/pages/%s" % (BASE, p["id"]), {"properties": {"Types": {"multi_select": ms(ts)}}})
        filled += 1
print("rows backfilled with types:", filled)
