# script.py
# PyRevit pushbutton -- Family Parameter Audit & Cleanup
# Scans the open family for unused parameters and presents a WPF dialog
# allowing the user to select which ones to delete.

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from Autodesk.Revit.DB import (
    BuiltInParameter,
    Dimension,
    FilteredElementCollector,
    InternalDefinition,
    Transaction,
)
from System.Windows.Markup import XamlReader

# -----------------------------------------------------------------------
# Revit context
# -----------------------------------------------------------------------
doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

XAML = """
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Family Parameter Audit"
    Width="780" Height="560"
    WindowStartupLocation="CenterScreen"
    Background="#1E1E1E"
    FontFamily="Segoe UI"
    FontSize="13">

  <Window.Resources>
    <Style TargetType="Button">
      <Setter Property="Background"       Value="#2D2D2D"/>
      <Setter Property="Foreground"       Value="#E0E0E0"/>
      <Setter Property="BorderBrush"      Value="#444"/>
      <Setter Property="BorderThickness"  Value="1"/>
      <Setter Property="Padding"          Value="14,6"/>
      <Setter Property="Cursor"           Value="Hand"/>
      <Setter Property="FontSize"         Value="12"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#3A3A3A"/>
        </Trigger>
      </Style.Triggers>
    </Style>
    <Style TargetType="CheckBox">
      <Setter Property="Foreground" Value="#E0E0E0"/>
      <Setter Property="VerticalContentAlignment" Value="Center"/>
    </Style>
    <Style TargetType="DataGrid">
      <Setter Property="Background"            Value="#252525"/>
      <Setter Property="Foreground"            Value="#E0E0E0"/>
      <Setter Property="BorderBrush"           Value="#444"/>
      <Setter Property="BorderThickness"       Value="1"/>
      <Setter Property="RowBackground"         Value="#252525"/>
      <Setter Property="AlternatingRowBackground" Value="#2A2A2A"/>
      <Setter Property="HorizontalGridLinesBrush" Value="#333"/>
      <Setter Property="VerticalGridLinesBrush"   Value="#333"/>
      <Setter Property="ColumnHeaderHeight"    Value="28"/>
    </Style>
    <Style TargetType="DataGridColumnHeader">
      <Setter Property="Background"   Value="#333"/>
      <Setter Property="Foreground"   Value="#AAB4BE"/>
      <Setter Property="FontWeight"   Value="SemiBold"/>
      <Setter Property="Padding"      Value="8,0"/>
      <Setter Property="BorderBrush"  Value="#444"/>
      <Setter Property="BorderThickness" Value="0,0,1,1"/>
    </Style>
    <Style TargetType="DataGridRow">
      <Setter Property="Foreground" Value="#E0E0E0"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#303030"/>
        </Trigger>
        <Trigger Property="IsSelected" Value="True">
          <Setter Property="Background" Value="#1A3A52"/>
        </Trigger>
      </Style.Triggers>
    </Style>
    <Style TargetType="DataGridCell">
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Padding"         Value="6,2"/>
      <Style.Triggers>
        <Trigger Property="IsSelected" Value="True">
          <Setter Property="Background" Value="Transparent"/>
          <Setter Property="Foreground" Value="#E0E0E0"/>
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
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <!-- Header -->
    <StackPanel Grid.Row="0" Margin="0,0,0,12">
      <TextBlock Text="Family Parameter Audit"
                 FontSize="18" FontWeight="Bold"
                 Foreground="#E0E0E0"/>
      <TextBlock x:Name="SubTitle"
                 FontSize="11" Foreground="#888"
                 Margin="0,2,0,0"/>
    </StackPanel>

    <!-- Column legend -->
    <Border Grid.Row="1" Background="#2A2A2A" BorderBrush="#444"
            BorderThickness="1" CornerRadius="3" Padding="10,6" Margin="0,0,0,10">
      <WrapPanel Orientation="Horizontal">
        <TextBlock Foreground="#888" FontSize="11" Text="Columns:  "/>
        <TextBlock Foreground="#7DBBE8" FontSize="11" Text="Frml"/>
        <TextBlock Foreground="#888" FontSize="11" Text=" = has formula    "/>
        <TextBlock Foreground="#7DBBE8" FontSize="11" Text="FInpt"/>
        <TextBlock Foreground="#888" FontSize="11" Text=" = used inside formula    "/>
        <TextBlock Foreground="#7DBBE8" FontSize="11" Text="Dim"/>
        <TextBlock Foreground="#888" FontSize="11" Text=" = dimension constraint    "/>
        <TextBlock Foreground="#7DBBE8" FontSize="11" Text="Tag"/>
        <TextBlock Foreground="#888" FontSize="11" Text=" = label/tag    "/>
        <TextBlock Foreground="#7DBBE8" FontSize="11" Text="Geo"/>
        <TextBlock Foreground="#888" FontSize="11" Text=" = geometry association"/>
      </WrapPanel>
    </Border>

    <!-- Data grid -->
    <DataGrid x:Name="ParamGrid" Grid.Row="2"
              AutoGenerateColumns="False"
              CanUserAddRows="False"
              CanUserDeleteRows="False"
              CanUserResizeRows="False"
              SelectionMode="Extended"
              IsReadOnly="False"
              Margin="0,0,0,10">
      <DataGrid.Columns>
        <!-- Checkbox for selection -->
        <DataGridTemplateColumn Header="" Width="32" CanUserResize="False">
          <DataGridTemplateColumn.CellTemplate>
            <DataTemplate>
              <CheckBox IsChecked="{Binding Selected, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}"
                        HorizontalAlignment="Center" VerticalAlignment="Center"
                        IsEnabled="{Binding IsUnused}"/>
                        <!-- IsUnused is False for both used params AND built-ins, so checkbox is disabled for both -->
            </DataTemplate>
          </DataGridTemplateColumn.CellTemplate>
        </DataGridTemplateColumn>

        <DataGridTextColumn Header="Parameter Name" Binding="{Binding Name}"    Width="220" IsReadOnly="True"/>
        <DataGridTextColumn Header="Type"           Binding="{Binding PType}"   Width="80"  IsReadOnly="True"/>
        <DataGridTextColumn Header="Frml"           Binding="{Binding Frml}"    Width="50"  IsReadOnly="True"/>
        <DataGridTextColumn Header="FInpt"          Binding="{Binding FInpt}"   Width="50"  IsReadOnly="True"/>
        <DataGridTextColumn Header="Dim"            Binding="{Binding Dim}"     Width="50"  IsReadOnly="True"/>
        <DataGridTextColumn Header="Tag"            Binding="{Binding Tag}"     Width="50"  IsReadOnly="True"/>
        <DataGridTextColumn Header="Geo"            Binding="{Binding Geo}"     Width="50"  IsReadOnly="True"/>
        <DataGridTextColumn Header="Status"         Binding="{Binding Status}"  Width="*"   IsReadOnly="True"/>
      </DataGrid.Columns>
    </DataGrid>

    <!-- Select controls -->
    <StackPanel Grid.Row="3" Orientation="Horizontal" Margin="0,0,0,12">
      <Button x:Name="BtnSelectUnused"  Content="Select All Unused"  Margin="0,0,8,0"/>
      <Button x:Name="BtnSelectNone"    Content="Clear Selection"    Margin="0,0,8,0"/>
      <TextBlock x:Name="SelectionCount" Foreground="#888" FontSize="11"
                 VerticalAlignment="Center" Margin="8,0,0,0"/>
    </StackPanel>

    <!-- Action buttons -->
    <StackPanel Grid.Row="4" Orientation="Horizontal" HorizontalAlignment="Right">
      <Button x:Name="BtnDelete" Content="Delete Selected"
              Background="#8B2A2A" Foreground="White"
              BorderBrush="#A33" Margin="0,0,8,0"/>
      <Button x:Name="BtnClose"  Content="Close"/>
    </StackPanel>
  </Grid>
</Window>
"""


