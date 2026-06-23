# -*- coding: utf-8 -*-
__title__ = "Clearance\nCheck"
__doc__ = """Version = 1.0
Date    = 22.06.2026
________________________________________________________________
Description:
Audits ceiling tags and clearance thresholds across the entire
model.

Tag Audit   — finds ceiling tags NOT using the standard
              B_ANNO_Ceiling Tag_Clear Height family and groups
              them by family, type, view, and sheet.

Clearance   — reads existing S_Ceiling Tag_Clear Height values
              from all ceilings and flags those below the
              configured tier thresholds.

Requires Configure to have been run first.
________________________________________________________________
How-To:
1. Run Configure to set clearance thresholds.
2. Click this button — the audit runs automatically.
________________________________________________________________
Author: BBB DCT Team"""

import json

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    Viewport,
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
        title="Clearance Check",
        warn_icon=True
    )
    script.exit()

_cfg = load()
MIN_CLR_T3 = _cfg['tier3']
MIN_CLR_T2 = _cfg['tier2']
MIN_CLR_T1 = _cfg['tier1']

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

PARAM_NAME = "S_Ceiling Tag_Clear Height"
CLR_FAMILY = "B_ANNO_Ceiling Tag_Clear Height"

# ---------------------------------------------------------------------------
# output window
# ---------------------------------------------------------------------------

output = script.get_output()
output.set_title("Clearance Check")

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
    ".hdr{margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid #ebebeb;}"
    ".hdr h1{margin:0 0 2px;font-size:15px;font-weight:600;color:#111;}"
    ".hdr p{margin:0;font-size:11px;color:#999;}"
    ".prog-wrap{margin-bottom:12px;}"
    ".prog-label{position:relative;height:20px;margin-bottom:5px;}"
    ".prog-text{position:absolute;left:0;top:50%;font-size:11px;color:#999;margin-top:-6px;}"
    ".cancel-btn{position:absolute;right:0;top:50%;margin-top:-8px;padding:2px 8px;"
    "background:#999;color:#fff;border:none;border-radius:3px;cursor:pointer;font-size:10px;}"
    ".cancel-btn:disabled{background:#ccc;cursor:default;}"
    ".prog-bg{background:#ebebeb;height:3px;border-radius:2px;}"
    ".prog-fill{background:#111;height:3px;width:0%;border-radius:2px;}"
    ".res-section{margin-bottom:6px;border:1px solid #ebebeb;border-radius:4px;overflow:hidden;}"
    ".res-hdr{display:-ms-flexbox;display:flex;-ms-flex-pack:justify;justify-content:space-between;"
    "-ms-flex-align:center;align-items:center;padding:7px 12px;background:#f8f8f8;"
    "border-bottom:1px solid #ebebeb;cursor:pointer;font-size:12px;font-weight:600;color:#333;}"
    ".res-lbl{font-size:11px;color:#999;font-weight:400;}"
    ".res-body{background:#fff;padding:8px;}"
    ".sub-section{margin:4px 0;border:1px solid #ebebeb;border-radius:3px;overflow:hidden;}"
    ".sub-hdr{display:-ms-flexbox;display:flex;-ms-flex-pack:justify;justify-content:space-between;"
    "-ms-flex-align:center;align-items:center;padding:5px 10px;background:#f5f5f5;"
    "border-bottom:1px solid #ebebeb;cursor:pointer;font-size:11px;font-weight:600;color:#555;}"
    ".sub-lbl{font-size:10px;color:#aaa;font-weight:400;}"
    ".sub-body{background:#fff;padding:6px;}"
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
# initial HTML — header + progress bar
# ---------------------------------------------------------------------------

