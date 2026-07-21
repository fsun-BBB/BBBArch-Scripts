# Content Conformance Audit — Operational Scripts

One-off and repeatable Python scripts supporting the **BBB BIM Content Conformance**
family audit (July 2026): reorganizing the audited family library to the naming
convention, syncing family/nested-family data into Notion, and analysing the
Family Efficiency benchmark for reporting.

These are **operational scripts**, not a packaged tool. They ran against live data
on the `N:` drive and the team Notion workspace. Most carry **hardcoded paths and
Notion database IDs** specific to that migration — read them before re-running.

## Requirements
- **Python 3** (standard library only, except `export_notion_to_excel.py` needs `openpyxl`).
- **Notion token**: every `notion/` script reads the integration token from
  `N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\notion_token.txt`
  (not embedded in code). The integration must be shared with the target pages.

## `notion/` — Notion database & row operations
| Script | What it does |
| :-- | :-- |
| `create_kitchen_db_and_import.py` | Creates the "Kitchen Nested Family Audit" database and imports the walk manifest. |
| `create_bathroom_db.py` | Creates the "Bathroom Nested Family Audit" database (same schema). |
| `add_types_column.py` | Adds a `Types` multi-select column and backfills family type variants. |
| `set_proposed_names_kitchen.py` | Writes convention-based Proposed Names to kitchen rows. |
| `set_proposed_names_bathroom.py` | Writes convention-based Proposed Names to bathroom rows. |
| `add_to_revit_families.py` | Adds newly-audited families as rows in the "Revit Families" database. |
| `fix_filesize_kb_column.py` | Renames the File Size column to KB and updates values. |
| `omit_system_families.py` | Archives system/annotation family rows and scrubs them from relationships. |
| `simple_table_sync_reference.py` | Reference implementation for upserting into a Notion **simple table block** (vs a database). |

## `reorg/` — Filesystem reorganization (AUDITED / GUARDIAN PASS / CLEANED)
| Script | What it does |
| :-- | :-- |
| `plan_reorg.py` | **Dry run** — matches each family to its AUDITED category and prints the move/rename plan. |
| `execute_reorg.py` | Executes the plan: mirrors the AUDITED folder structure, moves/renames files, removes obsolete empty folders, writes a reversible JSON log. |
| `dedupe_and_rename.py` | Quarantines duplicate families and renames the rest to the `B_<CAT>_` convention. |
| `rename_unit_families.py` | Renames Unit Families + accessory overwrites to convention. |
| `final_rename_fixes.py` | Final rename/dedup touch-ups + Notion Proposed Name updates. |

Moves are non-destructive (quarantine, not delete) and logged for reversal.

## `benchmark/` — Analysis & reporting
| Script | What it does |
| :-- | :-- |
| `analyze_benchmark.py` | Aggregates the Family Efficiency benchmark CSVs (file size, nested families, params, CAD/raster, scores) across pipeline stages; emits `bench_stats.json`. |
| `export_notion_to_excel.py` | Exports the Kitchen/Bathroom Notion audit databases to `.xlsx`. |
| `report_template.html` | The manager progress-report template (rendered to HTML/PDF). |

## Naming convention (reference)
`B_<CAT>_<Subtype>_<Descriptor>[_<Dim>][_<Size>]` — four-letter uppercase category
code (e.g. `PLMB`, `EQPT`, `CASE`, `UNIT`, `ANNO`), Title-Case segments, single
underscore between segments.
