# Company Research — Multi-Agent AI Pipeline

This project is an **AI-only company research system** powered by a multi-agent OpenAI workflow. It no longer includes manual scraping, browser/TUI workflows, or Selenium-based navigation.

## What it does

1. Identifies a company's official website with `WebsiteAgent`
2. Classifies the company into a **schema class** with `ClassifierAgent` (skipped when you specify the class explicitly)
3. Generates a structured Markdown report with `AnalystAgent`, guided by a **two-schema system** (extraction + output format)
4. Saves reports to `data/companies/<Company>/markdown/` with YAML metadata
5. Optionally merges generated Markdown files into a flat database using `scripts/merge_markdown_db.py`, initialising new database entries from a **per-class template**

## Architecture

| File | Purpose |
|---|---|
| `src/openai_agent.py` | Core multi-agent pipeline; exports `CompanyResearchPipeline` and `CompanyResearchOutput` |
| `src/main.py` | Interactive and batch runners |
| `prompts/` | Editable system prompts for each agent |
| `schemas/` | Schema class directories (see below) |
| `src/store.py` | Markdown/front-matter persistence helpers |
| `scripts/merge_markdown_db.py` | Merge tool: adds per-company Markdown into a flat DB |
| `scripts/merge_existing_data.py` | Merge-only tool for already-existing Markdown files |

---

## Installation

```bash
python -m venv .venv
.\.venv\Scripts\activate        # Windows
source .venv/bin/activate       # macOS / Linux
python -m pip install -r requirements.txt
```

---

## Configuration

Edit `config.yaml`:

```yaml
openai:
  api_key: ''              # or set OPENAI_API_KEY environment variable
  model: 'gpt-4o-mini'
  max_subpages: 5
  schemas_dir: 'schemas'   # directory containing schema class subdirectories
  prompts_dir: 'prompts'   # directory containing agent prompt markdown files

storage:
  base_dir: 'data/companies'
  database_dir: 'company_markdown_db/companies'
  # template_path: ''      # optional fallback template for new database files
```

You can supply `OPENAI_API_KEY` via:

- Environment variable
- `.env.local` or `.env` file in the repo root

---

## Schema Classes — Two-Schema System

Each **schema class** is a subdirectory under `schemas/` that contains up to three files:

```
schemas/
  general/
    extraction.md   ← what data to extract from the company website
    output.md       ← how to format / structure the stored Markdown
    template.md     ← template used when creating a new database file
  commercial_real_estate/
    extraction.md
    output.md
    template.md
```

### `extraction.md` — extraction schema

Instructs the `AnalystAgent` on **what information to gather** from the company's website. Write this as a list of sections and bullet points describing the fields you want extracted. The title line (any `# Heading` at the top) is stripped automatically before it is injected into the agent prompt.

Example (`schemas/commercial_real_estate/extraction.md`):

```markdown
Use this schema to extract information about CRE companies.

## Company Overview
- **Firm Type**: [investor, lender, broker, advisor, REIT, developer]
- **Geographic Focus**: [markets or regions served]

## Loan Programs / Investment Strategies
[describe loan types, LTV, deal sizes]
...
```

### `output.md` — output format schema

Instructs the `AnalystAgent` on **how to structure and format its output**. This controls the section headings that appear in the stored Markdown report.

Example (`schemas/commercial_real_estate/output.md`):

```markdown
## Overview
[1–2 sentence summary]

## Description
[2–3 paragraph narrative]

## Loan Programs / Investment Strategies
[deal structures and specifics]

## Property Types
- [type 1]
- [type 2]
```

### `template.md` — database template

The template that is used when **creating a new database file** for a company. It should contain the YAML front-matter fields you want pre-populated (left blank) and the section headings for the database entry. New research content is inserted under the `## Basic Underwriting` heading.

Example (`schemas/commercial_real_estate/template.md`):

