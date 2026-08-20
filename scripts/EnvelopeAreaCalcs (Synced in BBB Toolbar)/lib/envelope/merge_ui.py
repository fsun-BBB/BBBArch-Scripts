# -*- coding: utf-8 -*-
"""Merge Types table window.

Opened from the Config window's "Merge wall types..." button. Shows one row
per (Revit Category, Type Name) and lets the user multi-select rows to merge
into a named group, or unmerge them back out - replacing the old blind
list-picker menu with a table where the current grouping is visible at a
glance.
"""

import os

from pyrevit import forms

from envelope import core
from envelope.config_ui import _ensure_brand_styles_loaded, _common_prefix

XAML = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "merge_window.xaml")

# A fixed, visually distinct palette a group name hashes into - deterministic
# across window reopens and app restarts since it depends only on the name
# string, no persistence needed. Deliberately separate from
# core.assign_colors/core.COLOR_PALETTE, which recompute at draw time based
# on the current sorted label order and are not meant to be stable UI colors.
_SWATCH_COLORS = [
    "#0078D4", "#D13438", "#107C10", "#8764B8", "#CA5010",
    "#00B7C3", "#C239B3", "#986F0B", "#498205", "#0B6A0B",
    "#B4009E", "#5C2D91",
]


def _color_for(group_name):
    h = 0
    for ch in group_name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _SWATCH_COLORS[h % len(_SWATCH_COLORS)]


def _group_of(groups, type_name):
    """Which group (if any) a type name currently belongs to - groups are
    keyed purely by string, the same category-blind membership core.OPT
    ["groups"]/core.group_label already use."""
    for gname in sorted(groups):
        if type_name in groups[gname]:
            return gname
    return None


class _Row(object):
    """Plain attribute object - no INotifyPropertyChanged needed since the
    grid's ItemsSource is reassigned wholesale after every edit rather than
    mutated in place."""

    def __init__(self, category_label, type_name, group_name, color_hex):
        self.CategoryLabel = category_label
        self.TypeName = type_name
        self.GroupName = group_name
        self.ColorHex = color_hex
        self.HasGroup = bool(group_name)


def _build_rows(groups):
    """One row per (category, type name), not filtered by which categories
    are currently ticked in the outer config - matches the old merge flow,
    which drew its type pool from every category regardless."""
    rows = []
    for _key, label, bic in core.TYPE_CATEGORIES:
        for name in sorted(core.envelope_type_names_for(bic)):
            gname = _group_of(groups, name)
            rows.append(_Row(label, name, gname or "",
                              _color_for(gname) if gname else "Transparent"))
    return rows


def _do_merge(groups, selected_type_names, group_name):
    """Resolve/create the target group by exact name match, then steal each
    selected type out of any OTHER group it is currently in - deleting that
    old group if it drops below 2 members - before adding it to the target.
    A type already in the target group is a harmless no-op."""
    group_name = group_name.strip()
    target = groups.get(group_name)
    if target is None:
        target = set()
        groups[group_name] = target
    for type_name in selected_type_names:
        old = _group_of(groups, type_name)
        if old is not None and old != group_name:
            groups[old].discard(type_name)
            if len(groups[old]) < 2:
                del groups[old]
        target.add(type_name)


def _do_unmerge(groups, selected_type_names):
    """Remove each type from its group, deleting the group if it drops below
    2 members. No-ops on rows with no group, so callers do not need to
    pre-filter the selection."""
    for type_name in selected_type_names:
        gname = _group_of(groups, type_name)
        if gname is None:
            continue
        groups[gname].discard(type_name)
        if len(groups[gname]) < 2:
            del groups[gname]


class MergeWindow(forms.WPFWindow):
    """Stages edits to a working copy of `groups`; the caller only sees them
    if the user hits Save."""

    def __init__(self, groups):
        _ensure_brand_styles_loaded()
        forms.WPFWindow.__init__(self, XAML)
        self.confirmed = False
        self._groups = dict((k, set(v)) for k, v in groups.items())
        self._refresh()

    def _refresh(self):
        self.grid.ItemsSource = _build_rows(self._groups)
        self.grid.SelectedIndex = -1

    def merge(self, sender, args):
        rows = list(self.grid.SelectedItems)
        if len(rows) < 2:
            forms.alert("Select two or more rows to merge.", title="Merge")
            return
        names = [r.TypeName for r in rows]
        default = _common_prefix(names) or names[0]
        name = forms.ask_for_string(
            default=default.strip(" -_"),
            prompt="Name for this group of {} type(s):".format(len(names)),
            title="Merge Types",
        )
        if not name or not name.strip():
            return
        _do_merge(self._groups, names, name)
        self._refresh()

    def unmerge(self, sender, args):
        rows = list(self.grid.SelectedItems)
        if not rows:
            forms.alert("Select one or more merged rows to unmerge.",
                        title="Unmerge")
            return
        _do_unmerge(self._groups, [r.TypeName for r in rows])
        self._refresh()

    def confirm(self, sender, args):
        self.confirmed = True
        self.Close()

    def cancel(self, sender, args):
        self.Close()


def show(groups):
    """groups: working-copy dict from ConfigWindow._groups. Returns the
    (possibly edited) dict if the user confirmed, else the original dict
    unchanged."""
    win = MergeWindow(groups)
    win.ShowDialog()
    return win._groups if win.confirmed else groups
