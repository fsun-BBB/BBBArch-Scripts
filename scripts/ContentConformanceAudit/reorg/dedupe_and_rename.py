# -*- coding: utf-8 -*-
"""Quarantine un-renamed duplicates (that already have a B_ twin) and rename
the genuinely-new bathroom families to the B_<CAT>_ convention.

Safety:
- Duplicates are MOVED to a _DUPLICATES subfolder (reversible), only after
  confirming the B_ twin actually exists in the same folder.
- Renames never overwrite: if the target name already exists, it's skipped
  and reported.
- Specials (X_… base family, Parts_… sub-components) are left untouched.
"""
import os, shutil

BASE = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\1_AUDITED"

# unrenamed duplicate -> the B_ twin that must exist for the move to happen
DUPES = {
    "Specialty Equipment": {
        "Kitchens - Appliance - Hood": "B_EQPT_Hood_Kitchen",
        "Kitchens - Appliance - Microwave - 24in - Wall Mounted": "B_EQPT_Microwave_WallMounted_24in",
        "Kitchens - Appliance - Microwave - 30in - Wall Mounted": "B_EQPT_Microwave_WallMounted_30in",
        "_Kitchens - Appliance - Dishwasher": "B_EQPT_Dishwasher_Kitchen",
        "_Kitchens - Appliance - Range - 24in": "B_EQPT_Range_Kitchen_24in",
        "_Kitchens - Appliance - Range - 30in": "B_EQPT_Range_Kitchen_30in",
        "_Kitchens - Appliance - Refrigerator": "B_EQPT_Refrigerator_Kitchen",
    },
    "Plumbing Fixtures": {
        "Kitchens - Fixture - Sink": "B_PLMB_Sink_Kitchen",
        "Kitchens - Fixture - Faucet": "B_PLMB_Faucet_Kitchen",
    },
}

# unrenamed new family -> convention name (no B_ twin exists)
RENAMES = {
    "Specialty Equipment": {
        "Resi-Bath - Accessories - Curtain Rod": "B_EQPT_Curtain Rod_Shower",
        "Resi-Bath - Accessories - Med. Cabinet - Double": "B_EQPT_Medicine Cabinet_Double",
        "Resi-Bath - Accessories - Med. Cabinet - Single": "B_EQPT_Medicine Cabinet_Single",
        "Resi-Bath - Accessories - Robe Hook": "B_EQPT_Robe Hook_Residential",
        "Resi-Bath - Accessories - TP Holder": "B_EQPT_Toilet Paper Holder_Residential",
        "Resi-Bath - Accessories - Towel Bar": "B_EQPT_Towel Bar_Residential",
        "Resi-Bath - Grab Bars - Bathtub": "B_EQPT_Grab Bar_Bathtub",
        "Resi-Bath - Grab Bars - Shower": "B_EQPT_Grab Bar_Shower",
        "Resi-Bath - Grab Bars - Toilet": "B_EQPT_Grab Bar_Toilet",
    },
    "Plumbing Fixtures": {
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
        "_Resi-Bath - Fixtures - Shower Drain": "B_PLMB_Drain_Shower",
        "_Resi-Bath - Fixtures - Sink w Faucet": "B_PLMB_Sink_Bath With Faucet",
    },
}

# left untouched on purpose (flagged for user decision)
SPECIALS = {
    "Specialty Equipment": ["X_ Grab Bar - Single - Parametric"],
    "Plumbing Fixtures": ["Parts_ Resi-Bath - Fixtures - Sink Faucet 1",
                          "Parts_ Resi-Bath - Fixtures - Sink Faucet 2"],
}


def run():
    for cat in ["Specialty Equipment", "Plumbing Fixtures"]:
        folder = os.path.join(BASE, cat)
        print("=" * 20, cat, "=" * 20)

        # 1. quarantine duplicates
        qdir = os.path.join(folder, "_DUPLICATES")
        for dup, twin in DUPES.get(cat, {}).items():
            src = os.path.join(folder, dup + ".rfa")
            twin_path = os.path.join(folder, twin + ".rfa")
            if not os.path.exists(src):
                print("  [dup] MISSING (already gone?):", dup)
                continue
            if not os.path.exists(twin_path):
                print("  [dup] SKIP - twin not found, NOT moving:", dup, "->", twin)
                continue
            if not os.path.isdir(qdir):
                os.makedirs(qdir)
            shutil.move(src, os.path.join(qdir, dup + ".rfa"))
            print("  [dup] quarantined:", dup, " (twin kept:", twin + ")")

        # 2. rename new families
        for old, new in RENAMES.get(cat, {}).items():
            src = os.path.join(folder, old + ".rfa")
            dst = os.path.join(folder, new + ".rfa")
            if not os.path.exists(src):
                print("  [rename] MISSING:", old)
                continue
            if os.path.exists(dst):
                print("  [rename] SKIP - target exists:", new)
                continue
            os.rename(src, dst)
            print("  [rename]", old, "->", new)

        # 3. report specials left alone
        for s in SPECIALS.get(cat, []):
            exists = os.path.exists(os.path.join(folder, s + ".rfa"))
            print("  [special] left untouched%s:" % ("" if exists else " (missing)"), s)


run()
