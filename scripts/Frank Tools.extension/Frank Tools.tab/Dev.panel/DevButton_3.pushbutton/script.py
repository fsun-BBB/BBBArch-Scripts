# -*- coding: utf-8 -*-
__title__   = "Family\nReport"
__doc__     = """Version = 1.0
Date    = 10.06.2026
________________________________________________________________
Description:
Lists every family loaded in the project alongside its instance
count. Families with zero instances are purge candidates and
inflate model file size unnecessarily.
________________________________________________________________
How-To:
Click the button. The report shows all families split into
"Placed" and "Unplaced (purge candidates)" sections, sorted
by instance count so the heaviest hitters appear first.
________________________________________________________________
Author: Frank Sun"""

from Autodesk.Revit.DB import *
from collections import defaultdict
from pyrevit import script

app   = __revit__.Application
uidoc = __revit__.ActiveUIDocument
doc   = __revit__.ActiveUIDocument.Document  # type: Document

output = script.get_output()
output.print_md("# 📦 Family Usage Report")
output.print_md("**Model:** `{}`".format(doc.Title))
output.print_md("")

# Count placed instances per family name
instance_counts = defaultdict(int)
for el in FilteredElementCollector(doc).OfClass(FamilyInstance).ToElements():
    try:
        instance_counts[el.Symbol.Family.Name] += 1
    except Exception:
        pass

# All loaded families
families = list(FilteredElementCollector(doc).OfClass(Family).ToElements())

placed   = sorted(
    [(f, instance_counts[f.Name]) for f in families if instance_counts[f.Name] > 0],
    key=lambda x: -x[1]
)
unplaced = sorted(
    [f for f in families if instance_counts[f.Name] == 0],
    key=lambda f: f.Name
)

output.print_md("**Families loaded:** {}  |  **Placed:** {}  |  **Unplaced:** {}".format(
    len(families), len(placed), len(unplaced)))
output.print_md("")

# Placed families table
output.print_md("## ✅ Placed Families ({})".format(len(placed)))
output.print_md("| Family | Category | Instances |")
output.print_md("|--------|----------|----------:|")
for fam, count in placed:
    cat = fam.FamilyCategory.Name if fam.FamilyCategory else "—"
    output.print_md("| {} | {} | {:,} |".format(fam.Name, cat, count))

output.print_md("")

# Unplaced families table
output.print_md("## 🗑️ Unplaced — Purge Candidates ({})".format(len(unplaced)))
if unplaced:
    output.print_md("| Family | Category |")
    output.print_md("|--------|----------|")
    for fam in unplaced:
        cat = fam.FamilyCategory.Name if fam.FamilyCategory else "—"
        output.print_md("| {} | {} |".format(fam.Name, cat))
else:
    output.print_md("_All loaded families have at least one instance placed._")
