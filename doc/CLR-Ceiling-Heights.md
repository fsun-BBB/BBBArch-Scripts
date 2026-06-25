# Ceiling Tags

The Ceiling Tags toolset calculates the **clear height (CLR)** from every ceiling
to the floor directly below it, writes the result to the shared parameter
`S_Ceiling Tag_Clear Height`, and lets you audit clearance thresholds across the
entire model.

> **make a screenshot of the BBB Tools ribbon showing the CLRCeilingHeights pulldown with all 4 buttons visible**

---

## What It Does

By default, ceiling tags in Revit report the **distance from the ceiling to its
hosted level**. This can cause issues when the floor below is hosted to a different
level or has a level offset. This toolset calculates the **actual floor-to-ceiling
clearance** instead.

> **make a screenshot of the ceiling-to-level vs ceiling-to-floor diagram**

---

## The Toolset

The pulldown contains four buttons that work together:

| Button | What it does |
|---|---|
| **Configure** | Set clearance thresholds and floor search depth — run this first |
| **Update Ceiling Tags** | Calculate CLR for all ceilings and place tags in the active view |
| **Clearance Check** | Audit existing tags and flag ceilings below threshold |
| **Documentation** | Opens this page |

---

## Step 1 — Configure

**Configure must be run before Update Ceiling Tags or Clearance Check.**

Click **Configure** to open the settings dialog.

> **make a screenshot of the Configure dialog**

### Floor Search

**Search depth below ceiling (ft)** — how far below each ceiling the tool looks
for a floor. Ceilings where the floor is farther away than this value fall back to
level datum.

### Clearance Thresholds

Three severity tiers define what counts as a clearance issue. Tier 1 must be the
lowest value; Tier 3 the highest.

| Tier | Severity | Meaning |
|---|---|---|
| **Tier 1** | Critical | Clearance is dangerously low — immediate review required |
| **Tier 2** | Warning | Clearance is tight — flag for coordination |
| **Tier 3** | Caution | Clearance is worth noting |

> **Rule:** Tier 1 < Tier 2 < Tier 3. The tool will not save if this order is violated.

Click **Save** to apply. A confirmation dialog shows your saved values.

---

## Step 2 — Update Ceiling Tags

1. Open a **Floor Plan** or **Reflected Ceiling Plan**
2. Navigate to **BBB Tools → Graphics**
3. Click **Update Ceiling Tags**
4. Review the results in the output window

The tool runs automatically — no selection required.

### If the Tag Family Is Missing

A pre-flight dialog appears before the tool runs. Click **View Documentation** to
open this page, then load `B_ANNO_Ceiling Tag_Clear Height` into the project and
re-run.

> **make a screenshot of the "Missing Required Ceiling Tag Family" TaskDialog**

### Output Window

A progress bar shows calculation and tag-placement status. You can cancel at any
time — no changes are saved if cancelled.

> **make a screenshot of the Update Ceiling Tags output window showing the Results,
> Broken Ceilings, and Unresolved Ceilings sections**

The output has three collapsible sections:

**Results** *(expanded by default)*

| Row | Description |
|---|---|
| Processed | Total ceilings found in the model |
| Updated | Ceilings written successfully; count in parentheses shows how many values actually changed |
| No level reference (Broken) | Ceilings with a missing or broken level reference — could not be calculated |
| Ambiguous floor (Unresolved) | Multiple floors below; no single floor dominates the footprint |
| Tags placed | Tags added to the active view this run |

**Broken Ceilings** *(collapsed)*
Lists ceilings that could not be processed due to a missing level reference.
Click any ceiling ID to select it in the model.

**Unresolved Ceilings — Ambiguous Floor** *(collapsed)*
Lists ceilings where multiple floors were found below but none covers ≥ 95% of the
ceiling footprint. Shows each candidate floor with a visual overlap bar. These
ceilings and floors are selected in the model automatically for review.

