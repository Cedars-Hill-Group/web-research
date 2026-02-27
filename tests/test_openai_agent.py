"""Tests for the OpenAI multi-agent integration (src/openai_agent.py).

All OpenAI API calls are mocked so these tests run without a real API key.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to build minimal file-system fixtures
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def dirs(tmp_path):
    """Return (prompts_dir, schemas_dir) with minimal fixture files."""
    prompts = tmp_path / "prompts"
    schemas = tmp_path / "schemas"

    _write(
        prompts / "website_agent.md",
        "System: find the website. Respond with JSON: {website, confidence, reasoning}",
    )
    _write(
        prompts / "classifier_agent.md",
        "System: classify. Available: {schema_list}. Respond: {schema, confidence, reasoning}",
    )
    _write(
        prompts / "analyst_agent.md",
        "Schema:\n{schema_content}\n\nContent:\n{website_content}\n\nAnalyse the company.",
    )
    _write(schemas / "general.md", "# General Schema\n## Overview\n## Products")
    _write(
        schemas / "commercial_real_estate.md",
        "# CRE Schema\n## Overview\n## Loan Programs",
    )
    return prompts, schemas


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------

def test_parse_json_response_plain():
    from src.openai_agent import _parse_json_response

    raw = '{"website": "https://example.com", "confidence": "high", "reasoning": "ok"}'
    result = _parse_json_response(raw)
    assert result["website"] == "https://example.com"


def test_parse_json_response_with_code_fence():
    from src.openai_agent import _parse_json_response

    raw = '```json\n{"schema": "general", "confidence": "high", "reasoning": "ok"}\n```'
    result = _parse_json_response(raw)
    assert result["schema"] == "general"


def test_parse_json_response_no_json_raises():
    from src.openai_agent import _parse_json_response

    with pytest.raises(ValueError):
        _parse_json_response("This is just plain text with no JSON.")


# ---------------------------------------------------------------------------
# _list_schemas
# ---------------------------------------------------------------------------

def test_list_schemas(dirs):
    from src.openai_agent import _list_schemas

    _, schemas_dir = dirs
    schemas = _list_schemas(schemas_dir)
    assert "general" in schemas
    assert "commercial_real_estate" in schemas


def test_list_schemas_missing_dir():
    from src.openai_agent import _list_schemas

    result = _list_schemas("/nonexistent/path")
    assert result == ["general"]


# ---------------------------------------------------------------------------
# _load_prompt / _load_schema
# ---------------------------------------------------------------------------

def test_load_prompt(dirs):
    from src.openai_agent import _load_prompt

    prompts_dir, _ = dirs
    prompt = _load_prompt(prompts_dir, "website_agent.md")
    assert "website" in prompt.lower()


def test_load_prompt_missing_raises(tmp_path):
    from src.openai_agent import _load_prompt

    with pytest.raises(FileNotFoundError):
        _load_prompt(tmp_path, "nonexistent.md")


def test_load_schema(dirs):
    from src.openai_agent import _load_schema

    _, schemas_dir = dirs
    schema = _load_schema(schemas_dir, "general")
    assert "General Schema" in schema


def test_load_schema_missing_raises(tmp_path):
    from src.openai_agent import _load_schema

    with pytest.raises(FileNotFoundError):
        _load_schema(tmp_path, "nonexistent")


# ---------------------------------------------------------------------------
# WebsiteAgent
# ---------------------------------------------------------------------------

def _mock_chat_response(content: str):
    """Return a minimal mock that looks like an openai ChatCompletion."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


def test_website_agent_run(dirs):
    from src.openai_agent import WebsiteAgent

    prompts_dir, _ = dirs
    payload = {"website": "https://acme.com", "confidence": "high", "reasoning": "Known brand"}
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_chat_response(json.dumps(payload))

    agent = WebsiteAgent(client, "gpt-4o-mini", prompts_dir)
    result = agent.run("Acme Corp")

    assert result["website"] == "https://acme.com"
    assert result["confidence"] == "high"
    client.chat.completions.create.assert_called_once()


def test_website_agent_passes_context(dirs):
    from src.openai_agent import WebsiteAgent

    prompts_dir, _ = dirs
    payload = {"website": "https://beta.io", "confidence": "medium", "reasoning": "Context match"}
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_chat_response(json.dumps(payload))

    agent = WebsiteAgent(client, "gpt-4o-mini", prompts_dir)
    agent.run("Beta Inc", context="commercial real estate")

    call_args = client.chat.completions.create.call_args
    user_msg = call_args.kwargs["messages"][1]["content"]
    assert "commercial real estate" in user_msg


# ---------------------------------------------------------------------------
# ClassifierAgent
# ---------------------------------------------------------------------------