# -----------------------------------------------------------------------
# Built-in parameter detection
# -----------------------------------------------------------------------
def is_builtin(family_param):
    """Returns True if this FamilyParameter wraps a Revit built-in parameter
    and therefore cannot be removed via FamilyManager.RemoveParameter()."""
    try:
        defn = family_param.Definition
        if isinstance(defn, InternalDefinition):
            bip = defn.BuiltInParameter
            return bip != BuiltInParameter.INVALID
    except Exception:
        pass
    return False


# -----------------------------------------------------------------------
# Data model (plain Python object -- IronPython doesn't need INotifyPropertyChanged
# for DataGrid initial binding, but we use a simple wrapper)
# -----------------------------------------------------------------------
class ParamRow(object):
    def __init__(
        self,
        name,
        ptype,
        frml,
        finpt,
        dim,
        tag,
        geo,
        is_unused,
        is_builtin_param,
        param_id,
    ):
        self.Name = name
        self.PType = ptype
        self.Frml = frml
        self.FInpt = finpt
        self.Dim = dim
        self.Tag = tag
        self.Geo = geo
        self.IsBuiltIn = is_builtin_param
        self.IsUnused = is_unused and not is_builtin_param  # builtins never deletable
        self.Selected = (
            is_unused and not is_builtin_param
        )  # pre-tick deletable unused only
        self.ParamId = param_id  # IntegerValue of ElementId

        if is_builtin_param:
            self.Status = "BUILT-IN"
        elif is_unused:
            self.Status = "UNUSED"
        else:
            self.Status = ""


