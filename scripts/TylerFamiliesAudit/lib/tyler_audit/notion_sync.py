# -*- coding: utf-8 -*-
"""
Shared Notion sync helpers for Tyler's Families Audit.

Upserts one row per family (top-level or nested) into the "Revit Families
Audit" Notion database, matched by Family Name.

Updates are merge-based, not overwrite-based: Parent Family, Child Family,
and Type are unioned with whatever is already on the existing row. This
matters because a family can be discovered as nested inside more than one
different host, possibly across separate tool runs (e.g. a shared hardware
family already logged as a standalone row gets a parent added once some
other family is found to nest it) - re-running an import should only ever
add relationships, never erase ones found earlier.

Both column NAMES and TYPES are resolved live from the database schema
rather than hardcoded, since this database gets edited in the Notion UI
over time (columns get renamed - "File Size" -> "File Size (KB)" - and
retyped - Child Family and Parent Family both went from text to
multi_select at different points). Hardcoding either one breaks the import
the moment the schema drifts from what the code assumed. Family Name is
resolved by being the database's title column (every database has exactly
one, so this is structurally guaranteed rather than a name guess); every
other column is resolved by keyword so a rename doesn't break it.
"""

import json
import os

import clr

clr.AddReference("System.Net.Http")
from System.Net.Http import HttpClient, HttpMethod, HttpRequestMessage, StringContent
from System.Net.Http.Headers import MediaTypeWithQualityHeaderValue
from System.Text import Encoding

CONTENT_CONFORMANCE_ROOT = (
    r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance"
)
TOKEN_PATH = os.path.join(CONTENT_CONFORMANCE_ROOT, "notion_token.txt")
DATABASE_ID = "397d917dca758022aa3ae00a2d4472cf"
API_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

HTTP_PATCH = HttpMethod("PATCH")

# manifest field -> keyword(s) that must all appear (case-insensitive) in
# the live column name to match it. Family Name isn't here - it's matched
# structurally (the title column) instead, see resolve_columns().
FIELD_KEYWORDS = {
    "category": ("categor",),
    "types": ("type",),
    "parent_families": ("parent",),
    "child_families": ("child",),
    "file_size_kb": ("size",),
}


def load_token():
    with open(TOKEN_PATH, "r") as f:
        return f.read().strip()


def make_client(token):
    client = HttpClient()
    client.DefaultRequestHeaders.Add("Authorization", "Bearer {}".format(token))
    client.DefaultRequestHeaders.Add("Notion-Version", API_VERSION)
    client.DefaultRequestHeaders.Accept.Add(
        MediaTypeWithQualityHeaderValue("application/json")
    )
    return client


def send(client, method, url, payload=None):
    request = HttpRequestMessage(method, url)
    if payload is not None:
        request.Content = StringContent(
            json.dumps(payload), Encoding.UTF8, "application/json"
        )
    response = client.SendAsync(request).Result
    content = response.Content.ReadAsStringAsync().Result
    if not response.IsSuccessStatusCode:
        raise Exception(
            "Notion API error {}: {}".format(int(response.StatusCode), content)
        )
    return json.loads(content)


def resolve_columns(client):
    """manifest field -> (current column name, current column type).

    Re-resolved on every import_manifest() call so schema edits made in
    Notion between runs (or even mid-session) are always picked up.
    """
    data = send(client, HttpMethod.Get, "{}/databases/{}".format(BASE_URL, DATABASE_ID))
    schema = data.get("properties", {})

    title_name = next((n for n, p in schema.items() if p["type"] == "title"), None)
    if not title_name:
        raise Exception("Database has no title column - can't match Family Name.")

    columns = {"family_name": (title_name, "title")}
    for field, keywords in FIELD_KEYWORDS.items():
        match = next(
            (
                (name, prop["type"])
                for name, prop in schema.items()
                if all(k in name.lower() for k in keywords)
            ),
            None,
        )
        if match is None:
            raise Exception(
                "Could not find a Notion column matching keywords {} for "
                "manifest field '{}'. Current columns: {}".format(
                    keywords, field, sorted(schema.keys())
                )
            )
        columns[field] = match
    return columns


def sanitize_option(name):
    # Notion select/multi_select option names cannot contain commas.
    return name.replace(",", ";").strip()


