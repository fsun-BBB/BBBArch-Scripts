# -*- coding: utf-8 -*-
"""
Notion sync for Frank's "Kitchen Nested Family Audit".

Target is a Notion DATABASE (created inline on the Kitchen Nested Family
Audit page) with typed columns:

    Family Name     title
    File Size (KB)  number      <- manifest file_size_kb, as-is
    Proposed Name   rich_text   <- reference name; NEVER written by the tool
    Revit Category  multi_select
    File Location   rich_text   <- path to the .rfa the walk recorded
    Status          select      <- Audited / Guardian Passed / Manually Cleaned
    Parent Family   multi_select
    Child Families  multi_select
    Types           multi_select <- the family's type/variant names

(The page originally held a plain *table block*, which can't carry
multi_select/select columns - that's why this was rebuilt as a database.)

Upsert model, matched by Family Name (the title column):
  - Family Name / File Size / Revit Category / File Location -> replaced
    with the freshly-walked value.
  - Parent Family / Child Families -> MERGED (union) with the options
    already on the row, so a shared nested family found under two parents
    accumulates both links instead of one overwriting the other.
  - Status -> set to "Guardian Passed" on CREATE only; on update it's left
    alone so a human's later change (e.g. "Manually Cleaned") survives.
  - Proposed Name -> never touched; it's a human/reference field.

Column NAMES are resolved live from the schema by keyword so a rename in
the Notion UI doesn't break the import; the column TYPES are assumed to be
the ones above.
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

# Inline databases created on page 3a3d917d-ca75-80a1-b4f7-c9f04b0d48c6.
# The kitchen and bathroom unit audits use identical schemas but separate
# databases, chosen at import time.
KITCHEN_DATABASE_ID = "3a3d917d-ca75-81f7-8e23-f779ce6fe15f"
BATHROOM_DATABASE_ID = "3a3d917d-ca75-81ce-b86b-d06386b2e588"

# Selectable targets, keyed by the label the tool shows in its prompt.
AUDIT_TARGETS = {
    "Kitchen": KITCHEN_DATABASE_ID,
    "Bathroom": BATHROOM_DATABASE_ID,
}
API_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

HTTP_PATCH = HttpMethod("PATCH")

DEFAULT_STATUS = "Guardian Passed"
MAX_OPTION_CHARS = 100  # Notion multi_select / select option-name limit

# "System"/annotation helper families to omit from the audit entirely - they
# get auto-loaded into content families but aren't BBB content themselves.
# Excluded rows are never created, and their names are scrubbed out of the
# Parent Family / Child Families of the rows that are kept.
EXCLUDED_CATEGORIES = ("generic annotations", "section marks", "detail items")
EXCLUDED_NAMES = ("ADA Clearance Lines",)


def _is_excluded(item):
    category = (item.get("category") or "").lower()
    return category in EXCLUDED_CATEGORIES or item.get("family_name") in EXCLUDED_NAMES

# manifest field -> keyword(s) that must all appear (case-insensitive) in
# the live column name. Family Name is matched structurally (title column);
# Proposed Name is intentionally absent so it's never written.
FIELD_KEYWORDS = {
    "file_size_kb": ("size",),
    "category": ("categor",),
    "file_path": ("location",),
    "parent_families": ("parent",),
    "child_families": ("child",),
    "types": ("type",),
    "status": ("status",),
}
MERGE_KEYS = ("parent_families", "child_families", "types")


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


def resolve_columns(client, database_id):
    """manifest field -> current column name (types are assumed).

    Re-resolved every run so a rename in Notion is picked up; raises with
    the live column list if a keyword matches nothing.
    """
    data = send(client, HttpMethod.Get, "{}/databases/{}".format(BASE_URL, database_id))
    schema = data.get("properties", {})

    title_name = next((n for n, p in schema.items() if p["type"] == "title"), None)
    if not title_name:
        raise Exception("Database has no title column - can't match Family Name.")

    columns = {"family_name": title_name}
    for field, keywords in FIELD_KEYWORDS.items():
        match = next(
            (n for n in schema if all(k in n.lower() for k in keywords)), None
        )
        if match is None:
            raise Exception(
                "No Notion column matching keywords {} for field '{}'. "
                "Columns: {}".format(keywords, field, sorted(schema.keys()))
            )
        columns[field] = match
    return columns


def _num(kb):
    try:
        return float(kb)
    except (TypeError, ValueError):
        return None


def _option(name):
    name = (name or "").replace(",", ";").strip()  # commas illegal in option names
    if len(name) > MAX_OPTION_CHARS:
        name = name[:MAX_OPTION_CHARS]
    return name


def _multi_select(names):
    seen, out = set(), []
    for n in names:
        n = _option(n)
        if n and n not in seen:
            seen.add(n)
            out.append({"name": n})
    return {"multi_select": out}


def _rich_text(text):
    return {"rich_text": [{"text": {"content": text}}] if text else []}


def fetch_existing_pages(client, columns, database_id):
    """Family Name -> {page_id, parent_families:set, child_families:set} for
    every existing row, so the multi_selects can merge instead of overwrite."""
    title_name = columns["family_name"]
    existing = {}
    url = "{}/databases/{}/query".format(BASE_URL, database_id)
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
            row = {"page_id": page["id"]}
            for key in MERGE_KEYS:
                opts = props.get(columns[key], {}).get("multi_select", [])
                row[key] = set(o.get("name", "") for o in opts if o.get("name"))
            existing[name] = row
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data.get("next_cursor")
    return existing


def build_properties(item, columns, existing_data=None):
    parents = set(item.get("parent_families", []))
    children = set(item.get("child_families", []))
    types = set(item.get("types", []))
    if existing_data:
        parents |= existing_data.get("parent_families", set())
        children |= existing_data.get("child_families", set())
        types |= existing_data.get("types", set())

    props = {
        columns["family_name"]: {"title": [{"text": {"content": item["family_name"]}}]},
        columns["file_size_kb"]: {"number": _num(item.get("file_size_kb"))},
        columns["category"]: _multi_select([item.get("category")]),
        columns["file_path"]: _rich_text(item.get("file_path", "")),
        columns["parent_families"]: _multi_select(parents),
        columns["child_families"]: _multi_select(children),
        columns["types"]: _multi_select(types),
    }
    # Status: stamp the default on new rows only; leave existing rows'
    # Status alone so a human's later change is never overwritten.
    if not existing_data:
        props[columns["status"]] = {"select": {"name": DEFAULT_STATUS}}
    return props


def import_manifest(manifest, database_id, logger=None):
    """Upsert every family in `manifest` into the given audit database.

    Returns {"created": n, "updated": n, "failed": n, "details": [str, ...]}.
    """
    token = load_token()
    client = make_client(token)
    columns = resolve_columns(client, database_id)
    existing = fetch_existing_pages(client, columns, database_id)

    # Drop excluded (system/annotation) families, and remember their names so
    # they can be scrubbed from the kept rows' parent/child relationships too.
    excluded_names = set(it["family_name"] for it in manifest if _is_excluded(it))
    manifest = [it for it in manifest if not _is_excluded(it)]

    created, updated, failed = 0, 0, 0
    details = []
    for item in manifest:
        name = item["family_name"]
        try:
            # Scrub references to excluded families out of this row's links.
            item = dict(
                item,
                parent_families=[
                    p for p in item.get("parent_families", []) if p not in excluded_names
                ],
                child_families=[
                    c for c in item.get("child_families", []) if c not in excluded_names
                ],
            )
            existing_data = existing.get(name)
            props = build_properties(item, columns, existing_data)
            if existing_data:
                url = "{}/pages/{}".format(BASE_URL, existing_data["page_id"])
                send(client, HTTP_PATCH, url, {"properties": props})
                updated += 1
                details.append("Updated {}".format(name))
            else:
                url = "{}/pages".format(BASE_URL)
                payload = {"parent": {"database_id": database_id}, "properties": props}
                send(client, HttpMethod.Post, url, payload)
                created += 1
                details.append("Created {}".format(name))
        except Exception as ex:
            failed += 1
            details.append("FAILED {}: {}".format(name, ex))
            if logger:
                logger.error("Failed to import '{}': {}".format(name, ex))

    return {"created": created, "updated": updated, "failed": failed, "details": details}


def import_manifest_kitchen(manifest, logger=None):
    """Back-compat wrapper: import into the Kitchen audit database."""
    return import_manifest(manifest, KITCHEN_DATABASE_ID, logger)


def import_manifest_bathroom(manifest, logger=None):
    """Import into the Bathroom audit database."""
    return import_manifest(manifest, BATHROOM_DATABASE_ID, logger)
