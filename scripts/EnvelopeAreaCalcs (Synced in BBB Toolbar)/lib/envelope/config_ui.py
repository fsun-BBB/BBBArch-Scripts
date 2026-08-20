# -*- coding: utf-8 -*-
"""The Envelope Areas configuration window.

A WPF window rather than a stack of prompts, because these are settings the user
returns to and compares, not a question to answer once. It is shared by the
Configurations button (Save) and by Select Elevations (Run), so there is one
place that decides what counts as envelope.
"""

import os
import re

from pyrevit import forms

from envelope import core

XAML = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "config_window.xaml")

# The style files this window's XAML pulls Fluent card/button DynamicResources
# from - same set, same toolbar-wide brand system, as lib/shared_ui/base_window.py.
_STYLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "shared_ui", "xaml", "styles")
_STYLE_FILES = ("Foundation.xaml", "Brushes.xaml", "Effects.xaml", "Typography.xaml",
                "Buttons.xaml", "Controls.xaml", "Cards.xaml", "Lists.xaml")

_styles_loaded = [False]


def _ensure_brand_styles_loaded():
    """Merge the toolbar's shared brand/Fluent style dictionaries into the WPF
    Application's resources once, so this window's {DynamicResource ...} button
    and card styles resolve. Reads files directly rather than using Source=
    file:// URIs, which break on paths containing spaces."""
    if _styles_loaded[0]:
        return
    _styles_loaded[0] = True

    from System.Windows import Application
    from System.Windows.Markup import XamlReader

    if Application.Current is None:
        Application()

    merged_re = re.compile(
        r'<ResourceDictionary\.MergedDictionaries>.*?</ResourceDictionary\.MergedDictionaries>\s*',
        re.DOTALL)
    inner_re = re.compile(r'<ResourceDictionary[^>]*>(.*)</ResourceDictionary>', re.DOTALL)

    chunks = []
    for fname in _STYLE_FILES:
        path = os.path.join(_STYLES_DIR, fname)
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r') as f:
                text = f.read()
            text = merged_re.sub('', text)
            m = inner_re.search(text)
            if m:
                chunks.append(m.group(1).strip())
        except Exception:
            pass

    if not chunks:
        return

    combined = (
        u'<ResourceDictionary'
        u' xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"'
        u' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"'
        u' xmlns:System="clr-namespace:System;assembly=mscorlib">'
        + u'\n'.join(chunks) +
        u'</ResourceDictionary>'
    )
    try:
        rd = XamlReader.Parse(combined)
        Application.Current.Resources.MergedDictionaries.Add(rd)
    except Exception:
        pass


# Reuses the Run Now button's icon rather than a separate asset, so the
# header visually ties back to the tool this window configures.
_HEADER_ICON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..",
    "BBB Tools.tab", "Energy.panel", "1.RunNow.pushbutton", "icon.png")


def _load_header_icon(window):
    path = os.path.abspath(_HEADER_ICON)
    if not os.path.exists(path):
        return
    try:
        from System import Uri, UriKind
        from System.Windows.Media.Imaging import BitmapImage
        bmp = BitmapImage()
        bmp.BeginInit()
        bmp.UriSource = Uri(path, UriKind.Absolute)
        bmp.DecodePixelWidth = 64
        bmp.EndInit()
        window.header_icon.Source = bmp
    except Exception:
        pass


def _common_prefix(names):
    """The text every one of these names starts with - the default group name."""
    if not names:
        return ""
    first = names[0]
    for i in range(len(first)):
        ch = first[i]
        if any(len(n) <= i or n[i] != ch for n in names):
            return first[:i]
    return first

# OPT key -> display label, the categories eligible for detail grouping (a
# different feature from the "groups" merge-by-name one above: this makes 2+
# IDENTICAL elements instances of one Revit Detail Group instead of separate
# regions - see core.OPT["detail_group_enabled"]).
_DETAIL_GROUP_KEYS = ("detail_group_enabled",)
_DETAIL_GROUP_CATEGORIES = [
    ("detail_group_windows", "Windows"),
    ("detail_group_doors", "Doors"),
    ("detail_group_panels", "Curtain wall panels"),
]
_DETAIL_GROUP_KEYS += tuple(k for k, _lbl in _DETAIL_GROUP_CATEGORIES)

# OPT key -> display label, in the order they are listed and picked from
_CATEGORIES = [
    ("walls", "Walls"),
    ("panels", "Curtain wall panels"),
    ("mullions", "Curtain wall mullions"),
    ("windows", "Windows"),
    ("doors", "Doors"),
    ("slab_edges", "Walls with slab edges"),
    ("columns", "Walls with columns"),
]


