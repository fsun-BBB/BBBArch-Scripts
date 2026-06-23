# Sync Audited Families

A PowerShell script that pulls reviewed Revit families out of the Notion **Revit Families**
database and copies them into the firm's **AUDITED** library, renamed to their standardized
Proposed Name and filed under their Category.

---

## What it does

1. Queries the Notion database for every entry whose **Review Status** matches `-Status`
   (default **`Cleaned`**).
2. For each match, copies the source `.rfa` to:
   ```
   <DestRoot>\<Category>\<Proposed Name>.rfa
   ```
3. Writes that destination path back into the Notion **Audited File Location** field.
4. Skips files that are already up to date (destination newer than or equal to source).

---

## Source field priority

The source file is read from the **first populated** field, in this order:

| Priority | Notion field | Example | Notes |
|:--:|---|---|---|
| 1 | **Original Location** | `N:\…\01_BIM CONTENT\2025\<Cat>\…` | **Canonical** curated library copy — preferred |
| 2 | Source Location | `H:\<project>\…` | Per-project working copy |
| 3 | Location | — | Legacy field name |

> ⚠️ Always prefer **Original Location**. The `N:` library is the source of truth; the
> `H:` project paths are working folders and some Cleaned entries leave Source Location blank.

---

## Usage

```powershell
# Preview only — nothing is copied, nothing is written back to Notion
.\Sync-AuditedFamilies.ps1 -DryRun

# Real run — copies "Cleaned" families and updates Notion
.\Sync-AuditedFamilies.ps1

# Sync a different status
.\Sync-AuditedFamilies.ps1 -Status Approved

# Also create an empty folder for every category (complete AUDITED tree)
.\Sync-AuditedFamilies.ps1 -CreateAllCategoryFolders
```

### Parameters

| Parameter | Default | Description |
|---|---|---|
| `-Status` | `Cleaned` | Review Status to filter on (`Cleaned`, `Approved`, `Conformed`, `Uploaded`, …) |
| `-NotionToken` | *(reads token file)* | Notion integration token; overrides `notion_token.txt` |
| `-DestRoot` | `N:\…\1_AUDITED` | Root AUDITED folder |
| `-CreateAllCategoryFolders` | off | Pre-create an empty subfolder for every category |
| `-DryRun` | off | Preview without copying or writing to Notion |

---

## First-time setup

1. Go to <https://www.notion.so/profile/integrations> and create an integration.
2. Copy the integration token.
3. In Notion, open the **Revit Families** database → 3-dot menu → **Connections**, and
   connect your integration (needs read **and** write access to backfill the audited path).
4. Save the token as **`notion_token.txt`** in this folder.

> 🔒 `notion_token.txt` is git-ignored — never commit it.

---

## Notes

- **Run `-DryRun` first.** Always confirm the source paths resolve before a real copy.
- The Notion MCP/SQL query layer can lag the live UI by an entry or two. If a board view
  count disagrees with the script's "Found N" line, give the sync a minute and re-run, or
  paginate the board view to find the straggler.
- Database ID is hard-coded near the top of the script (`$DATABASE_ID`).

## Related

- [`../FamilyBenchmark/`](../FamilyBenchmark/) — scores families for efficiency before they're cleaned/approved.
