# -*- coding: utf-8 -*-
"""Configurations - what counts as envelope, and the purge.

Settings live here rather than in the run, so Run Now can ask nothing. Saved per
user, shared by all three buttons.
"""

__title__ = "Config\nurations"
__author__ = "BBB"

import sys

# Force re-import of the envelope package on every run. pyRevit's IronPython
# engine caches sys.modules across button clicks within a session, so without
# this, edits to config_ui.py/core.py keep running the stale cached version
# until Revit restarts.
for _key in list(sys.modules.keys()):
    if _key == 'envelope' or _key.startswith('envelope.'):
        del sys.modules[_key]

from envelope import config_ui

config_ui.show("Save")
