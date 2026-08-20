# -*- coding: utf-8 -*-
"""Select Elevations - pick the elevations to measure, then run.

The full pass: pick the views, confirm what counts as envelope, check each
view's depth, draw, report, refresh the schedule.
"""

__title__ = "Select\nElevations"
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

core.run_pick_views()