def test_classifier_agent_run(dirs):
    from src.openai_agent import ClassifierAgent

    prompts_dir, schemas_dir = dirs
    payload = {
        "schema": "commercial_real_estate",
        "focus": "commercial real estate lending",
        "confidence": "high",
        "reasoning": "CRE lender",
    }
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_chat_response(json.dumps(payload))

    agent = ClassifierAgent(client, "gpt-4o-mini", prompts_dir, schemas_dir)
    result = agent.run("Acme Lending", "We provide commercial real estate loans.")

    assert result["schema"] == "commercial_real_estate"
    assert result["focus"] == "commercial real estate lending"


def test_classifier_agent_falls_back_to_general(dirs):
    from src.openai_agent import ClassifierAgent

    prompts_dir, schemas_dir = dirs
    # Return an unknown schema name
    payload = {"schema": "unknown_schema_xyz", "confidence": "low", "reasoning": "Unclear"}
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_chat_response(json.dumps(payload))

    agent = ClassifierAgent(client, "gpt-4o-mini", prompts_dir, schemas_dir)
    result = agent.run("Mystery Corp", "We do things.")

    assert result["schema"] == "general"
    assert result["focus"] == "general"


def test_classifier_agent_focus_falls_back_to_schema_when_missing(dirs):
    from src.openai_agent import ClassifierAgent

    prompts_dir, schemas_dir = dirs
    payload = {"schema": "commercial_real_estate", "confidence": "high", "reasoning": "CRE lender"}
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_chat_response(json.dumps(payload))

    agent = ClassifierAgent(client, "gpt-4o-mini", prompts_dir, schemas_dir)
    result = agent.run("Acme Lending", "We provide commercial real estate loans.")

    assert result["schema"] == "commercial_real_estate"
    assert result["focus"] == "commercial real estate"


# ---------------------------------------------------------------------------
# AnalystAgent
# ---------------------------------------------------------------------------

def test_analyst_agent_run(dirs):
    from src.openai_agent import AnalystAgent

    prompts_dir, schemas_dir = dirs
    report_text = "# Acme Corp\n## Overview\nAcme is a great company."
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_chat_response(report_text)

    agent = AnalystAgent(client, "gpt-4o-mini", prompts_dir, schemas_dir)
    report = agent.run("Acme Corp", "general", "Acme makes widgets.")

    assert "Acme" in report
    client.chat.completions.create.assert_called_once()


# ---------------------------------------------------------------------------
# CompanyResearchPipeline
# ---------------------------------------------------------------------------

def test_pipeline_run_end_to_end(dirs, tmp_path):
    """Full pipeline run with all external calls mocked."""
    from src.openai_agent import CompanyResearchPipeline

    prompts_dir, schemas_dir = dirs

    website_payload = {"website": "https://acme.com", "confidence": "high", "reasoning": "Known"}
    classifier_payload = {
        "schema": "general",
        "focus": "manufacturing widgets",
        "confidence": "high",
        "reasoning": "General co",
    }
    report_text = "# Acme Corp\n## Overview\nAcme Corp provides widgets."

    responses = [
        _mock_chat_response(json.dumps(website_payload)),
        _mock_chat_response(json.dumps(classifier_payload)),
        _mock_chat_response(report_text),
    ]
    client = MagicMock()
    client.chat.completions.create.side_effect = responses

    with patch("src.openai_agent._get_openai_client", return_value=client), \
         patch("src.openai_agent._fetch_page_text", return_value="Acme makes widgets."), \
         patch("src.openai_agent._collect_subpage_urls", return_value=[]):

        pipeline = CompanyResearchPipeline(
            api_key="test-key",
            model="gpt-4o-mini",
            prompts_dir=prompts_dir,
            schemas_dir=schemas_dir,
            max_subpages=0,
        )
        result = pipeline.run("Acme Corp")

    assert result["company"] == "Acme Corp"
    assert result["website"] == "https://acme.com"
    assert result["schema"] == "general"
    assert result["classifier_agent"]["focus"] == "manufacturing widgets"
    assert "Acme" in result["report"]
    assert client.chat.completions.create.call_count == 3


def test_pipeline_from_config(dirs, tmp_path):
    """from_config() reads openai settings from a config file."""
    import yaml
    from src.openai_agent import CompanyResearchPipeline

    prompts_dir, schemas_dir = dirs
    config = {
        "openai": {
            "api_key": "test-key",
            "model": "gpt-4o-mini",
            "max_subpages": 2,
            "schemas_dir": str(schemas_dir),
            "prompts_dir": str(prompts_dir),
        }
    }
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.safe_dump(config), encoding="utf-8")

    with patch("src.openai_agent._get_openai_client", return_value=MagicMock()):
        pipeline = CompanyResearchPipeline.from_config(config_file)

    assert pipeline._model == "gpt-4o-mini"
    assert pipeline._max_subpages == 2
