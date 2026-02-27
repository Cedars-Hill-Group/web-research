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

from .config import load_config

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
    except Exception as exc:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
        return []


def _load_prompt(prompts_dir: str | Path, filename: str) -> str:
    """Read a prompt markdown file and return its contents."""
    path = Path(prompts_dir) / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Prompt file not found: {path}")


def _load_schema(schemas_dir: str | Path, schema_name: str) -> str:
    """Return the contents of a schema markdown file by schema name."""
    path = Path(schemas_dir) / f"{schema_name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Schema file not found: {path}")


def _list_schemas(schemas_dir: str | Path) -> list[str]:
    """Return a list of available schema names (filename stems)."""
    d = Path(schemas_dir)
    if not d.exists():
        return ["general"]
    return sorted(p.stem for p in d.glob("*.md"))


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

    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ValueError(
            "An OpenAI API key is required. Set it via the OPENAI_API_KEY "
            "environment variable or the 'openai.api_key' field in config.yaml."
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
            context: Optional additional context (e.g., industry, location).

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
        """Return a dict with keys: schema, confidence, reasoning.

        Args:
            company_name: The name of the company.
            website_content: Scraped text from the company's website.

        Returns:
            Dict with ``schema``, ``confidence``, and ``reasoning`` keys.
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
            schema_name: The schema to apply (must match a file in schemas_dir).
            website_content: Scraped text from the company's website.

        Returns:
            A Markdown string containing the structured analysis.
        """
        schema_content = _load_schema(self._schemas_dir, schema_name)
        system_prompt = _load_prompt(self._prompts_dir, "analyst_agent.md")
        system_prompt = (
            system_prompt
            .replace("{schema_content}", schema_content)
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
        result = pipeline.run("Acme Corp", context="commercial real estate lender")
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

    def run(self, company_name: str, context: str = "") -> dict[str, Any]:
        """Run the full research pipeline for *company_name*.

        Args:
            company_name: Name of the company to research.
            context: Optional context to help identify the correct company.

        Returns:
            A dict with keys:
              - ``company``  : the company name
              - ``website``  : resolved website URL
              - ``schema``   : schema used for analysis
              - ``report``   : Markdown report produced by the analyst agent
              - ``website_agent``    : raw output from WebsiteAgent
              - ``classifier_agent`` : raw output from ClassifierAgent
        """
        # Step 1 — find the website
        website_result = self._website_agent.run(company_name, context)
        website_url = website_result.get("website", "")

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

        # Step 3 — classify the company
        classifier_result = self._classifier_agent.run(company_name, website_content)
        schema_name = classifier_result.get("schema", "general")

        # Step 4 — generate the analysis
        report = self._analyst_agent.run(company_name, schema_name, website_content)

        return {
            "company": company_name,
            "website": website_url,
            "schema": schema_name,
            "report": report,
            "website_agent": website_result,
            "classifier_agent": classifier_result,
        }
