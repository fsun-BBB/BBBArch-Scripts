# -*- coding: utf-8 -*-
"""
Standalone re-import of the manifest produced by "Extract Legend Families"
into the "Revit Families Audit" Notion database for Tyler's Families Audit.

Normally the extraction tool offers to do this itself right after
extracting. Use this button if you skipped that prompt, the import failed
partway, or you just want to re-push the same manifest again.

Upserts one row per family, matched by Family Name.
"""

__title__ = "Import to\nNotion"
__author__ = "BBB"

import json
import os

try:
    from pyrevit import forms, script
except ImportError:
    pass

from tyler_audit.extraction import MANIFEST_PATH
from tyler_audit.notion_sync import import_manifest

output = script.get_output()
logger = script.get_logger()


def main():
    if not os.path.exists(MANIFEST_PATH):
        forms.alert(
            "No manifest found at:\n{}\n\nRun 'Extract Legend Families' first.".format(
                MANIFEST_PATH
            ),
            exitscript=True,
        )
    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    if not manifest:
        forms.alert("Manifest is empty - nothing to import.", exitscript=True)

    try:
        result = import_manifest(manifest, logger)
    except Exception as ex:
        forms.alert("Could not reach Notion:\n{}".format(ex), exitscript=True)
        return

    output.print_md(
        "### Notion import complete: {} created, {} updated, {} failed".format(
            result["created"], result["updated"], result["failed"]
        )
    )
    for line in result["details"]:
        output.print_md("- {}".format(line))


if __name__ == "__main__":
    main()
