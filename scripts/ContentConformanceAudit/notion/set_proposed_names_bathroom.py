# -*- coding: utf-8 -*-
"""Set Proposed Name (naming convention) on the Bathroom Nested Family Audit
rows, matched by Family Name."""
import json, urllib.request, urllib.error

TOKEN = open(r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt").read().strip()
BASE = "https://api.notion.com/v1"; V = "2022-06-28"
DB = "3a3d917d-ca75-81ce-b86b-d06386b2e588"


def req(m, u, p=None):
    data = json.dumps(p).encode() if p is not None else None
    r = urllib.request.Request(u, data=data, method=m, headers={
        "Authorization": "Bearer %s" % TOKEN, "Notion-Version": V, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as x:
            return json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        raise Exception("HTTP %s: %s" % (e.code, e.read().decode()[:300]))


PROP = {
    "Resi-Bath - Accessories - Curtain Rod": "B_EQPT_Curtain Rod_Shower",
    "Resi-Bath - Accessories - Med. Cabinet - Double": "B_EQPT_Medicine Cabinet_Double",
    "Resi-Bath - Accessories - Med. Cabinet - Single": "B_EQPT_Medicine Cabinet_Single",
    "Resi-Bath - Accessories - Robe Hook": "B_EQPT_Robe Hook",
    "Resi-Bath - Accessories - TP Holder": "B_EQPT_Toilet Paper Holder",
    "Resi-Bath - Accessories - Towel Bar": "B_EQPT_Towel Bar",
    "Resi-Bath - Fixture - Shower Base": "B_PLMB_Shower_Base",
    "Resi-Bath - Fixture - Shower Diverter": "B_PLMB_Diverter_Shower",
    "Resi-Bath - Fixture - Shower Handshower": "B_PLMB_Handshower_Shower",
    "Resi-Bath - Fixture - Shower Showerhead": "B_PLMB_Showerhead_Shower",
    "Resi-Bath - Fixture - Sink": "B_PLMB_Sink_Bath",
    "Resi-Bath - Fixture - Sink Faucet": "B_PLMB_Faucet_Bath Sink",
    "Resi-Bath - Fixture - Toilet": "B_PLMB_Toilet_Residential",
    "Resi-Bath - Fixture - Tub": "B_PLMB_Tub_Residential",
    "Resi-Bath - Fixture - Tub Diverter": "B_PLMB_Diverter_Tub",
    "Resi-Bath - Fixture - Tub Faucet": "B_PLMB_Faucet_Tub",
    "Resi-Bath - Fixture - Tub Handshower": "B_PLMB_Handshower_Tub",
    "Resi-Bath - Fixture - Tub Showerhead": "B_PLMB_Showerhead_Tub",
    "Resi-Bath - Fixtures - Handshower Bar": "B_PLMB_Handshower Bar_Bath",
    "Resi-Bath - Fixtures - HandshowerFixture": "B_PLMB_Handshower_Fixture",
    "Resi-Bath - Grab Bars - Bathtub": "B_EQPT_Grab Bar_Bathtub",
    "Resi-Bath - Grab Bars - Shower": "B_EQPT_Grab Bar_Shower",
    "Resi-Bath - Grab Bars - Toilet": "B_EQPT_Grab Bar_Toilet",
    "X_ Grab Bar - Single - Parametric": "B_Grab Bar - Single - Parametric",
    "_Res-Bathroom - Type 1": "B_UNIT_Bathroom Assembly_Type01",
    "_Res-Bathroom - Type 2": "B_UNIT_Bathroom Assembly_Type02",
    "_Res-Bathroom - Type 3": "B_UNIT_Bathroom Assembly_Type03",
    "_Res-Bathroom - Type 4": "B_UNIT_Bathroom Assembly_Type04",
    "_Res-Bathroom - Type 5": "B_UNIT_Bathroom Assembly_Type05",
    "_Resi-Bath - Bathtub": "B_PLMB_Bathtub_Residential",
    "_Resi-Bath - Fixtures - Shower Drain": "B_PLMB_Drain_Shower",
    "_Resi-Bath - Fixtures - Sink w Faucet": "B_PLMB_Sink_Bath With Faucet",
    "_Resi-Bath - Shower": "B_PLMB_Shower_Residential",
    "_Resi-Bath - Vanity": "B_CASE_Vanity_Single",
    "_Resi-Bath - Vanity_Double": "B_CASE_Vanity_Double",
}

rows, cur = [], None
while True:
    pl = {"page_size": 100}
    if cur:
        pl["start_cursor"] = cur
    d = req("POST", "%s/databases/%s/query" % (BASE, DB), pl)
    rows += d["results"]
    if not d.get("has_more"):
        break
    cur = d["next_cursor"]

done = skipped = 0
for p in rows:
    ta = p["properties"].get("Family Name", {}).get("title", [])
    if not ta:
        continue
    name = ta[0]["plain_text"]
    prop = PROP.get(name)
    if not prop:
        skipped += 1
        print("  (left blank):", name)
        continue
    req("PATCH", "%s/pages/%s" % (BASE, p["id"]),
        {"properties": {"Proposed Name": {"rich_text": [{"text": {"content": prop}}]}}})
    done += 1
print("Bathroom proposed names set: %d, left blank: %d" % (done, skipped))
