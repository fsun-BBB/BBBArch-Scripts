# -*- coding: utf-8 -*-
"""Execute the reorg for one stage folder to mirror 1_AUDITED.
Full exact folder mirror + moves/renames + remove obsolete empty folders.
Writes a reversible JSON log. Usage: python execute_reorg.py "2_GUARDIAN PASS"
"""
import os, re, sys, json, shutil

CC = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance"
AUD = os.path.join(CC, "1_AUDITED")
STAGE = sys.argv[1]
ROOT = os.path.join(CC, STAGE)
LOG = os.path.join(r"C:\Users\fsun\AppData\Local\Temp\claude\c--Users-fsun-Documents-GitHub-BIMAutomations\1b4d7225-e9e7-4c8b-9949-dd2b4e6f2555\scratchpad",
                   "reorg_log_%s.json" % re.sub(r"[^A-Za-z0-9]", "_", STAGE))

CODE_RE = re.compile(r"^B_([A-Za-z]{2,5})_(.+)$")
def parse(stem):
    m = CODE_RE.match(stem)
    return (m.group(1).upper(), m.group(2)) if m else (None, stem)
def norm(s): return re.sub(r"[^a-z0-9]", "", s.lower())

# index AUDITED
code2folder, rest_map, exact_full = {}, {}, {}
AUD_FOLDERS = [f for f in os.listdir(AUD) if os.path.isdir(os.path.join(AUD, f))]
for folder in AUD_FOLDERS:
    for f in os.listdir(os.path.join(AUD, folder)):
        if f.lower().endswith(".rfa"):
            stem = os.path.splitext(f)[0]
            code, rest = parse(stem)
            if code:
                code2folder[code] = folder
                rest_map.setdefault(norm(rest), (folder, code))
                exact_full[stem] = (folder, code)

def find_dest(stem):
    code, rest = parse(stem)
    if stem in exact_full: return exact_full[stem]
    nr = norm(rest)
    if nr in rest_map: return rest_map[nr]
    for k, v in rest_map.items():
        if nr.startswith(k) or k.startswith(nr): return v
    if code in code2folder: return (code2folder[code], code)
    return (None, None)

log = {"stage": STAGE, "folders_created": [], "moves": [], "folders_removed": [], "skipped": []}

# 1) full mirror: create every AUDITED subfolder here
for folder in AUD_FOLDERS:
    p = os.path.join(ROOT, folder)
    if not os.path.isdir(p):
        os.makedirs(p)
        log["folders_created"].append(folder)

# 2) moves/renames
for cur in sorted(os.listdir(ROOT)):
    d = os.path.join(ROOT, cur)
    if not os.path.isdir(d):
        continue
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".rfa"):
            continue
        stem = os.path.splitext(f)[0]
        code, rest = parse(stem)
        dfolder, dcode = find_dest(stem)
        if dfolder is None:
            log["skipped"].append("%s/%s (UNMATCHED)" % (cur, f))
            continue
        new_name = ("B_%s_%s" % (dcode, rest) if code else stem) + ".rfa"
        if cur == dfolder and new_name == f:
            continue  # stay
        src = os.path.join(ROOT, cur, f)
        dst = os.path.join(ROOT, dfolder, new_name)
        if os.path.exists(dst):
            log["skipped"].append("%s/%s -> %s/%s (TARGET EXISTS)" % (cur, f, dfolder, new_name))
            continue
        shutil.move(src, dst)
        log["moves"].append({"from": "%s/%s" % (cur, f), "to": "%s/%s" % (dfolder, new_name)})

# 3) remove obsolete folders (not in AUDITED) if now empty
aud_set = set(AUD_FOLDERS)
for cur in sorted(os.listdir(ROOT)):
    d = os.path.join(ROOT, cur)
    if os.path.isdir(d) and cur not in aud_set:
        if not os.listdir(d):
            os.rmdir(d)
            log["folders_removed"].append(cur)
        else:
            log["skipped"].append("folder '%s' NOT removed (not empty): %s" % (cur, os.listdir(d)))

with open(LOG, "w") as fh:
    json.dump(log, fh, indent=2)

print("STAGE:", STAGE)
print("folders created:", len(log["folders_created"]))
print("files moved/renamed:", len(log["moves"]))
for m in log["moves"]:
    print("   ", m["from"], "->", m["to"])
print("obsolete folders removed:", log["folders_removed"])
if log["skipped"]:
    print("SKIPPED/FLAGGED:")
    for s in log["skipped"]:
        print("   ", s)
print("log written:", LOG)
