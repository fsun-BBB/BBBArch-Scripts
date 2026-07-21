# -*- coding: utf-8 -*-
"""Create rows in the 'Revit Families' Notion DB for the .rfa files added to
1_AUDITED_TYLER today, skipping any Family Name already present."""
import os, json, datetime, urllib.request, urllib.error
from pathlib import PureWindowsPath

TOKEN = open(r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt").read().strip()
BASE = "https://api.notion.com/v1"; V = "2022-06-28"
RF = "e561580beff2432395b0ef2db491dd6f"
DIR = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\1_AUDITED_TYLER"
TODAY = "2026-07-20"


def req(m, u, p=None):
    data = json.dumps(p).encode() if p is not None else None
    r = urllib.request.Request(u, data=data, method=m, headers={
        "Authorization": "Bearer %s" % TOKEN, "Notion-Version": V, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as x:
            return json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        raise Exception("HTTP %s: %s" % (e.code, e.read().decode()[:300]))


files = []
for root, _, fs in os.walk(DIR):
    for f in fs:
        if f.lower().endswith(".rfa"):
            p = os.path.join(root, f)
            if datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d") == TODAY:
                files.append((os.path.splitext(f)[0], os.path.basename(root),
                              int(round(os.path.getsize(p) / 1024.0)),
                              PureWindowsPath(p).as_posix()))

existing = set(); cur = None
while True:
    pl = {"page_size": 100}
    if cur:
        pl["start_cursor"] = cur
    d = req("POST", "%s/databases/%s/query" % (BASE, RF), pl)
    for pg in d["results"]:
        ta = pg["properties"].get("Family Name", {}).get("title", [])
        if ta:
            existing.add(ta[0]["plain_text"])
    if not d.get("has_more"):
        break
    cur = d["next_cursor"]

created = skipped = failed = 0
for name, cat, kb, path in sorted(files):
    if name in existing:
        skipped += 1
        continue
    props = {
        "Family Name": {"title": [{"text": {"content": name}}]},
        "Category": {"select": {"name": cat}},
        "File Size": {"rich_text": [{"text": {"content": "%d KB" % kb}}]},
        "Audited File Location": {"rich_text": [{"text": {"content": path}}]},
        "Date Loaded": {"date": {"start": TODAY}},
    }
    try:
        req("POST", "%s/pages" % BASE, {"parent": {"database_id": RF}, "properties": props})
        created += 1
        print("  + created:", name)
    except Exception as e:
        failed += 1
        print("  FAILED:", name, str(e)[:200])

print("Revit Families -> created=%d skipped(existing)=%d failed=%d (of %d today files)" % (
    created, skipped, failed, len(files)))
