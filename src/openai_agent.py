"""openai_agent.py — Multi-agent OpenAI integration for company research.

Three agents collaborate to research a company:
  1. WebsiteAgent   – identifies the company's official website
  2. ClassifierAgent – determines which schema best fits the company
  3. AnalystAgent    – applies the schema to produce a structured report

Each agent reads its system prompt from a Markdown file in the ``prompts/``
directory so prompts can be customised without touching source code.  Schemas
live in the ``schemas/`` directory; any ``.md`` file found there is treated as
an available schema whose name equals the filename stem (e.g.
``commercial_real_estate.md`` → ``commercial_real_estate``).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from bs4 import FeatureNotFound
from pydantic import BaseModel, Field

from .config import load_config


# ---------------------------------------------------------------------------
# Structured output model
# ---------------------------------------------------------------------------

class CompanyResearchOutput(BaseModel):
    """Structured output from the full company research pipeline."""

    company: str = Field(description="Company name")
    website: str = Field(default="", description="Resolved company website URL")
    schema_class: str = Field(default="general", description="Schema class used for analysis")
    report: str = Field(default="", description="Markdown report produced by the analyst agent")
    firm_type: str | None = Field(default=None, description="AI-inferred or user-supplied firm type")
    focus: str | None = Field(default=None, description="Company focus phrase")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; WebResearchBot/1.0; "
        "+https://github.com/rounder22/web-research)"
    )
}
_REQUEST_TIMEOUT = 10  # seconds


def _normalise_api_key(value: str | None) -> str:
    if value is None:
        return ""
    normalised = str(value).strip().strip('"').strip("'").strip()
    return normalised


def _read_windows_env_from_registry(name: str) -> str:
    """Read a persisted Windows environment variable directly from registry."""
    if os.name != "nt":
        return ""

    try:
        import winreg  # noqa: PLC0415
    except ImportError:
        return ""

    locations = [
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ]
    for hive, path in locations:
        try:
            with winreg.OpenKey(hive, path) as key:
                value, _ = winreg.QueryValueEx(key, name)
        except OSError:
            continue

        normalised = _normalise_api_key(value)
        if normalised:
            return normalised

    return ""


def _read_env_var_from_dotenv(name: str) -> str:
    """Read an environment variable from .env.local or .env in CWD."""
    for path in (Path.cwd() / ".env.local", Path.cwd() / ".env"):
        if not path.exists() or not path.is_file():
            continue

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            if key.strip() != name:
                continue

            resolved = _normalise_api_key(value)
            if resolved:
                return resolved

    return ""


def _resolve_openai_api_key(api_key: str | None = None) -> str:
    """Resolve API key from explicit arg, env, .env files, and Windows persisted env."""
    explicit = _normalise_api_key(api_key)
    if explicit:
        return explicit

    process_env = _normalise_api_key(os.environ.get("OPENAI_API_KEY", ""))
    if process_env:
        return process_env

    dotenv_env = _read_env_var_from_dotenv("OPENAI_API_KEY")
    if dotenv_env:
        return dotenv_env

    registry_env = _read_windows_env_from_registry("OPENAI_API_KEY")
    if registry_env:
        return registry_env

    return ""


def _fetch_page_text(url: str, timeout: int = _REQUEST_TIMEOUT) -> str:
    """Fetch a URL and return cleaned plain-text suitable for an LLM prompt."""
    try:
        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        # Remove non-content elements
        for tag in soup(["script", "style", "nav", "footer", "header", "meta", "link"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:8000]  # Limit per-page context to keep prompts manageable
    except (requests.RequestException, OSError, ValueError, FeatureNotFound) as exc:
        return f"[Could not fetch {url}: {exc}]"


def _collect_subpage_urls(base_url: str, max_links: int = 5) -> list[str]:
    """Return up to *max_links* internal URLs found on the company home page."""
    try:
        resp = requests.get(base_url, headers=_DEFAULT_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        base_netloc = urlparse(base_url).netloc
        seen: set[str] = {base_url}
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            full = urljoin(base_url, href)
            parsed = urlparse(full)
            if parsed.netloc != base_netloc:
                continue
            # Ignore anchors, query-only URLs, common non-content paths
            if parsed.fragment or not parsed.path:
                continue
            skip_patterns = ("/cdn-cgi/", "/wp-content/", "/wp-admin/", "/feed/")
            if any(parsed.path.startswith(p) for p in skip_patterns):
                continue
            if full not in seen:
                seen.add(full)
                links.append(full)
            if len(links) >= max_links:
                break
        return links
    except (requests.RequestException, OSError, ValueError, FeatureNotFound):
        return []


def _normalise_homepage_url(url: str) -> str:
    """Return the scheme+netloc root of *url* (strips path, query, fragment).

    Ensures that the URL stored as a company's canonical website is always
    the homepage root and not a redirect-target deep-link.  For example,
    ``https://amstar.com/about?ref=foo`` becomes ``https://amstar.com/``.

    If the URL has no scheme, ``https://`` is prepended before parsing.
    Non-parseable inputs are returned unchanged.
    """
    if not url:
        return url
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/"
    return url


def _load_prompt(prompts_dir: str | Path, filename: str) -> str:
    """Read a prompt markdown file and return its contents."""
    path = Path(prompts_dir) / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Prompt file not found: {path}")


def _list_schemas(schemas_dir: str | Path) -> list[str]:
    """Return a list of available schema class names.

    Schema classes are discovered in two ways (merged, deduplicated):
    1. Subdirectories of *schemas_dir* that contain an ``extraction.md`` file.
    2. ``.md`` files in the root of *schemas_dir* (legacy flat-file format).
    """
    d = Path(schemas_dir)
    if not d.exists():
        return ["general"]
    names: set[str] = set()
    for item in d.iterdir():
        if item.is_dir() and (item / "extraction.md").exists():
            names.add(item.name)
    for f in d.glob("*.md"):
        names.add(f.stem)
    return sorted(names) if names else ["general"]


def _load_extraction_schema(schemas_dir: str | Path, schema_name: str) -> str:
    """Return the extraction schema for *schema_name*, with its title line stripped.

    Looks for ``<schemas_dir>/<schema_name>/extraction.md`` first, then falls
    back to the legacy flat file ``<schemas_dir>/<schema_name>.md``.
    The leading ``# Heading`` line (if present) is removed so that the schema
    title does not appear in the analyst prompt or the stored output.
    """
    d = Path(schemas_dir)
    subdir_path = d / schema_name / "extraction.md"
    flat_path = d / f"{schema_name}.md"

    if subdir_path.exists():
        content = subdir_path.read_text(encoding="utf-8").strip()
    elif flat_path.exists():
        content = flat_path.read_text(encoding="utf-8").strip()
    else:
        raise FileNotFoundError(f"Extraction schema not found for class: {schema_name!r}")

    # Strip the leading title line (e.g. "# General Company Schema") — level-1 only
    lines = content.splitlines()
    if lines and re.match(r"^#\s", lines[0]):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def _load_output_schema(schemas_dir: str | Path, schema_name: str) -> str | None:
    """Return the output/format schema for *schema_name*, or ``None`` if absent."""
    path = Path(schemas_dir) / schema_name / "output.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return None


def _load_template_for_class(schemas_dir: str | Path, schema_name: str) -> str | None:
    """Return the database template for *schema_name*, or ``None`` if absent."""
    path = Path(schemas_dir) / schema_name / "template.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return None


def _load_schema(schemas_dir: str | Path, schema_name: str) -> str:
    """Return the extraction schema contents (legacy alias for ``_load_extraction_schema``)."""
    return _load_extraction_schema(schemas_dir, schema_name)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract the first JSON object from an LLM response string."""
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text.strip(), flags=re.MULTILINE)
    # Find the JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {text!r}")
    return json.loads(match.group())


