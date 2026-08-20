# -*- coding: utf-8 -*-
"""Frank's Content Audit helpers.

Reuses the recursive nested-family extraction from ``tyler_audit.extraction``
(the walk is identical) but syncs the result into a DIFFERENT Notion
database - the "Kitchen Nested Family Audit" table - with its own column
set. Kept separate from ``tyler_audit.notion_sync`` so the two audits can
evolve independently and a change to one never breaks the other.
"""
