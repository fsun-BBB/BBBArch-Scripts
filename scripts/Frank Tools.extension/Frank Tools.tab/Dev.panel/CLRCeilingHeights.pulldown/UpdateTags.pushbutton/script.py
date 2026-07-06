# -*- coding: utf-8 -*-
__title__ = "Update\nCeiling\nTags"
__doc__ = """Version = 5.0
Date    = 22.06.2026
________________________________________________________________
Description:
Calculates the clear height (CLR) from every ceiling to the
floor directly below it.  Results are written to the shared
parameter "S_Ceiling Tag_Clear Height".

Requires the tag family "B_ANNO_Ceiling Tag_Clear Height" to be
loaded, and Configure to have been run first.
________________________________________________________________
How-To:
1. Run Configure to set clearance thresholds and search depth.
2. Click this button — calculation runs automatically.
________________________________________________________________
Author: BBB DCT Team"""

import os
import uuid
import json

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    ExternalDefinitionCreationOptions,
    FamilySymbol,
    FilteredElementCollector,
    GroupTypeId,
    Options,
    Solid,
    SpecTypeId,
    Transaction,
)
from Autodesk.Revit.UI import (
    TaskDialog,
    TaskDialogCommonButtons,
    TaskDialogCommandLinkId,
    TaskDialogResult,
)
from System.Collections.Generic import List as CsList
import System as _System
import clr as _clr
_clr.AddReference('System.Windows.Forms')
import System.Windows.Forms as _WinForms
from pyrevit import script, forms
from clr_ceiling_config import is_configured, load

app   = __revit__.Application
uidoc = __revit__.ActiveUIDocument
doc   = __revit__.ActiveUIDocument.Document  # type: ignore

# ---------------------------------------------------------------------------
# configuration check
# ---------------------------------------------------------------------------

if not is_configured():
    forms.alert(
        "Please run Configure first to set your clearance thresholds and search depth.",
        title="Update Ceiling Tags",
        warn_icon=True
    )
    script.exit()

_cfg = load()
SEARCH_DEPTH = _cfg['search_depth']
MIN_CLR_T3   = _cfg['tier3']
MIN_CLR_T2   = _cfg['tier2']
MIN_CLR_T1   = _cfg['tier1']

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

PARAM_NAME          = "S_Ceiling Tag_Clear Height"
SPF_PATH            = os.path.normpath(
                          os.path.join(os.path.dirname(__file__),
                                       '..', '..', '..', '..', 'BBB_SharedParams.txt'))
SPF_GROUP           = "BBB Ceiling Data"
CLR_FAMILY          = "B_ANNO_Ceiling Tag_Clear Height"
DOMINANCE_THRESHOLD = 0.95
GRID_N              = 9

# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def polygon_area(pts):
    n = len(pts)
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(a) / 2.0


def point_in_polygon(x, y, poly):
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
                if upward  and nz < 0.9:  continue
                if not upward and nz > -0.9: continue
                try:
                    loops = list(face.GetEdgesAsCurveLoops())
                except Exception:
                    continue
                if not loops:
                    continue
                pts  = [(c.GetEndPoint(0).X, c.GetEndPoint(0).Y) for c in loops[0]]
                area = polygon_area(pts)
                if area > best_area:
                    best_area = area
                    best_pts  = pts
    except Exception:
        pass
    if best_pts is None:
        bb = element.get_BoundingBox(None)
        if bb:
            best_pts = [
                (bb.Min.X, bb.Min.Y), (bb.Max.X, bb.Min.Y),
                (bb.Max.X, bb.Max.Y), (bb.Min.X, bb.Max.Y),
            ]
    return best_pts


def overlap_fraction(clg_poly, flr_poly):
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
# pre-run validation — CLR family check
# ---------------------------------------------------------------------------

CLR_FAMILY_PATH = (
    r"N:\Design Technology Resources\01_BIM CONTENT\Toolbar Content"
    r"\Annotations\B_ANNO_Ceiling Tag_Clear Height.rfa"
)