# -----------------------------------------------------------------------
# Audit logic (same as param_audit.py)
# -----------------------------------------------------------------------
def run_audit(doc):
    fm = doc.FamilyManager

    formula_outputs = set()
    formula_inputs = set()
    for p in fm.GetParameters():
        if p.Formula:
            formula_outputs.add(p.Id.IntegerValue)
            for other in fm.GetParameters():
                if other.Definition.Name in p.Formula:
                    formula_inputs.add(other.Id.IntegerValue)

    dim_associated = set()
    dims = FilteredElementCollector(doc).OfClass(Dimension).ToElements()
    for dim in dims:
        try:
            if dim.FamilyLabel is not None:
                dim_associated.add(dim.FamilyLabel.Id.IntegerValue)
        except Exception:
            pass

    label_params = set()
    try:
        from Autodesk.Revit.DB import FamilyLabel

        family_labels = FilteredElementCollector(doc).OfClass(FamilyLabel).ToElements()
        for fl in family_labels:
            for seg in fl.GetSegments():
                if seg.IsParam:
                    label_params.add(seg.FamilyParameter.Id.IntegerValue)
    except Exception:
        pass

    element_params = set()
    for elem in (
        FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
    ):
        try:
            for p in elem.Parameters:
                try:
                    assoc = fm.GetAssociatedFamilyParameter(p)
                    if assoc is not None:
                        element_params.add(assoc.Id.IntegerValue)
                except Exception:
                    pass
        except Exception:
            pass

    rows = []
    for p in sorted(fm.GetParameters(), key=lambda x: x.Definition.Name):
        pid = p.Id.IntegerValue
        used = any(
            [
                pid in formula_outputs,
                pid in formula_inputs,
                pid in dim_associated,
                pid in label_params,
                pid in element_params,
            ]
        )
        rows.append(
            ParamRow(
                name=p.Definition.Name,
                ptype="Instance" if p.IsInstance else "Type",
                frml="Y" if pid in formula_outputs else "-",
                finpt="Y" if pid in formula_inputs else "-",
                dim="Y" if pid in dim_associated else "-",
                tag="Y" if pid in label_params else "-",
                geo="Y" if pid in element_params else "-",
                is_unused=not used,
                is_builtin_param=is_builtin(p),
                param_id=pid,
            )
        )
    return rows, fm


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------
if not doc.IsFamilyDocument:
    from pyrevit import forms

    forms.alert(
        "Active document is not a family.\nOpen a family (.rfa) first.",
        title="Family Parameter Audit",
    )
