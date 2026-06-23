# CLR Ceiling Heights

The **CLR Ceiling Heights** pyRevit tool set — calculates the clear height (ceiling bottom
to the floor directly below) and tags ceilings with it. Consolidated here from the
production **BBB-pyRevit-Toolbar** repo.

> ⚠️ **Canonical / running copy lives in `BBB-pyRevit-Toolbar`** (BBB Tools tab →
> Graphics panel). This is a versioned snapshot for consolidation — edit the production
> repo for changes that ship, and keep this copy in sync.

For the full functional write-up (CLR vs AFF, calculation logic, troubleshooting), see
[`../../doc/CLR-Ceiling-Heights.md`](../../doc/CLR-Ceiling-Heights.md).

---

## Contents

```
CLRCeilingHeights/
├── lib/clr_ceiling_config.py        # shared config (load/save/is_configured)
└── CLRCeilingHeights.pulldown/
    ├── UpdateTags.pushbutton/       # calc clear heights + place ceiling tags
    ├── ClearanceCheck.pushbutton/   # report ceilings under a clearance threshold
    ├── Configure.pushbutton/        # set thresholds / options
    └── Documentation.pushbutton/    # opens the docs
```

## Tools

| Button | Description |
|---|---|
| **UpdateTags** | Calculates ceiling-to-floor clear height, writes `S_Ceiling Tag_Clear Height`, and places `B_ANNO_Ceiling Tag_Clear Height` tags in the active view. |
| **ClearanceCheck** | Flags ceilings whose clear height falls under a configured threshold. |
| **Configure** | Sets the clearance thresholds and tool options (feet/inches input). |
| **Documentation** | Opens the tool documentation. |

## Dependency

The pushbutton scripts import `clr_ceiling_config` (`from clr_ceiling_config import …`).
In the production extension that module lives on the extension `lib/` path; here it's
vendored under `lib/` alongside the pulldown for completeness. To run inside Revit, the
module must be importable on pyRevit's `lib` path.