def _find_clr_types():
    return [
        t for t in
        FilteredElementCollector(doc)
        .OfClass(FamilySymbol)
        .OfCategory(BuiltInCategory.OST_CeilingTags)
        .ToElements()
        if t.Family.Name == CLR_FAMILY
    ]


_clr_types = _find_clr_types()

if not _clr_types:
    _dlg = TaskDialog("Update Ceiling Tags")
    _dlg.MainInstruction = "Missing Required Ceiling Tag Family"
    _dlg.MainContent = (
        "The required ceiling tag family \"{}\" is not loaded in this project.\n\n"
        "Click \"Load Family\" to load it automatically, or load it manually "
        "before running.".format(CLR_FAMILY)
    )
    _dlg.AddCommandLink(
        TaskDialogCommandLinkId.CommandLink1,
        "Load Family",
        "Load \"{}\" from the BBB content library".format(CLR_FAMILY),
    )
    _dlg.AddCommandLink(
        TaskDialogCommandLinkId.CommandLink2,
        "View Documentation",
        "Open detailed instructions in SharePoint",
    )
    _dlg.CommonButtons = TaskDialogCommonButtons.Close
    _dlg.DefaultButton = TaskDialogResult.Close
    _result = _dlg.Show()

    if _result == TaskDialogResult.CommandLink2:
        os.startfile(
            "https://beyerblinderbelle.sharepoint.com/sites/revitstandards/SitePages/"
            "Clear-Ceiling-Tags.aspx?csf=1&web=1&e=lPmO0h&CID=1c2d935e-70a1-4e9a-ad30-aef04834b0bd"
        )
        script.exit()
    elif _result != TaskDialogResult.CommandLink1:
        script.exit()

    # user chose "Load Family" — pull it in from the N: drive automatically
    if not os.path.exists(CLR_FAMILY_PATH):
        forms.alert(
            "Could not find the family file on the N: drive:\n\n{}\n\n"
            "Check your network connection or load it manually.".format(CLR_FAMILY_PATH),
            title="Load Family Failed",
            warn_icon=True,
        )
        script.exit()

    t_load = Transaction(doc, "Load CLR Ceiling Tag Family")
    t_load.Start()
    try:
        _loaded = doc.LoadFamily(CLR_FAMILY_PATH)
    except Exception as e:
        t_load.RollBack()
        forms.alert(
            "Failed to load family:\n\n{}".format(e),
            title="Load Family Failed",
            warn_icon=True,
        )
        script.exit()
    else:
        if _loaded:
            t_load.Commit()
        else:
            t_load.RollBack()

    _clr_types = _find_clr_types()
    if not _clr_types:
        forms.alert(
            "The family could not be loaded. Please load it manually before running.",
            title="Load Family Failed",
            warn_icon=True,
        )
        script.exit()

# ---------------------------------------------------------------------------
# output window
# ---------------------------------------------------------------------------

output = script.get_output()
output.set_title("Update Ceiling Tags")

def _js(code):
    try:
        output.renderer.Document.InvokeScript(
            "eval", _System.Array[object]([code])
        )
        _WinForms.Application.DoEvents()
    except Exception:
        pass

def _is_cancelled():
    try:
        return bool(output.renderer.Document.InvokeScript(
            "eval", _System.Array[object](["window._cancelled === true"])
        ))
    except Exception:
        return False

# ---------------------------------------------------------------------------
# inject CSS
# ---------------------------------------------------------------------------

