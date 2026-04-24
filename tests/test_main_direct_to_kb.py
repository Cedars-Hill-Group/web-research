"""Tests for direct-to-KB workflow functions in src/main.py.

Covers:
  _insert_under_heading         – inserts / creates headings correctly
  _kb_clean_company_filename    – returns unique, prettified paths
  _resolve_against_kb           – entity resolution + interactive prompting
  _write_research_direct_to_kb  – creates KB file with correct content
  _extract_section_content      – extracts markdown section content
  _replace_section_content      – replaces markdown section content
  _process_existing_company_in_kb – updates existing KB entries
"""
from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.main import (
    _insert_under_heading,
    _kb_clean_company_filename,
    _resolve_against_kb,
    _write_research_direct_to_kb,
)


# ---------------------------------------------------------------------------
# _insert_under_heading
# ---------------------------------------------------------------------------

class TestInsertUnderHeading:
    def test_inserts_after_existing_heading(self):
        body = "## Basic Underwriting\n\n## Other\n\nOther content.\n"
        result = _insert_under_heading(body, "Basic Underwriting", "New stuff.")
        assert "New stuff." in result
        idx_heading = result.index("## Basic Underwriting")
        idx_content = result.index("New stuff.")
        assert idx_content > idx_heading

    def test_creates_heading_when_absent(self):
        body = "## Overview\n\nSome overview.\n"
        result = _insert_under_heading(body, "Basic Underwriting", "New stuff.")
        assert "## Basic Underwriting" in result
        assert "New stuff." in result

    def test_no_op_when_addition_is_empty(self):
        body = "## Overview\n\nContent.\n"
        result = _insert_under_heading(body, "Basic Underwriting", "   ")
        assert result == body

    def test_case_insensitive_heading_match(self):
        body = "## basic underwriting\n\n"
        result = _insert_under_heading(body, "Basic Underwriting", "Data.")
        assert "Data." in result
        # The existing heading was matched, so no new ## heading should be added
        assert result.count("## ") == 1


# ---------------------------------------------------------------------------
# _kb_clean_company_filename
# ---------------------------------------------------------------------------

class TestKbCleanCompanyFilename:
    def test_returns_prettified_path(self, tmp_path):
        path = _kb_clean_company_filename("acme capital llc", tmp_path)
        assert path.suffix == ".md"
        assert path.parent == tmp_path
        # Name should be Title Case (no dashes)
        assert "-" not in path.stem

    def test_increments_when_file_exists(self, tmp_path):
        (tmp_path / "Acme Capital LLC.md").write_text("exists", encoding="utf-8")
        path = _kb_clean_company_filename("acme capital llc", tmp_path)
        assert path.stem == "Acme Capital LLC 2"

    def test_non_existent_db_dir_returns_path(self, tmp_path):
        db_dir = tmp_path / "does_not_exist"
        path = _kb_clean_company_filename("Test Co", db_dir)
        assert path.name.endswith(".md")


# ---------------------------------------------------------------------------
# _resolve_against_kb
# ---------------------------------------------------------------------------

