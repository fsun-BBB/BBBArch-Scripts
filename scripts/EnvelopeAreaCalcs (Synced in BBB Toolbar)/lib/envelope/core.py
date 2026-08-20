# -*- coding: utf-8 -*-
"""
Envelope Area Calculations for Energy Analysis.

Native-Revit replacement for the Rhino.Inside / Grasshopper "Envelope /
Facade Area Calculations" script. The user clicks one button and the tool
does the whole job inside Revit.

USER FLOW
---------
1. The user builds the elevation view(s) themselves.
2. They run this tool and pick the elevation(s) in the selection window.
3. A depth check dialog shows what each picked elevation currently sees (crop,
   clipping distance, scope box, wall count, and how far the frontmost wall is
   from the elevation tag). Without a depth limit an elevation looks straight
   through the building and every interior wall behind the facade gets
   measured, so the dialog offers to set the clipping plane at a distance the
   user gives in feet FROM THE ELEVATION TAG (20 = cut 20 ft in front of the
   tag), or to assign a scope box.
4. The tool reads every wall / window / door visible in each elevation
   (including from linked models), drops anything past the view's clip distance,
   drops walls seen edge-on, then keeps only the FRONT TIER: the elevation plane
   is walked in cells and each cell goes to whichever wall lies nearest the
   elevation tag, so a mass set back 40 ft is still measured over its own
   stretch of the elevation while interior walls behind the facade win nothing.
   It classifies each into a clean set of categories - like the reference sheet:
       - Wall          (masonry - one uniform color)
       - Curtain Wall
       - Window
       - Door
   Slab-edge / column conditions are NOT a wall color; they belong to the
   linear thermal-bridge overlay (a later addition).
5. It draws a colored Filled Region per element: the exact front-face outline
   where possible (arched heads preserved; a wall's face already carries its
   window/door openings as holes, so wall area is net and nothing overlaps),
   else the bounding-box rectangle (exact for rectangular windows).
6. It writes each region's area into "Type Area", the host elevation name into
   "Elevation" and its distance from the tag into "Depth from Tag" so the areas
   are schedulable, and reports area + Window/Wall Ratio per category and per
   elevation.

PARAMETERS
----------
Three instance project parameters, bound to the Filled Region ("Detail Items")
category:
    - "Type Area" (Area, instance)
    - "Elevation" (Text, instance)
    - "Depth from Tag" (Length, instance) - distance from the elevation tag
      plane to the nearest point of the element, i.e. what the front tier pass
      ranks on. Schedule it to check the tier: the facade should sit at one
      distance, anything behind it further back.

CONFIG WINDOW
-------------
A tick box per category, because what counts as envelope is a project decision,
not something to infer from geometry:
    - Curtain wall panels     (on)  glazing separates from spandrel by type name
    - Curtain wall mullions   (off) frame; its own row, out of the ratio
    - Windows and doors       (on)  carved out of their host wall, so net area
    - Slab edges              (off) OFF because many projects model the slab
                                    separately from the facade - there the
                                    category is noise
    - Columns                 (off) same reasoning
It also holds a type whitelist, the wall-type merging, and the purge.

THE ROOF CUTS THE TOP OFF
-------------------------
Nothing belongs above the roof assembly. The roof's highest point in the
elevation becomes one horizontal line, and every region is trimmed against it -
a sloped or stepped roof is NOT followed as a profile, it is reduced to its high
point, so all the regions are cut at the same height. A wall that stands proud of
the roof loses that portion; one entirely above it is not measured at all. If the
view shows no roof, nothing is trimmed and the report says so.

MERGING WALL TYPES
------------------
A facade modelled as thirty near-identical wall types reports as thirty rows.
Types put in a group report as the group: one row, one colour, one schedule
line. Measurement is unchanged - the areas are still taken per element, only the
name they add up under changes. The editor can suggest groups from the shared
start of the type names, but never applies them on its own: a naming convention
is a convention, not a fact.

SCHEDULE
--------
Two visible columns, Type and Area, grouped by elevation with a total per group.
Elevation and Comments are in the schedule but HIDDEN: Revit can only group or
filter on a field the schedule contains, so Comments carries the filter (every
region this tool draws is stamped with MARKER) and Elevation carries the
grouping. Rows are not itemised - one line per type per elevation - because a
curtain wall facade runs to thousands of panels.

TAGGED VERSIONS
---------------
envelope-v1.0 - walls only, gross areas, no openings carved.

NOT YET DONE (next)
-------------------
- Slab edges measured as LINEAR thermal bridges (linear feet, red "existing to
  remain" / cyan "infill") rather than as area.
- Mechanical Louvers; Dormer Side walls (perpendicular to the elevation).
"""

import clr
import json
import os
import time
import uuid

from pyrevit import forms, revit, script

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

from System.Collections.Generic import List

# The host handles are bound per run, not at import: this module is shared by
# three buttons and IronPython keeps it in sys.modules for the whole session, so
# binding at import would pin whichever document happened to be active first.
doc = None
uidoc = None
app = None
output = None
logger = None
SHORT_CURVE_TOL = None
MERGE_TOL = None


class Cancelled(Exception):
    """The user pressed Cancel in the progress window."""


# --- Progress ------------------------------------------------------------
#
# Drawn into the pyRevit output window as HTML, the same way the Real Ceiling
# Height tool does it, rather than as a modal progress dialog. Three reasons:
# the window is already open for the report, the Cancel button can live in it,
# and DoEvents on every update is what keeps Revit from going Not Responding
# during the long geometry passes.

_PROG = {"on": False, "caption": "", "total": 1, "step": 1, "shown": False}

_PROG_CSS = (
    ".env-prog{margin:6px 0 14px;font-family:'Segoe UI',Arial,sans-serif;}"
    ".env-prog-label{position:relative;height:20px;margin-bottom:5px;}"
    ".env-prog-text{position:absolute;left:0;top:50%;margin-top:-7px;"
    "font-size:11px;color:#888;}"
    ".env-cancel{position:absolute;right:0;top:50%;margin-top:-9px;"
    "padding:2px 9px;background:#888;color:#fff;border:none;border-radius:3px;"
    "cursor:pointer;font-size:10px;}"
    ".env-cancel:disabled{background:#ccc;cursor:default;}"
    ".env-prog-bg{background:#E8EBEF;height:4px;border-radius:2px;}"
    ".env-prog-fill{background:#2C3E50;height:4px;width:0%;border-radius:2px;}"
)

_PROG_JS = (
    "window._envCancelled=false;"
    "function envCancel(){window._envCancelled=true;"
    "var b=document.getElementById('env-cancel');"
    "if(b){b.disabled=true;b.innerHTML='Cancelling';}}"
)

_PROG_HTML = (
    '<div class="env-prog" id="env-prog">'
    '  <div class="env-prog-label">'
    '    <span class="env-prog-text" id="env-prog-text">Starting</span>'
    '    <button class="env-cancel" id="env-cancel" onclick="envCancel()">'
    '&#10005; Cancel</button>'
    '  </div>'
    '  <div class="env-prog-bg"><div class="env-prog-fill" id="env-prog-fill">'
    '</div></div>'
    '</div>'
)


def _js(code):
    """Run JS in the output window and let it repaint. Silent on failure -
    progress must never be the reason a run stops."""
    try:
        import System
        from System.Windows import Forms
        output.renderer.Document.InvokeScript(
            "eval", System.Array[object]([code]))
        Forms.Application.DoEvents()
    except Exception:
        pass


def progress_open(title):
    """Show the window with its bar before any work starts, so the user sees
    something the moment they press Run."""
    _PROG["on"] = True
    _PROG["shown"] = False
    try:
        output.set_title(title)
        output.show()
        try:
            output.window.Topmost = True
        except Exception:
            pass
        output.inject_to_head("style", _PROG_CSS)
        output.inject_script(_PROG_JS)
        output.print_html(_PROG_HTML)
        try:
            output.window.WaitReadyBrowser()
        except Exception:
            pass
        _PROG["shown"] = True
    except Exception as ex:
        _PROG["on"] = False
        if logger:
            logger.warning("Could not open the progress window: {}".format(ex))


