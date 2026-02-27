"""Interactive tool to add company markdown files into a centralized database.

Database format (flat):
- DB_DIR/<company-name>.md
  (one markdown file per company; filename is a slugified company name)

This script will iterate company subfolders under the source directory (default: `data/companies`),
collect markdown files from each company's `markdown/` folder, then either append their content to an
existing company markdown file in the DB (using fuzzy matching), or create a new one.

Usage: python scripts/merge_markdown_db.py
"""
from __future__ import annotations

import argparse
import difflib
import re
from pathlib import Path
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.store import safe_slug, pretty_company_name, pretty_company_name_enhanced, normalize_list_field, append_to_list_field
from src.config import load_config

SRC_DIR = Path("data/companies")
DB_DIR = Path("company_markdown_db/companies")
TEMPLATE_PATH = Path("C:\\Obsidian\\Josh's Garden\\templates\\company template.md")

THRESHOLD = 0.75


def _clean_company_filename(name: str, db_dir: Path, preserve_case: bool = False) -> Path:
    """Return a Title Case filename with spaces (no dashes) that is safe for the filesystem.
    
    Args:
        name: The company name
        db_dir: The database directory
        preserve_case: If True, preserve the original capitalization (useful for user input)
    """
    if preserve_case:
        # For user-provided names, only clean dangerous characters but preserve capitalization
        pretty = name.strip()
        pretty = re.sub(r'[<>:"/\\|?*]+', " ", pretty)
        pretty = re.sub(r"\s+", " ", pretty).strip() or "Company"
    else:
        # For derived names, use enhanced prettification with acronym support
        pretty = pretty_company_name_enhanced(name) or safe_slug(name)
        pretty = re.sub(r'[<>:"/\\|?*]+', " ", pretty)
        pretty = re.sub(r"\s+", " ", pretty).strip() or "Company"

    candidate = pretty
    idx = 1
    while True:
        suffix = "" if idx == 1 else f" {idx}"
        filename = f"{candidate}{suffix}.md"
        path = db_dir / filename
        if not path.exists():
            return path
        idx += 1


def _insert_under_heading(body: str, heading: str, addition: str) -> str:
    """Insert the addition under the given markdown heading (case-insensitive)."""
    if not addition.strip():
        return body

    lines = body.splitlines()
    target_idx = None
    for i, line in enumerate(lines):
        stripped = line.lstrip('#').strip()
        if stripped.lower() == heading.lower():
            target_idx = i
            break

    addition_block = addition.strip()

    if target_idx is None:
        # create the heading if missing
        prefix = "\n\n" if body.strip() else ""
        return f"{body.rstrip()}{prefix}## {heading}\n\n{addition_block}\n"

    insert_at = target_idx + 1
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1

    new_lines = lines[:insert_at] + ["", addition_block, ""] + lines[insert_at:]
    return "\n".join(new_lines).strip() + "\n"


def choose_match(name: str, candidates: list[str]) -> tuple[str | None, str | None]:
    """Return a tuple of (chosen_candidate_stem, custom_company_name).
    
    Returns:
        - (candidate_stem, None): Use existing company with that stem
        - (None, custom_name): Create new company with custom name
        - (None, None): Skip this company
    """
    if not candidates:
        return (None, None)
    best = difflib.get_close_matches(name, candidates, n=1, cutoff=THRESHOLD)
    close = difflib.get_close_matches(name, candidates, n=5, cutoff=THRESHOLD/2)

    if best:
        b = best[0]
        resp = input(f"Found close match in DB: '{b}' for '{name}'. Use it? (y/n): ").strip().lower()
        if resp == "y":
            return (b, None)
    # fallback: ask user to pick from list or none
    print("No suitable automatic match. Candidates:")
    for i, c in enumerate(close, 1):
        print(f"  {i}. {c}")
    resp = input("Enter number to choose existing, 'n' for new, or 's' to skip: ").strip().lower()
    if resp == "s":
        return (None, None)
    if resp == "n":
        # Prompt for the company name to save in the database
        custom_name = input(f"Enter company name for database (or press Enter to use '{name}'): ").strip()
        if not custom_name:
            custom_name = name
        return (None, custom_name)
    try:
        idx = int(resp) - 1
        if 0 <= idx < len(close):
            return (close[idx], None)
    except Exception:
        pass
    return (None, None)


