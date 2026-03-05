# Company Research — AI Multi-Agent Pipeline

This repository researches companies using an OpenAI multi-agent workflow, stores structured markdown reports, and merges those reports into a flat markdown database.

Detailed internals are documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Overview

The pipeline has three AI stages:
1. `WebsiteAgent` resolves the official company website.
2. `ClassifierAgent` chooses a schema class (unless you provide one explicitly).
3. `AnalystAgent` produces a structured markdown report using schema instructions.

Outputs are written under `data/companies/<Company>/markdown/` with YAML front matter metadata. Merge utilities then consolidate per-company files into one database markdown file per company.

## Repository Structure

### Core source (`src/`)

| Path | Responsibility |
|---|---|
| `src/main.py` | CLI entrypoint for interactive and batch research modes |
| `src/openai_agent.py` | Agent implementations + `CompanyResearchPipeline` orchestration |
| `src/store.py` | Markdown/front-matter read-write helpers and metadata normalization |
| `src/config.py` | Configuration loading and storage path resolution |
| `src/entity_resolution.py` | Matching logic used by merge flows |

### Prompt and schema content

| Path | Responsibility |
|---|---|
| `prompts/` | Agent system prompts (`website_agent.md`, `classifier_agent.md`, `analyst_agent.md`) |
| `schemas/<class>/extraction.md` | What information to extract |
| `schemas/<class>/output.md` | How to format report output |
| `schemas/<class>/template.md` | Base template for new DB entries |

### Merge and utility scripts (`scripts/`)

| Path | Responsibility |
|---|---|
| `scripts/merge_markdown_db.py` | Merge researched markdown into DB interactively |
| `scripts/merge_existing_data.py` | Merge-only mode for pre-existing markdown data |

### Tests

- `tests/` contains the main automated test suite.
- Root-level `test_*.py` files exist for targeted/legacy scenarios and compatibility checks.

## Workflow and Logic

### 1) Research phase (`python -m src.main`)

For each company:
1. Resolve website from company name.
2. Fetch homepage + subpage text.
3. Determine schema class (auto or explicit).
4. Generate markdown report with schema-driven structure.
5. Save report with metadata YAML in `data/companies/.../markdown/`.

Important logic notes:
- `source` metadata is never auto-guessed; it must come from user input (interactive) or CSV (`batch`).
- `firm_type` is merged when both AI and CSV values exist.
- List-like fields (`focus`, `firm_type`, `source`, etc.) are normalized for consistent YAML output.

### 2) Merge phase (`scripts/merge_markdown_db.py` or `scripts/merge_existing_data.py`)

For each company folder under the configured source directory:
1. Detect company identity against existing DB files.
2. Choose/create destination markdown file.
3. Resolve schema template (class template first, fallback template second).
4. Append new content while preserving/merging metadata.
5. Remove processed source folder (unless keep-source mode is enabled).

Entity matching uses probabilistic linkage when available, with deterministic fallback behavior when optional dependencies are missing.

## Installation

```bash
python -m venv .venv
.\.venv\Scripts\activate        # Windows
source .venv/bin/activate       # macOS / Linux
python -m pip install -r requirements.txt
```

## Configuration

Edit `config.yaml`:

```yaml
openai:
  api_key: ''
  model: 'gpt-4o-mini'
  max_subpages: 5
  schemas_dir: 'schemas'
  prompts_dir: 'prompts'

storage:
  database_dir: 'company_markdown_db/companies'
  # template_path: ''
```

Path resolution rules:
- Source reports are always read/written under `data/companies`.
- `storage.database_dir` controls DB output path.
- Relative paths resolve from the config file directory.
- Absolute paths are used directly.

OpenAI API key sources (in priority order):
1. Explicit config value
2. `OPENAI_API_KEY` environment variable
3. `.env.local` / `.env`
4. Windows persisted environment variable

## Schema System

Each schema class directory can include:
- `extraction.md` (required): extraction instructions
- `output.md` (recommended): section/output format contract
- `template.md` (recommended): new DB file layout

Example layout:

```text
schemas/
  general/
    extraction.md
    output.md
    template.md
  commercial_real_estate/
    extraction.md
    output.md
    template.md
```

To add a new schema class, create a new subdirectory with these files.

## Usage

### Interactive mode

```bash
python -m src.main
```

Choose mode `1` and enter company names one at a time.

### Batch mode (CSV)

Create `companies.csv`:

```csv
company,source,firm_type,schema_class
Acme Capital,newsletter,Debt Fund,commercial_real_estate
Bright Bridge,conference,Bridge Lender,commercial_real_estate
Startup Inc,,,general
Other Co,,,
```

Column semantics:
- `company` (required)
- `source` (optional metadata)
- `firm_type` (optional; merged with AI value)
- `schema_class` (optional; if omitted classifier auto-detects)

Run and choose mode `2`:

```bash
python -m src.main
```

### Merge researched markdown into database

```bash
python scripts/merge_markdown_db.py --config config.yaml
```

### Merge only existing markdown data

```bash
python scripts/merge_existing_data.py --config config.yaml
```

Keep source folders after merge:

```bash
python scripts/merge_existing_data.py --keep-merged-source --config config.yaml
```

## Programmatic API

`CompanyResearchPipeline.run()` returns a dict with key fields:
- `company`
- `website`
- `schema`
- `report`
- `website_agent`
- `classifier_agent`
- `structured_output` (`CompanyResearchOutput` Pydantic model)

Example:

```python
from src.openai_agent import CompanyResearchPipeline

pipeline = CompanyResearchPipeline.from_config()
result = pipeline.run("Acme Corp", schema_class="commercial_real_estate")

structured = result["structured_output"]
print(structured.company)
print(structured.website)
print(structured.schema_class)
```

## Testing

Run full suite:

```bash
python -m pytest -q
```

Run a focused module:

```bash
python -m pytest tests/test_openai_agent.py -v
```

## Additional Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): execution flow, module responsibilities, and data model
- [docs/OPENAI_INTEGRATION.md](docs/OPENAI_INTEGRATION.md): quick OpenAI-specific integration notes

## Troubleshooting

- `companies.csv not found`: ensure the file exists in project root when using batch mode.
- No API key error: set `OPENAI_API_KEY` or `openai.api_key` in `config.yaml`.
- No merge output: verify source files exist under `data/companies/<Company>/markdown/`.
- Unexpected matching behavior during merge: review candidate prompts and schema metadata in source markdown front matter.

