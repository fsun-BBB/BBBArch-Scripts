# -*- coding: utf-8 -*-
"""(1) Overwrite generic accessories with the residential versions (old
generic quarantined for safety), (2) rename X_ -> B_, (3) rename all Unit
Families to the naming convention."""
import os, shutil

BASE = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\1_AUDITED"
SPEC = os.path.join(BASE, "Specialty Equipment")
UNIT = os.path.join(BASE, "Unit Families")


def qmove(folder, name):
    q = os.path.join(folder, "_DUPLICATES")
    if not os.path.isdir(q):
        os.makedirs(q)
    shutil.move(os.path.join(folder, name), os.path.join(q, name))


def rename(folder, old, new):
    src = os.path.join(folder, old + ".rfa")
    dst = os.path.join(folder, new + ".rfa")
    if not os.path.exists(src):
        print("  MISSING:", old); return
    if os.path.exists(dst):
        print("  SKIP (target exists):", new); return
    os.rename(src, dst)
    print("  %s -> %s" % (old, new))


print("=== Specialty Equipment: overwrite generics with residential ===")
# quarantine old generic, promote residential to the plain name
for base in ["Robe Hook", "Toilet Paper Holder"]:
    old = "B_EQPT_%s.rfa" % base
    res = "B_EQPT_%s_Residential.rfa" % base
    if os.path.exists(os.path.join(SPEC, old)) and os.path.exists(os.path.join(SPEC, res)):
        qmove(SPEC, old)
        os.rename(os.path.join(SPEC, res), os.path.join(SPEC, old))
        print("  overwrote B_EQPT_%s (old quarantined)" % base)
    else:
        print("  SKIP overwrite for", base, "(missing old or residential)")
# Towel Bar: no old generic, just drop the _Residential suffix
rename(SPEC, "B_EQPT_Towel Bar_Residential", "B_EQPT_Towel Bar")

print("=== Specialty Equipment: X_ -> B_ ===")
rename(SPEC, "X_ Grab Bar - Single - Parametric", "B_Grab Bar - Single - Parametric")

print("=== Unit Families: rename all to convention ===")
for i in range(1, 15):
    rename(UNIT, "B_UNIT_KitchenAssembly_Unit%02d" % i, "B_UNIT_Kitchen Assembly_Unit%02d" % i)
for i in range(1, 6):
    rename(UNIT, "_Res-Bathroom - Type %d" % i, "B_UNIT_Bathroom Assembly_Type%02d" % i)
rename(UNIT, "_Resi-Bath - Bathtub", "B_PLMB_Bathtub_Residential")
rename(UNIT, "_Resi-Bath - Shower", "B_PLMB_Shower_Residential")
rename(UNIT, "_Resi-Bath - Vanity", "B_CASE_Vanity_Single")
rename(UNIT, "_Resi-Bath - Vanity_Double", "B_CASE_Vanity_Double")

print("=== Unit Families now contains ===")
for f in sorted(os.listdir(UNIT)):
    if f.lower().endswith(".rfa"):
        print("  ", f)