output.print_html(
    '<div class="hdr"><h1>&#128269; Clearance Check</h1>'
    '<p>Auditing ceiling tags and clearance thresholds</p></div>'
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
    bg = ' style="background:rgba(0,0,0,.03);"' if alt else ''
    return '<tr{}>'.format(bg) + ''.join(
        '<td style="padding:5px 8px;border-bottom:1px solid #eee;font-size:11px;">{}</td>'.format(c)
        for c in cells
    ) + '</tr>'

def _kv_row(label, value, alt=False):
    bg = 'background:rgba(0,0,0,.03);' if alt else ''
    return (
        u'<tr style="{bg}">'
        u'<td style="padding:5px 8px;border-bottom:1px solid #eee;font-size:11px;">{lbl}</td>'
        u'<td style="padding:5px 12px 5px 8px;border-bottom:1px solid #eee;'
        u'font-size:11px;">{val}</td>'
        u'</tr>'
    ).format(bg=bg, lbl=label, val=value)

def _tbl(headers, rows):
    if headers:
        th = ''.join(
            '<th style="padding:6px 8px;text-align:left;font-size:10px;font-weight:600;'
            'text-transform:uppercase;letter-spacing:.4px;background:#f0f0f0;color:#555;">{h}</th>'
            .format(h=h) for h in headers
        )
        thead = '<tr>{}</tr>'.format(th)
    else:
        thead = ''
    return (
        '<table style="width:100%;border-collapse:collapse;margin-top:6px;">'
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
# TAG AUDIT — find off-template ceiling tags
# ---------------------------------------------------------------------------

_upd("Scanning model for ceiling tags", 10)

_view_to_sheet = {}
for _vp in FilteredElementCollector(doc).OfClass(Viewport).ToElements():
    _sht = doc.GetElement(_vp.SheetId)
    try:
        _view_to_sheet[_vp.ViewId.IntegerValue] = "{} - {}".format(
            _sht.SheetNumber, _sht.Name)
    except Exception:
        pass

off_template_info = {}

for _tag in (
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_CeilingTags)
    .WhereElementIsNotElementType()
    .ToElements()
):
    _sym = doc.GetElement(_tag.GetTypeId())
    try:    _fam = _sym.Family.Name
    except: _fam = "Unknown"
    if _fam == CLR_FAMILY:
        continue
    try:
        _typ = (_sym.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString() or _sym.Name)
    except:
        _typ = "Unknown"
    _vid   = _tag.OwnerViewId.IntegerValue
    _ve    = doc.GetElement(_tag.OwnerViewId)
    _vname = _ve.Name if _ve else "Unknown View"
    _sheet = _view_to_sheet.get(_vid, "Not on sheet")
    _key   = (_fam, _typ, _vid)
    if _key not in off_template_info:
        off_template_info[_key] = {"family": _fam, "type": _typ,
                                   "view": _vname, "sheet": _sheet,
                                   "count": 0, "ids": []}
    off_template_info[_key]["count"] += 1
    off_template_info[_key]["ids"].append(_tag.Id)

if _is_cancelled():
    _js("var btn=document.getElementById('cancel-btn');if(btn)btn.style.display='none';")
    output.print_html(
        '<p style="color:#e74c3c;font-size:12px;font-weight:600;">'
        '&#10060; Cancelled.</p>'
    )
    script.exit()

_upd("Tag audit complete", 40)

if not off_template_info:
    _ta_html   = ('<p style="font-size:11px;color:#27ae60;padding:2px 0;">'
                  '&#10003; No off-template ceiling tags found.</p>')
    _ta_title  = 'Tag Audit &#8212; off-template tag(s) (0)'
else:
    _total_off = sum(v["count"] for v in off_template_info.values())
    _ta_rows   = []
    _prev      = None
    for _i2, ((_fam2, _typ2, _vid2), _info) in enumerate(
            sorted(off_template_info.items(),
                   key=lambda x: (x[1]["family"], x[1]["type"], x[1]["view"]))):
        _cur_ft = (_fam2, _typ2)
        _fc     = _fam2 if _cur_ft != _prev else ""
        _tc     = _typ2 if _cur_ft != _prev else ""
        _prev   = _cur_ft
        _ids_cs = CsList[ElementId](_info["ids"])
        _ta_rows.append(_tbl_row(
            [_fc, _tc, _info["view"], _info["sheet"],
             output.linkify(_ids_cs, title=str(_info["count"]))],
            _i2 % 2 == 1
        ))
    _ta_html  = _tbl(['Family', 'Type', 'View', 'Sheet', 'Instances'], _ta_rows)
    _ta_title = 'Tag Audit &#8212; off-template tag(s) ({})'.format(_total_off)

# ---------------------------------------------------------------------------
# CLEARANCE AUDIT — read existing param values
# ---------------------------------------------------------------------------

_upd("Checking clearances", 50)

warn1 = []
warn2 = []
warn3 = []

def _ftin(ft):
    total_in = ft * 12.0
    feet     = int(total_in // 12)
    inches   = total_in - feet * 12.0
    if feet > 0:
        return "{:d}' - {:.0f}\"".format(feet, round(inches))
    return "{:.0f}\"".format(round(inches))

_all_ceilings = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Ceilings)
    .WhereElementIsNotElementType()
    .ToElements()
)
_nc = len(_all_ceilings)

