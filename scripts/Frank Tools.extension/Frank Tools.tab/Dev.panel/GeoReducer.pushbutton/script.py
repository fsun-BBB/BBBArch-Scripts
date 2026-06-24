# -*- coding: utf-8 -*-
__title__   = "Geo\nReducer"
__doc__     = """Version = 1.0
Date    = 23.06.2026
________________________________________________________________
Description:
Scans all solid-producing forms in the open family, shows their
face / solid / edge counts, and lets you delete selected ones to
improve the Blended Geo Score.
________________________________________________________________
Author: Frank Sun"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    Extrusion, Blend, Revolution, Sweep, SweptBlend, FreeFormElement,
    ViewDetailLevel, Solid, GeometryInstance, Options,
    Transaction,
)
from System.Windows.Markup import XamlReader

doc = __revit__.ActiveUIDocument.Document

# ── GEOMETRY HELPERS ─────────────────────────────────────────────────────────
def _geom_for_elem(elem):
    opt = Options()
    opt.DetailLevel = ViewDetailLevel.Fine
    opt.ComputeReferences = False
    counts = [0, 0, 0]  # solids, faces, edges
    def _walk(obj):
        if isinstance(obj, Solid):
            try:
                if obj.Volume > 0:
                    counts[0] += 1
                    counts[1] += obj.Faces.Size
                    counts[2] += obj.Edges.Size
            except: pass
        elif isinstance(obj, GeometryInstance):
            try:
                for inner in obj.GetInstanceGeometry(): _walk(inner)
            except: pass
    try:
        geom = elem.get_Geometry(opt)
        if geom:
            for obj in geom: _walk(obj)
    except: pass
    return counts[0], counts[1], counts[2]

def _total_geom(doc):
    opt = Options()
    opt.DetailLevel = ViewDetailLevel.Fine
    opt.ComputeReferences = False
    counts = [0, 0, 0]  # solids, faces, edges
    def _walk(obj):
        if isinstance(obj, Solid):
            try:
                if obj.Volume > 0:
                    counts[0] += 1
                    counts[1] += obj.Faces.Size
                    counts[2] += obj.Edges.Size
            except: pass
        elif isinstance(obj, GeometryInstance):
            try:
                for inner in obj.GetInstanceGeometry(): _walk(inner)
            except: pass
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            g = el.get_Geometry(opt)
            if g:
                for obj in g: _walk(obj)
        except: pass
    return counts[0], counts[1], counts[2]

# ── SCORING ──────────────────────────────────────────────────────────────────
def _blended_geo_score(n_faces, n_solids, n_edges):
    fc = max(0, 10 - n_faces  // 10)
    sc = max(0, 10 - n_solids)
    ec = max(0, 10 - n_edges  // 10)
    return round((fc + sc + ec) / 3.0 * 1.25, 2)

# ── XAML ─────────────────────────────────────────────────────────────────────
XAML = """
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Geo Reducer"
    Width="880" Height="600"
    WindowStartupLocation="CenterScreen"
    Background="#1A1A1A"
    FontFamily="Segoe UI" FontSize="12">

  <Window.Resources>
    <Style TargetType="Button">
      <Setter Property="Background"      Value="#2D2D2D"/>
      <Setter Property="Foreground"      Value="#E0E0E0"/>
      <Setter Property="BorderBrush"     Value="#444"/>
      <Setter Property="BorderThickness" Value="1"/>
      <Setter Property="Padding"         Value="12,5"/>
      <Setter Property="Cursor"          Value="Hand"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#3A3A3A"/>
        </Trigger>
      </Style.Triggers>
    </Style>
    <Style TargetType="DataGrid">
      <Setter Property="Background"               Value="#1E1E1E"/>
      <Setter Property="Foreground"               Value="#E0E0E0"/>
      <Setter Property="BorderBrush"              Value="#444"/>
      <Setter Property="BorderThickness"          Value="1"/>
      <Setter Property="RowBackground"            Value="#1E1E1E"/>
      <Setter Property="AlternatingRowBackground" Value="#252525"/>
      <Setter Property="HorizontalGridLinesBrush" Value="#2A2A2A"/>
      <Setter Property="VerticalGridLinesBrush"   Value="#2A2A2A"/>
      <Setter Property="ColumnHeaderHeight"       Value="28"/>
    </Style>
    <Style TargetType="DataGridColumnHeader">
      <Setter Property="Background"       Value="#2A2A2A"/>
      <Setter Property="Foreground"       Value="#AAB4BE"/>
      <Setter Property="FontWeight"       Value="SemiBold"/>
      <Setter Property="Padding"          Value="8,0"/>
      <Setter Property="BorderBrush"      Value="#444"/>
      <Setter Property="BorderThickness"  Value="0,0,1,1"/>
    </Style>
    <Style TargetType="DataGridCell">
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Padding"         Value="6,2"/>
    </Style>
    <Style TargetType="DataGridRow">
      <Setter Property="Foreground" Value="#E0E0E0"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#303030"/>
        </Trigger>
      </Style.Triggers>
    </Style>
  </Window.Resources>

  <Grid Margin="16">
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <!-- Header -->
    <StackPanel Grid.Row="0" Margin="0,0,0,10">
      <TextBlock Text="Geo Reducer" FontSize="20" FontWeight="Bold" Foreground="#E0E0E0"/>
      <TextBlock x:Name="SubTitle" FontSize="11" Foreground="#888" Margin="0,3,0,0"/>
    </StackPanel>

    <!-- Score banner -->
    <Border Grid.Row="1" Background="#1E1E2A" BorderBrush="#2E2E5A"
            BorderThickness="1" CornerRadius="4" Padding="14,10" Margin="0,0,0,12">
      <Grid>
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="*"/>
          <ColumnDefinition Width="*"/>
          <ColumnDefinition Width="*"/>
          <ColumnDefinition Width="*"/>
          <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>
        <StackPanel Grid.Column="0" HorizontalAlignment="Center">
          <TextBlock Text="Faces"   Foreground="#888" FontSize="10" TextAlignment="Center"/>
          <TextBlock x:Name="LblFaces"   Foreground="#7DBBE8" FontSize="22" FontWeight="Bold" TextAlignment="Center"/>
        </StackPanel>
        <StackPanel Grid.Column="1" HorizontalAlignment="Center">
          <TextBlock Text="Solids"  Foreground="#888" FontSize="10" TextAlignment="Center"/>
          <TextBlock x:Name="LblSolids"  Foreground="#7DBBE8" FontSize="22" FontWeight="Bold" TextAlignment="Center"/>
        </StackPanel>
        <StackPanel Grid.Column="2" HorizontalAlignment="Center">
          <TextBlock Text="Edges"   Foreground="#888" FontSize="10" TextAlignment="Center"/>
          <TextBlock x:Name="LblEdges"   Foreground="#7DBBE8" FontSize="22" FontWeight="Bold" TextAlignment="Center"/>
        </StackPanel>
        <StackPanel Grid.Column="3" HorizontalAlignment="Center">
          <TextBlock Text="Geo Score Now"  Foreground="#888" FontSize="10" TextAlignment="Center"/>
          <TextBlock x:Name="LblScoreNow"  Foreground="#F2994A" FontSize="22" FontWeight="Bold" TextAlignment="Center"/>
        </StackPanel>
        <StackPanel Grid.Column="4" HorizontalAlignment="Center">
          <TextBlock Text="Score if Deleted"  Foreground="#888" FontSize="10" TextAlignment="Center"/>
          <TextBlock x:Name="LblScoreAfter"   Foreground="#6FCF97" FontSize="22" FontWeight="Bold" TextAlignment="Center"/>
        </StackPanel>
      </Grid>
    </Border>

    <!-- Grid -->
    <DataGrid x:Name="Grid" Grid.Row="2"
              AutoGenerateColumns="False"
              CanUserAddRows="False" CanUserDeleteRows="False"
              CanUserResizeRows="False" IsReadOnly="False"
              Margin="0,0,0,10">
      <DataGrid.Columns>
        <DataGridTemplateColumn Header="" Width="32" CanUserResize="False">
          <DataGridTemplateColumn.CellTemplate>
            <DataTemplate>
              <CheckBox IsChecked="{Binding Selected, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}"
                        HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </DataTemplate>
          </DataGridTemplateColumn.CellTemplate>
        </DataGridTemplateColumn>
        <DataGridTextColumn Header="Element Type"  Binding="{Binding EType}"   Width="160" IsReadOnly="True"/>
        <DataGridTextColumn Header="Name / Id"     Binding="{Binding EName}"   Width="160" IsReadOnly="True"/>
        <DataGridTextColumn Header="Solids"        Binding="{Binding Solids}"  Width="70"  IsReadOnly="True"/>
        <DataGridTextColumn Header="Faces"         Binding="{Binding Faces}"   Width="70"  IsReadOnly="True"/>
        <DataGridTextColumn Header="Edges"         Binding="{Binding Edges}"   Width="70"  IsReadOnly="True"/>
        <DataGridTextColumn Header="% of Total"    Binding="{Binding Pct}"     Width="80"  IsReadOnly="True"/>
        <DataGridTextColumn Header="Geo Score Impact" Binding="{Binding Impact}" Width="*" IsReadOnly="True"/>
      </DataGrid.Columns>
    </DataGrid>

    <!-- Footer -->
    <Grid Grid.Row="3">
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="*"/>
        <ColumnDefinition Width="Auto"/>
      </Grid.ColumnDefinitions>
      <StackPanel Grid.Column="0" Orientation="Horizontal" VerticalAlignment="Center">
        <Button x:Name="BtnSelectAll"  Content="Select All"   Margin="0,0,8,0"/>
        <Button x:Name="BtnSelectNone" Content="Clear"        Margin="0,0,16,0"/>
        <Button x:Name="BtnDelete"
                Content="Delete Selected Forms"
                Background="#3A1010" Foreground="#E07B7B" BorderBrush="#6A2020"
                Margin="0,0,12,0"/>
        <TextBlock x:Name="Status" Foreground="#6FCF97" FontSize="11"
                   VerticalAlignment="Center"/>
      </StackPanel>
      <Button x:Name="BtnClose" Grid.Column="1" Content="Close"/>
    </Grid>
  </Grid>
