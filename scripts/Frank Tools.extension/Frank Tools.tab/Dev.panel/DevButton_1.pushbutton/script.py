# -*- coding: utf-8 -*-
__title__   = "Count\nElements"
__doc__     = """Version = 1.0
Date    = 10.06.2026
________________________________________________________________
Description:
Counts every model element grouped by category and prints
a summary report sorted from most to fewest instances.
Great for auditing model size and spotting bloated categories.
________________________________________________________________
How-To:
Click the button. A report opens in the pyRevit output window
showing element counts across all categories.
________________________________________________________________
Author: Frank Sun"""

from Autodesk.Revit.DB import *
from collections import Counter
from pyrevit import script

app   = __revit__.Application
uidoc = __revit__.ActiveUIDocument
doc   = __revit__.ActiveUIDocument.Document  # type: Document

output = script.get_output()
output.print_md("# 📊 Element Count by Category")
output.print_md("**Model:** `{}`".format(doc.Title))
output.print_md("")

# Collect every non-type element that has a category
elements = FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()

counts = Counter()
for el in elements:
    if el.Category:
        counts[el.Category.Name] += 1

# Print as a markdown table sorted by count descending
output.print_md("| # | Category | Count |")
output.print_md("|---|----------|------:|")
for i, (cat_name, count) in enumerate(sorted(counts.items(), key=lambda x: -x[1]), 1):
    output.print_md("| {} | {} | {:,} |".format(i, cat_name, count))

output.print_md("")
output.print_md("---")
output.print_md("**Total: {:,} elements across {} categories**".format(
    sum(counts.values()), len(counts)))
