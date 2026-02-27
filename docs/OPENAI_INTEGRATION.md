# OpenAI Integration

The project uses a three-agent OpenAI pipeline for company research:

1. `WebsiteAgent` — identifies the official company website
2. `ClassifierAgent` — selects the best schema from `schemas/`
3. `AnalystAgent` — generates the structured markdown report

## Configuration

Set OpenAI settings in `config.yaml`:

```yaml
openai:
  api_key: ''
  model: 'gpt-4o-mini'
  max_subpages: 5
  schemas_dir: 'schemas'
  prompts_dir: 'prompts'
```

Or set `OPENAI_API_KEY` in your environment.

## Runtime modes

Run `python -m src.main` and choose one mode:

- `1` — AI interactive research
- `2` — AI batch research from `companies.csv`

## Programmatic use

```python
from src.openai_agent import CompanyResearchPipeline

pipeline = CompanyResearchPipeline.from_config()
result = pipeline.run("Acme Lending", context="commercial real estate lender")

print(result["website"])
print(result["schema"])
print(result["report"])
```

## Prompt and schema customization

- Agent prompts are in `prompts/`
- Output schemas are in `schemas/`
- New schema files are auto-discovered by filename stem

## Output

Saved report files include YAML metadata such as:

- `website`
- `date`
- `focus`
- `firm_type`
- `source`
- `schema`
