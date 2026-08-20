# -*- coding: utf-8 -*-
"""
Shared family-extraction helpers for Tyler's Families Audit tools.

Relationship model: a family that is nested inside another family is that
family's "child"; the host is the "parent". Only the immediate (one-level)
relationship is ever recorded on a given row - if A nests B and B nests C,
then B's parent is A and C's parent is B, but C's parent is never recorded
as A (no transitive/flattened ancestry).

A family can be nested inside more than one different host (e.g. the same
hardware family reused by two different door families) - parent_families
and child_families are therefore both lists, not single values.
"""

import os

import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    BuiltInParameter,
    Element,
    ElementId,
    Family,
    FamilySymbol,
    FilteredElementCollector,
    SaveAsOptions,
)

OUTPUT_ROOT = (
    r"N:\Design Technology Resources\01_BIM CONTENT"
    r"\Content Conformance\0_HOLDING_TYLER"
)
MANIFEST_PATH = os.path.join(OUTPUT_ROOT, "_tyler_audit_manifest.json")


def manifest_path_for(output_root):
    """Manifest path under a caller-chosen root, for tools that let the
    user pick where to save (e.g. Extract Legend Families). Callers that
    always use the default OUTPUT_ROOT can keep using MANIFEST_PATH
    directly instead.
    """
    return os.path.join(output_root, "_tyler_audit_manifest.json")


def elem_name(elem):
    """Name of a Family/ElementType, resolved defensively.

    Some Revit element types expose Name in ways that trip up IronPython's
    dynamic dot-access (AttributeError: Name) depending on API version.
    Try plain access first, then fall back to the base Element.Name
    descriptor, rather than letting one bad element abort extraction.
    """
    try:
        return elem.Name
    except Exception:
        pass
    try:
        return Element.Name.__get__(elem)
    except Exception:
        return "<unnamed {}>".format(elem.Id)


def get_symbol_from_element(doc, elem):
    """Resolve the family symbol/type an element represents.

    Handles:
    - True Legend Components (LEGEND_COMPONENT parameter), which reference
      a model family/type.
    - Any other family-based element - family instances, tags (which
      reference their own tag family - AnnotationSymbolType derives from
      FamilySymbol), detail items - via GetTypeId().

    Uses isinstance(x, FamilySymbol) rather than hasattr(x, "Family")
    duck-typing: hasattr can report a false positive for elements whose
    dynamic attribute resolution in IronPython doesn't reflect a real
    FamilySymbol, which then blows up later on attribute access.
    """
    param = elem.get_Parameter(BuiltInParameter.LEGEND_COMPONENT)
    if param:
        symbol_id = param.AsElementId()
        if symbol_id != ElementId.InvalidElementId:
            symbol = doc.GetElement(symbol_id)
            if isinstance(symbol, FamilySymbol):
                return symbol

    try:
        type_id = elem.GetTypeId()
    except Exception:
        type_id = ElementId.InvalidElementId
    if type_id != ElementId.InvalidElementId:
        elem_type = doc.GetElement(type_id)
        if isinstance(elem_type, FamilySymbol):
            return elem_type

    return None


def get_all_type_names(doc, family):
    """Every type defined on `family`, resolved in `doc` (where it's loaded).

    Collects FamilySymbol elements directly and filters to this family,
    rather than using Family.GetFamilySymbolIds() - that call comes back
    empty for Document.OwnerFamily on a standalone-opened family document
    (the same kind of gap that makes OwnerFamily.Name unreliable), which
    silently dropped every type for a family opened directly rather than
    via EditFamily from a project.
    """
    names = []
    for sym in FilteredElementCollector(doc).OfClass(FamilySymbol):
        try:
            if sym.Family.Id == family.Id:
                names.append(elem_name(sym))
        except Exception:
            continue
    return sorted(names)


def dest_path_for(family_name, category_name, output_root=OUTPUT_ROOT):
    dest_folder = os.path.join(output_root, category_name)
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)
    return os.path.join(dest_folder, "{}.rfa".format(family_name))


