# -*- coding: utf-8 -*-
"""Create a proper Notion DATABASE (with multi_select / select / number
columns) on the Kitchen Nested Family Audit page, then import the 41
families. Prints the new database id to reuse in the IronPython module.
"""
import json, sys, time, urllib.request, urllib.error

TOKEN_PATH = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt"
MANIFEST = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\0_HOLDING_TYLER\_kitchen_audit_manifest.json"
PAGE_ID = "3a3d917dca7580a1b4f7c9f04b0d48c6"
BASE = "https://api.notion.com/v1"
API_VERSION = "2022-06-28"
TOKEN = open(TOKEN_PATH).read().strip()


def req(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer %s" % TOKEN, "Notion-Version": API_VERSION,
        "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(r) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 429 and attempt < 3:
                time.sleep(1.0 + attempt)
                continue
            raise Exception("HTTP %s: %s" % (e.code, body))


def mb(kb):
    try:
        return round(float(kb) / 1024.0, 2)
    except (TypeError, ValueError):
        return None


def create_db():
    schema = {
        "parent": {"type": "page_id", "page_id": PAGE_ID},
        "is_inline": True,
        "title": [{"type": "text", "text": {"content": "Kitchen Nested Family Audit"}}],
        "properties": {
            "Family Name": {"title": {}},
            "File Size (MB)": {"number": {"format": "number"}},
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
        },
    }
    d = req("POST", "%s/databases" % BASE, schema)
    return d["id"]


def ms(names):
    # de-dupe + drop empties/commas for multi_select option names
    seen, out = set(), []
    for n in names or []:
        n = (n or "").replace(",", ";").strip()
        if n and n not in seen:
            seen.add(n)
            out.append({"name": n})
    return out


def import_rows(db_id, manifest):
    created = failed = 0
    for item in manifest:
        name = item["family_name"]
        props = {
            "Family Name": {"title": [{"text": {"content": name}}]},
            "File Size (MB)": {"number": mb(item.get("file_size_kb"))},
            "Proposed Name": {"rich_text": []},  # pending naming-convention decision
            "Revit Category": {"multi_select": ms([item.get("category")])},
            "File Location": {"rich_text": [{"text": {"content": item.get("file_path", "")}}]},
            "Status": {"select": {"name": "Guardian Passed"}},
            "Parent Family": {"multi_select": ms(item.get("parent_families"))},
            "Child Families": {"multi_select": ms(item.get("child_families"))},
        }
        try:
            req("POST", "%s/pages" % BASE, {"parent": {"database_id": db_id}, "properties": props})
            created += 1
        except Exception as e:
            failed += 1
            print("FAILED", name, str(e)[:300])
    return created, failed


def main():
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    db_id = create_db()
    print("NEW_DATABASE_ID:", db_id)
    created, failed = import_rows(db_id, manifest)
    print("IMPORT DONE: created=%d failed=%d (of %d)" % (created, failed, len(manifest)))


main()
