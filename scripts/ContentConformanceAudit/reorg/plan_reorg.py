# -*- coding: utf-8 -*-
"""DRY RUN: build the move/rename plan for 2_GUARDIAN PASS and 3_CLEANED to
mirror 1_AUDITED. Matches each file to AUDITED by normalized family
descriptor (ignoring the current 4-letter code). No filesystem changes."""
import os, re, collections

CC = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance"
AUD = os.path.join(CC, "1_AUDITED")

CODE_RE = re.compile(r"^B_([A-Za-z]{2,5})_(.+)$")


def parse(stem):
    m = CODE_RE.match(stem)
    if m:
        return m.group(1).upper(), m.group(2)
    return None, stem


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


# --- index AUDITED ---
folder2code = {}
code2folder = {}
rest_map = {}        # norm(rest) -> (folder, code)
exact_full = {}      # "B_CODE_rest" stem -> (folder, code)
for folder in os.listdir(AUD):
    d = os.path.join(AUD, folder)
    if not os.path.isdir(d):
        continue
    for f in os.listdir(d):
        if not f.lower().endswith(".rfa"):
            continue
        stem = os.path.splitext(f)[0]
        code, rest = parse(stem)
        if code:
            folder2code[folder] = code
            code2folder[code] = folder
            rest_map.setdefault(norm(rest), (folder, code))
            exact_full[stem] = (folder, code)
AUD_FOLDERS = sorted([f for f in os.listdir(AUD) if os.path.isdir(os.path.join(AUD, f))])


def find_dest(stem):
    code, rest = parse(stem)
    # 1) exact full-name match already in AUDITED -> keep that folder/code
    if stem in exact_full:
        return exact_full[stem] + ("exact-full",)
    nr = norm(rest)
    if nr in rest_map:
        return rest_map[nr] + ("exact",)
    # prefix fallback (e.g. "Robe Hook_02" -> "Robe Hook")
    for k, v in rest_map.items():
        if nr.startswith(k) or k.startswith(nr):
            return v + ("fuzzy:%s" % k,)
    # code fallback: current code maps to an AUDITED folder
    if code in code2folder:
        return (code2folder[code], code, "by-code")
    return (None, None, "UNMATCHED")


def plan_for(stage):
    root = os.path.join(CC, stage)
    print("=" * 70)
    print(stage)
    print("=" * 70)
    actions = []
    stays = 0
    for cur_folder in sorted(os.listdir(root)):
        d = os.path.join(root, cur_folder)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".rfa"):
                continue
            stem = os.path.splitext(f)[0]
            code, rest = parse(stem)
            dfolder, dcode, how = find_dest(stem)
            if dfolder is None:
                actions.append(("UNMATCHED", cur_folder, f, "?", "?", how))
                continue
            new_stem = "B_%s_%s" % (dcode, rest) if code else stem
            new_name = new_stem + ".rfa"
            if cur_folder == dfolder and new_name == f:
                stays += 1
            else:
                kind = "MOVE" if cur_folder != dfolder else "RENAME"
                actions.append((kind, cur_folder, f, dfolder, new_name, how))
    for kind in ("MOVE", "RENAME", "UNMATCHED"):
        for a in [x for x in actions if x[0] == kind]:
            print("  [%s] %s/%s" % (a[0], a[1], a[2]))
            print("        -> %s/%s   (%s)" % (a[3], a[4], a[5]))
    print("  STAY (already correct): %d files" % stays)
    # folder plan
    cur_folders = set(x for x in os.listdir(root) if os.path.isdir(os.path.join(root, x)))
    missing = [f for f in AUD_FOLDERS if f not in cur_folders]
    obsolete = [f for f in cur_folders if f not in AUD_FOLDERS]
    print("  FOLDERS to CREATE (in AUDITED, missing here):", missing)
    print("  FOLDERS obsolete (not in AUDITED) - remove once empty:", sorted(obsolete))


print("AUDITED folder -> code map:")
for f in AUD_FOLDERS:
    if f in folder2code:
        print("   %-24s %s" % (f, folder2code[f]))
plan_for("2_GUARDIAN PASS")
plan_for("3_CLEANED")
