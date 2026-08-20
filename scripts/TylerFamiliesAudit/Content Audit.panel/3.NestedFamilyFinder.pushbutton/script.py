# -*- coding: utf-8 -*-
"""
Scans one or more family files for nested families (however deep the
nesting goes) and extracts every one of them into 0_HOLDING_TYLER for
Tyler's Families Audit.

Usage: run this tool and browse to the family/families you want to scan in
the file picker - they do NOT need to be already open or loaded into the
current model; any .rfa on disk can be picked.

The family/families you picked are NOT copied/moved; each is registered in
the manifest/Notion using its own file path. Every *nested* family found
inside them IS saved into 0_HOLDING_TYLER\\<Revit Category>\\<Family
Name>.rfa, unrenamed, overwriting any existing file of the same name.

Relationship model: if the opened family is D, and D nests E, and E nests
F, then D's Child Family is E and E's Child Family is F - D's row never
lists F (only the immediate, one-level relationship is recorded per row).
A family can have more than one parent if it's shared between hosts (e.g.
the same hardware family nested in two different door families) - that's
expected, not an error.
"""

__title__ = "Nested Family\nFinder"
__author__ = "BBB"

import json
import os

try:
    from pyrevit import forms, script
except ImportError:
    pass

from tyler_audit.extraction import (
    MANIFEST_PATH,
    OUTPUT_ROOT,
    entry_for_open_family,
    extract_nested_tree,
)
from tyler_audit.notion_sync import import_manifest

output = script.get_output()
logger = script.get_logger()


def pick_family_paths():
    """Browse the filesystem for one or more .rfa files to scan."""
    paths = forms.pick_file(
        file_ext="rfa",
        multi_file=True,
        title="Select Family or Families to Scan",
    )
    if not paths:
        forms.alert("Nothing selected. Nothing to scan.", exitscript=True)
    return paths


def resolve_family_docs(paths):
    """Open the given .rfa paths, reusing already-open documents where
    possible. Returns (family_docs, opened_by_us) - opened_by_us marks
    which ones this tool opened itself (and should therefore close when
    done), as opposed to ones the user already had open.
    """
    app = __revit__.Application
    already_open = {}
    for d in app.Documents:
        if d.IsFamilyDocument and d.PathName:
            already_open[os.path.normcase(d.PathName)] = d

    family_docs = []
    opened_by_us = []
    for path in paths:
        key = os.path.normcase(path)
        if key in already_open:
            family_docs.append(already_open[key])
            opened_by_us.append(False)
            continue
        try:
            family_doc = app.OpenDocumentFile(path)
        except Exception as ex:
            logger.error("Could not open '{}': {}".format(path, ex))
            continue
        family_docs.append(family_doc)
        opened_by_us.append(True)
    return family_docs, opened_by_us


def main():
    paths = pick_family_paths()
    family_docs, opened_by_us = resolve_family_docs(paths)
    if not family_docs:
        forms.alert("None of the selected files could be opened.", exitscript=True)

    manifest = []
    visited = {}
    top_level_names = []

    with forms.ProgressBar(title="Scanning families ({value} of {max_value})") as pb:
        for i, family_doc in enumerate(family_docs):
            pb.update_progress(i + 1, len(family_docs))
            opened_family = family_doc.OwnerFamily
            entry = entry_for_open_family(family_doc, opened_family)
            if entry is None:
                logger.warning(
                    "'{}' has not been saved - skipped.".format(family_doc.Title)
                )
                continue
            if entry["family_name"] in visited:
                # Already covered (e.g. picked twice, or nested inside
                # another family also picked in this same run).
                continue
            manifest.append(entry)
            visited[entry["family_name"]] = entry
            top_level_names.append(entry["family_name"])
            try:
                extract_nested_tree(family_doc, entry, manifest, visited, logger)
            except Exception as ex:
                logger.error(
                    "Nested extraction failed for '{}': {}".format(
                        entry["family_name"], ex
                    )
                )

    # Close whatever this tool opened itself - leave anything the user
    # already had open exactly as they had it.
    for family_doc, was_opened_by_us in zip(family_docs, opened_by_us):
        if was_opened_by_us:
            try:
                family_doc.Close(False)
            except Exception as ex:
                logger.warning("Could not close '{}': {}".format(family_doc.Title, ex))

    if not manifest:
        forms.alert(
            "Nothing could be scanned - none of the selected families have "
            "been saved to disk yet.",
            exitscript=True,
        )

    nested_count = len(manifest) - len(top_level_names)

    # Window 1: confirm the export to N: drive.
    forms.alert(
        "Exported {} nested famil{} to:\n\n{}\n\n"
        "({} famil{} total, including the {} you picked.)".format(
            nested_count,
            "y" if nested_count == 1 else "ies",
            OUTPUT_ROOT,
            len(manifest),
            "y" if len(manifest) == 1 else "ies",
            ", ".join(top_level_names),
        ),
        title="Export Complete",
    )

    # Window 2: ask about Notion, separately.
    do_import = forms.alert(
        "Import all {} famil{} into Tyler's Families Audit in Notion "
        "now?".format(len(manifest), "y" if len(manifest) == 1 else "ies"),
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
            import_result = {
                "created": 0,
                "updated": 0,
                "failed": len(manifest),
                "details": [str(ex)],
            }

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    # All interactive prompts are done - safe to open the console now.
    output.print_md(
        "### Scanned {} famil{} - found {} nested famil{} ({} total) - "
        "saved into `{}`".format(
            len(top_level_names),
            "y" if len(top_level_names) == 1 else "ies",
            nested_count,
            "y" if nested_count == 1 else "ies",
            len(manifest),
            OUTPUT_ROOT,
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
    output.print_md("\nManifest written to `{}`".format(MANIFEST_PATH))

    if import_result is not None:
        output.print_md("---")
        output.print_md(
            "### Notion import: {} created, {} updated, {} failed".format(
                import_result["created"],
                import_result["updated"],
                import_result["failed"],
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