class TestResolveAgainstKb:
    def test_empty_kb_create_new(self, tmp_path, monkeypatch):
        """Empty KB → offer to create new company."""
        answers = iter(["y", ""])  # confirm create, accept default name
        monkeypatch.setattr(builtins, "input", lambda _: next(answers))

        matched, new_name = _resolve_against_kb("Acme Corp", None, tmp_path / "kb")

        assert matched is None
        assert new_name == "Acme Corp"

    def test_empty_kb_skip(self, tmp_path, monkeypatch):
        """Empty KB → user skips."""
        monkeypatch.setattr(builtins, "input", lambda _: "n")

        matched, new_name = _resolve_against_kb("Acme Corp", None, tmp_path / "kb")

        assert matched is None
        assert new_name is None

    def test_empty_kb_custom_name(self, tmp_path, monkeypatch):
        """Empty KB → user provides custom name."""
        answers = iter(["y", "Custom Acme"])
        monkeypatch.setattr(builtins, "input", lambda _: next(answers))

        matched, new_name = _resolve_against_kb("Acme Corp", None, tmp_path / "kb")

        assert matched is None
        assert new_name == "Custom Acme"

    def test_probabilistic_match_accepted(self, tmp_path, monkeypatch):
        """Splink/difflib finds a close name; user accepts it."""
        db = tmp_path / "kb"
        db.mkdir()
        existing_file = db / "Acme Capital.md"
        existing_file.write_text("---\nwebsite: https://acme.com/\n---\n", encoding="utf-8")

        # patch find_best_match to return a certain match
        with patch("src.main.find_best_match", return_value=("Acme Capital", 0.92)):
            monkeypatch.setattr(builtins, "input", lambda _: "y")
            matched, new_name = _resolve_against_kb("Acme Capital LLC", None, db)

        assert matched == existing_file
        assert new_name is None

    def test_probabilistic_match_rejected_create_new(self, tmp_path, monkeypatch):
        """Splink finds a match, user rejects it and creates a new entry."""
        db = tmp_path / "kb"
        db.mkdir()
        (db / "Acme Capital.md").write_text("---\n---\n", encoding="utf-8")

        with patch("src.main.find_best_match", return_value=("Acme Capital", 0.82)):
            answers = iter(["n", "y", ""])  # reject match, create new, accept default name
            monkeypatch.setattr(builtins, "input", lambda _: next(answers))
            matched, new_name = _resolve_against_kb("Completely Different Co", None, db)

        assert matched is None
        assert new_name == "Completely Different Co"

    def test_no_match_create_new(self, tmp_path, monkeypatch):
        """No probabilistic match; user creates new entry."""
        db = tmp_path / "kb"
        db.mkdir()
        (db / "Existing Company.md").write_text("---\n---\n", encoding="utf-8")

        with patch("src.main.find_best_match", return_value=(None, 0.0)):
            answers = iter(["y", "Brand New Co"])
            monkeypatch.setattr(builtins, "input", lambda _: next(answers))
            matched, new_name = _resolve_against_kb("Brand New Co", None, db)

        assert matched is None
        assert new_name == "Brand New Co"

    def test_no_match_skip(self, tmp_path, monkeypatch):
        """No match; user skips."""
        db = tmp_path / "kb"
        db.mkdir()
        (db / "Existing Company.md").write_text("---\n---\n", encoding="utf-8")

        with patch("src.main.find_best_match", return_value=(None, 0.0)):
            monkeypatch.setattr(builtins, "input", lambda _: "n")
            matched, new_name = _resolve_against_kb("Brand New Co", None, db)

        assert matched is None
        assert new_name is None


# ---------------------------------------------------------------------------
# _write_research_direct_to_kb
# ---------------------------------------------------------------------------

