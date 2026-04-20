"""Tests for src/config.resolve_knowledge_base_paths (Phase 1 — Foundation)."""
from __future__ import annotations

from pathlib import Path

from src.config import resolve_knowledge_base_paths


def test_knowledge_base_derived_from_storage_database_dir(tmp_path):
    """When no knowledge_base section, root is derived from storage.database_dir."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "storage:\n  database_dir: Companies\n",
        encoding="utf-8",
    )

    result = resolve_knowledge_base_paths(cfg)

    # KB root should be the parent of the resolved Companies dir.
    assert result["root"] == tmp_path
    assert result["companies_dir"] == "Companies"
    assert result["people_dir"] == "people"
    assert result["projects_dir"] == "Properties"


def test_knowledge_base_explicit_section_takes_precedence(tmp_path):
    """Explicit knowledge_base.path overrides the derived value."""
    kb_root = tmp_path / "MyVault"
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"storage:\n  database_dir: Companies\n"
        f"knowledge_base:\n  path: {kb_root.as_posix()}\n  companies_dir: Firms\n",
        encoding="utf-8",
    )

    result = resolve_knowledge_base_paths(cfg)

    assert result["root"] == kb_root
    assert result["companies_dir"] == "Firms"


def test_knowledge_base_explicit_section_defaults_sub_dirs(tmp_path):
    """When knowledge_base.path is set but sub-dirs omitted, defaults apply."""
    kb_root = tmp_path / "MyVault"
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"knowledge_base:\n  path: {kb_root.as_posix()}\n",
        encoding="utf-8",
    )

    result = resolve_knowledge_base_paths(cfg)

    assert result["root"] == kb_root
    assert result["companies_dir"] == "companies"
    assert result["people_dir"] == "people"
    assert result["projects_dir"] == "Properties"


def test_knowledge_base_legacy_defaults_when_config_missing(tmp_path):
    """When config is missing, legacy defaults are returned."""
    missing = tmp_path / "no-config.yaml"

    result = resolve_knowledge_base_paths(missing)

    # root = parent of company_markdown_db/companies relative to config dir
    assert result["root"] == tmp_path / "company_markdown_db"
    assert result["companies_dir"] == "companies"


def test_knowledge_base_absolute_storage_dir(tmp_path):
    """Absolute storage.database_dir is accepted and parent becomes the KB root."""
    abs_db = tmp_path / "Vault" / "Companies"
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"storage:\n  database_dir: {abs_db.as_posix()}\n",
        encoding="utf-8",
    )

    result = resolve_knowledge_base_paths(cfg)

    assert result["root"] == tmp_path / "Vault"
    assert result["companies_dir"] == "Companies"
