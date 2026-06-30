# -*- coding: utf-8 -*-
__title__   = "Family\nOptimizer"
__doc__     = """Version = 5.0
Date    = 24.06.2026
________________________________________________________________
Description:
Full family health tool — scores every benchmark attribute,
shows gain potential, and lets you fix each one directly.
Sections: Score | File & Performance | Parameters |
          Required Params | Reference Planes | Nested Families |
          Subcategories | Family Types | Internal Views | Geometry
________________________________________________________________
Author: Frank Sun"""

import clr, os
clr.AddReference("RevitAPI"); clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework"); clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from Autodesk.Revit.DB import (
    FilteredElementCollector, ImportInstance, ReferencePlane,
    Family, FamilyInstance, Group, Dimension, InternalDefinition, BuiltInParameter,
    ViewDetailLevel, Solid, GeometryInstance, Options, Transaction, ElementId, View,
)
from System.Windows.Markup import XamlReader
from System.Collections.ObjectModel import ObservableCollection

doc = __revit__.ActiveUIDocument.Document

REQUIRED_PARAMS = {
    "Manufacturer","Model","OmniClass Number","OmniClass Title",
    "Description","Keynote","URL","Type Comments","Type Mark",
    "Assembly Code","Assembly Description","Cost",
}

# ── SCORING ───────────────────────────────────────────────────────────────────
def _blended(f,s,e):
    return (max(0,10-f//10)+max(0,10-s)+max(0,10-e//10))/3.0

def _final(sz,cad,img,nest,grp,rp,ut,ui,tp,sh,fp,f,s,e):
    return round(
        max(0,10-sz)*1.25 + _blended(f,s,e)*1.25 +
        max(0,10-10*cad)*1.25 + max(0,10-nest)*1.25 +
        max(0,10-10*img)*0.5 + max(0,10-5*grp)*0.75 +
        max(0,10-rp)*0.5 + max(0,10-2*ut)*0.75 + max(0,10-2*ui)*0.75 +
        max(0,10-tp//2)*0.5 + max(0,10-2*sh)*0.5 + max(0,10-2*fp)*0.75, 1)

def contrib(vc,vm,per,w,base=10):
    return max(0.,base-vc*per)*w, max(0.,base-vm*per)*w

# ── GEOMETRY ──────────────────────────────────────────────────────────────────
def _walk(obj,c):
    if isinstance(obj,Solid):
        try:
            if obj.Volume>0: c[0]+=1; c[1]+=obj.Faces.Size; c[2]+=obj.Edges.Size
        except: pass
    elif isinstance(obj,GeometryInstance):
        try:
            for i in obj.GetInstanceGeometry(): _walk(i,c)
        except: pass

def _geom_of(elem):
    opt=Options(); opt.DetailLevel=ViewDetailLevel.Fine; opt.ComputeReferences=False
    c=[0,0,0]
    try:
        g=elem.get_Geometry(opt)
        if g:
            for o in g: _walk(o,c)
    except: pass
    return c[0],c[1],c[2]

def _total_geom():
    opt=Options(); opt.DetailLevel=ViewDetailLevel.Fine; opt.ComputeReferences=False
    c=[0,0,0]
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            g=el.get_Geometry(opt)
            if g:
                for o in g: _walk(o,c)
        except: pass
    return c[0],c[1],c[2]

def _scan_forms(tf,ts,te):
    gs=_blended(tf,ts,te)*1.25; rows=[]; seen=set()
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            eid=el.Id.IntegerValue
            if eid in seen: continue
            seen.add(eid)
            s,f,e=_geom_of(el)
            if f==0 and s==0: continue
            pct="{:.0f}%".format(100.*f/tf) if tf>0 else "0%"
            after=_blended(max(0,tf-f),max(0,ts-s),max(0,te-e))*1.25
            gain=after-gs
            try: cat=el.Category.Name if el.Category else ""
            except: cat=""
            try: nm=el.Name or ""
            except: nm=""
            rows.append(GeoRow(
                cat or el.GetType().Name.split(".")[-1],
                nm or "Id {}".format(eid),
                s,f,e,pct,
                "+{:.2f}".format(gain) if gain>0 else "—",eid))
        except: pass
    rows.sort(key=lambda r:r.Faces,reverse=True)
    return rows

# ── PARAMS ────────────────────────────────────────────────────────────────────
def _collect_params():
    fm=doc.FamilyManager; all_p=list(fm.Parameters)
    n_sh=sum(1 for p in all_p if p.IsShared)
    fo=set(); fi=set()
    for p in all_p:
        try: f=p.Formula or ""
        except: f=""
        if f.strip():
            fo.add(p.Id.IntegerValue)
            for o in all_p:
                if o.Definition.Name in f: fi.add(o.Id.IntegerValue)
    da=set()
    for d in FilteredElementCollector(doc).OfClass(Dimension).ToElements():
        try:
            if d.FamilyLabel is not None: da.add(d.FamilyLabel.Id.IntegerValue)
        except: pass
    lp=set()
    try:
        from Autodesk.Revit.DB import FamilyLabel as FL
        for fl in FilteredElementCollector(doc).OfClass(FL).ToElements():
            for seg in fl.GetSegments():
                if seg.IsParam: lp.add(seg.FamilyParameter.Id.IntegerValue)
    except: pass
    ep=set()
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            for p2 in el.Parameters:
                try:
                    a=fm.GetAssociatedFamilyParameter(p2)
                    if a is not None: ep.add(a.Id.IntegerValue)
                except: pass
        except: pass
    ut=[]; ui=[]; ush=[]
    for p in all_p:
        pid=p.Id.IntegerValue
        try:
            d=p.Definition
            if isinstance(d,InternalDefinition) and d.BuiltInParameter!=BuiltInParameter.INVALID: continue
        except: pass
        if p.Definition.Name in REQUIRED_PARAMS: continue
        used=(pid in fo or pid in fi or pid in da or pid in lp or pid in ep)
        if used: continue
        if p.IsInstance: ui.append(p.Definition.Name)
        else:
            ut.append(p.Definition.Name)
            if p.IsShared: ush.append(p.Definition.Name)
    for p in all_p:
        pid=p.Id.IntegerValue
        if not (p.IsShared and p.IsInstance): continue
        if p.Definition.Name in REQUIRED_PARAMS: continue
        if not (pid in fo or pid in fi or pid in da or pid in lp or pid in ep):
            if p.Definition.Name not in ush: ush.append(p.Definition.Name)
    return len(all_p),n_sh,len(fo),ut,ui,ush

# ── REQUIRED PARAMS ───────────────────────────────────────────────────────────
def _collect_req_params():
    fm = doc.FamilyManager
    all_p = {p.Definition.Name: p for p in fm.Parameters}
    types = list(fm.Types)
    first_type = types[0] if types else None
    rows = []
    for name in sorted(REQUIRED_PARAMS):
        p = all_p.get(name)
        if p is None:
            rows.append(ReqParamRow(name, False, ""))
            continue
        val = ""
        if first_type:
            try: val = first_type.AsString(p) or ""
            except:
                try: val = first_type.AsValueString(p) or ""
                except: val = ""
        rows.append(ReqParamRow(name, True, val))
    return rows

# ── NESTED FAMILIES ───────────────────────────────────────────────────────────
def _collect_nested():
    inst_by_type = {}
    for inst in FilteredElementCollector(doc).OfClass(FamilyInstance).ToElements():
        try:
            tid = inst.GetTypeId().IntegerValue
            inst_by_type[tid] = inst_by_type.get(tid, 0) + 1
        except: pass
    rows = []
    for fam in FilteredElementCollector(doc).OfClass(Family).ToElements():
        try:
            cat = ""
            try: cat = fam.FamilyCategory.Name if fam.FamilyCategory else ""
            except: pass
            count = sum(inst_by_type.get(sid.IntegerValue, 0) for sid in fam.GetFamilySymbolIds())
            rows.append(NestedRow(fam.Name, cat, count, fam.Id.IntegerValue))
        except: pass
    rows.sort(key=lambda r: r.InstanceCount)
    return rows

# ── SUBCATEGORIES ─────────────────────────────────────────────────────────────
def _collect_subcats():
    rows = []
    try:
        main_cat = doc.OwnerFamily.FamilyCategory
        if not main_cat: return rows
        used = set()
        for el in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
            try:
                c = el.Category
                if c: used.add(c.Id.IntegerValue)
            except: pass
        for sc in main_cat.SubCategories:
            try:
                if isinstance(sc, str):
                    sc = main_cat.SubCategories.get_Item(sc)
                eid = sc.Id.IntegerValue
                if eid < 0: continue
                has_geo = eid in used
                rows.append(SubcatRow(sc.Name, has_geo, eid))
            except: pass
    except: pass
    return rows

# ── REFERENCE PLANES FULL ─────────────────────────────────────────────────────
def _collect_rp_full():
    rows = []
    for rp in FilteredElementCollector(doc).OfClass(ReferencePlane).ToElements():
        try:
            name = rp.Name or ""
            is_unnamed = name.strip().lower() in ("reference plane", "")
            status = "Unnamed" if is_unnamed else "Named"
            rows.append(RPFullRow(name, status, rp.Id.IntegerValue))
        except: pass
    rows.sort(key=lambda r: (r.Status == "Named", r.Name.lower()))
    return rows

# ── INTERNAL VIEWS ────────────────────────────────────────────────────────────
def _collect_views():
    DEFAULT_NAMES = {
        "ref. level","floor plan","ceiling plan","view 1","{3d}","3d view",
        "elevation: left","elevation: right","elevation: front","elevation: back",
        "ref level","section",
    }
    rows = []
    for v in FilteredElementCollector(doc).OfClass(View).ToElements():
        try:
            is_tmpl = False
            try: is_tmpl = v.IsTemplate
            except: pass
            if is_tmpl: continue
            name = v.Name or ""
            vtype = str(v.ViewType)
            is_default = (name.lower() in DEFAULT_NAMES or
                          name.lower().startswith("ref.") or
                          name.lower().startswith("section "))
            note = "Default" if is_default else ""
            rows.append(ViewRow(name, vtype, note, v.Id.IntegerValue, not is_default))
        except: pass
    return rows

# ── FAMILY TYPES ──────────────────────────────────────────────────────────────
def _collect_types():
    fm = doc.FamilyManager
    all_p = {p.Definition.Name: p for p in fm.Parameters}
    req_in_family = {n: p for n, p in all_p.items() if n in REQUIRED_PARAMS}
    rows = []
    for ft in fm.Types:
        missing_names = []
        for n2, p2 in req_in_family.items():
            try:
                val = ft.AsString(p2) or ""
                if not val.strip(): missing_names.append(n2)
            except: missing_names.append(n2)
        rows.append(TypeRow(ft.Name or "(Default)", missing_names))
    return rows

# ── MODELS ────────────────────────────────────────────────────────────────────
class AttrRow(object):
    def __init__(self,attr,current,minimum,sn,sa,items=""):
        self.Attr=attr; self.Current=str(current); self.Min=str(minimum)
        try:
            d=current-minimum; self.ReduceBy=str(d) if d>0 else "—"
        except TypeError: self.ReduceBy="—"
        self.ScoreNow="{:.1f}".format(sn); self.ScoreAfter="{:.1f}".format(sa)
        g=sa-sn; self.Gain="+{:.1f}".format(g) if g>0.05 else "—"
        self.Items=items
        self.HasGain = g>0.05

class GeoRow(object):
    def __init__(self,etype,ename,solids,faces,edges,pct,impact,eid):
        self.EType=etype; self.EName=ename; self.Solids=solids
        self.Faces=faces; self.Edges=edges; self.Pct=pct
        self.Impact=impact; self.ElemId=eid; self.Selected=False

class ReqParamRow(object):
    def __init__(self, name, exists, value):
        self.Name = name
        self.Exists = "Yes" if exists else "No"
        self.Value = value
        self.HasIssue = not exists or not (value or "").strip()
        self._exists = exists

class NestedRow(object):
    def __init__(self, fname, cat, count, fid):
        self.FamilyName = fname
        self.Category = cat
        self.InstanceCount = count
        self.FamId = fid

class SubcatRow(object):
    def __init__(self, name, has_geo, eid):
        self.Name = name
        self.HasGeometry = "Yes" if has_geo else "No"
        self.SubcatId = eid
        self._has_geo = has_geo

class RPFullRow(object):
    def __init__(self, name, status, eid):
        self.Name = name
        self.OriginalName = name
        self.Status = status
        self.ElemId = eid
        self.Selected = False

class ViewRow(object):
    def __init__(self, name, vtype, note, eid, can_delete):
        self.Name = name
        self.ViewType = vtype
        self.Note = note
        self.ElemId = eid
        self.Selected = False
        self.CanDelete = can_delete

class TypeRow(object):
    def __init__(self, type_name, missing_names):
        self.TypeName = type_name
        self.MissingCount = ", ".join(sorted(missing_names)) if missing_names else "OK"
        self.HasIssue = len(missing_names) > 0
        self.Selected = False

# ── CONFIRM HELPER ────────────────────────────────────────────────────────────
def _confirm(title, msg):
    from System.Windows import MessageBox, MessageBoxButton, MessageBoxResult
    r = MessageBox.Show(msg, title, MessageBoxButton.YesNo)
    return r == MessageBoxResult.Yes


# â”€â”€ XAML â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Family Optimizer" Width="1100" Height="820"
        WindowStartupLocation="CenterScreen"
        Background="#FFFFFF" FontFamily="Segoe UI" FontSize="12">
  <Window.Resources>

    <Style TargetType="Button">
      <Setter Property="Background"      Value="#F3F4F6"/>
      <Setter Property="Foreground"      Value="#000000"/>
      <Setter Property="BorderBrush"     Value="#D1D5DB"/>
      <Setter Property="BorderThickness" Value="1"/>
      <Setter Property="Padding"         Value="12,6"/>
      <Setter Property="Cursor"          Value="Hand"/>
      <Setter Property="FontSize"        Value="11"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#E8EAED"/>
          <Setter Property="BorderBrush" Value="#9EA3AB"/>
        </Trigger>
        <Trigger Property="IsEnabled" Value="False">
          <Setter Property="Opacity" Value="0.4"/>
        </Trigger>
      </Style.Triggers>
    </Style>

    <Style x:Key="ActBtn" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Background"  Value="#FFF3E0"/>
      <Setter Property="Foreground"  Value="#B45309"/>
      <Setter Property="BorderBrush" Value="#F0C060"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#FFE8C0"/>
          <Setter Property="BorderBrush" Value="#F0883E"/>
        </Trigger>
      </Style.Triggers>
    </Style>

    <Style x:Key="DangerBtn" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Background"  Value="#FFF0F0"/>
      <Setter Property="Foreground"  Value="#B91C1C"/>
      <Setter Property="BorderBrush" Value="#FFB0AE"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#FFE5E5"/>
          <Setter Property="BorderBrush" Value="#F85149"/>
        </Trigger>
      </Style.Triggers>
    </Style>

    <Style TargetType="DataGrid">
      <Setter Property="Background"               Value="#FFFFFF"/>
      <Setter Property="Foreground"               Value="#000000"/>
      <Setter Property="BorderBrush"              Value="#D0D7DE"/>
      <Setter Property="BorderThickness"          Value="1"/>
      <Setter Property="RowBackground"            Value="#FFFFFF"/>
      <Setter Property="AlternatingRowBackground" Value="#F6F8FA"/>
      <Setter Property="HorizontalGridLinesBrush" Value="#E8EBEF"/>
      <Setter Property="VerticalGridLinesBrush"   Value="#E8EBEF"/>
      <Setter Property="ColumnHeaderHeight"       Value="32"/>
      <Setter Property="RowHeight"                Value="28"/>
      <Setter Property="SelectionUnit"            Value="FullRow"/>
    </Style>
    <Style TargetType="DataGridColumnHeader">
      <Setter Property="Background"      Value="#F0F2F5"/>
      <Setter Property="Foreground"      Value="#000000"/>
      <Setter Property="FontWeight"      Value="SemiBold"/>
      <Setter Property="FontSize"        Value="11"/>
      <Setter Property="Padding"         Value="10,0"/>
      <Setter Property="BorderBrush"     Value="#D0D7DE"/>
      <Setter Property="BorderThickness" Value="0,0,0,1"/>
    </Style>
    <Style TargetType="DataGridCell">
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Padding"         Value="10,0"/>
      <Setter Property="VerticalContentAlignment" Value="Center"/>
      <Style.Triggers>
        <Trigger Property="IsSelected" Value="True">
          <Setter Property="Background" Value="#E8F0FF"/>
          <Setter Property="Foreground" Value="#000000"/>
        </Trigger>
      </Style.Triggers>
    </Style>
    <Style TargetType="DataGridRow">
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#F0F2F5"/>
        </Trigger>
      </Style.Triggers>
    </Style>

    <Style TargetType="ListBox">
      <Setter Property="Background"      Value="#F6F8FA"/>
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Padding"         Value="0,6"/>
    </Style>
    <Style TargetType="ListBoxItem">
      <Setter Property="Background"      Value="Transparent"/>
      <Setter Property="Foreground"      Value="#000000"/>
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Padding"         Value="16,9,12,9"/>
      <Setter Property="Cursor"          Value="Hand"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#E4ECF3"/>
        </Trigger>
        <Trigger Property="IsSelected" Value="True">
          <Setter Property="Background" Value="#D8E8F5"/>
          <Setter Property="FontWeight" Value="SemiBold"/>
        </Trigger>
      </Style.Triggers>
    </Style>

  </Window.Resources>

  <Grid>
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
    </Grid.RowDefinitions>

    <!-- HEADER -->
    <Border Grid.Row="0" Background="#FFFFFF" BorderBrush="#D0D7DE" BorderThickness="0,0,0,1" Padding="24,13,20,13">
      <Grid>
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="*"/>
          <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <StackPanel Grid.Column="0" VerticalAlignment="Center">
          <TextBlock Text="Family Optimizer" FontSize="17" FontWeight="Bold" Foreground="#000000"/>
          <TextBlock x:Name="SubTitle" FontSize="11" Foreground="#555F6D" Margin="0,2,0,0"/>
        </StackPanel>
        <StackPanel Grid.Column="1" Orientation="Horizontal" VerticalAlignment="Center">
          <Border Padding="14,6" Margin="0,0,6,0" Background="#FFF3E0" CornerRadius="6" BorderBrush="#F0C060" BorderThickness="1">
            <StackPanel>
              <TextBlock Text="CURRENT" FontSize="8" FontWeight="Bold" Foreground="#B45309" HorizontalAlignment="Center"/>
              <TextBlock x:Name="ScoreCurrent" FontSize="26" FontWeight="Bold" FontFamily="Consolas" Foreground="#F0883E" HorizontalAlignment="Center"/>
            </StackPanel>
          </Border>
          <TextBlock Text="&#8594;" FontSize="16" Foreground="#D0D7DE" VerticalAlignment="Center" Margin="0,0,6,0"/>
          <Border Padding="14,6" Margin="0,0,6,0" Background="#EAFFF0" CornerRadius="6" BorderBrush="#A8E6B8" BorderThickness="1">
            <StackPanel>
              <TextBlock Text="POTENTIAL" FontSize="8" FontWeight="Bold" Foreground="#16803A" HorizontalAlignment="Center"/>
              <TextBlock x:Name="ScorePotential" FontSize="26" FontWeight="Bold" FontFamily="Consolas" Foreground="#3FB950" HorizontalAlignment="Center"/>
            </StackPanel>
          </Border>
          <Border Padding="14,6" Margin="0,0,16,0" Background="#EFF3FF" CornerRadius="6" BorderBrush="#B8CCFF" BorderThickness="1">
            <StackPanel>
              <TextBlock Text="GAIN" FontSize="8" FontWeight="Bold" Foreground="#1A56D6" HorizontalAlignment="Center"/>
              <TextBlock x:Name="ScoreGain" FontSize="26" FontWeight="Bold" FontFamily="Consolas" Foreground="#58A6FF" HorizontalAlignment="Center"/>
            </StackPanel>
          </Border>
          <Button x:Name="BtnOpenOther" Content="Open Other..." VerticalAlignment="Center" Margin="0,0,8,0"/>
          <Button x:Name="BtnClose" Content="Close" VerticalAlignment="Center"/>
        </StackPanel>
      </Grid>
    </Border>

    <!-- BODY -->
    <Grid Grid.Row="1">
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="210"/>
        <ColumnDefinition Width="*"/>
      </Grid.ColumnDefinitions>

      <!-- SIDEBAR -->
      <Border Grid.Column="0" Background="#F6F8FA" BorderBrush="#D0D7DE" BorderThickness="0,0,1,0">
        <ListBox x:Name="NavList" SelectedIndex="0">
          <ListBoxItem><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><Ellipse Grid.Column="0" Width="7" Height="7" Fill="#58A6FF" VerticalAlignment="Center"/><TextBlock Grid.Column="1" Text="Overview" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/><TextBlock Grid.Column="2" x:Name="NavBadge_Overview" FontSize="10" Foreground="#555F6D" VerticalAlignment="Center"/></Grid></ListBoxItem>
          <ListBoxItem><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><Ellipse Grid.Column="0" Width="7" Height="7" Fill="#F0883E" VerticalAlignment="Center"/><TextBlock Grid.Column="1" Text="File &amp; Performance" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/><TextBlock Grid.Column="2" x:Name="NavBadge_File" FontSize="10" Foreground="#555F6D" VerticalAlignment="Center"/></Grid></ListBoxItem>
          <ListBoxItem><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><Ellipse Grid.Column="0" Width="7" Height="7" Fill="#58A6FF" VerticalAlignment="Center"/><TextBlock Grid.Column="1" Text="Parameters" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/><TextBlock Grid.Column="2" x:Name="NavBadge_Params" FontSize="10" Foreground="#555F6D" VerticalAlignment="Center"/></Grid></ListBoxItem>
          <ListBoxItem><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><Ellipse Grid.Column="0" Width="7" Height="7" Fill="#E3B341" VerticalAlignment="Center"/><TextBlock Grid.Column="1" Text="Required Params" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/><TextBlock Grid.Column="2" x:Name="NavBadge_ReqParams" FontSize="10" Foreground="#555F6D" VerticalAlignment="Center"/></Grid></ListBoxItem>
          <ListBoxItem><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><Ellipse Grid.Column="0" Width="7" Height="7" Fill="#3FB950" VerticalAlignment="Center"/><TextBlock Grid.Column="1" Text="Reference Planes" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/><TextBlock Grid.Column="2" x:Name="NavBadge_RefPlanes" FontSize="10" Foreground="#555F6D" VerticalAlignment="Center"/></Grid></ListBoxItem>
          <ListBoxItem><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><Ellipse Grid.Column="0" Width="7" Height="7" Fill="#DB6D28" VerticalAlignment="Center"/><TextBlock Grid.Column="1" Text="Nested Families" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/><TextBlock Grid.Column="2" x:Name="NavBadge_Nested" FontSize="10" Foreground="#555F6D" VerticalAlignment="Center"/></Grid></ListBoxItem>
          <ListBoxItem><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><Ellipse Grid.Column="0" Width="7" Height="7" Fill="#56D364" VerticalAlignment="Center"/><TextBlock Grid.Column="1" Text="Subcategories" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/><TextBlock Grid.Column="2" x:Name="NavBadge_Subcats" FontSize="10" Foreground="#555F6D" VerticalAlignment="Center"/></Grid></ListBoxItem>
          <ListBoxItem><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><Ellipse Grid.Column="0" Width="7" Height="7" Fill="#BC8CFF" VerticalAlignment="Center"/><TextBlock Grid.Column="1" Text="Family Types" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/><TextBlock Grid.Column="2" x:Name="NavBadge_Types" FontSize="10" Foreground="#555F6D" VerticalAlignment="Center"/></Grid></ListBoxItem>
          <ListBoxItem><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><Ellipse Grid.Column="0" Width="7" Height="7" Fill="#79C0FF" VerticalAlignment="Center"/><TextBlock Grid.Column="1" Text="Internal Views" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/><TextBlock Grid.Column="2" x:Name="NavBadge_Views" FontSize="10" Foreground="#555F6D" VerticalAlignment="Center"/></Grid></ListBoxItem>
          <ListBoxItem><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><Ellipse Grid.Column="0" Width="7" Height="7" Fill="#A78BFA" VerticalAlignment="Center"/><TextBlock Grid.Column="1" Text="Geometry" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/><TextBlock Grid.Column="2" x:Name="NavBadge_Geometry" FontSize="10" Foreground="#555F6D" VerticalAlignment="Center"/></Grid></ListBoxItem>
        </ListBox>
      </Border>

      <!-- CONTENT -->
      <ScrollViewer Grid.Column="1" VerticalScrollBarVisibility="Auto">
        <StackPanel>

          <!-- OVERVIEW -->
          <StackPanel x:Name="Panel_Overview" Visibility="Visible">
            <Border Background="#F8FAFC" BorderBrush="#E8EBEF" BorderThickness="0,0,0,1" Padding="28,18,28,14">
              <StackPanel>
                <TextBlock Text="Health Overview" FontSize="14" FontWeight="SemiBold" Foreground="#000000"/>
                <TextBlock Text="Score breakdown across 13 family health attributes. Use the left navigation to jump to any section and take action." FontSize="12" Foreground="#555F6D" Margin="0,4,0,0" TextWrapping="Wrap"/>
              </StackPanel>
            </Border>
            <StackPanel Margin="28,16,28,20">
              <DataGrid x:Name="AttrGrid" Height="310" AutoGenerateColumns="False" CanUserAddRows="False" CanUserDeleteRows="False" CanUserResizeRows="False" IsReadOnly="True">
                <DataGrid.Columns>
                  <DataGridTextColumn Header="Attribute"   Binding="{Binding Attr}"       Width="175"/>
                  <DataGridTextColumn Header="Current"     Binding="{Binding Current}"    Width="78"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="HorizontalAlignment" Value="Center"/><Setter Property="FontFamily" Value="Consolas"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                  <DataGridTextColumn Header="Min"         Binding="{Binding Min}"        Width="62"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="HorizontalAlignment" Value="Center"/><Setter Property="FontFamily" Value="Consolas"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                  <DataGridTextColumn Header="Score Now"   Binding="{Binding ScoreNow}"   Width="78"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="HorizontalAlignment" Value="Right"/><Setter Property="FontFamily" Value="Consolas"/><Setter Property="Foreground" Value="#555F6D"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                  <DataGridTextColumn Header="After Fix"   Binding="{Binding ScoreAfter}" Width="78"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="HorizontalAlignment" Value="Right"/><Setter Property="FontFamily" Value="Consolas"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                  <DataGridTemplateColumn Header="Gain" Width="70">
                    <DataGridTemplateColumn.CellTemplate>
                      <DataTemplate>
                        <Border CornerRadius="10" Padding="6,2" HorizontalAlignment="Center" Margin="0,3">
                          <Border.Style><Style TargetType="Border"><Setter Property="Background" Value="Transparent"/><Style.Triggers><DataTrigger Binding="{Binding HasGain}" Value="True"><Setter Property="Background" Value="#D4F5DC"/></DataTrigger></Style.Triggers></Style></Border.Style>
                          <TextBlock Text="{Binding Gain}" FontSize="11" FontFamily="Consolas" HorizontalAlignment="Center"><TextBlock.Style><Style TargetType="TextBlock"><Setter Property="Foreground" Value="#9EA3AB"/><Style.Triggers><DataTrigger Binding="{Binding HasGain}" Value="True"><Setter Property="Foreground" Value="#3FB950"/></DataTrigger></Style.Triggers></Style></TextBlock.Style></TextBlock>
                        </Border>
                      </DataTemplate>
                    </DataGridTemplateColumn.CellTemplate>
                  </DataGridTemplateColumn>
                  <DataGridTextColumn Header="Items to Fix" Binding="{Binding Items}" Width="*"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="Foreground" Value="#555F6D"/><Setter Property="FontSize" Value="11"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                </DataGrid.Columns>
              </DataGrid>
            </StackPanel>
          </StackPanel>

          <!-- FILE AND PERFORMANCE -->
          <StackPanel x:Name="Panel_File" Visibility="Collapsed">
            <Border Background="#FFFCF5" BorderBrush="#FDD9A0" BorderThickness="0,0,0,1" Padding="28,18,28,14">
              <StackPanel>
                <TextBlock Text="File &amp; Performance" FontSize="14" FontWeight="SemiBold" Foreground="#B45309"/>
                <TextBlock Text="Reduce file weight by removing embedded objects. Each action is independent and undoable." FontSize="12" Foreground="#555F6D" Margin="0,4,0,0" TextWrapping="Wrap"/>
              </StackPanel>
            </Border>
            <StackPanel Margin="28,20,28,8">
              <TextBlock Text="Purge Unused" FontWeight="SemiBold" FontSize="12" Margin="0,0,0,4"/>
              <TextBlock Text="Launches Revit's built-in Purge Unused dialog. You confirm the selection inside Revit before anything is removed." FontSize="11" Foreground="#555F6D" TextWrapping="Wrap" Margin="0,0,0,10"/>
              <Button x:Name="BtnPurge" Content="Purge Unused" Style="{StaticResource ActBtn}" HorizontalAlignment="Left"/>
            </StackPanel>
            <Border Background="#F6F8FA" BorderBrush="#E8EBEF" BorderThickness="0,1,0,1" Padding="28,16">
              <StackPanel>
                <TextBlock Text="Embedded Objects" FontWeight="SemiBold" FontSize="12" Margin="0,0,0,4"/>
                <TextBlock Text="CAD imports and raster images bloat the family. Model groups inside families serve no purpose and can cause instability." FontSize="11" Foreground="#555F6D" TextWrapping="Wrap" Margin="0,0,0,12"/>
                <WrapPanel>
                  <Button x:Name="BtnDelCAD"    Content="Delete CAD Imports"   Style="{StaticResource ActBtn}" Margin="0,0,8,0"/>
                  <Button x:Name="BtnDelImages" Content="Delete Raster Images" Style="{StaticResource ActBtn}" Margin="0,0,8,0"/>
                  <Button x:Name="BtnUngroup"   Content="Ungroup All Groups"   Style="{StaticResource ActBtn}"/>
                </WrapPanel>
              </StackPanel>
            </Border>
            <Border Padding="28,10" Background="#FAFAFA">
              <StackPanel Orientation="Horizontal">
                <TextBlock x:Name="PerfStatus" Foreground="#16803A" FontSize="11" VerticalAlignment="Center" Margin="0,0,12,0"/>
                <Button x:Name="BtnUndoPerf" Content="&#8617; Undo" Visibility="Collapsed" Background="#F3EEFF" Foreground="#7C3AED" BorderBrush="#C4A6FF" Padding="8,4"/>
              </StackPanel>
            </Border>
          </StackPanel>

          <!-- PARAMETERS -->
          <StackPanel x:Name="Panel_Params" Visibility="Collapsed">
            <Border Background="#EFF3FF" BorderBrush="#B8CCFF" BorderThickness="0,0,0,1" Padding="28,18,28,14">
              <StackPanel>
                <TextBlock Text="Parameters" FontSize="14" FontWeight="SemiBold" Foreground="#1A56D6"/>
                <TextBlock Text="Unused parameters are not referenced by any formula, dimension, tag, or geometry. Shared parameters need care - removing them breaks schedules or tags in projects using this family." FontSize="12" Foreground="#555F6D" Margin="0,4,0,0" TextWrapping="Wrap"/>
              </StackPanel>
            </Border>
            <StackPanel Margin="28,20,28,8">
              <WrapPanel Margin="0,0,0,12">
                <Button x:Name="BtnDelType"   Content="Delete Unused Type Params"   Style="{StaticResource ActBtn}" Margin="0,0,8,4"/>
                <Button x:Name="BtnDelInst"   Content="Delete Unused Inst Params"   Style="{StaticResource ActBtn}" Margin="0,0,8,4"/>
                <Button x:Name="BtnDelShared" Content="Delete Unused Shared Params" Style="{StaticResource DangerBtn}" Margin="0,0,0,4"/>
              </WrapPanel>
              <Border Background="#F6F8FA" BorderBrush="#D0D7DE" BorderThickness="1" CornerRadius="4" Padding="12,8" MaxHeight="90">
                <ScrollViewer VerticalScrollBarVisibility="Auto">
                  <TextBlock x:Name="DetailText" Foreground="#555F6D" FontSize="10" FontFamily="Consolas" TextWrapping="Wrap"/>
                </ScrollViewer>
              </Border>
            </StackPanel>
            <Border Padding="28,10" Background="#FAFAFA" BorderBrush="#E8EBEF" BorderThickness="0,1,0,0">
              <StackPanel Orientation="Horizontal">
                <TextBlock x:Name="ParamStatus" Foreground="#16803A" FontSize="11" VerticalAlignment="Center" Margin="0,0,12,0"/>
                <Button x:Name="BtnUndoParam" Content="&#8617; Undo" Visibility="Collapsed" Background="#F3EEFF" Foreground="#7C3AED" BorderBrush="#C4A6FF" Padding="8,4"/>
              </StackPanel>
            </Border>
          </StackPanel>

          <!-- REQUIRED PARAMS -->
          <StackPanel x:Name="Panel_ReqParams" Visibility="Collapsed">
            <Border Background="#FFFCF5" BorderBrush="#FDD9A0" BorderThickness="0,0,0,1" Padding="28,18,28,14">
              <StackPanel>
                <TextBlock Text="Required Parameters" FontSize="14" FontWeight="SemiBold" Foreground="#B45309"/>
                <TextBlock Text="BBB standard parameters. Click a Value cell to edit it, then Apply to All Types to write across every type. Parameters showing No under Exists must be added via Revit Family Types dialog first." FontSize="12" Foreground="#555F6D" Margin="0,4,0,0" TextWrapping="Wrap"/>
              </StackPanel>
            </Border>
            <StackPanel Margin="28,16,28,16">
              <DataGrid x:Name="ReqGrid" Height="260" AutoGenerateColumns="False" CanUserAddRows="False" CanUserDeleteRows="False" CanUserResizeRows="False" IsReadOnly="False">
                <DataGrid.RowStyle>
                  <Style TargetType="DataGridRow">
                    <Style.Triggers>
                      <DataTrigger Binding="{Binding HasIssue}" Value="True"><Setter Property="Background" Value="#FFF5E5"/></DataTrigger>
                      <Trigger Property="IsMouseOver" Value="True"><Setter Property="Background" Value="#F0F2F5"/></Trigger>
                    </Style.Triggers>
                  </Style>
                </DataGrid.RowStyle>
                <DataGrid.Columns>
                  <DataGridTextColumn Header="Parameter" Binding="{Binding Name}"   Width="185" IsReadOnly="True"/>
                  <DataGridTextColumn Header="Exists"    Binding="{Binding Exists}" Width="65"  IsReadOnly="True"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="HorizontalAlignment" Value="Center"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                  <DataGridTextColumn Header="Value (click to edit)" Binding="{Binding Value, Mode=TwoWay, UpdateSourceTrigger=LostFocus}" Width="*"/>
                </DataGrid.Columns>
              </DataGrid>
            </StackPanel>
            <Border Padding="28,10" Background="#FAFAFA" BorderBrush="#E8EBEF" BorderThickness="0,1,0,0">
              <StackPanel Orientation="Horizontal">
                <Button x:Name="BtnApplyReq" Content="Apply to All Types" Style="{StaticResource ActBtn}" Margin="0,0,12,0"/>
                <TextBlock x:Name="ReqStatus" Foreground="#16803A" FontSize="11" VerticalAlignment="Center"/>
              </StackPanel>
            </Border>
          </StackPanel>

          <!-- REFERENCE PLANES -->
          <StackPanel x:Name="Panel_RefPlanes" Visibility="Collapsed">
            <Border Background="#F0FFF5" BorderBrush="#A8E6B8" BorderThickness="0,0,0,1" Padding="28,18,28,14">
              <StackPanel>
                <TextBlock Text="Reference Planes" FontSize="14" FontWeight="SemiBold" Foreground="#16803A"/>
                <TextBlock Text="Planes still named Reference Plane count against the score. Click a Name cell to rename inline, then Apply Renames. Check to select planes for deletion - constrained planes will be skipped." FontSize="12" Foreground="#555F6D" Margin="0,4,0,0" TextWrapping="Wrap"/>
              </StackPanel>
            </Border>
            <StackPanel Margin="28,16,28,16">
              <DataGrid x:Name="RPGrid" Height="230" AutoGenerateColumns="False" CanUserAddRows="False" CanUserDeleteRows="False" CanUserResizeRows="False" IsReadOnly="False">
                <DataGrid.Columns>
                  <DataGridTemplateColumn Header="" Width="32" CanUserResize="False"><DataGridTemplateColumn.CellTemplate><DataTemplate><CheckBox IsChecked="{Binding Selected, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}" HorizontalAlignment="Center" VerticalAlignment="Center"/></DataTemplate></DataGridTemplateColumn.CellTemplate></DataGridTemplateColumn>
                  <DataGridTextColumn Header="Name (click to rename)" Binding="{Binding Name, Mode=TwoWay, UpdateSourceTrigger=LostFocus}" Width="*"/>
                  <DataGridTextColumn Header="Status" Binding="{Binding Status}" Width="90" IsReadOnly="True"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="HorizontalAlignment" Value="Center"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                </DataGrid.Columns>
              </DataGrid>
            </StackPanel>
            <Border Padding="28,10" Background="#FAFAFA" BorderBrush="#E8EBEF" BorderThickness="0,1,0,0">
              <StackPanel Orientation="Horizontal">
                <Button x:Name="BtnRenameRP" Content="Apply Renames"   Style="{StaticResource ActBtn}"    Margin="0,0,8,0"/>
                <Button x:Name="BtnDelSelRP" Content="Delete Selected"  Style="{StaticResource DangerBtn}" Margin="0,0,12,0"/>
                <TextBlock x:Name="RPStatus" Foreground="#16803A" FontSize="11" VerticalAlignment="Center" Margin="0,0,12,0"/>
                <Button x:Name="BtnUndoRP" Content="&#8617; Undo" Visibility="Collapsed" Background="#F3EEFF" Foreground="#7C3AED" BorderBrush="#C4A6FF" Padding="8,4"/>
              </StackPanel>
            </Border>
          </StackPanel>

          <!-- NESTED FAMILIES -->
          <StackPanel x:Name="Panel_Nested" Visibility="Collapsed">
            <Border Background="#FFF8F0" BorderBrush="#FFC4A0" BorderThickness="0,0,0,1" Padding="28,18,28,14">
              <StackPanel>
                <TextBlock Text="Nested Families" FontSize="14" FontWeight="SemiBold" Foreground="#9A3412"/>
                <TextBlock Text="Families loaded inside this family. Zero-instance families are loaded but never placed - they add file weight with no benefit. Families with instances are shown for reference only." FontSize="12" Foreground="#555F6D" Margin="0,4,0,0" TextWrapping="Wrap"/>
              </StackPanel>
            </Border>
            <StackPanel Margin="28,16,28,16">
              <DataGrid x:Name="NestGrid" Height="220" AutoGenerateColumns="False" CanUserAddRows="False" CanUserDeleteRows="False" CanUserResizeRows="False" IsReadOnly="True">
                <DataGrid.Columns>
                  <DataGridTextColumn Header="Family Name" Binding="{Binding FamilyName}"    Width="*"/>
                  <DataGridTextColumn Header="Category"    Binding="{Binding Category}"      Width="160"/>
                  <DataGridTextColumn Header="Instances"   Binding="{Binding InstanceCount}" Width="85"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="HorizontalAlignment" Value="Center"/><Setter Property="FontFamily" Value="Consolas"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                </DataGrid.Columns>
              </DataGrid>
            </StackPanel>
            <Border Padding="28,10" Background="#FAFAFA" BorderBrush="#E8EBEF" BorderThickness="0,1,0,0">
              <StackPanel Orientation="Horizontal">
                <Button x:Name="BtnOpenNested" Content="Open in Optimizer" Style="{StaticResource ActBtn}" IsEnabled="False" Margin="0,0,8,0"/>
                <Button x:Name="BtnPurgeNest" Content="Purge Unplaced (0 instances)" Style="{StaticResource DangerBtn}" Margin="0,0,12,0"/>
                <TextBlock x:Name="NestStatus" Foreground="#16803A" FontSize="11" VerticalAlignment="Center" Margin="0,0,12,0"/>
                <Button x:Name="BtnUndoNest" Content="&#8617; Undo" Visibility="Collapsed" Background="#F3EEFF" Foreground="#7C3AED" BorderBrush="#C4A6FF" Padding="8,4"/>
              </StackPanel>
            </Border>
          </StackPanel>

          <!-- SUBCATEGORIES -->
          <StackPanel x:Name="Panel_Subcats" Visibility="Collapsed">
            <Border Background="#F0FFF3" BorderBrush="#A8E6B8" BorderThickness="0,0,0,1" Padding="28,18,28,14">
              <StackPanel>
                <TextBlock Text="Subcategories" FontSize="14" FontWeight="SemiBold" Foreground="#16803A"/>
                <TextBlock Text="User-created subcategories. Those with no geometry assigned are safe to delete - they appear in Object Styles and add noise without serving any graphic purpose. Built-in subcategories are excluded." FontSize="12" Foreground="#555F6D" Margin="0,4,0,0" TextWrapping="Wrap"/>
              </StackPanel>
            </Border>
            <StackPanel Margin="28,16,28,16">
              <DataGrid x:Name="SubcatGrid" Height="180" AutoGenerateColumns="False" CanUserAddRows="False" CanUserDeleteRows="False" CanUserResizeRows="False" IsReadOnly="True">
                <DataGrid.Columns>
                  <DataGridTextColumn Header="Subcategory Name" Binding="{Binding Name}"        Width="*"/>
                  <DataGridTextColumn Header="Has Geometry"     Binding="{Binding HasGeometry}" Width="120"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="HorizontalAlignment" Value="Center"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                </DataGrid.Columns>
              </DataGrid>
            </StackPanel>
            <Border Padding="28,10" Background="#FAFAFA" BorderBrush="#E8EBEF" BorderThickness="0,1,0,0">
              <StackPanel Orientation="Horizontal">
                <Button x:Name="BtnDelSubcat" Content="Delete Unused Subcategories" Style="{StaticResource DangerBtn}" Margin="0,0,12,0"/>
                <TextBlock x:Name="SubcatStatus" Foreground="#16803A" FontSize="11" VerticalAlignment="Center" Margin="0,0,12,0"/>
                <Button x:Name="BtnUndoSubcat" Content="&#8617; Undo" Visibility="Collapsed" Background="#F3EEFF" Foreground="#7C3AED" BorderBrush="#C4A6FF" Padding="8,4"/>
              </StackPanel>
            </Border>
          </StackPanel>

          <!-- FAMILY TYPES -->
          <StackPanel x:Name="Panel_Types" Visibility="Collapsed">
            <Border Background="#F5F0FF" BorderBrush="#D8C0FF" BorderThickness="0,0,0,1" Padding="28,18,28,14">
              <StackPanel>
                <TextBlock Text="Family Types" FontSize="14" FontWeight="SemiBold" Foreground="#6D28D9"/>
                <TextBlock Text="All types in this family. Required Params shows how many BBB standard values are missing per type. Select types to delete - at least one must remain. Highlighted rows have missing required values." FontSize="12" Foreground="#555F6D" Margin="0,4,0,0" TextWrapping="Wrap"/>
              </StackPanel>
            </Border>
            <StackPanel Margin="28,16,28,16">
              <DataGrid x:Name="TypeGrid" Height="220" AutoGenerateColumns="False" CanUserAddRows="False" CanUserDeleteRows="False" CanUserResizeRows="False" IsReadOnly="False">
                <DataGrid.RowStyle>
                  <Style TargetType="DataGridRow">
                    <Style.Triggers>
                      <DataTrigger Binding="{Binding HasIssue}" Value="True"><Setter Property="Background" Value="#F0EEFF"/></DataTrigger>
                      <Trigger Property="IsMouseOver" Value="True"><Setter Property="Background" Value="#F0F2F5"/></Trigger>
                    </Style.Triggers>
                  </Style>
                </DataGrid.RowStyle>
                <DataGrid.Columns>
                  <DataGridTemplateColumn Header="" Width="32" CanUserResize="False"><DataGridTemplateColumn.CellTemplate><DataTemplate><CheckBox IsChecked="{Binding Selected, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}" HorizontalAlignment="Center" VerticalAlignment="Center"/></DataTemplate></DataGridTemplateColumn.CellTemplate></DataGridTemplateColumn>
                  <DataGridTextColumn Header="Type Name"            Binding="{Binding TypeName}"    Width="200" IsReadOnly="True"/>
                  <DataGridTextColumn Header="Missing Required Params" Binding="{Binding MissingCount}" Width="*"   IsReadOnly="True"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="Foreground" Value="#555F6D"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                </DataGrid.Columns>
              </DataGrid>
            </StackPanel>
            <Border Padding="28,10" Background="#FAFAFA" BorderBrush="#E8EBEF" BorderThickness="0,1,0,0">
              <StackPanel Orientation="Horizontal">
                <Button x:Name="BtnDelTypes" Content="Delete Selected Types" Style="{StaticResource DangerBtn}" Margin="0,0,12,0"/>
                <TextBlock x:Name="TypeStatus" Foreground="#16803A" FontSize="11" VerticalAlignment="Center" Margin="0,0,12,0"/>
                <Button x:Name="BtnUndoTypes" Content="&#8617; Undo" Visibility="Collapsed" Background="#F3EEFF" Foreground="#7C3AED" BorderBrush="#C4A6FF" Padding="8,4"/>
              </StackPanel>
            </Border>
          </StackPanel>

          <!-- INTERNAL VIEWS -->
          <StackPanel x:Name="Panel_Views" Visibility="Collapsed">
            <Border Background="#F0F4FF" BorderBrush="#B8CCFF" BorderThickness="0,0,0,1" Padding="28,18,28,14">
              <StackPanel>
                <TextBlock Text="Internal Views" FontSize="14" FontWeight="SemiBold" Foreground="#1A56D6"/>
                <TextBlock Text="Views embedded inside the family. Default views (Floor Plan, Elevations, Ref Level) cannot be deleted. User-added views - saved 3D views, sections, drafting views - increase file size without being visible in any project." FontSize="12" Foreground="#555F6D" Margin="0,4,0,0" TextWrapping="Wrap"/>
              </StackPanel>
            </Border>
            <StackPanel Margin="28,16,28,16">
              <DataGrid x:Name="ViewGrid" Height="200" AutoGenerateColumns="False" CanUserAddRows="False" CanUserDeleteRows="False" CanUserResizeRows="False" IsReadOnly="False">
                <DataGrid.Columns>
                  <DataGridTemplateColumn Header="" Width="32" CanUserResize="False"><DataGridTemplateColumn.CellTemplate><DataTemplate><CheckBox IsChecked="{Binding Selected, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}" HorizontalAlignment="Center" VerticalAlignment="Center"/></DataTemplate></DataGridTemplateColumn.CellTemplate></DataGridTemplateColumn>
                  <DataGridTextColumn Header="View Name" Binding="{Binding Name}"     Width="*"   IsReadOnly="True"/>
                  <DataGridTextColumn Header="Type"      Binding="{Binding ViewType}" Width="130" IsReadOnly="True"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="Foreground" Value="#555F6D"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                  <DataGridTextColumn Header="Note"      Binding="{Binding Note}"     Width="100" IsReadOnly="True"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="Foreground" Value="#555F6D"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                </DataGrid.Columns>
              </DataGrid>
            </StackPanel>
            <Border Padding="28,10" Background="#FAFAFA" BorderBrush="#E8EBEF" BorderThickness="0,1,0,0">
              <StackPanel Orientation="Horizontal">
                <Button x:Name="BtnDelViews" Content="Delete Selected Views" Style="{StaticResource DangerBtn}" Margin="0,0,12,0"/>
                <TextBlock x:Name="ViewStatus" Foreground="#16803A" FontSize="11" VerticalAlignment="Center" Margin="0,0,12,0"/>
                <Button x:Name="BtnUndoViews" Content="&#8617; Undo" Visibility="Collapsed" Background="#F3EEFF" Foreground="#7C3AED" BorderBrush="#C4A6FF" Padding="8,4"/>
              </StackPanel>
            </Border>
          </StackPanel>

          <!-- GEOMETRY -->
          <StackPanel x:Name="Panel_Geometry" Visibility="Collapsed">
            <Border Background="#F5F0FF" BorderBrush="#D8C0FF" BorderThickness="0,0,0,1" Padding="28,18,28,14">
              <StackPanel>
                <TextBlock Text="Geometry Forms" FontSize="14" FontWeight="SemiBold" Foreground="#6D28D9"/>
                <TextBlock Text="Solid geometry ranked by face count. Check elements to preview the score impact in the stats strip before deleting. Geometry deletion is permanent - use Undo immediately if needed. Constrained geometry will be skipped." FontSize="12" Foreground="#555F6D" Margin="0,4,0,0" TextWrapping="Wrap"/>
              </StackPanel>
            </Border>
            <StackPanel Margin="28,16,28,16">
              <Border Background="#F6F8FA" BorderBrush="#D0D7DE" BorderThickness="1" CornerRadius="6" Padding="16,12" Margin="0,0,0,12">
                <UniformGrid Columns="5">
                  <StackPanel HorizontalAlignment="Center"><TextBlock Text="FACES"        Foreground="#555F6D" FontSize="9" FontWeight="SemiBold" TextAlignment="Center"/><TextBlock x:Name="LblF"  Foreground="#58A6FF" FontSize="22" FontWeight="Bold" FontFamily="Consolas" TextAlignment="Center"/></StackPanel>
                  <StackPanel HorizontalAlignment="Center"><TextBlock Text="SOLIDS"       Foreground="#555F6D" FontSize="9" FontWeight="SemiBold" TextAlignment="Center"/><TextBlock x:Name="LblS"  Foreground="#58A6FF" FontSize="22" FontWeight="Bold" FontFamily="Consolas" TextAlignment="Center"/></StackPanel>
                  <StackPanel HorizontalAlignment="Center"><TextBlock Text="EDGES"        Foreground="#555F6D" FontSize="9" FontWeight="SemiBold" TextAlignment="Center"/><TextBlock x:Name="LblE"  Foreground="#58A6FF" FontSize="22" FontWeight="Bold" FontFamily="Consolas" TextAlignment="Center"/></StackPanel>
                  <StackPanel HorizontalAlignment="Center"><TextBlock Text="GEO SCORE"   Foreground="#555F6D" FontSize="9" FontWeight="SemiBold" TextAlignment="Center"/><TextBlock x:Name="LblGS" Foreground="#F0883E" FontSize="22" FontWeight="Bold" FontFamily="Consolas" TextAlignment="Center"/></StackPanel>
                  <StackPanel HorizontalAlignment="Center"><TextBlock Text="AFTER DELETE" Foreground="#555F6D" FontSize="9" FontWeight="SemiBold" TextAlignment="Center"/><TextBlock x:Name="LblGA" Foreground="#3FB950" FontSize="22" FontWeight="Bold" FontFamily="Consolas" TextAlignment="Center"/></StackPanel>
                </UniformGrid>
              </Border>
              <DataGrid x:Name="GeoGrid" Height="260" AutoGenerateColumns="False" CanUserAddRows="False" CanUserDeleteRows="False" CanUserResizeRows="False" IsReadOnly="False">
                <DataGrid.Columns>
                  <DataGridTemplateColumn Header="" Width="32" CanUserResize="False"><DataGridTemplateColumn.CellTemplate><DataTemplate><CheckBox IsChecked="{Binding Selected, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}" HorizontalAlignment="Center" VerticalAlignment="Center"/></DataTemplate></DataGridTemplateColumn.CellTemplate></DataGridTemplateColumn>
                  <DataGridTextColumn Header="Type"      Binding="{Binding EType}"  Width="140" IsReadOnly="True"/>
                  <DataGridTextColumn Header="Name / Id" Binding="{Binding EName}"  Width="160" IsReadOnly="True"/>
                  <DataGridTextColumn Header="Faces"     Binding="{Binding Faces}"  Width="58"  IsReadOnly="True"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="FontFamily" Value="Consolas"/><Setter Property="HorizontalAlignment" Value="Center"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                  <DataGridTextColumn Header="Solids"    Binding="{Binding Solids}" Width="58"  IsReadOnly="True"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="FontFamily" Value="Consolas"/><Setter Property="HorizontalAlignment" Value="Center"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                  <DataGridTextColumn Header="Edges"     Binding="{Binding Edges}"  Width="58"  IsReadOnly="True"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="FontFamily" Value="Consolas"/><Setter Property="HorizontalAlignment" Value="Center"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                  <DataGridTextColumn Header="% Total"   Binding="{Binding Pct}"    Width="68"  IsReadOnly="True"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="Foreground" Value="#555F6D"/><Setter Property="HorizontalAlignment" Value="Center"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                  <DataGridTextColumn Header="Gain if Removed" Binding="{Binding Impact}" Width="*" IsReadOnly="True"><DataGridTextColumn.ElementStyle><Style TargetType="TextBlock"><Setter Property="Foreground" Value="#3FB950"/><Setter Property="FontFamily" Value="Consolas"/></Style></DataGridTextColumn.ElementStyle></DataGridTextColumn>
                </DataGrid.Columns>
              </DataGrid>
            </StackPanel>
            <Border Padding="28,10" Background="#FAFAFA" BorderBrush="#E8EBEF" BorderThickness="0,1,0,0">
              <StackPanel Orientation="Horizontal">
                <Button x:Name="BtnGA" Content="Select All" Margin="0,0,6,0"/>
                <Button x:Name="BtnGC" Content="Clear"      Margin="0,0,12,0"/>
                <Button x:Name="BtnGD" Content="Delete Selected Forms" Style="{StaticResource DangerBtn}" Margin="0,0,12,0"/>
                <TextBlock x:Name="GeoStatus" Foreground="#16803A" FontSize="11" VerticalAlignment="Center" Margin="0,0,12,0"/>
                <Button x:Name="BtnUndoGeo" Content="&#8617; Undo" Visibility="Collapsed" Background="#F3EEFF" Foreground="#7C3AED" BorderBrush="#C4A6FF" Padding="8,4"/>
              </StackPanel>
            </Border>
          </StackPanel>

        </StackPanel>
      </ScrollViewer>
    </Grid>
  </Grid>
</Window>
"""

# â”€â”€ MAIN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if not doc.IsFamilyDocument:
    from Microsoft.Win32 import OpenFileDialog
    _dlg = OpenFileDialog()
    _dlg.Title = "Select a Revit Family to Optimize"
    _dlg.Filter = "Revit Family (*.rfa)|*.rfa"
    _dlg.DefaultExt = ".rfa"
    if _dlg.ShowDialog():
        try:
            _uid = __revit__.OpenAndActivateDocument(_dlg.FileName)
            _opened = _uid.Document if _uid else None
            if _opened is not None:
                doc = _opened
        except Exception as _ex:
            from pyrevit import forms
            forms.alert("Could not open family:\n{}".format(str(_ex)[:120]))


# ── OPTIMIZER RUNNER ─────────────────────────────────────────────────────────
def _run_optimizer(target_doc):
    global doc
    doc = target_doc
    _next = [None]  # stores nested family doc to open after window closes

    try: nbytes=os.path.getsize(doc.PathName) if doc.PathName else 0
    except: nbytes=0
    sz=nbytes/1000000.0
    n_cad=len(list(FilteredElementCollector(doc).OfClass(ImportInstance).ToElements()))
    all_rp=list(FilteredElementCollector(doc).OfClass(ReferencePlane).ToElements())
    n_rp=sum(1 for rp in all_rp if (rp.Name or "").strip().lower() in ("reference plane",""))
    try:
        from Autodesk.Revit.DB import RasterImage
        n_img=len(list(FilteredElementCollector(doc).OfClass(RasterImage).ToElements()))
    except: n_img=0
    n_nest=len(list(FilteredElementCollector(doc).OfClass(Family).ToElements()))
    n_grp=len(list(FilteredElementCollector(doc).OfClass(Group).ToElements()))
    n_s,n_f,n_e=_total_geom()
    n_tp,n_sh,n_fp,ut,ui,ush=_collect_params()
    n_ut=len(ut); n_ui=len(ui)
    cur=_final(sz,n_cad,n_img,n_nest,n_grp,n_rp,n_ut,n_ui,n_tp,n_sh,n_fp,n_f,n_s,n_e)
    pot=_final(sz,0,0,n_nest,0,0,0,0,max(0,n_tp-n_ut-n_ui),n_sh,n_fp,n_f,n_s,n_e)
    ar=[]
    sn,sm=contrib(sz,0,1,1.25)
    ar.append(AttrRow("File Size","{:.2f} MB".format(sz),"Purge",sn,sm,"Run Purge Unused"))
    sn,sm=contrib(n_cad,0,10,1.25)
    try: cl="; ".join(el.Category.Name if el.Category else "CAD" for el in FilteredElementCollector(doc).OfClass(ImportInstance).ToElements())
    except: cl=""
    ar.append(AttrRow("Imported CAD",n_cad,0,sn,sm,cl or "---"))
    sn,sm=contrib(n_img,0,10,0.5)
    ar.append(AttrRow("Raster Images",n_img,0,sn,sm,"Delete all images" if n_img else "---"))
    sn,sm=contrib(n_grp,0,5,0.75)
    ar.append(AttrRow("Model Groups",n_grp,0,sn,sm,"Ungroup all" if n_grp else "---"))
    sn,sm=contrib(n_rp,0,1,0.5)
    rp_names=[rp.Name for rp in all_rp if (rp.Name or "").strip().lower() in ("reference plane","")]
    ar.append(AttrRow("Unnamed Ref Planes",n_rp,0,sn,sm,("; ".join(rp_names[:5])) if rp_names else "---"))
    sn,sm=contrib(n_ut,0,2,0.75)
    ar.append(AttrRow("Unused Type Params",n_ut,0,sn,sm,(", ".join(ut[:8])+(" ..." if len(ut)>8 else "")) if ut else "---"))
    sn,sm=contrib(n_ui,0,2,0.75)
    ar.append(AttrRow("Unused Inst Params",n_ui,0,sn,sm,(", ".join(ui[:8])+(" ..." if len(ui)>8 else "")) if ui else "---"))
    sn,sm=contrib(len(ush),0,2,0.5)
    ar.append(AttrRow("Unused Shared Params",len(ush),0,sn,sm,(", ".join(ush[:6])) if ush else "---"))
    tp2=max(0,n_tp-n_ut-n_ui)
    sn2=max(0.,10-n_tp//2)*0.5; sm2=max(0.,10-tp2//2)*0.5
    ar.append(AttrRow("Total Params",n_tp,tp2,sn2,sm2,"Remove {} unused".format(n_ut+n_ui) if (n_ut+n_ui) else "---"))
    sn=max(0.,10-n_sh*2)*0.5
    ar.append(AttrRow("Shared Params",n_sh,"---",sn,sn,"Needed for schedules/tags"))
    sn=max(0.,10-n_fp*2)*0.75
    ar.append(AttrRow("Formula Params",n_fp,"---",sn,sn,"Formulas are healthy"))
    geo_s=_blended(n_f,n_s,n_e)*1.25
    ar.append(AttrRow("Blended Geo Score",n_f,"---",geo_s,geo_s,"See Geometry section"))
    sn=max(0.,10-n_nest)*1.25
    ar.append(AttrRow("Nested Families",n_nest,"---",sn,sn,"See Nested Families section"))
    geo_rows=_scan_forms(n_f,n_s,n_e)
    req_rows=_collect_req_params()
    nest_rows=_collect_nested()
    subcat_rows=_collect_subcats()
    rp_rows=_collect_rp_full()
    view_rows=_collect_views()
    type_rows=_collect_types()
    window=XamlReader.Parse(XAML)
    window.FindName("SubTitle").Text=u"{} . {} types . {} nested . {} geo forms".format(
        doc.Title, len(type_rows), len(nest_rows), len(geo_rows))
    window.FindName("ScoreCurrent").Text="{:.1f}".format(cur)
    window.FindName("ScorePotential").Text="{:.1f}".format(pot)
    gv=pot-cur
    window.FindName("ScoreGain").Text="+{:.1f}".format(gv) if gv>0 else "0"
    window.FindName("LblF").Text=str(n_f); window.FindName("LblS").Text=str(n_s)
    window.FindName("LblE").Text=str(n_e); window.FindName("LblGS").Text="{:.2f}".format(geo_s)
    window.FindName("LblGA").Text="---"
    a_items=ObservableCollection[object]()
    for r in ar: a_items.Add(r)
    window.FindName("AttrGrid").ItemsSource=a_items
    g_items=ObservableCollection[object]()
    for r in geo_rows: g_items.Add(r)
    gg=window.FindName("GeoGrid"); gg.ItemsSource=g_items
    req_items=ObservableCollection[object]()
    for r in req_rows: req_items.Add(r)
    window.FindName("ReqGrid").ItemsSource=req_items
    nest_items=ObservableCollection[object]()
    for r in nest_rows: nest_items.Add(r)
    window.FindName("NestGrid").ItemsSource=nest_items
    subcat_items=ObservableCollection[object]()
    for r in subcat_rows: subcat_items.Add(r)
    window.FindName("SubcatGrid").ItemsSource=subcat_items
    rp_items=ObservableCollection[object]()
    for r in rp_rows: rp_items.Add(r)
    window.FindName("RPGrid").ItemsSource=rp_items
    view_items=ObservableCollection[object]()
    for r in view_rows: view_items.Add(r)
    window.FindName("ViewGrid").ItemsSource=view_items
    type_items=ObservableCollection[object]()
    for r in type_rows: type_items.Add(r)
    window.FindName("TypeGrid").ItemsSource=type_items
    dl=[]
    if ut: dl.append("UNUSED TYPE ({}):\n  {}".format(len(ut),"\n  ".join(ut)))
    if ui: dl.append("UNUSED INST ({}):\n  {}".format(len(ui),"\n  ".join(ui)))
    if ush: dl.append("UNUSED SHARED ({}):\n  {}".format(len(ush),"\n  ".join(ush)))
    window.FindName("DetailText").Text="\n\n".join(dl) if dl else "No unused parameters found."
    n_fix=sum(1 for r in a_items if r.HasGain)
    window.FindName("NavBadge_Overview").Text="  {} fixable".format(n_fix) if n_fix else "  All good"
    n_file=n_cad+n_img+n_grp
    window.FindName("NavBadge_File").Text="  {} items".format(n_file) if n_file else "  Clean"
    n_pu=n_ut+n_ui
    window.FindName("NavBadge_Params").Text="  {} unused".format(n_pu) if n_pu else "  Clean"
    n_req=sum(1 for r in req_items if r.HasIssue)
    window.FindName("NavBadge_ReqParams").Text="  {} empty".format(n_req) if n_req else "  Filled"
    n_rpu=sum(1 for r in rp_items if r.Status=="Unnamed")
    window.FindName("NavBadge_RefPlanes").Text="  {} unnamed".format(n_rpu) if n_rpu else "  Named"
    n_unp=sum(1 for r in nest_items if r.InstanceCount==0)
    window.FindName("NavBadge_Nested").Text="  {} unplaced".format(n_unp) if n_unp else "  All placed"
    n_su=sum(1 for r in subcat_items if not r._has_geo)
    window.FindName("NavBadge_Subcats").Text="  {} unused".format(n_su) if n_su else "  Clean"
    window.FindName("NavBadge_Types").Text="  {} types".format(len(list(type_items)))
    n_ve=sum(1 for r in view_items if r.CanDelete)
    window.FindName("NavBadge_Views").Text="  {} extra".format(n_ve) if n_ve else "  Default"
    window.FindName("NavBadge_Geometry").Text="  {} faces".format(n_f)
    from System.Windows import Visibility as WVis
    PANELS=["Panel_Overview","Panel_File","Panel_Params","Panel_ReqParams",
            "Panel_RefPlanes","Panel_Nested","Panel_Subcats","Panel_Types",
            "Panel_Views","Panel_Geometry"]
    def on_nav(s,e):
        idx=window.FindName("NavList").SelectedIndex
        for i,nm in enumerate(PANELS):
            p=window.FindName(nm)
            if p: p.Visibility=WVis.Visible if i==idx else WVis.Collapsed
    window.FindName("NavList").SelectionChanged+=on_nav
    def _post_undo():
        try:
            from Autodesk.Revit.UI import PostableCommand, RevitCommandId
            undo_id=RevitCommandId.LookupPostableCommandId(PostableCommand.Undo)
            __revit__.PostCommand(undo_id); return True
        except: return False
    def _make_undo_btn(btn_name,status_name):
        btn=window.FindName(btn_name)
        if btn: btn.Visibility=WVis.Visible
        def _do(s,e):
            ok=_post_undo()
            st=window.FindName(status_name)
            if st: st.Text="Undo posted. Close this dialog then check Revit." if ok else "Use Ctrl+Z in Revit."
            if btn: btn.Visibility=WVis.Collapsed
        if btn: btn.Click+=_do
    def _update_row(attr,cur2,min2,per,w):
        sn2,sm2=contrib(cur2,min2,per,w)
        for r in a_items:
            if r.Attr==attr:
                r.Current=str(cur2); r.Min=str(min2)
                try: d=cur2-min2; r.ReduceBy=str(d) if d>0 else "---"
                except: r.ReduceBy="---"
                r.ScoreNow="{:.1f}".format(sn2); r.ScoreAfter="{:.1f}".format(sm2)
                g2=sm2-sn2; r.Gain="+{:.1f}".format(g2) if g2>0.05 else "---"
                r.HasGain=g2>0.05
        window.FindName("AttrGrid").Items.Refresh()
    def _refresh_params():
        _,_,_,ut2,ui2,ush2=_collect_params()
        _update_row("Unused Type Params",len(ut2),0,2,0.75)
        _update_row("Unused Inst Params",len(ui2),0,2,0.75)
        _update_row("Unused Shared Params",len(ush2),0,2,0.5)
        dl2=[]
        if ut2: dl2.append("UNUSED TYPE ({}):\n  {}".format(len(ut2),"\n  ".join(ut2)))
        if ui2: dl2.append("UNUSED INST ({}):\n  {}".format(len(ui2),"\n  ".join(ui2)))
        if ush2: dl2.append("UNUSED SHARED ({}):\n  {}".format(len(ush2),"\n  ".join(ush2)))
        window.FindName("DetailText").Text="\n\n".join(dl2) if dl2 else "No unused parameters found."
        n2=len(ut2)+len(ui2)
        window.FindName("NavBadge_Params").Text="  {} unused".format(n2) if n2 else "  Clean"
    def do_purge(s,e):
        if not _confirm("Purge Unused","Launch Revit's built-in Purge Unused?\nRevit will open its own dialog."): return
        try:
            from Autodesk.Revit.UI import PostableCommand, RevitCommandId
            __revit__.PostCommand(RevitCommandId.LookupPostableCommandId(PostableCommand.PurgeUnused))
            window.FindName("PerfStatus").Text="Purge Unused launched."
        except Exception as ex: window.FindName("PerfStatus").Text="Error: {}".format(str(ex)[:80])
    def do_del_cad(s,e):
        els=list(FilteredElementCollector(doc).OfClass(ImportInstance).ToElements())
        if not els: window.FindName("PerfStatus").Text="No CAD imports."; return
        if not _confirm("Delete CAD Imports","Delete {} CAD import(s)?".format(len(els))): return
        n=0
        for el in els:
            try:
                with Transaction(doc,"Delete CAD Imports") as t: t.Start(); doc.Delete(el.Id); t.Commit(); n+=1
            except: pass
        _update_row("Imported CAD",0,0,10,1.25)
        window.FindName("PerfStatus").Text="Deleted {} CAD import(s).".format(n)
        _make_undo_btn("BtnUndoPerf","PerfStatus"); _refresh_btn_states()
    def do_del_images(s,e):
        try:
            from Autodesk.Revit.DB import RasterImage
            els=list(FilteredElementCollector(doc).OfClass(RasterImage).ToElements())
        except: els=[]
        if not els: window.FindName("PerfStatus").Text="No raster images."; return
        if not _confirm("Delete Raster Images","Delete {} embedded image(s)?".format(len(els))): return
        n=0
        for el in els:
            try:
                with Transaction(doc,"Delete Raster Images") as t: t.Start(); doc.Delete(el.Id); t.Commit(); n+=1
            except: pass
        _update_row("Raster Images",0,0,10,0.5)
        window.FindName("PerfStatus").Text="Deleted {} image(s).".format(n)
        _make_undo_btn("BtnUndoPerf","PerfStatus"); _refresh_btn_states()
    def do_ungroup(s,e):
        grps=list(FilteredElementCollector(doc).OfClass(Group).ToElements())
        if not grps: window.FindName("PerfStatus").Text="No groups."; return
        if not _confirm("Ungroup All","Ungroup {} model group(s)?".format(len(grps))): return
        n=0
        for grp in grps:
            try:
                with Transaction(doc,"Ungroup All Groups") as t: t.Start(); grp.UngroupMembers(); t.Commit(); n+=1
            except: pass
        _update_row("Model Groups",0,0,5,0.75)
        window.FindName("PerfStatus").Text="Ungrouped {} group(s).".format(n)
        _make_undo_btn("BtnUndoPerf","PerfStatus"); _refresh_btn_states()
    def _del_by_names(names,label,status_key):
        if not names: window.FindName(status_key).Text="No {} to delete.".format(label); return
        if not _confirm("Delete Params","Delete {} {}?\n\nParams:\n{}".format(
                len(names),label,"\n".join(names[:10])+("\n..." if len(names)>10 else ""))): return
        fm=doc.FamilyManager; n=0
        with Transaction(doc,"Delete "+label) as t:
            t.Start()
            for p in list(fm.Parameters):
                if p.Definition.Name in names:
                    try: fm.RemoveParameter(p); n+=1
                    except: pass
            t.Commit()
        _refresh_params()
        window.FindName(status_key).Text="Deleted {}.".format(n)
        _make_undo_btn("BtnUndoParam","ParamStatus"); _refresh_btn_states()
    def do_del_type(s,e):
        _,_,_,ut2,_,_=_collect_params(); _del_by_names(ut2,"unused type params","ParamStatus")
    def do_del_inst(s,e):
        _,_,_,_,ui2,_=_collect_params(); _del_by_names(ui2,"unused inst params","ParamStatus")
    def do_del_shared(s,e):
        _,_,_,_,_,ush2=_collect_params(); _del_by_names(ush2,"unused shared params","ParamStatus")
    def do_apply_req(s,e):
        fm=doc.FamilyManager
        all_p={p.Definition.Name: p for p in fm.Parameters}
        applied=skipped=0
        with Transaction(doc,"Apply Required Params") as t:
            t.Start()
            for row in req_items:
                if not row._exists: skipped+=1; continue
                p=all_p.get(row.Name)
                if p is None: skipped+=1; continue
                val=(row.Value or "").strip()
                for ft in fm.Types:
                    try: fm.CurrentType=ft; fm.Set(p,val); applied+=1
                    except: pass
            t.Commit()
        new_rows=_collect_req_params()
        req_items.Clear()
        for r in new_rows: req_items.Add(r)
        window.FindName("ReqGrid").Items.Refresh()
        n_req2=sum(1 for r in req_items if r.HasIssue)
        window.FindName("NavBadge_ReqParams").Text="  {} empty".format(n_req2) if n_req2 else "  Filled"
        msg="Applied to {} type/param combinations.".format(applied)
        if skipped: msg+=" {} skipped.".format(skipped)
        window.FindName("ReqStatus").Text=msg
    def do_rename_rp(s,e):
        changes=[(r.ElemId,r.Name) for r in rp_items if r.Name!=r.OriginalName]
        if not changes: window.FindName("RPStatus").Text="No name changes to apply."; return
        n=0
        for eid,new_name in changes:
            try:
                rp=doc.GetElement(ElementId(eid))
                with Transaction(doc,"Rename Ref Plane") as t: t.Start(); rp.Name=new_name; t.Commit(); n+=1
            except: pass
        rp_items.Clear()
        for r in _collect_rp_full(): rp_items.Add(r)
        window.FindName("RPGrid").Items.Refresh()
        n_rpu2=sum(1 for r in rp_items if r.Status=="Unnamed")
        _update_row("Unnamed Ref Planes",n_rpu2,0,1,0.5)
        window.FindName("NavBadge_RefPlanes").Text="  {} unnamed".format(n_rpu2) if n_rpu2 else "  Named"
        window.FindName("RPStatus").Text="Renamed {}.".format(n)
    def do_del_sel_rp(s,e):
        sel=[r for r in rp_items if r.Selected]
        if not sel: window.FindName("RPStatus").Text="Nothing selected."; return
        if not _confirm("Delete Reference Planes","Delete {} selected reference plane(s)?\nPlanes in use will be skipped.".format(len(sel))): return
        deleted=blocked=0
        for row in sel:
            try:
                with Transaction(doc,"Delete Ref Plane") as t: t.Start(); doc.Delete(ElementId(row.ElemId)); t.Commit(); deleted+=1
            except: blocked+=1
        rp_items.Clear()
        for r in _collect_rp_full(): rp_items.Add(r)
        window.FindName("RPGrid").Items.Refresh()
        n_rpu2=sum(1 for r in rp_items if r.Status=="Unnamed")
        _update_row("Unnamed Ref Planes",n_rpu2,0,1,0.5)
        msg="Deleted {}.".format(deleted)
        if blocked: msg+=" {} blocked (in use).".format(blocked)
        window.FindName("RPStatus").Text=msg
        _make_undo_btn("BtnUndoRP","RPStatus"); _refresh_btn_states()
    def do_purge_nest(s,e):
        to_purge=[r for r in nest_items if r.InstanceCount==0]
        if not to_purge: window.FindName("NestStatus").Text="No unplaced nested families."; return
        names="\n".join(r.FamilyName for r in to_purge[:8])
        if len(to_purge)>8: names+="\n..."
        if not _confirm("Purge Unplaced","Remove {} unplaced nested families?\n\n{}".format(len(to_purge),names)): return
        deleted=blocked=0
        for row in to_purge:
            try:
                with Transaction(doc,"Purge Nested Family") as t: t.Start(); doc.Delete(ElementId(row.FamId)); t.Commit(); deleted+=1
            except: blocked+=1
        nest_items.Clear()
        for r in _collect_nested(): nest_items.Add(r)
        window.FindName("NestGrid").Items.Refresh()
        n_unp2=sum(1 for r in nest_items if r.InstanceCount==0)
        window.FindName("NavBadge_Nested").Text="  {} unplaced".format(n_unp2) if n_unp2 else "  All placed"
        msg="Removed {}.".format(deleted)
        if blocked: msg+=" {} blocked.".format(blocked)
        window.FindName("NestStatus").Text=msg
        _make_undo_btn("BtnUndoNest","NestStatus"); _refresh_btn_states()
    def do_del_subcat(s,e):
        to_del=[r for r in subcat_items if not r._has_geo]
        if not to_del: window.FindName("SubcatStatus").Text="No unused subcategories."; return
        if not _confirm("Delete Subcategories","Delete {} unused subcategories?".format(len(to_del))): return
        deleted=blocked=0
        for row in to_del:
            try:
                with Transaction(doc,"Delete Subcategory") as t: t.Start(); doc.Delete(ElementId(row.SubcatId)); t.Commit(); deleted+=1
            except: blocked+=1
        subcat_items.Clear()
        for r in _collect_subcats(): subcat_items.Add(r)
        window.FindName("SubcatGrid").Items.Refresh()
        msg="Deleted {}.".format(deleted)
        if blocked: msg+=" {} blocked.".format(blocked)
        window.FindName("SubcatStatus").Text=msg
        _make_undo_btn("BtnUndoSubcat","SubcatStatus")
    def do_del_types(s,e):
        sel=[r for r in type_items if r.Selected]
        if not sel: window.FindName("TypeStatus").Text="Nothing selected."; return
        fm=doc.FamilyManager
        if len(list(fm.Types))-len(sel)<1:
            window.FindName("TypeStatus").Text="Cannot delete all types."; return
        names_to_del=set(r.TypeName for r in sel)
        if not _confirm("Delete Types","Delete {} type(s)?\n\n{}".format(len(sel),"\n".join(list(names_to_del)[:8]))): return
        deleted=blocked=0
        with Transaction(doc,"Delete Family Types") as t:
            t.Start()
            for ft in list(fm.Types):
                if (ft.Name or "(Default)") in names_to_del:
                    try: fm.CurrentType=ft; fm.DeleteCurrentType(); deleted+=1
                    except: blocked+=1
            t.Commit()
        type_items.Clear()
        for r in _collect_types(): type_items.Add(r)
        window.FindName("TypeGrid").Items.Refresh()
        window.FindName("NavBadge_Types").Text="  {} types".format(len(list(type_items)))
        msg="Deleted {}.".format(deleted)
        if blocked: msg+=" {} blocked.".format(blocked)
        window.FindName("TypeStatus").Text=msg
        _make_undo_btn("BtnUndoTypes","TypeStatus"); _refresh_btn_states()
    def do_del_views(s,e):
        sel=[r for r in view_items if r.Selected]
        if not sel: window.FindName("ViewStatus").Text="Nothing selected."; return
        non_default=[r for r in sel if r.CanDelete]
        if not non_default: window.FindName("ViewStatus").Text="All selected are defaults."; return
        if not _confirm("Delete Views","Delete {} view(s)? Default views will be skipped.".format(len(non_default))): return
        deleted=blocked=0
        for row in non_default:
            try:
                with Transaction(doc,"Delete View") as t: t.Start(); doc.Delete(ElementId(row.ElemId)); t.Commit(); deleted+=1
            except: blocked+=1
        view_items.Clear()
        for r in _collect_views(): view_items.Add(r)
        window.FindName("ViewGrid").Items.Refresh()
        n_ve2=sum(1 for r in view_items if r.CanDelete)
        window.FindName("NavBadge_Views").Text="  {} extra".format(n_ve2) if n_ve2 else "  Default"
        msg="Deleted {}.".format(deleted)
        if blocked: msg+=" {} blocked.".format(blocked)
        window.FindName("ViewStatus").Text=msg
        _make_undo_btn("BtnUndoViews","ViewStatus")
    def _geo_preview(s=None,e=None):
        sel=[r for r in g_items if r.Selected]
        if not sel: window.FindName("LblGA").Text="---"; return
        rf=sum(r.Faces for r in sel); rs=sum(r.Solids for r in sel); re=sum(r.Edges for r in sel)
        window.FindName("LblGA").Text="{:.2f}".format(
            _blended(max(0,n_f-rf),max(0,n_s-rs),max(0,n_e-re))*1.25)
    gg.CellEditEnding+=lambda s,e: _geo_preview()
    def geo_all(s,e):
        for r in g_items: r.Selected=True
        gg.Items.Refresh(); _geo_preview()
    def geo_clear(s,e):
        for r in g_items: r.Selected=False
        gg.Items.Refresh(); window.FindName("LblGA").Text="---"
    def geo_delete(s,e):
        sel=[r for r in g_items if r.Selected]
        if not sel: window.FindName("GeoStatus").Text="Nothing selected."; return
        if not _confirm("Delete Geometry","Delete {} selected form(s)? This is permanent.".format(len(sel))): return
        deleted=blocked=0
        for row in sel:
            try:
                with Transaction(doc,"Delete Geo") as t:
                    t.Start()
                    from Autodesk.Revit.DB import ElementId as EId
                    doc.Delete(EId(row.ElemId)); t.Commit(); deleted+=1
            except: blocked+=1
        nf2,ns2,ne2=_total_geom()
        window.FindName("LblF").Text=str(nf2); window.FindName("LblS").Text=str(ns2)
        window.FindName("LblE").Text=str(ne2)
        gs2=_blended(nf2,ns2,ne2)*1.25
        window.FindName("LblGS").Text="{:.2f}".format(gs2); window.FindName("LblGA").Text="---"
        for r in a_items:
            if r.Attr=="Blended Geo Score":
                r.Current=str(nf2); r.ScoreNow="{:.1f}".format(gs2); r.ScoreAfter="{:.1f}".format(gs2)
        window.FindName("AttrGrid").Items.Refresh()
        ng=_scan_forms(nf2,ns2,ne2); g_items.Clear()
        for r in ng: g_items.Add(r)
        gg.Items.Refresh()
        window.FindName("NavBadge_Geometry").Text="  {} faces".format(nf2)
        msg="Deleted {} form(s).".format(deleted)
        if blocked: msg+=" {} blocked (constrained).".format(blocked)
        window.FindName("GeoStatus").Text=msg
        _make_undo_btn("BtnUndoGeo","GeoStatus"); _refresh_btn_states()
    window.FindName("BtnPurge").Click      += do_purge
    window.FindName("BtnDelCAD").Click     += do_del_cad
    window.FindName("BtnDelImages").Click  += do_del_images
    window.FindName("BtnUngroup").Click    += do_ungroup
    window.FindName("BtnDelType").Click    += do_del_type
    window.FindName("BtnDelInst").Click    += do_del_inst
    window.FindName("BtnDelShared").Click  += do_del_shared
    window.FindName("BtnApplyReq").Click   += do_apply_req
    window.FindName("BtnRenameRP").Click   += do_rename_rp
    window.FindName("BtnDelSelRP").Click   += do_del_sel_rp
    
    def on_rp_row_click(s, e):
        row = window.FindName("RPGrid").SelectedItem
        if row is None: return
        try:
            uid = __revit__.ActiveUIDocument
            if uid is None or not uid.Document.Equals(doc): return
            from System.Collections.Generic import List as CsList
            ids = CsList[ElementId]()
            ids.Add(ElementId(row.ElemId))
            uid.Selection.SetElementIds(ids)
        except: pass
    window.FindName("RPGrid").SelectionChanged += on_rp_row_click
    window.FindName("BtnPurgeNest").Click  += do_purge_nest

    def on_nest_select(s, e):
        row = window.FindName("NestGrid").SelectedItem
        window.FindName("BtnOpenNested").IsEnabled = (row is not None)
        if row is None or row.InstanceCount == 0: return
        try:
            uid = __revit__.ActiveUIDocument
            if uid is None or not uid.Document.Equals(doc): return
            fam = doc.GetElement(ElementId(row.FamId))
            from System.Collections.Generic import List as CsList
            ids = CsList[ElementId]()
            for sym_id in fam.GetFamilySymbolIds():
                for inst in FilteredElementCollector(doc).OfClass(FamilyInstance).ToElements():
                    try:
                        if inst.GetTypeId() == sym_id: ids.Add(inst.Id)
                    except: pass
            if ids.Count > 0:
                uid.Selection.SetElementIds(ids)
        except: pass
    window.FindName("NestGrid").SelectionChanged += on_nest_select

    def do_open_nested(s, e):
        row = window.FindName("NestGrid").SelectedItem
        if row is None: return
        fam_path = ""
        fam_file = row.FamilyName + ".rfa"
        cat       = row.Category or ""

        # 1. Try PathName (instant when families retain source path)
        try:
            fam = doc.GetElement(ElementId(row.FamId))
            try:
                p = fam.PathName
                if p and os.path.exists(p): fam_path = p
            except: pass
        except: pass

        # 2. Direct path guesses — os.listdir + os.path.exists only (no walking)
        if not fam_path and doc.PathName:
            try:
                cur_dir = os.path.dirname(doc.PathName)   # e.g. ..\Air Terminals
                stage   = os.path.dirname(cur_dir)         # e.g. ..\2_GUARDIAN PASS
                conf    = os.path.dirname(stage)           # e.g. ..\Content Conformance

                candidates = [
                    os.path.join(cur_dir, fam_file),        # same folder as current family
                    os.path.join(stage,   cat, fam_file),   # stage / Category / name
                    os.path.join(stage,   fam_file),        # directly in stage root
                    os.path.join(conf,    cat, fam_file),   # conf / Category / name
                ]
                # Check every direct subfolder of stage (one listdir call, no recursion)
                try:
                    for _sub in os.listdir(stage):
                        candidates.append(os.path.join(stage, _sub, fam_file))
                except: pass
                # Check every direct subfolder of conf (covers sibling stages)
                try:
                    for _sub in os.listdir(conf):
                        candidates.append(os.path.join(conf, _sub, cat, fam_file))
                        candidates.append(os.path.join(conf, _sub, fam_file))
                except: pass

                for _p in candidates:
                    if os.path.exists(_p):
                        fam_path = _p; break
            except: pass

        if fam_path and os.path.exists(fam_path):
            try:
                _uid = __revit__.OpenAndActivateDocument(fam_path)
                nested = _uid.Document if _uid else None
                if nested and nested.IsFamilyDocument:
                    global doc
                    _saved_doc = doc
                    _run_optimizer(nested)
                    doc = _saved_doc
                    return
            except Exception as _ex:
                window.FindName("NestStatus").Text = "Cannot open: {}".format(str(_ex)[:80])
        else:
            window.FindName("NestStatus").Text = "Not found: {}".format(fam_file)
    window.FindName("BtnOpenNested").Click += do_open_nested

    window.FindName("BtnDelSubcat").Click  += do_del_subcat
    window.FindName("BtnDelTypes").Click   += do_del_types
    window.FindName("BtnDelViews").Click   += do_del_views
    window.FindName("BtnGA").Click         += geo_all
    window.FindName("BtnGC").Click         += geo_clear
    window.FindName("BtnGD").Click         += geo_delete
    def do_open_other(s, e):
        from Microsoft.Win32 import OpenFileDialog as _OFD
        _dlg = _OFD()
        _dlg.Title  = "Select a Revit Family to Optimize"
        _dlg.Filter = "Revit Family (*.rfa)|*.rfa"
        _dlg.DefaultExt = ".rfa"
        if _dlg.ShowDialog():
            try:
                _uid = __revit__.OpenAndActivateDocument(_dlg.FileName)
                _nd  = _uid.Document if _uid else None
                if _nd and _nd.IsFamilyDocument:
                    _next[0] = _nd
                    window.Close()
            except Exception as _ex:
                pass
    window.FindName("BtnOpenOther").Click   += do_open_other
    window.FindName("BtnClose").Click       += lambda s,e: window.Close()
    def _refresh_btn_states():
        _,_,_,ut2,ui2,ush2=_collect_params()
        cad_now=len(list(FilteredElementCollector(doc).OfClass(ImportInstance).ToElements()))
        try:
            from Autodesk.Revit.DB import RasterImage
            img_now=len(list(FilteredElementCollector(doc).OfClass(RasterImage).ToElements()))
        except: img_now=0
        grp_now=len(list(FilteredElementCollector(doc).OfClass(Group).ToElements()))
        n_unp=sum(1 for r in nest_items if r.InstanceCount==0)
        n_su=sum(1 for r in subcat_items if not r._has_geo)
        window.FindName("BtnDelCAD").IsEnabled     = cad_now > 0
        window.FindName("BtnDelImages").IsEnabled  = img_now > 0
        window.FindName("BtnUngroup").IsEnabled    = grp_now > 0
        window.FindName("BtnDelType").IsEnabled    = len(ut2) > 0
        window.FindName("BtnDelInst").IsEnabled    = len(ui2) > 0
        window.FindName("BtnDelShared").IsEnabled  = len(ush2) > 0
        window.FindName("BtnDelSelRP").IsEnabled   = len(list(rp_items)) > 0
        window.FindName("BtnRenameRP").IsEnabled   = len(list(rp_items)) > 0
        window.FindName("BtnPurgeNest").IsEnabled  = n_unp > 0
        window.FindName("BtnDelSubcat").IsEnabled  = n_su > 0
        window.FindName("BtnDelTypes").IsEnabled   = len(list(type_items)) > 1
        window.FindName("BtnDelViews").IsEnabled   = len(list(view_items)) > 0
        window.FindName("BtnGD").IsEnabled         = len(list(g_items)) > 0
    _refresh_btn_states()
    window.ShowDialog()
    if _next[0]:
        _run_optimizer(_next[0])

if doc.IsFamilyDocument:
    _run_optimizer(doc)
