# -*- coding: utf-8 -*-
__title__   = "Family\nBenchmark"
__doc__     = """Version = 6.0
Date    = 16.06.2026
________________________________________________________________
Description:
Click to choose any folder. Scans all .rfa files recursively,
scores each family, then writes a run table to the Notion Rating
System page and updates individual family score columns.

Run logic:
  - First run or new family set  → new numbered table appended
  - Same families as a prior run → popup asks replace or new run
  - Every run is numbered and dated for traceability
________________________________________________________________
Author: Frank Sun"""

import os
import csv
import time
import json
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System")
from System.Windows.Forms import FolderBrowserDialog, DialogResult
from System.Threading  import Thread, ThreadStart, ApartmentState
from System.Net        import WebRequest
from System.IO         import StreamReader
from System.Text       import Encoding

from Autodesk.Revit.DB import (
    FilteredElementCollector, ImportInstance, ReferencePlane,
    ViewDrafting, ModelText, Family, Group,
    ModelPathUtils, OpenOptions, BuiltInCategory,
    ViewDetailLevel, Solid, GeometryInstance, Options,
)
from pyrevit import script

# ── SETUP ─────────────────────────────────────────────────────────────────────

app    = __revit__.Application
output = script.get_output()
output.set_height(900)
output.set_title("Family Benchmark")

# ── FOLDER PICKER (STA thread) ────────────────────────────────────────────────

_picked = [None]
def _pick():
    d = FolderBrowserDialog()
    d.Description         = "Select root folder containing Revit families (.rfa)"
    d.ShowNewFolderButton = False
    if d.ShowDialog() == DialogResult.OK:
        _picked[0] = d.SelectedPath

_t = Thread(ThreadStart(_pick))
_t.SetApartmentState(ApartmentState.STA)
_t.Start(); _t.Join()

ROOT = _picked[0]
if not ROOT:
    output.print_md("Cancelled.")
    script.exit()

# ── CONSTANTS ─────────────────────────────────────────────────────────────────

AUDITED_ROOT = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\1_AUDITED"
DATABASE_ID  = "e561580b-eff2-4323-95b0-ef2db491dd6f"

_token_candidates = [
    os.path.join(ROOT, "notion_token.txt"),
    os.path.join(AUDITED_ROOT, "notion_token.txt"),
]
TOKEN_FILE = next((p for p in _token_candidates if os.path.exists(p)), None)

# ── REQUIRED PARAMETERS ───────────────────────────────────────────────────────

REQUIRED_PARAMS = [
    "Manufacturer", "Model", "OmniClass Number", "OmniClass Title",
    "Assembly Code", "Type Comments", "URL",
]

# ── SCORING CONFIGS ───────────────────────────────────────────────────────────

CONFIGS = [
    {"label": "v1", "size": 15, "up": 25, "ot": 25, "rp": 15, "nc": 20},
    {"label": "v2", "size": 10, "up": 30, "ot": 30, "rp": 15, "nc": 15},
    {"label": "v3", "size": 10, "up": 20, "ot": 25, "rp": 10, "nc": 35},
]

BASE_SIZE_MAX = 15;  BASE_UP_MAX = 25;  BASE_OT_MAX = 25
BASE_RP_MAX   = 15;  BASE_NC_MAX = 20

SIZE_RATIOS  = [(500000,1.00),(1000000,0.73),(2000000,0.47),(5000000,0.20),(float("inf"),0.00)]
OT_CAD_PEN   = 8;   OT_DRAFT_PEN = 4;  OT_IMAGE_PEN = 5;  OT_TEXT_PEN  = 3
UP_TYPE_PEN  = 2;   UP_INST_PEN  = 1
RP_PEN       = 2
NC_FAM_PEN   = 3;   NC_GROUP_PEN = 5
GEOM_THRESHOLDS = [(20,20),(50,16),(100,12),(200,7),(500,3),(float("inf"),0)]

