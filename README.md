# BBB Scripts

A collection of Python scripts and utilities developed for BBB Architecture.

## Repository Structure

```
bbb-scripts/
├── scripts/        # Python scripts and tools
├── markdown/       # Markdown documentation and notes
├── doc/            # Extended documentation, specs, and references
├── pyproject.toml  # Project config, dependencies, and RUFF settings
└── README.md
```

## Development Setup

### Prerequisites

- Python 3.11+
- VS Code with extensions: Python, Pylance, Claude Code, RUFF, GitHub

### Getting Started

```bash
# Clone the repo
git clone https://github.com/<your-username>/bbb-scripts.git
cd bbb-scripts

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

## Notes on pyRevit Scripts

Scripts under `scripts/pyrevit/` target pyRevit's embedded IronPython environment and run inside Revit. External packages are difficult to install in that context — keep dependencies minimal and prefer the standard library or pyRevit's bundled libraries.
