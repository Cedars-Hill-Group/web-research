"""Merge-only utility: consolidate existing markdown under data/companies into a DB folder.

This script does not run website search, scraping, or AI research. It only reads
existing markdown files that already exist under the configured source directory and merges them
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
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import merge_helpers  # noqa: E402
from scripts.merge_markdown_db import (  # noqa: E402
    append_markdown_to_company,
    choose_match,
    _build_company_repo,
    _resolve_template,
)
from src.config import load_config, resolve_storage_paths  # noqa: E402
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
    for md_file in md_files:
        meta = _load_front_matter_meta(md_file)
        if not meta:
            continue
        schema = str(meta.get("schema") or "").strip()
        if schema:
            return schema
    return None


def _extract_company_name(md_files: list[Path], fallback: str) -> str:
    for md_file in md_files:
        meta = _load_front_matter_meta(md_file)
        if not meta:
            continue
        company = str(meta.get("company") or "").strip()
        if company:
            return company
    return fallback


def _load_front_matter_meta(md_file: Path) -> dict:
    try:
        text = md_file.read_text(encoding="utf-8")
    except OSError:
        return {}

    meta, _ = merge_helpers.parse_front_matter(text)
    return meta if isinstance(meta, dict) else {}


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

    # Load existing KB companies into CompanyRepository for deterministic
    # entity resolution (Phase 3). Falls back to splink when data-platform
    # is not installed.
    repo = _build_company_repo(db_dir)
    if repo is not None:
        print("Loaded existing companies into entity resolution repository.")

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

        # Extract website for domain-based entity resolution.
        website = None
        for md_file in md_files:
            meta = _load_front_matter_meta(md_file)
            if meta.get("website"):
                website = str(meta["website"])
                break

        print(f"\nProcessing: {company_name}")
        match, custom_name = choose_match(company_name, existing, repo=repo, website=website)

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
                print(f"  Company processing complete; source folder removed: {company_name}")
            except OSError as exc:
                print(f"  Warning: failed to delete {company_dir}: {exc}")
        else:
            print(f"  Company processing complete; source folder preserved (--keep-merged-source): {company_name}")

    print("\nMerge complete.")
    print(f"Companies with markdown found: {companies_seen}")
    print(f"Companies with new appended data: {companies_merged}")
    print(f"Markdown files appended: {files_appended}")
    print(f"Markdown files skipped as duplicates: {files_skipped}")

    return 0


def _resolve_storage_dirs(
    cli_source_dir: str | None,
    cli_db_dir: str | None,
    config_path: str,
) -> tuple[Path, Path]:
    resolved = resolve_storage_paths(
        config_path,
        source_dir_override=cli_source_dir,
        database_dir_override=cli_db_dir,
    )
    return resolved["source_dir"], resolved["database_dir"]


def _resolve_schemas_dir(cli_schemas_dir: str | None, config_path: str) -> Path | None:
    if cli_schemas_dir:
        return Path(cli_schemas_dir)

    try:
        cfg = load_config(config_path)
        configured = (cfg.get("openai") or {}).get("schemas_dir")
        if configured:
            return Path(str(configured))
    except (FileNotFoundError, OSError, ValueError, TypeError, yaml.YAMLError):
        pass

    default = Path("schemas")
    return default if default.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge existing markdown under data/companies into a flat DB folder."
    )
    parser.add_argument(
        "--source-dir",
        default=None,
        help="Root folder containing per-company folders with markdown subfolders (defaults to data/companies).",
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
    source_dir, db_dir = _resolve_storage_dirs(args.source_dir, args.db_dir, args.config)
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
