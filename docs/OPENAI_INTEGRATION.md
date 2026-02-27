# OpenAI Integration — AI-Assisted Company Research

This document describes the OpenAI multi-agent integration added to the **web-research** toolset. The integration uses three coordinated AI agents to research a company and produce a structured Markdown report without requiring any manual web browsing.

---

## Overview

The pipeline consists of three agents that work in sequence:

| Agent | File | Purpose |
|---|---|---|
| **WebsiteAgent** | `prompts/website_agent.md` | Identifies the company's official website URL |
| **ClassifierAgent** | `prompts/classifier_agent.md` | Selects the most appropriate schema for the company |
| **AnalystAgent** | `prompts/analyst_agent.md` | Generates a structured description and summary |

Each agent has a **customisable system prompt** stored as a Markdown file in the `prompts/` directory, and the analyst uses **schema files** stored in the `schemas/` directory to structure its output.

---

## Prerequisites

1. An **OpenAI API key** — obtain one from [platform.openai.com](https://platform.openai.com).
2. The `openai` Python package (included in `requirements.txt`).

---

## Configuration

Edit `config.yaml` and fill in your API key, or set the `OPENAI_API_KEY` environment variable:

```yaml
openai:
  api_key: 'sk-...'          # or leave blank and use OPENAI_API_KEY env var
  model: 'gpt-4o-mini'       # OpenAI model to use for all agents
  max_subpages: 5            # How many sub-pages to read per company website
  schemas_dir: 'schemas'     # Directory containing schema .md files
  prompts_dir: 'prompts'     # Directory containing agent prompt .md files
```

Environment variable (takes precedence over `config.yaml`):

```bash
export OPENAI_API_KEY="sk-..."
```

---

## Usage

### Interactive Mode

Run the main application and choose option **3 — AI Research**:

```bash
python -m src.main
```

```
Choose input mode - (1) Single company, (2) Batch from companies.csv, (3) AI Research (OpenAI): 3

=== AI Research Mode (OpenAI) ===
Enter company name (or 'q' to quit): Acme Lending
Enter optional context (industry, location, etc.) or press Enter to skip: commercial real estate lender

Researching 'Acme Lending'…
✓ Website identified: https://acmelending.com
✓ Schema applied:     commercial_real_estate
✓ Classifier notes:   Company focuses on CRE bridge loans.

--- Report ---
# Acme Lending

## Company Overview
...
```

### Programmatic Usage

```python
from src.openai_agent import CompanyResearchPipeline

pipeline = CompanyResearchPipeline.from_config()           # reads config.yaml
result = pipeline.run("Acme Lending", context="CRE lender")

print(result["website"])    # https://acmelending.com
print(result["schema"])     # commercial_real_estate
print(result["report"])     # Full Markdown report
```

The `result` dictionary contains:

| Key | Description |
|---|---|
| `company` | The company name provided |
| `website` | URL resolved by the WebsiteAgent |
| `schema` | Schema name selected by the ClassifierAgent |
| `report` | Markdown report produced by the AnalystAgent |
| `website_agent` | Raw JSON output from the WebsiteAgent |
| `classifier_agent` | Raw JSON output from the ClassifierAgent |

---

## Schemas

Schemas are Markdown files in the `schemas/` directory. The filename stem (without `.md`) is the schema name used internally.

### Built-in schemas

| File | Schema name | Use for |
|---|---|---|
| `schemas/general.md` | `general` | Any company that doesn't fit a specific category |
| `schemas/commercial_real_estate.md` | `commercial_real_estate` | CRE lenders, brokers, investors, developers |

### Adding a custom schema

1. Create a new Markdown file in `schemas/`, e.g. `schemas/technology_saas.md`.
2. Structure it with the sections you want the analyst to fill in.
3. The ClassifierAgent will automatically discover it and may select it for matching companies.

Example:

```markdown
# Technology / SaaS Schema

## Company Overview
- **Company Name**: [Full legal name]
- **Product**: [Primary product or platform]
...

## Pricing & Plans
...
```

---

## Customising Agent Prompts

Each agent prompt is a plain Markdown/text file in the `prompts/` directory. Edit these files to change agent behaviour without modifying source code.

| File | Template variables |
|---|---|
| `prompts/website_agent.md` | *(none)* |
| `prompts/classifier_agent.md` | `{schema_list}` — replaced with the list of available schemas |
| `prompts/analyst_agent.md` | `{schema_content}` — the selected schema, `{website_content}` — scraped text |

### Example: restricting the ClassifierAgent

Open `prompts/classifier_agent.md` and add instructions to prefer specific schemas:

```
... (existing prompt) ...

Additional rule: For any company in the real estate sector, always prefer
the commercial_real_estate schema over general.
```

---

## Architecture

```
CompanyResearchPipeline.run(company_name, context)
  │
  ├─ WebsiteAgent.run()          → {"website": "...", "confidence": "...", ...}
  │    └─ reads prompts/website_agent.md
  │
  ├─ _fetch_page_text(website)   → scraped homepage + subpages text
  │    └─ requests + BeautifulSoup (no Selenium required)
  │
  ├─ ClassifierAgent.run()       → {"schema": "...", "confidence": "...", ...}
  │    └─ reads prompts/classifier_agent.md
  │    └─ discovers schemas/*.md
  │
  └─ AnalystAgent.run()          → Markdown report string
       └─ reads prompts/analyst_agent.md
       └─ reads schemas/<selected>.md
```

---

## Error Handling

| Situation | Behaviour |
|---|---|
| `OPENAI_API_KEY` not set | `ValueError` with a clear message |
| `openai` package not installed | `ImportError` with install instructions |
| Website cannot be fetched | Placeholder text included in content; analysis continues |
| Unknown schema returned by classifier | Falls back to `general` schema |
| Prompt file missing | `FileNotFoundError` with the missing file path |

---

## Testing

Unit tests for the integration live in `tests/test_openai_agent.py`. All OpenAI API calls are mocked, so no real API key is needed to run them:

```bash
python -m pytest tests/test_openai_agent.py -v
```
