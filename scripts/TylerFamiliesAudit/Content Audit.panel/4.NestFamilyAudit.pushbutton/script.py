# -*- coding: utf-8 -*-
"""
Nest Family Audit
=================

Click the button, pick one or more "mother" (parent) families in the file
picker, and this walks each one's nested-family tree to full depth
(A -> B -> C -> D ...), producing a single FLAT list where every family -
parents, nested families, all of them - is its own row.

Each row carries: Family Name (original name), Revit Category, File Size,
File Location, and the IMMEDIATE (one-level) Parent Family / Child Families
relationships - never the flattened/transitive ancestry (A never lists C
just because A -> B -> C).

The whole flat list is then offered up for import into the "Kitchen Nested
Family Audit" Notion database. Proposed Name and Status columns are left
alone for humans to fill in - re-running never overwrites them.

The nested-family WALK is shared with Tyler's Nested Family Finder
(tyler_audit.extraction); only the Notion target differs
(frank_audit.kitchen_notion_sync).
"""

__title__ = "Nest Family\nAudit"
__author__ = "BBB"

import json
import os

try:
    from pyrevit import forms, script
except ImportError:
    pass

from tyler_audit.extraction import (
    OUTPUT_ROOT,
    entry_for_open_family,
    extract_nested_tree,
)
from frank_audit.kitchen_notion_sync import AUDIT_TARGETS, import_manifest

# Own manifest file, separate from Tyler's _tyler_audit_manifest.json, so the
# two audits never clobber each other's saved run.
MANIFEST_PATH = os.path.join(OUTPUT_ROOT, "_unit_audit_manifest.json")

output = script.get_output()
logger = script.get_logger()


def pick_family_paths():
    """Browse the filesystem for one or more .rfa files (the parent
    families) to audit."""
    paths = forms.pick_file(
        file_ext="rfa",
        multi_file=True,
        title="Select the parent (unit) families to audit",
    )
    if not paths:
        forms.alert("Nothing selected. Nothing to audit.", exitscript=True)
    return paths


def resolve_family_docs(paths):
    """Open the given .rfa paths, reusing already-open documents where
    possible. Returns (family_docs, opened_by_us) - opened_by_us marks which
    ones this tool opened itself (and should close when done), as opposed to
    ones the user already had open.
    """
    app = __revit__.Application  # noqa: F821 (injected by pyRevit at runtime)
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

    with forms.ProgressBar(title="Auditing families ({value} of {max_value})") as pb:
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
                # Already covered (picked twice, or nested inside another
                # family also picked in this same run).
                continue
            manifest.append(entry)
            visited[entry["family_name"]] = entry
            top_level_names.append(entry["family_name"])
            try:
                extract_nested_tree(family_doc, entry, manifest, visited, logger)
            except Exception as ex:
                logger.error(
                    "Nested walk failed for '{}': {}".format(entry["family_name"], ex)
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
            "Nothing could be audited - none of the selected families have "
            "been saved to disk yet.",
            exitscript=True,
        )

    nested_count = len(manifest) - len(top_level_names)

    # Which audit database to import into? (Kitchen vs Bathroom, etc.)
    target = forms.CommandSwitchWindow.show(
        sorted(AUDIT_TARGETS.keys()),
        message="Audited {} picked famil{} + {} nested ({} rows). Import into "
        "which Notion audit? (Esc to skip import)".format(
            len(top_level_names),
            "y" if len(top_level_names) == 1 else "ies",
            nested_count,
            len(manifest),
        ),
    )

    import_result = None
    if target:
        try:
            import_result = import_manifest(manifest, AUDIT_TARGETS[target], logger)
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
        "### Audited {} famil{} - {} nested ({} rows total)".format(
            len(top_level_names),
            "y" if len(top_level_names) == 1 else "ies",
            nested_count,
            len(manifest),
        )
    )
    for item in manifest:
        parent_display = (
            ", ".join(item["parent_families"]) if item["parent_families"] else "-"
        )
        children_display = (
            ", ".join(item["child_families"]) if item["child_families"] else "-"
        )
        output.print_md(
            "- **{}** ({}) — parent: {} — children: {} — {} KB — `{}`".format(
                item["family_name"],
                item["category"],
                parent_display,
                children_display,
                item["file_size_kb"],
                item["file_path"],
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
        output.print_md("\nSkipped Notion import.")


if __name__ == "__main__":
    main()