# ---------------------------------------------------------------------------
# OpenAI client factory
# ---------------------------------------------------------------------------

def _get_openai_client(api_key: str | None = None):
    """Return an ``openai.OpenAI`` client, raising a clear error when unavailable."""
    try:
        import openai  # noqa: PLC0415 (lazy import — optional dependency)
    except ImportError as exc:
        raise ImportError(
            "The 'openai' package is required for AI-assisted research. "
            "Install it with: pip install openai"
        ) from exc

    key = _resolve_openai_api_key(api_key)
    if not key:
        raise ValueError(
            "An OpenAI API key is required. Set it via the OPENAI_API_KEY "
            "environment variable, a .env/.env.local file, or the 'openai.api_key' "
            "field in config.yaml."
        )
    return openai.OpenAI(api_key=key)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class WebsiteAgent:
    """Determines a company's official website from its name and optional context."""

    def __init__(self, client, model: str, prompts_dir: str | Path):
        self._client = client
        self._model = model
        self._prompts_dir = prompts_dir

    def run(self, company_name: str, context: str = "") -> dict[str, Any]:
        """Return a dict with keys: website, confidence, reasoning.

        Args:
            company_name: The name of the company to look up.
            context: Optional context string to bias website resolution.

        Returns:
            Dict with ``website``, ``confidence``, and ``reasoning`` keys.
        """
        system_prompt = _load_prompt(self._prompts_dir, "website_agent.md")
        user_message = f"Company name: {company_name}"
        if context:
            user_message += f"\nAdditional context: {context}"

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
        )
        raw = response.choices[0].message.content or ""
        return _parse_json_response(raw)


