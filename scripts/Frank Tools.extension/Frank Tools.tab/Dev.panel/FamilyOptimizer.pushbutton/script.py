# -*- coding: utf-8 -*-
__title__   = "Family\nOptimizer"
__doc__     = """Version = 4.0
Date    = 23.06.2026
________________________________________________________________
Description:
Full family health tool — scores every benchmark attribute,
shows gain potential, and lets you fix each one directly.
Tabs: Score | Actions | Geometry
________________________________________________________________
Author: Frank Sun"""

import clr, os
clr.AddReference("RevitAPI"); clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework"); clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from Autodesk.Revit.DB import (
    FilteredElementCollector, ImportInstance, ReferencePlane,
    Family, Group, Dimension, InternalDefinition, BuiltInParameter,
    ViewDetailLevel, Solid, GeometryInstance, Options, Transaction,
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

# ── CONFIRM HELPER ───────────────────────────────────────────────────────────
def _confirm(title, msg):
    from System.Windows import MessageBox, MessageBoxButton, MessageBoxResult
    r = MessageBox.Show(msg, title, MessageBoxButton.YesNo)
    return r == MessageBoxResult.Yes

# ── XAML ──────────────────────────────────────────────────────────────────────
XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Family Optimizer" Width="960" Height="860"
        WindowStartupLocation="CenterScreen"
        Background="#0D1117" FontFamily="Segoe UI" FontSize="12">
  <Window.Resources>

    <!-- ── Base button ── -->
    <Style TargetType="Button">
      <Setter Property="Background"      Value="#21262D"/>
      <Setter Property="Foreground"      Value="#E6EDF3"/>
      <Setter Property="BorderBrush"     Value="#30363D"/>
      <Setter Property="BorderThickness" Value="1"/>
      <Setter Property="Padding"         Value="10,5"/>
      <Setter Property="Cursor"          Value="Hand"/>
      <Setter Property="FontSize"        Value="11"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#30363D"/>
          <Setter Property="BorderBrush" Value="#8B949E"/>
        </Trigger>
        <Trigger Property="IsEnabled" Value="False">
          <Setter Property="Opacity" Value="0.4"/>
        </Trigger>
      </Style.Triggers>
    </Style>

    <!-- ── Action button (amber) ── -->
    <Style x:Key="ActBtn" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Background"  Value="#2D1F0E"/>
      <Setter Property="Foreground"  Value="#F0883E"/>
      <Setter Property="BorderBrush" Value="#4A3010"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#3D2A10"/>
          <Setter Property="BorderBrush" Value="#F0883E"/>
        </Trigger>
      </Style.Triggers>
    </Style>

    <!-- ── Danger button (red) ── -->
    <Style x:Key="DangerBtn" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Background"  Value="#2D1010"/>
      <Setter Property="Foreground"  Value="#F85149"/>
      <Setter Property="BorderBrush" Value="#4A1A1A"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#3D1515"/>
          <Setter Property="BorderBrush" Value="#F85149"/>
        </Trigger>
      </Style.Triggers>
    </Style>

    <!-- ── DataGrid ── -->
    <Style TargetType="DataGrid">
      <Setter Property="Background"               Value="#0D1117"/>
      <Setter Property="Foreground"               Value="#E6EDF3"/>
      <Setter Property="BorderBrush"              Value="#21262D"/>
      <Setter Property="BorderThickness"          Value="1"/>
      <Setter Property="RowBackground"            Value="#0D1117"/>
      <Setter Property="AlternatingRowBackground" Value="#111820"/>
      <Setter Property="HorizontalGridLinesBrush" Value="#161B22"/>
      <Setter Property="VerticalGridLinesBrush"   Value="#161B22"/>
      <Setter Property="ColumnHeaderHeight"       Value="30"/>
      <Setter Property="RowHeight"                Value="28"/>
      <Setter Property="SelectionUnit"            Value="FullRow"/>
    </Style>
    <Style TargetType="DataGridColumnHeader">
      <Setter Property="Background"      Value="#161B22"/>
      <Setter Property="Foreground"      Value="#8B949E"/>
      <Setter Property="FontWeight"      Value="SemiBold"/>
      <Setter Property="FontSize"        Value="11"/>
      <Setter Property="Padding"         Value="10,0"/>
      <Setter Property="BorderBrush"     Value="#21262D"/>
      <Setter Property="BorderThickness" Value="0,0,0,1"/>
    </Style>
    <Style TargetType="DataGridCell">
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Padding"         Value="10,0"/>
      <Setter Property="VerticalContentAlignment" Value="Center"/>
      <Style.Triggers>
        <Trigger Property="IsSelected" Value="True">
          <Setter Property="Background" Value="#1C2333"/>
          <Setter Property="Foreground" Value="#E6EDF3"/>
        </Trigger>
      </Style.Triggers>
    </Style>
    <Style TargetType="DataGridRow">
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#161B22"/>
        </Trigger>
      </Style.Triggers>
    </Style>

    <!-- ── TabControl ── -->
    <Style TargetType="TabControl">
      <Setter Property="Background"   Value="#0D1117"/>
      <Setter Property="BorderBrush"  Value="#21262D"/>
      <Setter Property="BorderThickness" Value="0,1,0,0"/>
      <Setter Property="Padding"      Value="0"/>
    </Style>
    <Style TargetType="TabItem">
      <Setter Property="Background"   Value="Transparent"/>
      <Setter Property="Foreground"   Value="#8B949E"/>
      <Setter Property="BorderBrush"  Value="Transparent"/>
      <Setter Property="BorderThickness" Value="0,0,0,2"/>
      <Setter Property="Padding"      Value="16,8"/>
      <Setter Property="FontSize"     Value="12"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="TabItem">
            <Border x:Name="Border" Padding="{TemplateBinding Padding}"
                    BorderThickness="0,0,0,2" BorderBrush="Transparent"
                    Background="Transparent">
              <ContentPresenter ContentSource="Header"/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsSelected" Value="True">
                <Setter TargetName="Border" Property="BorderBrush" Value="#F0883E"/>
                <Setter Property="Foreground" Value="#E6EDF3"/>
              </Trigger>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter Property="Foreground" Value="#C6D0D9"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>

  </Window.Resources>

  <Grid>
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
    </Grid.RowDefinitions>

    <!-- ══ HEADER ══════════════════════════════════════════════════════════ -->
    <Border Grid.Row="0" Background="#0D1117" Padding="20,14,20,0">
      <Grid>
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="*"/>
          <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <StackPanel Grid.Column="0">
          <TextBlock Text="Family Optimizer"
                     FontSize="18" FontWeight="SemiBold" Foreground="#E6EDF3"/>
          <TextBlock x:Name="SubTitle" FontSize="11" Foreground="#8B949E" Margin="0,2,0,0"/>
        </StackPanel>
        <TextBlock Text="✕ Close" Grid.Column="1" Foreground="#8B949E"
                   VerticalAlignment="Center" Cursor="Hand" FontSize="11"/>
      </Grid>
    </Border>

    <!-- ══ SCORE STRIP ═════════════════════════════════════════════════════ -->
    <Border Grid.Row="1" Background="#161B22" Margin="0,12,0,0"
            BorderBrush="#21262D" BorderThickness="0,1,0,1">
      <Grid Margin="20,0">
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="Auto"/>
          <ColumnDefinition Width="1"/>
          <ColumnDefinition Width="Auto"/>
          <ColumnDefinition Width="1"/>
          <ColumnDefinition Width="Auto"/>
          <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>

        <!-- Current -->
        <StackPanel Grid.Column="0" Orientation="Horizontal" Margin="0,10,32,10">
          <StackPanel VerticalAlignment="Center">
            <TextBlock Text="CURRENT SCORE" Foreground="#8B949E" FontSize="9"
                       FontWeight="SemiBold"/>
            <TextBlock x:Name="ScoreCurrent" Foreground="#F0883E"
                       FontSize="32" FontWeight="Bold" FontFamily="Consolas"
                       LineHeight="34"/>
            <TextBlock Text="/ 100" Foreground="#3A4450" FontSize="12" FontFamily="Consolas"/>
          </StackPanel>
        </StackPanel>

        <Rectangle Grid.Column="1" Fill="#21262D" Width="1"/>

        <!-- Potential -->
        <StackPanel Grid.Column="2" Margin="32,10,32,10">
          <TextBlock Text="POTENTIAL" Foreground="#8B949E" FontSize="9"
                     FontWeight="SemiBold"/>
          <TextBlock x:Name="ScorePotential" Foreground="#3FB950"
                     FontSize="32" FontWeight="Bold" FontFamily="Consolas"
                     LineHeight="34"/>
          <TextBlock Text="/ 100" Foreground="#3A4450" FontSize="12" FontFamily="Consolas"/>
        </StackPanel>

        <Rectangle Grid.Column="3" Fill="#21262D" Width="1"/>

        <!-- Gain -->
        <StackPanel Grid.Column="4" Margin="32,10,32,10">
          <TextBlock Text="MAX GAIN" Foreground="#8B949E" FontSize="9"
                     FontWeight="SemiBold"/>
          <TextBlock x:Name="ScoreGain" Foreground="#58A6FF"
                     FontSize="32" FontWeight="Bold" FontFamily="Consolas"
                     LineHeight="34"/>
          <TextBlock Text="pts" Foreground="#3A4450" FontSize="12" FontFamily="Consolas"/>
        </StackPanel>

      </Grid>
    </Border>

    <!-- ══ SINGLE PAGE ════════════════════════════════════════════════════ -->
    <ScrollViewer Grid.Row="2" VerticalScrollBarVisibility="Auto">
     <StackPanel Margin="20,14,20,20">

      <!-- ── SCORE TABLE ── -->
      <DataGrid x:Name="AttrGrid" Height="210"
                AutoGenerateColumns="False" CanUserAddRows="False"
                CanUserDeleteRows="False" CanUserResizeRows="False"
                IsReadOnly="True" Margin="0,0,0,6">
            <DataGrid.Columns>
              <DataGridTextColumn Header="Attribute"    Binding="{Binding Attr}"       Width="175"/>
              <DataGridTextColumn Header="Current"      Binding="{Binding Current}"    Width="75">
                <DataGridTextColumn.ElementStyle>
                  <Style TargetType="TextBlock">
                    <Setter Property="HorizontalAlignment" Value="Center"/>
                    <Setter Property="FontFamily" Value="Consolas"/>
                  </Style>
                </DataGridTextColumn.ElementStyle>
              </DataGridTextColumn>
              <DataGridTextColumn Header="Min"          Binding="{Binding Min}"        Width="65">
                <DataGridTextColumn.ElementStyle>
                  <Style TargetType="TextBlock">
                    <Setter Property="HorizontalAlignment" Value="Center"/>
                    <Setter Property="FontFamily" Value="Consolas"/>
                  </Style>
                </DataGridTextColumn.ElementStyle>
              </DataGridTextColumn>
              <DataGridTextColumn Header="Score Now"    Binding="{Binding ScoreNow}"   Width="78">
                <DataGridTextColumn.ElementStyle>
                  <Style TargetType="TextBlock">
                    <Setter Property="HorizontalAlignment" Value="Right"/>
                    <Setter Property="FontFamily" Value="Consolas"/>
                    <Setter Property="Foreground" Value="#8B949E"/>
                  </Style>
                </DataGridTextColumn.ElementStyle>
              </DataGridTextColumn>
              <DataGridTextColumn Header="After Fix"    Binding="{Binding ScoreAfter}" Width="78">
                <DataGridTextColumn.ElementStyle>
                  <Style TargetType="TextBlock">
                    <Setter Property="HorizontalAlignment" Value="Right"/>
                    <Setter Property="FontFamily" Value="Consolas"/>
                  </Style>
                </DataGridTextColumn.ElementStyle>
              </DataGridTextColumn>
              <DataGridTemplateColumn Header="Gain" Width="72">
                <DataGridTemplateColumn.CellTemplate>
                  <DataTemplate>
                    <Border CornerRadius="10" Padding="6,1" HorizontalAlignment="Center"
                            Margin="0,3">
                      <Border.Style>
                        <Style TargetType="Border">
                          <Setter Property="Background" Value="Transparent"/>
                          <Style.Triggers>
                            <DataTrigger Binding="{Binding HasGain}" Value="True">
                              <Setter Property="Background" Value="#0D2A15"/>
                            </DataTrigger>
                          </Style.Triggers>
                        </Style>
                      </Border.Style>
                      <TextBlock Text="{Binding Gain}" FontSize="11" FontFamily="Consolas"
                                 HorizontalAlignment="Center">
                        <TextBlock.Style>
                          <Style TargetType="TextBlock">
                            <Setter Property="Foreground" Value="#3A4450"/>
                            <Style.Triggers>
                              <DataTrigger Binding="{Binding HasGain}" Value="True">
                                <Setter Property="Foreground" Value="#3FB950"/>
                              </DataTrigger>
                            </Style.Triggers>
                          </Style>
                        </TextBlock.Style>
                      </TextBlock>
                    </Border>
                  </DataTemplate>
                </DataGridTemplateColumn.CellTemplate>
              </DataGridTemplateColumn>
              <DataGridTextColumn Header="Items to Fix" Binding="{Binding Items}"      Width="*">
                <DataGridTextColumn.ElementStyle>
                  <Style TargetType="TextBlock">
                    <Setter Property="Foreground" Value="#8B949E"/>
                    <Setter Property="FontSize"   Value="11"/>
                  </Style>
                </DataGridTextColumn.ElementStyle>
              </DataGridTextColumn>
            </DataGrid.Columns>
          </DataGrid>

      <!-- param detail -->
      <Border Background="#111820" BorderBrush="#21262D" BorderThickness="1"
              CornerRadius="4" Padding="10,7" Margin="0,0,0,10" MaxHeight="72">
        <ScrollViewer VerticalScrollBarVisibility="Auto">
          <TextBlock x:Name="DetailText" Foreground="#6E7681" FontSize="10"
                     FontFamily="Consolas" TextWrapping="Wrap"/>
        </ScrollViewer>
      </Border>

      <!-- ── File & Performance ── -->
      <Border BorderBrush="#F0883E" BorderThickness="2,0,0,0"
              Padding="12,10" Margin="0,0,0,8" Background="#111208">
        <StackPanel>
          <TextBlock Text="File &amp; Performance" Foreground="#F0883E" FontWeight="SemiBold" FontSize="12"/>
          <TextBlock Text="Reduce file weight, remove embedded objects, clean up groups."
                     Foreground="#8B949E" FontSize="10" Margin="0,2,0,8"/>
          <WrapPanel>
            <Button x:Name="BtnPurge"     Content="Purge Unused"
                    Style="{StaticResource ActBtn}" Margin="0,0,6,4"/>
            <Button x:Name="BtnDelCAD"    Content="Delete CAD Imports"
                    Style="{StaticResource ActBtn}" Margin="0,0,6,4"/>
            <Button x:Name="BtnDelImages" Content="Delete Raster Images"
                    Style="{StaticResource ActBtn}" Margin="0,0,6,4"/>
            <Button x:Name="BtnUngroup"   Content="Ungroup All Groups"
                    Style="{StaticResource ActBtn}" Margin="0,0,6,4"/>
          </WrapPanel>
          <StackPanel Orientation="Horizontal" Margin="0,6,0,0">
            <TextBlock x:Name="PerfStatus" Foreground="#3FB950" FontSize="11"
                       VerticalAlignment="Center" Margin="0,0,10,0"/>
            <Button x:Name="BtnUndoPerf" Content="↩ Undo" Visibility="Collapsed"
                    Background="#1C1A2A" Foreground="#A78BFA" BorderBrush="#3D2A6A" Padding="8,3"/>
          </StackPanel>
        </StackPanel>
      </Border>

      <!-- ── Parameters ── -->
      <Border BorderBrush="#58A6FF" BorderThickness="2,0,0,0"
              Padding="12,10" Margin="0,0,0,8" Background="#0E1220">
        <StackPanel>
          <TextBlock Text="Parameters" Foreground="#58A6FF" FontWeight="SemiBold" FontSize="12"/>
          <TextBlock Text="Remove parameters not used by any formula, dimension, tag, or geometry."
                     Foreground="#8B949E" FontSize="10" Margin="0,2,0,8"/>
          <WrapPanel>
            <Button x:Name="BtnDelType"   Content="Delete Unused Type Params"
                    Style="{StaticResource ActBtn}" Margin="0,0,6,4"/>
            <Button x:Name="BtnDelInst"   Content="Delete Unused Inst Params"
                    Style="{StaticResource ActBtn}" Margin="0,0,6,4"/>
            <Button x:Name="BtnDelShared" Content="Delete Unused Shared Params"
                    Style="{StaticResource ActBtn}" Margin="0,0,6,4"/>
          </WrapPanel>
          <StackPanel Orientation="Horizontal" Margin="0,6,0,0">
            <TextBlock x:Name="ParamStatus" Foreground="#3FB950" FontSize="11"
                       VerticalAlignment="Center" Margin="0,0,10,0"/>
            <Button x:Name="BtnUndoParam" Content="↩ Undo" Visibility="Collapsed"
                    Background="#1C1A2A" Foreground="#A78BFA" BorderBrush="#3D2A6A" Padding="8,3"/>
          </StackPanel>
        </StackPanel>
      </Border>

      <!-- ── Cleanliness ── -->
      <Border BorderBrush="#3FB950" BorderThickness="2,0,0,0"
              Padding="12,10" Margin="0,0,0,8" Background="#0D1810">
        <StackPanel>
          <TextBlock Text="Cleanliness" Foreground="#3FB950" FontWeight="SemiBold" FontSize="12"/>
          <TextBlock Text="Reference planes named 'Reference Plane' are counted as unnamed."
                     Foreground="#8B949E" FontSize="10" Margin="0,2,0,8"/>
          <WrapPanel>
            <Button x:Name="BtnDelRP" Content="Delete Unnamed Ref Planes"
                    Style="{StaticResource ActBtn}" Margin="0,0,6,4"/>
          </WrapPanel>
          <StackPanel Orientation="Horizontal" Margin="0,6,0,0">
            <TextBlock x:Name="CleanStatus" Foreground="#3FB950" FontSize="11"
                       VerticalAlignment="Center" Margin="0,0,10,0"/>
            <Button x:Name="BtnUndoClean" Content="↩ Undo" Visibility="Collapsed"
                    Background="#1C1A2A" Foreground="#A78BFA" BorderBrush="#3D2A6A" Padding="8,3"/>
          </StackPanel>
        </StackPanel>
      </Border>

      <!-- ── Geometry ── -->
      <Border BorderBrush="#7C3AED" BorderThickness="2,0,0,0"
              Padding="12,10" Margin="0,0,0,8" Background="#110E1A">
        <StackPanel>
          <TextBlock Text="Geometry Forms" Foreground="#A78BFA" FontWeight="SemiBold" FontSize="12"/>
          <TextBlock Text="Select forms to delete. Preview shows score impact before committing."
                     Foreground="#8B949E" FontSize="10" Margin="0,2,0,8"/>

          <!-- geo stats strip -->
          <Border Background="#161B22" BorderBrush="#21262D" BorderThickness="1"
                  CornerRadius="4" Padding="12,8" Margin="0,0,0,8">
            <UniformGrid Columns="5">
              <StackPanel HorizontalAlignment="Center">
                <TextBlock Text="FACES"  Foreground="#8B949E" FontSize="9" FontWeight="SemiBold" TextAlignment="Center"/>
                <TextBlock x:Name="LblF" Foreground="#58A6FF" FontSize="20" FontWeight="Bold" FontFamily="Consolas" TextAlignment="Center"/>
              </StackPanel>
              <StackPanel HorizontalAlignment="Center">
                <TextBlock Text="SOLIDS" Foreground="#8B949E" FontSize="9" FontWeight="SemiBold" TextAlignment="Center"/>
                <TextBlock x:Name="LblS" Foreground="#58A6FF" FontSize="20" FontWeight="Bold" FontFamily="Consolas" TextAlignment="Center"/>
              </StackPanel>
              <StackPanel HorizontalAlignment="Center">
                <TextBlock Text="EDGES"  Foreground="#8B949E" FontSize="9" FontWeight="SemiBold" TextAlignment="Center"/>
                <TextBlock x:Name="LblE" Foreground="#58A6FF" FontSize="20" FontWeight="Bold" FontFamily="Consolas" TextAlignment="Center"/>
              </StackPanel>
              <StackPanel HorizontalAlignment="Center">
                <TextBlock Text="GEO SCORE" Foreground="#8B949E" FontSize="9" FontWeight="SemiBold" TextAlignment="Center"/>
                <TextBlock x:Name="LblGS" Foreground="#F0883E" FontSize="20" FontWeight="Bold" FontFamily="Consolas" TextAlignment="Center"/>
              </StackPanel>
              <StackPanel HorizontalAlignment="Center">
                <TextBlock Text="AFTER DELETE" Foreground="#8B949E" FontSize="9" FontWeight="SemiBold" TextAlignment="Center"/>
                <TextBlock x:Name="LblGA" Foreground="#3FB950" FontSize="20" FontWeight="Bold" FontFamily="Consolas" TextAlignment="Center"/>
              </StackPanel>
            </UniformGrid>
          </Border>

          <!-- geo grid -->
          <DataGrid x:Name="GeoGrid" Height="160"
                    AutoGenerateColumns="False" CanUserAddRows="False"
                    CanUserDeleteRows="False" CanUserResizeRows="False"
                    IsReadOnly="False" Margin="0,0,0,8">
            <DataGrid.Columns>
              <DataGridTemplateColumn Header="" Width="30" CanUserResize="False">
                <DataGridTemplateColumn.CellTemplate>
                  <DataTemplate>
                    <CheckBox IsChecked="{Binding Selected, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}"
                              HorizontalAlignment="Center" VerticalAlignment="Center"/>
                  </DataTemplate>
                </DataGridTemplateColumn.CellTemplate>
              </DataGridTemplateColumn>
              <DataGridTextColumn Header="Type"      Binding="{Binding EType}"  Width="130" IsReadOnly="True"/>
              <DataGridTextColumn Header="Name / Id" Binding="{Binding EName}"  Width="150" IsReadOnly="True"/>
              <DataGridTextColumn Header="Faces"     Binding="{Binding Faces}"  Width="55"  IsReadOnly="True">
                <DataGridTextColumn.ElementStyle>
                  <Style TargetType="TextBlock"><Setter Property="FontFamily" Value="Consolas"/><Setter Property="HorizontalAlignment" Value="Center"/></Style>
                </DataGridTextColumn.ElementStyle>
              </DataGridTextColumn>
              <DataGridTextColumn Header="Solids"    Binding="{Binding Solids}" Width="55"  IsReadOnly="True">
                <DataGridTextColumn.ElementStyle>
                  <Style TargetType="TextBlock"><Setter Property="FontFamily" Value="Consolas"/><Setter Property="HorizontalAlignment" Value="Center"/></Style>
                </DataGridTextColumn.ElementStyle>
              </DataGridTextColumn>
              <DataGridTextColumn Header="Edges"     Binding="{Binding Edges}"  Width="55"  IsReadOnly="True">
                <DataGridTextColumn.ElementStyle>
                  <Style TargetType="TextBlock"><Setter Property="FontFamily" Value="Consolas"/><Setter Property="HorizontalAlignment" Value="Center"/></Style>
                </DataGridTextColumn.ElementStyle>
              </DataGridTextColumn>
              <DataGridTextColumn Header="% Total"   Binding="{Binding Pct}"    Width="65"  IsReadOnly="True">
                <DataGridTextColumn.ElementStyle>
                  <Style TargetType="TextBlock"><Setter Property="Foreground" Value="#8B949E"/><Setter Property="HorizontalAlignment" Value="Center"/></Style>
                </DataGridTextColumn.ElementStyle>
              </DataGridTextColumn>
              <DataGridTextColumn Header="Gain if Removed" Binding="{Binding Impact}" Width="*" IsReadOnly="True">
                <DataGridTextColumn.ElementStyle>
                  <Style TargetType="TextBlock"><Setter Property="Foreground" Value="#3FB950"/><Setter Property="FontFamily" Value="Consolas"/></Style>
                </DataGridTextColumn.ElementStyle>
              </DataGridTextColumn>
            </DataGrid.Columns>
          </DataGrid>

          <WrapPanel>
            <Button x:Name="BtnGA" Content="Select All"  Margin="0,0,6,0"/>
            <Button x:Name="BtnGC" Content="Clear"       Margin="0,0,16,0"/>
            <Button x:Name="BtnGD" Content="Delete Selected Forms"
                    Style="{StaticResource DangerBtn}" Margin="0,0,8,0"/>
            <TextBlock x:Name="GeoStatus" Foreground="#3FB950" FontSize="11"
                       VerticalAlignment="Center" Margin="0,0,10,0"/>
            <Button x:Name="BtnUndoGeo" Content="↩ Undo" Visibility="Collapsed"
                    Background="#1C1A2A" Foreground="#A78BFA" BorderBrush="#3D2A6A" Padding="8,3"/>
          </WrapPanel>
        </StackPanel>
      </Border>

      <!-- ── Undo + Close bar ── -->
      <Border BorderBrush="#21262D" BorderThickness="0,1,0,0" Padding="0,10,0,0" Margin="0,4,0,0">
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="Auto"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0" Orientation="Horizontal" VerticalAlignment="Center">
            <Button x:Name="BtnUndo" Content="↩ Undo Last Action"
                    Background="#1C1A2A" Foreground="#A78BFA" BorderBrush="#3D2A6A"
                    Margin="0,0,10,0"/>
            <TextBlock x:Name="UndoStatus" Foreground="#8B949E" FontSize="11"
                       VerticalAlignment="Center"/>
          </StackPanel>
          <Button x:Name="BtnClose" Grid.Column="1" Content="Close"/>
        </Grid>
      </Border>

     </StackPanel>
    </ScrollViewer>

  </Grid>
