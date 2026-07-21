# -*- coding: utf-8 -*-
"""Final file renames + duplicate quarantine, then update the 3 Notion
Proposed Names in the Bathroom DB."""
import os, shutil, json, urllib.request, urllib.error

BASE_DIR = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\1_AUDITED"
SPEC = os.path.join(BASE_DIR, "Specialty Equipment")
PLMB = os.path.join(BASE_DIR, "Plumbing Fixtures")
TOKEN = open(r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt").read().strip()
API = "https://api.notion.com/v1"; V = "2022-06-28"
BATH_DB = "3a3d917d-ca75-81ce-b86b-d06386b2e588"


def rename(folder, old, new):
    src, dst = os.path.join(folder, old + ".rfa"), os.path.join(folder, new + ".rfa")
    if not os.path.exists(src):
        print("  MISSING:", old); return
    if os.path.exists(dst):
        print("  SKIP (exists):", new); return
    os.rename(src, dst); print("  %s -> %s" % (old, new))


def quarantine(folder, name, keep):
    if not os.path.exists(os.path.join(folder, keep + ".rfa")):
        print("  SKIP quarantine - keeper missing:", keep); return
    src = os.path.join(folder, name + ".rfa")
    if not os.path.exists(src):
        print("  MISSING dup:", name); return
    q = os.path.join(folder, "_DUPLICATES")
    if not os.path.isdir(q): os.makedirs(q)
    shutil.move(src, os.path.join(q, name + ".rfa"))
    print("  quarantined dup:", name, "(kept", keep + ")")


print("=== file renames ===")
rename(PLMB, "Parts_ Resi-Bath - Fixtures - Sink Faucet 1", "B_EQPT_Sink Faucet 1")
rename(PLMB, "Parts_ Resi-Bath - Fixtures - Sink Faucet 2", "B_EQPT_Sink Faucet 2")
rename(SPEC, "B_Grab Bar - Single - Parametric", "B_EQPT_Grab Bar - Single - Parametric")
print("=== duplicate ===")
quarantine(PLMB, "B_PLMB_Sink Faucet", keep="B_PLMB_Sink")


def req(m, u, p=None):
    data = json.dumps(p).encode() if p is not None else None
    r = urllib.request.Request(u, data=data, method=m, headers={
        "Authorization": "Bearer %s" % TOKEN, "Notion-Version": V, "Content-Type": "application/json"})
    with urllib.request.urlopen(r) as x:
        return json.loads(x.read().decode())


PROP = {
    "Parts_ Resi-Bath - Fixtures - Sink Faucet 1": "B_EQPT_Sink Faucet 1",
    "Parts_ Resi-Bath - Fixtures - Sink Faucet 2": "B_EQPT_Sink Faucet 2",
    "X_ Grab Bar - Single - Parametric": "B_EQPT_Grab Bar - Single - Parametric",
}
print("=== notion proposed names ===")
rows, cur = [], None
while True:
    pl = {"page_size": 100}
    if cur: pl["start_cursor"] = cur
    d = req("POST", "%s/databases/%s/query" % (API, BATH_DB), pl)
    rows += d["results"]
    if not d.get("has_more"): break
    cur = d["next_cursor"]
for p in rows:
    ta = p["properties"].get("Family Name", {}).get("title", [])
    if ta and ta[0]["plain_text"] in PROP:
        nm = ta[0]["plain_text"]
        req("PATCH", "%s/pages/%s" % (API, p["id"]),
            {"properties": {"Proposed Name": {"rich_text": [{"text": {"content": PROP[nm]}}]}}})
        print("  set:", nm, "->", PROP[nm])