class TestWriteResearchDirectToKb:
    """Tests for _write_research_direct_to_kb."""

    _BASE_RESULT: dict = {
        "report": "## Overview\nSome overview.\n\n## Description\nFull description here.",
        "website": "https://example.com/",
        "schema": "general",
        "classifier_agent": {"focus": "commercial real estate", "reasoning": "test"},
    }

    def _call(self, tmp_path, result=None, schemas_dir=None, **kwargs):
        db_file = tmp_path / "Example Co.md"
        _write_research_direct_to_kb(
            "Example Co",
            result or self._BASE_RESULT,
            db_file,
            schemas_dir=schemas_dir,
            **kwargs,
        )
        return db_file

    def test_creates_file(self, tmp_path):
        db_file = self._call(tmp_path)
        assert db_file.exists()

    def test_front_matter_has_website_and_schema(self, tmp_path):
        db_file = self._call(tmp_path)
        text = db_file.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        meta = yaml.safe_load(parts[1])
        assert meta["website"] == "https://example.com/"
        assert meta["schema"] == "general"

    def test_front_matter_has_date(self, tmp_path):
        db_file = self._call(tmp_path)
        text = db_file.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1])
        assert meta.get("date")

    def test_content_under_basic_underwriting(self, tmp_path):
        db_file = self._call(tmp_path)
        text = db_file.read_text(encoding="utf-8")
        body = text.split("---", 2)[2]
        assert "## Basic Underwriting" in body
        idx_heading = body.index("## Basic Underwriting")
        idx_content = body.index("Some overview.")
        assert idx_content > idx_heading

    def test_website_stripped_from_body(self, tmp_path):
        result = dict(self._BASE_RESULT)
        result["report"] = (
            "## Company Overview\n"
            "- **Website**: https://example.com/\n"
            "- **Firm Type**: lender\n"
            "\n## Description\nContent here.\n"
        )
        db_file = self._call(tmp_path, result=result)
        body = db_file.read_text(encoding="utf-8").split("---", 2)[2]
        assert "**Website**" not in body
        assert "**Firm Type**" not in body
        assert "Content here." in body

    def test_uses_template_structure(self, tmp_path):
        schemas_dir = tmp_path / "schemas" / "general"
        schemas_dir.mkdir(parents=True)
        (schemas_dir / "template.md").write_text(
            "---\nwebsite:\ndate:\n---\n\n## Overview\n\n## Basic Underwriting\n\n## Notes\n",
            encoding="utf-8",
        )
        db_file = self._call(tmp_path, schemas_dir=str(tmp_path / "schemas"))
        body = db_file.read_text(encoding="utf-8").split("---", 2)[2]
        # Template headings should be present
        assert "## Overview" in body
        assert "## Notes" in body
        # Research content should be under Basic Underwriting
        assert "## Basic Underwriting" in body

    def test_llm_normalize_called(self, tmp_path):
        with patch("src.main._llm_normalize_catalog_properties") as mock_norm:
            self._call(tmp_path)
            mock_norm.assert_called_once()
            call_args = mock_norm.call_args
            assert call_args[0][0].name == "Example Co.md"

    def test_sanitize_on_save_calls_full_sanitizer(self, tmp_path):
        with patch("src.main._try_sanitize_research_output") as mock_san:
            self._call(tmp_path, sanitize=True)
            mock_san.assert_called_once()

    def test_website_from_body_takes_precedence(self, tmp_path):
        """When the AI report contains a Website: line, that URL is used in front-matter."""
        result = dict(self._BASE_RESULT)
        result["website"] = "https://fallback.com/"
        result["report"] = (
            "## Company Overview\n"
            "- **Website**: https://from-body.com/\n\n"
            "## Description\nContent.\n"
        )
        db_file = self._call(tmp_path, result=result)
        meta = yaml.safe_load(db_file.read_text(encoding="utf-8").split("---", 2)[1])
        assert meta["website"] == "https://from-body.com/"


# ---------------------------------------------------------------------------
# _extract_section_content
# ---------------------------------------------------------------------------

from src.main import _extract_section_content, _replace_section_content  # noqa: E402


class TestExtractSectionContent:
    def test_returns_content_under_heading(self):
        body = "## Basic Underwriting\n\nSome content here.\n\n## Other\n\nOther stuff.\n"
        result = _extract_section_content(body, "Basic Underwriting")
        assert "Some content here." in result
        assert "Other stuff." not in result

    def test_returns_empty_when_heading_absent(self):
        body = "## Overview\n\nContent.\n"
        result = _extract_section_content(body, "Basic Underwriting")
        assert result == ""

    def test_returns_empty_when_section_has_no_content(self):
        body = "## Basic Underwriting\n\n## Other\n\nContent.\n"
        result = _extract_section_content(body, "Basic Underwriting")
        assert result == ""

    def test_returns_empty_for_blank_section(self):
        body = "## Basic Underwriting\n\n   \n\n## Other\n"
        result = _extract_section_content(body, "Basic Underwriting")
        assert result == ""

    def test_case_insensitive_heading_match(self):
        body = "## basic underwriting\n\nData here.\n"
        result = _extract_section_content(body, "Basic Underwriting")
        assert "Data here." in result

    def test_content_up_to_next_heading(self):
        body = "## Basic Underwriting\n\nLine 1.\nLine 2.\n\n## Notes\n\nNote content.\n"
        result = _extract_section_content(body, "Basic Underwriting")
        assert "Line 1." in result
        assert "Line 2." in result
        assert "Note content." not in result

    def test_content_at_end_of_document(self):
        body = "## Overview\n\nIntro.\n\n## Basic Underwriting\n\nFinal section.\n"
        result = _extract_section_content(body, "Basic Underwriting")
        assert "Final section." in result

    def test_does_not_include_heading_line(self):
        body = "## Basic Underwriting\n\nContent.\n"
        result = _extract_section_content(body, "Basic Underwriting")
        assert "## Basic Underwriting" not in result

    def test_multiline_content(self):
        body = (
            "## Basic Underwriting\n\n"
            "- Point A\n"
            "- Point B\n"
            "- Point C\n\n"
            "## Other\n\nSomething.\n"
        )
        result = _extract_section_content(body, "Basic Underwriting")
        assert "Point A" in result
        assert "Point B" in result
        assert "Point C" in result