for _ci, _clg in enumerate(_all_ceilings):
    if _ci % 20 == 0:
        if _is_cancelled():
            _js("var btn=document.getElementById('cancel-btn');if(btn)btn.style.display='none';")
            output.print_html(
                '<p style="color:#e74c3c;font-size:12px;font-weight:600;">'
                '&#10060; Cancelled.</p>'
            )
            script.exit()
        _pct = 50 + int((_ci + 1) * 50.0 / _nc) if _nc else 100
        _upd("Checking clearances  {} / {}".format(_ci + 1, _nc), _pct)

    _p = _clg.LookupParameter(PARAM_NAME)
    if not (_p and _p.HasValue):
        continue
    _v = _p.AsDouble()
    if _v <= 0:
        continue

    if   _v < MIN_CLR_T1: warn1.append((_clg.Id, _ftin(_v)))
    elif _v < MIN_CLR_T2: warn2.append((_clg.Id, _ftin(_v)))
    elif _v < MIN_CLR_T3: warn3.append((_clg.Id, _ftin(_v)))

_upd("Clearance audit complete", 100)

def _sub_section(group, title, html):
    return (
        u'<div class="sub-section">'
        u'<div class="sub-hdr" onclick="toggleSection(\'{g}\')">'
        u'<span>{t}</span>'
        u'<span class="sub-lbl" id="{g}-lbl">&#9660; Expand</span>'
        u'</div>'
        u'<div id="{g}-body" class="sub-body" style="display:none;">{h}</div>'
        u'</div>'
    ).format(g=group, t=title, h=html)

_ca_html = ''

if warn1:
    _w1rows  = [_tbl_row([output.linkify(cid), '<strong>{}</strong>'.format(d)], i%2==1)
                for i,(cid,d) in enumerate(warn1)]
    _ca_html += _sub_section(
        'tier1',
        'Tier 1 &#8212; Critical (under {}) ({})'.format(_ftin(MIN_CLR_T1), len(warn1)),
        _tbl(['Ceiling', 'CLR'], _w1rows)
    )

if warn2:
    _w2rows  = [_tbl_row([output.linkify(cid), '<strong>{}</strong>'.format(d)], i%2==1)
                for i,(cid,d) in enumerate(warn2)]
    _ca_html += _sub_section(
        'tier2',
        'Tier 2 &#8212; Warning (under {}) ({})'.format(_ftin(MIN_CLR_T2), len(warn2)),
        _tbl(['Ceiling', 'CLR'], _w2rows)
    )

if warn3:
    _w3rows  = [_tbl_row([output.linkify(cid), '<strong>{}</strong>'.format(d)], i%2==1)
                for i,(cid,d) in enumerate(warn3)]
    _ca_html += _sub_section(
        'tier3',
        'Tier 3 &#8212; Caution (under {}) ({})'.format(_ftin(MIN_CLR_T3), len(warn3)),
        _tbl(['Ceiling', 'CLR'], _w3rows)
    )

if not (warn1 or warn2 or warn3):
    _ca_html = (
        '<p style="font-size:11px;color:#27ae60;padding:2px 0;">'
        '&#10003; No clearance issues found.</p>'
    )

_ta_count   = sum(v["count"] for v in off_template_info.values()) if off_template_info else 0
_clr_issues = len(warn1) + len(warn2) + len(warn3)

# ── Section 1: Results (expanded) ─────────────────────────────────────────
_stat_rows = [
    _kv_row('Off-template tags found', str(_ta_count)),
    _kv_row('Tier 1 &#8212; Critical (under {})'.format(_ftin(MIN_CLR_T1)), str(len(warn1)), True),
    _kv_row('Tier 2 &#8212; Warning  (under {})'.format(_ftin(MIN_CLR_T2)), str(len(warn2))),
    _kv_row('Tier 3 &#8212; Caution  (under {})'.format(_ftin(MIN_CLR_T3)), str(len(warn3)), True),
]
_inject_results('results', 'Results', _tbl([], _stat_rows),
                collapsed=False)

# ── Section 2: Tag Audit ──────────────────────────────────────────────────
_inject_results('tagaudit', _ta_title, _ta_html, collapsed=True)

# ── Section 3: Clearance Audit ────────────────────────────────────────────
_inject_results(
    'clearance',
    'Clearance Audit',
    _ca_html,
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
