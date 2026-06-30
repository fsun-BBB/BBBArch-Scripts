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
import datetime
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
    Dimension, DimensionType, InternalDefinition, BuiltInParameter,
    FilledRegion, TextNoteType,
)
from pyrevit import script, forms

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
# (stage detection function defined below with GP_ROOT / CLN_ROOT)

AUDITED_ROOT = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\1_AUDITED"
GP_ROOT      = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\2_GUARDIAN PASS"
CLN_ROOT     = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance\3_CLEANED"
DATABASE_ID  = "387d917d-ca75-818e-b124-e7b8f7a8d530"   # Revit Families Scores
RUNS_DB_ID   = "387d917d-ca75-80a8-a323-de09adfce8ab"   # Revit Families Scoring Log

def _get_stage(path):
    norm = os.path.normpath(path).lower()
    if norm.startswith(os.path.normpath(GP_ROOT).lower()):
        return "2_Guardian Pass"
    if norm.startswith(os.path.normpath(CLN_ROOT).lower()):
        return "3_Cleaned"
    return "Others"

_PREFIX_CATEGORY = {
    "AIRT": "Air Terminals",
    "PLMB": "Plumbing Fixtures",
    "LGHT": "Lighting Fixtures",
    "ELEC": "Electrical",
    "SPKR": "Sprinkler",
    "FIRE": "Fire Protection",
    "LIFE": "Life Safety",
    "CASE": "Casework",
    "EQPT": "Equipment",
    "BATH": "Bathrooms",
    "CDEV": "Ceiling Devices",
    "DOOR": "Doors",
    "WIND": "Windows",
    "FURN": "Furniture",
    "SITE": "Site",
    "PRKG": "Parking",
    "SECU": "Security Devices",
    "ANNO": "Annotations",
    "KITC": "Kitchens",
    "MLWK": "Kitchens and Millwork",
    "WALL": "Wall Finishes",
    "AMTY": "Amenity Families",
    "UNIT": "Unit Families",
    "ACCB": "Accessories - Bathroom",
}

def _infer_category(name):
    """Infer Notion category from family name prefix e.g. B_AIRT_... → Air Terminals."""
    parts = name.upper().split("_")
    for part in parts:
        if part in _PREFIX_CATEGORY:
            return _PREFIX_CATEGORY[part]
    return ""

_CONFORMANCE_ROOT = os.path.dirname(GP_ROOT)   # N:\...\Content Conformance
_token_candidates = [
    os.path.join(ROOT,              "notion_token.txt"),
    os.path.join(os.path.dirname(ROOT), "notion_token.txt"),   # one level up
    os.path.join(_CONFORMANCE_ROOT, "notion_token.txt"),
    os.path.join(GP_ROOT,           "notion_token.txt"),
    os.path.join(CLN_ROOT,          "notion_token.txt"),
    os.path.join(AUDITED_ROOT,      "notion_token.txt"),
]
TOKEN_FILE = next((p for p in _token_candidates if os.path.exists(p)), None)

RUN_STAGE = _get_stage(ROOT)
_STAGE_COLOR = {"2_Guardian Pass": "#58A6FF", "3_Cleaned": "#3FB950", "Others": "#888888"}

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