CSS = (
    "body{font-family:'Segoe UI',Arial,sans-serif;margin:0;padding:16px;background:#fff;color:#222;}"
    ".hdr{margin-bottom:16px;padding-bottom:12px;border-bottom:2px solid #D0D7DE;}"
    ".hdr h1{margin:0 0 3px;font-size:15px;font-weight:700;color:#111;}"
    ".hdr p{margin:0;font-size:10px;color:#888;text-transform:uppercase;letter-spacing:.6px;font-weight:600;}"
    ".prog-wrap{margin-bottom:14px;}"
    ".prog-label{position:relative;height:20px;margin-bottom:5px;}"
    ".prog-text{position:absolute;left:0;top:50%;font-size:11px;color:#888;margin-top:-6px;}"
    ".cancel-btn{position:absolute;right:0;top:50%;margin-top:-8px;padding:2px 8px;"
    "background:#888;color:#fff;border:none;border-radius:3px;cursor:pointer;font-size:10px;}"
    ".cancel-btn:disabled{background:#ccc;cursor:default;}"
    ".prog-bg{background:#E8EBEF;height:3px;border-radius:2px;}"
    ".prog-fill{background:#2C3E50;height:3px;width:0%;border-radius:2px;}"
    ".res-section{margin-bottom:8px;border:1px solid #D0D7DE;border-radius:8px;overflow:hidden;}"
    ".res-hdr{display:-ms-flexbox;display:flex;-ms-flex-pack:justify;justify-content:space-between;"
    "-ms-flex-align:center;align-items:center;padding:8px 14px;background:#F6F8FA;"
    "border-bottom:2px solid #D0D7DE;cursor:pointer;"
    "font-size:10px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:.5px;}"
    ".res-lbl{font-size:10px;color:#888;font-weight:400;text-transform:none;letter-spacing:0;}"
    ".res-body{background:#fff;padding:10px;}"
)

output.inject_to_head('style', CSS)

# ---------------------------------------------------------------------------
# inject JS
# ---------------------------------------------------------------------------

JS = (
    "window._cancelled=false;"
    "function cancelRun(){window._cancelled=true;var b=document.getElementById('cancel-btn');if(b){b.disabled=true;b.innerHTML='Cancelling';}}"
    "function toggleSection(id){"
    "  var body=document.getElementById(id+'-body');"
    "  var lbl=document.getElementById(id+'-lbl');"
    "  if(!body)return;"
    "  if(body.style.display==='none'){body.style.display='block';if(lbl)lbl.innerHTML='\\u25b2 Collapse';}"
    "  else{body.style.display='none';if(lbl)lbl.innerHTML='\\u25bc Expand';}"
    "}"
)

output.inject_script(JS)

# ---------------------------------------------------------------------------
# initial HTML — header + progress bar (auto-starts)
# ---------------------------------------------------------------------------

output.print_html(
    '<div class="hdr"><h1>Update Ceiling Tags</h1>'
    '<p>Real Ceiling Height &mdash; Calculating clear heights</p></div>'
    '<div class="prog-wrap" id="prog-wrap" style="display:block;">'
    '  <div class="prog-label">'
    '    <span class="prog-text"><span id="proc-text">Starting</span><span id="proc-dots">.</span></span>'
    '    <button class="cancel-btn" id="cancel-btn" onclick="cancelRun()">&#10005; Cancel</button>'
    '  </div>'
    '  <div class="prog-bg"><div class="prog-fill" id="proc-bar"></div></div>'
    '</div>'
)

try:
    output.window.WaitReadyBrowser()
except Exception:
    pass

# ---------------------------------------------------------------------------
# progress helpers
# ---------------------------------------------------------------------------

_dots_cycle = ['.', '..', '...']
_dot_idx    = 0

def _tick_dots():
    global _dot_idx
    d = _dots_cycle[_dot_idx % 3]
    _dot_idx += 1
    return d

def _upd(text, pct, dots=None):
    if dots is None:
        dots = _tick_dots()
    _js(
        "var t=document.getElementById('proc-text');if(t)t.innerHTML={t};"
        "var d=document.getElementById('proc-dots');if(d)d.innerHTML={d};"
        "var b=document.getElementById('proc-bar');if(b)b.style.width='{p}%';"
        .format(t=json.dumps(text), d=json.dumps(dots), p=pct)
    )

