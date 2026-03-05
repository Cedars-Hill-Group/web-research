from pathlib import Path

from src.config import resolve_storage_paths


def test_resolve_storage_paths_uses_fixed_source_and_relative_database(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
storage:
    database_dir: "Companies"
""".strip(),
        encoding="utf-8",
    )

    resolved = resolve_storage_paths(cfg)

    assert resolved["source_dir"] == tmp_path / "data" / "companies"
    assert resolved["database_dir"] == tmp_path / "Companies"


def test_resolve_storage_paths_keeps_absolute_database_dir(tmp_path):
    abs_db = tmp_path / "Vault" / "Companies"
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
storage:
  database_dir: "{abs_db.as_posix()}"
""".strip(),
        encoding="utf-8",
    )

    resolved = resolve_storage_paths(cfg)

    assert resolved["source_dir"] == tmp_path / "data" / "companies"
    assert resolved["database_dir"] == abs_db


def test_resolve_storage_paths_legacy_defaults_when_config_missing(tmp_path):
    missing_cfg = tmp_path / "missing-config.yaml"

    resolved = resolve_storage_paths(missing_cfg)

    assert resolved["source_dir"] == tmp_path / "data" / "companies"
    assert resolved["database_dir"] == tmp_path / "company_markdown_db" / "companies"


def test_resolve_storage_paths_ignores_deprecated_base_dir(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
storage:
  base_dir: "Obsidian/Knowledge Base"
  database_dir: "Companies"
""".strip(),
        encoding="utf-8",
    )

    resolved = resolve_storage_paths(cfg)

    assert resolved["source_dir"] == tmp_path / "data" / "companies"
    assert resolved["database_dir"] == tmp_path / "Companies"


def test_resolve_storage_paths_keeps_rooted_database_dir_outside_project(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
storage:
    database_dir: "/Obsidian/Knowledge Base/Companies"
""".strip(),
        encoding="utf-8",
    )

    resolved = resolve_storage_paths(cfg)

    assert resolved["source_dir"] == tmp_path / "data" / "companies"
    assert resolved["database_dir"] == Path("/Obsidian/Knowledge Base/Companies").resolve()