def compute_normalize(nbytes, n_faces, n_solids, n_edges,
                      n_cad, n_images, n_nested, n_groups,
                      n_anon_rp, n_formula_params,
                      n_unused_type, n_unused_inst,
                      n_params, n_shared):
    size_mb = nbytes / 1000000.0
    return round(
        max(0, 10 - size_mb) +
        max(0, 10 - n_faces // 10) +
        max(0, 10 - n_solids) +
        max(0, 10 - n_edges // 10) +
        max(0, 10 - 10 * n_cad) +
        max(0, 10 - 10 * n_images) +
        max(0, 10 - n_nested) +
        max(0, 10 - 5 * n_groups) +
        max(0, 10 - n_anon_rp) +
        max(0, 10 - 2 * n_formula_params) +
        max(0, 10 - 2 * n_unused_type) +
        max(0, 10 - 2 * n_unused_inst) +
        max(0, 10 - n_params // 2) +
        max(0, 10 - 2 * n_shared),
        1)

def compute_final_score(nbytes, n_faces, n_solids, n_edges,
                        n_cad, n_images, n_nested, n_groups,
                        n_anon_rp, n_formula_params,
                        n_unused_type, n_unused_inst,
                        n_params, n_shared):
    size_mb = nbytes / 1000000.0
    fc = max(0, 10 - n_faces // 10)
    sc = max(0, 10 - n_solids)
    ec = max(0, 10 - n_edges // 10)
    blended_geo = (fc + sc + ec) / 3.0
    return round(
        1.25 * max(0, 10 - size_mb) +        # File Size      1.25x
        1.25 * blended_geo +                  # Blended Geo    1.25x
        1.25 * max(0, 10 - 10 * n_cad) +     # Imported CAD   1.25x
        1.25 * max(0, 10 - n_nested) +        # Nested Fams    1.25x
        0.5  * max(0, 10 - 10 * n_images) +   # Raster Images  0.5x
        0.75 * max(0, 10 - 5 * n_groups) +    # Model Groups   0.75x
        0.5  * max(0, 10 - n_anon_rp) +       # Ref Planes     0.5x
        0.75 * max(0, 10 - 2 * n_unused_type)+# Unused Type    0.75x
        0.75 * max(0, 10 - 2 * n_unused_inst)+# Unused Inst    0.75x
        0.5  * max(0, 10 - n_params // 2) +   # Total Params   0.5x
        0.5  * max(0, 10 - 2 * n_shared) +    # Shared Params  0.5x
        0.75 * max(0, 10 - 2 * n_formula_params), # Formula P  0.75x
        1)

def fmt_bytes(n):
    if n>=1000000: return "{:.1f} MB".format(n/1000000.0)
    if n>=1024:    return "{:.0f} KB".format(n/1024.0)
    return "{} B".format(n)

def _score_color(s):
    if s is None: return "#888","#F6F8FA"
    if s >= 90: return "#16803A","#EAFFF0"
    if s >= 80: return "#16803A","#D4F5DC"
    if s >= 70: return "#B45309","#FEF3C7"
    if s >= 60: return "#C2410C","#FFF3E0"
    return "#B91C1C","#FFF0F0"

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
    try:
        resp = req.GetResponse()
    except Exception as _we:
        _err_body = ""
        try:
            _err_resp = getattr(_we, 'Response', None)
            if _err_resp is not None:
                _err_body = StreamReader(_err_resp.GetResponseStream()).ReadToEnd()
                _err_resp.Close()
        except Exception:
            pass
        if _err_body:
            raise Exception("Notion API error: {}".format(_err_body[:400]))
        raise
    text = StreamReader(resp.GetResponseStream()).ReadToEnd()
    resp.Close()
    return json.loads(text) if text.strip() else {}

def _load_page_map_by_name(token):
    """Returns {proposed_name.lower(): (page_id, category)} — location-independent matching."""
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
                if not rt: continue
                cat = ""
                try: cat = page["properties"]["Category"]["select"]["name"]
                except Exception: pass
                lookup[rt[0]["plain_text"].lower()] = (page["id"], cat)
            except Exception: pass
        if resp.get("has_more"): cursor = resp["next_cursor"]
        else: break
    return lookup

def _update_family_scores(page_id, token, r):
    # Main scores — always runs, same as before my off-template addition
    _notion_call(
        "https://api.notion.com/v1/pages/{}".format(page_id), token, "PATCH",
        {"properties": {
            "Final Score":        {"number": r.get("fs", 0)},
            "Geom Score":         {"number": r.get("g_score", 0)},
            "File Size":          {"rich_text": [{"type": "text", "text": {"content": "{:.2f} MB".format(r.get("bytes", 0) / 1000000.0)}}]},
            "Face Count":         {"number": r.get("n_faces", 0)},
            "Solid Count":        {"number": r.get("n_solids", 0)},
            "Edge Count":         {"number": r.get("n_edges", 0)},
            "Imported CAD":       {"number": r.get("n_cad", 0)},
            "Raster Images":      {"number": r.get("n_images", 0)},
            "Nested Families":    {"number": r.get("n_nested", 0)},
            "Model Groups":       {"number": r.get("n_groups", 0)},
            "Unnamed Ref Planes": {"number": r.get("n_anon_rp", 0)},
            "Unused Type Params": {"number": r.get("n_unused_type", 0)},
            "Unused Inst Params": {"number": r.get("n_unused_inst", 0)},
            "Shared Params":      {"number": r.get("n_shared", 0)},
            "Total Params":       {"number": r.get("n_params", 0)},
            "Formula Params":     {"number": r.get("n_formula_params", 0)},
        }})
    # Off-template columns — separate call, failure is silent so main scores still count
    try:
        _notion_call(
            "https://api.notion.com/v1/pages/{}".format(page_id), token, "PATCH",
            {"properties": {
                "Line Styles":    {"number": r.get("n_line_styles", 0)},
                "Dimension Styles": {"number": r.get("n_dims", 0)},
                "Filled Regions": {"number": r.get("n_filled", 0)},
                "Text Styles":    {"number": r.get("n_text_styles", 0)},
            }})
    except Exception as _ot_exc:
        return "OT_ERR:{}".format(str(_ot_exc)[:300])

def _add_log_row(family_page_id, family_name, category, token, r, run_time, stage):
    """Append a new log entry to the log database — always creates, never updates."""
    title = "{} - {}".format(run_time, family_name)
    _notion_call(
        "https://api.notion.com/v1/pages", token, "POST",
        {"parent": {"database_id": RUNS_DB_ID},
         "properties": {
             "Time Stamp":        {"title": [{"text": {"content": title}}]},
             "relation":          {"relation": [{"id": family_page_id}]},
             "Stage":             {"select": {"name": stage}},
             "Category":          {"select": {"name": category}} if category else {"select": None},
             "Proposed Name":     {"rich_text": [{"type": "text", "text": {"content": family_name}}]},
             "Final Score":       {"number": r.get("fs", 0)},
             "File Size":         {"rich_text": [{"type": "text", "text": {"content": "{:.2f} MB".format(r.get("bytes", 0) / 1000000.0)}}]},
             "Geom Score":        {"number": r.get("g_score", 0)},
             "Face Count":        {"number": r.get("n_faces", 0)},
             "Solid Count":       {"number": r.get("n_solids", 0)},
             "Edge Count":        {"number": r.get("n_edges", 0)},
             "Imported CAD":      {"number": r.get("n_cad", 0)},
             "Raster Images":     {"number": r.get("n_images", 0)},
             "Nested Families":   {"number": r.get("n_nested", 0)},
             "Model Groups":      {"number": r.get("n_groups", 0)},
             "Unnamed Ref Planes":{"number": r.get("n_anon_rp", 0)},
             "Unused Type Params":{"number": r.get("n_unused_type", 0)},
             "Unused Inst Params":{"number": r.get("n_unused_inst", 0)},
             "Total Params":      {"number": r.get("n_params", 0)},
             "Shared Params":     {"number": r.get("n_shared", 0)},
             "Formula Params":    {"number": r.get("n_formula_params", 0)},
             "Line Styles":       {"number": r.get("n_line_styles", 0)},
             "Dimensions":        {"number": r.get("n_dims", 0)},
             "Filled Regions":    {"number": r.get("n_filled", 0)},
             "Text Styles":       {"number": r.get("n_text_styles", 0)},
         }})

# ── SCORES DB: find-or-create per family+stage ───────────────────────────────

def _score_props(r):
    return {
        "Final Score":        {"number": r.get("fs", 0)},
        "Geom Score":         {"number": r.get("g_score", 0)},
        "File Size":          {"rich_text": [{"type": "text", "text": {"content": "{:.2f} MB".format(r.get("bytes", 0) / 1000000.0)}}]},
        "Face Count":         {"number": r.get("n_faces", 0)},
        "Solid Count":        {"number": r.get("n_solids", 0)},
        "Edge Count":         {"number": r.get("n_edges", 0)},
        "Imported CAD":       {"number": r.get("n_cad", 0)},
        "Raster Images":      {"number": r.get("n_images", 0)},
        "Nested Families":    {"number": r.get("n_nested", 0)},
        "Model Groups":       {"number": r.get("n_groups", 0)},
        "Unnamed Ref Planes": {"number": r.get("n_anon_rp", 0)},
        "Unused Type Params": {"number": r.get("n_unused_type", 0)},
        "Unused Inst Params": {"number": r.get("n_unused_inst", 0)},
        "Shared Params":      {"number": r.get("n_shared", 0)},
        "Total Params":       {"number": r.get("n_params", 0)},
        "Formula Params":     {"number": r.get("n_formula_params", 0)},
        "Line Styles":        {"number": r.get("n_line_styles", 0)},
        "Dimensions":         {"number": r.get("n_dims", 0)},
        "Filled Regions":     {"number": r.get("n_filled", 0)},
        "Text Styles":        {"number": r.get("n_text_styles", 0)},
    }

def _upsert_score_page(name, stage, category, token, r):
    """Find existing row for this family+stage, update it; or create if missing."""
    q = _notion_call(
        "https://api.notion.com/v1/databases/{}/query".format(DATABASE_ID),
        token, "POST",
        {"filter": {"and": [
            {"property": "Family Name", "title":  {"equals": name}},
            {"property": "Stage",       "select": {"equals": stage}},
        ]}, "page_size": 1})
    pages = q.get("results", [])
    props = _score_props(r)
    if pages:
        _notion_call("https://api.notion.com/v1/pages/{}".format(pages[0]["id"]),
                     token, "PATCH", {"properties": props})
    else:
        props["Proposed Name"] = {"title": [{"text": {"content": name}}]}
        props["Stage"]       = {"select": {"name": stage}}
        if category:
            props["Category"] = {"select": {"name": category}}
        _notion_call("https://api.notion.com/v1/pages", token, "POST",
                     {"parent": {"database_id": DATABASE_ID}, "properties": props})

# ── HTML HELPERS ──────────────────────────────────────────────────────────────

def _score_td(score):
    if score is None:
        return '<td style="padding:5px 10px;text-align:right;color:#444">—</td>'
    fg, bg = _score_color(score)
    return ('<td style="padding:5px 10px;text-align:right;background:{};'
            'color:{};font-weight:600">{}</td>').format(bg,fg,score)

def _num_td(val):
    return '<td style="padding:5px 10px;text-align:right;color:#555;font-family:Consolas,monospace">{}</td>'.format(val)

def _flag_td(val):
    if val == 0:
        return '<td style="padding:5px 10px;text-align:right;color:#bbb;font-family:Consolas,monospace">0</td>'
    return '<td style="padding:5px 10px;text-align:right;color:#C2410C;font-weight:700;font-family:Consolas,monospace">{}</td>'.format(val)

# ── SCAN ──────────────────────────────────────────────────────────────────────

output.print_html("""
<div style="border-bottom:2px solid #2a2a2a;padding-bottom:10px;margin-bottom:12px">
  <span style="font-size:18px;font-weight:700;color:#e0e0e0">Family Efficiency Benchmark</span>
  <span style="font-size:11px;color:#444;margin-left:12px">v6</span>
  <span style="margin-left:14px;background:{sc};color:#000;border-radius:3px;padding:2px 10px;font-size:11px;font-weight:700">{st}</span>
</div>
<p style="font-size:11px;color:#555;font-family:monospace;margin:4px 0">{root}</p>
""".format(sc=_STAGE_COLOR.get(RUN_STAGE,"#888"), st=RUN_STAGE, root=ROOT))

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

_cancelled = False
_pb = forms.ProgressBar(
    title="Family Benchmark  —  0 / {}".format(len(rfa_files)),
    cancellable=True,
    total=len(rfa_files),
)
_pb.update_progress(0, len(rfa_files))

for idx, fpath in enumerate(rfa_files, 1):
    if _pb.cancelled:
        _cancelled = True
        output.print_html(
            '<div style="margin:10px 0;padding:10px 14px;background:#1a1000;'
            'border-left:3px solid #f2994a;border-radius:4px;'
            'color:#f2994a;font-size:12px;font-weight:700">'
            '&#9940; Cancelled after {}/{} families — results below are partial.'
            '</div>'.format(idx - 1, len(rfa_files)))
        break

    _pb.update_progress(idx, len(rfa_files))

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
        rows.append({"name":name,"rel":rel,"fpath":fpath,"bytes":nbytes,"v1":None,"ws":None,"fs":None,"err":str(exc)})
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

        fm = fdoc.FamilyManager; all_fparams = list(fm.Parameters)
        n_shared = sum(1 for p in all_fparams if p.IsShared)

        # ── Build usage sets (same 5-criteria logic as ParamAudit) ──────────
        formula_outputs = set()
        formula_inputs  = set()
        for p in all_fparams:
            try: f = p.Formula or ""
            except Exception: f = ""
            if f.strip():
                formula_outputs.add(p.Id.IntegerValue)
                for other in all_fparams:
                    if other.Definition.Name in f:
                        formula_inputs.add(other.Id.IntegerValue)

        dim_associated = set()
        _all_dims = list(FilteredElementCollector(fdoc).OfClass(Dimension).ToElements())
        n_dims = len(list(FilteredElementCollector(fdoc).OfClass(DimensionType).ToElements()))
        for dim in _all_dims:
            try:
                if dim.FamilyLabel is not None:
                    dim_associated.add(dim.FamilyLabel.Id.IntegerValue)
            except Exception: pass

        label_params = set()
        try:
            from Autodesk.Revit.DB import FamilyLabel as _FL
            for fl in FilteredElementCollector(fdoc).OfClass(_FL).ToElements():
                for seg in fl.GetSegments():
                    if seg.IsParam:
                        label_params.add(seg.FamilyParameter.Id.IntegerValue)
        except Exception: pass

        element_params = set()
        for elem in FilteredElementCollector(fdoc).WhereElementIsNotElementType().ToElements():
            try:
                for ep in elem.Parameters:
                    try:
                        assoc = fm.GetAssociatedFamilyParameter(ep)
                        if assoc is not None:
                            element_params.add(assoc.Id.IntegerValue)
                    except Exception: pass
            except Exception: pass

        # ── Classify orphans ─────────────────────────────────────────────────
        n_formula_params = len(formula_outputs)
        unused_type = []; unused_inst = []

        for p in all_fparams:
            pid = p.Id.IntegerValue
            # skip built-ins (cannot be deleted)
            try:
                defn = p.Definition
                if isinstance(defn, InternalDefinition) and defn.BuiltInParameter != BuiltInParameter.INVALID:
                    continue
            except Exception: pass
            # skip required BBB params
            if p.Definition.Name in required_set: continue
            # skip if used by any of the 5 criteria
            if (pid in formula_outputs or pid in formula_inputs or
                    pid in dim_associated or pid in label_params or
                    pid in element_params):
                continue
            # truly unused — classify
            if p.IsInstance:
                unused_inst.append(p.Definition.Name)
            else:
                unused_type.append(p.Definition.Name)

        n_nested = len(list(FilteredElementCollector(fdoc).OfClass(Family).ToElements()))
        n_groups = len(list(FilteredElementCollector(fdoc).OfClass(Group).ToElements()))

        # ── Off-template informational (no score impact) ──────────────────────
        try:
            from Autodesk.Revit.DB import GraphicsStyle, GraphicsStyleType
            n_line_styles = sum(
                1 for gs in FilteredElementCollector(fdoc).OfClass(GraphicsStyle).ToElements()
                if (gs.GraphicsStyleType == GraphicsStyleType.Projection
                    and gs.GraphicsStyleCategory is not None
                    and gs.GraphicsStyleCategory.Parent is not None
                    and gs.GraphicsStyleCategory.Parent.BuiltInCategory == BuiltInCategory.OST_Lines
                    and not gs.Name.startswith('<'))
            )
        except Exception: n_line_styles = 0
        n_filled      = len(list(FilteredElementCollector(fdoc).OfClass(FilledRegion).ToElements()))
        n_text_styles = len(list(FilteredElementCollector(fdoc).OfClass(TextNoteType).ToElements()))

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
            "ws":compute_normalize(
                nbytes,n_faces,n_solids,n_edges,
                n_cad,n_images,n_nested,n_groups,
                n_anon,n_formula_params,
                len(unused_type),len(unused_inst),
                len(all_fparams),n_shared),
            "fs":compute_final_score(
                nbytes,n_faces,n_solids,n_edges,
                n_cad,n_images,n_nested,n_groups,
                n_anon,n_formula_params,
                len(unused_type),len(unused_inst),
                len(all_fparams),n_shared),
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
            "n_line_styles":n_line_styles,"n_dims":n_dims,
            "n_filled":n_filled,"n_text_styles":n_text_styles,
            "err":"",
        })

    except Exception as exc:
        rows.append({"name":name,"rel":rel,"fpath":fpath,"bytes":nbytes,"v1":None,"ws":None,"fs":None,"err":str(exc)})
    finally:
        if opened_here:
            try: fdoc.Close(False)
            except Exception: pass

# ── SUMMARY CARD ──────────────────────────────────────────────────────────────

elapsed = time.time() - start_time
scored  = sorted([r for r in rows if r.get("fs") is not None], key=lambda x: x["fs"])
errors  = [r for r in rows if r.get("fs") is None]

if scored:
    avg_ws = sum(r["fs"] for r in scored) / float(len(scored))
    grade_dist = {}
    for r in scored:
        s = r["fs"]
        g = "A" if s>=90 else "B" if s>=80 else "C" if s>=70 else "D" if s>=60 else "F"
        grade_dist[g] = grade_dist.get(g,0)+1

    gc = {"A":"#6fcf97","B":"#27ae60","C":"#f2c94c","D":"#f2994a","F":"#eb5757"}
    pills = "".join(
        '<span style="background:{};color:#111;border-radius:3px;padding:2px 8px;'
        'font-size:11px;font-weight:700;margin-right:6px">{}: {}</span>'.format(
            gc.get(g,"#888"),g,n)
        for g,n in sorted(grade_dist.items()))

    avg_fg, _ = _score_color(int(avg_ws))

    output.print_html("""
<div style="background:#FFFFFF;border:1px solid #D0D7DE;border-radius:8px;padding:16px 22px;margin:14px 0 10px 0">
  <table style="width:100%;border-collapse:collapse">
    <tr>
      <td style="padding:0 24px 0 0;border-right:1px solid #E8EBEF;white-space:nowrap">
        <div style="color:#888;font-size:9px;text-transform:uppercase;letter-spacing:1px;font-weight:600">Families</div>
        <div style="color:#000;font-size:28px;font-weight:700;line-height:1.2;font-family:Consolas,monospace">{total}</div>
      </td>
      <td style="padding:0 24px;border-right:1px solid #E8EBEF;white-space:nowrap">
        <div style="color:#888;font-size:9px;text-transform:uppercase;letter-spacing:1px;font-weight:600">Avg Final Score</div>
        <div style="color:{avg_fg};font-size:28px;font-weight:700;line-height:1.2;font-family:Consolas,monospace">{avg:.1f}</div>
      </td>
      <td style="padding:0 24px;border-right:1px solid #E8EBEF;white-space:nowrap">
        <div style="color:#888;font-size:9px;text-transform:uppercase;letter-spacing:1px;font-weight:600">Time</div>
        <div style="color:#000;font-size:28px;font-weight:700;line-height:1.2;font-family:Consolas,monospace">{t}</div>
      </td>
      <td style="padding:0 0 0 24px">
        <div style="color:#888;font-size:9px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:8px">Grade Distribution</div>
        {pills}
      </td>
    </tr>
  </table>
</div>
""".format(
        total=len(scored), avg=avg_ws, avg_fg=avg_fg,
        t="{:.0f}m {:.0f}s".format(elapsed//60,elapsed%60) if elapsed>=60 else "{:.0f}s".format(elapsed),
        pills=pills))

    # Results table
    _th = 'style="padding:7px 10px;text-align:right;border-bottom:2px solid #D0D7DE;color:#555;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;white-space:nowrap;background:#F6F8FA"'
    _th_l = 'style="padding:7px 10px;text-align:left;border-bottom:2px solid #D0D7DE;color:#555;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;background:#F6F8FA"'
    output.print_html(
        '<table style="width:100%;border-collapse:collapse;font-size:12px">'
        '<thead><tr>'
        '<th {tl}>#</th>'
        '<th {tl}>Family</th>'
        '<th {t}>File Size</th>'
        '<th {t}>Final</th>'
        '<th {t}>Norm</th>'
        '<th {t}>Geom</th>'
        '<th {t}>Faces</th>'
        '<th {t}>CAD</th>'
        '<th {t}>Img</th>'
        '<th {t}>Nested</th>'
        '<th {t}>Groups</th>'
        '<th {t}>Ref Planes</th>'
        '<th {t}>Unused T</th>'
        '<th {t}>Unused I</th>'
        '<th {t}>Params</th>'
        '<th {t}>Shared</th>'
        '<th {t}>Formulas</th>'
        '<th {t} style="border-left:2px solid #D0D7DE;padding:7px 10px;text-align:right;background:#F6F8FA;color:#555;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;font-weight:600">Line Styles</th>'
        '<th {t}>Dim Styles</th>'
        '<th {t}>Filled Rgn</th>'
        '<th {t}>Text Styles</th>'
        '</tr></thead><tbody>'.format(t=_th, tl=_th_l))

    for i, r in enumerate(scored, 1):
        bg = "#F6F8FA" if i%2==0 else "#FFFFFF"
        output.print_html(
            '<tr style="background:{bg};border-bottom:1px solid #E8EBEF">'
            '<td style="padding:5px 10px;color:#aaa;font-size:10px;font-family:Consolas,monospace">{i}</td>'
            '<td style="padding:5px 10px;color:#000;font-weight:500;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{n}</td>'
            '{sz}{fs}{ws}{gm}{fc}{cd}{img}{ns}{grp}{rp}{ut}{ui}{pm}{sh}{fm}{ls}{dm}{fl}{ts}</tr>'.format(
                bg=bg,i=i,n=r["name"],
                sz=_num_td(r["size_fmt"]),
                fs=_score_td(r["fs"]),
                ws=_num_td(r["ws"]),
                gm=_score_td(r["g_score"]),
                fc=_num_td(r["n_faces"]),
                cd=_flag_td(r["n_cad"]),
                img=_flag_td(r["n_images"]),
                ns=_flag_td(r["n_nested"]),
                grp=_flag_td(r["n_groups"]),
                rp=_flag_td(r["n_anon_rp"]),
                ut=_flag_td(r["n_unused_type"]),
                ui=_flag_td(r["n_unused_inst"]),
                pm=_num_td(r["n_params"]),
                sh=_flag_td(r["n_shared"]),
                fm=_num_td(r["n_formula_params"]),
                ls=_flag_td(r.get("n_line_styles",0)),
                dm=_flag_td(r.get("n_dims",0)),
                fl=_flag_td(r.get("n_filled",0)),
                ts=_flag_td(r.get("n_text_styles",0)),
            )
        )

    output.print_html("</tbody></table>")

    flagged = [r for r in scored if r["fs"] < 70]
    if flagged:
        output.print_html(
            '<div style="margin-top:14px;background:#FFFCF5;border:1px solid #FDD9A0;'
            'border-left:4px solid #F0883E;border-radius:6px;padding:14px 16px">'
            '<div style="color:#B45309;font-size:12px;font-weight:700;margin-bottom:10px">'
            'Below 70 — {} families need attention</div>'.format(len(flagged)))
        for r in flagged:
            issues = []
            if r["n_cad"]:           issues.append("CAD imports ({})".format(r["n_cad"]))
            if r["n_images"]:        issues.append("raster images ({})".format(r["n_images"]))
            if r["n_nested"]:        issues.append("nested ({})".format(r["n_nested"]))
            if r["n_groups"]:        issues.append("groups ({})".format(r["n_groups"]))
            if r["n_anon_rp"]:       issues.append("unnamed planes ({})".format(r["n_anon_rp"]))
            if r["n_unused_type"]:   issues.append("unused type params ({})".format(r["n_unused_type"]))
            if r["n_unused_inst"]:   issues.append("unused inst params ({})".format(r["n_unused_inst"]))
            if r["n_shared"]:        issues.append("shared params ({})".format(r["n_shared"]))
            fg, bg = _score_color(r["fs"])
            output.print_html(
                '<div style="font-size:11px;margin:4px 0;display:flex;align-items:baseline">'
                '<span style="background:{bg};color:{fg};font-weight:700;border-radius:3px;'
                'padding:1px 7px;margin-right:8px;font-family:Consolas,monospace;font-size:11px">{sc}</span>'
                '<span style="color:#000;font-weight:600;margin-right:6px">{nm}</span>'
                '<span style="color:#888;font-size:10px">{issues}</span></div>'.format(
                    bg=bg, fg=fg, sc=r["fs"], nm=r["name"],
                    issues=" · ".join(issues) if issues else "review manually"))
        output.print_html("</div>")

if errors:
    output.print_html(
        '<div style="margin-top:12px;background:#FFF0F0;border:1px solid #FFB0AE;'
        'border-left:4px solid #F85149;border-radius:6px;padding:12px 16px">'
        '<div style="color:#B91C1C;font-size:11px;font-weight:700;margin-bottom:6px">'
        'Could not open — {} files</div>'.format(len(errors)))
    for r in errors:
        output.print_html('<div style="color:#555;font-size:10px;font-family:Consolas,monospace">{}</div>'.format(r["rel"]))
    output.print_html("</div>")

# ── NOTION WRITEBACK ──────────────────────────────────────────────────────────
# 1. Log rows  — always written, tagged with stage
# 2. Scores DB — only written when user confirms; blocked for "Others" stage

if not TOKEN_FILE:
    output.print_html(
        '<p style="color:#555;font-size:11px;margin-top:10px">'
        'Notion skipped — notion_token.txt not found in ROOT or AUDITED_ROOT.</p>')
elif scored:
    try:
        with open(TOKEN_FILE, "r") as _f:
            token = _f.read().strip().lstrip(u'﻿')

        run_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        # ── 1. LOG ROWS (always, with stage) ─────────────────────────────────
        output.print_html(
            '<div style="margin-top:14px;padding:12px 16px;background:#0d160d;'
            'border:1px solid #1a3a1a;border-radius:6px">'
            '<div style="color:#aaa;font-size:11px;font-weight:700;margin-bottom:6px">'
            '&#128196; Writing log rows (stage: {})...</div>'.format(RUN_STAGE))

        # Build name→(page_id, category) map — match by Proposed Name first (BBB code
        # name like "B_PLMB_Shower Stall"), then fall back to Family Name title.
        _page_map = {}
        _cursor = None
        while True:
            _body = {"page_size": 100}
            if _cursor: _body["start_cursor"] = _cursor
            _resp = _notion_call(
                "https://api.notion.com/v1/databases/{}/query".format(DATABASE_ID),
                token, "POST", _body)
            for _pg in _resp.get("results", []):
                try:
                    _cat = ""
                    try: _cat = _pg["properties"]["Category"]["select"]["name"]
                    except Exception: pass
                    _pid = _pg["id"]
                    # Match by Proposed Name (title field)
                    try:
                        _fn = _pg["properties"]["Proposed Name"]["title"]
                        if _fn:
                            _k = _fn[0]["plain_text"].lower()
                            if _k and _k not in _page_map:
                                _page_map[_k] = (_pid, _cat)
                    except Exception: pass
                except Exception: pass
            if _resp.get("has_more"): _cursor = _resp["next_cursor"]
            else: break

        n_log = 0; n_log_fail = 0
        for r in scored:
            pid, category = _page_map.get(r["name"].lower(), (None, ""))
            if not category:
                category = _infer_category(r["name"])
            if pid is None:
                # Family not yet in scores DB — create a stub so log can link to it
                try:
                    _stub = _score_props(r)
                    _stub["Proposed Name"] = {"title": [{"text": {"content": r["name"]}}]}
                    _stub["Stage"] = {"select": {"name": RUN_STAGE}}
                    if category:
                        _stub["Category"] = {"select": {"name": category}}
                    _new = _notion_call("https://api.notion.com/v1/pages", token, "POST",
                                       {"parent": {"database_id": DATABASE_ID}, "properties": _stub})
                    pid = _new.get("id")
                    _page_map[r["name"].lower()] = (pid, category)
                except Exception: pass
            if pid:
                try:
                    _add_log_row(pid, r["name"], category, token, r, run_time, RUN_STAGE)
                    n_log += 1
                except Exception as _le:
                    n_log_fail += 1
                    if n_log_fail <= 3:
                        output.print_html(
                            '<div style="color:#f2994a;font-size:10px">Log row failed ({}): {}</div>'.format(
                                r["name"], str(_le)[:200]))

        output.print_html(
            '<div style="color:#6fcf97;font-size:12px">&#10003; {} log rows written{}</div>'.format(
                n_log, " ({} failed)".format(n_log_fail) if n_log_fail else ""))
        output.print_html("</div>")

        # ── 2. SCORES DB (user must confirm; blocked for Others) ──────────────
        if RUN_STAGE == "Others":
            forms.alert(
                "Stage detected: Others\n\n"
                "This folder is not under 2_GUARDIAN PASS or 3_CLEANED.\n"
                "Scores have been logged but will NOT be saved to Revit Families Scores.",
                title="Save Scores — Not a Valid Stage")
        else:
            save_confirmed = forms.alert(
                "Save scores to Revit Families Scores?\n\n"
                "Stage: {}\n"
                "Families: {}\n"
                "Folder: {}\n\n"
                "This will override all scores for these families at this stage.".format(
                    RUN_STAGE, len(scored), ROOT),
                title="Save Scores to Notion",
                options=["Save Scores", "Skip"])

            if save_confirmed == "Save Scores":
                output.print_html(
                    '<div style="margin-top:10px;padding:12px 16px;background:#0d160d;'
                    'border:1px solid #1a3a1a;border-radius:6px">'
                    '<div style="color:#aaa;font-size:11px;font-weight:700;margin-bottom:6px">'
                    '&#128190; Saving scores (stage: {})...</div>'.format(RUN_STAGE))

                n_saved = 0; n_save_fail = 0
                for r in scored:
                    _, cat = _page_map.get(r["name"].lower(), (None, ""))
                    if not cat: cat = _infer_category(r["name"])
                    try:
                        _upsert_score_page(r["name"], RUN_STAGE, cat, token, r)
                        n_saved += 1
                    except Exception as _se:
                        n_save_fail += 1
                        if n_save_fail <= 3:
                            output.print_html(
                                '<div style="color:#eb5757;font-size:10px">'
                                'Save failed ({}): {}</div>'.format(r["name"], str(_se)[:300]))

                output.print_html(
                    '<div style="color:#6fcf97;font-size:12px">&#10003; {}/{} scores saved to {}{}</div>'.format(
                        n_saved, len(scored), RUN_STAGE,
                        " ({} errors)".format(n_save_fail) if n_save_fail else ""))
                output.print_html("</div>")

    except Exception as exc:
        output.print_html(
            '<div style="color:#eb5757;font-size:11px">Notion error: {}</div>'.format(exc))

# ── CSV ───────────────────────────────────────────────────────────────────────

_csv_date  = datetime.datetime.now().strftime("%Y%m%d_%H%M")
_csv_name  = "_benchmark_{}_{}.csv".format(RUN_STAGE.replace(" ", "_"), _csv_date)
csv_path   = os.path.join(ROOT, _csv_name)
_CSV_MAP = [
    ("_stage",           "Stage"),
    ("name",             "Family Name"),
    ("rel",              "Relative Path"),
    ("size_fmt",         "File Size"),
    ("ws",               "Normalize"),
    ("fs",               "Final Score"),
    ("n_faces",          "Face Count"),
    ("n_solids",         "Solid Count"),
    ("n_edges",          "Edge Count"),
    ("n_cad",            "Imported CAD"),
    ("n_images",         "Raster Images"),
    ("n_nested",         "Nested Families"),
    ("n_groups",         "Model Groups"),
    ("n_anon_rp",        "Unnamed Ref Planes"),
    ("n_unused_type",    "Unused Type Params"),
    ("unused_type",      "Unused Type Params (Names)"),
    ("n_unused_inst",    "Unused Inst Params"),
    ("unused_inst",      "Unused Inst Params (Names)"),
    ("n_shared",         "Shared Params"),
    ("n_params",         "Total Params"),
    ("n_formula_params", "Formula Params"),
    ("n_line_styles",    "Line Styles"),
    ("n_dims",           "Dimension Styles"),
    ("n_filled",         "Filled Regions"),
    ("n_text_styles",    "Text Styles"),
    ("err",              "Error"),
]
_csv_fields = [col for _, col in _CSV_MAP]
def _remap_csv(r):
    row = {col: r.get(key, "") for key, col in _CSV_MAP}
    row["Stage"] = RUN_STAGE
    return row

def _write_csv(path):
    with open(path, "wb") as f:
        w = csv.DictWriter(f, fieldnames=_csv_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(_remap_csv(r) for r in rows)

_wrote_csv = False
for _attempt in [csv_path] + [
        os.path.join(ROOT, "_benchmark_results_{}.csv".format(i)) for i in range(1, 6)]:
    try:
        _write_csv(_attempt)
        output.print_html(
            '<p style="color:#333;font-size:11px;font-family:monospace;margin-top:8px">'
            'CSV → {}</p>'.format(_attempt))
        _wrote_csv = True
        break
    except IOError:
        continue
if not _wrote_csv:
    output.print_html('<p style="color:#eb5757;font-size:11px">'
        'CSV failed — close _benchmark_results.csv in Excel and re-run.</p>')
