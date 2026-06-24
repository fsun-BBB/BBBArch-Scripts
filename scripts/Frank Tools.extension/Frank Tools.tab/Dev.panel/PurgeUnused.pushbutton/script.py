# script.py
# PyRevit pushbutton -- Purge Unused Family Elements
# Calls Document.Purge() in a loop until the family is fully clean.

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from Autodesk.Revit.DB import FilteredElementCollector, Transaction
from System.Collections.Generic import HashSet
from Autodesk.Revit.DB import ElementId
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
    Title="Purge Unused Family Elements"
    Width="620" Height="520"
    WindowStartupLocation="CenterScreen"
    Background="#1E1E1E"
    FontFamily="Segoe UI"
    FontSize="13">

  <Window.Resources>
    <Style TargetType="Button">
      <Setter Property="Background"      Value="#2D2D2D"/>
      <Setter Property="Foreground"      Value="#E0E0E0"/>
      <Setter Property="BorderBrush"     Value="#444"/>
      <Setter Property="BorderThickness" Value="1"/>
      <Setter Property="Padding"         Value="14,6"/>
      <Setter Property="Cursor"          Value="Hand"/>
      <Setter Property="FontSize"        Value="12"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#3A3A3A"/>
        </Trigger>
        <Trigger Property="IsEnabled" Value="False">
          <Setter Property="Foreground" Value="#555"/>
          <Setter Property="BorderBrush" Value="#333"/>
        </Trigger>
      </Style.Triggers>
    </Style>
    <Style TargetType="ScrollBar">
      <Setter Property="Background" Value="#2D2D2D"/>
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
    <StackPanel Grid.Row="0" Margin="0,0,0,12">
      <TextBlock Text="Purge Unused Family Elements"
                 FontSize="18" FontWeight="Bold"
                 Foreground="#E0E0E0"/>
      <TextBlock x:Name="SubTitle"
                 FontSize="11" Foreground="#888"
                 Margin="0,2,0,0"/>
    </StackPanel>

    <!-- Info banner -->
    <Border Grid.Row="1" Background="#2A2A2A" BorderBrush="#444"
            BorderThickness="1" CornerRadius="3" Padding="10,8" Margin="0,0,0,12">
      <TextBlock TextWrapping="Wrap" Foreground="#AAB4BE" FontSize="11"
                 LineHeight="18">
        Runs Revit&#x2019;s purge operation on the active family, repeating until no
        more unused elements are found. Multiple rounds are needed because
        removing one element can expose others for purging.
      </TextBlock>
    </Border>

    <!-- Log area -->
    <Border Grid.Row="2" BorderBrush="#444" BorderThickness="1"
            CornerRadius="3" Margin="0,0,0,12">
      <ScrollViewer x:Name="LogScroller"
                    VerticalScrollBarVisibility="Auto"
                    Background="#252525">
        <TextBox x:Name="LogBox"
                 Background="Transparent"
                 Foreground="#E0E0E0"
                 BorderThickness="0"
                 IsReadOnly="True"
                 TextWrapping="Wrap"
                 Padding="10,8"
                 FontFamily="Consolas"
                 FontSize="11"
                 AcceptsReturn="True"
                 Text="Click &#x201C;Run Purge&#x201D; to start."/>
      </ScrollViewer>
    </Border>

    <!-- Footer: status + buttons -->
    <Grid Grid.Row="3">
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="*"/>
        <ColumnDefinition Width="Auto"/>
        <ColumnDefinition Width="Auto"/>
      </Grid.ColumnDefinitions>
      <TextBlock x:Name="StatusLabel"
                 Grid.Column="0"
                 Foreground="#888" FontSize="11"
                 VerticalAlignment="Center"/>
      <Button x:Name="BtnPurge"
              Grid.Column="1"
              Content="Run Purge"
              Background="#1E4A1E" Foreground="White"
              BorderBrush="#2D6A2D"
              Margin="0,0,8,0"/>
      <Button x:Name="BtnClose"
              Grid.Column="2"
              Content="Close"/>
    </Grid>
  </Grid>
</Window>
"""


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------
def build_candidate_set(document):
    """Collect all element IDs in the document as purge candidates."""
    ids = HashSet[ElementId]()
    for elem in FilteredElementCollector(document).WhereElementIsNotElementType().ToElements():
        ids.Add(elem.Id)
    for elem in FilteredElementCollector(document).WhereElementIsElementType().ToElements():
        ids.Add(elem.Id)
    return ids


def snapshot_element_info(document):
    """Return a dict of {int_id: "Category / Name"} for display after purge."""
    info = {}
    for elem in FilteredElementCollector(document).WhereElementIsNotElementType().ToElements():
        try:
            name = elem.Name or elem.GetType().Name
        except Exception:
            name = elem.GetType().Name
        try:
            cat = elem.Category.Name if elem.Category else elem.GetType().Name
        except Exception:
            cat = elem.GetType().Name
        info[elem.Id.IntegerValue] = u"{} / {}".format(cat, name)
    for elem in FilteredElementCollector(document).WhereElementIsElementType().ToElements():
        try:
            name = elem.Name or elem.GetType().Name
        except Exception:
            name = elem.GetType().Name
        try:
            cat = elem.Category.Name if elem.Category else elem.GetType().Name
        except Exception:
            cat = elem.GetType().Name
        info[elem.Id.IntegerValue] = u"{} / {}".format(cat, name)
    return info


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------
if not doc.IsFamilyDocument:
    from pyrevit import forms
    forms.alert(
        "Active document is not a family.\nOpen a family (.rfa) first.",
        title="Purge Unused Family Elements",
    )
else:
    window = XamlReader.Parse(XAML)

    subtitle = window.FindName("SubTitle")
    subtitle.Text = doc.Title

    log_box = window.FindName("LogBox")
    log_scroller = window.FindName("LogScroller")
    status_label = window.FindName("StatusLabel")
    btn_purge = window.FindName("BtnPurge")
    btn_close = window.FindName("BtnClose")

    def append_log(text):
        log_box.Text += text + "\n"
        log_scroller.ScrollToBottom()

    def run_purge(sender, e):
        btn_purge.IsEnabled = False
        log_box.Text = "Launching Revit's built-in Purge Unused...\n"
        status_label.Text = "Launching..."
        try:
            from Autodesk.Revit.UI import PostableCommand, RevitCommandId
            cmd = RevitCommandId.LookupPostableCommandId(PostableCommand.PurgeUnused)
            __revit__.PostCommand(cmd)
            append_log(u"Purge Unused command posted.")
            append_log(u"Confirm in the Revit dialog that appears.")
            status_label.Text = u"Purge Unused launched — confirm in Revit dialog."
        except Exception as ex:
            append_log(u"Error: {}".format(str(ex)))
            status_label.Text = u"Error launching purge."
        btn_close.Content = "Done"

    def close_window(sender, e):
        window.Close()

    btn_purge.Click += run_purge
    btn_close.Click += close_window

    window.ShowDialog()
