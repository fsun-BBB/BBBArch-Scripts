# Envelope Area Calcs

The **Envelope Area Calculations** pyRevit tool set — measures facade area per element
off a Revit elevation, draws a coloured filled region for each piece, stamps the areas
into schedulable parameters and reports the window-to-wall ratio.

A native-Revit replacement for the Rhino.Inside / Grasshopper "Envelope / Facade Area
Calculations" script: the user builds the elevation, presses one button, and the work
happens inside Revit.

> ⚠️ **Canonical / running copy lives in `BBB-pyRevit-Toolbar`** (BBB Tools tab →
> Energy panel). This is a versioned snapshot for consolidation — edit the production
> repo for changes that ship, and keep this copy in sync.

---

## Contents

```
EnvelopeAreaCalcs/
├── Energy.panel/
│   ├── 1.RunNow.pushbutton/            # re-measure the open elevation, no questions
│   ├── 2.SelectElevations.pushbutton/  # pick views, then the full pass
│   └── 3.Configurations.pushbutton/    # what counts as envelope, type limits, purge
└── lib/envelope/
    ├── core.py                         # the whole measurement pass (~3,900 lines)
    ├── config_ui.py / config_window.xaml   # settings window
    └── merge_ui.py / merge_window.xaml     # wall-type merging editor
```

## How it runs

1. **The user builds the elevation.** The tool does not create views.
2. **Pick the elevations** from a list (or use *Run Now* on the open one).
3. **Depth check.** An elevation with no far clip looks straight through the building
   and every interior wall behind the facade gets measured. The dialog reports what each
   view currently sees — crop, clipping distance, scope box, wall count, and how far the
   frontmost wall sits from the elevation tag — and offers to set the clip at a distance
   given **in feet from the tag** (20 = cut 20 ft in front of the tag), or to assign a
   scope box.
4. **Collect and cull.** Every wall, window and door visible in the elevation, linked
   models included. Anything past the clip distance is dropped, as is any wall seen
   edge-on.
5. **Front tier.** The elevation plane is walked in cells and each cell goes to whichever
   wall lies nearest the tag. A mass set back 40 ft is still measured over its own stretch
   of the elevation, while interior walls behind the facade win nothing.
6. **Draw.** One filled region per element, using the exact front-face outline where
   possible — arched heads survive, and because a wall's face already carries its window
   and door openings as holes, **wall area is net and nothing overlaps**. Non-planar cases
   fall back to the bounding box, which is exact for rectangular windows.
7. **Stamp and report.** Areas into parameters, refresh the schedule, report area and
   window-to-wall ratio per category and per elevation.

## Categories

Wall (masonry, one uniform colour) · Curtain Wall · Window · Door.

Glazing separates from spandrel by type name. Slab-edge and column conditions are **not**
a wall colour — they belong to the linear thermal-bridge overlay, which is not built yet.

## Parameters

Three instance project parameters bound to Filled Region (Detail Items):

| Parameter | Type | Holds |
| :-- | :-- | :-- |
| `Type Area` | Area | The measured net area |
| `Elevation` | Text | Host elevation view name |
| `Depth from Tag` | Length | Distance from the tag plane to the element's nearest point |

`Depth from Tag` is what the front-tier pass ranks on — schedule it to verify the tier.
The facade should sit at one distance with anything behind it further back.

## Design decisions worth knowing

**The config window is a set of tick boxes, not inference.** What counts as envelope is a
project decision. Curtain wall panels and windows/doors default on; mullions, slab edges
and columns default off — many projects model the slab separately from the facade, and
there the category is noise.

**The roof reduces to one line.** The roof's highest point in the elevation becomes a
single horizontal cut and every region is trimmed to it. A sloped or stepped roof is *not*
followed as a profile — all regions are cut at the same height, so a wall standing proud
of the roof loses that portion and one entirely above it is not measured. If the view
shows no roof, nothing is trimmed and the report says so.

**Wall-type merging changes the name, never the measurement.** A facade modelled as thirty
near-identical wall types reports as thirty rows; grouped types report as one row, one
colour, one schedule line. Areas are still taken per element. The editor can *suggest*
groups from a shared prefix but never applies them on its own — a naming convention is a
convention, not a fact.

**The schedule hides two of its four fields.** Type and Area are visible, grouped by
elevation with a per-group total. Elevation and Comments are present but hidden, because
Revit can only group or filter on a field the schedule contains: Comments carries the
filter (every region the tool draws is stamped `MARKER`) and Elevation carries the
grouping. Rows are not itemised — one line per type per elevation — because a curtain wall
facade runs to thousands of panels.

## Versions

- `envelope-v1.0` — walls only, gross areas, openings not carved.

## Not yet done

- Slab edges measured as **linear** thermal bridges (linear feet, red "existing to remain"
  / cyan "infill") rather than as area.
- Mechanical louvers.
- Dormer side walls, i.e. surfaces perpendicular to the elevation.

## pyRevit note

Runs inside pyRevit's embedded IronPython. Standard library and pyRevit's bundled
libraries only — external packages are impractical in that environment. The WPF windows
are XAML loaded through `pyrevit.forms`.