class ClassifierAgent:
    """Determines which schema best describes a company."""

    def __init__(self, client, model: str, prompts_dir: str | Path, schemas_dir: str | Path):
        self._client = client
        self._model = model
        self._prompts_dir = prompts_dir
        self._schemas_dir = schemas_dir

    def run(self, company_name: str, website_content: str) -> dict[str, Any]:
        """Return a dict with keys: schema, focus, confidence, reasoning.

        Args:
            company_name: The name of the company.
            website_content: Scraped text from the company's website.

        Returns:
            Dict with ``schema``, ``focus``, ``confidence``, and ``reasoning`` keys.
        """
        available = _list_schemas(self._schemas_dir)
        schema_list = "\n".join(f"- {s}" for s in available)
        system_prompt = _load_prompt(self._prompts_dir, "classifier_agent.md")
        system_prompt = system_prompt.replace("{schema_list}", schema_list)

        user_message = (
            f"Company name: {company_name}\n\n"
            f"Website content summary:\n{website_content[:3000]}"
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
        )
        raw = response.choices[0].message.content or ""
        result = _parse_json_response(raw)
        # Ensure schema is a valid option, fall back to "general"
        if result.get("schema") not in available:
            result["schema"] = "general"

        # Ensure focus is present; prefer model-provided focus, else derive from schema.
        focus = str(result.get("focus") or "").strip()
        if not focus:
            schema_name = str(result.get("schema") or "general").strip()
            if schema_name and schema_name != "general":
                focus = schema_name.replace("_", " ")
            else:
                focus = "general"
        result["focus"] = focus
        return result


