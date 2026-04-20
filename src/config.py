from __future__ import annotations

import yaml
from pathlib import Path


DEFAULT_SOURCE_DIR = Path("data/companies")
DEFAULT_STORAGE_DATABASE_DIR = Path("company_markdown_db/companies")


def load_config(path: str | Path = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_config_safe(path: str | Path) -> dict:
    try:
        cfg = load_config(path)
        return cfg if isinstance(cfg, dict) else {}
    except (FileNotFoundError, OSError, yaml.YAMLError):
        return {}


def _resolve_config_relative(path_value: str | Path, config_dir: Path) -> Path:
    candidate = Path(str(path_value)).expanduser()
    if candidate.is_absolute():
        return candidate
    # On Windows, rooted paths like "\\folder" or "/folder" are absolute to current drive
    # but pathlib may report is_absolute() as False.
    if candidate.anchor in {"\\", "/"}:
        return candidate.resolve()
    return config_dir / candidate


def resolve_storage_paths(
    config_path: str | Path = "config.yaml",
    source_dir_override: str | Path | None = None,
    database_dir_override: str | Path | None = None,
) -> dict[str, Path]:
    """Resolve source and database directories from config and optional CLI overrides.

    Resolution behavior:
    - Source defaults to ``data/companies`` under the project (or CLI override).
    - ``storage.database_dir`` controls DB output location.
    - Relative DB paths are resolved from the config file directory.
    - CLI overrides are resolved relative to the config file directory when relative.
    - If config is missing/unreadable, legacy defaults are used.
    """
    config_file = Path(config_path).expanduser()
    config_dir = config_file.resolve().parent

    cfg = _load_config_safe(config_file)
    storage = cfg.get("storage") or {}

    if source_dir_override is not None:
        source_dir = _resolve_config_relative(source_dir_override, config_dir)
    else:
        source_dir = _resolve_config_relative(DEFAULT_SOURCE_DIR, config_dir)

    if database_dir_override is not None:
        database_dir = _resolve_config_relative(database_dir_override, config_dir)
    else:
        db_raw = storage.get("database_dir")
        if db_raw:
            database_dir = _resolve_config_relative(str(db_raw), config_dir)
        else:
            database_dir = _resolve_config_relative(DEFAULT_STORAGE_DATABASE_DIR, config_dir)

    return {
        "config_dir": config_dir,
        "source_dir": source_dir,
        "database_dir": database_dir,
    }


def resolve_knowledge_base_paths(
    config_path: str | Path = "config.yaml",
) -> dict[str, Path | str]:
    """Resolve the data-platform Knowledge Base root and sub-folder configuration.

    The KB root and companies sub-folder name are derived in this order:

    1. Explicit ``knowledge_base:`` section in config.yaml (highest priority).
    2. Derived from ``storage.database_dir`` — KB root is the *parent* of the
       database dir, and the companies folder name is the last path component.
    3. Legacy defaults (``company_markdown_db/`` as KB root,
       ``companies`` as the sub-folder).

    Returns a dict with:
      - ``root``         : :class:`~pathlib.Path` to the KB root directory
      - ``companies_dir``: folder name of the companies sub-directory (str)
      - ``people_dir``   : folder name for the people sub-directory (str)
      - ``projects_dir`` : folder name for the properties/projects sub-directory (str)
    """
    config_file = Path(config_path).expanduser()
    config_dir = config_file.resolve().parent
    cfg = _load_config_safe(config_file)

    # 1. Explicit knowledge_base section takes precedence.
    kb_cfg = cfg.get("knowledge_base") or {}
    if kb_cfg.get("path"):
        kb_root = _resolve_config_relative(str(kb_cfg["path"]), config_dir)
        return {
            "root": kb_root,
            "companies_dir": str(kb_cfg.get("companies_dir", "companies")),
            "people_dir": str(kb_cfg.get("people_dir", "people")),
            "projects_dir": str(kb_cfg.get("projects_dir", "Properties")),
        }

    # 2. Derive from storage.database_dir.
    storage = cfg.get("storage") or {}
    db_raw = storage.get("database_dir")
    if db_raw:
        db_dir = _resolve_config_relative(str(db_raw), config_dir)
        return {
            "root": db_dir.parent,
            "companies_dir": db_dir.name,
            "people_dir": "people",
            "projects_dir": "Properties",
        }

    # 3. Legacy defaults.
    default_db = _resolve_config_relative(DEFAULT_STORAGE_DATABASE_DIR, config_dir)
    return {
        "root": default_db.parent,
        "companies_dir": default_db.name,
        "people_dir": "people",
        "projects_dir": "Properties",
    }