else:
    rows, fm = run_audit(doc)

    window = XamlReader.Parse(XAML)

    # Subtitle
    unused_count = sum(1 for r in rows if r.IsUnused)
    builtin_count = sum(1 for r in rows if r.IsBuiltIn)
    subtitle = window.FindName("SubTitle")
    subtitle.Text = (
        "{} parameters found  |  {} unused  |  {} built-in (protected)".format(
            len(rows), unused_count, builtin_count
        )
    )

    # Bind rows to grid
    grid = window.FindName("ParamGrid")
    from System.Collections.ObjectModel import ObservableCollection

    items = ObservableCollection[object]()
    for r in rows:
        items.Add(r)
    grid.ItemsSource = items

    # Colour unused rows red via row style trigger workaround:
    # We'll do it via the Status column cell style instead -- simplest in XAML-less code
    # (Full cell colouring requires DataTrigger in XAML; the UNUSED label is sufficient here)

    count_label = window.FindName("SelectionCount")

    def update_count():
        n = sum(1 for r in items if r.IsUnused and r.Selected)
        count_label.Text = "{} unused parameter(s) selected for deletion".format(n)

    update_count()

    # Select all unused (excluding built-ins, which are already non-selectable)
    def select_unused(sender, e):
        for r in items:
            if r.IsUnused and not r.IsBuiltIn:
                r.Selected = True
        grid.Items.Refresh()
        update_count()

    # Clear selection
    def select_none(sender, e):
        for r in items:
            r.Selected = False
        grid.Items.Refresh()
        update_count()

    # Refresh count whenever cell is edited
    def cell_edited(sender, e):
        update_count()

    window.FindName("BtnSelectUnused").Click += select_unused
    window.FindName("BtnSelectNone").Click += select_none
    grid.CellEditEnding += cell_edited

    # Delete
    def delete_selected(sender, e):
        to_delete = [r for r in items if r.IsUnused and r.Selected]
        if not to_delete:
            from pyrevit import forms

            forms.alert("No unused parameters selected.", title="Nothing to delete")
            return

        names = "\n".join("  - " + r.Name for r in to_delete)
        from pyrevit import forms

        confirm = forms.alert(
            "Delete {} parameter(s)?\n\n{}\n\nThis cannot be undone.".format(
                len(to_delete), names
            ),
            title="Confirm Deletion",
            yes=True,
            no=True,
        )
        if not confirm:
            return

        failed = []
        with Transaction(doc, "Delete Unused Family Parameters") as t:
            t.Start()
            for r in to_delete:
                try:
                    param = fm.GetParameters()
                    match = next(
                        (p for p in param if p.Id.IntegerValue == r.ParamId), None
                    )
                    if match:
                        fm.RemoveParameter(match)
                except Exception as ex:
                    failed.append("{} ({})".format(r.Name, str(ex)))
            t.Commit()

        # Refresh the list
        new_rows, _ = run_audit(doc)
        items.Clear()
        for row in new_rows:
            items.Add(row)
        grid.Items.Refresh()

        new_unused = sum(1 for r in new_rows if r.IsUnused)
        new_builtins = sum(1 for r in new_rows if r.IsBuiltIn)
        subtitle.Text = (
            "{} parameters found  |  {} unused  |  {} built-in (protected)".format(
                len(new_rows), new_unused, new_builtins
            )
        )
        update_count()

        if failed:
            from pyrevit import forms

            forms.alert(
                "Some parameters could not be deleted:\n" + "\n".join(failed),
                title="Partial Success",
            )

    def close_window(sender, e):
        window.Close()

    window.FindName("BtnDelete").Click += delete_selected
    window.FindName("BtnClose").Click += close_window

    window.ShowDialog()
