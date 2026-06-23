# CLR Ceiling Heights

The CLR Ceiling Heights tool calculates the **clear height (CLR)** from every ceiling to the floor directly below it, writes the result to the shared parameter `S_Ceiling Tag_Clear Height`, and places ceiling tags in the active view.

---

## What It Does

This tool measures **ceiling-to-floor clearance** — not ceiling-to-level height. The distinction matters:

| Tag Family | Measures From | Measures To |
|---|---|---|
| B_ANNO_Ceiling Tag_Clear Height *(this tool)* | Ceiling bottom | Floor top surface |
| Default Revit ceiling tag | Ceiling bottom | Level datum |

The tool intelligently handles:

- Ceilings with a single floor below — direct measurement
- Ceilings with multiple overlapping floors — uses 2D footprint projection to find the dominant floor (>= 95% coverage required)
- Ceilings with no floor below — falls back to level datum and flags for review

---

## ⚠️ CLR vs AFF — Critical Distinction

The native Revit ceiling tag and the CLR tag look **visually identical** on drawings. However they display different values:

- **AFF** (ceiling-to-level) — what Revit places by default
- **CLR** (ceiling-to-floor) — what this tool places

Mixed use of both families on the same sheet will mislead reviewers. The tool automatically detects and flags any non-CLR ceiling tags found anywhere in the model when you run it.

---

## Prerequisites

**Required Components**

1. **Ceiling Tag Family:** `B_ANNO_Ceiling Tag_Clear Height`
2. **Shared Parameter:** `S_Ceiling Tag_Clear Height` (bound to Ceilings — auto-bound on first run)
3. **Active View:** Floor Plan or Reflected Ceiling Plan (required for tag placement)

**Note:** The shared parameter is created and bound automatically the first time you run the tool. You only need to load the tag family manually.

**If the Tag Family Is Missing**

1. Access the BBB Content Catalog
2. Load `B_ANNO_Ceiling Tag_Clear Height` into your project
3. Re-run the tool

---

## How to Use

1. Load `B_ANNO_Ceiling Tag_Clear Height` into your project
2. Open a **Floor Plan** or **Reflected Ceiling Plan** view
3. Navigate to the **BBB Tools** tab -> **Graphics** panel
4. Click **CLR Ceiling** (below Update Scales)
5. Review the results in the output window

The output window displays:

- Number of ceilings updated with CLR values
- Ceilings with no floor found (fell back to level datum)
- Ceilings with ambiguous floors (selected in model for review)
- Number of tags placed in the active view
- Off-template ceiling tags detected in the model, with view and sheet location

---

## Behind the Scenes

**Pre-Flight Check**

Before making any changes, the tool checks that `B_ANNO_Ceiling Tag_Clear Height` is loaded. If not found, it stops and directs you to load it first.

**Off-Template Scan**

The tool scans the entire model for ceiling tag instances that do not belong to the `B_ANNO_Ceiling Tag_Clear Height` family. Any found are reported at the top of the output window with their view and sheet location.

**Calculation Logic**

The tool:

1. Collects all ceilings in the model
2. For each ceiling, finds all floors whose top surface is below the ceiling bottom
3. If one floor -> uses it directly
4. If multiple floors -> runs a 25x25 grid point-in-polygon overlap test; the floor covering >= 95% of the ceiling footprint is selected
5. If no dominant floor -> clears the parameter and flags the ceiling for review
6. Writes the calculated clearance to `S_Ceiling Tag_Clear Height`

**Tag Placement**

Tags are placed only when the active view is a Floor Plan, Ceiling Plan, or Area Plan. Ceilings already tagged in that view are skipped automatically.

---

## Troubleshooting

**Tool shows "Required ceiling tag family not loaded"**

- Load `B_ANNO_Ceiling Tag_Clear Height` from the BBB Content Catalog

**Output shows off-template ceiling tags**

- These are tags from other families (typically the default Revit ceiling tag showing AFF, not CLR)
- Click the instance count in the report to select them in the model and review or delete

**Output shows "Errors: X ceilings"**

- Multiple floors exist below these ceilings and none covers >= 95% of the ceiling footprint
- The tool selects these ceilings and candidate floors in the model automatically — review the geometry

**Tags were not placed**

- Verify the active view is a Floor Plan or Reflected Ceiling Plan
- Ceilings that already have a tag in the active view are skipped

---

## Best Practices

- Run this tool after adding, moving, or modifying ceilings or floors
- Always use `B_ANNO_Ceiling Tag_Clear Height` — never mix with the default Revit ceiling tag
- If off-template tags are reported, delete them and re-run
- For ambiguous floor errors, check for overlapping floor slabs in the model geometry

---

*For additional support, contact DCT*