def _finish_progress():
    _js(
        "var d=document.getElementById('proc-dots');if(d)d.innerHTML='';"
        "var b=document.getElementById('proc-bar');if(b)b.style.width='100%';"
        "var btn=document.getElementById('cancel-btn');if(btn)btn.style.display='none';"
    )

# ---------------------------------------------------------------------------
# result HTML helpers
# ---------------------------------------------------------------------------

def _tbl_row(cells, alt=False):
    bg = ' style="background:#F6F8FA;"' if alt else ''
    return '<tr{}>'.format(bg) + ''.join(
        '<td style="padding:6px 10px;border-bottom:1px solid #E8EBEF;font-size:11px;color:#333;">{}</td>'.format(c)
        for c in cells
    ) + '</tr>'

def _kv_row(label, value, alt=False):
    bg = 'background:#F6F8FA;' if alt else ''
    return (
        u'<tr style="{bg}">'
        u'<td style="padding:6px 10px;border-bottom:1px solid #E8EBEF;'
        u'font-size:10px;color:#888;text-transform:uppercase;letter-spacing:.5px;font-weight:600;">{lbl}</td>'
        u'<td style="padding:6px 12px 6px 10px;border-bottom:1px solid #E8EBEF;'
        u'font-size:12px;font-weight:600;color:#111;font-family:Consolas,monospace;">{val}</td>'
        u'</tr>'
    ).format(bg=bg, lbl=label, val=value)

def _tbl(headers, rows):
    if headers:
        th = ''.join(
            '<th style="padding:7px 10px;text-align:left;font-size:10px;font-weight:600;'
            'text-transform:uppercase;letter-spacing:.5px;background:#F6F8FA;'
            'color:#555;border-bottom:2px solid #D0D7DE;">{h}</th>'
            .format(h=h) for h in headers
        )
        thead = '<tr>{}</tr>'.format(th)
    else:
        thead = ''
    return (
        '<table style="width:100%;border-collapse:collapse;margin-top:4px;">'
        '{}{}</table>'
        .format(thead, ''.join(rows))
    )

def _inject_results(group, title, html, collapsed=False):
    lbl   = u'&#9660; Expand' if collapsed else u'&#9650; Collapse'
    style = u'display:none;' if collapsed else u''
    output.print_html(
        u'<div class="res-section">'
        u'<div class="res-hdr" onclick="toggleSection(\'{group}\')">'
        u'<span>{title}</span>'
        u'<span class="res-lbl" id="{group}-lbl">{lbl}</span>'
        u'</div>'
        u'<div id="{group}-body" class="res-body" style="{style}">{html}</div>'
        u'</div>'.format(group=group, title=title, html=html,
                         lbl=lbl, style=style)
    )

# ---------------------------------------------------------------------------
# CALCULATE — ceiling CLR
# ---------------------------------------------------------------------------

results          = []   # (ceiling_id, dist_str, changed)  — all successfully written
_changed_results = []   # subset of results where value changed
errors           = []
no_floor         = []
warn1            = []
warn2            = []
warn3            = []
skipped          = []   # (ceiling_id, reason) — collected but could not be processed

_upd("Collecting elements", 0)

ensure_spf()
if not param_already_bound(doc):
    bind_shared_param(doc, app)

ceilings = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Ceilings)
    .WhereElementIsNotElementType()
    .ToElements()
)
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
    floor_data.append((fl, top))

if not ceilings:
    _upd("No ceilings found", 100, '')
    output.print_html(
        u'<div style="margin:24px auto;max-width:480px;text-align:center;'
        u'padding:32px 24px;background:#f8f9fa;border-radius:8px;'
        u'border:1px solid #e0e0e0;">'
        u'<div style="font-size:32px;margin-bottom:12px;">&#127968;</div>'
        u'<p style="font-size:15px;font-weight:600;color:#333;margin:0 0 8px;">No ceilings found</p>'
        u'<p style="font-size:12px;color:#666;margin:0;">'
        u'This model has no ceiling elements. Open a model that contains ceilings and run the tool again.'
        u'</p></div>'
    )
    script.exit()
