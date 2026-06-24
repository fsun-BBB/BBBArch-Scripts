# BBB Scripts

A collection of Python scripts and utilities developed for BBB Architecture.

## Repository Structure

```
BBBArch-Scripts/
├── scripts/        # One folder per script/tool — see "Layout" below
├── markdown/       # Markdown documentation and notes
├── doc/            # Extended documentation, specs, and references
├── pyproject.toml  # Project config, dependencies, and RUFF settings
└── README.md
```

### Layout

Every script gets its own folder under `scripts/`, holding all of its code (any
language) plus a `README.md` describing it:

```
scripts/
├── _template/                  # Starting point — copy this for a new script
├── FamilyBenchmark/            # pyRevit (IronPython) — scores .rfa families
├── SyncAuditedFamilies/        # PowerShell — Notion → AUDITED folder sync
├── CLRCeilingHeights/          # pyRevit pulldown — ceiling clear-height calc + tags
└── Frank Tools.extension/      # Full pyRevit extension (dev toolbar), version-controlled
```

Folder names are descriptive; a folder may mix languages if a tool needs it. A folder
ending in `.extension` is a complete pyRevit extension kept under version control (Revit
loads it via a pyRevit Custom Extension Directory — see that folder's README).

## Development Setup

### Prerequisites

- Python 3.11+
- VS Code with extensions: Python, Pylance, Claude Code, RUFF, GitHub

### Getting Started

```bash
# Clone the repo
git clone https://github.com/fsun-BBB/BBBArch-Scripts.git
cd BBBArch-Scripts

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -e ".[dev]"
```

### Linting & Formatting

[RUFF](https://docs.astral.sh/ruff/) handles both linting and formatting.

```bash
ruff check .        # lint
ruff format .       # format
```

RUFF is configured in `pyproject.toml`.

## Code Conventions

- **Style**: PEP 8 naming throughout.
- **Type hints**: Required on all function signatures.
- **Docstrings**: Google style, required on all public functions, classes, and modules.
- **Environments**: One venv per repo — never install globally.

## Scripts

| Script | Lang | Description |
|--------|------|-------------|
| [FamilyBenchmark](scripts/FamilyBenchmark/) | pyRevit / Python | Batch-analyses `.rfa` files for efficiency, cleanliness, and geometry complexity. Scores each family under three weighted configs, writes results to Notion, and exports a CSV. |
| [SyncAuditedFamilies](scripts/SyncAuditedFamilies/) | PowerShell | Queries the Notion Revit Families database for a given Review Status (default `Cleaned`) and copies each source `.rfa` to the AUDITED folder, renaming to the Proposed Name and writing the destination path back to Notion. |
| [CLRCeilingHeights](scripts/CLRCeilingHeights/) | pyRevit / Python | Ceiling clear-height (ceiling-to-floor) calculator and tagger, plus clearance check and config. Snapshot of the production tool in `BBB-pyRevit-Toolbar`. |
| [Frank Tools.extension](scripts/Frank%20Tools.extension/) | pyRevit extension | Full dev toolbar (FamilyBenchmark, FamilyOptimizer, GeoReducer, ParamAudit, PurgeUnused, CeilingHeights) plus pyRevit starter-kit boilerplate. Load via a pyRevit Custom Extension Directory. |

> **pyRevit note:** scripts that run inside Revit target pyRevit's embedded IronPython
> environment. External packages are hard to install there — keep dependencies minimal and
> prefer the standard library or pyRevit's bundled libraries.
