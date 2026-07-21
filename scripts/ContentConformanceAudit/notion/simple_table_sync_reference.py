# -*- coding: utf-8 -*-
"""CPython port of the kitchen table sync logic, for validating against the
real Notion table from this environment (the IronPython module can't run
here). Same header-mapping / cell-building / merge logic as
frank_audit.kitchen_notion_sync so a pass here means the module is sound.

Modes:
  probe   - read table, print header mapping + preview cells for 3 families,
            then append ONE test row and immediately delete it (self-cleaning).
  import  - perform the real upsert of the whole manifest.
"""
import json, sys, urllib.request, urllib.error

TOKEN_PATH = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt"
MANIFEST = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\0_HOLDING_TYLER\_kitchen_audit_manifest.json"
TABLE_BLOCK_ID = "3a3d917d-ca75-80ef-81d7-f795b4adf42f"
BASE = "https://api.notion.com/v1"
API_VERSION = "2022-06-28"
MAX_CELL_CHARS = 2000

TOKEN = open(TOKEN_PATH).read().strip()
REPLACE_ROLES = {"family_name": "family_name", "size": "file_size_kb",
                 "category": "category", "location": "file_path"}
MERGE_ROLES = {"parent": "parent_families", "child": "child_families"}


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


def role_for_header(label):
    h = label.lower()
    for kw, role in [("proposed", "proposed"), ("status", "status"),
                     ("parent", "parent"), ("child", "child"),
                     ("categor", "category"), ("location", "location"),
                     ("size", "size")]:
        if kw in h:
            return role
    if "family" in h and "name" in h:
        return "family_name"
    return None


def cell_text(cell):
    return "".join(rt.get("plain_text", "") for rt in cell).strip()


def _cell(text):
    if not text:
        return []
    if len(text) > MAX_CELL_CHARS:
        text = text[:MAX_CELL_CHARS - 3] + "..."
    return [{"type": "text", "text": {"content": text}}]


def _fmt_size(v):
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else str(f)


def _merge_join(existing_text, new_values):
    have = set(p.strip() for p in existing_text.split(",") if p.strip()) if existing_text else set()
    for v in (new_values or []):
        if v:
            have.add(v)
    return ", ".join(sorted(have))


def get_children(block_id):
    blocks, cursor = [], None
    while True:
        url = "%s/blocks/%s/children?page_size=100" % (BASE, block_id)
        if cursor:
            url += "&start_cursor=%s" % cursor
        d = req("GET", url)
        blocks += d.get("results", [])
        if not d.get("has_more"):
            break
        cursor = d.get("next_cursor")
    return blocks


def read_table():
    blocks = get_children(TABLE_BLOCK_ID)
    rows = [{"id": b["id"], "texts": [cell_text(c) for c in b["table_row"]["cells"]]}
            for b in blocks if b.get("type") == "table_row"]
    header = rows[0]["texts"]
    role_to_index = {}
    for i, label in enumerate(header):
        role = role_for_header(label)
        if role and role not in role_to_index:
            role_to_index[role] = i
    return header, role_to_index, rows[1:]


def build_cells(item, role_to_index, width, existing):
    if existing:
        cells = [_cell(existing["texts"][i]) if i < len(existing["texts"]) else [] for i in range(width)]
    else:
        cells = [[] for _ in range(width)]
    idx_role = {idx: role for role, idx in role_to_index.items()}
    for i in range(width):
        role = idx_role.get(i)
        if role in REPLACE_ROLES:
            key = REPLACE_ROLES[role]
            val = _fmt_size(item.get(key)) if role == "size" else (item.get(key) or "")
            cells[i] = _cell(val)
        elif role in MERGE_ROLES:
            key = MERGE_ROLES[role]
            et = existing["texts"][i] if (existing and i < len(existing["texts"])) else ""
            cells[i] = _cell(_merge_join(et, item.get(key, [])))
    return cells


def preview(cells):
    return [(c[0]["text"]["content"][:40] if c else "") for c in cells]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    header, role_to_index, data_rows = read_table()
    width = len(header)
    print("HEADER:", header)
    print("ROLE->INDEX:", role_to_index)
    print("existing data rows:", len(data_rows), "->", [r["texts"][role_to_index["family_name"]] for r in data_rows])

    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    print("manifest families:", len(manifest))

    if mode == "probe":
        for item in manifest[:3]:
            print("  ", item["family_name"], "=>", preview(build_cells(item, role_to_index, width, None)))
        # self-cleaning write test
        test_cells = [_cell("__PROBE_DELETE_ME__")] + [[] for _ in range(width - 1)]
        res = req("PATCH", "%s/blocks/%s/children" % (BASE, TABLE_BLOCK_ID),
                  {"children": [{"object": "block", "type": "table_row", "table_row": {"cells": test_cells}}]})
        new_id = res["results"][0]["id"]
        print("APPEND ok, test row id:", new_id)
        req("DELETE", "%s/blocks/%s" % (BASE, new_id))
        print("DELETE ok - table left clean. WRITE MECHANISM VALIDATED.")
    elif mode == "import":
        fam_idx = role_to_index["family_name"]
        existing = {}
        for r in data_rows:
            n = r["texts"][fam_idx].strip()
            if n:
                existing[n.lower()] = r
        created = updated = failed = 0
        to_append = []
        for item in manifest:
            name = item["family_name"]
            try:
                ex = existing.get(name.lower())
                cells = build_cells(item, role_to_index, width, ex)
                if ex:
                    req("PATCH", "%s/blocks/%s" % (BASE, ex["id"]), {"table_row": {"cells": cells}})
                    updated += 1
                else:
                    to_append.append(cells)
            except Exception as e:
                failed += 1
                print("FAILED", name, e)
        for s in range(0, len(to_append), 100):
            chunk = to_append[s:s + 100]
            req("PATCH", "%s/blocks/%s/children" % (BASE, TABLE_BLOCK_ID),
                {"children": [{"object": "block", "type": "table_row", "table_row": {"cells": c}} for c in chunk]})
            created += len(chunk)
        print("IMPORT DONE: created=%d updated=%d failed=%d" % (created, updated, failed))


main()