else:
    _n         = len(ceilings)
    _w         = "ceiling" if _n == 1 else "ceilings"
    _cancelled = False

    t = Transaction(doc, "Update CLR")
    t.Start()

    for _i, ceiling in enumerate(ceilings):
        if _i % 5 == 0 or _i == _n - 1:
            if _is_cancelled():
                _cancelled = True
                break
            _cur = _i + 1
            _pct = int(_cur * 100.0 / _n)
            _upd("Processing {} / {}  {}".format(_cur, _n, _w), _pct)

        lvl  = doc.GetElement(ceiling.LevelId)
        if lvl is None:
            skipped.append((ceiling.Id, 'No level — broken level reference'))
            continue
        p_ht = ceiling.get_Parameter(BuiltInParameter.CEILING_HEIGHTABOVELEVEL_PARAM)
        if p_ht is None:
            skipped.append((ceiling.Id, 'Missing height parameter'))
            continue
        clg_bottom  = lvl.Elevation + p_ht.AsDouble()
        _from_floor = False

        clg_bb = ceiling.get_BoundingBox(None)
        below  = []
        for fl, top in floor_data:
            if top >= clg_bottom - 0.01:
                continue
            if clg_bottom - top > SEARCH_DEPTH:
                continue
            if clg_bb:
                fl_bb = fl.get_BoundingBox(None)
                if fl_bb:
                    if (fl_bb.Max.X <= clg_bb.Min.X or fl_bb.Min.X >= clg_bb.Max.X or
                            fl_bb.Max.Y <= clg_bb.Min.Y or fl_bb.Min.Y >= clg_bb.Max.Y):
                        continue
            below.append((fl, top))

        if not below:
            clearance = clg_bottom - lvl.Elevation
            no_floor.append(ceiling.Id)
        elif len(below) == 1:
            _, floor_top = below[0]
            clearance   = clg_bottom - floor_top
            _from_floor = True
        else:
            clg_poly = horizontal_face_polygon(ceiling, upward=False)
            scored   = []
            for fl, floor_top in below:
                fl_poly = horizontal_face_polygon(fl, upward=True)
                frac    = overlap_fraction(clg_poly, fl_poly) if (clg_poly and fl_poly) else 0.0
                scored.append((fl, floor_top, frac))

            dominant = [(fl, top, frac) for fl, top, frac in scored if frac >= DOMINANCE_THRESHOLD]

            if dominant:
                dominant.sort(key=lambda x: -x[1])
                _, floor_top, _ = dominant[0]
                clearance   = clg_bottom - floor_top
                _from_floor = True
            else:
                p_shared = ceiling.LookupParameter(PARAM_NAME)
                if p_shared and not p_shared.IsReadOnly:
                    try:    p_shared.ClearValue()
                    except: p_shared.Set(0.0)
                scored.sort(key=lambda x: -x[2])
                errors.append((ceiling, scored))
                continue

        p_shared = ceiling.LookupParameter(PARAM_NAME)
        if p_shared and not p_shared.IsReadOnly:
            _old_val = p_shared.AsDouble() if p_shared.HasValue else None
            _changed = (_old_val is None) or (abs(_old_val - clearance) > 0.0001)
            p_shared.Set(clearance)
            results.append((ceiling.Id, ft_to_ftin(clearance), _changed))
            if _from_floor:
                if   clearance < MIN_CLR_T1: warn1.append((ceiling.Id, ft_to_ftin(clearance)))
                elif clearance < MIN_CLR_T2: warn2.append((ceiling.Id, ft_to_ftin(clearance)))
                elif clearance < MIN_CLR_T3: warn3.append((ceiling.Id, ft_to_ftin(clearance)))

    if _cancelled:
        t.RollBack()
        _js(
            "var d=document.getElementById('proc-dots');if(d)d.innerHTML='';"
            "var btn=document.getElementById('cancel-btn');if(btn)btn.style.display='none';"
        )
        output.print_html(
            '<p style="color:#e74c3c;font-size:12px;font-weight:600;">'
            '&#10060; Cancelled &#8212; no changes saved.</p>'
        )
        script.exit()
    else:
        t.Commit()

    _changed_results = [(cid, dist) for cid, dist, chg in results if chg]

