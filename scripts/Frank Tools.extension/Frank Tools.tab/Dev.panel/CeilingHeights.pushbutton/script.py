# -*- coding: utf-8 -*-
__title__ = "CLR\nCeiling\nHeights"
__doc__ = """Version = 3.0
Date    = 17.06.2026
________________________________________________________________
Description:
Calculates the clear height (CLR) from every ceiling bottom to
the floor directly below it, writes the result to the shared
parameter "S_Ceiling Tag_Clear Height", and places ceiling
tags in the active view.

When multiple floor sections exist at the same elevation under
a ceiling, the tool projects both footprints onto the XY plane
and computes the 2-D overlap fraction for each floor.

  - One floor covers >= 95 % of the ceiling footprint
    -> that floor is used for the CLR calculation.

  - No floor reaches 95 %
    -> an error is logged, the ceiling and all candidate floors
       are selected / highlighted in the model for review.

Tags are placed only when the active view is a Floor Plan,
Ceiling Plan, or Area Plan.  Ceilings already tagged in the
active view are skipped.
________________________________________________________________
How-To:
Open a Floor Plan or Reflected Ceiling Plan, then click this
button.  Re-run whenever ceilings or floors are added or moved.
________________________________________________________________
Author: Frank Sun"""

import os
import uuid

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    ExternalDefinitionCreationOptions,
    FamilySymbol,
    FilteredElementCollector,
    GroupTypeId,
    IndependentTag,
    Options,
    Reference,
    Solid,
    SpecTypeId,
    TagOrientation,
    Transaction,
    Viewport,
    ViewType,
    XYZ,
)
from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons
from System.Collections.Generic import List as CsList
from pyrevit import script, forms

app   = __revit__.Application
uidoc = __revit__.ActiveUIDocument
doc   = __revit__.ActiveUIDocument.Document  # type: ignore

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

PARAM_NAME          = "S_Ceiling Tag_Clear Height"
SPF_PATH            = r"C:\Users\fsun\AppData\Roaming\myRevitExtension\BBB_SharedParams.txt"
SPF_GROUP           = "BBB Ceiling Data"
CLR_FAMILY          = "B_ANNO_Ceiling Tag_Clear Height"
DOMINANCE_THRESHOLD = 0.95  # floor must cover >= 95 % of the ceiling footprint
GRID_N              = 25    # 25 x 25 = 625 sample points per overlap test

# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def polygon_area(pts):
    """Shoelace formula — 2-D signed area (returned as positive)."""
    n = len(pts)
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(a) / 2.0