# ── SCORING HELPERS ───────────────────────────────────────────────────────────

required_set = set(REQUIRED_PARAMS)

def raw_size_score(n):
    for lim, r in SIZE_RATIOS:
        if n < lim: return int(round(BASE_SIZE_MAX * r))
    return 0

def apply_config(raw, cfg):
    return int(round(
        raw["size"]/float(BASE_SIZE_MAX)*cfg["size"] +
        raw["up"]  /float(BASE_UP_MAX)  *cfg["up"]   +
        raw["ot"]  /float(BASE_OT_MAX)  *cfg["ot"]   +
        raw["rp"]  /float(BASE_RP_MAX)  *cfg["rp"]   +
        raw["nc"]  /float(BASE_NC_MAX)  *cfg["nc"]
    ))

def score_geom(n):
    for lim, pts in GEOM_THRESHOLDS:
        if n < lim: return pts
    return 0

def fmt_bytes(n):
    if n>=1000000: return "{:.1f} MB".format(n/1000000.0)
    if n>=1024:    return "{:.0f} KB".format(n/1024.0)
    return "{} B".format(n)

def _score_color(s):
    if s is None: return "#555","#111"
    if s >= 90: return "#6fcf97","#0d2015"
    if s >= 80: return "#27ae60","#0a1f0f"
    if s >= 70: return "#f2c94c","#2a2000"
    if s >= 60: return "#f2994a","#2a1500"
    return "#eb5757","#2a0a0a"

def _read_type_val(ft, p):
    try: return str(round(ft.AsDouble(p),6))
    except Exception: pass
    try: return ft.AsString(p) or ""
    except Exception: pass
    try: return str(ft.AsInteger(p))
    except Exception: return "__na__"

# ── REVIT HELPERS ─────────────────────────────────────────────────────────────

def _open_doc(fpath):
    try:
        return app.OpenDocumentFile(
            ModelPathUtils.ConvertUserVisiblePathToModelPath(fpath), OpenOptions())
    except Exception:
        return app.OpenDocumentFile(fpath)

def _already_open(fpath):
    for d in app.Documents:
        try:
            if d.PathName.lower() == fpath.lower(): return d
        except Exception: pass
    return None

def _collect_images(fdoc):
    try:
        from Autodesk.Revit.DB import ImageInstance
        return len(list(FilteredElementCollector(fdoc).OfClass(ImageInstance).ToElements()))
    except Exception: pass
    try:
        return len(list(FilteredElementCollector(fdoc)
            .OfCategory(BuiltInCategory.OST_RasterImages)
            .WhereElementIsNotElementType().ToElements()))
    except Exception: return 0

def _collect_geom(fdoc):
    opt = Options()
    opt.DetailLevel = ViewDetailLevel.Fine
    opt.ComputeReferences = False
    counts = [0, 0, 0]
    def _walk(obj):
        if isinstance(obj, Solid):
            try:
                if obj.Volume > 0:
                    counts[0]+=1; counts[1]+=obj.Faces.Size; counts[2]+=obj.Edges.Size
            except Exception: pass
        elif isinstance(obj, GeometryInstance):
            try:
                for inner in obj.GetInstanceGeometry(): _walk(inner)
            except Exception: pass
    for el in FilteredElementCollector(fdoc).WhereElementIsNotElementType().ToElements():
        try:
            geom = el.get_Geometry(opt)
            if geom:
                for obj in geom: _walk(obj)
        except Exception: pass
    return counts[0], counts[1], counts[2]

# ── NOTION API ────────────────────────────────────────────────────────────────