# ---------------------------------------------------------------------------
# _replace_section_content
# ---------------------------------------------------------------------------

class TestReplaceSectionContent:
    def test_replaces_existing_section(self):
        body = "## Basic Underwriting\n\nOld content.\n\n## Notes\n\nNote stuff.\n"
        result = _replace_section_content(body, "Basic Underwriting", "New content.")
        assert "New content." in result
        assert "Old content." not in result
        assert "## Notes" in result

    def test_creates_heading_when_absent(self):
        body = "## Overview\n\nSome overview.\n"
        result = _replace_section_content(body, "Basic Underwriting", "Added content.")
        assert "## Basic Underwriting" in result
        assert "Added content." in result
        assert "Some overview." in result

    def test_no_op_when_new_content_blank(self):
        body = "## Basic Underwriting\n\nExisting.\n"
        result = _replace_section_content(body, "Basic Underwriting", "   ")
        assert result == body

    def test_preserves_surrounding_sections(self):
        body = (
            "## Intro\n\nIntro text.\n\n"
            "## Basic Underwriting\n\nOld.\n\n"
            "## Conclusion\n\nConclusion text.\n"
        )
        result = _replace_section_content(body, "Basic Underwriting", "New research.")
        assert "Intro text." in result
        assert "New research." in result
        assert "Old." not in result
        assert "Conclusion text." in result

    def test_case_insensitive_heading_match(self):
        body = "## BASIC UNDERWRITING\n\nOld.\n"
        result = _replace_section_content(body, "Basic Underwriting", "Fresh.")
        assert "Fresh." in result
        assert "Old." not in result

    def test_heading_level_preserved(self):
        body = "### Basic Underwriting\n\nOld content.\n"
        result = _replace_section_content(body, "Basic Underwriting", "New.")
        assert "### Basic Underwriting" in result

    def test_replaces_multiline_content(self):
        body = (
            "## Basic Underwriting\n\n"
            "- A\n- B\n- C\n\n"
            "## Next\n\nNext stuff.\n"
        )
        result = _replace_section_content(body, "Basic Underwriting", "Single line.")
        assert "Single line." in result
        assert "- A" not in result
        assert "Next stuff." in result


# ---------------------------------------------------------------------------
# _process_existing_company_in_kb
# ---------------------------------------------------------------------------

from src.main import _process_existing_company_in_kb  # noqa: E402


