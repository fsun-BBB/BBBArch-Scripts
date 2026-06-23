# _template

Starting point for a new script in this repo. Copy this folder, rename it to your
script's name, and replace the contents.

## Convention

Every script lives in its own folder under `scripts/`:

```
scripts/
└── YourScriptName/
    ├── <code>           # .py, .ps1, or any language
    └── README.md        # what it does, how to run it, parameters
```

- **Folder name**: clear and descriptive (e.g. `FamilyBenchmark`, `SyncAuditedFamilies`).
- **README.md**: required. State what the script does, how to run it, its parameters,
  and any setup (tokens, dependencies, drive paths).
- **Code**: a folder may contain more than one file and mix languages if a tool needs it.

## Python conventions

`template.py` shows the house style enforced by RUFF (see `pyproject.toml`):

- PEP 8 naming, 100-char lines, double quotes.
- Type hints required on all function signatures.
- Google-style docstrings on every public module, class, and function.

```bash
ruff check .     # lint
ruff format .    # format
```
