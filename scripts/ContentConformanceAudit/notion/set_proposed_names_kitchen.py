# -*- coding: utf-8 -*-
"""Write best-effort Proposed Name (per BBB naming convention) to each row.
Convention: B_<CAT>_<Subtype>_<Descriptor>[_<Size>], 4-letter uppercase CAT,
Title-Case segments (spaces allowed within a segment), single _ between.
"""
import json, urllib.request, urllib.error

TOKEN_PATH = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt"
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


PROPOSED = {
    "Section Tail - Upgrade": "B_ANNO_Section Tail_Upgrade",
    "Kitchens - Fixture - Sink": "B_PLMB_Sink_Kitchen",
    "Kitchens_ Side Panel - Base": "B_CASE_Side Panel_Base",
    "Kitchens_ Wall Shelf": "B_CASE_Shelf_Wall",
    "Kitchens_ Resi Overhead Cabinet": "B_CASE_Cabinet_Resi Overhead",
    "Casework_ Cabinet Front": "B_CASE_Cabinet_Front",
    "Casework_ Cabinet Door": "B_CASE_Cabinet_Door",
    "Kitchens_ Resi Overhead Cabinet - Corner": "B_CASE_Cabinet_Resi Overhead Corner",
    "Kitchens_ Resi Base Cabinet - Corner": "B_CASE_Cabinet_Resi Base Corner",
    "Kitchens_ Side Panel - Overhead": "B_CASE_Side Panel_Overhead",
    "Kitchens_ Resi Pantry Cabinet": "B_CASE_Cabinet_Resi Pantry",
    "EL_Outlet - Single Appliance - Unhosted": "B_ELEC_Outlet_Single Appliance",
    "Outlet Annotation-Label": "B_ANNO_Outlet_Label",
    "Symbol - Outlet": "B_ANNO_Outlet_Symbol",
    "Outlet Annotation-Label_Single": "B_ANNO_Outlet_Label Single",
    "ADA Clearance Lines": "B_ANNO_Clearance_ADA",
    "_Kitchens - Appliance - Range - 24in": "B_EQPT_Range_Kitchen_24in",
    "Kitchens - Appliance - Hood": "B_EQPT_Hood_Kitchen",
    "Kitchens - Appliance - Hood Duct": "B_EQPT_Duct_Hood",
    "_Kitchens - Appliance - Refrigerator": "B_EQPT_Refrigerator_Kitchen",
    "_Kitchens - Appliance - Dishwasher": "B_EQPT_Dishwasher_Kitchen",
    "Kitchens - Appliance - Microwave - 24in - Wall Mounted": "B_EQPT_Microwave_Wall Mounted_24in",
    "Kitchens_ Resi Base Cabinet": "B_CASE_Cabinet_Resi Base",
    "_Kitchens - Appliance - Range - 30in": "B_EQPT_Range_Kitchen_30in",
    "Kitchens - Fixture - Faucet": "B_PLMB_Faucet_Kitchen",
    "Kitchens - Fixtures - Sink w Faucet": "B_PLMB_Sink_With Faucet",
    "Kitchens - Appliance - Microwave - 30in - Wall Mounted": "B_EQPT_Microwave_Wall Mounted_30in",
}
for i in range(1, 15):
    PROPOSED["B_UNIT_KitchenAssembly_Unit%02d" % i] = "B_UNIT_Kitchen Assembly_Unit%02d" % i

# query all rows, set Proposed Name by title match
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

done = missing = 0
for p in rows:
    ta = p["properties"].get("Family Name", {}).get("title", [])
    if not ta:
        continue
    name = ta[0]["plain_text"]
    prop = PROPOSED.get(name)
    if not prop:
        missing += 1
        print("  no proposal for:", name)
        continue
    req("PATCH", "%s/pages/%s" % (BASE, p["id"]),
        {"properties": {"Proposed Name": {"rich_text": [{"text": {"content": prop}}]}}})
    done += 1
print("proposed names written: %d, unmatched: %d" % (done, missing))
