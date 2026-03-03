"""Merge-only utility: consolidate existing markdown under data/companies into a DB folder.

This script does not run website search, scraping, or AI research. It only reads
existing markdown files that already exist under the data directory and merges them
into a flat markdown database using the same merge logic as merge_markdown_db.py.

Usage:
    python scripts/merge_existing_data.py
    python scripts/merge_existing_data.py --source-dir data/companies --db-dir company_markdown_db/companies
    python scripts/merge_existing_data.py --db-dir "C:/Obsidian/MyVault/Companies"
    python scripts/merge_existing_data.py --keep-merged-source
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.merge_markdown_db import (  # noqa: E402
    append_markdown_to_company,
    choose_match,
    _resolve_template,
)
from src.config import load_config  # noqa: E402
from src.store import safe_slug, pretty_company_name_enhanced  # noqa: E402


def _clean_company_filename(name: str, db_dir: Path, preserve_case: bool = False) -> Path:
    if preserve_case:
        pretty = name.strip()
        pretty = re.sub(r'[<>:"/\\|?*]+', " ", pretty)
        pretty = re.sub(r"\s+", " ", pretty).strip() or "Company"
    else:
        pretty = pretty_company_name_enhanced(name) or safe_slug(name)
        pretty = re.sub(r'[<>:"/\\|?*]+', " ", pretty)
        pretty = re.sub(r"\s+", " ", pretty).strip() or "Company"

    candidate = pretty
    idx = 1
    while True:
        suffix = "" if idx == 1 else f" {idx}"
        path = db_dir / f"{candidate}{suffix}.md"
        if not path.exists():
            return path
        idx += 1


def _extract_schema_class(md_files: list[Path]) -> str | None:
    """Extract the schema class from the YAML front matter of the first matching file."""
    try:
        import yaml
    except Exception:
        return None

    for md_file in md_files:
        try:
            text = md_file.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            parts = text.split("---", 2)
            if len(parts) < 3:
                continue
            meta = yaml.safe_load(parts[1]) or {}
            schema = str(meta.get("schema") or "").strip()
            if schema:
                return schema
        except Exception:
            continue
    return None


def _extract_company_name(md_files: list[Path], fallback: str) -> str:
    try:
        import yaml
    except Exception:
        return fallback

    for md_file in md_files:
        try:
            text = md_file.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            parts = text.split("---", 2)
            if len(parts) < 3:
                continue
            meta = yaml.safe_load(parts[1]) or {}
            company = str(meta.get("company") or "").strip()
            if company:
                return company
        except Exception:
            continue
    return fallback


def run_merge(
    source_dir: Path,
    db_dir: Path,
    keep_merged_source: bool = False,
    schemas_dir: Path | None = None,
    fallback_template: Path | None = None,
) -> int:
    if not source_dir.exists():
        print(f"Source directory not found: {source_dir}")
        return 1

    db_dir.mkdir(parents=True, exist_ok=True)
    existing = [path.stem for path in db_dir.glob("*.md")]

    companies_seen = 0
    companies_merged = 0
    files_appended = 0
    files_skipped = 0

    for company_dir in sorted(source_dir.iterdir()):
        if not company_dir.is_dir():
            continue

        md_dir = company_dir / "markdown"
        md_files = sorted(md_dir.glob("*.md")) if md_dir.exists() else []
        if not md_files:
            continue

        companies_seen += 1
        company_name = _extract_company_name(md_files, company_dir.name)
        schema_class = _extract_schema_class(md_files)
        print(f"\nProcessing: {company_name}")
        match, custom_name = choose_match(company_name, existing)

        if match:
            target_file = db_dir / f"{match}.md"
            print(f"  Using existing DB file: {target_file.name}")
        elif custom_name:
            target_file = _clean_company_filename(custom_name, db_dir, preserve_case=True)
            existing.append(target_file.stem)
            company_name = custom_name
            print(f"  Creating DB file: {target_file.name}")
        else:
            print(f"  Skipped company: {company_name}")
            continue

        template_content = _resolve_template(schema_class, schemas_dir, fallback_template)

        appended_for_company = 0
        for md_file in md_files:
            if append_markdown_to_company(
                md_file,
                target_file,
                company_display=company_name,
                template_content=template_content,
            ):
                appended_for_company += 1
                files_appended += 1
                print(f"  Appended: {md_file.name}")
            else:
                files_skipped += 1
                print(f"  Skipped duplicate: {md_file.name}")

        if appended_for_company > 0:
            companies_merged += 1
            if not keep_merged_source:
                try:
                    import shutil

                    shutil.rmtree(company_dir)
                    print(f"  Deleted source folder: {company_dir}")
                except Exception as exc:
                    print(f"  Warning: failed to delete {company_dir}: {exc}")

    print("\nMerge complete.")
    print(f"Companies with markdown found: {companies_seen}")
    print(f"Companies with new appended data: {companies_merged}")
    print(f"Markdown files appended: {files_appended}")
    print(f"Markdown files skipped as duplicates: {files_skipped}")

    return 0


def _resolve_db_dir(cli_db_dir: str | None, config_path: str) -> Path:
    if cli_db_dir:
        return Path(cli_db_dir)

    try:
        cfg = load_config(config_path)
        configured = (cfg.get("storage") or {}).get("database_dir")
        if configured:
            return Path(str(configured))
    except Exception:
        pass

    return Path("company_markdown_db/companies")


def _resolve_schemas_dir(cli_schemas_dir: str | None, config_path: str) -> Path | None:
    if cli_schemas_dir:
        return Path(cli_schemas_dir)

    try:
        cfg = load_config(config_path)
        configured = (cfg.get("openai") or {}).get("schemas_dir")
        if configured:
            return Path(str(configured))
    except Exception:
        pass

    default = Path("schemas")
    return default if default.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge existing markdown under data/companies into a flat DB folder."
    )
    parser.add_argument(
        "--source-dir",
        default="data/companies",
        help="Root folder containing per-company folders with markdown subfolders.",
    )
    parser.add_argument(
        "--db-dir",
        default=None,
        help="Destination database folder (one markdown file per company).",
    )
    parser.add_argument(
        "--schemas-dir",
        default=None,
        help="Schemas directory for schema-class-specific templates. Overrides openai.schemas_dir from config.yaml.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file used for storage.database_dir default.",
    )
    parser.add_argument(
        "--keep-merged-source",
        action="store_true",
        help="Keep company source folders after merge (default behavior is to delete after successful append).",
    )

    args = parser.parse_args()
    source_dir = Path(args.source_dir)
    db_dir = _resolve_db_dir(args.db_dir, args.config)
    schemas_dir = _resolve_schemas_dir(args.schemas_dir, args.config)

    print(f"Source: {source_dir}")
    print(f"Database: {db_dir}")
    if schemas_dir:
        print(f"Schemas dir: {schemas_dir}")
    print("Mode: merge-only (no search/scrape/research)")

    return run_merge(
        source_dir=source_dir,
        db_dir=db_dir,
        keep_merged_source=args.keep_merged_source,
        schemas_dir=schemas_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