def point_in_polygon(x, y, poly):
    """Ray-casting point-in-polygon test."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def horizontal_face_polygon(element, upward):
    """Return the 2-D XY polygon of the largest horizontal face of element.

    upward=True  -> top face (floor),    normal Z ~= +1
    upward=False -> bottom face (ceiling), normal Z ~= -1

    Falls back to the element's bounding-box rectangle if geometry is
    unavailable or the expected face is not found.
    """
    opts = Options()
    opts.ComputeReferences = False
    best_area = 0.0
    best_pts  = None

    try:
        for obj in element.get_Geometry(opts):
            if not isinstance(obj, Solid) or obj.Volume <= 0:
                continue
            for face in obj.Faces:
                nz = face.FaceNormal.Z
                if upward  and nz < 0.9:
                    continue
                if not upward and nz > -0.9:
                    continue
                try:
                    loops = list(face.GetEdgesAsCurveLoops())
                except Exception:
                    continue
                if not loops:
                    continue
                pts = [
                    (c.GetEndPoint(0).X, c.GetEndPoint(0).Y)
                    for c in loops[0]
                ]
                area = polygon_area(pts)
                if area > best_area:
                    best_area = area
                    best_pts  = pts
    except Exception:
        pass

    # Bounding-box fallback
    if best_pts is None:
        bb = element.get_BoundingBox(None)
        if bb:
            best_pts = [
                (bb.Min.X, bb.Min.Y),
                (bb.Max.X, bb.Min.Y),
                (bb.Max.X, bb.Max.Y),
                (bb.Min.X, bb.Max.Y),
            ]

    return best_pts


def overlap_fraction(clg_poly, flr_poly):
    """Fraction of ceiling footprint area covered by floor footprint.

    Uses a uniform grid of GRID_N x GRID_N sample points over the ceiling
    bounding box, tests each against both polygons, and returns:
        points inside BOTH / points inside ceiling
    """
    xs = [p[0] for p in clg_poly]
    ys = [p[1] for p in clg_poly]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 == x0 or y1 == y0:
        return 0.0

    dx = (x1 - x0) / GRID_N
    dy = (y1 - y0) / GRID_N
    total = covered = 0

    for i in range(GRID_N):
        for j in range(GRID_N):
            px = x0 + (i + 0.5) * dx
            py = y0 + (j + 0.5) * dy
            if point_in_polygon(px, py, clg_poly):
                total += 1
                if point_in_polygon(px, py, flr_poly):
                    covered += 1

    return float(covered) / total if total > 0 else 0.0


def ft_to_ftin(ft):
    total_in = ft * 12.0
    feet     = int(total_in // 12)
    inches   = total_in - feet * 12.0
    if feet > 0:
        return "{:d}' - {:.0f}\"".format(feet, round(inches))
    return "{:.0f}\"".format(round(inches))

# ---------------------------------------------------------------------------
# shared parameter helpers
# ---------------------------------------------------------------------------

def ensure_spf():
    if os.path.exists(SPF_PATH):
        return
    guid = str(uuid.uuid4()).upper()
    with open(SPF_PATH, "w") as f:
        f.write(
            "# This is a Revit shared parameter file.\n# Do not edit manually.\n"
            "*META\tVERSION\tMINVERSION\nMETA\t2\t1\n*GROUP\tID\tNAME\n"
            "GROUP\t1\t{group}\n"
            "*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\t"
            "VISIBLE\tDESCRIPTION\tUSERMODAFIABLE\tHIDEWHENNOVALUETYPE\n"
            "PARAM\t{{{guid}}}\t{name}\tLENGTH\t\t1\t1\t\t1\t0\n"
            .format(group=SPF_GROUP, guid=guid, name=PARAM_NAME)
        )


def param_already_bound(doc):
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        if it.Key.Name == PARAM_NAME:
            return True
    return False


def bind_shared_param(doc, app):
    old_spf = app.SharedParametersFilename
    app.SharedParametersFilename = SPF_PATH
    spf  = app.OpenSharedParameterFile()
    grp  = spf.Groups.get_Item(SPF_GROUP) or spf.Groups.Create(SPF_GROUP)
    defn = grp.Definitions.get_Item(PARAM_NAME)
    if defn is None:
        opts         = ExternalDefinitionCreationOptions(PARAM_NAME, SpecTypeId.Length)
        opts.Visible = True
        defn         = grp.Definitions.Create(opts)
    cat     = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Ceilings)
    cat_set = app.Create.NewCategorySet()
    cat_set.Insert(cat)
    binding = app.Create.NewInstanceBinding(cat_set)
    t = Transaction(doc, "Bind Shared Param")
    t.Start()
    doc.ParameterBindings.Insert(defn, binding, GroupTypeId.Data)
    t.Commit()
    app.SharedParametersFilename = old_spf

# ---------------------------------------------------------------------------
# pre-run validation (dialog shown only when issues are found)
# ---------------------------------------------------------------------------

_clr_types = [
    t for t in
    FilteredElementCollector(doc)
    .OfClass(FamilySymbol)
    .OfCategory(BuiltInCategory.OST_CeilingTags)
    .ToElements()
    if t.Family.Name == CLR_FAMILY
]

if not _clr_types:
    forms.alert(
        "Required ceiling tag family \"{}\" is not loaded.\n\n"
        "Please load this family before running.".format(CLR_FAMILY),
        title="CLR Ceiling Heights",
        warn_icon=True,
    )
    script.exit()

tag_type_id      = _clr_types[0].Id
_template_family = CLR_FAMILY
view             = uidoc.ActiveView

# ---------------------------------------------------------------------------
# off-template ceiling tag scan (before calculations)
# ---------------------------------------------------------------------------

_view_to_sheet = {}
for _vp in FilteredElementCollector(doc).OfClass(Viewport).ToElements():
    _sht = doc.GetElement(_vp.SheetId)
    try:
        _view_to_sheet[_vp.ViewId.IntegerValue] = "{} - {}".format(
            _sht.SheetNumber, _sht.Name)
    except Exception:
        pass

off_template_info = {}  # (fam, type, view_id) -> {family, type, view, sheet, count, ids}
for _tag in (
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_CeilingTags)
    .WhereElementIsNotElementType()
    .ToElements()
):
    _sym = doc.GetElement(_tag.GetTypeId())
    try:
        _fam = _sym.Family.Name
    except Exception:
        _fam = "Unknown"
    if _fam == _template_family:
        continue
    try:
        _typ = (_sym.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
                or _sym.Name)
    except Exception:
        _typ = "Unknown"
    _vid        = _tag.OwnerViewId.IntegerValue
    _view_elem  = doc.GetElement(_tag.OwnerViewId)
    _view_name  = _view_elem.Name if _view_elem else "Unknown View"
    _sheet_lbl  = _view_to_sheet.get(_vid, "Not on sheet")
    _key = (_fam, _typ, _vid)
    if _key not in off_template_info:
        off_template_info[_key] = {"family": _fam, "type": _typ,
                                   "view": _view_name, "sheet": _sheet_lbl,
                                   "count": 0, "ids": []}
    off_template_info[_key]["count"] += 1
    off_template_info[_key]["ids"].append(_tag.Id)

# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

ensure_spf()
if not param_already_bound(doc):
    bind_shared_param(doc, app)

ceilings = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Ceilings)
    .WhereElementIsNotElementType()
    .ToElements()
)
if not ceilings:
    forms.alert("No ceilings found in the model.", title="Ceiling Heights")
    script.exit()

# Pre-build floor data: (element, top_elevation, footprint_polygon)
# Polygon is computed once here so we don't re-extract geometry per ceiling.
floor_data = []
for fl in (
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Floors)
    .WhereElementIsNotElementType()
    .ToElements()
):
    flvl = doc.GetElement(fl.LevelId)
    if flvl is None:
        continue
    p   = fl.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
    top = flvl.Elevation + (p.AsDouble() if p else 0.0)
    poly = horizontal_face_polygon(fl, upward=True)
    floor_data.append((fl, top, poly))

# ---------------------------------------------------------------------------
# calculate CLR for every ceiling
# ---------------------------------------------------------------------------

output = script.get_output()
output.set_title("Ceiling Heights")

results = []  # (ceiling_id, dist_str)
errors  = []  # (ceiling, [(floor, overlap_frac), ...])
no_floor = [] # ceiling ids where no floor was found at all

t = Transaction(doc, "Update Height Offset From Floor Below")
t.Start()

for ceiling in ceilings:
    lvl  = doc.GetElement(ceiling.LevelId)
    if lvl is None:
        continue
    p_ht = ceiling.get_Parameter(BuiltInParameter.CEILING_HEIGHTABOVELEVEL_PARAM)
    if p_ht is None:
        continue
    clg_bottom = lvl.Elevation + p_ht.AsDouble()

    # All floors whose top surface is meaningfully below this ceiling.
    # Use ceiling bounding box for a fast XY pre-filter before the
    # expensive polygon overlap computation.
    clg_bb = ceiling.get_BoundingBox(None)
    below = []
    for fl, top, fl_poly in floor_data:
        if top >= clg_bottom - 0.01:
            continue
        if clg_bb:
            fl_bb = fl.get_BoundingBox(None)
            if fl_bb:
                if (fl_bb.Max.X <= clg_bb.Min.X or fl_bb.Min.X >= clg_bb.Max.X or
                        fl_bb.Max.Y <= clg_bb.Min.Y or fl_bb.Min.Y >= clg_bb.Max.Y):
                    continue  # bounding boxes don't overlap in XY — skip
        below.append((fl, top, fl_poly))

    if not below:
        # No floor elements below — fall back to level datum
        clearance = clg_bottom - lvl.Elevation
        no_floor.append(ceiling.Id)

    elif len(below) == 1:
        # Exactly one floor below — use it directly, no overlap check needed
        _, floor_top, _ = below[0]
        clearance = clg_bottom - floor_top

    else:
        # Multiple floors below — compute 2-D overlap for every one of them.
        # We check ALL floors (not just the nearest) because two floors at
        # different elevations can each cover only part of the ceiling.
        clg_poly = horizontal_face_polygon(ceiling, upward=False)

        scored = []
        for fl, floor_top, fl_poly in below:
            if clg_poly and fl_poly:
                frac = overlap_fraction(clg_poly, fl_poly)
            else:
                frac = 0.0
            scored.append((fl, floor_top, frac))

        # Floors that individually cover >= 95 % of the ceiling footprint
        dominant = [
            (fl, top, frac)
            for fl, top, frac in scored
            if frac >= DOMINANCE_THRESHOLD
        ]

        if dominant:
            # One or more dominant floors — use the nearest one (highest top)
            dominant.sort(key=lambda x: -x[1])
            _, floor_top, _ = dominant[0]
            clearance = clg_bottom - floor_top
        else:
            # No single floor covers >= 95 % — ambiguous, log error.
            # Clear any stale CLR value so the tag shows nothing.
            p_shared = ceiling.LookupParameter(PARAM_NAME)
            if p_shared and not p_shared.IsReadOnly:
                try:
                    p_shared.ClearValue()
                except Exception:
                    p_shared.Set(0.0)
            scored.sort(key=lambda x: -x[2])  # best overlap first for readability
            errors.append((ceiling, scored))
            continue

    # Write calculated value to the shared parameter
    p_shared = ceiling.LookupParameter(PARAM_NAME)
    if p_shared and not p_shared.IsReadOnly:
        p_shared.Set(clearance)
        results.append((ceiling.Id, ft_to_ftin(clearance)))

t.Commit()

# ---------------------------------------------------------------------------
# place IndependentTag for updated ceilings (plan views only)
# ---------------------------------------------------------------------------

tags_placed = 0

if view.ViewType in (ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.AreaPlan):
    # Build set of ceiling IDs already tagged in this view to avoid duplicates
    existing_tagged = set()
    for _tag in (
        FilteredElementCollector(doc, view.Id)
        .OfCategory(BuiltInCategory.OST_CeilingTags)
        .WhereElementIsNotElementType()
        .ToElements()
    ):
        try:
            existing_tagged.add(_tag.TaggedLocalElementId.IntegerValue)
        except Exception:
            pass

    t_tags = Transaction(doc, "Place Ceiling Tags")
    t_tags.Start()
    for cid, _ in results:
        if cid.IntegerValue in existing_tagged:
            continue
        clg = doc.GetElement(cid)
        bbox = clg.get_BoundingBox(view) or clg.get_BoundingBox(None)
        pt = XYZ(
            (bbox.Min.X + bbox.Max.X) / 2.0,
            (bbox.Min.Y + bbox.Max.Y) / 2.0,
            0.0,
        ) if bbox else XYZ(0.0, 0.0, 0.0)
        try:
            IndependentTag.Create(
                doc,
                tag_type_id,
                view.Id,
                Reference(clg),
                False,
                TagOrientation.Horizontal,
                pt,
            )
            tags_placed += 1
        except Exception:
            pass
    t_tags.Commit()

# ---------------------------------------------------------------------------
# report  (styled HTML)
# ---------------------------------------------------------------------------

S = {
    "page":    "font-family:'Segoe UI',Arial,sans-serif;font-size:13px;color:#222;margin:0;padding:12px;",
    "header":  "background:#1e2d3d;color:#fff;padding:14px 18px;border-radius:6px;margin-bottom:14px;",
    "h_title": "margin:0 0 4px;font-size:17px;font-weight:600;letter-spacing:.3px;",
    "h_sub":   "margin:0;font-size:12px;opacity:.75;",
    "section": "border-radius:6px;margin-bottom:12px;overflow:hidden;",
    "sec_ok":  "border-left:4px solid #27ae60;background:#f0faf4;",
    "sec_warn":"border-left:4px solid #f39c12;background:#fffbf0;",
    "sec_err": "border-left:4px solid #e74c3c;background:#fff5f5;",
    "sec_hdr": "padding:10px 14px 4px;font-weight:600;font-size:13px;",
    "hdr_ok":  "color:#1e8449;",
    "hdr_warn":"color:#b7770d;",
    "hdr_err": "color:#c0392b;",
    "sec_note":"padding:2px 14px 8px;font-size:11px;color:#666;",
    "tbl":     "width:100%;border-collapse:collapse;font-size:12px;",
    "th":      "padding:7px 10px;text-align:left;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px;",
    "th_ok":   "background:#27ae60;color:#fff;",
    "th_warn": "background:#f39c12;color:#fff;",
    "th_err":  "background:#e74c3c;color:#fff;",
    "td":      "padding:6px 10px;border-bottom:1px solid rgba(0,0,0,.06);",
    "td_alt":  "background:rgba(0,0,0,.025);",
    "footer":  "margin-top:14px;padding-bottom:10px;",
    "badge":   "display:inline-block;padding:4px 12px;border-radius:12px;color:#fff;font-size:12px;font-weight:600;margin-right:6px;",
    "b_ok":    "background:#1e2d3d;",
    "b_warn":  "background:#1e2d3d;",
    "b_err":   "background:#1e2d3d;",
}

def bar(frac, width=90):
    filled = max(1, int(width * frac)) if frac > 0 else 0
    color  = "#27ae60" if frac >= DOMINANCE_THRESHOLD else (
             "#2980b9" if frac >= 0.5 else "#5d8aa8")
    return (
        '<div style="display:inline-block;vertical-align:middle;'
        'background:#ddd;height:8px;width:{w}px;border-radius:4px;">'
        '<div style="background:{c};height:8px;width:{f}px;border-radius:4px;"></div>'
        '</div>&nbsp;<span style="font-size:11px;color:#555;">{p:.1f}%</span>'
    ).format(w=width, c=color, f=filled, p=frac * 100)

html = '<div style="{page}">'.format(**S)

# header
html += (
    '<div style="{header}">'
    '<p style="{h_title}">&#128207; Ceiling Heights &mdash; CLR Calculator</p>'
    '<p style="{h_sub}">Model: <strong>{model}</strong>'
    ' &nbsp;&bull;&nbsp; Threshold: <strong>{thresh}%</strong>'
    ' &nbsp;&bull;&nbsp; Processed: <strong>{count}</strong> ceiling(s)</p>'
    '</div>'
).format(model=doc.Title, thresh=int(DOMINANCE_THRESHOLD * 100),
         count=len(ceilings), **S)

# ── off-template warning banner + log ────────────────────────────────────────
if off_template_info:
    _total_off = sum(v["count"] for v in off_template_info.values())
    _tag_rows  = ""
    _prev_ft   = None
    for _i, ((_fam, _typ, _vid), _info) in enumerate(
            sorted(off_template_info.items(),
                   key=lambda x: (x[1]["family"], x[1]["type"], x[1]["view"]))):
        _bg       = ' style="{td_alt}"'.format(**S) if _i % 2 else ""
        _ids_cs   = CsList[ElementId](_info["ids"])
        _cnt_link = output.linkify(_ids_cs, title=str(_info["count"]))
        _cur_ft   = (_fam, _typ)
        _fam_cell = _fam if _cur_ft != _prev_ft else ""
        _typ_cell = _typ if _cur_ft != _prev_ft else ""
        _prev_ft  = _cur_ft
        _tag_rows += (
            "<tr{bg}>"
            "<td style='{td}'>{fam}</td>"
            "<td style='{td}'>{typ}</td>"
            "<td style='{td}'>{view}</td>"
            "<td style='{td}'>{sheet}</td>"
            "<td style='{td};text-align:center;'><strong>{cnt}</strong></td>"
            "</tr>"
        ).format(bg=_bg, fam=_fam_cell, typ=_typ_cell,
                 view=_info["view"], sheet=_info["sheet"],
                 cnt=_cnt_link, **S)

    html += (
        '<div style="{section}{sec_warn}">'
        '<div style="padding:6px 14px;font-size:11px;color:#b7770d;">'
        '&#9888; <strong>Off-template ceiling tags detected &mdash; {tt} instance(s).</strong> '
        'These families are NOT the CLR tag (<strong>{tmpl}</strong>). '
        'Original Revit tags = ceiling-to-level &nbsp;|&nbsp; CLR tags = ceiling-to-floor.</div>'
        '<table style="{tbl}">'
        '<tr><th style="{th}{th_warn}">Family</th>'
        '<th style="{th}{th_warn}">Type</th>'
        '<th style="{th}{th_warn}">View</th>'
        '<th style="{th}{th_warn}">Sheet</th>'
        '<th style="{th}{th_warn}" align="center">Instances</th></tr>'
        '{rows}'
        '</table></div>'
    ).format(tt=_total_off, tmpl=_template_family, rows=_tag_rows, **S)

# ── updated ──────────────────────────────────────────────────────────────────
if results:
    rows = ""
    for i, (cid, dist) in enumerate(results):
        bg = ' style="{td_alt}"'.format(**S) if i % 2 else ""
        rows += (
            "<tr{bg}>"
            "<td style='{td}'>{clg}</td>"
            "<td style='{td}'><strong>{dist}</strong></td>"
            "</tr>"
        ).format(bg=bg, clg=output.linkify(cid), dist=dist, **S)

    html += (
        '<div style="{section}{sec_ok}">'
        '<div style="{sec_hdr}{hdr_ok}">&#10003; Updated ({n})</div>'
        '<table style="{tbl}">'
        '<tr><th style="{th}{th_ok}">Ceiling</th>'
        '<th style="{th}{th_ok}">CLR</th></tr>'
        '{rows}'
        '</table></div>'
    ).format(n=len(results), rows=rows, **S)

# ── errors ────────────────────────────────────────────────────────────────────
if errors:
    error_ids = CsList[ElementId]()
    rows = ""
    for i, (ceiling, fracs) in enumerate(errors):
        error_ids.Add(ceiling.Id)
        for j, (fl, _, frac) in enumerate(fracs):
            error_ids.Add(fl.Id)
            bg = ' style="{td_alt}"'.format(**S) if (i + j) % 2 else ""
            rows += (
                "<tr{bg}>"
                "<td style='{td}'>{clg}</td>"
                "<td style='{td}'>{fl}</td>"
                "<td style='{td}'>{bar}</td>"
                "</tr>"
            ).format(
                bg=bg,
                clg=output.linkify(ceiling.Id) if j == 0 else
                    '<span style="color:#bbb;">&#8595;</span>',
                fl=output.linkify(fl.Id),
                bar=bar(frac),
                **S
            )

    html += (
        '<div style="{section}{sec_err}">'
        '<div style="{sec_hdr}{hdr_err}">'
        '&#10007; Multiple floors &mdash; no floor is dominant (&ge; {thresh}%) &nbsp;({n})</div>'
        '<div style="{sec_note}">These ceilings &amp; floors have been '
        '<strong>selected</strong> in the model for review.</div>'
        '<table style="{tbl}">'
        '<tr><th style="{th}{th_err}">Ceiling</th>'
        '<th style="{th}{th_err}">Floor below</th>'
        '<th style="{th}{th_err}">Projection overlap</th></tr>'
        '{rows}'
        '</table></div>'
    ).format(thresh=int(DOMINANCE_THRESHOLD * 100), n=len(errors), rows=rows, **S)

    uidoc.Selection.SetElementIds(error_ids)

# ── summary footer ────────────────────────────────────────────────────────────
html += (
    '<div style="{footer}">'
    '<span style="{badge}{b_ok}">&#10003; Updated: {ok}</span>'
    '<span style="{badge}{b_warn}">&#9888; No floor: {warn}</span>'
    '<span style="{badge}{b_err}">&#10007; Errors: {err}</span>'
    '<span style="{badge}{b_ok}">&#127991; Tagged: {tagged}</span>'
    '</div>'
).format(ok=len(results), warn=len(no_floor), err=len(errors), tagged=tags_placed, **S)

html += "</div>"
output.print_html(html)