class AnalystAgent:
    """Applies a schema to produce a structured company description and summary."""

    def __init__(self, client, model: str, prompts_dir: str | Path, schemas_dir: str | Path):
        self._client = client
        self._model = model
        self._prompts_dir = prompts_dir
        self._schemas_dir = schemas_dir

    def run(self, company_name: str, schema_name: str, website_content: str) -> str:
        """Return a Markdown-formatted company analysis.

        Args:
            company_name: The name of the company.
            schema_name: The schema class to apply (must match a class in schemas_dir).
            website_content: Scraped text from the company's website.

        Returns:
            A Markdown string containing the structured analysis.
        """
        extraction_schema = _load_extraction_schema(self._schemas_dir, schema_name)
        output_schema = _load_output_schema(self._schemas_dir, schema_name)
        system_prompt = _load_prompt(self._prompts_dir, "analyst_agent.md")
        system_prompt = (
            system_prompt
            .replace("{schema_content}", extraction_schema)
            .replace("{output_schema}", output_schema or "")
            .replace("{website_content}", website_content[:6000])
        )

        user_message = f"Please analyze this company: {company_name}"

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
        )
        return (response.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# High-level orchestrator
# ---------------------------------------------------------------------------

class CompanyResearchPipeline:
    """Orchestrates all three agents to produce a full company research report.

    Usage::

        pipeline = CompanyResearchPipeline.from_config()
        result = pipeline.run("Acme Corp")
        print(result["report"])
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        prompts_dir: str | Path = "prompts",
        schemas_dir: str | Path = "schemas",
        max_subpages: int = 5,
    ):
        client = _get_openai_client(api_key)
        self._model = model
        self._prompts_dir = Path(prompts_dir)
        self._schemas_dir = Path(schemas_dir)
        self._max_subpages = max_subpages
        self._website_agent = WebsiteAgent(client, model, prompts_dir)
        self._classifier_agent = ClassifierAgent(client, model, prompts_dir, schemas_dir)
        self._analyst_agent = AnalystAgent(client, model, prompts_dir, schemas_dir)

    @classmethod
    def from_config(cls, config_path: str | Path = "config.yaml") -> "CompanyResearchPipeline":
        """Create a pipeline instance from *config.yaml*."""
        cfg = load_config(config_path)
        oa = cfg.get("openai", {})
        return cls(
            api_key=oa.get("api_key") or None,
            model=oa.get("model", "gpt-4o-mini"),
            prompts_dir=oa.get("prompts_dir", "prompts"),
            schemas_dir=oa.get("schemas_dir", "schemas"),
            max_subpages=int(oa.get("max_subpages", 5)),
        )

    def list_schema_classes(self) -> list[str]:
        """Return available schema classes configured for this pipeline."""
        return _list_schemas(self._schemas_dir)

    def summarize_existing_content(self, company_name: str, existing_content: str) -> str:
        """Return a cleaned-up, more succinct version of *existing_content*.

        The LLM is instructed to retain every fact, number, name, and data
        point from the original and only improve readability and conciseness.
        All markdown formatting is preserved.

        Args:
            company_name:     Name of the company the content belongs to.
            existing_content: Current text under the "Basic Underwriting" heading.

        Returns:
            Cleaned-up markdown content string (no heading, no preamble).
        """
        system_prompt = (
            "You are a professional editor specializing in financial company research "
            "reports. Your task is to clean up and condense the provided 'Basic "
            "Underwriting' section for a company while strictly preserving all "
            "factual content.\n\n"
            "Rules:\n"
            "- Retain EVERY fact, number, name, strategy, and data point from the "
            "original.\n"
            "- Do NOT add any new information that is not present in the original.\n"
            "- Remove redundancy, fix grammar, and improve clarity and conciseness.\n"
            "- Preserve all markdown formatting (lists, bold, tables, headings, "
            "etc.).\n"
            "- Output only the cleaned content — no preamble, explanation, or "
            "section heading."
        )
        user_message = (
            f"Company: {company_name}\n\n"
            f"Existing 'Basic Underwriting' content to clean up:\n\n{existing_content}"
        )
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
        )
        return (response.choices[0].message.content or "").strip()

    def find_website(self, company_name: str, context: str = "") -> dict[str, Any]:
        """Run only the WebsiteAgent and return its result dict.

        Useful when the caller needs the website URL before deciding whether to
        proceed with full research (e.g. for KB entity resolution).

        Args:
            company_name: Name of the company to look up.
            context:      Optional context string passed to the WebsiteAgent.

        Returns:
            Dict with ``website``, ``confidence``, and ``reasoning`` keys.
        """
        return self._website_agent.run(company_name, context)

    def run(
        self,
        company_name: str,
        schema_class: str | None = None,
        website: str | None = None,
    ) -> dict[str, Any]:
        """Run the full research pipeline for *company_name*.

        Args:
            company_name: Name of the company to research.
            schema_class: Explicitly specify which schema class to use.  When
                provided the ClassifierAgent is skipped entirely and the given
                class is used directly.  Must match a directory name (or legacy
                flat file stem) in *schemas_dir*.
            website:      Pre-resolved website URL.  When provided the
                WebsiteAgent step is skipped entirely and this URL is used
                directly, saving one LLM call.  The URL is still normalised to
                its homepage root before scraping.

        Returns:
            A dict with keys:
              - ``company``         : the company name
              - ``website``         : resolved website URL
              - ``schema``          : schema class used for analysis
              - ``report``          : Markdown report produced by the analyst agent
              - ``website_agent``   : raw output from WebsiteAgent
              - ``classifier_agent``: raw output from ClassifierAgent (or a stub
                                      when the classifier was skipped)
              - ``structured_output``: :class:`CompanyResearchOutput` Pydantic model
        """
        # Step 1 — find the website (skip when a URL is pre-provided)
        if website:
            website_url = _normalise_homepage_url(website)
            website_result: dict[str, Any] = {
                "website": website_url,
                "confidence": "pre-provided",
                "reasoning": "Website URL provided directly; WebsiteAgent skipped.",
            }
        else:
            website_context = schema_class or ""
            website_result = self._website_agent.run(company_name, website_context)
            website_url = website_result.get("website", "")
            # Normalise to canonical homepage root before scraping and storing so
            # the URL in metadata always reflects the root domain, not a redirect
            # target or deep-link path (fixes Issue #13).
            if website_url:
                website_url = _normalise_homepage_url(website_url)

        # Step 2 — fetch website content (homepage + subpages)
        website_content = ""
        if website_url:
            homepage_text = _fetch_page_text(website_url)
            website_content = f"=== {website_url} ===\n{homepage_text}"

            subpages = _collect_subpage_urls(website_url, self._max_subpages)
            for subpage_url in subpages:
                time.sleep(0.3)  # polite crawl delay
                subpage_text = _fetch_page_text(subpage_url)
                website_content += f"\n\n=== {subpage_url} ===\n{subpage_text}"

        # Step 3 — classify the company (skip when schema class is explicit)
        available = _list_schemas(self._schemas_dir)
        if schema_class:
            if schema_class in available:
                schema_name = schema_class
                classifier_result: dict[str, Any] = {
                    "schema": schema_name,
                    "focus": None,
                    "confidence": "n/a",
                    "reasoning": "Schema class explicitly specified by user.",
                }
            else:
                print(
                    f"Warning: schema_class {schema_class!r} is not a known class "
                    f"(available: {', '.join(available)}). Auto-detecting instead."
                )
                classifier_result = self._classifier_agent.run(company_name, website_content)
                schema_name = classifier_result.get("schema", "general")
        else:
            classifier_result = self._classifier_agent.run(company_name, website_content)
            schema_name = classifier_result.get("schema", "general")

        # Step 4 — generate the analysis
        report = self._analyst_agent.run(company_name, schema_name, website_content)

        structured = CompanyResearchOutput(
            company=company_name,
            website=website_url,
            schema_class=schema_name,
            report=report,
        )

        return {
            "company": company_name,
            "website": website_url,
            "schema": schema_name,
            "report": report,
            "website_agent": website_result,
            "classifier_agent": classifier_result,
            "structured_output": structured,
        }