# ---------------------------------------------------------------------------
# OUTPUT SECTIONS — shown after Calculate completes
# ---------------------------------------------------------------------------

# ── Section 1: Results (expanded) ─────────────────────────────────────────
_n_updated = len(results)
_n_changed = len(_changed_results)
_stat_rows = [
    _kv_row('Processed', str(_n)),
    _kv_row('Updated',
            '{} ({} value changed)'.format(_n_updated, _n_changed), True),
    _kv_row('No level reference (Broken)',   str(len(skipped))),
    _kv_row('Ambiguous floor (Unresolved)',  str(len(errors)), True),
]
_inject_results('results', 'Results', _tbl([], _stat_rows),
                collapsed=False)

# ── Section 2: Broken Ceilings (collapsed) ────────────────────────────────
if skipped:
    skip_ids = CsList[ElementId]([cid for cid, _ in skipped])
    sk_rows  = [_tbl_row([output.linkify(cid), reason], i % 2 == 1)
                for i, (cid, reason) in enumerate(skipped)]
    skip_html = (
        '<p style="font-size:11px;color:#555;margin:0 0 6px;">'
        'Could not be processed — selected in model for review.</p>'
    )
    skip_html += _tbl(['Ceiling', 'Reason'], sk_rows)
    _inject_results(
        'broken',
        'Broken Ceilings &#8212; No Level Reference ({n})'.format(
            n=len(skipped)),
        skip_html,
        collapsed=True
    )
    uidoc.Selection.SetElementIds(skip_ids)

# ── Section 3: Unresolved Ceilings (collapsed) ────────────────────────────
if errors:
    err_rows = []
    for i, (ceil, fracs) in enumerate(errors):
        for j, (fl, _, frac) in enumerate(fracs):
            filled = max(1, int(80 * frac)) if frac > 0 else 0
            bar = (
                '<div style="display:inline-block;vertical-align:middle;'
                'background:#ddd;height:6px;width:80px;border-radius:3px;">'
                '<div style="background:#999;height:6px;width:{f}px;'
                'border-radius:3px;"></div></div>'
                ' <span style="font-size:10px;color:#555;">{p:.0f}%</span>'
                .format(f=filled, p=frac * 100)
            )
            clg_cell = output.linkify(ceil.Id) if j == 0 else '&#8595;'
            err_rows.append(
                _tbl_row([clg_cell, output.linkify(fl.Id), bar],
                          (i + j) % 2 == 1)
            )
    err_html = (
        '<p style="font-size:11px;color:#555;margin:0 0 6px;">'
        'Multiple floors found below — none covers &#8805; 95% of the '
        'ceiling footprint. CLR value was cleared.</p>'
    )
    err_html += _tbl(['Ceiling', 'Floor below', 'Overlap'], err_rows)
    _inject_results(
        'unresolved',
        'Unresolved Ceilings &#8212; Ambiguous Floor ({n})'.format(
            n=len(errors)),
        err_html,
        collapsed=True
    )

# ---------------------------------------------------------------------------
# finish
# ---------------------------------------------------------------------------

_finish_progress()
_upd("&#10003; Done", 100, '')


try:
    output.window.WaitReadyBrowser()
    output.renderer.Document.Window.ScrollTo(0, 0)
    output.window.Show()
    output.window.Activate()
    output.window.Topmost = True
    output.window.Topmost = False
except Exception:
    pass