class ConfigWindow(forms.WPFWindow):
    """Reads OPT on open and writes it back on Save; nothing else touches it."""

    def __init__(self, primary_label="Save"):
        _ensure_brand_styles_loaded()
        forms.WPFWindow.__init__(self, XAML)
        self.confirmed = False
        self.btn_ok.Content = primary_label
        _load_header_icon(self)
        self._types = set(core.OPT["types"])
        self._groups = dict((k, set(v)) for k, v in core.OPT["groups"].items())
        self._categories = dict((k, bool(core.OPT[k])) for k, _lbl in _CATEGORIES)
        self._detail_group = dict(
            (k, bool(core.OPT[k])) for k in _DETAIL_GROUP_KEYS)

    # --- categories ---------------------------------------------------------

    def pick_categories(self, sender, args):
        opts = [
            forms.TemplateListItem(lbl, checked=self._categories.get(k, False))
            for k, lbl in _CATEGORIES
        ]
        picked = forms.SelectFromList.show(
            opts,
            title="Categories to include",
            multiselect=True, button_name="Use these types", width=620,
        )
        if picked is None:
            return
        picked = set(str(p) for p in picked)
        for k, lbl in _CATEGORIES:
            self._categories[k] = lbl in picked

    # --- types ------------------------------------------------------------

    def pick_types(self, sender, args):
        cats = [(key, label, bic) for key, label, bic in core.TYPE_CATEGORIES
                if self._categories.get(key)]
        if not cats:
            forms.alert("No categories are included yet - pick some under "
                        "Revit Categories to Include first.",
                        title="Choose Types")
            return
        labels = [label for _key, label, _bic in cats]
        while True:
            choice = forms.CommandSwitchWindow.show(
                labels + ["Back"],
                message="Choose a category to filter its types")
            if not choice or choice == "Back":
                return
            key, _label, bic = next(c for c in cats if c[1] == choice)
            self._pick_types_for_category(key, bic, choice)

    def _pick_types_for_category(self, key, bic, label):
        cat_names = core.envelope_type_names_for(bic)
        if not cat_names:
            forms.alert("No {} types found in this model.".format(label.lower()),
                        title="Choose Types")
            return
        # Opens with everything ticked, so the list starts from what the tool
        # would measure anyway and the job is to untick. If a subset is already
        # saved, that subset is what comes up ticked instead.
        opts = [
            forms.TemplateListItem(
                n, checked=(n in self._types) if self._types else True)
            for n in sorted(cat_names)
        ]
        picked = forms.SelectFromList.show(
            opts,
            title="{} - untick what to leave out".format(label),
            multiselect=True, button_name="Use these types", width=620,
        )
        if picked is None:
            return
        picked = set(picked)
        # self._types is one flat whitelist across every category, so editing
        # just this category's slice has to leave the other categories' current
        # selection untouched - "everything ticked" (an empty whitelist) reads
        # as every other category being fully selected too.
        all_names = core.envelope_type_names()
        other_selected = ((all_names - cat_names) if not self._types
                          else (self._types - cat_names))
        new_types = other_selected | picked
        # Everything ticked means no restriction at all, which is stored as an
        # empty set - otherwise a type added to the model later would be left
        # out by a whitelist that only looked complete on the day it was made.
        self._types = set() if new_types == all_names else new_types

    # --- merging wall types ----------------------------------------------

    def edit_groups(self, sender, args):
        from envelope import merge_ui
        self._groups = merge_ui.show(self._groups)

    # --- detail groups (identical elements) --------------------------------

    def edit_detail_groups(self, sender, args):
        opts = [
            forms.TemplateListItem(lbl, checked=self._detail_group.get(k, False))
            for k, lbl in _DETAIL_GROUP_CATEGORIES
        ]
        picked = forms.SelectFromList.show(
            opts,
            title="Create a detail group when type + shape match - categories",
            multiselect=True, button_name="Use these", width=620,
        )
        if picked is None:
            return
        picked = set(str(p) for p in picked)
        for k, lbl in _DETAIL_GROUP_CATEGORIES:
            self._detail_group[k] = lbl in picked
        # Enabled exactly when at least one category is ticked - a separate
        # on/off switch would be one more thing to forget to flip.
        self._detail_group["detail_group_enabled"] = bool(picked)

    # --- purge ------------------------------------------------------------

    def purge(self, sender, args):
        counts = core.purge_counts()
        labels = dict(core.PURGE_KINDS)
        kinds = [(k, lbl) for k, lbl in core.PURGE_KINDS if counts.get(k, 0) > 0]
        if not kinds:
            forms.alert("Nothing to purge.", title="Purge")
            return
        opts = [forms.TemplateListItem(
                    "{}  ({})".format(lbl, counts[k]), checked=False)
                for k, lbl in kinds]
        picked = forms.SelectFromList.show(
            opts,
            title="Select what to purge",
            multiselect=True, button_name="Purge selected", width=620,
        )
        if not picked:
            return
        picked = set(str(p) for p in picked)
        chosen = [k for k, lbl in kinds
                  if "{}  ({})".format(lbl, counts[k]) in picked]
        if not chosen:
            return
        if not forms.alert(
            "Remove this from the model?",
            title="Purge Envelope Output",
            sub_msg="\n".join("{}: {}".format(labels[k], counts.get(k, 0))
                              for k in chosen),
            expanded="Only what this tool made is matched: regions carrying its "
            "marker or an EN_ region type. Anything else, including filled "
            "regions you drew yourself, is left alone.",
            ok=False, yes=True, no=True, warn_icon=True,
        ):
            return
        done, blocked = core.purge(chosen)
        lines = ["{}: {}".format(labels[k], v) for k, v in done.items() if v]
        if blocked:
            lines.append("")
            lines.append("Revit would not release: " + ", ".join(
                "{} ({})".format(labels[k], v) for k, v in blocked.items()))
            lines.append("Region types stay while their regions are still "
                         "there - purge Filled regions as well.")
        forms.alert("\n".join(lines) or "Nothing was removed.", title="Purged")

    # --- buttons ----------------------------------------------------------

    def confirm(self, sender, args):
        for key, _lbl in _CATEGORIES:
            core.OPT[key] = bool(self._categories.get(key, False))
        core.OPT["types"] = set(self._types)
        core.OPT["groups"] = dict((k, set(v)) for k, v in self._groups.items())
        for key in _DETAIL_GROUP_KEYS:
            core.OPT[key] = bool(self._detail_group.get(key, False))
        self.confirmed = True
        self.Close()

    def cancel(self, sender, args):
        self.Close()


def show(primary_label="Save"):
    """Open the window. True if the user confirmed, False if they cancelled."""
    core.bind_host()
    core.load_options()
    win = ConfigWindow(primary_label)
    win.ShowDialog()
    if win.confirmed:
        core.save_options()
    return win.confirmed