def progress_phase(caption, total, updates=90):
    """Start a phase. `total` may be an estimate; the bar is clamped at 100%."""
    _PROG["caption"] = caption
    _PROG["total"] = max(int(total), 1)
    _PROG["step"] = max(_PROG["total"] // max(updates, 1), 1)
    progress_step(0)


def progress_step(i, note=None):
    """Report progress within the phase. True if Cancel has been pressed.

    Throttled: the browser repaints on every call, which is unusably slow for
    thousands of panels, so the window is updated about ninety times a phase.
    """
    if not _PROG["on"] or not _PROG["shown"]:
        return False
    total = _PROG["total"]
    if i and i % _PROG["step"] and i != total:
        return False                      # cheap path - no repaint, no poll
    pct = min(int(i * 100.0 / total), 100)
    text = "{} - {:,} of {:,}  ({}%)".format(
        _PROG["caption"], i, total, pct)
    if note:
        text += "  " + note
    _js("var t=document.getElementById('env-prog-text');"
        "if(t)t.innerHTML={};"
        "var b=document.getElementById('env-prog-fill');"
        "if(b)b.style.width='{}%';".format(json.dumps(text), pct))
    return progress_cancelled()


def progress_note(text, cancellable=True):
    """A caption with no percentage, for a step that cannot report progress -
    Revit committing thousands of elements, for one. Takes the Cancel button away
    when it could not be honoured anyway, rather than leaving a button that lies.
    """
    if not _PROG["on"] or not _PROG["shown"]:
        return
    _js("var t=document.getElementById('env-prog-text');"
        "if(t)t.innerHTML={};"
        "var c=document.getElementById('env-cancel');"
        "if(c)c.style.display={};".format(
            json.dumps(text), json.dumps("" if cancellable else "none")))


# How long each phase took. The bar sitting at 99% was Revit's commit, which no
# progress bar can tick through - so it gets measured and reported instead.
_TIMES = []


class Phase(object):
    """Times a phase and captions it. Use as a context manager."""

    def __init__(self, label, cancellable=True, note=None):
        self.label = label
        self.cancellable = cancellable
        self.note = note

    def __enter__(self):
        self._t0 = time.time()
        progress_note(self.note or self.label, self.cancellable)
        return self

    def __exit__(self, *args):
        _TIMES.append((self.label, time.time() - self._t0))
        return False


def timing_md():
    """One line of where the time went, so 'why was it slow' is answerable."""
    if not _TIMES:
        return []
    total = sum(s for _lbl, s in _TIMES)
    return ["_Time: {} - **{}s total**._".format(
        " | ".join("{} {:.0f}s".format(lbl, s) for lbl, s in _TIMES
                   if s >= 0.5),
        int(round(total)))]


def progress_cancelled():
    if not _PROG["on"] or not _PROG["shown"]:
        return False
    try:
        import System
        return bool(output.renderer.Document.InvokeScript(
            "eval", System.Array[object](["window._envCancelled === true"])))
    except Exception:
        return False


def progress_raise_if_cancelled():
    if progress_cancelled():
        raise Cancelled()


def progress_finish():
    """Fill the bar and take the Cancel button away - the report follows."""
    if not _PROG["on"]:
        return
    _js("var b=document.getElementById('env-prog-fill');"
        "if(b)b.style.width='100%';"
        "var c=document.getElementById('env-cancel');"
        "if(c)c.style.display='none';"
        "var t=document.getElementById('env-prog-text');"
        "if(t)t.innerHTML='Done';")
    _PROG["on"] = False


def bind_host():
    """Point the module at the active document, and clear everything that is
    per-run. Every entry point calls this.

    The reset matters as much as the binding: IronPython keeps this module for
    the whole session, so a second run would otherwise add its phases to the
    first run's timings and keep counting mullions from where it left off.
    """
    global doc, uidoc, app, output, logger, SHORT_CURVE_TOL, MERGE_TOL
    del _TIMES[:]
    _MULLIONS_SKIPPED[0] = 0
    _EDGE_DIAG.clear()
    _SCAN_CACHE.clear()
    doc = revit.doc
    uidoc = revit.uidoc
    app = doc.Application
    output = script.get_output()
    logger = script.get_logger()
    # Tessellated outline points closer than this are merged so every drawn
    # segment clears Revit's ShortCurveTolerance (else Line.CreateBound throws).
    SHORT_CURVE_TOL = app.ShortCurveTolerance
    MERGE_TOL = SHORT_CURVE_TOL * 1.5

# --- Configuration -------------------------------------------------------

# Instance project parameters written onto every Filled Region this tool
# draws. "Type Area" (not "Area") avoids the built-in read-only Area.
# Everything this tool CREATES - parameters, filled region types, schedules,
# views - is prefixed EN_, so it is obvious in a browser or a type list what came
# from here and it can all be found or purged with one search.
NEW_PREFIX = "EN_"

AREA_PARAM_NAME = NEW_PREFIX + "Type Area"
ELEV_PARAM_NAME = NEW_PREFIX + "Elevation"

# Perpendicular distance from the elevation tag plane to the NEAREST point of
# the element the region was drawn from - the number the front tier pass ranks
# on. Written out so the tier can be checked in a schedule: sort by it and the
# facade should sit at one distance, with anything behind it further back.
DEPTH_PARAM_NAME = NEW_PREFIX + "Depth from Tag"

# Token stamped into each region's Comments so a re-run can find and delete
# its own previous output instead of piling up duplicates.
MARKER = "BBB_ENVELOPE_CALC"


def _find_spf():
    """The extension's BBB_SharedParams.txt, found by walking up from this file
    rather than by counting folders - this module has moved once already."""
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        candidate = os.path.join(here, "BBB_SharedParams.txt")
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return os.path.join(here, "BBB_SharedParams.txt")


SPF_PATH = _find_spf()
SPF_GROUP = "BBB View Data"

# Roles drive behavior: walls get openings cut out (true face) and drive the
# Window/Wall Ratio denominator; windows/doors are the openings.
ROLE_WALL = "wall"
ROLE_WINDOW = "window"
ROLE_DOOR = "door"
# Slab edges and columns at the facade are linear thermal-bridge conditions, not
# wall area, so they carry their own roles: separate rows, separate colours, and
# kept out of the Window/Wall Ratio.
ROLE_SLAB = "slab"
ROLE_COLUMN = "column"
# Mullions are frame, neither glazing nor wall, so they get their own row and
# stay out of the ratio - how to allocate aluminium is the engineer's call.
ROLE_MULLION = "mullion"

LABEL_SLAB_PREFIX = "Slab: "
LABEL_COLUMN_PREFIX = "Column: "
LABEL_MULLION_PREFIX = "Mullion: "

# Opening category labels (fixed). WALLS are labelled by their WALL TYPE NAME
# instead - so slab-edge / column walls (which are thinner, distinct wall
# types) separate out automatically and reliably.
LABEL_WINDOW = "Window"
LABEL_DOOR = "Door"

# Named color palette - the single source of truth for colors. Edit RGBs
# here; add named colors as needed.
COLOR_PALETTE = {
    "Masonry Tan": (247, 197, 150),
    "Window Purple": (214, 190, 224),
    "Door Pink": (242, 155, 165),
    "Orange": (255, 140, 0),
    "Green": (60, 180, 90),
    "Blue": (0, 130, 220),
    "Teal": (0, 170, 160),
    "Gold": (230, 190, 70),
    "Violet": (150, 110, 200),
    "Slate": (120, 140, 160),
    "Glass Blue": (150, 200, 235),
    "Red": (210, 70, 70),
}

# Openings always use these; each distinct WALL TYPE cycles through the wall
# color list (deterministic by sorted type name).
OPENING_COLOR = {LABEL_WINDOW: "Window Purple", LABEL_DOOR: "Door Pink"}
WALL_COLOR_CYCLE = [
    "Masonry Tan", "Orange", "Green", "Blue", "Teal", "Gold",
    "Violet", "Slate", "Glass Blue", "Red",
]

# Read ONLY the host model - ignore all Revit links. Projects that keep the
# building shell in a link need the opposite, and a facade in an ignored link is
# invisible to every depth test in this file, so the pre-flight offers to switch
# this on when it finds links in the picked elevations (see ask_about_links).
USE_LINKS = False
_USE_LINKS_OVERRIDE = None


def use_links():
    return USE_LINKS if _USE_LINKS_OVERRIDE is None else _USE_LINKS_OVERRIDE

# --- What counts as envelope ---------------------------------------------
#
# Defaults the config window opens with; the user's answers land in OPT below.
# Slab edges and columns default OFF: plenty of projects model the slab
# separately from the facade, and there a slab-edge category is noise the user
# should not have to think about.
DRAW_OPENINGS = True
DRAW_SLAB_EDGES = False
DRAW_COLUMNS = False

# --- Curtain walls --------------------------------------------------------
#
# A curtain wall element carries NO geometry: 0 solids, 0 faces. Everything is
# on its panels. Measured as one wall it degrades to a rectangle with glass and
# spandrel lumped together; measured per panel the areas are exact AND the
# glazing separates from the opaque panels for free - no boolean subtraction of
# window openings needed, which is what a facade of window families would have
# required.
DRAW_CURTAIN_PANELS = True

# Mullions are a separate element per bar and would multiply the region count
# for a few percent of area. Off, but always REPORTED, so the gap is visible.
DRAW_MULLIONS = False

# A panel whose TYPE NAME contains one of these counts as glazing for the
# Window/Wall Ratio. It is a name test: the API cannot cheaply tell glass from
# spandrel. Edit to match the model's naming.
GLAZED_PANEL_TOKENS = ("glaz", "glass", "vision", "window")

# Runtime answers from the config window. Read through OPT everywhere, never the
# constants above - those are only the defaults it opens with.
#
# "types" is a whitelist of type names: empty means every type counts, which is
# the normal case. Non-empty means only those types are measured, for a project
# where the model holds more than the envelope you want in the numbers.
OPT = {
    "walls": True,
    "windows": DRAW_OPENINGS,
    "doors": DRAW_OPENINGS,
    "panels": DRAW_CURTAIN_PANELS,
    "mullions": DRAW_MULLIONS,
    "slab_edges": DRAW_SLAB_EDGES,
    "columns": DRAW_COLUMNS,
    "types": set(),
    # group name -> set of type names. Types in a group report as the group:
    # one row, one colour, one schedule line.
    "groups": {},
    # Detail-group identical elements (a different feature from "groups"
    # above, which merges wall TYPES into one reporting row by name): when
    # enabled, 2+ elements of the same enabled category that are the same
    # type AND the same true outline shape become instances of one Revit
    # Detail Group, so editing one instance's region edits every sibling.
    "detail_group_enabled": False,
    "detail_group_windows": False,
    "detail_group_doors": False,
    "detail_group_panels": False,
}


def type_allowed(type_name):
    """True unless a type whitelist is set and this name is not on it."""
    return not OPT["types"] or type_name in OPT["types"]


def group_label(type_name):
    """The name this type reports under - its group's, or its own.

    Grouping is a reporting decision, not a measuring one: the areas are still
    taken per element, they are just added up under one name. A facade modelled
    as thirty near-identical wall types ("...24\"_No Slab Cut", "...24\"_Slab
    Cut", "...32\"_Corbelled") is thirty rows of noise otherwise.
    """
    if not OPT["groups"]:
        return type_name
    for name in sorted(OPT["groups"]):
        if type_name in OPT["groups"][name]:
            return name
    return type_name


def suggest_groups(names, min_members=2):
    """Group name -> members, guessed by the longest shared prefix.

    Offered as a starting point in the group editor, never applied on its own:
    a naming convention is a convention, not a fact, so the user confirms it.
    Splits on the separators these type names actually use.
    """
    import re
    buckets = {}
    for n in names:
        # Cut at the last separator that still leaves a meaningful stem.
        stem = re.split(r"\s*[-_]\s*(?=[^-_]*$)", n)[0].strip()
        if not stem or stem == n.strip():
            stem = re.split(r"[-_(]", n)[0].strip()
        if not stem:
            continue
        buckets.setdefault(stem, set()).add(n)
    return dict((k, v) for k, v in buckets.items() if len(v) >= min_members)

# An elevation with no far clip / scope box looks straight through the
# building, so every interior wall behind the facade gets measured too. The
# pre-flight dialog asks for a TAG-TO-CLIP distance: the far clipping plane
# sits that many feet in front of the elevation tag. The suggested value
# reaches this far PAST the back of the frontmost wall - deep enough to keep a
# projecting bay or a wall behind a shallow canopy, shallow enough to cut the
# interior.
FAR_CLIP_MARGIN_FT = 3.0

# Offered when the view shows no wall to measure from, so there is nothing to
# base a suggestion on.
DEFAULT_TAG_TO_CLIP_FT = 20.0

# A clip reaching more than this far past the back of the frontmost wall means
# the view still looks into the building. That is legitimate when the building
# has masses at different depths - the clip must reach the furthest one - so
# this only drives a note in the dialog, never a filter. The front tier pass
# below is what actually picks the facade.
CLIP_SLACK_FT = 5.0

# --- Front tier: which layer of the building counts as "the facade" -------
#
# The elevation plane is walked in cells; at each cell the wall nearest the tag
# plane wins (see _keep_front_tier). Horizontal steps are fine because facade
# articulation is horizontal; vertical bands are coarse because they only exist
# to catch masses set back on upper floors.
TIER_STEP_U_FT = 0.5
TIER_STEP_V_FT = 2.0

# A wall must be the nearest one across at least this much width to be kept, so
# a partition poking through a gap between two facade walls does not qualify on
# a sliver. One step = keep anything that wins at all.
MIN_WIN_FT = 0.5

# --- The elevation's left and right edge ----------------------------------
#
# At a building corner the wall of the ADJACENT facade is seen end-on, as a strip
# at the extreme edge of the elevation. It is dropped and the facade beside it is
# stretched onto the edge, so the region reaches the corner.
#
# The strip's width is MEASURED, not assumed: whatever starts at the edge and is
# narrow relative to the elevation is the return, and the facade is then snapped
# by exactly that much. A fixed distance was the first attempt and it silently
# did nothing whenever the return happened to be wider than the guess.

# How close to the edge a piece must start to count as sitting on it.
EDGE_TOUCH_FT = 0.25

# A return can be at most this fraction of the elevation's width. Guards against
# treating a genuine stretch of facade that happens to start at the edge as a
# return - that one is not narrow, so it stays.
EDGE_MAX_FRAC = 0.10

# What to do with the return once the facade has been stretched over it. Dropped:
# the strip is then inside exactly one region, the stretched facade, so the
# surface is counted once and the corner reads as one clean run of facade.
# Set True to keep the return as well - it is drawn first so the facade lands on
# top of it, but the strip then sits inside two regions and its area is counted
# twice.
EDGE_KEEP_RETURNS = False


# --- Step 1: pick elevations --------------------------------------------

def pick_elevations():
    """Prompt the user to pick one or more elevation views."""
    elevations = [
        v
        for v in FilteredElementCollector(doc).OfClass(View).ToElements()
        if not v.IsTemplate and v.ViewType == ViewType.Elevation
    ]
    if not elevations:
        forms.alert(
            "No elevation views found. Create the elevation(s) first, then "
            "run this tool.",
            exitscript=True,
        )
    picked = forms.SelectFromList.show(
        sorted(elevations, key=lambda v: v.Name),
        name_attr="Name",
        title="Pick Elevation(s) to Calculate",
        multiselect=True,
        button_name="Calculate Envelope Areas",
    )
    if not picked:
        forms.alert("No elevation picked. Nothing to do.", exitscript=True)
    return picked


# --- Step 1b: clipping pre-flight (far clip / scope box) -----------------
#
# An elevation with no depth limit sees the WHOLE building: every interior
# wall behind the facade lands in the collector and gets a filled region. The
# only reliable cure is a far clip depth or a scope box on the view, and that
# is a judgement call about which layer of the building is "the facade" - so we
# show the user what each picked elevation currently sees and let them set it
# before a single region is drawn.

OPT_FAR_CLIP = "Set the clip distance from the tag"
OPT_RUN = "Run as-is"
OPT_CANCEL = "Cancel"


class _ElevationOption(forms.TemplateListItem):
    """Checkbox row for one elevation: its name plus what it currently sees.
    The label is built once - WPF re-reads `name` while scrolling, and each
    read would otherwise re-run a view collector."""

    def __init__(self, view, checked=False):
        forms.TemplateListItem.__init__(self, view, checked=checked)
        self._label = clip_state_label(view)

    @property
    def name(self):
        return self._label


def _param(view, bip):
    try:
        return view.get_Parameter(bip)
    except Exception:
        return None


def _fmt_len(ft):
    """Feet and inches, rounded to the nearest inch. Unrounded, a clip
    distance formats as 233' - 9 85/128", which is noise."""
    try:
        inches = round(ft * 12.0)
        return UnitFormatUtils.Format(
            doc.GetUnits(), SpecTypeId.Length, inches / 12.0, False)
    except Exception:
        return "{:.1f} ft".format(ft)


def far_clip_state(view):
    """(is_active, offset_in_ft) of the view's Far Clip."""
    p_act = _param(view, BuiltInParameter.VIEWER_BOUND_ACTIVE_FAR)
    p_off = _param(view, BuiltInParameter.VIEWER_BOUND_OFFSET_FAR)
    active = bool(p_act) and p_act.AsInteger() == 1
    offset = p_off.AsDouble() if p_off else 0.0
    return active, offset


def scope_box_of(view):
    """The Scope Box element assigned to `view`, or None."""
    p = _param(view, BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
    if p is None:
        return None
    eid = p.AsElementId()
    if eid is None or eid == ElementId.InvalidElementId:
        return None
    return doc.GetElement(eid)


def iter_view_category(view, bic):
    """(element, xform) for one category across the host and the read links."""
    for elem in _cat_collector(doc, bic, view, None):
        yield elem, None
    if not use_links():
        return
    for inst in get_link_instances_in_view(view):
        xform = inst.GetTotalTransform()
        bbfilter = crop_filter_for_link(view, xform)
        for elem in _cat_collector(inst.GetLinkDocument(), bic, None, bbfilter):
            yield elem, xform


def roof_top_v(view):
    """The height on the elevation of the roof's highest point, or None if the
    view shows no roof.

    Nothing belongs above the roof assembly, so this is where the regions get
    cut. A sloped or stepped roof is reduced to ONE horizontal line at its
    highest point, as asked - not followed as a profile - so the cut is a single
    v value and every region is trimmed against the same line.

    Roofs are not filtered by faces_elevation: a roof's face points up, nearly
    perpendicular to the view direction, so that test would drop every one.
    """
    limit = depth_limit(view)
    top = None
    for bic in (BuiltInCategory.OST_Roofs, BuiltInCategory.OST_RoofSoffit):
        for elem, xform in iter_view_category(view, bic):
            span = span_from_tag(elem, view, xform)
            if _span_beyond(span, limit):
                continue
            m = _elem_metrics(elem, view, xform)
            if m is None:
                continue
            v_max = m[4][3]                 # uv_rect = (umin, umax, vmin, vmax)
            if top is None or v_max > top:
                top = v_max
    return top


def iter_view_walls(view):
    """(wall, xform) for every wall this view can show - the host model, plus
    the loaded links when they are being read. `xform` places a linked wall in
    host coordinates and is None for host walls.

    Every count and diagnostic goes through here, so they describe the same set
    of walls the drawing pass works from. Without it, switching links on would
    change what gets drawn while the reported numbers stayed host-only.
    """
    for wall in _cat_collector(doc, BuiltInCategory.OST_Walls, view, None):
        yield wall, None
    if not use_links():
        return
    for inst in get_link_instances_in_view(view):
        xform = inst.GetTotalTransform()
        bbfilter = crop_filter_for_link(view, xform)
        for wall in _cat_collector(inst.GetLinkDocument(),
                                   BuiltInCategory.OST_Walls, None, bbfilter):
            yield wall, xform


def estimate_wall_count(view):
    """Roughly how many walls a pass over this view will touch - the host's, plus
    each read link's. Cheap: a collector count, no geometry."""
    n = 0
    try:
        n += (_cat_collector(doc, BuiltInCategory.OST_Walls, view, None)
              .GetElementCount())
    except Exception:
        pass
    if use_links():
        for inst in get_link_instances_in_view(view):
            try:
                ldoc = inst.GetLinkDocument()
                n += (FilteredElementCollector(ldoc)
                      .OfCategory(BuiltInCategory.OST_Walls)
                      .WhereElementIsNotElementType().GetElementCount())
            except Exception:
                pass
    return n


def _run_view_scan(view):
    limit = depth_limit(view)
    total = facing = within = 0
    front = None
    # The phase is started here rather than by the caller: this loop and the
    # collection it triggers are where the seconds go, so they have to be the
    # thing driving the bar.
    progress_phase("Scanning {}".format(view.Name), estimate_wall_count(view))
    for wall, xform in iter_view_walls(view):
        total += 1
        if progress_step(total):
            raise Cancelled()
        if not faces_elevation(wall, view, xform):
            continue
        facing += 1
        span = span_from_tag(wall, view, xform)
        # The frontmost wall is a fact about the model, so it is tracked
        # regardless of the current clip - otherwise a clip set too tight would
        # hide the very wall needed to suggest a better distance.
        if span is not None and span[1] > 0 and (front is None
                                                 or span[0] < front[0]):
            front = span
        if not _span_beyond(span, limit):
            within += 1

    # Run the real collection so the dialog can show the FRONT TIER count - the
    # number that becomes filled regions. Only the count is kept: holding the
    # elements themselves across the transactions that follow would risk stale
    # references, and collecting again at draw time costs one more pass.
    tier = 0
    try:
        items, _meta = collect_view_items(view)
        tier = sum(1 for it in items if it[1] == ROLE_WALL)
    except Exception as ex:
        logger.warning("Front tier preview failed for '{}': {}".format(
            view.Name, ex))
        tier = None
    return total, facing, within, tier, front


# Scanning walks every wall the view reports (thousands, on an overall
# elevation) and then runs a full collection, while the dialog reads the same
# numbers several times per refresh. Cached per view, dropped whenever a clip
# or scope box changes.
_SCAN_CACHE = {}


def view_scan(view):
    """The whole funnel for one elevation:
    (available, facing_the_elevation, within_the_clip, front_tier, front_span).

    The raw count is not the workload and never was: an overall elevation
    reports every partition in the building, and the great majority are seen
    edge-on. Those go first (faces_elevation), then anything past the clip
    distance, then anything behind the front tier - so `front_tier` is what
    actually becomes filled regions and the earlier numbers show where the rest
    went. Counts walls from the links too when they are being read.
    """
    key = view.UniqueId
    if key not in _SCAN_CACHE:
        _SCAN_CACHE[key] = _run_view_scan(view)
    return _SCAN_CACHE[key]


def is_depth_limited(view):
    """True if the view's depth is bounded - by an active far clip or a scope
    box. Far Clip is its OWN control on a section/elevation: it cuts the depth
    whether or not Crop View is on, so the crop state is not part of this
    test."""
    if scope_box_of(view) is not None:
        return True
    active, _ = far_clip_state(view)
    return bool(active)


def _clip_facts(view):
    """(where it clips, where the facade starts, how many pieces) as phrases.

    Three facts, because they are the only ones that answer the question this
    dialog exists for: is this elevation cutting at the right depth? The funnel
    counts behind them are diagnostics and belong in the details pane.
    """
    active, offset = far_clip_state(view)
    _t, _f, _w, tier, front = view_scan(view)
    where = ("clips {} from the tag".format(_fmt_len(offset)) if active
             else "NO clip distance - measures the whole depth")
    if front is None:
        facade = "no facade wall found"
    elif front[0] < 0:
        # The nearest wall straddles the tag plane. A negative distance reads as
        # nonsense, so say what it means.
        facade = "facade crosses the tag"
    else:
        facade = "facade starts at {}".format(_fmt_len(front[0]))
    pieces = "{} pieces to draw".format("?" if tier is None else tier)
    return where, facade, pieces


def clip_state_label(view):
    """One line for the checkbox list: name, clip, facade."""
    where, facade, _pieces = _clip_facts(view)
    return "{}   -   {} | {}".format(view.Name, where, facade)


def clip_state_row(view):
    """Two lines for the depth dialog - the name, then its three facts."""
    where, facade, pieces = _clip_facts(view)
    return "{}\n     {}   |   {}   |   {}".format(
        view.Name, where, facade, pieces)


def clip_detail_row(view):
    """The funnel, for the dialog's details pane."""
    total, facing, within, tier, front = view_scan(view)
    active, offset = far_clip_state(view)
    extra = ""
    if active and front is not None and (offset - front[1]) > CLIP_SLACK_FT:
        extra = ", clip reaches {} past the facade".format(
            _fmt_len(offset - front[1]))
    return ("{}: {} walls in the view, {} face this elevation, {} within the "
            "clip, {} pieces to draw{}".format(
                view.Name, total, facing, within,
                "?" if tier is None else tier, extra))


def needs_attention(view):
    """True if this elevation has no depth bound at all.

    A clip set deeper than the facade is NOT a defect: a building in several
    masses needs the clip past the furthest one, and the front tier pass then
    discards whatever sits behind the facade. Only a view with no bound at all
    is a problem, because a separate building further away would win the tier
    wherever the near one has no wall.
    """
    return not is_depth_limited(view)


# --- Distances measured from the elevation tag ----------------------------
#
# Revit's Far Clip Offset is measured from the elevation tag's plane (the
# view's cut plane) along the view direction into the building - so "20 ft"
# means the clipping plane sits 20 ft in front of the tag. Everything below
# uses that same origin, so every number the dialog shows is comparable:
# tag -> front wall, tag -> back of front wall, tag -> clipping plane.


def dist_from_tag(point, view):
    """How far `point` lies in FRONT of the elevation tag, in feet, measured
    along the view direction (negative = behind the tag, on the viewer's
    side). ViewDirection points toward the viewer, hence the sign flip."""
    return -(point - view.Origin).DotProduct(view.ViewDirection)


def span_from_tag(elem, view, xform=None):
    """(nearest, farthest) distance from the tag to `elem`'s bounding box, in
    feet. `xform` places a linked element into host coordinates."""
    try:
        bb = elem.get_BoundingBox(None)
    except Exception:
        return None
    if bb is None:
        return None
    ds = []
    for x in (bb.Min.X, bb.Max.X):
        for y in (bb.Min.Y, bb.Max.Y):
            for z in (bb.Min.Z, bb.Max.Z):
                p = XYZ(x, y, z)
                if xform is not None:
                    p = xform.OfPoint(p)
                ds.append(dist_from_tag(p, view))
    return min(ds), max(ds)


def depth_limit(view):
    """How deep past the tag this view is allowed to look, in feet, or None if
    nothing bounds it.

    The tool measures against this itself rather than trusting the view-based
    collector. Revit's collector does respond to the far clip, but it is not
    guaranteed to (the depth reaches it through the crop box), and the same
    number then bounds linked models and drives the reported counts - so one
    explicit test covers every path.
    """
    active, offset = far_clip_state(view)
    if active:
        return offset
    box = scope_box_of(view)
    if box is not None:
        span = span_from_tag(box, view)
        if span is not None:
            return span[1]
    return None


def _span_beyond(span, limit):
    """True if a (nearest, farthest) span lies outside what the elevation
    shows: entirely past the clipping plane, or entirely behind the tag on the
    viewer's side. A span straddling either plane is partly visible, so it is
    kept."""
    if span is None:
        return False                          # no bbox - let it through
    if span[1] <= 0:                          # entirely on the viewer's side
        return True
    return limit is not None and span[0] > limit


def beyond_depth(elem, view, xform, limit):
    return _span_beyond(span_from_tag(elem, view, xform), limit)


def front_wall_span(view):
    """(front_face, back_face) distances from the elevation tag to the
    frontmost wall FACING this elevation, in feet. Perpendicular walls are
    ignored - one partition ending near the tag would otherwise pass for the
    facade. None if the view shows no such wall."""
    return view_scan(view)[4]


def suggest_far_clip(view):
    """A tag-to-clip distance (ft) that reaches just past the BACK of the
    frontmost wall - keeps the facade, cuts the interior behind it. None if
    the view shows no wall in front of the tag."""
    span = front_wall_span(view)
    if span is None:
        return None
    return span[1] + FAR_CLIP_MARGIN_FT


def pick_views_to_change(views, action):
    """Checkbox list of the picked elevations, pre-checked on the ones that
    would still measure more than their facade. Returns the views to change
    (may be []), or None if the user cancelled."""
    opts = [
        _ElevationOption(v, checked=needs_attention(v))
        for v in sorted(views, key=lambda v: v.Name)
    ]
    return forms.SelectFromList.show(
        opts,
        title="Apply to which elevations? - {}".format(action),
        multiselect=True,
        button_name="Apply",
        width=760,
    )


def apply_far_clip(views, offset_ft):
    """Turn on Far Clip at `offset_ft` from the tag. Returns the view names
    where it could not be set. The view's Crop View setting is left alone -
    far clipping works independently of it, and switching the crop on would
    change the drawn extent of the user's elevation."""
    failed = []
    for view in views:
        p_act = _param(view, BuiltInParameter.VIEWER_BOUND_ACTIVE_FAR)
        p_off = _param(view, BuiltInParameter.VIEWER_BOUND_OFFSET_FAR)
        if (p_act is None or p_act.IsReadOnly
                or p_off is None or p_off.IsReadOnly):
            failed.append(view.Name)
            continue
        p_act.Set(1)
        p_off.Set(offset_ft)
    _SCAN_CACHE.clear()
    return failed


def _do_far_clip(views):
    """Ask which views + how far in front of the tag to clip, then set it.
    Returns True if anything changed."""
    targets = pick_views_to_change(views, "distance from elevation tag")
    if not targets:
        return False

    # Suggest the deepest of the picked views, so one number keeps every
    # facade: past the back of that view's frontmost wall.
    suggested = None
    for view in targets:
        s = suggest_far_clip(view)
        if s is not None and (suggested is None or s > suggested):
            suggested = s
    default = "{:.1f}".format(
        suggested if suggested is not None else DEFAULT_TAG_TO_CLIP_FT
    )
    answer = forms.ask_for_string(
        default=default,
        prompt="Distance in FEET from the ELEVATION TAG to the clipping "
        "plane - 20 means the view is cut 20 ft in front of the tag.",
        title="Tag to Clipping Plane",
    )
    if not answer:
        return False
    try:
        offset = float(str(answer).strip())
    except ValueError:
        forms.alert("'{}' is not a number - nothing changed.".format(answer),
                    title="Tag to Clipping Plane")
        return False
    if offset <= 0:
        forms.alert(
            "The distance must be greater than zero - nothing changed.",
            title="Tag to Clipping Plane",
        )
        return False

    t = Transaction(doc, "Set Elevation Far Clip")
    t.Start()
    try:
        failed = apply_far_clip(targets, offset)
        t.Commit()
    except Exception as ex:
        t.RollBack()
        logger.error("Could not set far clip: {}".format(ex))
        forms.alert("Could not set the far clip:\n\n{}".format(ex),
                    title="Failed", warn_icon=True)
        return False
    if failed:
        forms.alert(
            "The far clip is read-only (or missing) on:\n\n{}\n\nSet it by "
            "hand in the view's Properties, or use a scope box.".format(
                "\n".join(failed)),
            title="Far Clip Not Set",
        )

    # Read the far clip parameters straight back: that IS Revit's tag-to-clip
    # distance, so this only speaks up when the value genuinely did not stick
    # (a view template driving Far Clip Offset, for instance).
    off_target = []
    for view in targets:
        if view.Name in failed:
            continue
        active, actual = far_clip_state(view)
        if not active:
            off_target.append("{}: far clip still off".format(view.Name))
        elif abs(actual - offset) > 0.01:
            off_target.append("{}: cut at {} from the tag".format(
                view.Name, _fmt_len(actual)))
    if off_target:
        forms.alert(
            "The far clip did not take the {} asked for on:\n\n{}\n\nA view "
            "template is most likely driving Far Clip Offset on these "
            "views.".format(_fmt_len(offset), "\n".join(off_target)),
            title="Far Clip Not Applied",
        )
    return True


def ask_options():
    """Open the configuration window before a run. True if the user went ahead.

    The window itself lives in config_ui, imported here rather than at module
    level: it imports this module back, and the Configurations button loads it
    without ever needing the calculation.
    """
    from envelope import config_ui
    return config_ui.show("Run")


def ask_about_links(views):
    """Offer to read the Revit links the picked elevations show.

    The tool reads the host model only by default, and a building shell that
    lives in a link is then invisible to everything here - the front tier ends
    up ranking interior partitions because they are the only walls present. So
    when links turn up in the picked views, ask instead of silently measuring
    the wrong layer.
    """
    global _USE_LINKS_OVERRIDE
    if use_links():
        return
    titles = set()
    unloaded = set()
    uncropped = []
    for view in views:
        for inst in FilteredElementCollector(doc, view.Id).OfClass(
                RevitLinkInstance):
            ldoc = inst.GetLinkDocument()
            if ldoc is not None:
                titles.add(ldoc.Title)
            else:
                unloaded.add(_name(inst))
        if not view.CropBoxActive:
            uncropped.append(view.Name)

    if unloaded and not titles:
        # Nothing to offer: an unloaded link has no geometry to read at all.
        forms.alert(
            "The picked elevation(s) reference {} Revit link(s) that are NOT "
            "loaded, so their walls cannot be read. Load them (Manage > Manage "
            "Links > Reload) and run again.".format(len(unloaded)),
            title="Linked Model Not Loaded",
            sub_msg="\n".join(sorted(unloaded)),
            warn_icon=True,
        )
        return
    if not titles:
        return

    sub = list(sorted(titles))
    if unloaded:
        sub.append("")
        sub.append("Not loaded (cannot be read): {}".format(
            ", ".join(sorted(unloaded))))
    if forms.alert(
        "The picked elevation(s) show {} loaded Revit link(s). This tool reads "
        "the host model only, so anything modelled in a link - very often the "
        "building shell - is not measured and cannot win the front tier.".format(
            len(titles)),
        title="Read the Linked Model(s)?",
        sub_msg="\n".join(sub),
        expanded="Say No if the shell is in this model and the links are "
        "context, structure, MEP and so on. Say Yes if the walls you want "
        "measured live in a link - the tool will then read the host and the "
        "link(s) together, de-duplicating a link placed more than once.\n\n"
        "One catch: the clip distance bounds a link by DEPTH only. The view's "
        "crop region is what bounds it sideways and vertically, so with Crop "
        "View off the whole linked model is measured, not just this "
        "elevation's stretch of it."
        + ("\n\nCrop View is currently OFF on: {}".format(", ".join(uncropped))
           if uncropped else ""),
        ok=False, yes=True, no=True,
    ):
        _USE_LINKS_OVERRIDE = True
        _SCAN_CACHE.clear()


def preflight_clipping(views):
    """Show what each picked elevation currently sees and let the user set a
    far clip / scope box first. Loops so several passes are possible. Returns
    False if the user backed out."""
    ask_about_links(views)
    while True:
        # Warm the scan cache with feedback: each view walks every wall it
        # reports and runs a full collection to get its front tier count, which
        # is seconds of work on an overall elevation.
        try:
            for v in sorted(views, key=lambda v: v.Name):
                view_scan(v)
        except Cancelled:
            progress_finish()
            return False

        ordered = sorted(views, key=lambda v: v.Name)
        deep = [v for v in views if needs_attention(v)]
        pieces = sum((view_scan(v)[3] or 0) for v in views)

        if deep:
            msg = (
                "{} of these {} elevation(s) has no clip distance, so it will "
                "measure the whole depth of the building.".format(
                    len(deep), len(views))
            )
        else:
            msg = ("Compare each clip distance with where its facade starts. "
                   "If the clip is right, run.")
        choice = forms.alert(
            msg,
            title="Elevation Depth Check",
            sub_msg="\n\n".join(clip_state_row(v) for v in ordered),
            footer="{} region(s) will be drawn.".format(pieces),
            expanded="Clip distance is measured from the elevation tag toward "
            "the building, so 20 puts the cut 20 ft in front of the tag. A clip "
            "deeper than the facade is fine - whatever a nearer wall stands in "
            "front of is discarded anyway.\n\n"
            + "\n".join(clip_detail_row(v) for v in ordered),
            options=[OPT_FAR_CLIP, OPT_RUN, OPT_CANCEL],
            warn_icon=bool(deep),
        )
        if choice == OPT_FAR_CLIP:
            _do_far_clip(views)
        elif choice == OPT_RUN:
            return True
        else:                               # Cancel, Esc, or window closed
            return False


# --- Project parameters --------------------------------------------------

def _ensure_spf_definition(name, spec_type_id):
    old_spf = app.SharedParametersFilename
    if not os.path.exists(SPF_PATH):
        with open(SPF_PATH, "w") as f:
            f.write(
                "# This is a Revit shared parameter file.\n"
                "# Do not edit manually.\n"
                "*META\tVERSION\tMINVERSION\nMETA\t2\t1\n"
                "*GROUP\tID\tNAME\nGROUP\t1\t{0}\n"
                "*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\t"
                "VISIBLE\tDESCRIPTION\tUSERMODIFIABLE\tHIDEWHENNOVALUE\n".format(
                    SPF_GROUP
                )
            )
    app.SharedParametersFilename = SPF_PATH
    spf = app.OpenSharedParameterFile()
    grp = spf.Groups.get_Item(SPF_GROUP) or spf.Groups.Create(SPF_GROUP)
    defn = grp.Definitions.get_Item(name)
    if defn is None:
        opts = ExternalDefinitionCreationOptions(name, spec_type_id)
        opts.Visible = True
        opts.GUID = _new_guid()
        defn = grp.Definitions.Create(opts)
    app.SharedParametersFilename = old_spf
    return defn


def _new_guid():
    from System import Guid

    return Guid(str(uuid.uuid4()))


def filled_region_category():
    """The actual Category Filled Regions report in THIS model."""
    frt = FilteredElementCollector(doc).OfClass(FilledRegionType).FirstElement()
    if frt is not None and frt.Category is not None:
        return frt.Category
    fr = FilteredElementCollector(doc).OfClass(FilledRegion).FirstElement()
    if fr is not None and fr.Category is not None:
        return fr.Category
    return doc.Settings.Categories.get_Item(BuiltInCategory.OST_DetailComponents)


def _find_binding(param_name):
    it = doc.ParameterBindings.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        if it.Key.Name == param_name:
            return it.Key, it.Current
    return None, None


def _categories_contain(cat_set, cat):
    """Is `cat` already in this CategorySet? Compares ElementId objects
    directly - Revit 2026 removed ElementId.IntegerValue, and ElementId
    equality works in every version."""
    for c in cat_set:
        if c.Id == cat.Id:
            return True
    return False


def ensure_project_parameters(target_cat):
    """Bind Type Area (Area) and Elevation (Text) to `target_cat` as instance
    params. Idempotent. Returns True on success."""
    specs = [
        (AREA_PARAM_NAME, SpecTypeId.Area),
        (ELEV_PARAM_NAME, SpecTypeId.String.Text),
        (DEPTH_PARAM_NAME, SpecTypeId.Length),
    ]
    t = Transaction(doc, "Bind Envelope Area Parameters")
    t.Start()
    try:
        for name, spec in specs:
            defn, binding = _find_binding(name)
            if binding is not None:
                if not _categories_contain(binding.Categories, target_cat):
                    binding.Categories.Insert(target_cat)
                    doc.ParameterBindings.ReInsert(defn, binding, GroupTypeId.Data)
                continue
            defn = _ensure_spf_definition(name, spec)
            cat_set = app.Create.NewCategorySet()
            cat_set.Insert(target_cat)
            doc.ParameterBindings.Insert(
                defn, app.Create.NewInstanceBinding(cat_set), GroupTypeId.Data
            )
        t.Commit()
        return True
    except Exception as ex:
        t.RollBack()
        logger.error("Could not bind project parameters: {}".format(ex))
        forms.alert(
            "Could not create/bind the '{}' and '{}' project parameters:\n\n{}"
            .format(AREA_PARAM_NAME, ELEV_PARAM_NAME, ex),
            title="Parameter Setup Failed",
            warn_icon=True,
        )
        return False


# --- Filled region types (one colored solid-fill type per category) ------

def _name(elem):
    try:
        return Element.Name.GetValue(elem)
    except Exception:
        try:
            return elem.Name
        except Exception:
            return "Unknown"


def type_name_of(elem):
    """The construction type name of `elem` (e.g. its wall type name). Works
    for host and linked elements (type lives in the element's own document)."""
    try:
        tid = elem.GetTypeId()
        if tid is not None and tid != ElementId.InvalidElementId:
            te = elem.Document.GetElement(tid)
            if te is not None:
                return _name(te)
    except Exception:
        pass
    return _name(elem)


def is_exterior_wall(wall):
    """True only for envelope walls: WallType.Function == Exterior. Drops
    interior / core / party / foundation / retaining / soffit walls."""
    try:
        return wall.WallType.Function == WallFunction.Exterior
    except Exception:
        return False


def faces_elevation(wall, view, xform):
    """True if the wall's face is turned toward this elevation (so you SEE a
    face, not an edge). A wall running perpendicular to the elevation is seen
    edge-on and is dropped. Curved/oriention-less walls are kept."""
    try:
        o = wall.Orientation            # exterior normal, perpendicular to wall
        if xform is not None:
            o = xform.OfVector(o)
        return abs(o.DotProduct(view.ViewDirection)) >= 0.5
    except Exception:
        return True


def opening_host_wall(inst):
    """The host wall of a window/door IF it's an exterior wall, else None."""
    try:
        host = inst.Host
    except Exception:
        host = None
    if isinstance(host, Wall) and is_exterior_wall(host):
        return host
    return None


def get_filled_region_type_id():
    frt = FilteredElementCollector(doc).OfClass(FilledRegionType).FirstElement()
    return frt.Id if frt is not None else None


def _solid_fill_pattern_id():
    for fp in FilteredElementCollector(doc).OfClass(FillPatternElement):
        pat = fp.GetFillPattern()
        if pat.IsSolidFill and pat.Target == FillPatternTarget.Drafting:
            return fp.Id
    for fp in FilteredElementCollector(doc).OfClass(FillPatternElement):
        if fp.GetFillPattern().IsSolidFill:
            return fp.Id
    return ElementId.InvalidElementId


def _apply_type_style(frt, rgb, solid):
    """Force a FilledRegionType to the given solid color (foreground and
    background), not masking - applied every run so color edits always take."""
    color = Color(rgb[0], rgb[1], rgb[2])
    if solid != ElementId.InvalidElementId:
        frt.ForegroundPatternId = solid
        frt.BackgroundPatternId = solid
    frt.ForegroundPatternColor = color
    frt.BackgroundPatternColor = color
    frt.IsMasking = False


def assign_colors(label_roles):
    """Map each category label to a palette color NAME, given {label: role}.

    Glazing gets a glass colour and doors a door colour by ROLE, not by name -
    a curtain wall's glazed panels are called things like "System Panel: Glazed",
    never "Window". Opaque types cycle through WALL_COLOR_CYCLE, deterministic
    on the sorted label order so a type keeps its colour across runs.
    """
    color_of = {}
    wi = 0
    for label in sorted(label_roles):
        role = label_roles[label]
        if label in OPENING_COLOR:
            color_of[label] = OPENING_COLOR[label]
        elif role == ROLE_WINDOW:
            color_of[label] = "Glass Blue"
        elif role == ROLE_DOOR:
            color_of[label] = OPENING_COLOR[LABEL_DOOR]
        elif role == ROLE_SLAB:
            color_of[label] = "Red"
        elif role == ROLE_COLUMN:
            color_of[label] = "Teal"
        elif role == ROLE_MULLION:
            color_of[label] = "Slate"
        else:
            color_of[label] = WALL_COLOR_CYCLE[wi % len(WALL_COLOR_CYCLE)]
            wi += 1
    return color_of


_ILLEGAL_TYPE_CHARS = ':{}[]|;<>?`~'


def _safe_type_name(s):
    for ch in _ILLEGAL_TYPE_CHARS:
        s = s.replace(ch, "-")
    return s


def ensure_region_types(base_id, color_of):
    """Ensure a colored solid-fill FilledRegionType 'ENV - <label> - <color>'
    exists for each label and is re-styled to its palette color every run.
    Returns {label: typeId}. Must run in a transaction."""
    existing = {}
    for frt in FilteredElementCollector(doc).OfClass(FilledRegionType):
        existing[_name(frt)] = frt
    base = doc.GetElement(base_id)
    solid = _solid_fill_pattern_id()

    type_ids = {}
    for label, color_name in color_of.items():
        rgb = COLOR_PALETTE[color_name]
        tname = "{}{} - {}".format(
            NEW_PREFIX, _safe_type_name(label), color_name)
        try:
            frt = existing.get(tname)
            if frt is None:
                frt = base.Duplicate(tname)
            _apply_type_style(frt, rgb, solid)
            type_ids[label] = frt.Id
        except Exception as ex:
            logger.warning("Could not create/update region type '{}': {}".format(
                tname, ex))
            type_ids[label] = base_id
    return type_ids


# --- Step 2: classify by category ----------------------------------------
# Walls are labelled by their WALL TYPE NAME, so distinct (thinner) slab-edge /
# column wall types separate out automatically and reliably.


# --- Geometry: true element outline projected onto the elevation plane ---
#
# We take the element's real face that looks at the elevation (its silhouette)
# and use that face's actual edge loops - so arched heads, chamfers, etc. are
# preserved, and a wall's face already contains its window/door openings as
# inner loops (net area comes for free, exact, no manual boolean).

def _iter_solids(geo):
    for g in geo:
        if isinstance(g, Solid):
            if g.Faces.Size > 0 and g.Volume > 1e-9:
                yield g
        elif isinstance(g, GeometryInstance):
            for s in _iter_solids(g.GetInstanceGeometry()):
                yield s


def _front_face(elem, view, xform):
    """The planar face most squarely facing the viewer (largest area x
    facing-ness). None if the element has no suitable planar face."""
    opt = Options()
    opt.DetailLevel = ViewDetailLevel.Fine
    opt.ComputeReferences = False
    try:
        geo = elem.get_Geometry(opt)
    except Exception:
        return None
    if geo is None:
        return None

    vdir = view.ViewDirection  # points toward the viewer
    best = None
    best_score = 0.0
    for solid in _iter_solids(geo):
        for f in solid.Faces:
            if not isinstance(f, PlanarFace):
                continue
            n = f.FaceNormal
            if xform is not None:
                n = xform.OfVector(n)
            dot = n.DotProduct(vdir)
            if dot <= 0.5:            # must genuinely face the viewer
                continue
            score = f.Area * dot
            if score > best_score:
                best_score = score
                best = f
    return best


def _proj_uv(p, view, xform):
    """Project a model point to (u, v) on the elevation plane."""
    if xform is not None:
        p = xform.OfPoint(p)
    d = p - view.Origin
    return (d.DotProduct(view.RightDirection), d.DotProduct(view.UpDirection))


def _uv_to_xyz(uv, view):
    return (
        view.Origin
        + view.RightDirection.Multiply(uv[0])
        + view.UpDirection.Multiply(uv[1])
    )


def _uv_dist(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5


def _merge_uv_points(raw):
    """Drop points closer than MERGE_TOL, including a closing point that
    coincides with the start, so every segment clears Revit's short-curve
    tolerance and Line.CreateBound will take it."""
    pts = []
    for uv in raw:
        if not pts or _uv_dist(pts[-1], uv) > MERGE_TOL:
            pts.append(uv)
    while len(pts) >= 2 and _uv_dist(pts[0], pts[-1]) <= MERGE_TOL:
        pts.pop()
    return pts


def _loop_uv_points(curveloop, view, xform):
    """Tessellate a CurveLoop and project to a list of (u, v) points (arcs become
    fine polylines - visually exact)."""
    raw = []
    for c in curveloop:
        for p in c.Tessellate():
            raw.append(_proj_uv(p, view, xform))
    return _merge_uv_points(raw)


def clip_below(pts, v_cut):
    """The part of a polygon at or below `v_cut`, or [] if none of it is.

    Sutherland-Hodgman against one horizontal half-plane: walk the edges, keep
    the points below the line, and add the crossing point wherever an edge cuts
    it. Works on a concave outline as well as a rectangle, which matters because
    a wall's true face is whatever shape Revit gives us.
    """
    if v_cut is None or not pts:
        return pts
    out = []
    n = len(pts)
    for i in range(n):
        cur = pts[i]
        nxt = pts[(i + 1) % n]
        cur_in = cur[1] <= v_cut
        if cur_in:
            out.append(cur)
        if cur_in != (nxt[1] <= v_cut):
            dv = nxt[1] - cur[1]
            t = (v_cut - cur[1]) / dv if abs(dv) > 1e-12 else 0.0
            out.append((cur[0] + (nxt[0] - cur[0]) * t, v_cut))
    out = _merge_uv_points(out)
    return out if len(out) >= 3 else []


def snap_to_edges(pts, edges):
    """Pull points that sit within the measured return band of the elevation's
    left or right edge onto that edge, so a facade whose corner return was
    dropped still reaches the corner.

    Applied to OUTER boundaries only - snapping a hole would stretch a window
    near the corner out to the edge.
    """
    if not edges:
        return pts
    u_left, u_right, snap_left, snap_right = edges
    out = []
    for uv in pts:
        u = uv[0]
        if snap_left > 0 and u <= u_left + snap_left:
            u = u_left
        elif snap_right > 0 and u >= u_right - snap_right:
            u = u_right
        out.append((u, uv[1]))
    # Snapping can land two points on top of each other; re-merge or the loop
    # gets a zero-length segment.
    return _merge_uv_points(out)


def _signed_area(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def _pts_to_loop(pts, view):
    """Build a closed CurveLoop through pre-merged points (all consecutive
    pairs, incl. wrap-around, are > MERGE_TOL apart, so every segment is legal
    and the loop stays contiguous)."""
    loop = CurveLoop()
    n = len(pts)
    for i in range(n):
        a = _uv_to_xyz(pts[i], view)
        b = _uv_to_xyz(pts[(i + 1) % n], view)
        loop.Append(Line.CreateBound(a, b))
    return loop


def _wall_exterior_face(wall):
    """The wall's actual EXTERIOR side face (largest, if a jogged wall gives
    several). Its edge loops are the real window/door openings in that wall -
    far more reliable than guessing the frontmost planar face."""
    best = None
    best_area = 0.0
    try:
        refs = HostObjectUtils.GetSideFaces(wall, ShellLayerType.Exterior)
        for r in refs:
            f = wall.GetGeometryObjectFromReference(r)
            if f is not None and f.Area > best_area:
                best_area = f.Area
                best = f
    except Exception:
        pass
    return best


def stacked_members(wall):
    """The member walls of a stacked wall, or [].

    A stacked wall element carries NO geometry of its own - Revit puts it on the
    members - so asking it for a face returns nothing and the outline silently
    degrades to a bounding box. The members are real walls with real faces.
    """
    try:
        if not wall.IsStackedWall:
            return []
    except Exception:
        return []
    out = []
    try:
        for mid in wall.GetStackedWallMemberIds():
            member = wall.Document.GetElement(mid)
            if member is not None:
                out.append(member)
    except Exception as ex:
        logger.warning("Could not read stacked wall {}: {}".format(wall.Id, ex))
    return out


def face_failure_note(elem, view, xform):
    """(note, solid_count) - why no face turned toward the elevation could be
    found. Reports what the geometry actually contains instead of guessing,
    because the cure differs: a stacked wall needs its members, a curtain wall
    its panels, a curved wall has no planar face at all, and an element with no
    solids at all has nothing to measure."""
    notes = []
    try:
        if elem.IsStackedWall:
            notes.append("STACKED wall (geometry lives on its member walls)")
    except Exception:
        pass
    try:
        if elem.CurtainGrid is not None:
            notes.append("CURTAIN wall (geometry lives on its panels)")
    except Exception:
        pass

    solids = planar = 0
    best_dot = None
    try:
        opt = Options()
        opt.DetailLevel = ViewDetailLevel.Fine
        opt.ComputeReferences = False
        geo = elem.get_Geometry(opt)
        if geo is not None:
            for solid in _iter_solids(geo):
                solids += 1
                for f in solid.Faces:
                    if not isinstance(f, PlanarFace):
                        continue
                    planar += 1
                    n = f.FaceNormal
                    if xform is not None:
                        n = xform.OfVector(n)
                    d = n.DotProduct(view.ViewDirection)
                    if best_dot is None or d > best_dot:
                        best_dot = d
    except Exception as ex:
        notes.append("geometry read failed: {}".format(_why(ex)))
    notes.append("{} solid(s), {} planar face(s), best facing dot {}".format(
        solids, planar,
        "n/a" if best_dot is None else "{:.2f}".format(best_dot)))
    return "; ".join(notes), solids


def outline_pieces(elem, view, xform, edges=None, v_cut=None):
    """[(loops, area)] for `elem` as seen in `view` - one entry per face that
    makes up its front outline, or [] if none could be built.

    Normally a single piece: the element's own front face. A STACKED wall has no
    geometry of its own, so each member wall contributes a piece; the caller
    keeps the stacked assembly's type name as the label, so the report still
    reads as one facade type while the areas come from the real faces.
    """
    members = stacked_members(elem)
    if members:
        pieces = []
        for member in members:
            built = outline_loops(member, view, xform, edges, v_cut)
            if built is not None:
                pieces.append(built)
        if pieces:
            return pieces
    built = outline_loops(elem, view, xform, edges, v_cut)
    return [built] if built is not None else []


def outline_loops(elem, view, xform, edges=None, v_cut=None):
    """Return (loops, net_area) for `elem` as seen in `view`, or None.
    loops[0] is the outer boundary (CCW), the rest are holes (CW); net_area is
    outer minus holes in square feet."""
    face = None
    if isinstance(elem, Wall):
        face = _wall_exterior_face(elem)   # real openings, correct position
    if face is None:
        face = _front_face(elem, view, xform)
    if face is None:
        return None

    raw = []
    for lp in face.GetEdgesAsCurveLoops():
        pts = _loop_uv_points(lp, view, xform)
        if len(pts) >= 3:
            raw.append(pts)
    if not raw:
        return None

    raw.sort(key=lambda p: abs(_signed_area(p)), reverse=True)
    outer = clip_below(snap_to_edges(raw[0], edges), v_cut)
    if len(outer) < 3:
        return None                       # entirely above the roof
    if _signed_area(outer) < 0:            # outer must wind CCW
        outer = list(reversed(outer))
    area = abs(_signed_area(outer))

    if not (OPT["windows"] or OPT["doors"]):
        # Gross fill: outer boundary only, openings included in the area.
        return [_pts_to_loop(outer, view)], area

    # Net fill: the wall's own face already carries its window and door openings
    # as INNER loops, so the boolean difference is Revit's own topology rather
    # than a geometric operation - exact, and no risk of a subtraction that
    # misses an arched head. Holes must wind opposite to the outer loop.
    loops = [_pts_to_loop(outer, view)]
    for pts in raw[1:]:
        pts = clip_below(pts, v_cut)
        if not pts:
            continue                      # the opening was above the roof
        hole_area = abs(_signed_area(pts))
        if hole_area <= MERGE_TOL:
            continue
        if _signed_area(pts) > 0:          # holes wind CW against a CCW outer
            pts = list(reversed(pts))
        loops.append(_pts_to_loop(pts, view))
        area -= hole_area
    return loops, max(area, 0.0)


def _bbox_uv_rect(elem, view, xform, edges=None, v_cut=None):
    """(umin, umax, vmin, vmax) of elem's projected bounding box, with the same
    corner-return edge snap bbox_loops applies - the rectangle bbox_loops
    would draw. `v_cut`, if given, clips vmax to the roof-trim cut plane, same
    as bbox_loops. None if degenerate. Split out of bbox_loops so the detail-
    group shape signature (see _shape_signature) can agree with it on what
    "this element's rectangle" means, without computing it twice."""
    bb = _elem_bbox(elem, view, xform)
    if bb is None:
        return None
    us = []
    vs = []
    for x in (bb.Min.X, bb.Max.X):
        for y in (bb.Min.Y, bb.Max.Y):
            for z in (bb.Min.Z, bb.Max.Z):
                uv = _proj_uv(XYZ(x, y, z), view, xform)
                us.append(uv[0])
                vs.append(uv[1])
    umin, umax, vmin, vmax = min(us), max(us), min(vs), max(vs)
    if edges:
        u_left, u_right, snap_left, snap_right = edges
        if snap_left > 0 and umin <= u_left + snap_left:
            umin = u_left
        if snap_right > 0 and umax >= u_right - snap_right:
            umax = u_right
    if v_cut is not None:
        vmax = min(vmax, v_cut)
    if (umax - umin) <= MERGE_TOL or (vmax - vmin) <= MERGE_TOL:
        return None                       # nothing left below the roof
    return umin, umax, vmin, vmax


def bbox_loops(elem, view, xform, edges=None, v_cut=None):
    """Fallback outline: the element's projected bounding-box rectangle. Used
    when the true front face can't be extracted (odd families). For rectangular
    windows this is exact anyway. Returns (loops, area) or None."""
    rect = _bbox_uv_rect(elem, view, xform, edges, v_cut)
    if rect is None:
        return None
    umin, umax, vmin, vmax = rect
    pts = [(umin, vmin), (umax, vmin), (umax, vmax), (umin, vmax)]
    return [_pts_to_loop(pts, view)], (umax - umin) * (vmax - vmin)


# --- Detail grouping: is this element identical to another one? ----------
#
# "Identical" means same type name AND same true outline shape - not just the
# same overall bounding box, so a panel with a notch or cut corner never gets
# silently lumped in with a plain rectangular one of the same bbox size. Only
# used to decide whether elements can share one Detail Group; it never changes
# what gets DRAWN (still the bbox rectangle for these categories, exactly as
# today) or how area is measured.

GROUP_SHAPE_TOL_FT = 1e-3   # ~1/64" - swallows tessellation/float noise only,
                            # never intended to merge genuinely different sizes


def _true_shape_loops(elem, view, xform, edges=None):
    """(outer_pts, [hole_pts, ...]) for elem's own front face, in UV - the same
    face-finding as outline_loops, but without the wall-specific exterior-face
    lookup or the OPT-gated hole carving (a grouping decision always accounts
    for a hole/notch, regardless of whether wall net-area carving is on).
    None if no usable face."""
    face = _front_face(elem, view, xform)
    if face is None:
        return None
    raw = []
    for lp in face.GetEdgesAsCurveLoops():
        pts = _loop_uv_points(lp, view, xform)
        if len(pts) >= 3:
            raw.append(pts)
    if not raw:
        return None
    raw.sort(key=lambda p: abs(_signed_area(p)), reverse=True)
    outer = snap_to_edges(raw[0], edges)
    if len(outer) < 3:
        return None
    return outer, raw[1:]


def _normalize_shape(outer, holes):
    """Translate every point so the shape's own bbox min sits at (0, 0), then
    round - two identical shapes compare equal wherever they sit on the
    elevation, while two genuinely different sizes still compare unequal.
    Sorting the points makes the comparison independent of where the outline
    happened to start and which way it wound."""
    all_pts = outer + [p for h in holes for p in h]
    u0 = min(p[0] for p in all_pts)
    v0 = min(p[1] for p in all_pts)

    def norm(pts):
        return tuple(sorted(
            (round(p[0] - u0, 3), round(p[1] - v0, 3)) for p in pts))

    return norm(outer), tuple(sorted(norm(h) for h in holes))


def _shape_signature(elem, view, xform, edges=None, v_cut=None):
    """A hashable, translation-independent description of elem's true front
    outline (outer boundary plus any hole, e.g. a notch or a cut corner) -
    used only to decide whether two elements are identical enough to share
    one Detail Group. Falls back to the plain bounding-box rectangle when no
    usable face is found, same fallback philosophy as bbox_loops. `v_cut` is
    threaded into that fallback so a window trimmed by the roof cut plane
    never buckets together with an untrimmed one of the same nominal size -
    their drawn rectangles would no longer match. None if neither works."""
    built = _true_shape_loops(elem, view, xform, edges)
    if built is not None:
        outer, holes = built
        holes = [h for h in holes if abs(_signed_area(h)) > MERGE_TOL]
        return _normalize_shape(outer, holes)
    rect = _bbox_uv_rect(elem, view, xform, edges, v_cut)
    if rect is None:
        return None
    umin, umax, vmin, vmax = rect
    outer = [(umin, vmin), (umax, vmin), (umax, vmax), (umin, vmax)]
    return _normalize_shape(outer, [])


# --- Region params, cleanup, verification --------------------------------

def set_region_params(region, area, elevation_name, depth=None):
    p_area = region.LookupParameter(AREA_PARAM_NAME)
    if p_area and not p_area.IsReadOnly:
        p_area.Set(area)
    p_elev = region.LookupParameter(ELEV_PARAM_NAME)
    if p_elev and not p_elev.IsReadOnly:
        p_elev.Set(elevation_name)
    if depth is not None:
        p_depth = region.LookupParameter(DEPTH_PARAM_NAME)
        if p_depth and not p_depth.IsReadOnly:
            p_depth.Set(depth)
    p_cmt = region.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p_cmt and not p_cmt.IsReadOnly:
        p_cmt.Set(MARKER)


def _delete_regions(regions):
    """Delete these FilledRegions. One that is a Detail Group member this tool
    placed is removed by deleting its GroupId instead - this tool never puts
    more than one region in a placed group instance, so that removes exactly
    this region and nothing else, without leaving an orphaned empty instance
    behind. Returns (done, blocked) counts."""
    deleted_groups = set()
    done = blocked = 0
    for fr in regions:
        gid = fr.GroupId
        try:
            if gid is not None and gid != ElementId.InvalidElementId:
                if gid not in deleted_groups:
                    doc.Delete(gid)
                    deleted_groups.add(gid)
            else:
                doc.Delete(fr.Id)
            done += 1
        except Exception:
            blocked += 1
    return done, blocked


def clear_previous_regions(view):
    regions = []
    for fr in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
        p = fr.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p and p.AsString() == MARKER:
            regions.append(fr)
    done, _blocked = _delete_regions(regions)
    return done


def verify_view_params(view):
    n = area_bound = area_set = area_zero = elev_bound = elev_set = 0
    for fr in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
        p = fr.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if not (p and p.AsString() == MARKER):
            continue
        n += 1
        pa = fr.LookupParameter(AREA_PARAM_NAME)
        if pa is not None:
            area_bound += 1
            if pa.HasValue:
                area_set += 1
                if abs(pa.AsDouble()) < 1e-6:
                    area_zero += 1
        pe = fr.LookupParameter(ELEV_PARAM_NAME)
        if pe is not None:
            elev_bound += 1
            if pe.HasValue and pe.AsString():
                elev_set += 1
    return n, area_bound, area_set, area_zero, elev_bound, elev_set


# --- Linked models -------------------------------------------------------

def get_link_instances_in_view(view):
    """Link instances to read. Prefer the ones actually SHOWN in this view
    (view-restricted collector) so drawn regions line up with the linework you
    see; fall back to doc-wide only if the view returns none. De-dupe by link
    DOCUMENT so a building placed more than once is processed only ONCE."""
    shown = [
        i for i in FilteredElementCollector(doc, view.Id).OfClass(RevitLinkInstance)
        if i.GetLinkDocument() is not None
    ]
    pool = shown if shown else [
        i for i in FilteredElementCollector(doc).OfClass(RevitLinkInstance)
        if i.GetLinkDocument() is not None
    ]

    insts = []
    seen_docs = set()
    for inst in pool:
        ld = inst.GetLinkDocument()
        key = ld.PathName or ld.Title
        if key in seen_docs:
            continue
        seen_docs.add(key)
        insts.append(inst)
    return insts


def crop_filter_for_link(view, link_transform):
    """BoundingBoxIntersectsFilter (in link coords) covering the host view's
    crop region, or None if the view has no active crop box."""
    if not view.CropBoxActive:
        return None
    cb = view.CropBox
    if cb is None:
        return None
    inv = link_transform.Inverse
    pts = []
    for x in (cb.Min.X, cb.Max.X):
        for y in (cb.Min.Y, cb.Max.Y):
            for z in (cb.Min.Z, cb.Max.Z):
                pts.append(inv.OfPoint(cb.Transform.OfPoint(XYZ(x, y, z))))
    xs = [p.X for p in pts]
    ys = [p.Y for p in pts]
    zs = [p.Z for p in pts]
    return BoundingBoxIntersectsFilter(
        Outline(XYZ(min(xs), min(ys), min(zs)), XYZ(max(xs), max(ys), max(zs)))
    )


# --- Step 2b: collect items from host + links ----------------------------

def _cat_collector(source_doc, bic, view_for_host, bbfilter):
    if view_for_host is not None:
        return (
            FilteredElementCollector(source_doc, view_for_host.Id)
            .OfCategory(bic)
            .WhereElementIsNotElementType()
        )
    col = FilteredElementCollector(source_doc).OfCategory(bic).WhereElementIsNotElementType()
    if bbfilter is not None:
        col = col.WherePasses(bbfilter)
    return col


def _elem_bbox(elem, view, xform):
    """The element's MODEL bounding box (world coords, identity transform).
    Using get_BoundingBox(view) is wrong here - its Min/Max are in the view's
    own coordinate system, which corrupted the front/back depth used for
    occlusion."""
    return elem.get_BoundingBox(None)


def _elem_metrics(elem, view, xform):
    """(depth_w, uv_area) for `elem`: depth along the viewing axis (larger =
    closer to viewer) and its projected bounding-box area (a cheap size proxy
    used to weight facade planes). None if no bbox."""
    bb = _elem_bbox(elem, view, xform)
    if bb is None:
        return None
    o = view.Origin
    r = view.RightDirection
    up = view.UpDirection
    vd = view.ViewDirection
    us = []
    vs = []
    ws = []
    for x in (bb.Min.X, bb.Max.X):
        for y in (bb.Min.Y, bb.Max.Y):
            for z in (bb.Min.Z, bb.Max.Z):
                p = XYZ(x, y, z)
                if xform is not None:
                    p = xform.OfPoint(p)
                d = p.Subtract(o)
                us.append(d.DotProduct(r))
                vs.append(d.DotProduct(up))
                ws.append(d.DotProduct(vd))
    w = sum(ws) / 8.0
    umin, umax, vmin, vmax = min(us), max(us), min(vs), max(vs)
    area = (umax - umin) * (vmax - vmin)
    cu = (umin + umax) / 2.0
    cv = (vmin + vmax) / 2.0
    return w, area, cu, cv, (umin, umax, vmin, vmax)


def curtain_grid_of(wall):
    """The wall's CurtainGrid, or None for a normal wall."""
    try:
        return wall.CurtainGrid
    except Exception:
        return None


def _grid_elements(wall, ids):
    out = []
    for eid in ids:
        if eid is None or eid == ElementId.InvalidElementId:
            continue
        elem = wall.Document.GetElement(eid)
        if elem is not None:
            out.append(elem)
    return out


def curtain_panels(wall):
    """(panels, mullions) for a curtain wall. A panel is either a Panel family
    instance (glazing, custom panels) or a Wall - Revit allows a basic wall type
    as a panel, which is how brick spandrels are usually built."""
    grid = curtain_grid_of(wall)
    if grid is None:
        return [], []
    panels = []
    mullions = []
    try:
        panels = _grid_elements(wall, grid.GetPanelIds())
    except Exception as ex:
        logger.warning("Could not read curtain panels of {}: {}".format(
            wall.Id, ex))
    try:
        mullions = _grid_elements(wall, grid.GetMullionIds())
    except Exception:
        pass
    return panels, mullions


def panel_role(type_name):
    """Glazing or opaque, from the panel type name (see GLAZED_PANEL_TOKENS)."""
    low = type_name.lower()
    for token in GLAZED_PANEL_TOKENS:
        if token in low:
            return ROLE_WINDOW
    return ROLE_WALL


# Mullions not measured this run, so the report can say so instead of leaving a
# few percent of facade area silently missing.
_MULLIONS_SKIPPED = [0]


def _collect_from(items, source_doc, view, view_for_host, bbfilter, xform,
                  limit, walked=None):
    """Append (label, role, element, xform, depth_w, uv_area) for walls/
    windows/doors from one source. Walls are labelled by their type name, and a
    curtain wall contributes one item per PANEL instead of one for itself.
    Geometry is read later, at draw time. Anything past `limit` feet from the
    elevation tag is dropped here - Revit's collector will not do it for us.
    Returns how many elements the clip distance dropped."""
    dropped = [0]

    def add(elem, label, role, wall_uid, is_panel=False):
        if not type_allowed(type_name_of(elem)):
            return
        span = span_from_tag(elem, view, xform)
        if _span_beyond(span, limit):
            dropped[0] += 1
            return
        m = _elem_metrics(elem, view, xform)
        if m is not None:
            # tuple: (label, role, elem, xform, depth_w, uv_area, wall_uid,
            #         center_u, center_v, uv_rect, near_dist, is_panel).
            # wall_uid ties openings to their host wall; center_u/v de-dupe;
            # uv_rect is the strip of elevation it covers; near_dist is its
            # distance to the tag plane, which decides the front tier;
            # is_panel marks a curtain wall panel, since panel_role() can
            # return ROLE_WALL for an opaque panel - the same role literal
            # walls use - so this is the only way to tell the two apart for
            # detail-group bucketing.
            items.append((label, role, elem, xform, m[0], m[1], wall_uid,
                          m[2], m[3], m[4],
                          span[0] if span is not None else None, is_panel))

    mullions_skipped = [0]
    for elem in _cat_collector(source_doc, BuiltInCategory.OST_Walls, view_for_host, bbfilter):
        if walked is not None:
            walked[0] += 1
            if progress_step(walked[0]):
                raise Cancelled()
        # Keep walls that FACE this elevation (drop edge-on). Do NOT filter by
        # Function - the facade has walls that aren't marked Exterior (e.g.
        # "Chase - GWB..."). Hidden interior walls are removed later by the
        # frontmost/occlusion pass, not by Function.
        if not faces_elevation(elem, view, xform):
            continue

        # A curtain wall has no geometry of its own, so measure its panels. They
        # keep the parent's UniqueId as their group key, which makes the front
        # tier rank the whole system as one thing (see _keep_front_tier) - panels
        # do not compete with each other or with their own parent.
        if OPT["panels"]:
            panels, mullions = curtain_panels(elem)
            if panels:
                for panel in panels:
                    tname = type_name_of(panel)
                    add(panel, group_label(tname), panel_role(tname),
                        elem.UniqueId, is_panel=True)
                if OPT["mullions"]:
                    for mullion in mullions:
                        add(mullion,
                            LABEL_MULLION_PREFIX
                            + group_label(type_name_of(mullion)),
                            ROLE_MULLION, elem.UniqueId)
                else:
                    mullions_skipped[0] += len(mullions)
                continue

        if OPT["walls"]:
            add(elem, group_label(type_name_of(elem)), ROLE_WALL, elem.UniqueId)

    if mullions_skipped[0] and not OPT["mullions"]:
        _MULLIONS_SKIPPED[0] += mullions_skipped[0]

    # Slab edges and columns: same machinery as walls, so they are ranked by the
    # front tier too - a slab band standing proud of the facade wins its strip,
    # a slab behind the curtain wall loses and is not measured.
    if OPT["slab_edges"]:
        for elem in _cat_collector(source_doc, BuiltInCategory.OST_Floors,
                                   view_for_host, bbfilter):
            add(elem, LABEL_SLAB_PREFIX + group_label(type_name_of(elem)),
                ROLE_SLAB, elem.UniqueId)
    if OPT["columns"]:
        for bic in (BuiltInCategory.OST_StructuralColumns,
                    BuiltInCategory.OST_Columns):
            for elem in _cat_collector(source_doc, bic, view_for_host, bbfilter):
                add(elem, LABEL_COLUMN_PREFIX + group_label(type_name_of(elem)),
                    ROLE_COLUMN, elem.UniqueId)

    # Openings are grouped with their host wall, so they survive the front tier
    # exactly when it does, and outline_loops() carves them out of the wall's
    # region so the wall area is net and nothing is counted twice.
    if OPT["windows"]:
        for elem in _cat_collector(source_doc, BuiltInCategory.OST_Windows,
                                   view_for_host, bbfilter):
            host = opening_host_wall(elem)
            if host is None:
                continue
            add(elem, LABEL_WINDOW, ROLE_WINDOW, host.UniqueId)
    if OPT["doors"]:
        for elem in _cat_collector(source_doc, BuiltInCategory.OST_Doors,
                                   view_for_host, bbfilter):
            host = opening_host_wall(elem)
            if host is None:
                continue
            add(elem, LABEL_DOOR, ROLE_DOOR, host.UniqueId)
    return dropped[0]


def _keep_front_tier(items):
    """Keep only the wall nearest the elevation tag at each position on the
    elevation - the front tier, i.e. the facade.

    Depth alone cannot pick the facade: a building in several masses NEEDS the
    far clip set past the furthest mass, or that wing drops out of the
    elevation entirely. So instead of ranking by depth globally, the elevation
    plane is walked in cells. Every wall knows the strip of that plane it covers
    (uv_rect) and how far its NEAREST point lies from the tag plane (near_dist,
    index 10). Each cell is won by whichever wall is nearest; a wall survives if
    it wins at least MIN_WIN_FT of width. So:

      - a wing set back 40 ft still gets measured, over its own stretch of the
        elevation, because nothing nearer covers those cells;
      - an interior partition behind a nearer wall wins nothing and is dropped,
        which the old pairwise test could not do - a long partition is covered
        by SEVERAL facade walls, by no single one of them.

    Cells are fine horizontally and coarse vertically. Pure per-column ranking
    (the plan-view version of this test) would drop a mass set back only on
    upper floors, since a nearer wall lower down would claim the whole column -
    that is real envelope area, so the vertical band keeps it. Setting
    TIER_STEP_V_FT very large reduces this to the plain per-column test.

    Ranking is per GROUP (index 6), not per element. A curtain wall's panels all
    share their parent's key, so the system is ranked as one thing: panels never
    compete with each other, a mullion gap cannot let a partition behind show
    through on a sliver, and the whole system survives or falls together. For a
    plain wall the group is itself, which is the same as ranking elements.

    Returns (kept_items, dropped_by_label).
    """
    ranked = [it for it in items if it[10] is not None]
    # An element with no measurable distance cannot be ranked, so it is kept
    # rather than silently lost.
    unranked = [it for it in items if it[10] is None]
    if not ranked:
        return items, {}

    # group key -> [nearest distance, [items]]
    groups = {}
    for it in ranked:
        grp = groups.get(it[6])
        if grp is None:
            grp = [it[10], []]
            groups[it[6]] = grp
        elif it[10] < grp[0]:
            grp[0] = it[10]
        grp[1].append(it)

    u_origin = min(it[9][0] for it in ranked)
    v_origin = min(it[9][2] for it in ranked)

    best = {}                       # cell -> (near_dist, group key)
    for key in groups:
        near, members = groups[key]
        for it in members:
            u0, u1, v0, v1 = it[9]
            iu0 = int((u0 - u_origin) / TIER_STEP_U_FT)
            iu1 = int((u1 - u_origin) / TIER_STEP_U_FT)
            iv0 = int((v0 - v_origin) / TIER_STEP_V_FT)
            iv1 = int((v1 - v_origin) / TIER_STEP_V_FT)
            for iu in range(iu0, iu1 + 1):
                for iv in range(iv0, iv1 + 1):
                    cell = best.get((iu, iv))
                    if cell is None or near < cell[0]:
                        best[(iu, iv)] = (near, key)

    # Width won, not cells won: a tall wall wins many cells in one column.
    columns_won = {}
    for (iu, _iv), (_near, key) in best.items():
        cols = columns_won.get(key)
        if cols is None:
            cols = set()
            columns_won[key] = cols
        cols.add(iu)

    keep_keys = set(
        key for key in columns_won
        if len(columns_won[key]) * TIER_STEP_U_FT >= MIN_WIN_FT
    )

    kept = list(unranked)
    dropped_by_label = {}
    for key in groups:
        members = groups[key][1]
        if key in keep_keys:
            kept.extend(members)
        else:
            # If EXTERIOR types show up here while partitions survive, the tag
            # is on the wrong side of the facade and no depth ranking can fix
            # it - that is worth seeing.
            for it in members:
                dropped_by_label[it[0]] = dropped_by_label.get(it[0], 0) + 1
    return kept, dropped_by_label


# What the edge rule measured on the last view it ran on, for the report.
_EDGE_DIAG = {}


def _apply_edge_rule(items):
    """Find the elevation's left and right edge, so the facade can be stretched
    onto them, and deal with the corner returns sitting there.

    At a building corner the adjacent facade's wall is seen end-on: a narrow
    strip at the very edge of the elevation. Being nearer the tag it wins those
    cells and blocks the facade from reaching the corner - the brown strip
    standing where the brick should run out to the edge.

    Either way the facade gets stretched onto the edge by the drawing pass. What
    happens to the return depends on EDGE_KEEP_RETURNS: kept (drawn first, so the
    facade covers it, and its strip is counted twice) or dropped (counted once,
    as facade).

    Returns (items in draw order, edges or None, dropped_by_label,
    kept_return_count), where edges is
    (u_left, u_right, snap_from_left, snap_from_right) in feet.
    """
    if not items:
        return items, None, {}, 0
    u_left = min(it[9][0] for it in items)
    u_right = max(it[9][1] for it in items)
    total = u_right - u_left
    max_band = total * EDGE_MAX_FRAC

    # Record what the rule actually saw. Two versions of this rule looked like
    # they had worked while silently standing down, because the numbers it judges
    # on were never shown.
    def _near(edge_u, key):
        ranked = sorted(items, key=key)[:6]
        return [(it[0], it[9][0], it[9][1], it[9][1] - it[9][0])
                for it in ranked]
    _EDGE_DIAG.clear()
    _EDGE_DIAG.update({
        "u_left": u_left, "u_right": u_right, "width": total,
        "max_band": max_band,
        "leftmost": _near(u_left, lambda it: it[9][0]),
        "rightmost": _near(u_right, lambda it: -it[9][1]),
    })

    if max_band <= EDGE_TOUCH_FT:       # nothing meaningful to measure
        return items, None, {}, 0

    # How far the returns reach in from each edge - measured from the pieces that
    # actually start there and are narrow enough to be returns.
    left_band = 0.0
    right_band = 0.0
    for it in items:
        a, b = it[9][0], it[9][1]
        width = b - a
        if width > max_band:
            continue
        if a <= u_left + EDGE_TOUCH_FT:
            left_band = max(left_band, b - u_left)
        if b >= u_right - EDGE_TOUCH_FT:
            right_band = max(right_band, u_right - a)
    if left_band <= 0.0 and right_band <= 0.0:
        return items, None, {}, 0

    snap_left = left_band + EDGE_TOUCH_FT if left_band > 0 else 0.0
    snap_right = right_band + EDGE_TOUCH_FT if right_band > 0 else 0.0

    at_edge = []
    inboard = []
    for it in items:
        a, b = it[9][0], it[9][1]
        in_left = snap_left > 0 and b <= u_left + snap_left
        in_right = snap_right > 0 and a >= u_right - snap_right
        if in_left or in_right:
            at_edge.append(it)
        else:
            inboard.append(it)
    if not inboard:                 # nothing but edge strips - leave it alone
        return items, None, {}, 0

    edges = (u_left, u_right, snap_left, snap_right)
    if EDGE_KEEP_RETURNS:
        # Returns first: a filled region drawn later sits on top, so the
        # stretched facade covers them.
        return at_edge + inboard, edges, {}, len(at_edge)

    dropped = {}
    for it in at_edge:
        dropped[it[0]] = dropped.get(it[0], 0) + 1
    return inboard, edges, dropped, 0


def _dedupe(items):
    """Drop regions that are genuinely the same draw: same role, same projected
    centre AND same distance from the tag (all on a 0.25 ft grid). That is what
    a link placed twice produces. Depth is part of the key because the front
    tier pass has already decided which walls are visible - two walls sharing a
    centre at different depths are both visible somewhere, so dropping one here
    would lose real area. Index: role=[1], depth_w=[4], center_u=[7],
    center_v=[8], near_dist=[10]."""
    best = {}
    for it in items:
        near = it[10] if it[10] is not None else 0.0
        key = (it[1], round(it[7] / 0.25), round(it[8] / 0.25),
               round(near / 0.25))
        cur = best.get(key)
        if cur is None or it[4] > cur[4]:
            best[key] = it
    return list(best.values())


def collect_view_items(view):
    """Read-only: every wall/window/door in `view` across host + loaded links,
    cut to the view's clip distance and then to the front tier - the layer
    nearest the elevation tag at each position. Returns (items, meta)."""
    limit = depth_limit(view)
    items = []
    progress_phase("Reading {}".format(view.Name), estimate_wall_count(view))
    walked = [0]
    dropped_deep = _collect_from(items, doc, view, view, None, None, limit,
                                 walked)

    used_links = 0
    uncropped_links = 0
    if use_links():
        for inst in get_link_instances_in_view(view):
            link_doc = inst.GetLinkDocument()
            xform = inst.GetTotalTransform()
            bbfilter = crop_filter_for_link(view, xform)
            if bbfilter is None:
                uncropped_links += 1
            dropped_deep += _collect_from(items, link_doc, view, None, bbfilter,
                                          xform, limit, walked)
            used_links += 1

    # Keep only what the elevation really shows: facing walls (done above),
    # minus anything behind the front tier. Then de-dupe.
    collected = len(items)
    kept, dropped_by_label = _keep_front_tier(items)
    # De-dupe first: _apply_edge_rule sets the draw order, so nothing may
    # reshuffle the list after it.
    kept, edges, edge_dropped, edge_kept = _apply_edge_rule(_dedupe(kept))
    v_cut = roof_top_v(view)
    # Anything entirely above the roof is not measured at all; what straddles it
    # is trimmed at draw time.
    above = 0
    if v_cut is not None:
        still = []
        for it in kept:
            if it[9][2] >= v_cut:          # its whole bottom edge is above
                above += 1
            else:
                still.append(it)
        kept = still
    return kept, {
        "v_cut": v_cut,
        "above_roof": above,
        "edge_kept": edge_kept,
        "links": used_links,
        "uncropped": uncropped_links,
        "deep": dropped_deep,
        "tier": sum(dropped_by_label.values()),
        "tier_by_label": dropped_by_label,
        "edges": edges,
        "edge_dropped": edge_dropped,
        "collected": collected,
    }


# --- Step 3: draw (boolean difference, colored per category) -------------

def _make_region(view, frt_id, loops):
    ll = List[CurveLoop]()
    for cl in loops:
        ll.Add(cl)
    return FilledRegion.Create(doc, frt_id, view.Id, ll)


def _why(ex):
    """First line of an exception message, short enough for a report row."""
    msg = str(ex).strip().splitlines()
    msg = msg[0] if msg else type(ex).__name__
    return msg[:90]


# --- Detail grouping: draw once, place the rest as group instances -------

def _group_category(it):
    """Which detail-group category this item belongs to ('window'/'door'/
    'panel'), or None if it can't be grouped at all. Walls (including opaque
    curtain panels, which share ROLE_WALL) never group - see _shape_signature
    for why bbox-matching a wall would be unsafe. Slab edges, columns and
    mullions are out of scope for this feature."""
    role, is_panel = it[1], it[11]
    if is_panel:
        return "panel" if OPT["detail_group_panels"] else None
    if role == ROLE_WINDOW:
        return "window" if OPT["detail_group_windows"] else None
    if role == ROLE_DOOR:
        return "door" if OPT["detail_group_doors"] else None
    return None


def _bucket_groupable_items(items, view, edges, v_cut=None):
    """item-index -> (category, label, shape_signature) bucket key, only for
    items whose bucket has 2+ members - a lone match still draws as a normal,
    ungrouped region exactly as today. Empty if the feature is off."""
    bucket_of = {}
    if not OPT["detail_group_enabled"]:
        return bucket_of
    keys = {}
    counts = {}
    for i, it in enumerate(items):
        cat = _group_category(it)
        if cat is None:
            continue
        sig = _shape_signature(it[2], view, it[3], edges, v_cut)
        if sig is None:
            continue
        key = (cat, it[0], sig)
        keys[i] = key
        counts[key] = counts.get(key, 0) + 1
    for i, key in keys.items():
        if counts[key] >= 2:
            bucket_of[i] = key
    return bucket_of


def _unique_group_type_name(label, w_ft, h_ft):
    base = _safe_type_name("{}{} {} x {}".format(
        NEW_PREFIX, label, _fmt_len(w_ft), _fmt_len(h_ft)))
    existing = set(_name(gt) for gt in
                   FilteredElementCollector(doc).OfClass(GroupType))
    name = base
    i = 2
    while name in existing:
        name = "{} ({})".format(base, i)
        i += 1
    return name


def _draw_grouped_item(view, frt_id, elem, xform, edges, bucket_key,
                       bucket_state, view_name, depth, v_cut=None):
    """Draw one member of a matching (2+) bucket as a Detail Group instance.
    The first item in a bucket ("master") draws as a normal region, gets its
    EN_ params set while it is still a plain, ungrouped region, and is THEN
    wrapped alone into a new Detail Group so its GroupType can be reused.
    (Setting instance parameters on a region AFTER grouping it triggers
    Revit's "changed outside group edit mode" prompt, and once a group has 2+
    instances Revit does not allow a member's parameters to diverge between
    instances at all - it shares the master's values, which is exactly what
    we want here since every element in a bucket has the same type and area
    anyway.) Every later item in the bucket becomes another placed instance of
    that same GroupType, positioned by the offset between its own
    shape-center and the master's, and already carries the master's params
    for free.

    Falls back to a normal standalone region (params set the usual way by the
    caller) on ANY failure: grouping is a bonus, never a reason an element
    goes undrawn or a run aborts.

    Returns (region, net_area, params_set) - params_set is True when this
    function already wrote the EN_ params itself (or Revit already copied
    them from the master), so the caller must NOT call set_region_params
    again; False for a fallback/ordinary region, which still needs it.
    """
    rect = _bbox_uv_rect(elem, view, xform, edges, v_cut)
    if rect is None:
        return None, 0.0, False
    umin, umax, vmin, vmax = rect
    net_area = (umax - umin) * (vmax - vmin)
    center = ((umin + umax) / 2.0, (vmin + vmax) / 2.0)
    pts = [(umin, vmin), (umax, vmin), (umax, vmax), (umin, vmax)]

    state = bucket_state.get(bucket_key)
    if state == "failed":
        return (_make_region(view, frt_id, [_pts_to_loop(pts, view)]),
                net_area, False)

    if state is None:
        # First (master) member: params first, while it is still a plain
        # region, THEN grouped alone so later members can be placed as
        # instances of its GroupType.
        region = _make_region(view, frt_id, [_pts_to_loop(pts, view)])
        set_region_params(region, net_area, view_name, depth)
        try:
            # There is no separate NewDetailGroup - Document.Create.NewGroup
            # makes a Detail Group automatically when every member is
            # view-specific, which a FilledRegion always is.
            group = doc.Create.NewGroup(List[ElementId]([region.Id]))
            gtype = group.GroupType
            gtype.Name = _unique_group_type_name(
                bucket_key[1], umax - umin, vmax - vmin)
            bucket_state[bucket_key] = (group.Location.Point, center, gtype)
        except Exception as ex:
            logger.warning("Could not start a detail group for '{}': {}"
                           .format(bucket_key[1], ex))
            bucket_state[bucket_key] = "failed"
        return region, net_area, True

    master_loc, master_center, gtype = state
    region = None
    try:
        delta = (view.RightDirection.Multiply(center[0] - master_center[0])
                 + view.UpDirection.Multiply(center[1] - master_center[1]))
        # Document.Create.PlaceGroup, not GroupType.Place - GroupType has no
        # Place method. No View argument: the new instance goes into the same
        # view its GroupType's members already belong to.
        new_group = doc.Create.PlaceGroup(master_loc + delta, gtype)
        member_ids = list(new_group.GetMemberIds())
        region = doc.GetElement(member_ids[0]) if member_ids else None
    except Exception as ex:
        logger.warning("Could not place a detail group instance for '{}': {}"
                       .format(bucket_key[1], ex))
    if region is None:
        return (_make_region(view, frt_id, [_pts_to_loop(pts, view)]),
                net_area, False)
    # This member already carries the master's EN_ params/Comments - Revit
    # shares a group's member parameters across every instance once there is
    # more than one, so there is nothing left to set.
    return region, net_area, True


def draw_items(view, items, type_ids, default_id, edges=None, done_before=0,
               v_cut=None):
    """Draw a colored region per element. Walls use the true front-face outline
    (arches preserved), bbox as fallback. Windows/doors/curtain panels fill
    the whole opening (bbox), since one element face can be just a sash - and,
    when enabled in Configurations, 2+ of them that are the same type and true
    shape are drawn once and placed again as Detail Group instances (see
    _draw_grouped_item) so a manual edit to one propagates to every sibling.
    Returns (results {label: [count, area, role, dmin, dmax]},
    skipped [(label, id)], approx_count, bbox_reasons)."""
    bucket_of = _bucket_groupable_items(items, view, edges, v_cut)
    bucket_state = {}
    results = {}
    skipped = []
    approx = 0
    # label -> [count, first reason]. A bounding box is the wall's rectangular
    # extent, so a stepped or notched facade measures too much - worth knowing
    # which types fell back and why, rather than just how many.
    bbox_reasons = {}
    # label -> count of elements with NO solid geometry. An "Empty" curtain panel
    # is Revit's placeholder for a grid cell with nothing in it: no geometry, no
    # material, no area. Falling back to its bounding box invents area, so these
    # are skipped and counted instead.
    no_geometry = {}

    for n, it in enumerate(items):
        if progress_step(done_before + n, "- " + view.Name):
            raise Cancelled()
        label, role, elem, xform = it[0], it[1], it[2], it[3]
        frt_id = type_ids.get(label, default_id)
        region = None
        net_area = 0.0
        used_bbox = False
        params_set = False           # True => _draw_grouped_item already set
                                      # the EN_ params; do not set them again
        extra = []                  # further regions for a stacked assembly

        if role == ROLE_WALL:
            reason = None
            try:
                pieces = outline_pieces(elem, view, xform, edges, v_cut)
                if not pieces:
                    note, solids = face_failure_note(elem, view, xform)
                    if solids == 0:
                        # Nothing to measure at all. A bounding box here would
                        # invent area out of an empty grid cell.
                        no_geometry[label] = no_geometry.get(label, 0) + 1
                        continue
                    reason = "no face facing the elevation - {}".format(note)
                for loops, piece_area in pieces:
                    try:
                        made = _make_region(view, frt_id, loops)
                    except Exception as ex:
                        reason = _why(ex)
                        continue
                    if region is None:
                        region, net_area = made, piece_area
                    else:
                        extra.append((made, piece_area))
            except Exception as ex:
                # Usually a wall seen edge-on, or an outline Revit will not take
                # as a region loop. It falls back to a bounding-box rectangle.
                reason = _why(ex)
                region = None
            if region is None:
                try:
                    built = bbox_loops(elem, view, xform, edges, v_cut)
                    if built is not None:
                        loops, net_area = built
                        region = _make_region(view, frt_id, loops)
                        used_bbox = True
                        entry = bbox_reasons.get(label)
                        if entry is None:
                            entry = [0, reason or "unknown"]
                            bbox_reasons[label] = entry
                        entry[0] += 1
                except Exception as ex:
                    logger.warning("Bbox outline failed for {} in '{}': {}"
                                   .format(elem.Id, view.Name, ex))
        else:
            bucket_key = bucket_of.get(n)
            if bucket_key is None:
                try:
                    built = bbox_loops(elem, view, xform, edges, v_cut)
                    if built is not None:
                        loops, net_area = built
                        region = _make_region(view, frt_id, loops)
                except Exception as ex:
                    logger.warning("Opening outline failed for {} in '{}': {}"
                                   .format(elem.Id, view.Name, ex))
            else:
                try:
                    region, net_area, params_set = _draw_grouped_item(
                        view, frt_id, elem, xform, edges, bucket_key,
                        bucket_state, view.Name, it[10], v_cut)
                except Exception as ex:
                    logger.warning(
                        "Grouped opening outline failed for {} in '{}': {}"
                        .format(elem.Id, view.Name, ex))

        if region is None:
            skipped.append((label, elem.Id))
            continue

        if not params_set:
            set_region_params(region, net_area, view.Name, it[10])
        for made, piece_area in extra:
            set_region_params(made, piece_area, view.Name, it[10])
            net_area += piece_area
        if used_bbox:
            approx += 1
        # [count, area, role, depth_min, depth_max]. The depths are what makes
        # a wrong tier obvious in the report: the facade should come out at one
        # distance, so a type showing up 30 ft back did not belong.
        entry = results.get(label)
        if entry is None:
            entry = [0, 0.0, role, None, None]
            results[label] = entry
        entry[0] += 1
        entry[1] += net_area
        near = it[10]
        if near is not None:
            entry[3] = near if entry[3] is None else min(entry[3], near)
            entry[4] = near if entry[4] is None else max(entry[4], near)

    return results, skipped, approx, bbox_reasons, no_geometry


# --- Orphan cleanup ------------------------------------------------------

def count_unmarked_regions(views):
    n = 0
    for view in views:
        for fr in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
            p = fr.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if not (p and p.AsString() == MARKER):
                n += 1
    return n


def delete_unmarked_regions(views):
    ids = []
    for view in views:
        for fr in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
            p = fr.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if not (p and p.AsString() == MARKER):
                ids.append(fr.Id)
    for fid in ids:
        doc.Delete(fid)
    return len(ids)


# --- Schedule ------------------------------------------------------------

SCHEDULE_NAME = NEW_PREFIX + "Envelope Areas"


def _schedulable(definition, names):
    """The schedulable field whose name matches one of `names` - exact match
    first, then a contains match."""
    fields = {}
    for sf in definition.GetSchedulableFields():
        try:
            fields[sf.GetName(doc)] = sf
        except Exception:
            continue
    for want in names:
        for name in fields:
            if name.lower() == want.lower():
                return fields[name]
    for want in names:
        for name in fields:
            if want.lower() in name.lower():
                return fields[name]
    return None


def existing_envelope_schedule():
    """This tool's schedule if it is already in the model, else None."""
    for vs in FilteredElementCollector(doc).OfClass(ViewSchedule):
        if _name(vs) == SCHEDULE_NAME:
            return vs
    return None


def refresh_envelope_schedule():
    """Build the areas schedule, replacing this tool's own if it already exists.

    Returns (schedule, replaced). Every run ends here, so the schedule is never
    stale and never accumulates copies: one named EN_Envelope Areas, rebuilt.
    Because it groups by elevation and filters on the marker, it shows every
    elevation that currently has regions - not only the ones just run - so
    replacing it does not lose earlier elevations.
    """
    old = existing_envelope_schedule()
    replaced = old is not None
    if replaced:
        t = Transaction(doc, "Remove Old Envelope Area Schedule")
        t.Start()
        try:
            doc.Delete(old.Id)
            t.Commit()
        except Exception as ex:
            t.RollBack()
            logger.warning("Could not replace the old schedule: {}".format(ex))
            replaced = False
    vs = create_envelope_schedule()
    return vs, (replaced and vs is not None)


def create_envelope_schedule():
    """Build the areas schedule: Type and Area as the only columns, grouped by
    Elevation, filtered to this tool's own regions.

    Elevation and Comments are added as fields and then HIDDEN, because Revit can
    only group or filter on a field the schedule contains. So Comments carries the
    filter (every region this tool draws is stamped with MARKER, and nothing else
    is), Elevation carries the grouping, and the table itself reads as Type + Area
    under each elevation's heading.

    Rows are not itemised: one line per type per elevation with the areas summed,
    because a curtain wall facade runs to thousands of panels.
    """
    cat = filled_region_category()
    t = Transaction(doc, "Create Envelope Area Schedule")
    t.Start()
    try:
        vs = ViewSchedule.CreateSchedule(doc, cat.Id)
        vs.Name = SCHEDULE_NAME
        d = vs.Definition

        wanted = [
            ("Type", ["Type", "Family and Type", "Type Name"]),
            (AREA_PARAM_NAME, [AREA_PARAM_NAME]),
            (ELEV_PARAM_NAME, [ELEV_PARAM_NAME]),
            ("Comments", ["Comments"]),
        ]
        found = {}
        missing = []
        for key, names in wanted:
            sf = _schedulable(d, names)
            if sf is None:
                missing.append(key)
            else:
                found[key] = sf
        if missing:
            t.RollBack()
            forms.alert(
                "The schedule needs these fields on {}, and Revit does not "
                "offer them:\n\n{}\n\nRun the calculation first - it binds "
                "'{}' and '{}' to that category.".format(
                    cat.Name, "\n".join(missing),
                    AREA_PARAM_NAME, ELEV_PARAM_NAME),
                title="Cannot Build the Schedule", warn_icon=True,
            )
            return None

        # Visible columns are added first, so the table reads Type | Area.
        c_type = d.AddField(found["Type"])
        c_area = d.AddField(found[AREA_PARAM_NAME])
        c_elev = d.AddField(found[ELEV_PARAM_NAME])
        c_cmt = d.AddField(found["Comments"])
        c_elev.IsHidden = True
        c_cmt.IsHidden = True

        d.AddFilter(ScheduleFilter(
            c_cmt.FieldId, ScheduleFilterType.Equal, MARKER))

        group = ScheduleSortGroupField(
            c_elev.FieldId, ScheduleSortOrder.Ascending)
        group.ShowHeader = True          # the elevation name titles each group
        group.ShowFooter = True          # ... with its area total
        group.ShowBlankLine = True
        d.AddSortGroupField(group)
        d.AddSortGroupField(ScheduleSortGroupField(
            c_type.FieldId, ScheduleSortOrder.Ascending))

        d.IsItemized = False
        c_area.DisplayType = ScheduleFieldDisplayType.Totals
        d.ShowGrandTotal = True

        t.Commit()
        return vs
    except Exception as ex:
        t.RollBack()
        logger.error("Schedule creation failed: {}".format(ex))
        forms.alert("Could not create the schedule:\n\n{}".format(ex),
                    title="Failed", warn_icon=True)
        return None


# --- Reporting -----------------------------------------------------------

def link_diagnostics(view):
    """The funnel and the depth settings for one view. Host-model counts; links
    are read only if the pre-flight was told to (see ask_about_links)."""
    def _n(bic):
        return (FilteredElementCollector(doc, view.Id).OfCategory(bic)
                .WhereElementIsNotElementType().GetElementCount())
    active, offset = far_clip_state(view)
    box = scope_box_of(view)
    total, facing, within, _tier, front = view_scan(view)
    lines = [
        "_Clip {} from tag{}{} | {} walls -> {} facing -> {} in clip | links "
        "{}._".format(
            _fmt_len(offset) if active else "OFF",
            " | front wall {}".format(_fmt_len(front[0]))
            if front is not None else "",
            " | box '{}'".format(_name(box)) if box is not None else "",
            total, facing, within,
            "read" if use_links() else "ignored",
        ),
    ]
    if not is_depth_limited(view):
        lines.append(
            "**[!] This elevation has no depth limit**, so a separate building "
            "further away can win the front tier wherever this one has no "
            "wall. Set a far clip or scope box and re-run."
        )
    return lines


DEPTH_BAND_FT = 5.0
DEPTH_BAND_ROWS = 8
CONTENT_ROWS = 12


def view_content_md(view):
    """Every category with visible elements in this view, plus its Revit links.

    Printed when the walls near the tag are too few to be a facade, because then
    the only question that matters is where the shell actually is: a link (which
    this tool ignores unless asked), curtain panels, or an in-place family
    category. Walks the whole view once, so it is a diagnostic, not a hot path.
    """
    counts = {}
    try:
        for el in (FilteredElementCollector(doc, view.Id)
                   .WhereElementIsNotElementType()):
            cat = el.Category
            name = cat.Name if cat is not None else "(no category)"
            counts[name] = counts.get(name, 0) + 1
    except Exception as ex:
        logger.warning("Could not inventory '{}': {}".format(view.Name, ex))
        return []

    md = [
        "",
        "**What else is in this view** - if the shell is not in Walls, it is "
        "in one of these:",
        "",
        "| Category | Elements |",
        "|---|---:|",
    ]
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    for name, n in ranked[:CONTENT_ROWS]:
        md.append("| {} | {} |".format(name, n))
    if len(ranked) > CONTENT_ROWS:
        md.append("| _{} more categor(ies)_ | {} |".format(
            len(ranked) - CONTENT_ROWS,
            sum(n for _c, n in ranked[CONTENT_ROWS:])))

    links = []
    for inst in FilteredElementCollector(doc, view.Id).OfClass(
            RevitLinkInstance):
        ldoc = inst.GetLinkDocument()
        links.append("{}{}".format(
            ldoc.Title if ldoc is not None else _name(inst),
            "" if ldoc is not None else " (not loaded)"))
    if links:
        md.append("")
        md.append(
            "_Links shown in this view: {}. Currently **{}**._".format(
                ", ".join(sorted(set(links))),
                "read" if use_links() else "ignored")
        )
    return md


def depth_bands(view):
    """{band index: [wall count, {type name: count}]} for the facing walls
    within the clip, banded by distance from the tag in DEPTH_BAND_FT steps."""
    limit = depth_limit(view)
    bands = {}
    for wall, xform in iter_view_walls(view):
        if not faces_elevation(wall, view, xform):
            continue
        span = span_from_tag(wall, view, xform)
        if span is None or _span_beyond(span, limit):
            continue
        idx = int(span[0] / DEPTH_BAND_FT) if span[0] > 0 else 0
        entry = bands.get(idx)
        if entry is None:
            entry = [0, {}]
            bands[idx] = entry
        entry[0] += 1
        tname = type_name_of(wall)
        entry[1][tname] = entry[1].get(tname, 0) + 1

    return bands


# Fewer facing walls than this within SHELL_NEAR_FT of the tag means the shell
# is not in this view's walls at all - a facade is many elements, not three.
SHELL_MIN_WALLS = 10
SHELL_NEAR_FT = 10.0


def depth_profile_md(view):
    """What the elevation contains at each distance from the tag - printed ONLY
    when the nearest bands are too thin to be a facade, which is the one case
    where it is needed.

    This is the diagnostic for a front tier that comes out as partitions. The
    tier can only rank what it is given: if the first 10 ft hold three walls,
    the interior partitions behind them are the frontmost thing at nearly every
    cell and they win honestly. When the facade IS there, the table is noise, so
    it stays out of the report.
    """
    bands = depth_bands(view)
    if not bands:
        return []
    near = sum(cnt for idx, (cnt, _t) in bands.items()
               if idx * DEPTH_BAND_FT < SHELL_NEAR_FT)
    if near >= SHELL_MIN_WALLS:
        return []

    md = [
        "",
        "**What is at each depth** (facing walls within the clip, before the "
        "front tier). The nearest band should be the facade:",
        "",
        "| Distance from tag | Walls | Wall types (most common first) |",
        "|---|---:|---|",
    ]
    for i, idx in enumerate(sorted(bands)):
        if i >= DEPTH_BAND_ROWS:
            rest = sum(bands[k][0] for k in sorted(bands)[DEPTH_BAND_ROWS:])
            md.append("| deeper than {:.0f} ft | {} | ... |".format(
                DEPTH_BAND_ROWS * DEPTH_BAND_FT, rest))
            break
        count, types = bands[idx]
        top = sorted(types.items(), key=lambda kv: -kv[1])[:3]
        md.append("| {:.0f} - {:.0f} ft | {} | {} |".format(
            idx * DEPTH_BAND_FT, (idx + 1) * DEPTH_BAND_FT, count,
            ", ".join("{} ({})".format(t, n) for t, n in top)))

    md.insert(1, "**[!] Only {} wall(s) within {:.0f} ft of the tag** - a facade "
              "is many elements, not a handful, so the shell is not in this "
              "view's Walls and the tier ranked what was behind it. The shell "
              "has to be found first:".format(near, SHELL_NEAR_FT))
    md.extend(view_content_md(view))
    return md


def _wwr(results):
    # Seed sums with 0.0 so an empty role yields a float (IronPython rejects
    # a float format spec applied to an int).
    win = sum((v[1] for v in results.values() if v[2] == ROLE_WINDOW), 0.0)
    door = sum((v[1] for v in results.values() if v[2] == ROLE_DOOR), 0.0)
    wall = sum((v[1] for v in results.values() if v[2] == ROLE_WALL), 0.0)
    gross = wall + win + door
    wwr = (win / gross * 100.0) if gross > 1e-6 else 0.0
    return win, wall, door, wwr


def _ordered_labels(results):
    """Opaque types first (alphabetical), then glazing, doors, and finally the
    thermal-bridge conditions - by ROLE, so curtain-wall glazed panels group with
    the glass rather than the walls."""
    def _of(role):
        return sorted(k for k in results if results[k][2] == role)
    return (_of(ROLE_WALL) + _of(ROLE_WINDOW) + _of(ROLE_DOOR)
            + _of(ROLE_SLAB) + _of(ROLE_COLUMN) + _of(ROLE_MULLION))


def edge_diag_md():
    """The numbers the edge rule judged on, so a rule that stood down says why.

    Both earlier versions of this rule looked as though they had worked while
    doing nothing, because these values were never shown. The pieces are listed
    with the strip of elevation each covers, so it is visible whether the return
    is at the extreme edge at all, and whether it is narrow enough to qualify.
    """
    d = _EDGE_DIAG
    if not d:
        return ["_The edge rule did not run on this view._"]
    md = [
        "",
        "_Elevation spans {} to {} ({} wide). A return may be at most {} "
        "wide._".format(
            _fmt_len(d["u_left"]), _fmt_len(d["u_right"]),
            _fmt_len(d["width"]), _fmt_len(d["max_band"])),
        "",
        "| Edge | Type | Covers | Width |",
        "|---|---|---|---:|",
    ]
    for side, key in (("left", "leftmost"), ("right", "rightmost")):
        for label, a, b, w in d.get(key, []):
            md.append("| {} | {} | {} to {} | {} |".format(
                side, label, _fmt_len(a), _fmt_len(b), _fmt_len(w)))
    return md


def _swatch(color_name):
    """An inline square in the region's own colour, so a row in the table can be
    matched to the colour on the elevation without hunting for the region type."""
    rgb = COLOR_PALETTE.get(color_name)
    if rgb is None:
        return ""
    return (
        '<span style="display:inline-block;width:11px;height:11px;'
        'background:#{:02X}{:02X}{:02X};border:1px solid #7f7f7f;'
        'vertical-align:middle;margin-right:6px;"></span>'.format(*rgb)
    )


def build_report(target_cat, grand, grand_views, grand_meta, color_of=None):
    md = [
        "_`{}` and `{}` written per region on **{}**, one colour per "
        "type._".format(AREA_PARAM_NAME, ELEV_PARAM_NAME, target_cat.Name)
    ]
    for view_name in sorted(grand):
        results = grand[view_name]
        meta = grand_meta[view_name]
        skipped = meta["skipped"]
        uncropped = meta["uncropped"]
        md.append("")
        md.append("### {}".format(view_name))
        for ln in link_diagnostics(grand_views[view_name]):
            md.append(ln)
        bits = []
        if meta["tier"]:
            bits.append("{} behind the tier".format(meta["tier"]))
        if meta["deep"]:
            bits.append("{} past the clip".format(meta["deep"]))
        no_geom = meta.get("no_geometry") or {}
        if no_geom:
            bits.append("{} with no geometry ({})".format(
                sum(no_geom.values()),
                ", ".join("{} x{}".format(t, n) for t, n in
                          sorted(no_geom.items(), key=lambda kv: -kv[1])[:3])))
        if meta["cleared"]:
            bits.append("{} cleared".format(meta["cleared"]))
        md.append("_**{} regions drawn** of {} pieces{}._".format(
            meta["collected"] - meta["tier"], meta["collected"],
            " - dropped: " + ", ".join(bits) if bits else ""))
        dropped_by_label = meta.get("tier_by_label") or {}
        if dropped_by_label:
            top = sorted(dropped_by_label.items(), key=lambda kv: -kv[1])[:5]
            md.append(
                "_Behind the tier: {}._".format(
                    ", ".join("{} ({})".format(t, n) for t, n in top))
            )
        v_cut = meta.get("v_cut")
        if v_cut is None:
            md.append(
                "_Roof: none found in this view, so nothing was trimmed off the "
                "top._")
        else:
            md.append(
                "_Roof: trimmed at the highest roof point{}._".format(
                    ", {} piece(s) dropped as entirely above it".format(
                        meta.get("above_roof") or 0)
                    if meta.get("above_roof") else
                    " - nothing stood above it")
            )
        edges = meta.get("edges")
        edge_dropped = meta.get("edge_dropped") or {}
        if edges:
            _ul, _ur, snap_left, snap_right = edges
            reach = []
            if snap_left > 0:
                reach.append("{} on the left".format(_fmt_len(snap_left)))
            if snap_right > 0:
                reach.append("{} on the right".format(_fmt_len(snap_right)))
            note = "_Edges: facade stretched {}".format(" and ".join(reach))
            if edge_dropped:
                top = sorted(edge_dropped.items(), key=lambda kv: -kv[1])[:4]
                note += ", over {} corner return(s) - {}".format(
                    sum(edge_dropped.values()),
                    ", ".join("{} ({})".format(t, n) for t, n in top))
            elif meta.get("edge_kept"):
                note += ", {} return(s) kept underneath".format(
                    meta["edge_kept"])
            md.append(note + "._")
        else:
            md.append(
                "**[!] Edges: nothing was stretched.** No piece both starts at "
                "an edge and is narrower than {:.0%} of the elevation, so the "
                "rule found no corner return. What it measured:".format(
                    EDGE_MAX_FRAC)
            )
            md.extend(edge_diag_md())
        if meta["approx"]:
            md.append(
                "**[!] {} region(s) drawn as a bounding-box rectangle**, so "
                "their area is the wall's rectangular extent - a stepped or "
                "notched facade measures too much:".format(meta["approx"])
            )
            for label, (n, why) in sorted(
                    (meta.get("bbox_reasons") or {}).items(),
                    key=lambda kv: -kv[1][0]):
                md.append("- `{}` x{} - {}".format(label, n, why))
        if skipped:
            by_cat = {}
            for cat, eid in skipped:
                by_cat[cat] = by_cat.get(cat, 0) + 1
            md.append(
                "**[!] {} element(s) skipped** (no usable outline at all): "
                "{}".format(
                    len(skipped),
                    ", ".join("{} x{}".format(c, n) for c, n in sorted(by_cat.items())),
                )
            )
        if uncropped:
            md.append(
                "**[!]** {} link(s) had no active crop box, so the whole "
                "linked building was measured. Turn on the view crop to limit "
                "it.".format(uncropped)
            )
        if not results:
            md.append("_No envelope elements classified._")
            continue

        # Depth from tag is written on every region and schedulable; it is left
        # out of the table because it is a diagnostic, not a deliverable.
        md.append("")
        md.append("| Type | Count | Area (SF) |")
        md.append("|---|---:|---:|")
        for label in _ordered_labels(results):
            count, area = results[label][0], results[label][1]
            swatch = _swatch((color_of or {}).get(label))
            md.append("| {}{} | {} | {:.1f} |".format(
                swatch, label, count, area))
        md.extend(depth_profile_md(grand_views[view_name]))
        win, wall, door, wwr = _wwr(results)
        if (win + door) > 1e-6:
            md.append("")
            md.append(
                "**Window/Wall Ratio** = window / (wall + window + door) = "
                "{:.1f} / {:.1f} = **{:.1f}%** _(confirm formula)_".format(
                    win, wall + win + door, wwr
                )
            )
            md.append(
                "_Glazing matched by type name: {}._".format(
                    ", ".join('"{}"'.format(t) for t in GLAZED_PANEL_TOKENS))
            )
        if _MULLIONS_SKIPPED[0]:
            md.append(
                "_{} mullions not measured - tick \"Curtain wall mullions\" to "
                "include them._".format(_MULLIONS_SKIPPED[0])
            )

        n, ab, aset, azero, eb, eset = verify_view_params(grand_views[view_name])
        if n:
            area_ok = "OK" if aset == n else "MISMATCH"
            elev_ok = "OK" if eset == n else "MISMATCH"
            md.append(
                "_Param check ({} region(s)): `{}` [{}] {}/{} &nbsp;|&nbsp; "
                "`{}` [{}] {}/{}_".format(
                    n, AREA_PARAM_NAME, area_ok, aset, n,
                    ELEV_PARAM_NAME, elev_ok, eset, n,
                )
            )
            if azero:
                md.append(
                    "_{} region(s) have 0 net area (a wall fully covered by an "
                    "opening)._".format(azero)
                )
    return "\n".join(md)


# --- Saved options -------------------------------------------------------
#
# One config section shared by all three buttons, so what is ticked in
# Configurations is what Run Now uses.

CONFIG_SECTION = "envelope_areas"
_OPT_KEYS = ("walls", "windows", "doors", "panels", "mullions",
             "slab_edges", "columns", "detail_group_enabled",
             "detail_group_windows", "detail_group_doors",
             "detail_group_panels")

# Set once the user has saved the Configurations window. Both run buttons refuse
# until then - see require_configured().
_CONFIGURED = False


def load_options():
    """Read the saved options into OPT. Missing keys keep their defaults."""
    try:
        cfg = script.get_config(CONFIG_SECTION)
    except Exception:
        return OPT
    for key in _OPT_KEYS:
        try:
            OPT[key] = bool(cfg.get_option(key, OPT[key]))
        except Exception:
            pass
    try:
        OPT["types"] = set(cfg.get_option("types", []) or [])
    except Exception:
        OPT["types"] = set()
    try:
        raw = cfg.get_option("groups", "") or ""
        OPT["groups"] = dict((k, set(v))
                             for k, v in (json.loads(raw) if raw else {}).items())
    except Exception:
        OPT["groups"] = {}
    global _CONFIGURED
    try:
        _CONFIGURED = bool(cfg.get_option("configured", False))
    except Exception:
        _CONFIGURED = False
    _SCAN_CACHE.clear()
    return OPT


def is_configured():
    """Has this user saved the configuration at least once?"""
    return _CONFIGURED


def save_options():
    global _CONFIGURED
    try:
        cfg = script.get_config(CONFIG_SECTION)
        for key in _OPT_KEYS:
            cfg.set_option(key, bool(OPT[key]))
        cfg.set_option("types", sorted(OPT["types"]))
        cfg.set_option("groups", json.dumps(
            dict((k, sorted(v)) for k, v in OPT["groups"].items())))
        cfg.set_option("configured", True)
        script.save_config()
        _CONFIGURED = True
    except Exception as ex:
        logger.warning("Could not save the options: {}".format(ex))
    _SCAN_CACHE.clear()


# OPT key -> (display label, BuiltInCategory), the categories the type
# whitelist can be filtered per-category by.
TYPE_CATEGORIES = (
    ("walls", "Walls", BuiltInCategory.OST_Walls),
    ("panels", "Curtain wall panels", BuiltInCategory.OST_CurtainWallPanels),
    ("mullions", "Curtain wall mullions", BuiltInCategory.OST_CurtainWallMullions),
    ("windows", "Windows", BuiltInCategory.OST_Windows),
    ("doors", "Doors", BuiltInCategory.OST_Doors),
)


def envelope_type_names_for(bic):
    """Every type name of one category, in the model and its read links."""
    names = set()
    docs = [doc]
    if use_links():
        for inst in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
            ldoc = inst.GetLinkDocument()
            if ldoc is not None and ldoc not in docs:
                docs.append(ldoc)
    for source in docs:
        try:
            for et in (FilteredElementCollector(source).OfCategory(bic)
                       .WhereElementIsElementType()):
                n = _name(et)
                if n:
                    names.add(n)
        except Exception:
            continue
    return names


def envelope_type_names():
    """Every wall / curtain panel / mullion / window / door type name in the
    model and its read links - the pool the type whitelist is chosen from."""
    names = set()
    for _key, _label, bic in TYPE_CATEGORIES:
        names |= envelope_type_names_for(bic)
    return names


# --- Purge ---------------------------------------------------------------

def _our_regions():
    return [fr for fr in FilteredElementCollector(doc).OfClass(FilledRegion)
            if _is_ours_region(fr)]


def _is_ours_region(fr):
    t = doc.GetElement(fr.GetTypeId())
    if t is not None and _name(t).startswith(NEW_PREFIX):
        return True
    p = fr.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    return bool(p) and p.AsString() == MARKER


def _our_region_types():
    return [frt for frt in FilteredElementCollector(doc).OfClass(FilledRegionType)
            if _name(frt).startswith(NEW_PREFIX)]


def _our_group_types():
    """GroupTypes this tool created to hold identical windows/doors/panels
    (see _draw_grouped_item). Deletion is attempted the same way as region
    types - Revit itself refuses one still in use, which is reported as
    blocked rather than checked for up front."""
    return [gt for gt in FilteredElementCollector(doc).OfClass(GroupType)
            if _name(gt).startswith(NEW_PREFIX)]


def _our_param_bindings():
    """The EN_ parameter definitions bound in this model."""
    found = []
    it = doc.ParameterBindings.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        if it.Key.Name.startswith(NEW_PREFIX):
            found.append(it.Key)
    return found


# What can be purged, in the order it has to happen: instances before the types
# they use, or Revit refuses the type. (key, label)
PURGE_KINDS = (
    ("regions", "Filled regions"),
    ("schedules", "Schedule"),
    ("types", "Region & group types"),
    ("parameters", "Parameters (the area values live on the regions)"),
)


def purge_counts():
    """How much of this tool's output is in the model, without touching it."""
    bind_host()
    return {
        "regions": len(_our_regions()),
        "schedules": 1 if existing_envelope_schedule() is not None else 0,
        "types": len(_our_region_types()) + len(_our_group_types()),
        "parameters": len(_our_param_bindings()),
    }


def purge(kinds):
    """Delete the chosen kinds of this tool's output. `kinds` is an iterable of
    PURGE_KINDS keys.

    Regions the user drew themselves are never matched - only regions carrying
    this tool's marker or an EN_ region type. Returns (done, blocked): counts
    deleted per kind, and kinds Revit would not let go, which happens when types
    are purged while their regions are still in the model.
    """
    bind_host()
    kinds = set(kinds)
    done = dict((k, 0) for k, _lbl in PURGE_KINDS)
    blocked = {}
    t = Transaction(doc, "Purge Envelope Output")
    t.Start()
    try:
        if "regions" in kinds:
            done["regions"], n_blocked = _delete_regions(_our_regions())
            if n_blocked:
                blocked["regions"] = n_blocked
        if "schedules" in kinds:
            vs = existing_envelope_schedule()
            if vs is not None:
                try:
                    doc.Delete(vs.Id)
                    done["schedules"] += 1
                except Exception:
                    blocked["schedules"] = 1
        if "types" in kinds:
            for frt in _our_region_types():
                try:
                    doc.Delete(frt.Id)
                    done["types"] += 1
                except Exception:
                    # In use by regions that were not purged.
                    blocked["types"] = blocked.get("types", 0) + 1
            for gt in _our_group_types():
                try:
                    doc.Delete(gt.Id)
                    done["types"] += 1
                except Exception:
                    # Still in use by placed instances.
                    blocked["types"] = blocked.get("types", 0) + 1
        if "parameters" in kinds:
            for defn in _our_param_bindings():
                try:
                    if doc.ParameterBindings.Remove(defn):
                        done["parameters"] += 1
                    else:
                        blocked["parameters"] = blocked.get("parameters", 0) + 1
                except Exception:
                    blocked["parameters"] = blocked.get("parameters", 0) + 1
        t.Commit()
    except Exception as ex:
        t.RollBack()
        logger.error("Purge failed: {}".format(ex))
        forms.alert("Purge failed and was rolled back:\n\n{}".format(ex),
                    title="Failed", warn_icon=True)
        return dict((k, 0) for k, _lbl in PURGE_KINDS), blocked
    return done, blocked


def options_summary():
    on = [k for k in _OPT_KEYS if OPT[k]]
    return ", ".join(on) if on else "nothing selected"


# --- Orchestration -------------------------------------------------------

def active_elevation():
    """The active view if it is an elevation, else None."""
    view = uidoc.ActiveView
    try:
        if view is not None and not view.IsTemplate \
                and view.ViewType == ViewType.Elevation:
            return view
    except Exception:
        pass
    return None


def require_configured():
    """Both run buttons stop here until Configurations has been saved once.

    Nothing about a model tells the tool whether the slab is part of the facade
    or modelled separately, so a first run on defaults would quietly produce the
    wrong set of areas. Better to send the user to the tick boxes once. The
    prompt opens the window itself, so it costs one click, and the answer is
    remembered per user from then on.
    """
    if is_configured():
        return True
    if not forms.alert(
        "Set what counts as envelope before the first run.",
        title="Configuration Needed",
        sub_msg="Nothing in the model says whether slab edges, columns, "
        "mullions or openings belong in your areas - that is a project "
        "decision.",
        expanded="Open Configurations, tick the categories this project needs "
        "and Save. It is remembered from then on, which is what lets Run Now "
        "measure the open elevation without asking anything.",
        ok=False, yes=True, no=True,
        warn_icon=True,
    ):
        return False
    from envelope import config_ui
    if not config_ui.show("Save"):
        return False
    load_options()
    return is_configured()


def run_active_view():
    """Run Now: measure the elevation that is open, with the saved options and no
    questions - except the depth check, which still speaks up if a view has no
    depth limit at all, because that one silently measures the whole building."""
    bind_host()
    load_options()
    if not require_configured():
        return
    view = active_elevation()
    if view is None:
        forms.alert(
            "The active view is not an elevation. Open the elevation you want "
            "measured, or use Select Elevations to pick from a list.",
            title="Run Now", warn_icon=True,
        )
        return
    main([view], ask_config=False, depth_check_if_needed=True)


def run_pick_views():
    """Select Elevations: the full flow - pick the views, confirm the options,
    check the depth."""
    bind_host()
    load_options()
    if not require_configured():
        return
    main(None, ask_config=True, depth_check_if_needed=False)


def main(elevations=None, ask_config=True, depth_check_if_needed=False):
    bind_host()
    if elevations is None:
        elevations = pick_elevations()

    # What counts as envelope, before the depth check - the options change what
    # the depth check's front tier preview counts.
    if ask_config:
        if not ask_options():       # the window saves on its way out
            return

    # Nothing is read or drawn until the user has seen (and had the chance to
    # fix) how deep each elevation looks into the building. Run Now skips this
    # when every view is already bounded.
    if not (depth_check_if_needed
            and not [v for v in elevations if needs_attention(v)]):
        if not preflight_clipping(elevations):
            return

    # The window opens before the first slow pass, so pressing Run shows
    # something immediately instead of a frozen Revit.
    progress_open("Envelope Area Calculations")

    target_cat = filled_region_category()
    if not ensure_project_parameters(target_cat):
        progress_finish()
        return

    base_id = get_filled_region_type_id()
    if base_id is None:
        progress_finish()       # or the Cancel button is left in the window
        forms.alert(
            "No Filled Region Type exists in this model. Create one first "
            "(Annotate > Region), then run again.",
            exitscript=True,
        )

    # Read-only pass: collect items per view, and every label with its role -
    # the role decides the colour, since glazed curtain panels are never called
    # "Window".
    per_view = {}
    label_roles = {}
    total_items = 0
    total_dropped = 0
    read_phase = Phase("reading")
    read_phase.__enter__()
    for view in elevations:
        try:
            items, meta = collect_view_items(view)
        except Cancelled:
            read_phase.__exit__()
            progress_finish()
            return
        per_view[view.Name] = (view, items, meta)
        total_items += len(items)
        total_dropped += meta["deep"]
        for it in items:
            label_roles[it[0]] = it[1]
    read_phase.__exit__()

    if not total_items:
        progress_finish()       # or the Cancel button is left in the window
        forms.alert(
            "No walls/windows/doors were found in the picked elevation(s) - "
            "nothing to draw.{}".format(
                "\n\nThe clip distance dropped all {} of them, so it is set "
                "shorter than the distance from the tag to the facade. Re-run "
                "and give it a larger distance.".format(total_dropped)
                if total_dropped else
                " (If the building is a link, make sure it's loaded and "
                "visible, with the view crop on.)"
            ),
            exitscript=True,
        )

    # One-time offer to clear untagged filled regions (earlier-run leftovers).
    orphan_count = count_unmarked_regions(elevations)
    delete_orphans = False
    if orphan_count:
        delete_orphans = forms.alert(
            "Found {} filled region(s) in the picked elevation(s) that this "
            "tool did not tag (possibly leftovers from an earlier run).\n\n"
            "Delete them before redrawing?".format(orphan_count),
            title="Clear Untagged Filled Regions?",
            ok=False, yes=True, no=True,
        )

    grand = {}
    grand_views = {}
    grand_meta = {}
    t = Transaction(doc, "Draw Envelope Filled Regions")
    t.Start()
    try:
        if delete_orphans:
            delete_unmarked_regions(elevations)
        color_of = assign_colors(label_roles)
        type_ids = ensure_region_types(base_id, color_of)
        # One bar across every view, since a facade of curtain panels is thousands
        # of regions and per-view bars would each restart at nothing.
        # One bar across every view, since a facade of curtain panels is
        # thousands of regions and per-view bars would each restart at nothing.
        draw_phase = Phase("drawing")
        draw_phase.__enter__()
        progress_phase("Drawing regions", total_items)
        drawn = 0
        for view_name in sorted(per_view):
            view, items, meta = per_view[view_name]
            meta["cleared"] = clear_previous_regions(view)
            results, skipped, approx, bbox_reasons, no_geometry = draw_items(
                view, items, type_ids, base_id, meta.get("edges"), drawn,
                meta.get("v_cut"))
            drawn += len(items)
            meta["skipped"] = skipped
            meta["approx"] = approx
            meta["bbox_reasons"] = bbox_reasons
            meta["no_geometry"] = no_geometry
            grand[view_name] = results
            grand_views[view_name] = view
            grand_meta[view_name] = meta
        draw_phase.__exit__()

        # The commit is where the bar used to sit at 99%: Revit writing thousands
        # of new annotation elements, in one call that cannot be ticked through or
        # interrupted. All that can be done is say so.
        with Phase("commit", cancellable=False,
                   note="Committing {:,} regions to the model - Revit's own "
                        "work, please wait".format(drawn)):
            t.Commit()
    except Cancelled:
        t.RollBack()
        progress_finish()
        forms.alert("Stopped - nothing was drawn.", title="Cancelled")
        return
    except Exception as ex:
        t.RollBack()
        progress_finish()
        logger.error("Envelope calc failed: {}".format(ex))
        forms.alert(
            "Envelope calculation failed and was rolled back:\n\n{}".format(ex),
            title="Failed", warn_icon=True,
        )
        return

    # Every run ends with the schedule refreshed - no prompt. It is grouped by
    # elevation and filtered on the marker, so it always shows every elevation
    # that currently has regions, this run's and any earlier one's.
    with Phase("schedule", cancellable=False,
               note="Refreshing the schedule"):
        vs, replaced = refresh_envelope_schedule()

    with Phase("report", cancellable=False, note="Writing the report"):
        report = build_report(target_cat, grand, grand_views, grand_meta,
                              color_of)
    progress_finish()
    output.print_md("## Envelope Area Calculations")
    for line in timing_md():
        output.print_md(line)
    output.print_md(report)
    if vs is not None:
        output.print_md("{} schedule **{}** {}".format(
            "Replaced" if replaced else "Created",
            _name(vs), output.linkify(vs.Id)))