def _notion_call(url, token, method, body=None):
    req = WebRequest.Create(url)
    req.Method = method
    req.Headers.Add("Authorization", "Bearer " + token)
    req.Headers.Add("Notion-Version", "2022-06-28")
    if body is not None:
        b = Encoding.UTF8.GetBytes(json.dumps(body))
        req.ContentType   = "application/json"
        req.ContentLength = b.Length
        s = req.GetRequestStream(); s.Write(b,0,b.Length); s.Close()
    elif method in ("POST", "PATCH"):
        req.ContentType = "application/json"; req.ContentLength = 0
    resp = req.GetResponse()
    text = StreamReader(resp.GetResponseStream()).ReadToEnd()
    resp.Close()
    return json.loads(text) if text.strip() else {}

def _load_page_map_by_name(token):
    """Returns {proposed_name.lower(): page_id} — location-independent matching."""
    lookup = {}; cursor = None
    while True:
        body = {"page_size": 100}
        if cursor: body["start_cursor"] = cursor
        resp = _notion_call(
            "https://api.notion.com/v1/databases/{}/query".format(DATABASE_ID),
            token, "POST", body)
        for page in resp.get("results", []):
            try:
                rt = page["properties"]["Proposed Name"]["rich_text"]
                if rt: lookup[rt[0]["plain_text"].lower()] = page["id"]
            except Exception: pass
        if resp.get("has_more"): cursor = resp["next_cursor"]
        else: break
    return lookup

def _update_family_scores(page_id, token, r):
    _notion_call(
        "https://api.notion.com/v1/pages/{}".format(page_id), token, "PATCH",
        {"properties": {
            # Scores
            "Score v1":           {"number": r["v1"]},
            "Score v2":           {"number": r["v2"]},
            "Score v3":           {"number": r["v3"]},
            "Geom Score":         {"number": r.get("g_score", 0)},
            # Performance
            "Face Count":         {"number": r.get("n_faces", 0)},
            "Solid Count":        {"number": r.get("n_solids", 0)},
            "Edge Count":         {"number": r.get("n_edges", 0)},
            "Imported CAD":       {"number": r.get("n_cad", 0)},
            "Raster Images":      {"number": r.get("n_images", 0)},
            "Nested Families":    {"number": r.get("n_nested", 0)},
            "Model Groups":       {"number": r.get("n_groups", 0)},
            # Cleanliness
            "Unnamed Ref Planes": {"number": r.get("n_anon_rp", 0)},
            "Orphan Type Params": {"number": r.get("n_unused_type", 0)},
            "Orphan Inst Params": {"number": r.get("n_unused_inst", 0)},
            # Informational
            "Shared Params":      {"number": r.get("n_shared", 0)},
            "Total Params":       {"number": r.get("n_params", 0)},
            "Formula Params":     {"number": r.get("n_formula_params", 0)},
        }})

# ── HTML HELPERS ──────────────────────────────────────────────────────────────

def _score_td(score):
    if score is None:
        return '<td style="padding:5px 10px;text-align:right;color:#444">—</td>'
    fg, bg = _score_color(score)
    return ('<td style="padding:5px 10px;text-align:right;background:{};'
            'color:{};font-weight:600">{}</td>').format(bg,fg,score)

def _num_td(val):
    return '<td style="padding:5px 10px;text-align:right;color:#888">{}</td>'.format(val)

def _flag_td(val):
    if val == 0:
        return '<td style="padding:5px 10px;text-align:right;color:#2a2a2a">0</td>'
    return '<td style="padding:5px 10px;text-align:right;color:#e07b39;font-weight:600">{}</td>'.format(val)

# ── SCAN ──────────────────────────────────────────────────────────────────────

output.print_html("""
<div style="border-bottom:2px solid #2a2a2a;padding-bottom:10px;margin-bottom:12px">
  <span style="font-size:18px;font-weight:700;color:#e0e0e0">Family Efficiency Benchmark</span>
  <span style="font-size:11px;color:#444;margin-left:12px">v6</span>
</div>
<p style="font-size:11px;color:#555;font-family:monospace;margin:4px 0">{}</p>
""".format(ROOT))

rfa_files = []
for root_dir, _, files in os.walk(ROOT):
    for f in sorted(files):
        if f.lower().endswith(".rfa"):
            rfa_files.append(os.path.join(root_dir, f))