</Window>
"""

# ── ROW ──────────────────────────────────────────────────────────────────────
class GeoRow(object):
    def __init__(self, etype, ename, solids, faces, edges, pct, impact, elem_id):
        self.EType    = etype
        self.EName    = ename
        self.Solids   = solids
        self.Faces    = faces
        self.Edges    = edges
        self.Pct      = pct
        self.Impact   = impact
        self.ElemId   = elem_id
        self.Selected = False

# ── FORM TYPE NAME ───────────────────────────────────────────────────────────
_FORM_TYPES = (Extrusion, Blend, Revolution, Sweep, SweptBlend, FreeFormElement)

def _type_name(elem):
    if isinstance(elem, Extrusion):   return "Extrusion"
    if isinstance(elem, Blend):       return "Blend"
    if isinstance(elem, Revolution):  return "Revolution"
    if isinstance(elem, Sweep):       return "Sweep"
    if isinstance(elem, SweptBlend):  return "Swept Blend"
    if isinstance(elem, FreeFormElement): return "Free Form"
    return elem.GetType().Name

# ── MAIN ─────────────────────────────────────────────────────────────────────
if not doc.IsFamilyDocument:
    from pyrevit import forms
    forms.alert("Open a family (.rfa) first.", title="Geo Reducer")
else:
    # Collect total geometry first
    tot_solids, tot_faces, tot_edges = _total_geom(doc)
    geo_score_now = _blended_geo_score(tot_faces, tot_solids, tot_edges)

    # Collect per-element geometry — scan ALL non-type elements
    form_rows = []
    seen_ids = set()
    for elem in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            eid = elem.Id.IntegerValue
            if eid in seen_ids: continue
            seen_ids.add(eid)
            s, f, e = _geom_for_elem(elem)
            if f == 0 and s == 0: continue
            pct = "{:.0f}%".format(100.0 * f / tot_faces) if tot_faces > 0 else "0%"
            rs   = _blended_geo_score(tot_faces - f, tot_solids - s, tot_edges - e)
            gain = rs - geo_score_now
            impact = "+{:.2f} pts if removed".format(gain) if gain > 0 else "no gain"
            try:
                cat = elem.Category.Name if elem.Category else ""
            except: cat = ""
            try:
                name = elem.Name or ""
            except: name = ""
            display_name = name if name else "Id {}".format(eid)
            etype = _type_name(elem) if any(isinstance(elem, ft) for ft in _FORM_TYPES) else (cat or elem.GetType().Name.split(".")[-1])
            form_rows.append(GeoRow(etype, display_name, s, f, e, pct, impact, eid))
        except: pass

    form_rows.sort(key=lambda r: r.Faces, reverse=True)

    if not form_rows:
        from pyrevit import forms
        forms.alert("No solid-producing forms found.", title="Geo Reducer")
    else:
        window = XamlReader.Parse(XAML)
        window.FindName("SubTitle").Text = (
            "Family: {}   |   {} geometry-producing forms   |   Total: {} faces  {} solids  {} edges".format(
                doc.Title, len(form_rows), tot_faces, tot_solids, tot_edges))

        window.FindName("LblFaces").Text   = str(tot_faces)
        window.FindName("LblSolids").Text  = str(tot_solids)
        window.FindName("LblEdges").Text   = str(tot_edges)
        window.FindName("LblScoreNow").Text  = str(geo_score_now)
        window.FindName("LblScoreAfter").Text = "-"

        from System.Collections.ObjectModel import ObservableCollection
        items = ObservableCollection[object]()
        for r in form_rows:
            items.Add(r)

        grid = window.FindName("Grid")
        grid.ItemsSource = items

        def _update_preview(sender=None, e=None):
            sel = [r for r in items if r.Selected]
            if not sel:
                window.FindName("LblScoreAfter").Text = "-"
                return
            rem_f = sum(r.Faces  for r in sel)
            rem_s = sum(r.Solids for r in sel)
            rem_e = sum(r.Edges  for r in sel)
            score_after = _blended_geo_score(
                max(0, tot_faces - rem_f),
                max(0, tot_solids - rem_s),
                max(0, tot_edges - rem_e))
            window.FindName("LblScoreAfter").Text = str(score_after)

        grid.CellEditEnding += lambda s, e: _update_preview()

        def select_all(sender, e):
            for r in items: r.Selected = True
            grid.Items.Refresh(); _update_preview()

        def select_none(sender, e):
            for r in items: r.Selected = False
            grid.Items.Refresh(); _update_preview()
            window.FindName("LblScoreAfter").Text = "-"

        def delete_selected(sender, e):
            sel = [r for r in items if r.Selected]
            if not sel:
                window.FindName("Status").Text = "Nothing selected."
                return
            deleted = 0; blocked = 0
            for row in sel:
                try:
                    with Transaction(doc, "Delete Geo Form") as t:
                        t.Start()
                        from Autodesk.Revit.DB import ElementId
                        doc.Delete(ElementId(row.ElemId))
                        t.Commit()
                    deleted += 1
                except Exception as ex:
                    blocked += 1

            # refresh totals
            new_s, new_f, new_e = _total_geom(doc)
            new_score = _blended_geo_score(new_f, new_s, new_e)
            window.FindName("LblFaces").Text   = str(new_f)
            window.FindName("LblSolids").Text  = str(new_s)
            window.FindName("LblEdges").Text   = str(new_e)
            window.FindName("LblScoreNow").Text  = str(new_score)
            window.FindName("LblScoreAfter").Text = "-"
            window.FindName("SubTitle").Text = (
                "Family: {}   |   Total: {} faces  {} solids  {} edges".format(
                    doc.Title, new_f, new_s, new_e))

            # remove deleted rows from list
            to_remove = [r for r in items if r.Selected and r.ElemId not in
                         [row.ElemId for row in [r2 for r2 in sel[blocked:]]]]
            keep = [r for r in items if not r.Selected or
                    any(r.ElemId == b.ElemId for b in [row for row in sel][:blocked])]
            items.Clear()
            for r in [r for r in form_rows if not r.Selected]:
                items.Add(r)
            grid.Items.Refresh()

            msg = "Deleted {}.".format(deleted)
            if blocked:
                msg += " {} blocked (constrained/hosted).".format(blocked)
            window.FindName("Status").Text = msg

        window.FindName("BtnSelectAll").Click  += select_all
        window.FindName("BtnSelectNone").Click += select_none
        window.FindName("BtnDelete").Click     += delete_selected
        window.FindName("BtnClose").Click      += lambda s, e: window.Close()
        window.ShowDialog()
