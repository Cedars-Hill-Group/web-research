"""Tests for _llm_normalize_catalog_properties (LLM-based focus/firm_type normalization)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.main import _llm_normalize_catalog_properties


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STUB_MD = """\
---
company: Acme Capital
website: https://acme.com/
---

Acme Capital is a real estate investment firm focused on commercial properties.
"""


def _write_stub_file(tmp_path: Path) -> Path:
    """Write a minimal staging markdown file and return its path."""
    md_dir = tmp_path / "acme-capital" / "markdown"
    md_dir.mkdir(parents=True)
    md_file = md_dir / "acme-ai-research.md"
    md_file.write_text(_STUB_MD, encoding="utf-8")
    return md_file


# ---------------------------------------------------------------------------
# ImportError fallback
# ---------------------------------------------------------------------------


def test_llm_normalize_catalog_properties_noop_when_data_platform_missing(tmp_path):
    """If data-platform is not installed, the function must return silently."""
    md_file = _write_stub_file(tmp_path)
    original_content = md_file.read_text(encoding="utf-8")

    with patch.dict(sys.modules, {
        "data_platform": None,
        "data_platform.actions": None,
        "data_platform.actions.llm_client": None,
        "data_platform.actions.sanitize_company": None,
        "data_platform.ontology_adapter": None,
    }):
        _llm_normalize_catalog_properties(md_file, api_key="key", model="gpt-4o-mini")

    # File must be unchanged.
    assert md_file.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# Normal path
# ---------------------------------------------------------------------------


def _build_mock_imports():
    """Return fake data-platform objects for use in tests."""
    # --- CatalogPropertyValue stub ---
    def make_value(v, d):
        pv = MagicMock()
        pv.value = v
        pv.description = d
        return pv

    # --- CatalogProperty stub ---
    def make_prop(field, accept_multiple, values):
        p = MagicMock()
        p.field = field
        p.accept_multiple_values = accept_multiple
        p.values = values
        return p

    firm_type_prop = make_prop("firm_type", False, [
        make_value("real_estate", "Real estate investment firm"),
        make_value("private_equity", "Private equity firm"),
    ])
    focus_prop = make_prop("focus", True, [
        make_value("real_estate", "Commercial and residential real estate"),
        make_value("technology", "Technology sector"),
    ])

    # --- AttributesCatalog stub ---
    mock_catalog = MagicMock()
    mock_catalog.properties = [firm_type_prop, focus_prop]

    # --- AttributesCatalog class (constructor) ---
    mock_attrs_catalog_cls = MagicMock(return_value=mock_catalog)

    # --- ParsedDocument stub ---
    mock_doc = MagicMock()
    mock_doc.metadata = {"company": "Acme Capital", "website": "https://acme.com/"}
    mock_doc.content = "Acme Capital is a real estate investment firm."
    mock_doc.path = MagicMock()
    mock_doc.path.name = "acme-ai-research.md"

    # --- Reader stub ---
    mock_reader = MagicMock()
    mock_reader.read_file.return_value = mock_doc

    # --- CompanySanitizer stub ---
    mock_sanitizer_instance = MagicMock()
    mock_sanitizer_instance._reader = mock_reader
    mock_sanitizer_instance._normalize_properties.return_value = {
        "firm_type": "real_estate",
        "focus": ["real_estate"],
    }

    mock_sanitizer_cls = MagicMock(return_value=mock_sanitizer_instance)
    mock_sanitizer_cls._write_metadata = MagicMock()

    # --- LLMClient stub ---
    mock_llm_cls = MagicMock()

    # --- get_attributes_catalog stub ---
    mock_get_catalog = MagicMock(return_value=mock_catalog)

    return {
        "llm_cls": mock_llm_cls,
        "sanitizer_cls": mock_sanitizer_cls,
        "sanitizer_instance": mock_sanitizer_instance,
        "attrs_catalog_cls": mock_attrs_catalog_cls,
        "get_attrs_catalog": mock_get_catalog,
        "mock_doc": mock_doc,
        "mock_catalog": mock_catalog,
    }


def test_llm_normalize_catalog_properties_writes_normalized_fields(tmp_path):
    """LLM-normalized changes must be written back to the file."""
    md_file = _write_stub_file(tmp_path)
    mocks = _build_mock_imports()

    mock_llm_module = MagicMock()
    mock_llm_module.LLMClient = mocks["llm_cls"]

    mock_sanitize_module = MagicMock()
    mock_sanitize_module.CompanySanitizer = mocks["sanitizer_cls"]

    mock_ontology_module = MagicMock()
    mock_ontology_module.AttributesCatalog = mocks["attrs_catalog_cls"]
    mock_ontology_module.get_attributes_catalog = mocks["get_attrs_catalog"]

    with patch.dict(sys.modules, {
        "data_platform.actions.llm_client": mock_llm_module,
        "data_platform.actions.sanitize_company": mock_sanitize_module,
        "data_platform.ontology_adapter": mock_ontology_module,
    }):
        _llm_normalize_catalog_properties(md_file, api_key="sk-test", model="gpt-4o-mini")

    # The sanitizer's _normalize_properties must have been called.
    mocks["sanitizer_instance"]._normalize_properties.assert_called_once()

    # _write_metadata must have been called with the returned changes merged in.
    mocks["sanitizer_cls"]._write_metadata.assert_called_once()
    _, written_meta = mocks["sanitizer_cls"]._write_metadata.call_args[0]
    assert written_meta["firm_type"] == "real_estate"
    assert written_meta["focus"] == ["real_estate"]


def test_llm_normalize_catalog_properties_filters_catalog_to_focus_and_firm_type(tmp_path):
    """Only the 'focus' and 'firm_type' properties should be passed to CompanySanitizer."""
    md_file = _write_stub_file(tmp_path)
    mocks = _build_mock_imports()

    # The catalog has both firm_type and focus; after filtering, both should remain.
    # Add a third property (e.g. 'naics_code') that must be filtered out.
    extra_prop = MagicMock()
    extra_prop.field = "naics_code"
    mocks["mock_catalog"].properties = [
        *mocks["mock_catalog"].properties,
        extra_prop,
    ]

    filtered_catalog_arg = None

    def capture_filtered(properties):
        nonlocal filtered_catalog_arg
        result = MagicMock()
        result.properties = properties
        filtered_catalog_arg = properties
        return result

    mock_llm_module = MagicMock()
    mock_llm_module.LLMClient = mocks["llm_cls"]

    mock_sanitize_module = MagicMock()
    mock_sanitize_module.CompanySanitizer = mocks["sanitizer_cls"]

    mock_ontology_module = MagicMock()
    mock_ontology_module.AttributesCatalog = MagicMock(side_effect=capture_filtered)
    mock_ontology_module.get_attributes_catalog = mocks["get_attrs_catalog"]

    with patch.dict(sys.modules, {
        "data_platform.actions.llm_client": mock_llm_module,
        "data_platform.actions.sanitize_company": mock_sanitize_module,
        "data_platform.ontology_adapter": mock_ontology_module,
    }):
        _llm_normalize_catalog_properties(md_file, api_key="sk-test", model="gpt-4o-mini")

    assert filtered_catalog_arg is not None
    field_names = {p.field for p in filtered_catalog_arg}
    assert field_names == {"focus", "firm_type"}, (
        f"Expected only 'focus' and 'firm_type', got {field_names!r}"
    )


def test_llm_normalize_catalog_properties_noop_when_no_changes(tmp_path):
    """When _normalize_properties returns {}, _write_metadata must not be called."""
    md_file = _write_stub_file(tmp_path)
    mocks = _build_mock_imports()
    mocks["sanitizer_instance"]._normalize_properties.return_value = {}

    mock_llm_module = MagicMock()
    mock_llm_module.LLMClient = mocks["llm_cls"]

    mock_sanitize_module = MagicMock()
    mock_sanitize_module.CompanySanitizer = mocks["sanitizer_cls"]

    mock_ontology_module = MagicMock()
    mock_ontology_module.AttributesCatalog = mocks["attrs_catalog_cls"]
    mock_ontology_module.get_attributes_catalog = mocks["get_attrs_catalog"]

    with patch.dict(sys.modules, {
        "data_platform.actions.llm_client": mock_llm_module,
        "data_platform.actions.sanitize_company": mock_sanitize_module,
        "data_platform.ontology_adapter": mock_ontology_module,
    }):
        _llm_normalize_catalog_properties(md_file, api_key="sk-test", model="gpt-4o-mini")

    mocks["sanitizer_cls"]._write_metadata.assert_not_called()


def test_llm_normalize_catalog_properties_swallows_runtime_exceptions(tmp_path, capsys):
    """Runtime errors inside the LLM call must not propagate."""
    md_file = _write_stub_file(tmp_path)
    original_content = md_file.read_text(encoding="utf-8")

    mocks = _build_mock_imports()
    mocks["sanitizer_instance"]._normalize_properties.side_effect = RuntimeError("LLM timeout")

    mock_llm_module = MagicMock()
    mock_llm_module.LLMClient = mocks["llm_cls"]

    mock_sanitize_module = MagicMock()
    mock_sanitize_module.CompanySanitizer = mocks["sanitizer_cls"]

    mock_ontology_module = MagicMock()
    mock_ontology_module.AttributesCatalog = mocks["attrs_catalog_cls"]
    mock_ontology_module.get_attributes_catalog = mocks["get_attrs_catalog"]

    with patch.dict(sys.modules, {
        "data_platform.actions.llm_client": mock_llm_module,
        "data_platform.actions.sanitize_company": mock_sanitize_module,
        "data_platform.ontology_adapter": mock_ontology_module,
    }):
        # Must not raise.
        _llm_normalize_catalog_properties(md_file, api_key="sk-test", model="gpt-4o-mini")

    # File must be unchanged after a failure.
    assert md_file.read_text(encoding="utf-8") == original_content
    captured = capsys.readouterr()
    assert "normalization skipped" in captured.out


def test_llm_normalize_catalog_properties_noop_when_catalog_has_no_matching_fields(tmp_path):
    """If the catalog has no 'focus' or 'firm_type' properties, return without calling LLM."""
    md_file = _write_stub_file(tmp_path)
    mocks = _build_mock_imports()

    # Catalog only has an unrelated property.
    other_prop = MagicMock()
    other_prop.field = "naics_code"
    mocks["mock_catalog"].properties = [other_prop]

    mock_llm_module = MagicMock()
    mock_llm_module.LLMClient = mocks["llm_cls"]

    mock_sanitize_module = MagicMock()
    mock_sanitize_module.CompanySanitizer = mocks["sanitizer_cls"]

    filtered_catalog = MagicMock()
    filtered_catalog.properties = []  # empty after filtering

    mock_ontology_module = MagicMock()
    mock_ontology_module.AttributesCatalog = MagicMock(return_value=filtered_catalog)
    mock_ontology_module.get_attributes_catalog = mocks["get_attrs_catalog"]

    with patch.dict(sys.modules, {
        "data_platform.actions.llm_client": mock_llm_module,
        "data_platform.actions.sanitize_company": mock_sanitize_module,
        "data_platform.ontology_adapter": mock_ontology_module,
    }):
        _llm_normalize_catalog_properties(md_file, api_key="sk-test", model="gpt-4o-mini")

    # CompanySanitizer should never be instantiated if the filtered catalog is empty.
    mocks["sanitizer_cls"].assert_not_called()


def test_llm_normalize_catalog_properties_does_not_swallow_keyboard_interrupt(tmp_path):
    """KeyboardInterrupt must propagate — ``except Exception`` does not catch BaseException."""
    md_file = _write_stub_file(tmp_path)
    mocks = _build_mock_imports()
    mocks["sanitizer_instance"]._normalize_properties.side_effect = KeyboardInterrupt

    mock_llm_module = MagicMock()
    mock_llm_module.LLMClient = mocks["llm_cls"]

    mock_sanitize_module = MagicMock()
    mock_sanitize_module.CompanySanitizer = mocks["sanitizer_cls"]

    mock_ontology_module = MagicMock()
    mock_ontology_module.AttributesCatalog = mocks["attrs_catalog_cls"]
    mock_ontology_module.get_attributes_catalog = mocks["get_attrs_catalog"]

    with patch.dict(sys.modules, {
        "data_platform.actions.llm_client": mock_llm_module,
        "data_platform.actions.sanitize_company": mock_sanitize_module,
        "data_platform.ontology_adapter": mock_ontology_module,
    }):
        with pytest.raises(KeyboardInterrupt):
            _llm_normalize_catalog_properties(md_file, api_key="sk-test", model="gpt-4o-mini")