</Window>
"""

# ── MAIN ──────────────────────────────────────────────────────────────────────
if not doc.IsFamilyDocument:
    from pyrevit import forms
    forms.alert("Open a family (.rfa) first.", title="Family Optimizer")
else:
    try: nbytes=os.path.getsize(doc.PathName) if doc.PathName else 0
    except: nbytes=0
    sz=nbytes/1000000.0
    n_cad=len(list(FilteredElementCollector(doc).OfClass(ImportInstance).ToElements()))
    all_rp=list(FilteredElementCollector(doc).OfClass(ReferencePlane).ToElements())
    n_rp=sum(1 for rp in all_rp if (rp.Name or "").strip().lower() in ("reference plane",""))
    rp_names=[rp.Name for rp in all_rp if (rp.Name or "").strip().lower() in ("reference plane","")]
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

    # attribute rows
    ar=[]
    sn,sm=contrib(sz,0,1,1.25)
    ar.append(AttrRow("File Size","{:.2f} MB".format(sz),"Purge",sn,sm,"Run Purge Unused"))
    sn,sm=contrib(n_cad,0,10,1.25)
    try: cl="; ".join(el.Category.Name if el.Category else "CAD" for el in FilteredElementCollector(doc).OfClass(ImportInstance).ToElements())
    except: cl=""
    ar.append(AttrRow("Imported CAD",n_cad,0,sn,sm,cl or "—"))
    sn,sm=contrib(n_img,0,10,0.5)
    ar.append(AttrRow("Raster Images",n_img,0,sn,sm,"Delete all images" if n_img else "—"))
    sn,sm=contrib(n_grp,0,5,0.75)
    ar.append(AttrRow("Model Groups",n_grp,0,sn,sm,"Ungroup all" if n_grp else "—"))
    sn,sm=contrib(n_rp,0,1,0.5)
    ar.append(AttrRow("Unnamed Ref Planes",n_rp,0,sn,sm,("; ".join(rp_names[:5])) if rp_names else "—"))
    sn,sm=contrib(n_ut,0,2,0.75)
    ar.append(AttrRow("Unused Type Params",n_ut,0,sn,sm,(", ".join(ut[:8])+(" …" if len(ut)>8 else "")) if ut else "—"))
    sn,sm=contrib(n_ui,0,2,0.75)
    ar.append(AttrRow("Unused Inst Params",n_ui,0,sn,sm,(", ".join(ui[:8])+(" …" if len(ui)>8 else "")) if ui else "—"))
    sn,sm=contrib(len(ush),0,2,0.5)
    ar.append(AttrRow("Unused Shared Params",len(ush),0,sn,sm,(", ".join(ush[:6])) if ush else "—"))
    tp2=max(0,n_tp-n_ut-n_ui)
    sn2=max(0.,10-n_tp//2)*0.5; sm2=max(0.,10-tp2//2)*0.5
    ar.append(AttrRow("Total Params",n_tp,tp2,sn2,sm2,"Remove {} unused".format(n_ut+n_ui) if (n_ut+n_ui) else "—"))
    sn=max(0.,10-n_sh*2)*0.5
    ar.append(AttrRow("Shared Params",n_sh,"—",sn,sn,"Needed for schedules/tags"))
    sn=max(0.,10-n_fp*2)*0.75
    ar.append(AttrRow("Formula Params",n_fp,"—",sn,sn,"Formulas are healthy — keep them"))
    geo_s=_blended(n_f,n_s,n_e)*1.25
    ar.append(AttrRow("Blended Geo Score",n_f,"—",geo_s,geo_s,"→ Geometry tab"))
    sn=max(0.,10-n_nest)*1.25
    ar.append(AttrRow("Nested Families",n_nest,"—",sn,sn,"Review usage manually"))

    geo_rows=_scan_forms(n_f,n_s,n_e)

    # build window
    window=XamlReader.Parse(XAML)
    window.FindName("SubTitle").Text="{} · {} attributes · {} geometry forms".format(
        doc.Title,len(ar),len(geo_rows))
    window.FindName("ScoreCurrent").Text="{:.1f}".format(cur)
    window.FindName("ScorePotential").Text="{:.1f}".format(pot)
    gv=pot-cur
    window.FindName("ScoreGain").Text="+{:.1f}".format(gv) if gv>0 else "0"
    window.FindName("LblF").Text=str(n_f); window.FindName("LblS").Text=str(n_s)
    window.FindName("LblE").Text=str(n_e); window.FindName("LblGS").Text="{:.2f}".format(geo_s)
    window.FindName("LblGA").Text="—"

    a_items=ObservableCollection[object]()
    for r in ar: a_items.Add(r)
    window.FindName("AttrGrid").ItemsSource=a_items

    g_items=ObservableCollection[object]()
    for r in geo_rows: g_items.Add(r)
    gg=window.FindName("GeoGrid"); gg.ItemsSource=g_items

    dl=[]
    if ut: dl.append("UNUSED TYPE ({}):\n  {}".format(len(ut),"\n  ".join(ut)))
    if ui: dl.append("UNUSED INST ({}):\n  {}".format(len(ui),"\n  ".join(ui)))
    if ush: dl.append("UNUSED SHARED ({}):\n  {}".format(len(ush),"\n  ".join(ush)))
    window.FindName("DetailText").Text="\n\n".join(dl) if dl else "No unused parameters found."

    def _status(msg): window.FindName("StatusBar").Text=msg

    # geo preview
    def _geo_preview(s=None,e=None):
        sel=[r for r in g_items if r.Selected]
        if not sel: window.FindName("LblGA").Text="—"; return
        rf=sum(r.Faces for r in sel); rs=sum(r.Solids for r in sel); re=sum(r.Edges for r in sel)
        window.FindName("LblGA").Text="{:.2f}".format(
            _blended(max(0,n_f-rf),max(0,n_s-rs),max(0,n_e-re))*1.25)
    gg.CellEditEnding+=lambda s,e: _geo_preview()

    def _update_row(attr,cur2,min2,per,w):
        sn2,sm2=contrib(cur2,min2,per,w)
        for r in a_items:
            if r.Attr==attr:
                r.Current=str(cur2); r.Min=str(min2)
                try: d=cur2-min2; r.ReduceBy=str(d) if d>0 else "—"
                except: r.ReduceBy="—"
                r.ScoreNow="{:.1f}".format(sn2); r.ScoreAfter="{:.1f}".format(sm2)
                g2=sm2-sn2; r.Gain="+{:.1f}".format(g2) if g2>0.05 else "—"
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

    from System.Windows import Visibility as WVis

    def _post_undo():
        try:
            from Autodesk.Revit.UI import PostableCommand, RevitCommandId
            undo_id = RevitCommandId.LookupPostableCommandId(PostableCommand.Undo)
            __revit__.PostCommand(undo_id)
            return True
        except: return False

    def _make_undo_btn(btn_name, status_name):
        """Show the undo button for a section and wire it to post undo + hide itself."""
        btn = window.FindName(btn_name)
        if btn: btn.Visibility = WVis.Visible
        def _do(s, e):
            ok = _post_undo()
            st = window.FindName(status_name)
            if st: st.Text = "Undo posted — close dialog then check Revit." if ok else "Use Ctrl+Z in Revit."
            if btn: btn.Visibility = WVis.Collapsed
        if btn: btn.Click += _do

    # ── perf actions ──────────────────────────────────────────────────────────
    def do_purge(s,e):
        if not _confirm("Purge Unused","Launch Revit's built-in Purge Unused?\nRevit will open its own dialog — confirm there to apply."):
            return
        try:
            from Autodesk.Revit.UI import PostableCommand, RevitCommandId
            cmd=RevitCommandId.LookupPostableCommandId(PostableCommand.PurgeUnused)
            __revit__.PostCommand(cmd)
            window.FindName("PerfStatus").Text="Purge Unused launched — confirm in the Revit dialog."
        except Exception as ex:
            window.FindName("PerfStatus").Text="Error: {}".format(str(ex)[:80])

    def do_del_cad(s,e):
        els=list(FilteredElementCollector(doc).OfClass(ImportInstance).ToElements())
        if not els: window.FindName("PerfStatus").Text="No CAD imports."; return
        if not _confirm("Delete CAD Imports","Delete {} CAD import(s)?\nThis can be undone with ↩ Undo Last Action.".format(len(els))): return
        n=0
        for el in els:
            try:
                with Transaction(doc,"Delete CAD Imports") as t:
                    t.Start(); doc.Delete(el.Id); t.Commit(); n+=1
            except: pass
        _update_row("Imported CAD",0,0,10,1.25)
        window.FindName("PerfStatus").Text="Deleted {} CAD import(s).".format(n)
        _make_undo_btn("BtnUndoPerf","PerfStatus")
        _refresh_btn_states()

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
                with Transaction(doc,"Delete Raster Images") as t:
                    t.Start(); doc.Delete(el.Id); t.Commit(); n+=1
            except: pass
        _update_row("Raster Images",0,0,10,0.5)
        window.FindName("PerfStatus").Text="Deleted {} image(s).".format(n)
        _make_undo_btn("BtnUndoPerf","PerfStatus")
        _refresh_btn_states()

    def do_ungroup(s,e):
        grps=list(FilteredElementCollector(doc).OfClass(Group).ToElements())
        if not grps: window.FindName("PerfStatus").Text="No groups."; return
        if not _confirm("Ungroup All","Ungroup {} model group(s)?".format(len(grps))): return
        n=0
        for grp in grps:
            try:
                with Transaction(doc,"Ungroup All Groups") as t:
                    t.Start(); grp.UngroupMembers(); t.Commit(); n+=1
            except: pass
        _update_row("Model Groups",0,0,5,0.75)
        window.FindName("PerfStatus").Text="Ungrouped {} group(s).".format(n)
        _make_undo_btn("BtnUndoPerf","PerfStatus")
        _refresh_btn_states()

    # ── param actions ─────────────────────────────────────────────────────────
    def _del_by_names(names,label,status_key):
        if not names: window.FindName(status_key).Text="No {} to delete.".format(label); return
        if not _confirm("Delete Params","Delete {} {}?\n\nParams:\n{}".format(
                len(names), label, "\n".join(names[:10])+("\n..." if len(names)>10 else ""))): return
        fm=doc.FamilyManager; n=0
        with Transaction(doc,"Delete "+label) as t:
            t.Start()
            for p in list(fm.GetParameters()):
                if p.Definition.Name in names:
                    try: fm.RemoveParameter(p); n+=1
                    except: pass
            t.Commit()
        _refresh_params()
        window.FindName(status_key).Text="Deleted {}.".format(n)
        _make_undo_btn("BtnUndoParam","ParamStatus")
        _refresh_btn_states()

    def do_del_type(s,e):
        _,_,_,ut2,_,_=_collect_params(); _del_by_names(ut2,"unused type params","ParamStatus")
    def do_del_inst(s,e):
        _,_,_,_,ui2,_=_collect_params(); _del_by_names(ui2,"unused inst params","ParamStatus")
    def do_del_shared(s,e):
        _,_,_,_,_,ush2=_collect_params(); _del_by_names(ush2,"unused shared params","ParamStatus")

    def do_del_rp(s,e):
        rps=[rp for rp in FilteredElementCollector(doc).OfClass(ReferencePlane).ToElements()
             if (rp.Name or "").strip().lower() in ("reference plane","")]
        if not rps: window.FindName("CleanStatus").Text="None to delete."; return
        if not _confirm("Delete Ref Planes","Delete {} unnamed reference plane(s)?\nAny in-use planes will be skipped.".format(len(rps))): return
        deleted=0; blocked=0
        for rp in rps:
            try:
                with Transaction(doc,"Delete Unnamed Ref Planes") as t:
                    t.Start(); doc.Delete(rp.Id); t.Commit(); deleted+=1
            except: blocked+=1
        n_rp2=sum(1 for rp in FilteredElementCollector(doc).OfClass(ReferencePlane).ToElements()
                  if (rp.Name or "").strip().lower() in ("reference plane",""))
        _update_row("Unnamed Ref Planes",n_rp2,0,1,0.5)
        msg="Deleted {}.".format(deleted)
        if blocked: msg+=" {} blocked — rename instead.".format(blocked)
        window.FindName("CleanStatus").Text=msg
        _make_undo_btn("BtnUndoClean","CleanStatus")
        _refresh_btn_states()

    # ── geo actions ───────────────────────────────────────────────────────────
    def geo_all(s,e):
        for r in g_items: r.Selected=True
        gg.Items.Refresh(); _geo_preview()
    def geo_clear(s,e):
        for r in g_items: r.Selected=False
        gg.Items.Refresh(); window.FindName("LblGA").Text="—"

    def geo_delete(s,e):
        sel=[r for r in g_items if r.Selected]
        if not sel: window.FindName("GeoStatus").Text="Nothing selected."; return
        if not _confirm("Delete Geometry","Delete {} selected form(s)?\nThis removes solid geometry permanently.".format(len(sel))): return
        deleted=0; blocked=0
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
        window.FindName("LblGS").Text="{:.2f}".format(gs2)
        window.FindName("LblGA").Text="—"
        for r in a_items:
            if r.Attr=="Blended Geo Score":
                r.Current=str(nf2); r.ScoreNow="{:.1f}".format(gs2); r.ScoreAfter="{:.1f}".format(gs2)
        window.FindName("AttrGrid").Items.Refresh()
        ng=_scan_forms(nf2,ns2,ne2)
        g_items.Clear()
        for r in ng: g_items.Add(r)
        gg.Items.Refresh()
        msg="Deleted {} form(s).".format(deleted)
        if blocked: msg+=" {} blocked (constrained).".format(blocked)
        window.FindName("GeoStatus").Text=msg
        _make_undo_btn("BtnUndoGeo","GeoStatus")
        _refresh_btn_states()

    # wire
    window.FindName("BtnPurge").Click     += do_purge
    window.FindName("BtnDelCAD").Click    += do_del_cad
    window.FindName("BtnDelImages").Click += do_del_images
    window.FindName("BtnUngroup").Click   += do_ungroup
    window.FindName("BtnDelType").Click   += do_del_type
    window.FindName("BtnDelInst").Click   += do_del_inst
    window.FindName("BtnDelShared").Click += do_del_shared
    window.FindName("BtnDelRP").Click     += do_del_rp
    window.FindName("BtnGA").Click        += geo_all
    window.FindName("BtnGC").Click        += geo_clear
    window.FindName("BtnGD").Click        += geo_delete
    window.FindName("BtnClose").Click     += lambda s,e: window.Close()

    # ── initial button state ──────────────────────────────────────────────────
    def _refresh_btn_states():
        _,_,_,ut2,ui2,ush2=_collect_params()
        rp_now=sum(1 for rp in FilteredElementCollector(doc).OfClass(ReferencePlane).ToElements()
                   if (rp.Name or "").strip().lower() in ("reference plane",""))
        cad_now=len(list(FilteredElementCollector(doc).OfClass(ImportInstance).ToElements()))
        try:
            from Autodesk.Revit.DB import RasterImage
            img_now=len(list(FilteredElementCollector(doc).OfClass(RasterImage).ToElements()))
        except: img_now=0
        grp_now=len(list(FilteredElementCollector(doc).OfClass(Group).ToElements()))
        geo_now=len(list(g_items))

        window.FindName("BtnDelCAD").IsEnabled    = cad_now > 0
        window.FindName("BtnDelImages").IsEnabled = img_now > 0
        window.FindName("BtnUngroup").IsEnabled   = grp_now > 0
        window.FindName("BtnDelType").IsEnabled   = len(ut2) > 0
        window.FindName("BtnDelInst").IsEnabled   = len(ui2) > 0
        window.FindName("BtnDelShared").IsEnabled = len(ush2) > 0
        window.FindName("BtnDelRP").IsEnabled     = rp_now > 0
        window.FindName("BtnGD").IsEnabled        = geo_now > 0

    _refresh_btn_states()
    window.ShowDialog()
