# TylerFamiliesAudit

pyRevit tools for Tyler's Families Audit: extract Revit families (and their
nested families) out of the BBB template/legends, save them into the audit
holding folder on the N: drive, and sync the results into the "Revit
Families Audit" Notion database.

Developed in `BBB-pyRevit-Toolbar` under `Frank Tools.tab > Content Audit`,
which is where it actually runs. This folder is a synced copy kept for this
repo's one-folder-per-script convention - **edit the toolbar repo for changes
that ship, then re-sync here**. Not wired into `Frank Tools.extension` in this
repo; see **Installing** below if you want it live there too.

## What's here

```
TylerFamiliesAudit/
├── Content Audit.panel/                   # pyRevit panel bundle (4 pushbuttons)
│   ├── 1.ExtractLegendFamilies.pushbutton/
│   ├── 2.ImportToNotion.pushbutton/
│   ├── 3.NestedFamilyFinder.pushbutton/
│   └── 4.NestFamilyAudit.pushbutton/
└── lib/
    ├── tyler_audit/                       # extraction + "Revit Families Audit" sync
    │   ├── extraction.py                  # the nested-family walk, shared by all four
    │   └── notion_sync.py
    └── frank_audit/                       # "Kitchen Nested Family Audit" sync
        └── kitchen_notion_sync.py
```

## The tools

**1. Extract Legend Families** — box-select families/symbols in the active
view (e.g. a legend), click Finish. Extracts every unique family involved
to `0_HOLDING_TYLER\<Revit Category>\<Family Name>.rfa` (overwrites by
default, no renaming). Then prompts:
- extract nested families too? (recurses through every level of nesting)
- import everything just extracted into Notion now?

**2. Import to Notion** — standalone re-import of the last manifest, in case
you skipped the prompt above, an import failed partway, or you just want to
re-push the same data again. Matches existing rows by Family Name; safe to
re-run.

**3. Nested Family Finder** — browse to one or more `.rfa` files anywhere on
disk (they don't need to be open or loaded into the current model) and scan
them for nested families, however deep the nesting goes. The picked
family/families are registered using their existing file path (not
copied); every nested family found IS extracted into `0_HOLDING_TYLER`.

**4. Nest Family Audit** — the same nested-family walk as tool 3, pointed at
a different Notion database. Pick one or more "mother" families in the file
picker (e.g. multi-select all the Unit Families) and it walks each tree to full
depth, producing a single FLAT list where every family — parents and nested
alike — is its own row, then offers to import into the **Kitchen Nested Family
Audit** database.

Rows carry Family Name (the original name), Revit Category, File Size (MB),
File Location, and the immediate Parent / Child relationships. `Status` is set
to *Guardian Passed* on new rows only, so a manual change survives a re-run;
`Proposed Name` is never written — it is a human field. Every nested family
found is also saved into `0_HOLDING_TYLER`; the families you picked are
registered at their own paths.

> The walk itself lives in `tyler_audit.extraction` and is shared with tool 3 —
> only the Notion target differs (`frank_audit.kitchen_notion_sync`). That is why
> both libs ship together and why splitting the buttons into separate folders
> would break them.

## Relationship model

A family nested inside another is that family's "child"; the host is its
"parent". Only the immediate (one-level) relationship is recorded per row —
if A nests B and B nests C, then B's parent is A and C's parent is B, but
C's parent is never recorded as A. A family can have more than one parent
if it's shared between hosts (e.g. the same hardware family reused by two
different door families) — both parents get recorded, no error.

Notion updates are merge-based, not overwrite-based: Parent Family, Child
Family, and Type are unioned with whatever is already on the existing row,
so re-running an import only ever adds relationships, never erases ones
found earlier.

Both column **names** and **types** on the Notion side (text vs. select vs.
multi_select) are resolved live from the database schema on every run
rather than hardcoded — this database gets edited in the Notion UI over
time (e.g. `File Size` → `File Size (KB)`, Child/Parent Family text →
multi_select), and hardcoding either one breaks the import the moment the
schema drifts from what the code assumes. `Family Name` is matched
structurally (whichever column is the title type); everything else is
matched by keyword (`categor`, `type`, `parent`, `child`, `size`).

## Setup

- **Notion token**: `N:\Design Technology Resources\01_BIM CONTENT\Content
  Conformance\notion_token.txt` — a Notion integration token
  ("Revit Family Collection Integration") with access to the "Revit
  Families Audit" database. The database ID is hardcoded in
  `notion_sync.py` (`DATABASE_ID`).
- **Output folder**: `N:\Design Technology Resources\01_BIM CONTENT\Content
  Conformance\0_HOLDING_TYLER` — created automatically if missing. Hardcoded
  in `extraction.py` (`OUTPUT_ROOT`).
- Both tools depend on the N: drive being mapped and the Notion database
  having granted access to that integration (Notion page → "..." →
  Connections → add the integration).

## Installing

pyRevit auto-discovers a `lib` folder at an extension's root and adds it to
`sys.path` for every script inside that extension. To use these tools:

1. Copy `Content Audit.panel/` into a tab folder inside a pyRevit
   `.extension` (e.g. `Frank Tools.extension/Frank Tools.tab/`).
2. Copy **both** `lib/tyler_audit/` and `lib/frank_audit/` into that same
   extension's `lib/` folder (create `lib/` at the extension root if it doesn't
   already exist). Tool 4 imports from `frank_audit`; the other three do not.
3. Reload pyRevit.

## Known gaps

- Two families (`Level Head - Upgrade`, `Section Head - Min`) turned up as
  referenced children during extraction but never got their own extracted
  row — likely `Family.IsEditable` was `False` for whatever hosted them, or
  extraction failed silently. Worth re-running Nested Family Finder on
  their host(s) to backfill.
- `Document.OwnerFamily` (used when a family is opened standalone rather
  than via `EditFamily` from a project) has been unreliable for both
  `.Name` and `Family.GetFamilySymbolIds()` across Revit versions — both
  are worked around in `extraction.py` (`elem_name()`,
  `get_all_type_names()`), but if a future symptom looks like "missing
  data only for directly-opened families," check there first.