class TestProcessExistingCompanyInKb:
    """Tests for _process_existing_company_in_kb."""

    def _make_kb_file(self, tmp_path: Path, body_content: str = "") -> Path:
        """Create a minimal KB markdown file and return its path."""
        meta = {"website": "https://example.com/", "schema": "general"}
        fm = yaml.safe_dump(meta, sort_keys=False)
        content = f"---\n{fm}---\n{body_content}"
        kb_file = tmp_path / "Example Co.md"
        kb_file.write_text(content, encoding="utf-8")
        return kb_file

    def _make_pipeline(self, summarized_text: str = "Summarized content.") -> MagicMock:
        pipeline = MagicMock()
        pipeline.summarize_existing_content.return_value = summarized_text
        pipeline.run.return_value = {
            "report": "## Overview\nResearched content.",
            "website": "https://example.com/",
            "schema": "general",
            "classifier_agent": {"focus": "lending", "reasoning": "test"},
        }
        return pipeline

    def test_existing_content_is_summarized(self, tmp_path, monkeypatch):
        """When Basic Underwriting has content, summarize_existing_content is called."""
        body = "## Basic Underwriting\n\nOriginal detailed content about the company.\n"
        kb_file = self._make_kb_file(tmp_path, body)
        pipeline = self._make_pipeline("Cleaned up content.")

        monkeypatch.setattr(builtins, "input", lambda _: "y")
        with patch("src.main._llm_normalize_catalog_properties"), \
             patch("src.main._crud_upsert_kb_file"):
            _process_existing_company_in_kb(
                "Example Co", kb_file, pipeline, website=None
            )

        pipeline.summarize_existing_content.assert_called_once_with(
            "Example Co", "Original detailed content about the company."
        )
        pipeline.run.assert_not_called()

    def test_existing_content_is_replaced(self, tmp_path, monkeypatch):
        """Summarized content replaces original in the file."""
        body = "## Basic Underwriting\n\nOld content.\n"
        kb_file = self._make_kb_file(tmp_path, body)
        pipeline = self._make_pipeline("New clean summary.")

        monkeypatch.setattr(builtins, "input", lambda _: "y")
        with patch("src.main._llm_normalize_catalog_properties"), \
             patch("src.main._crud_upsert_kb_file"):
            _process_existing_company_in_kb(
                "Example Co", kb_file, pipeline, website=None
            )

        text = kb_file.read_text(encoding="utf-8")
        assert "New clean summary." in text
        assert "Old content." not in text

    def test_user_rejects_summary_does_not_write(self, tmp_path, monkeypatch):
        """If user rejects the summary, the file is not modified."""
        body = "## Basic Underwriting\n\nOriginal content.\n"
        kb_file = self._make_kb_file(tmp_path, body)
        original_text = kb_file.read_text(encoding="utf-8")
        pipeline = self._make_pipeline("Summarized.")

        monkeypatch.setattr(builtins, "input", lambda _: "n")
        _process_existing_company_in_kb(
            "Example Co", kb_file, pipeline, website=None
        )

        assert kb_file.read_text(encoding="utf-8") == original_text

    def test_no_content_runs_research_pipeline(self, tmp_path, monkeypatch):
        """When Basic Underwriting is empty, the research pipeline is run."""
        body = "## Basic Underwriting\n\n## Other\n\nOther content.\n"
        kb_file = self._make_kb_file(tmp_path, body)
        pipeline = self._make_pipeline()

        monkeypatch.setattr(builtins, "input", lambda _: "y")
        with patch("src.main._llm_normalize_catalog_properties"), \
             patch("src.main._crud_upsert_kb_file"):
            _process_existing_company_in_kb(
                "Example Co", kb_file, pipeline, website="https://example.com/"
            )

        pipeline.run.assert_called_once_with(
            "Example Co", website="https://example.com/"
        )
        pipeline.summarize_existing_content.assert_not_called()

    def test_no_heading_runs_research_pipeline(self, tmp_path, monkeypatch):
        """When Basic Underwriting heading is absent, the research pipeline is run."""
        body = "## Overview\n\nSome overview text.\n"
        kb_file = self._make_kb_file(tmp_path, body)
        pipeline = self._make_pipeline()

        monkeypatch.setattr(builtins, "input", lambda _: "y")
        with patch("src.main._llm_normalize_catalog_properties"), \
             patch("src.main._crud_upsert_kb_file"):
            _process_existing_company_in_kb(
                "Example Co", kb_file, pipeline, website=None
            )

        pipeline.run.assert_called_once()

    def test_date_updated_added_to_metadata(self, tmp_path, monkeypatch):
        """date_updated is added to the front-matter after processing."""
        body = "## Basic Underwriting\n\nContent.\n"
        kb_file = self._make_kb_file(tmp_path, body)
        pipeline = self._make_pipeline()

        monkeypatch.setattr(builtins, "input", lambda _: "y")
        with patch("src.main._llm_normalize_catalog_properties"), \
             patch("src.main._crud_upsert_kb_file"):
            _process_existing_company_in_kb(
                "Example Co", kb_file, pipeline, website=None
            )

        meta = yaml.safe_load(kb_file.read_text(encoding="utf-8").split("---", 2)[1])
        assert "date_updated" in meta

    def test_existing_metadata_preserved(self, tmp_path, monkeypatch):
        """Existing front-matter fields (website, schema) are not lost."""
        body = "## Basic Underwriting\n\nContent.\n"
        kb_file = self._make_kb_file(tmp_path, body)
        pipeline = self._make_pipeline()

        monkeypatch.setattr(builtins, "input", lambda _: "y")
        with patch("src.main._llm_normalize_catalog_properties"), \
             patch("src.main._crud_upsert_kb_file"):
            _process_existing_company_in_kb(
                "Example Co", kb_file, pipeline, website=None
            )

        meta = yaml.safe_load(kb_file.read_text(encoding="utf-8").split("---", 2)[1])
        assert meta.get("website") == "https://example.com/"
        assert meta.get("schema") == "general"

    def test_sanitize_on_save_calls_full_sanitizer(self, tmp_path, monkeypatch):
        """When sanitize=True, _try_sanitize_research_output is called."""
        body = "## Basic Underwriting\n\nContent.\n"
        kb_file = self._make_kb_file(tmp_path, body)
        pipeline = self._make_pipeline()

        monkeypatch.setattr(builtins, "input", lambda _: "y")
        with patch("src.main._try_sanitize_research_output") as mock_san, \
             patch("src.main._crud_upsert_kb_file"):
            _process_existing_company_in_kb(
                "Example Co", kb_file, pipeline, website=None, sanitize=True
            )
            mock_san.assert_called_once()

    def test_llm_normalize_called_when_sanitize_false(self, tmp_path, monkeypatch):
        """When sanitize=False, _llm_normalize_catalog_properties is called."""
        body = "## Basic Underwriting\n\nContent.\n"
        kb_file = self._make_kb_file(tmp_path, body)
        pipeline = self._make_pipeline()

        monkeypatch.setattr(builtins, "input", lambda _: "y")
        with patch("src.main._llm_normalize_catalog_properties") as mock_norm, \
             patch("src.main._crud_upsert_kb_file"):
            _process_existing_company_in_kb(
                "Example Co", kb_file, pipeline, website=None, sanitize=False
            )
            mock_norm.assert_called_once()

    def test_crud_upsert_called_after_write(self, tmp_path, monkeypatch):
        """_crud_upsert_kb_file is called after the file is written."""
        body = "## Basic Underwriting\n\nContent.\n"
        kb_file = self._make_kb_file(tmp_path, body)
        pipeline = self._make_pipeline()

        monkeypatch.setattr(builtins, "input", lambda _: "y")
        with patch("src.main._llm_normalize_catalog_properties"), \
             patch("src.main._crud_upsert_kb_file") as mock_crud:
            _process_existing_company_in_kb(
                "Example Co", kb_file, pipeline, website=None
            )
            mock_crud.assert_called_once_with(kb_file)

    def test_research_error_does_not_raise(self, tmp_path, monkeypatch):
        """A pipeline.run() failure is caught gracefully."""
        body = "## Basic Underwriting\n\n## Other\n\n"
        kb_file = self._make_kb_file(tmp_path, body)
        pipeline = self._make_pipeline()
        pipeline.run.side_effect = RuntimeError("API failure")

        monkeypatch.setattr(builtins, "input", lambda _: "y")
        # Should not raise
        _process_existing_company_in_kb(
            "Example Co", kb_file, pipeline, website=None
        )

