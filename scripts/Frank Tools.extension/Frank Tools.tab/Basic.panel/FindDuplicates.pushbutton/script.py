# -*- coding: utf-8 -*-
__title__   = "Find\nDuplicates"
__doc__     = """Version = 1.0
Date    = 10.06.2026
________________________________________________________________
Description:
Scans Doors, Windows, Rooms, and Sheets for elements that
share the same Mark or Number. Duplicate values are a common
source of coordination errors. Clickable element IDs let you
jump straight to the offenders in the model.
________________________________________________________________
How-To:
Click the button. The report flags every duplicate group with
clickable links so you can select them directly in Revit.
________________________________________________________________
Author: Frank Sun"""

from Autodesk.Revit.DB import *
from collections import defaultdict
from pyrevit import script

app   = __revit__.Application
uidoc = __revit__.ActiveUIDocument
doc   = __revit__.ActiveUIDocument.Document  # type: Document

output = script.get_output()
output.print_md("# 🔍 Duplicate Finder")
output.print_md("**Model:** `{}`".format(doc.Title))
output.print_md("")

# Each entry: (display label, BuiltInCategory, BuiltInParameter used as the unique ID)
checks = [
    ("Rooms",   BuiltInCategory.OST_Rooms,   BuiltInParameter.ROOM_NUMBER),
    ("Sheets",  BuiltInCategory.OST_Sheets,  BuiltInParameter.SHEET_NUMBER),
    ("Doors",   BuiltInCategory.OST_Doors,   BuiltInParameter.ALL_MODEL_MARK),
    ("Windows", BuiltInCategory.OST_Windows, BuiltInParameter.ALL_MODEL_MARK),
]

found_any = False

for label, bic, bip in checks:
    elements = FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
    if not elements:
        output.print_md("— **{}**: none in model".format(label))
        continue

    value_map = defaultdict(list)
    for el in elements:
        p = el.get_Parameter(bip)
        val = p.AsString() if p else None
        if val and val.strip():
            value_map[val.strip()].append(el.Id)

    dupes = {v: ids for v, ids in value_map.items() if len(ids) > 1}

    if not dupes:
        output.print_md("✅ **{}** — no duplicates".format(label))
    else:
        found_any = True
        output.print_md("⚠️ **{}** — {} duplicate group(s)".format(label, len(dupes)))
        for val in sorted(dupes):
            ids = dupes[val]
            links = "  ".join([output.linkify(i) for i in ids])
            output.print_md("&nbsp;&nbsp;&nbsp;`{}` × {} → {}".format(val, len(ids), links))

    output.print_md("")

output.print_md("---")
if found_any:
    output.print_md("⚠️ **Duplicates found — review the items above.**")
else:
    output.print_md("✅ **All clear — no duplicates found in Doors, Windows, Rooms, or Sheets.**")
