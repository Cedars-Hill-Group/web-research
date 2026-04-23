"""Tests for the direct-to-KB interactive research helpers in src/main.py.

Covers:
  _insert_under_heading         – inserts / creates headings correctly
  _kb_clean_company_filename    – returns unique, prettified paths
  _resolve_against_kb           – entity resolution + interactive prompting
  _write_research_direct_to_kb  – creates KB file with correct content
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
