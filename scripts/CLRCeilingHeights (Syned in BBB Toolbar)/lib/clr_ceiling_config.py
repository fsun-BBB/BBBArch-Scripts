# Shared configuration helpers for the CLR Ceiling Heights pulldown tools.
import os
import json

_DIR  = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'BBB-pyRevit')
_FILE = os.path.join(_DIR, 'clr_ceiling_settings.json')

DEFAULTS = {
    'search_depth': 20.0,
    'tier3': 8.0,
    'tier2': 7.5,
    'tier1': 7.0,
}

def is_configured():
    return os.path.exists(_FILE)

def load():
    try:
        with open(_FILE, 'r') as f:
            data = json.load(f)
        for k, v in DEFAULTS.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return dict(DEFAULTS)

def save(cfg):
    if not os.path.exists(_DIR):
        os.makedirs(_DIR)
    with open(_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)
