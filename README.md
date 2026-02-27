# Company Research — Multi-Agent AI Pipeline

This project is now an **AI-only company research system** powered by a multi-agent OpenAI workflow.
It no longer includes manual scraping, browser/TUI workflows, or Selenium-based navigation.

## What it does

- Identifies a company website with `WebsiteAgent`
- Classifies the company against available schemas with `ClassifierAgent`
- Generates a structured markdown report with `AnalystAgent`
- Saves reports to `data/companies/<Company>/markdown` with YAML metadata
- Optionally merges generated markdown into a flat DB using `scripts/merge_markdown_db.py`

## Architecture

- `src/openai_agent.py` — core multi-agent pipeline
- `src/main.py` — AI interactive and AI batch runners
- `prompts/` — editable system prompts per agent
- `schemas/` — editable markdown schemas for classification + output structure
- `src/store.py` — markdown/front-matter persistence
- `scripts/merge_markdown_db.py` and `scripts/merge_existing_data.py` — post-processing merge tools

## Installation

```bash
python -m venv .venv
.\.venv\Scripts\activate
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
  base_dir: 'data/companies'
  database_dir: 'company_markdown_db/companies'
```

You can also set `OPENAI_API_KEY` as an environment variable.

## Usage

Run:

```bash
python -m src.main
```

Modes:

1. **AI Interactive** — research one company at a time
2. **AI Batch** — process `companies.csv` end-to-end

Both modes support saving reports and appending metadata. Batch mode can remove processed rows from `companies.csv` for resumable runs.

## Merge generated output

```bash
python scripts/merge_markdown_db.py
```

Merge-only existing files:

```bash
python scripts/merge_existing_data.py
```

## Testing

```bash
python -m pytest
```

For OpenAI pipeline tests only:

```bash
python -m pytest tests/test_openai_agent.py -v
```