def _parse_existing_value(prop):
    """Existing property value -> set of plain names, regardless of
    whether it's currently a rich_text, multi_select, or select column."""
    if not prop:
        return set()
    prop_type = prop.get("type")
    if prop_type == "multi_select":
        return set(opt.get("name", "") for opt in prop.get("multi_select", []) if opt.get("name"))
    if prop_type == "select":
        sel = prop.get("select")
        return {sel["name"]} if sel and sel.get("name") else set()
    if prop_type == "rich_text":
        text = "".join(rt.get("plain_text", "") for rt in prop.get("rich_text", [])).strip()
        if not text or text == "N/A":
            return set()
        return set(p.strip() for p in text.split(",") if p.strip() and p.strip() != "N/A")
    return set()


def _build_value(column_type, values, na_if_empty):
    """Build a Notion property payload for `values` (a list of strings),
    shaped according to `column_type` (whatever it currently is)."""
    values = sorted(set(v for v in values if v))
    if column_type == "multi_select":
        if not values and na_if_empty:
            values = ["N/A"]
        return {"multi_select": [{"name": v} for v in values]}
    if column_type == "select":
        return {"select": {"name": values[0]}} if values else {"select": None}
    if column_type == "number":
        return {"number": float(values[0]) if values else None}
    # default to rich_text
    display = ", ".join(values) if values else ("N/A" if na_if_empty else "")
    return {"rich_text": [{"text": {"content": display}}]}


def fetch_existing_pages(client, columns):
    """Map Family Name -> {page_id, parent_families, child_families, types}
    for every existing row, so updates can merge instead of overwrite."""
    title_name, _ = columns["family_name"]
    parent_col, _ = columns["parent_families"]
    child_col, _ = columns["child_families"]
    type_col, _ = columns["types"]

    existing = {}
    url = "{}/databases/{}/query".format(BASE_URL, DATABASE_ID)
    payload = {"page_size": 100}
    while True:
        data = send(client, HttpMethod.Post, url, payload)
        for page in data.get("results", []):
            props = page.get("properties", {})
            title_arr = props.get(title_name, {}).get("title", [])
            if not title_arr:
                continue
            name = title_arr[0].get("plain_text", "")
            if not name:
                continue
            existing[name] = {
                "page_id": page["id"],
                "parent_families": _parse_existing_value(props.get(parent_col)),
                "child_families": _parse_existing_value(props.get(child_col)),
                "types": _parse_existing_value(props.get(type_col)),
            }
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data.get("next_cursor")
    return existing


def build_properties(item, columns, existing_data=None):
    types = set(sanitize_option(t) for t in item.get("types", []) if t)
    parents = set(sanitize_option(p) for p in item.get("parent_families", []) if p)
    children = set(sanitize_option(c) for c in item.get("child_families", []) if c)

    if existing_data:
        types |= existing_data.get("types", set())
        parents |= existing_data.get("parent_families", set())
        children |= existing_data.get("child_families", set())

    title_name, _ = columns["family_name"]
    category_name, category_type = columns["category"]
    type_name, type_type = columns["types"]
    parent_name, parent_type = columns["parent_families"]
    child_name, child_type = columns["child_families"]
    size_name, size_type = columns["file_size_kb"]

    return {
        title_name: {"title": [{"text": {"content": item["family_name"]}}]},
        category_name: _build_value(category_type, [sanitize_option(item["category"])], False),
        type_name: _build_value(type_type, types, False),
        parent_name: _build_value(parent_type, parents, True),
        child_name: _build_value(child_type, children, True),
        size_name: _build_value(size_type, [item.get("file_size_kb", 0)], False)
        if size_type != "number"
        else {"number": item.get("file_size_kb", 0)},
    }


def import_manifest(manifest, logger=None):
    """Upsert every family in `manifest` into the Notion database.

    Returns {"created": n, "updated": n, "failed": n, "details": [str, ...]}.
    """
    token = load_token()
    client = make_client(token)
    columns = resolve_columns(client)
    existing = fetch_existing_pages(client, columns)

    created, updated, failed = 0, 0, 0
    details = []
    for item in manifest:
        name = item["family_name"]
        try:
            existing_data = existing.get(name)
            props = build_properties(item, columns, existing_data)
            if existing_data:
                url = "{}/pages/{}".format(BASE_URL, existing_data["page_id"])
                send(client, HTTP_PATCH, url, {"properties": props})
                updated += 1
                details.append("Updated {}".format(name))
            else:
                url = "{}/pages".format(BASE_URL)
                payload = {"parent": {"database_id": DATABASE_ID}, "properties": props}
                send(client, HttpMethod.Post, url, payload)
                created += 1
                details.append("Created {}".format(name))
        except Exception as ex:
            failed += 1
            details.append("FAILED {}: {}".format(name, ex))
            if logger:
                logger.error("Failed to import '{}': {}".format(name, ex))

    return {"created": created, "updated": updated, "failed": failed, "details": details}
