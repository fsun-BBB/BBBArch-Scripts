# Frank Tools (pyRevit extension)

The full **Frank Tools** pyRevit extension (formerly `FRANK.extension`), moved here from the
local pyRevit folder so it lives under version control. This is a complete pyRevit
extension — not a single script — so it keeps the required `*.extension` / `*.tab` /
`*.panel` / `*.pushbutton` folder structure.

> Moved verbatim from `%APPDATA%\pyRevit` style location. The extension folder and its
> ribbon tab were renamed `FRANK` → `Frank Tools`.

---

## Relinking in Revit (pyRevit)

Revit no longer loads this from the old location. To re-register it:

1. Revit → **pyRevit** tab → **Settings**
2. Under **Custom Extension Directories**, add the folder that *contains* this extension:
   ```
   C:\Users\fsun\Documents\GitHub\BBBArch-Scripts\scripts
   ```
3. **Save Settings and Reload**.

pyRevit discovers any `*.extension` folder in that directory, so the other per-script
folders under `scripts/` are ignored. A **Frank Tools** ribbon tab will appear.

---

## What's inside

### Dev.panel — the real tools

| Tool | Description |
|---|---|
| **FamilyBenchmark** | Scores `.rfa` families across five efficiency dimensions, writes to Notion, exports CSV. |
| **FamilyOptimizer** | Largest tool — automated family cleanup / optimization. |
| **GeoReducer** | Reduces geometry complexity in families. |
| **ParamAudit** | Audits family parameters (orphans, unused, formula). |
| **PurgeUnused** | Purges unused content. |
| **CeilingHeights** | CLR ceiling-height calculator (dev version; the production tool lives in [`../CLRCeilingHeights/`](../CLRCeilingHeights/)). |

### Other panels

`About.panel`, `PlaceholderPanel.panel`, and `Resource.panel` are the **pyRevit
starter-kit boilerplate** (sample buttons, documentation links, code samples) that ships
with the pyRevit extension template. Kept verbatim per request.

---

## Notes

- This is IronPython running inside Revit — keep dependencies to the standard library and
  pyRevit's bundled packages.
- A `README.md` at the extension root is ignored by pyRevit; it won't affect loading.
