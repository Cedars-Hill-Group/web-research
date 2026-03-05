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