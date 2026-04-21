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
    mock_sanitizer_instance._classify_naics.return_value = {}

    mock_sanitizer_cls = MagicMock(return_value=mock_sanitizer_instance)
    mock_sanitizer_cls._write_metadata = MagicMock()

    # --- LLMClient stub ---
    mock_llm_cls = MagicMock()

    # --- get_attributes_catalog stub ---
    mock_get_catalog = MagicMock(return_value=mock_catalog)

    # --- get_catalog (raw dict, for applies_when) stub ---
    # By default, return a raw catalog with no applies_when so all fields pass.
    mock_get_raw_catalog = MagicMock(return_value={"properties": []})

    return {
        "llm_cls": mock_llm_cls,
        "sanitizer_cls": mock_sanitizer_cls,
        "sanitizer_instance": mock_sanitizer_instance,
        "attrs_catalog_cls": mock_attrs_catalog_cls,
        "get_attrs_catalog": mock_get_catalog,
        "get_raw_catalog": mock_get_raw_catalog,
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


def test_llm_normalize_catalog_properties_filters_catalog_to_target_fields(tmp_path):
    """Only target fields (focus, firm_type, loan_structure) pass through; others are dropped."""
    md_file = _write_stub_file(tmp_path)
    mocks = _build_mock_imports()

    # Build a catalog that contains all three target fields plus two that must be filtered out.
    loan_structure_prop = MagicMock()
    loan_structure_prop.field = "loan_structure"
    naics_prop = MagicMock()
    naics_prop.field = "naics_code"
    website_prop = MagicMock()
    website_prop.field = "website"
    mocks["mock_catalog"].properties = [
        *mocks["mock_catalog"].properties,  # firm_type, focus
        loan_structure_prop,
        naics_prop,
        website_prop,
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
    assert field_names == {"focus", "firm_type", "loan_structure"}, (
        f"Unexpected filtered field set: {field_names!r}"
    )
    assert "naics_code" not in field_names
    assert "website" not in field_names


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


def test_llm_normalize_catalog_properties_calls_classify_naics(tmp_path):
    """_classify_naics must be called and its changes written to the file."""
    md_file = _write_stub_file(tmp_path)
    mocks = _build_mock_imports()
    mocks["sanitizer_instance"]._classify_naics.return_value = {
        "naics_code": "5239",
        "naics_title": "Other Financial Investment Activities",
        "naics_sector_code": "52",
        "naics_sector_title": "Finance and Insurance",
    }

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

    mocks["sanitizer_instance"]._classify_naics.assert_called_once()

    _, written_meta = mocks["sanitizer_cls"]._write_metadata.call_args[0]
    assert written_meta["naics_code"] == "5239"
    assert written_meta["naics_sector_code"] == "52"


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


# ---------------------------------------------------------------------------
# applies_when: loan_structure conditional behavior
# ---------------------------------------------------------------------------


def _loan_stub_md(focus: str | list[str]) -> str:
    """Build a stub front-matter with the given focus value(s)."""
    if isinstance(focus, list):
        focus_yaml = "[" + ", ".join(f'"{f}"' for f in focus) + "]"
    else:
        focus_yaml = f'"{focus}"'
    return f"""\
---
company: Acme Lending
website: https://acmelending.com/
focus: {focus_yaml}
---

Acme Lending provides commercial real estate debt financing.
"""


def _write_loan_stub_file(tmp_path: Path, focus: str | list[str]) -> Path:
    md_dir = tmp_path / "acme-lending" / "markdown"
    md_dir.mkdir(parents=True)
    md_file = md_dir / "acme-ai-research.md"
    md_file.write_text(_loan_stub_md(focus), encoding="utf-8")
    return md_file


def _build_loan_mocks(*, include_loan_structure_in_changes: bool = True):
    """Return mocks that include a loan_structure property with an applies_when condition.

    The raw catalog uses the actual flat dict structure from ontology-core, with a
    top-level ``"applies_when"`` key mapping field names to their conditions.
    """
    mocks = _build_mock_imports()

    # Add loan_structure property to the catalog (mirrors the real catalog)
    loan_structure_prop = MagicMock()
    loan_structure_prop.field = "loan_structure"
    mocks["mock_catalog"].properties = [*mocks["mock_catalog"].properties, loan_structure_prop]

    # LLM returns loan_structure as a change
    base_changes = {"firm_type": "real_estate", "focus": ["commercial_real_estate"]}
    if include_loan_structure_in_changes:
        base_changes["loan_structure"] = ["senior", "mezz"]
    mocks["sanitizer_instance"]._normalize_properties.return_value = base_changes

    # The raw catalog uses the FLAT dict format with a top-level "applies_when" key.
    # This mirrors the actual attributes.json structure in ontology-core, where each
    # field's condition is keyed by field name under "applies_when".
    raw_catalog_with_condition = {
        "$ontology_id": "attributes",
        "$schema_version": "1.0.0",
        "firm_type": [],
        "focus": [],
        "loan_structure": [],
        "accept_multiple_values": {"firm_type": True, "focus": True, "loan_structure": True},
        "applies_when": {
            "loan_structure": {"focus": {"contains_any": ["commercial_real_estate"]}},
        },
    }
    mocks["get_raw_catalog"].return_value = raw_catalog_with_condition
    return mocks


def test_loan_structure_written_when_focus_is_cre(tmp_path):
    """When focus contains 'commercial_real_estate', loan_structure changes must be written."""
    md_file = _write_loan_stub_file(tmp_path, focus=["commercial_real_estate"])
    mocks = _build_loan_mocks()

    # doc.metadata must reflect the CRE focus so the applies_when condition passes
    mocks["mock_doc"].metadata = {
        "company": "Acme Lending",
        "website": "https://acmelending.com/",
        "focus": ["commercial_real_estate"],
    }

    mock_llm_module = MagicMock()
    mock_llm_module.LLMClient = mocks["llm_cls"]

    mock_sanitize_module = MagicMock()
    mock_sanitize_module.CompanySanitizer = mocks["sanitizer_cls"]

    mock_ontology_module = MagicMock()
    mock_ontology_module.AttributesCatalog = mocks["attrs_catalog_cls"]
    mock_ontology_module.get_attributes_catalog = mocks["get_attrs_catalog"]
    mock_ontology_module.get_catalog = mocks["get_raw_catalog"]

    with patch.dict(sys.modules, {
        "data_platform.actions.llm_client": mock_llm_module,
        "data_platform.actions.sanitize_company": mock_sanitize_module,
        "data_platform.ontology_adapter": mock_ontology_module,
    }):
        _llm_normalize_catalog_properties(md_file, api_key="sk-test", model="gpt-4o-mini")

    mocks["sanitizer_cls"]._write_metadata.assert_called_once()
    _, written_meta = mocks["sanitizer_cls"]._write_metadata.call_args[0]
    assert written_meta["loan_structure"] == ["senior", "mezz"]


def test_loan_structure_excluded_when_focus_is_not_cre(tmp_path):
    """When focus does not include 'commercial_real_estate', loan_structure must not be written."""
    md_file = _write_loan_stub_file(tmp_path, focus=["technology", "healthcare"])
    mocks = _build_loan_mocks()

    # doc.metadata has a non-CRE focus
    mocks["mock_doc"].metadata = {
        "company": "Acme Tech",
        "website": "https://acmetech.com/",
        "focus": ["technology", "healthcare"],
    }

    mock_llm_module = MagicMock()
    mock_llm_module.LLMClient = mocks["llm_cls"]

    mock_sanitize_module = MagicMock()
    mock_sanitize_module.CompanySanitizer = mocks["sanitizer_cls"]

    mock_ontology_module = MagicMock()
    mock_ontology_module.AttributesCatalog = mocks["attrs_catalog_cls"]
    mock_ontology_module.get_attributes_catalog = mocks["get_attrs_catalog"]
    mock_ontology_module.get_catalog = mocks["get_raw_catalog"]

    with patch.dict(sys.modules, {
        "data_platform.actions.llm_client": mock_llm_module,
        "data_platform.actions.sanitize_company": mock_sanitize_module,
        "data_platform.ontology_adapter": mock_ontology_module,
    }):
        _llm_normalize_catalog_properties(md_file, api_key="sk-test", model="gpt-4o-mini")

    # loan_structure must NOT appear in the written metadata
    mocks["sanitizer_cls"]._write_metadata.assert_called_once()
    _, written_meta = mocks["sanitizer_cls"]._write_metadata.call_args[0]
    assert "loan_structure" not in written_meta


def test_loan_structure_included_when_applies_when_key_absent(tmp_path):
    """When the raw catalog has no 'applies_when' key, all LLM changes are kept."""
    md_file = _write_loan_stub_file(tmp_path, focus=["technology"])
    mocks = _build_loan_mocks()

    mocks["mock_doc"].metadata = {
        "company": "Acme Tech",
        "focus": ["technology"],
    }

    # Raw catalog with no applies_when key (mirrors catalog before the key is added)
    mocks["get_raw_catalog"].return_value = {
        "$ontology_id": "attributes",
        "$schema_version": "1.0.0",
        "firm_type": [],
        "focus": [],
        "loan_structure": [],
        "accept_multiple_values": {"loan_structure": True},
    }

    mock_llm_module = MagicMock()
    mock_llm_module.LLMClient = mocks["llm_cls"]

    mock_sanitize_module = MagicMock()
    mock_sanitize_module.CompanySanitizer = mocks["sanitizer_cls"]

    mock_ontology_module = MagicMock()
    mock_ontology_module.AttributesCatalog = mocks["attrs_catalog_cls"]
    mock_ontology_module.get_attributes_catalog = mocks["get_attrs_catalog"]
    mock_ontology_module.get_catalog = mocks["get_raw_catalog"]

    with patch.dict(sys.modules, {
        "data_platform.actions.llm_client": mock_llm_module,
        "data_platform.actions.sanitize_company": mock_sanitize_module,
        "data_platform.ontology_adapter": mock_ontology_module,
    }):
        _llm_normalize_catalog_properties(md_file, api_key="sk-test", model="gpt-4o-mini")

    # Without applies_when restrictions, loan_structure from _normalize_properties is kept
    _, written_meta = mocks["sanitizer_cls"]._write_metadata.call_args[0]
    assert written_meta["loan_structure"] == ["senior", "mezz"]


def test_loan_structure_still_written_when_get_catalog_raises(tmp_path):
    """If get_catalog raises, applies_when_map stays empty and no changes are filtered out."""
    md_file = _write_loan_stub_file(tmp_path, focus=["technology"])
    mocks = _build_loan_mocks()

    mocks["mock_doc"].metadata = {"company": "Acme Tech", "focus": ["technology"]}

    mock_llm_module = MagicMock()
    mock_llm_module.LLMClient = mocks["llm_cls"]

    mock_sanitize_module = MagicMock()
    mock_sanitize_module.CompanySanitizer = mocks["sanitizer_cls"]

    mock_ontology_module = MagicMock()
    mock_ontology_module.AttributesCatalog = mocks["attrs_catalog_cls"]
    mock_ontology_module.get_attributes_catalog = mocks["get_attrs_catalog"]
    mock_ontology_module.get_catalog.side_effect = RuntimeError("catalog unavailable")

    with patch.dict(sys.modules, {
        "data_platform.actions.llm_client": mock_llm_module,
        "data_platform.actions.sanitize_company": mock_sanitize_module,
        "data_platform.ontology_adapter": mock_ontology_module,
    }):
        _llm_normalize_catalog_properties(md_file, api_key="sk-test", model="gpt-4o-mini")

    # get_catalog failure must be swallowed; the LLM changes are still written
    _, written_meta = mocks["sanitizer_cls"]._write_metadata.call_args[0]
    assert written_meta["loan_structure"] == ["senior", "mezz"]