```markdown
---
website:
date:
focus:
firm_type:
source:
schema:
prop_type:
loan_type:
---

## Basic Underwriting

## Overview

## Description

## Loan Programs / Investment Strategies

## Property Types

## Loan / Deal Size
```

### Adding a new schema class

1. Create a new subdirectory under `schemas/`, e.g. `schemas/private_equity/`
2. Add `extraction.md` (required), `output.md` (recommended), and `template.md` (recommended)
3. The new class is automatically available for selection in interactive and batch modes

---

## Usage

```bash
python -m src.main
```

### Mode 1 — AI Interactive (single company)

```
=== AI Research Mode (Interactive) ===

Enter company name (or 'q' to quit): Acme Capital
Available schema classes: commercial_real_estate, general
Enter schema class for this company (or press Enter to auto-detect): commercial_real_estate
Enter optional context (industry, location, etc.) or press Enter to skip:
```

- You are shown the list of available schema classes and can choose one directly.
- If you press **Enter** without typing a class, the `ClassifierAgent` automatically picks the best match based on the company's website content.
- The optional context prompt remains available and is passed to the `WebsiteAgent` to help identify the correct company website.

### Mode 2 — AI Batch (CSV file)

Create `companies.csv` in the project root:

```csv
company,source,firm_type,schema_class
Acme Capital,newsletter,Debt Fund,commercial_real_estate
Bright Bridge,conference,Bridge Lender,commercial_real_estate
Startup Inc,,,general
Other Co,,,
```

| Column | Description |
|---|---|
| `company` | **Required.** Company name to research |
| `source` | Optional. Written into the `source` metadata field |
| `firm_type` | Optional. Merged with any AI-inferred firm type |
| `schema_class` | Optional. Explicitly set the schema class; if blank the ClassifierAgent auto-detects |

Run:

```bash
python -m src.main
# Choose option 2
```

After processing you are asked whether to remove processed rows from `companies.csv` (for resumable batch runs).

---

## Metadata fields

| Field | Interactive | Batch (`companies.csv`) |
|---|---|---|
| `source` | Prompted every run | Provide a `source` column |
| `firm_type` | AI infers; you can keep, replace, or extend | AI infers; optionally override with `firm_type` column |
| `schema_class` | You choose at the prompt (or auto-detect) | Provide a `schema_class` column |

**Note:** `source` is never populated automatically — it must come from user input or the CSV.

---

## Structured Output

`CompanyResearchPipeline.run()` returns a dict that includes a `structured_output` key containing a `CompanyResearchOutput` Pydantic model:

```python
from src.openai_agent import CompanyResearchPipeline

pipeline = CompanyResearchPipeline.from_config()
result = pipeline.run("Acme Corp", schema_class="commercial_real_estate")

out = result["structured_output"]  # CompanyResearchOutput
print(out.company)      # "Acme Corp"
print(out.website)      # resolved URL
print(out.schema_class) # "commercial_real_estate"
print(out.report)       # Markdown report
```

---

## Merge generated output into the database

```bash
python scripts/merge_markdown_db.py
```

The merge tool:
1. Reads source files from `data/companies/<Company>/markdown/`
2. Reads the `schema:` field from each source file's YAML front matter
3. For **new** database entries, loads `schemas/<schema_class>/template.md` as the initial file content
4. Inserts research content under the `## Basic Underwriting` heading
5. Merges YAML metadata (appending list fields like `firm_type` and `focus`)

To merge existing Markdown files without re-running research:

```bash
python scripts/merge_existing_data.py
```

### Custom template fallback

If you want a single fallback template for all schema classes (e.g. an Obsidian vault template), set `storage.template_path` in `config.yaml`:

```yaml
storage:
  template_path: '/path/to/my/vault/templates/company template.md'
```

The per-class template (`schemas/<class>/template.md`) always takes priority over this fallback.

---

## Testing

```bash
python -m pytest
```

For OpenAI pipeline tests only:

```bash
python -m pytest tests/test_openai_agent.py -v
```

