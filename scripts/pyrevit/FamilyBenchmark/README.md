# Family Benchmark

A pyRevit tool that batch-analyses Revit family files (`.rfa`) for efficiency, cleanliness,
and geometry complexity — then writes results to a Notion database and exports a CSV.

---

## What it does

Click the **Family Benchmark** button in the FRANK Revit tab.
A folder picker opens. Select any root folder (sub-folders are scanned recursively).
The script opens each `.rfa` in the background via the Revit API, measures it across
six dimensions, closes it without saving, then:

- Streams a live progress report in the pyRevit output window
- Writes all scores and metrics to the Notion **Revit Families** database
- Exports `_benchmark_results.csv` to the selected folder

---

## Scoring System

Each family receives three weighted scores (v1 / v2 / v3), each out of 100, plus a
standalone Geometry score out of 20.

### Score dimensions

| Dimension | What is measured |
|---|---|
| **File Size** | Raw `.rfa` weight on disk |
| **Unused Parameters** | Type params with no formula, constant across all types · User-created instance params with no formula |
| **Off-Template Bloat** | Imported CAD, drafting views, raster images, model text |
| **Unnamed Ref Planes** | Reference planes still named "Reference Plane" (Revit default) |
| **Nested Content** | Distinct nested family definitions + model groups |
| **Geometry** *(standalone)* | Total face count across all solids in Fine detail |

### Configuration weights

Three configs vary the relative weight of each dimension. All sum to 100.

| Config | File Size | Unused Params | Off-Template | Ref Planes | Nesting |
|--------|----------:|-------------:|-------------:|-----------:|--------:|
| v1 — Default | 15 | 25 | 25 | 15 | 20 |
| v2 — Lean Focus | 10 | 30 | 30 | 15 | 15 |
| v3 — Weight on Nesting | 10 | 20 | 25 | 10 | 35 |

Scores are computed by normalising raw subscores against the v1 base maxes and rescaling
to each config's dimension weights — so changing a config's weight shifts how much that
dimension contributes to the total without recomputing raw metrics.

### Deduction rates

| Dimension | Rule |
|---|---|
| File Size | < 500 KB = 100 % · < 1 MB = 73 % · < 2 MB = 47 % · < 5 MB = 20 % · ≥ 5 MB = 0 |
| Unused Params | −2 pts per orphan type param · −1 pt per orphan instance param |
| Off-Template | −8 pts if any CAD · −4 per drafting view · −5 per raster image · −3 per model text |
| Ref Planes | −2 pts per unnamed plane |
| Nested | −3 pts per nested family definition · −5 per model group |
| Geometry | < 20 faces = 20 · < 50 = 16 · < 100 = 12 · < 200 = 7 · < 500 = 3 · ≥ 500 = 0 |

---

## Installation

This script runs inside Revit via the [pyRevit](https://github.com/pyrevitlabs/pyRevit)
framework. It is not a standalone Python script.

1. Copy `script.py` into your pyRevit extension under a `.pushbutton` folder:

```
<YourExtension>.extension/
└── <YourTab>.tab/
    └── <YourPanel>.panel/
        └── FamilyBenchmark.pushbutton/
            └── script.py
```

2. Reload pyRevit (pyRevit tab → Reload).

The button will appear in your panel. Click to run.

---

## Configuration

Edit the constants block at the top of `script.py` before the first run:

```python
# Path to your firm's AUDITED family library (used as a fallback token search location)
AUDITED_ROOT = r"N:\..."

# Notion database ID for the Revit Families database
DATABASE_ID = "your-database-id-here"

# Shared parameter names required on every family regardless of category
REQUIRED_PARAMS = [
    "Manufacturer", "Model", "OmniClass Number", ...
]

# Scoring config weights — must each sum to 100
CONFIGS = [
    {"label": "v1", "size": 15, "up": 25, "ot": 25, "rp": 15, "nc": 20},
    ...
]
```

---

## Notion Integration

The script writes results back to a Notion database after each run.
Matching is done by **Proposed Name** (the intended filename without `.rfa`),
so it works regardless of where the files are scanned from.

### Setup

1. Create a Notion integration at [notion.so/profile/integrations](https://www.notion.so/profile/integrations).
2. Share the Revit Families database with the integration.
3. Save the token to a file called `notion_token.txt` in either:
   - The root folder you select at scan time, or
   - The `AUDITED_ROOT` path defined in the script.

### Columns written to Notion

**Scores**
`Score v1` · `Score v2` · `Score v3` · `Geom Score`

**Performance**
`Face Count` · `Solid Count` · `Edge Count` · `Imported CAD` · `Raster Images` ·
`Nested Families` · `Model Groups`

**Cleanliness**
`Unnamed Ref Planes` · `Orphan Type Params` · `Orphan Inst Params`

**Informational**
`Shared Params` · `Total Params` · `Formula Params`

---

## CSV Output

`_benchmark_results.csv` is saved to the selected root folder after every run.
Column groups match the Notion columns above.

| Group | Columns |
|---|---|
| Identity | `name` · `rel` · `bytes` · `size_fmt` |
| Scores | `v1` · `v2` · `v3` |
| Performance | `n_faces` · `n_solids` · `n_edges` · `n_cad` · `n_images` · `n_nested` · `n_groups` |
| Cleanliness | `n_anon_rp` · `n_unused_type` · `unused_type` · `n_unused_inst` · `unused_inst` |
| Informational | `n_shared` · `n_params` · `n_formula_params` |

---

## Notes

- The script runs inside Revit — opening families uses the Revit API, not a file parser.
  Revit must be open and a project must be active.
- Geometry collection uses **Fine** detail level and traverses into nested family geometry,
  since that is what loads into the model on placement.
- Orphan instance param detection skips **shared** parameters (MEP connector data,
  system parameters) — only user-created instance params with no formula are flagged.
- For single-type families, orphan type param detection is skipped (cannot determine
  whether a param would vary if more types were added).

---

## Related

- `scripts/powershell/Sync-ApprovedFamilies.ps1` — syncs approved families from Notion
  to the AUDITED folder and writes `Audited File Location` back to each Notion page.
- Notion page: **Revit Family Rating System** — documents the scoring configs and hosts
  the "Scores by Family" linked view.
