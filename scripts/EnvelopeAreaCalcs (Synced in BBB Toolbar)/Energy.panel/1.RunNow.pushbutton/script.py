# -*- coding: utf-8 -*-
"""Run Now - measure the elevation that is already open.

Uses whatever is ticked in Configurations and asks nothing, so it is the button
for a second and third pass while tuning a view. The depth check still appears
if the view has no depth limit at all, because that case silently measures the
whole building instead of the facade.
"""

__title__ = "Run\nNow"
__author__ = "BBB"

import sys

# Force re-import of the envelope package on every run. pyRevit's IronPython
# engine caches sys.modules across button clicks within a session, so without
# this, edits to core.py keep running the stale cached version until Revit
# restarts.
for _key in list(sys.modules.keys()):
    if _key == 'envelope' or _key.startswith('envelope.'):
        del sys.modules[_key]

from envelope import core

core.run_active_view()
