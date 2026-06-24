# Family Benchmark

A pyRevit button that scans any folder of Revit families, scores each `.rfa` across five
dimensions, and writes results to Notion and a CSV.

> Full reference guide (what every column means, higher vs. lower):
> [Rating Reference & Guide](https://app.notion.com/p/c33208bc23ec47cda97de96a49554744)

---

## How it works

1. Click **Family Benchmark** in the FRANK Revit tab
2. Pick any root folder — sub-folders are scanned recursively
3. The script opens each `.rfa` in the background, measures it, closes it without saving
4. Results stream into the pyRevit output window in real time
5. Scores are written to the Notion **Revit Families** database (matched by Proposed Name)
6. `_benchmark_results.csv` is saved to the selected folder

---

## Scoring

Each family gets three scores (v1 / v2 / v3), all out of 100, plus a standalone
Geometry score out of 20. Higher is always better.

### Five dimensions — same for all configs

| Dimension | What loses points | Deduction |
|---|---|---|
| **File Size** | Raw `.rfa` weight on disk | Banded: < 500 KB = full · ≥ 5 MB = 0 |
| **Unused Params** | Orphan type params · orphan instance params | −2 / −1 each |
| **Off-Template Bloat** | Imported CAD · drafting views · raster images · model text | −8 flat / −4 / −5 / −3 |
| **Unnamed Ref Planes** | Planes still named "Reference Plane" | −2 each |
| **Nested Content** | Nested family defs · model groups | −3 / −5 each |

### Three configs — different weights

| Config | File Size | Unused Params | Off-Template | Ref Planes | Nesting |
|--------|----------:|-------------:|-------------:|-----------:|--------:|
| v1 — Default | 15 | 25 | 25 | 15 | 20 |
| v2 — Lean Focus | 10 | 30 | 30 | 15 | 15 |
| v3 — Weight on Nesting | 10 | 20 | 25 | 10 | 35 |

**Reading the spread:**
- v3 much lower than v1/v2 → nesting problem
- v2 lowest → parameter clutter or template bloat
- All three low → multi-dimensional cleanup needed

### Geometry Score (separate /20)

Face count at Fine detail, banded:
`< 20 = 20 · < 50 = 16 · < 100 = 12 · < 200 = 7 · < 500 = 3 · ≥ 500 = 0`

A family can have a perfect /100 and still be geometrically heavy — always check Geom Score separately.

---

## Columns written to Notion

**Legend: 📈 higher is better · 📉 lower is better · ⚖️ informational**

| Column | Dir | Notes |
|--------|:---:|-------|
| Score v1 | 📈 | Balanced baseline (15+25+25+15+20) |
| Score v2 | 📈 | Punishes param clutter and bloat harder |
| Score v3 | 📈 | Punishes nesting harder |
| Geom Score | 📈 | Independent /20, face count |
| Face Count | 📉 | Raw driver of Geom Score. Target < 20 |
| Solid Count | 📉 | More solids = more faces = heavier |
| Edge Count | 📉 | Secondary geometric density indicator |
| Imported CAD | 📉 | Any non-zero triggers −8. Target: 0 |
| Raster Images | 📉 | Should never be in a production family. Target: 0 |
| Nested Families | 📉 | Each one inflates load time. Target: 0 unless deliberate |
| Model Groups | 📉 | Shouldn't exist inside a clean family. Target: 0 |
| Unnamed Ref Planes | 📉 | Can't be reliably referenced or locked. Target: 0 |
| Orphan Type Params | 📉 | No formula, same value in all types. Dead clutter. Target: 0 |
| Orphan Inst Params | 📉 | User-created, no formula, not required. Dead clutter. Target: 0 |
| Total Params | ⚖️ | High totals usually mean orphan buildup |
| Shared Params | ⚖️ | Should be non-zero on any scheduled family |
| Formula Params | ⚖️ | Some healthy; too many slow regeneration |

---

## How to read a family

1. **Start with Score v1** — balanced baseline
2. **Compare v2 and v3 to v1** — identifies the type of problem (params vs. nesting)
3. **Check Geom Score separately** — geometry is independent of the /100
4. **Drill into count columns** — shows exactly what's dragging the score down
5. **Set Review Status** — Conform, Wishlist, or Blocker based on findings

---

## Installation

Requires [pyRevit](https://github.com/pyrevitlabs/pyRevit). Copy `script.py` into a
`.pushbutton` folder inside your pyRevit extension, then reload pyRevit.

```
YourExtension.extension/
└── YourTab.tab/
    └── YourPanel.panel/
        └── FamilyBenchmark.pushbutton/
            └── script.py
```

---

## Configuration

Edit the top of `script.py`:

```python
AUDITED_ROOT    = r"N:\..."                         # fallback token search path
DATABASE_ID     = "your-notion-database-id"
REQUIRED_PARAMS = ["Manufacturer", "Model", ...]    # params required on every family
CONFIGS         = [...]                             # scoring weights — must each sum to 100
```

### Notion token

Save your Notion integration token as `notion_token.txt` in either the selected scan
folder or the `AUDITED_ROOT` path. The script looks in both.

---

## Related

- [`scripts/SyncAuditedFamilies/`](../SyncAuditedFamilies/) —
  syncs reviewed families (Cleaned/Approved/…) from Notion to the AUDITED folder
- [Revit Family Rating System](https://app.notion.com/p/381d917dca7581fc9f50d6eb6d02367a) —
  Notion page with scoring configs and the Scores by Family view
