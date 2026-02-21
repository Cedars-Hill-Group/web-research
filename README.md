# Company Research — Web Scraping & Markdown Export

A small toolset for quickly finding company websites, browsing them in a lightweight browser interface, marking pages to scrape, and exporting cleaned Markdown files with helpful metadata.

---

## 🔍 What it does

- Search for a company's official site and present candidate pages.
- Use a browser-driven TUI to open pages and *scrape* the current page using the TUI action (press **g** to "Scrape current page").
- Convert marked pages to cleaned Markdown suitable for note-taking or importing into personal knowledge bases.
- Provide batch processing (from `companies.csv`) and a merge tool to append scraped content into a flat company database.

---

## ✅ Key features

- Robust HTML-to-Markdown pipeline in `src/convert.py` using Readability + heuristics to remove boilerplate and preserve useful sections such as team/press when detected.
- Metadata written into YAML front matter: `website`, `date`, `focus`.
- Interactive TUI (`src/ui_tui.py`) for scraping, previewing, and saving pages.
- Batch mode (`companies.csv`) with optional per-company focus prompting, and a merge tool to consolidate markdown into `company_markdown_db/companies/`.
- **AI Research mode** — multi-agent OpenAI pipeline that identifies a company's website, classifies the company, and generates a structured Markdown report using customisable schema files (see [docs/OPENAI_INTEGRATION.md](docs/OPENAI_INTEGRATION.md)).

---

## Repository layout

```
.
├── README.md
├── requirements.txt
├── config.yaml            # filters, scrape options, and OpenAI settings
├── companies.csv          # optional CSV with company names for batch runs
├── prompts/               # agent system prompts (Markdown, editable)
├── schemas/               # company type schemas (Markdown, editable/extensible)
├── scripts/               # helper scripts (merge tool, demos)
├── data/                  # saved raw HTML + markdown per company
├── docs/                  # additional documentation
├── src/                   # application code
└── tests/                 # unit tests
```

---

## Installation

1. Create a Python virtual environment and activate it:

   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate     # Windows
   source .venv/bin/activate      # macOS/Linux
   ```

2. Install requirements:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. (Optional) Install `pytest` for running tests:

   ```bash
   python -m pip install pytest
   ```

---

## Configuration

Edit `config.yaml` to set filters and user-agent options for scraping. Example entries:

```yaml
scrape:
  user_agent: "MyScraper/1.0"
filters:
  include_paths: ["/team", "/about", "/press"]
```

For the **AI Research mode** add your OpenAI API key (or set the `OPENAI_API_KEY` environment variable):

```yaml
openai:
  api_key: 'sk-...'
  model: 'gpt-4o-mini'
  max_subpages: 5
```

See [docs/OPENAI_INTEGRATION.md](docs/OPENAI_INTEGRATION.md) for full OpenAI configuration details.

---

## Usage

Run the app:

```bash
python -m src.main
```

You will be prompted to choose **Single**, **Batch**, or **AI Research** mode.

### AI Research mode (OpenAI)

Choose option **3** and enter a company name. The pipeline will:
1. Use OpenAI to identify the company's official website.
2. Scrape the homepage and up to `max_subpages` sub-pages.
3. Classify the company and select the appropriate schema.
4. Generate a structured Markdown report.

You will be offered the option to save the report to the `data/companies/` directory.

See [docs/OPENAI_INTEGRATION.md](docs/OPENAI_INTEGRATION.md) for full details, programmatic usage, and how to add custom schemas.

Single mode
- Enter a company name, pick the candidate site, the TUI will open the site.
- In the TUI press `g` to scrape the currently-open page, `c` to commit scraped pages, or `f` to save and finish. You'll be prompted for an optional **focus** value when a company is accepted.

Batch mode
- Populate `companies.csv` with company names (header `company` or `name`).
- Choose batch mode and optionally set `Prompt for each company` to `y` to confirm results per company.
- When running batch, you'll be prompted for an optional focus value per company (you can leave it blank to skip).

Scraping from the TUI
- Use **g** in the TUI to scrape the currently-open page; scraped pages are staged in-session and committed using **c** (or saved&finished with **f**).
- The in-page 'mark' widget and hotkey have been removed; scraping is explicit via the TUI or programmatically using `fetch_html(driver, url)`.

### TUI Quick Reference (Keybindings) 🔧

- **g** — Scrape the currently-open page (stage it in-session)
- **l** — List scraped pages in the preview pane
- **c** — Commit scraped pages to disk (writes per-page markdown + raw HTML)
- **e** — Edit the selected scraped item using your `$EDITOR` (Notepad on Windows)
- **d** — Delete the selected scraped item from the session
- **f** — Save & finish (commit then exit)
- **q** — Quit the TUI without saving

Tip: Use **l** to view staged pages and preview them before editing or deleting; use `fetch_html(driver, url)` for programmatic/headless captures.

Merge tool
- After you have scraped files, run:

```bash
python scripts/merge_markdown_db.py
```

This appends unique markdown blocks into `company_markdown_db/companies/<company-slug>.md` using fuzzy matching and de-duplication.

---

## Testing

Run the unit tests with:

```bash
python -m pytest
```

Some integration-like scripts (e.g., `scripts/test_cleaning.py`) skip if sample HTML isn't available.

---

## Contributing

- Add tests for behavior you change.
- Keep functions small and add documentation for any new heuristics.

---

## License

This project is provided under an MIT-style license. See `LICENSE` if present.