if not rfa_files:
    output.print_html('<p style="color:#e07b39">No .rfa files found.</p>')
    script.exit()

output.print_html('<p style="color:#aaa;font-size:13px"><b>{}</b> families found — analysing...</p>'.format(len(rfa_files)))

# ── ANALYSE ───────────────────────────────────────────────────────────────────

rows       = []
start_time = time.time()

for idx, fpath in enumerate(rfa_files, 1):
    rel  = os.path.relpath(fpath, ROOT)
    name = os.path.splitext(os.path.basename(fpath))[0]

    output.print_html(
        '<div style="font-size:10px;color:#2e2e2e;font-family:monospace;line-height:1.6">'
        '<span style="color:#444">({}/{})</span>&nbsp;&nbsp;{}</div>'.format(
            idx, len(rfa_files), rel))

    try: nbytes = os.path.getsize(fpath)
    except Exception: nbytes = 0

    already     = _already_open(fpath)
    opened_here = already is None
    try:
        fdoc = already if already else _open_doc(fpath)
    except Exception as exc:
        rows.append({"name":name,"rel":rel,"fpath":fpath,"bytes":nbytes,"v1":None,"err":str(exc)})
        continue

    try:
        if not fdoc.IsFamilyDocument:
            if opened_here: fdoc.Close(False)
            continue

        n_cad      = len(list(FilteredElementCollector(fdoc).OfClass(ImportInstance).ToElements()))
        n_drafting = len(list(FilteredElementCollector(fdoc).OfClass(ViewDrafting).ToElements()))
        n_images   = _collect_images(fdoc)
        n_mtext    = len(list(FilteredElementCollector(fdoc).OfClass(ModelText).ToElements()))

        all_rp = list(FilteredElementCollector(fdoc).OfClass(ReferencePlane).ToElements())
        n_anon = sum(1 for rp in all_rp if (rp.Name or "").strip().lower() in ("reference plane",""))

        fm = fdoc.FamilyManager; all_fparams = list(fm.Parameters); fm_types = list(fm.Types)
        n_shared = sum(1 for p in all_fparams if p.IsShared)

        unused_type = []; unused_inst = []; n_formula_params = 0
        for p in all_fparams:
            try: formula = p.Formula or ""
            except Exception: formula = ""
            if formula.strip():
                n_formula_params += 1
                continue  # formula-driven → not orphan
            if p.Definition.Name in required_set: continue
            if p.IsInstance and not p.IsShared:
                # Shared instance params (MEP connectors, system data) are legitimate —
                # only flag user-created instance params with no formula.
                unused_inst.append(p.Definition.Name)
            elif len(fm_types) >= 2:
                if len(set(_read_type_val(ft,p) for ft in fm_types)) == 1:
                    unused_type.append(p.Definition.Name)

        n_nested = len(list(FilteredElementCollector(fdoc).OfClass(Family).ToElements()))
        n_groups = len(list(FilteredElementCollector(fdoc).OfClass(Group).ToElements()))
        n_solids, n_faces, n_edges = _collect_geom(fdoc)
        g_score  = score_geom(n_faces)

        raw = {
            "size": raw_size_score(nbytes),
            "up":   max(0, BASE_UP_MAX-(len(unused_type)*UP_TYPE_PEN+len(unused_inst)*UP_INST_PEN)),
            "ot":   max(0, BASE_OT_MAX-((OT_CAD_PEN if n_cad>0 else 0)+n_drafting*OT_DRAFT_PEN+n_images*OT_IMAGE_PEN+n_mtext*OT_TEXT_PEN)),
            "rp":   max(0, BASE_RP_MAX-n_anon*RP_PEN),
            "nc":   max(0, BASE_NC_MAX-(n_nested*NC_FAM_PEN+n_groups*NC_GROUP_PEN)),
        }
        scores = {cfg["label"]: apply_config(raw,cfg) for cfg in CONFIGS}

        rows.append({
            "name":name,"rel":rel,"fpath":fpath,"bytes":nbytes,"size_fmt":fmt_bytes(nbytes),
            "v1":scores["v1"],"v2":scores["v2"],"v3":scores["v3"],"g_score":g_score,
            "raw_size":raw["size"],"raw_up":raw["up"],"raw_ot":raw["ot"],"raw_rp":raw["rp"],"raw_nc":raw["nc"],
            "n_cad":n_cad,"n_drafting":n_drafting,"n_images":n_images,"n_mtext":n_mtext,
            "n_anon_rp":n_anon,
            "n_unused_type":len(unused_type),"unused_type":", ".join(unused_type[:5]),
            "n_unused_inst":len(unused_inst),"unused_inst":", ".join(unused_inst[:5]),
            "n_nested":n_nested,"n_groups":n_groups,
            "n_solids":n_solids,"n_faces":n_faces,"n_edges":n_edges,
            "n_shared":n_shared,
            "n_params":len(all_fparams),
            "n_formula_params":n_formula_params,
            "err":"",
        })

    except Exception as exc:
        rows.append({"name":name,"rel":rel,"fpath":fpath,"bytes":nbytes,"v1":None,"err":str(exc)})
    finally:
        if opened_here:
            try: fdoc.Close(False)
            except Exception: pass