> **make a screenshot of the Unresolved Ceilings section showing the overlap bars**

---

## Step 3 — Clearance Check

Clearance Check is a separate audit tool that reads existing `S_Ceiling Tag_Clear Height`
values and checks them against your configured thresholds. It does not recalculate
or modify anything.

1. Navigate to **BBB Tools → Graphics**
2. Click **Clearance Check**
3. Review the results in the output window

> **make a screenshot of the Clearance Check output window**

The output has three collapsible sections:

**Results** *(expanded)*
Summary counts: off-template tags found, and how many ceilings fall into each tier.

**Tag Audit** *(collapsed)*
All ceiling tags in the model that are NOT `B_ANNO_Ceiling Tag_Clear Height`,
grouped by family, type, view, and sheet. Click the instance count to select
them in the model.

**Clearance Audit** *(collapsed)*
Ceilings grouped by tier severity. Each sub-section shows ceiling ID and CLR value.
Click any ceiling ID to select it in the model.

---

## Native Revit Tag vs CLR Tag — Critical Distinction

The native Revit ceiling tag and the CLR tag look **visually identical** on
drawings, but they measure different things:

- **Native Revit tag** (ceiling-to-level) — what Revit places by default
- **CLR** (ceiling-to-floor) — what this toolset places

Both types can be used concurrently. If non-CLR tags are present, **Clearance
Check** will flag them in the Tag Audit section.

---

## Prerequisites

**Required components**

1. **Ceiling Tag Family:** `B_ANNO_Ceiling Tag_Clear Height`
2. **Shared Parameter:** `S_Ceiling Tag_Clear Height` *(auto-bound on first run)*
3. **Active View:** Floor Plan or Reflected Ceiling Plan *(for Update Ceiling Tags)*
4. **Configure** must be run before Update Ceiling Tags or Clearance Check

**Note:** The shared parameter is created and bound automatically the first time
you run Update Ceiling Tags. You only need to load the tag family manually.

---

## Behind the Scenes

**Calculation logic**

1. Collects all ceilings in the model
2. For each ceiling, finds all floors whose top surface is below the ceiling bottom
   and within the configured search depth
3. If one floor → uses it directly
4. If multiple floors → runs an overlap grid test; the floor covering ≥ 95% of the
   ceiling footprint is selected
5. If no dominant floor → clears the parameter and flags the ceiling as Unresolved
6. Writes the calculated clearance to `S_Ceiling Tag_Clear Height`

**Tag placement**

Tags are placed only when the active view is a Floor Plan, Ceiling Plan, or Area
Plan. Ceilings already tagged in the active view are skipped automatically.

---

## Troubleshooting

**"Please run Configure first"**
Configure has not been run yet, or the config file is missing. Open Configure, set
your thresholds, and click Save before re-running.

**"Missing Required Ceiling Tag Family"**
Load `B_ANNO_Ceiling Tag_Clear Height` from the BBB Content Catalog, then re-run.

**Unresolved Ceilings — Ambiguous Floor**
Multiple floors exist below the ceiling and none covers ≥ 95% of the footprint.
The tool selects these ceilings and candidate floors in the model — review for
overlapping slabs or geometry issues.

**Broken Ceilings — No Level Reference**
The ceiling has a missing or broken level reference in the model. Select the
ceiling and reassign its level in properties.

**Tags were not placed**
Verify the active view is a Floor Plan or Reflected Ceiling Plan. Ceilings that
already have a CLR tag in the active view are skipped.

---

## Best Practices

- Run **Configure** once per project to set appropriate thresholds for the
  building type
- Run **Update Ceiling Tags** after adding, moving, or modifying any ceilings
  or floors
- Run **Clearance Check** periodically as a QC step before issuing drawings
- Always use `B_ANNO_Ceiling Tag_Clear Height` — never mix with the default
  Revit ceiling tag
- If the Tag Audit flags off-template tags, delete them and re-run

---

*For additional support, contact DCT.*
