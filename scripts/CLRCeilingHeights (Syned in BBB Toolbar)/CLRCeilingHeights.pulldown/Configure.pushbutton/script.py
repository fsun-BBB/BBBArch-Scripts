# -*- coding: utf-8 -*-
__title__ = "Configure"
__doc__ = "Configure clearance thresholds and search settings for the Ceiling Tag tools."

import clr as _clr
_clr.AddReference('System.Windows.Forms')
_clr.AddReference('System.Drawing')
import System.Windows.Forms as _WF
import System.Drawing as _D

from clr_ceiling_config import load, save
from pyrevit import forms

cfg = load()

# ── helpers ───────────────────────────────────────────────────────────────────

def _dec_to_ftin(ft_val):
    """Decimal feet → (feet int, inches int)."""
    total_in = ft_val * 12.0
    f = int(total_in // 12)
    i = int(round(total_in - f * 12))
    return f, i

def _ftin_to_dec(feet, inches):
    """Feet + inches → decimal feet."""
    return feet + inches / 12.0

def _fmt(ft_val):
    f, i = _dec_to_ftin(ft_val)
    return "{:d}' - {:d}\"".format(f, i)

# ── build form ────────────────────────────────────────────────────────────────
frm = _WF.Form()
frm.Text = "Configure — Ceiling Tag Settings"
frm.Width = 380
frm.Height = 295
frm.FormBorderStyle = _WF.FormBorderStyle.FixedDialog
frm.MaximizeBox = False
frm.MinimizeBox = False
frm.StartPosition = _WF.FormStartPosition.CenterScreen
frm.Font = _D.Font("Segoe UI", 9)
frm.BackColor = _D.Color.White

def _lbl(text, x, y, bold=False):
    l = _WF.Label()
    l.Text = text
    l.Location = _D.Point(x, y)
    l.AutoSize = True
    if bold:
        l.Font = _D.Font("Segoe UI", 9, _D.FontStyle.Bold)
    frm.Controls.Add(l)

def _txt_small(val, x, y):
    t = _WF.TextBox()
    t.Text = str(val)
    t.Location = _D.Point(x, y - 2)
    t.Width = 34
    t.TextAlign = _WF.HorizontalAlignment.Center
    frm.Controls.Add(t)
    return t

def _sep(y):
    s = _WF.Label()
    s.Height = 1
    s.Width = 336
    s.Location = _D.Point(14, y)
    s.BorderStyle = _WF.BorderStyle.Fixed3D
    frm.Controls.Add(s)

# Section 1: Floor search
_lbl("Floor Search", 14, 12, bold=True)
_lbl("Search depth below ceiling  (ft):", 14, 36)
t_depth_ft = _WF.TextBox()
t_depth_ft.Text = str(int(cfg['search_depth']))
t_depth_ft.Location = _D.Point(254, 34)
t_depth_ft.Width = 50
frm.Controls.Add(t_depth_ft)
_lbl("ft", 308, 36)

_sep(62)

# Section 2: Clearance thresholds
_lbl("Clearance Thresholds", 14, 74, bold=True)
_lbl("Rule: Tier 1 < Tier 2 < Tier 3", 14, 92)

_t1f, _t1i = _dec_to_ftin(cfg['tier1'])
_t2f, _t2i = _dec_to_ftin(cfg['tier2'])
_t3f, _t3i = _dec_to_ftin(cfg['tier3'])

_lbl("Tier 1 — Critical  clearance under", 14, 118)
t_tier1_ft = _txt_small(_t1f, 244, 118)
_lbl("'  -", 281, 118)
t_tier1_in = _txt_small(_t1i, 298, 118)
_lbl('"', 336, 118)

_lbl("Tier 2 — Warning   clearance under", 14, 144)
t_tier2_ft = _txt_small(_t2f, 244, 144)
_lbl("'  -", 281, 144)
t_tier2_in = _txt_small(_t2i, 298, 144)
_lbl('"', 336, 144)

_lbl("Tier 3 — Caution   clearance under", 14, 170)
t_tier3_ft = _txt_small(_t3f, 244, 170)
_lbl("'  -", 281, 170)
t_tier3_in = _txt_small(_t3i, 298, 170)
_lbl('"', 336, 170)

_sep(202)

# Buttons
btn_save = _WF.Button()
btn_save.Text = "Save"
btn_save.Location = _D.Point(184, 214)
btn_save.Width = 72
btn_save.DialogResult = _WF.DialogResult.OK
frm.Controls.Add(btn_save)
frm.AcceptButton = btn_save

btn_cancel = _WF.Button()
btn_cancel.Text = "Cancel"
btn_cancel.Location = _D.Point(266, 214)
btn_cancel.Width = 72
btn_cancel.DialogResult = _WF.DialogResult.Cancel
frm.Controls.Add(btn_cancel)
frm.CancelButton = btn_cancel

# ── show and handle ───────────────────────────────────────────────────────────
if frm.ShowDialog() == _WF.DialogResult.OK:
    try:
        v1 = _ftin_to_dec(int(t_tier1_ft.Text), int(t_tier1_in.Text))
        v2 = _ftin_to_dec(int(t_tier2_ft.Text), int(t_tier2_in.Text))
        v3 = _ftin_to_dec(int(t_tier3_ft.Text), int(t_tier3_in.Text))
        sd = float(t_depth_ft.Text)

        if not (v1 < v2 < v3):
            forms.alert(
                "Invalid thresholds.\n\nTier 1 must be less than Tier 2, "
                "which must be less than Tier 3.",
                title="Configure — Invalid Input",
                warn_icon=True
            )
        else:
            new_cfg = {'search_depth': sd, 'tier1': v1, 'tier2': v2, 'tier3': v3}
            save(new_cfg)
            forms.alert(
                "Settings saved successfully.\n\n"
                "  Search depth:            {sd} ft\n"
                "  Tier 1 (Critical): under {t1}\n"
                "  Tier 2 (Warning):  under {t2}\n"
                "  Tier 3 (Caution):  under {t3}".format(
                    sd=sd, t1=_fmt(v1), t2=_fmt(v2), t3=_fmt(v3)
                ),
                title="Configure — Saved"
            )
    except ValueError:
        forms.alert(
            "Please enter whole numbers for feet and inches.",
            title="Configure — Invalid Input",
            warn_icon=True
        )