# ── SUMMARY CARD ──────────────────────────────────────────────────────────────

elapsed = time.time() - start_time
scored  = sorted([r for r in rows if r.get("v1") is not None], key=lambda x: x["v1"])
errors  = [r for r in rows if r.get("v1") is None]

if scored:
    avg_v1 = sum(r["v1"] for r in scored) / float(len(scored))
    grade_dist = {}
    for r in scored:
        s = r["v1"]
        g = "A" if s>=90 else "B" if s>=80 else "C" if s>=70 else "D" if s>=60 else "F"
        grade_dist[g] = grade_dist.get(g,0)+1

    gc = {"A":"#6fcf97","B":"#27ae60","C":"#f2c94c","D":"#f2994a","F":"#eb5757"}
    pills = "".join(
        '<span style="background:{};color:#111;border-radius:3px;padding:2px 8px;'
        'font-size:11px;font-weight:700;margin-right:6px">{}: {}</span>'.format(
            gc.get(g,"#888"),g,n)
        for g,n in sorted(grade_dist.items()))

    avg_fg, _ = _score_color(int(avg_v1))

    output.print_html("""
<div style="background:#161616;border:1px solid #2a2a2a;border-radius:8px;padding:16px 20px;margin:14px 0 8px 0">
  <table style="width:100%;border-collapse:collapse">
    <tr>
      <td style="padding:0 24px 0 0;border-right:1px solid #2a2a2a;white-space:nowrap">
        <div style="color:#555;font-size:10px;text-transform:uppercase;letter-spacing:1px">Families</div>
        <div style="color:#e0e0e0;font-size:26px;font-weight:700;line-height:1.2">{total}</div>
      </td>
      <td style="padding:0 24px;border-right:1px solid #2a2a2a;white-space:nowrap">
        <div style="color:#555;font-size:10px;text-transform:uppercase;letter-spacing:1px">Avg Score (v1)</div>
        <div style="color:{avg_fg};font-size:26px;font-weight:700;line-height:1.2">{avg:.1f}</div>
      </td>
      <td style="padding:0 24px;border-right:1px solid #2a2a2a;white-space:nowrap">
        <div style="color:#555;font-size:10px;text-transform:uppercase;letter-spacing:1px">Time</div>
        <div style="color:#e0e0e0;font-size:26px;font-weight:700;line-height:1.2">{t}</div>
      </td>
      <td style="padding:0 0 0 24px">
        <div style="color:#555;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">Grade Distribution (v1)</div>
        {pills}
      </td>
    </tr>
  </table>
</div>
<p style="color:#333;font-size:10px;margin:2px 0 10px 0">
  v1: Sz/15 UP/25 OT/25 RP/15 NC/20 &nbsp;|&nbsp;
  v2: Sz/10 UP/30 OT/30 RP/15 NC/15 &nbsp;|&nbsp;
  v3: Sz/10 UP/20 OT/25 RP/10 NC/35 &nbsp;|&nbsp;
  Geom /20 standalone
</p>
""".format(
        total=len(scored), avg=avg_v1, avg_fg=avg_fg,
        t="{:.0f}m {:.0f}s".format(elapsed//60,elapsed%60) if elapsed>=60 else "{:.0f}s".format(elapsed),
        pills=pills))

    # Results table
    output.print_html("""
<table style="width:100%;border-collapse:collapse;font-size:12px;font-family:monospace">
  <thead>
    <tr style="background:#1e1e1e;color:#555;font-size:10px;text-transform:uppercase;letter-spacing:0.5px">
      <th style="padding:6px 10px;text-align:left;border-bottom:1px solid #2a2a2a">#</th>
      <th style="padding:6px 10px;text-align:left;border-bottom:1px solid #2a2a2a">Family</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">Size</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">v1</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">v2</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">v3</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">Geom</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">Faces</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">CAD</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">Draft</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">AnonRP</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">UnusedT</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">UnusedI</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">Nested</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">Params</th>
      <th style="padding:6px 10px;text-align:right;border-bottom:1px solid #2a2a2a">Formulas</th>
    </tr>
  </thead><tbody>""")

    for i, r in enumerate(scored, 1):
        bg = "#0f0f0f" if i%2==0 else "#111"
        output.print_html(
            '<tr style="background:{bg};border-bottom:1px solid #1a1a1a">'
            '<td style="padding:5px 10px;color:#333;font-size:10px">{i}</td>'
            '<td style="padding:5px 10px;color:#d0d0d0;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{n}</td>'
            '{sz}{v1}{v2}{v3}{gm}{fc}{cd}{df}{rp}{ut}{ui}{ns}'.format(
                bg=bg,i=i,n=r["name"],
                sz=_num_td(r["size_fmt"]),
                v1=_score_td(r["v1"]),v2=_score_td(r["v2"]),v3=_score_td(r["v3"]),
                gm=_score_td(r["g_score"]),
                fc=_num_td(r["n_faces"]),
                cd=_flag_td(r["n_cad"]),df=_flag_td(r["n_drafting"]),
                rp=_flag_td(r["n_anon_rp"]),
                ut=_flag_td(r["n_unused_type"]),ui=_flag_td(r["n_unused_inst"]),
                ns=_flag_td(r["n_nested"]),
            ) + _num_td(r["n_params"]) + _num_td(r["n_formula_params"]) + "</tr>"
        )

    output.print_html("</tbody></table>")

    flagged = [r for r in scored if r["v1"] < 70]
    if flagged:
        output.print_html(
            '<div style="margin-top:16px;background:#1a0f00;border-left:3px solid #f2994a;'
            'border-radius:4px;padding:12px 16px">'
            '<div style="color:#f2994a;font-size:12px;font-weight:700;margin-bottom:8px">'
            'Below 70 — {} families</div>'.format(len(flagged)))
        for r in flagged:
            issues = []
            if r["n_cad"]:         issues.append("imported CAD ({})".format(r["n_cad"]))
            if r["n_drafting"]:    issues.append("drafting views ({})".format(r["n_drafting"]))
            if r["n_anon_rp"]:     issues.append("unnamed ref planes ({})".format(r["n_anon_rp"]))
            if r["n_unused_type"]: issues.append("orphan type params ({})".format(r["n_unused_type"]))
            if r["n_unused_inst"]: issues.append("orphan inst params ({})".format(r["n_unused_inst"]))
            if r["n_nested"]:      issues.append("nested families ({})".format(r["n_nested"]))
            output.print_html(
                '<div style="font-size:11px;margin:3px 0">'
                '<span style="color:#e07b39;font-weight:600">{}</span>'
                '<span style="color:#555"> {}/100</span>'
                '<span style="color:#444"> — {}</span></div>'.format(
                    r["name"], r["v1"], " · ".join(issues) if issues else "review manually"))
        output.print_html("</div>")

if errors:
    output.print_html(
        '<div style="margin-top:12px;background:#160a0a;border-left:3px solid #eb5757;'
        'border-radius:4px;padding:10px 14px">'
        '<div style="color:#eb5757;font-size:11px;font-weight:700">Could not open — {} files</div>'.format(len(errors)))
    for r in errors:
        output.print_html('<div style="color:#444;font-size:10px;font-family:monospace">{}</div>'.format(r["rel"]))
    output.print_html("</div>")

# ── NOTION WRITEBACK ──────────────────────────────────────────────────────────
# Matches each scanned family to its Notion page by Proposed Name,
# then updates Score v1 / v2 / v3 / Geom Score in place.

if not TOKEN_FILE:
    output.print_html(
        '<p style="color:#333;font-size:11px;margin-top:10px">'
        'Notion skipped — notion_token.txt not found.</p>')
elif scored:
    output.print_html(
        '<div style="margin-top:16px;padding:14px 16px;background:#0d160d;'
        'border:1px solid #1a3a1a;border-radius:6px">')
    try:
        with open(TOKEN_FILE, "r") as _f:
            token = _f.read().strip()

        output.print_html(
            '<div style="color:#aaa;font-size:11px;margin-bottom:6px">'
            'Loading Notion page map...</div>')
        page_map = _load_page_map_by_name(token)
        output.print_html(
            '<div style="color:#555;font-size:11px;margin-bottom:8px">'
            '{} entries in database</div>'.format(len(page_map)))

        n_written = 0
        unmatched = []
        for r in scored:
            pid = page_map.get(r["name"].lower())
            if not pid:
                unmatched.append(r["name"])
                continue
            try:
                _update_family_scores(pid, token, r)
                n_written += 1
            except Exception:
                pass

        output.print_html(
            '<div style="color:#6fcf97;font-size:13px;font-weight:700">'
            '&#10003; {}/{} families updated</div>'.format(n_written, len(scored)))

        if unmatched:
            output.print_html(
                '<div style="color:#f2994a;font-size:11px;margin-top:6px">'
                'Not matched in Notion ({}):</div>'.format(len(unmatched)))
            for nm in unmatched:
                output.print_html(
                    '<div style="color:#666;font-size:11px;font-family:monospace">'
                    '&nbsp;&nbsp;{}</div>'.format(nm))

    except Exception as exc:
        output.print_html(
            '<div style="color:#eb5757;font-size:11px">Notion error: {}</div>'.format(exc))

    output.print_html("</div>")

# ── CSV ───────────────────────────────────────────────────────────────────────

csv_path = os.path.join(ROOT, "_benchmark_results.csv")
fields = [
    # Identity
    "name", "rel", "bytes", "size_fmt",
    # Scores
    "v1", "v2", "v3",
    # Performance — geometry weight, render cost, load time
    "n_faces", "n_solids", "n_edges",
    "n_cad", "n_images",
    "n_nested", "n_groups",
    # Cleanliness — naming, param hygiene, template compliance
    "n_anon_rp",
    "n_unused_type", "unused_type",
    "n_unused_inst", "unused_inst",
    # Informational
    "n_shared", "n_params", "n_formula_params",
    "err",
]
try:
    with open(csv_path,"wb") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    output.print_html(
        '<p style="color:#333;font-size:11px;font-family:monospace;margin-top:8px">'
        'CSV → {}</p>'.format(csv_path))
except Exception as exc:
    output.print_html('<p style="color:#eb5757;font-size:11px">CSV failed: {}</p>'.format(exc))