def entry_for_open_family(family_doc, family):
    """Manifest entry for a family document that's already open, without
    re-saving it - it's registered using wherever it already lives on
    disk. Returns None if the document has never been saved (no path yet).
    """
    path = family_doc.PathName
    if not path:
        return None
    # Family.Name on Document.OwnerFamily is often blank for a family
    # opened standalone (not via EditFamily from a hosting project) - its
    # name is normally derived from that project context, which doesn't
    # exist here. Document.Title (filename minus extension) is reliable.
    family_name = elem_name(family) or family_doc.Title
    category_name = (
        family.FamilyCategory.Name if family.FamilyCategory else "Uncategorized"
    )
    file_size_kb = round(os.path.getsize(path) / 1024.0, 1)
    return {
        "family_name": family_name,
        "category": category_name,
        "types": get_all_type_names(family_doc, family),
        "parent_families": [],
        "child_families": [],
        "file_path": path,
        "file_size_kb": file_size_kb,
    }


def extract_one_family(host_doc, family, logger, output_root=OUTPUT_ROOT):
    """Edit + Save-As a single family (overwriting any existing file).

    Returns (family_doc, manifest_entry). The caller owns `family_doc` and
    is responsible for closing it once done inspecting it for nested
    families - it's kept open here so the caller can recurse into it.
    Returns (None, None) if the family isn't editable (system/in-place).
    """
    family_name = elem_name(family)
    category_name = (
        family.FamilyCategory.Name if family.FamilyCategory else "Uncategorized"
    )

    if not family.IsEditable:
        logger.warning(
            "Family '{}' is not editable (system/in-place family) - skipped.".format(
                family_name
            )
        )
        return None, None

    dest_path = dest_path_for(family_name, category_name, output_root)
    family_doc = host_doc.EditFamily(family)
    save_opts = SaveAsOptions()
    save_opts.OverwriteExistingFile = True
    family_doc.SaveAs(dest_path, save_opts)
    file_size_kb = round(os.path.getsize(dest_path) / 1024.0, 1)

    entry = {
        "family_name": family_name,
        "category": category_name,
        "types": [],
        "parent_families": [],
        "child_families": [],
        "file_path": dest_path,
        "file_size_kb": file_size_kb,
    }
    return family_doc, entry


def get_nested_families(family_doc):
    """Direct (one-level) nested Family elements loaded in a family doc."""
    try:
        owner_id = family_doc.OwnerFamily.Id
    except Exception:
        owner_id = None
    return [
        f
        for f in FilteredElementCollector(family_doc).OfClass(Family)
        if owner_id is None or f.Id != owner_id
    ]


def extract_nested_tree(family_doc, parent_entry, manifest, visited, logger, output_root=OUTPUT_ROOT):
    """Recursively extract every family nested inside `parent_entry`'s
    family_doc, however deep the nesting goes - each becomes its own
    manifest row, but parent/child links only ever record the immediate
    (one-level) relationship for that row.

    The same family can turn up nested inside more than one host in a
    single scan (e.g. a shared hardware family used by two different door
    families) - that's expected, not an error: it just accumulates an
    extra entry in both sides' parent_families / child_families lists.
    """
    for nested in get_nested_families(family_doc):
        nested_name = elem_name(nested)

        if nested_name not in parent_entry["child_families"]:
            parent_entry["child_families"].append(nested_name)

        if nested_name in visited:
            # Already extracted (possibly via a different host) - link the
            # new parent too, but don't re-extract or recurse into it again.
            nested_entry = visited[nested_name]
            if parent_entry["family_name"] not in nested_entry["parent_families"]:
                nested_entry["parent_families"].append(parent_entry["family_name"])
            continue

        try:
            nested_doc, nested_entry = extract_one_family(
                family_doc, nested, logger, output_root
            )
        except Exception as ex:
            logger.error(
                "Failed to extract nested family '{}': {}".format(nested_name, ex)
            )
            continue
        if nested_entry is None:
            continue

        nested_entry["parent_families"] = [parent_entry["family_name"]]
        nested_entry["types"] = get_all_type_names(family_doc, nested)
        manifest.append(nested_entry)
        visited[nested_name] = nested_entry

        try:
            extract_nested_tree(nested_doc, nested_entry, manifest, visited, logger, output_root)
        finally:
            nested_doc.Close(False)