def _parse_front_matter(text: str) -> tuple[dict, str]:
    """Return (meta, body) where meta is a dict (possibly empty) and body is the rest of the file."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            body = parts[2]
            try:
                import yaml
                meta = yaml.safe_load(fm) or {}
            except Exception:
                meta = {}
            return (meta, body)
    return ({}, text)


def _write_with_front_matter(path: Path, meta: dict, body: str) -> None:
    import yaml
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    content = f"---\n{fm}---\n{body.lstrip()}"
    path.write_text(content, encoding="utf-8")


def _parse_date(value: str) -> "datetime | None":
    """Attempt to parse an ISO-like date string into a datetime. Return None on failure."""
    if not value:
        return None
    v = str(value).strip()
    try:
        # handle trailing Z
        if v.endswith('Z'):
            v2 = v[:-1] + '+00:00'
            from datetime import datetime
            return datetime.fromisoformat(v2)
        from datetime import datetime
        # try full iso
        return datetime.fromisoformat(v)
    except Exception:
        # try date-only yyyy-mm-dd
        import re
        m = re.search(r"(\d{4}-\d{2}-\d{2})", v)
        if m:
            try:
                from datetime import datetime
                return datetime.fromisoformat(m.group(1))
            except Exception:
                return None
        return None


def append_markdown_to_company(src: Path, dst_file: Path, company_display: str | None = None) -> bool:
    """Append src markdown into dst_file. Returns True if appended, False if skipped (duplicate).

    Behavior changes:
      - Uses a company template (if present) for new files and inserts scraped content under the
        "Basic Underwriting" heading.
      - Normalizes focus/firm_type to YAML lists when comma-separated.
      - Stores company names in Title Case with spaces (no dashes) in metadata and filenames.
    """
    text = src.read_text(encoding="utf-8")
    fingerprint = "\n".join(text.splitlines()[:10]).strip()[:200]

    dst_text = dst_file.read_text(encoding="utf-8") if dst_file.exists() else ""
    if fingerprint and fingerprint in dst_text:
        return False

    # Extract metadata and body from source file (if present)
    src_meta, src_body = _parse_front_matter(text)
    src_body = (src_body or "").lstrip()

    # Determine a human-friendly company name
    derived_company = pretty_company_name(company_display or (src_meta or {}).get("company"))
    if not derived_company:
        if src.parent.name == 'markdown' and src.parent.parent:
            derived_company = pretty_company_name(src.parent.parent.name)
        else:
            derived_company = pretty_company_name(src.parent.name)

    # Load destination metadata/body, preferring the template when creating a new file
    if (not dst_file.exists() or not dst_text.strip()) and TEMPLATE_PATH.exists():
        try:
            tpl_text = TEMPLATE_PATH.read_text(encoding="utf-8")
            dst_meta, dst_body = _parse_front_matter(tpl_text)
        except Exception:
            dst_meta, dst_body = ({}, dst_text)
    else:
        dst_meta, dst_body = _parse_front_matter(dst_text)

    dst_meta = dst_meta or {}
    dst_body = dst_body or ""

    # If there is a date in the body (not metadata), prefer it and remove it from the body
    if "date" not in dst_meta:
        m = re.search(r"(?:[*_~`]{{1,3}})?(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z?)?)(?:[*_~`]{{1,3}})?", dst_body)
        if m:
            dst_meta["date"] = m.group(1)
            dst_body = re.sub(re.escape(m.group(0)), "", dst_body, count=1)

    # Normalize existing focus/firm_type values
    for key in ("focus", "firm_type"):
        if key in dst_meta:
            dst_meta[key] = normalize_list_field(dst_meta.get(key))

    # merge fields from src_meta into dst_meta, but preserve created_at and prefer older date
    for k, v in (src_meta or {}).items():
        if k in ("created_at",):
            continue
        if k == "company":
            continue
        if k == "date":
            if "date" not in dst_meta:
                # If destination doesn't have a date, use source's date
                dst_meta["date"] = v
            else:
                # Both have dates, preserve the older one
                dst_d = _parse_date(dst_meta.get("date"))
                src_d = _parse_date(v)
                if dst_d and src_d:
                    from datetime import timezone
                    def _ts(dt):
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt.timestamp()
                    src_ts = _ts(src_d)
                    dst_ts = _ts(dst_d)
                    chosen = dst_d if dst_ts <= src_ts else src_d
                    dst_meta["date"] = chosen.isoformat()
                else:
                    dst_meta["date"] = dst_meta.get("date") or v
        elif k in ("focus", "firm_type", "source", "prop_type", "loan_type"):
            # For list fields, append to existing values instead of overwriting
            if k in dst_meta and dst_meta.get(k) is not None:
                dst_meta[k] = append_to_list_field(dst_meta[k], v)
            else:
                dst_meta[k] = normalize_list_field(v)
        else:
            dst_meta[k] = v

    # Do NOT include company field in destination file metadata
    # (company is determined by directory structure and file location)
    dst_meta.pop("company", None)

    # Ensure date is always set (use current date if not already present)
    if "date" not in dst_meta:
        from datetime import datetime, timezone
        dst_meta["date"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    # Build the addition block and insert under Basic Underwriting
    addition = f"<!-- appended from: {src.name} -->\n\n{src_body}".strip() + "\n"
    dst_body = _insert_under_heading(dst_body, "Basic Underwriting", addition)

    # Ensure dst dir exists and write updated file with front matter
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    _write_with_front_matter(dst_file, dst_meta, dst_body)
    return True


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

    return DB_DIR


def main():
    parser = argparse.ArgumentParser(
        description="Merge markdown under data/companies into a flat markdown DB folder."
    )
    parser.add_argument(
        "--source-dir",
        default=str(SRC_DIR),
        help="Root folder containing per-company folders with markdown subfolders.",
    )
    parser.add_argument(
        "--db-dir",
        default=None,
        help="Destination database folder. Overrides storage.database_dir from config.yaml.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file used for storage.database_dir default.",
    )
    args = parser.parse_args()

    src = Path(args.source_dir)
    db = _resolve_db_dir(args.db_dir, args.config)
    print(f"Source dir: {src}")
    print(f"DB dir: {db}")
    if not src.exists():
        print("Source dir does not exist. Exiting.")
        return
    db.mkdir(parents=True, exist_ok=True)

    # list existing db companies (file stems)
    existing = [p.stem for p in db.glob("*.md")]

    for comp_dir in sorted(src.iterdir()):
        if not comp_dir.is_dir():
            continue
        md_dir = comp_dir / "markdown"
        if not md_dir.exists():
            continue
        mdfiles = list(md_dir.glob("*.md"))
        if not mdfiles:
            continue

        # attempt to determine a canonical company name from metadata, else dir name
        company_name = None
        for f in mdfiles:
            text = f.read_text(encoding="utf-8")
            # look for YAML company: field on first 20 lines
            header = "\n".join(text.splitlines()[:20])
            import re
            m = re.search(r"^company:\s*(.+)$", header, re.I | re.M)
            if m:
                company_name = m.group(1).strip()
                break
        if not company_name:
            company_name = comp_dir.name

        print(f"\nProcessing company: {company_name} (from {comp_dir})")

        match, custom_name = choose_match(company_name, existing)
        if match:
            # Use existing company
            target_file = db / f"{match}.md"
        elif custom_name:
            # Create new company with custom name
            target_file = _clean_company_filename(custom_name, db, preserve_case=True)
            print(f"Creating new company entry in DB: {target_file.name}")
            existing.append(target_file.stem)
            # Use the custom name for metadata
            company_name = custom_name
        else:
            # Skip this company
            print(f"  Skipped company: {company_name}")
            continue

        # append files into target file
        appended_count = 0
        for f in mdfiles:
            appended = append_markdown_to_company(f, target_file, company_display=company_name)
            if appended:
                print(f"  Appended {f.name} -> {target_file.name}")
                appended_count += 1
            else:
                print(f"  Skipped (duplicate) {f.name} -> {target_file.name}")

        # Remove the company data folder if any files were successfully merged
        if appended_count > 0:
            try:
                import shutil
                shutil.rmtree(comp_dir)
                print(f"  Removed data folder: {comp_dir}")
            except Exception as e:
                print(f"  Warning: Could not remove data folder {comp_dir}: {e}")

    print("\nMerge complete.")


if __name__ == '__main__':
    main()
