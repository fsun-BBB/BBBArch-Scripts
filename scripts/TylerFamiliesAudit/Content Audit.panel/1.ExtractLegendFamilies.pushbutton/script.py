# -*- coding: utf-8 -*-
"""
Extracts families referenced by legend symbols and saves each one as a
standalone .rfa, organized by Revit category, for Tyler's Families Audit.

Flow:
1. Box-select everything you want to extract (headers, dashed boxes, tags,
   detail lines, etc. are fine to sweep up - anything that isn't a
   family-based element is silently ignored). Click Finish on the ribbon.
2. Every unique family among the selection is extracted to
   0_HOLDING_TYLER\\<Revit Category>\\<Family Name>.rfa (overwriting any
   existing file of the same name).
3. You're asked whether to also extract nested families found inside those
   families (however deep the nesting goes - each nested family becomes
   its own row/file, with Parent Family recording only its immediate host).
4. You're asked whether to import everything just extracted into the
   "Revit Families Audit" Notion database now.
"""

__title__ = "Extract\nLegend Families"
__author__ = "BBB"

import json
import os

try:
    from pyrevit import forms, script
except ImportError:
    pass

from Autodesk.Revit.UI.Selection import ObjectType

from tyler_audit.extraction import (
    OUTPUT_ROOT,
    elem_name,
    extract_nested_tree,
    extract_one_family,
    get_symbol_from_element,
    manifest_path_for,
)
from tyler_audit.notion_sync import import_manifest

doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
output = script.get_output()
logger = script.get_logger()


def collect_top_level_symbols():
    """Prompt the user to box-select everything to extract, once."""
    forms.alert(
        "Box-select everything you want to extract, then click Finish on "
        "the ribbon (or Escape to cancel).\n\n"
        "It's fine to also sweep up headers, dashed boxes, tags, or detail "
        "lines - anything that isn't a family-based element is ignored "
        "automatically.",
        title="Select Families to Extract",
    )
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, "Select everything to extract, then click Finish"
        )
    except Exception:
        return []

    symbols = []
    seen_keys = []
    for ref in refs:
        try:
            elem = doc.GetElement(ref.ElementId)
            symbol = get_symbol_from_element(doc, elem)
            if symbol is None:
                continue
            key = (elem_name(symbol.Family), elem_name(symbol))
            if key in seen_keys:
                continue
            seen_keys.append(key)
            symbols.append(symbol)
        except Exception as ex:
            logger.warning(
                "Could not resolve element {} - skipping it: {}".format(
                    ref.ElementId, ex
                )
            )
    return symbols


def choose_output_root():
    """Let the user pick where extracted families get saved. Cancelling
    falls back to the default holding folder rather than aborting - the
    same <Revit Category>\\<Family Name>.rfa subfolder structure is created
    under whichever root ends up being used.
    """
    picked = forms.pick_folder(title="Choose Root Folder for Extracted Families")
    output_root = picked or OUTPUT_ROOT
    if not os.path.exists(output_root):
        os.makedirs(output_root)
    return output_root


def main():
    symbols = collect_top_level_symbols()
    if not symbols:
        forms.alert("Nothing was selected. Nothing to extract.", exitscript=True)

    output_root = choose_output_root()

    # One row per family - accumulate every selected type against it.
    family_type_map = {}
    for symbol in symbols:
        family = symbol.Family
        name = elem_name(family)
        entry = family_type_map.setdefault(name, {"family": family, "types": set()})
        entry["types"].add(elem_name(symbol))

    manifest = []
    top_level_docs = []  # kept open in case the user opts into nested extraction
    with forms.ProgressBar(title="Extracting families ({value} of {max_value})") as pb:
        items = list(family_type_map.items())
        for i, (name, data) in enumerate(items):
            pb.update_progress(i + 1, len(items))
            try:
                family_doc, entry = extract_one_family(doc, data["family"], logger, output_root)
            except Exception as ex:
                logger.error("Failed to extract family '{}': {}".format(name, ex))
                continue
            if entry is None:
                continue
            entry["types"] = sorted(data["types"])
            manifest.append(entry)
            top_level_docs.append(family_doc)

    if not manifest:
        forms.alert("Nothing could be extracted.", exitscript=True)

    do_nested = forms.alert(
        "Extracted {} top-level famil{}.\n\n"
        "Also extract nested families found inside them?".format(
            len(manifest), "y" if len(manifest) == 1 else "ies"
        ),
        title="Extract Nested Families?",
        ok=False,
        yes=True,
        no=True,
    )

    if do_nested:
        visited = {item["family_name"]: item for item in manifest}
        with forms.ProgressBar(
            title="Extracting nested families ({value} of {max_value})"
        ) as pb:
            for i, (family_doc, entry) in enumerate(zip(top_level_docs, list(manifest))):
                pb.update_progress(i + 1, len(top_level_docs))
                try:
                    extract_nested_tree(family_doc, entry, manifest, visited, logger, output_root)
                except Exception as ex:
                    logger.error(
                        "Nested extraction failed for '{}': {}".format(
                            entry["family_name"], ex
                        )
                    )

    for family_doc in top_level_docs:
        family_doc.Close(False)

    manifest_path = manifest_path_for(output_root)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    do_import = forms.alert(
        "Extracted {} famil{} total.\n\n"
        "Import all of them into Tyler's Families Audit in Notion now?".format(
            len(manifest), "y" if len(manifest) == 1 else "ies"
        ),
        title="Import to Notion?",
        ok=False,
        yes=True,
        no=True,
    )

    import_result = None
    if do_import:
        try:
            import_result = import_manifest(manifest, logger)
        except Exception as ex:
            logger.error("Notion import failed: {}".format(ex))
            import_result = {"created": 0, "updated": 0, "failed": len(manifest), "details": [str(ex)]}

    # All interactive prompts are done - safe to open the console now.
    output.print_md(
        "### Extracted {} famil{} to `{}`".format(
            len(manifest), "y" if len(manifest) == 1 else "ies", output_root
        )
    )
    for item in manifest:
        parent_display = (
            ", ".join(item["parent_families"]) if item["parent_families"] else "N/A"
        )
        children_display = (
            ", ".join(item["child_families"]) if item["child_families"] else "N/A"
        )
        output.print_md(
            "- **{}** ({}) — types: {} — parent: {} — children: {} — {} KB".format(
                item["family_name"],
                item["category"],
                ", ".join(item["types"]) if item["types"] else "N/A",
                parent_display,
                children_display,
                item["file_size_kb"],
            )
        )
    output.print_md("\nManifest written to `{}`".format(manifest_path))

    if import_result is not None:
        output.print_md("---")
        output.print_md(
            "### Notion import: {} created, {} updated, {} failed".format(
                import_result["created"], import_result["updated"], import_result["failed"]
            )
        )
        for line in import_result["details"]:
            output.print_md("- {}".format(line))
    else:
        output.print_md(
            "\nSkipped Notion import. Run **Import to Notion** later to push "
            "this manifest."
        )


if __name__ == "__main__":
    main()
