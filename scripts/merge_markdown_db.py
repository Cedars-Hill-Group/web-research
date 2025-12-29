"""Interactive tool to add company markdown files into a centralized database.

Database format (flat):
- DB_DIR/companies/<company-slug>.md
  (one markdown file per company; filename is a slugified company name)

This script will iterate company subfolders under the source directory (default: `data/companies`),
collect markdown files from each company's `markdown/` folder, then either append their content to an
existing company markdown file in the DB (using fuzzy matching), or create a new one.

Usage: python scripts/merge_markdown_db.py
"""
import difflib
from pathlib import Path
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.store import safe_slug

SRC_DIR = Path("data/companies")
DB_DIR = Path("C:\\Obsidian\\Josh's Garden\\Companies")

THRESHOLD = 0.75


def choose_match(name: str, candidates: list[str]) -> str | None:
    """Return a chosen candidate stem (filename without .md) or None."""
    if not candidates:
        return None
    best = difflib.get_close_matches(name, candidates, n=1, cutoff=THRESHOLD)
    close = difflib.get_close_matches(name, candidates, n=5, cutoff=THRESHOLD/2)

    if best:
        b = best[0]
        resp = input(f"Found close match in DB: '{b}' for '{name}'. Use it? (y/n): ").strip().lower()
        if resp == "y":
            return b
    # fallback: ask user to pick from list or none
    print("No suitable automatic match. Candidates:")
    for i, c in enumerate(close, 1):
        print(f"  {i}. {c}")
    resp = input("Enter number to choose existing, 'n' for new, or 's' to skip: ").strip().lower()
    if resp == "s":
        return None
    if resp == "n":
        return None
    try:
        idx = int(resp) - 1
        if 0 <= idx < len(close):
            return close[idx]
    except Exception:
        pass
    return None


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


def append_markdown_to_company(src: Path, dst_file: Path) -> bool:
    """Append src markdown into dst_file. Returns True if appended, False if skipped (duplicate).

    Behavior changes:
      - If dst_file exists and contains YAML front matter, update/merge metadata from src
        (src fields overwrite/add to dst metadata except 'company' and 'created_at').
      - If dst_file exists and has no front matter, insert merged metadata at the top of the file.
    Deduplication: we compare a short fingerprint (first 200 chars of src) against dst content.
    """
    text = src.read_text(encoding="utf-8")
    fingerprint = "\n".join(text.splitlines()[:10]).strip()[:200]

    dst_text = dst_file.read_text(encoding="utf-8") if dst_file.exists() else ""
    if fingerprint and fingerprint in dst_text:
        return False

    # Extract metadata and body from source file (if present)
    src_meta, src_body = _parse_front_matter(text)

    # Ensure dst dir exists
    dst_file.parent.mkdir(parents=True, exist_ok=True)

    # determine company name from expected layout: company/markdown/file.md
    if src.parent.name == 'markdown' and src.parent.parent:
        company_name = src.parent.parent.name
    else:
        company_name = src.parent.name

    if dst_file.exists():
        # read existing meta (if any) and merge
        dst_meta, dst_body = _parse_front_matter(dst_text)
        if not dst_meta:
            # create base metadata if missing
            dst_meta = {}

        # If there is a date in the body (not metadata), prefer it and remove it from the body
        import re
        if "date" not in dst_meta:
            # look for ISO date/time or YYYY-MM-DD in the body, handling markdown formatting (bold, italics, etc.)
            # This regex strips out common markdown formatting like **, *, __, _, ~~, etc. around dates
            m = re.search(r"(?:[*_~`]{{1,3}})?(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z?)?)(?:[*_~`]{{1,3}})?", dst_body)
            if m:
                dst_meta["date"] = m.group(1)
                # remove the entire matched occurrence including any formatting (first occurrence)
                dst_body = re.sub(re.escape(m.group(0)), "", dst_body, count=1)

        # merge fields from src_meta into dst_meta, but preserve certain keys
        for k, v in (src_meta or {}).items():
            if k in ("company", "created_at"):
                continue
            if k == "date" and "date" in dst_meta:
                # preserve the older date (the minimum)
                dst_d = _parse_date(dst_meta.get("date"))
                src_d = _parse_date(v)
                if dst_d and src_d:
                    # normalize to comparable timestamps (handle naive vs aware)
                    from datetime import timezone
                    def _ts(dt):
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt.timestamp()
                    src_ts = _ts(src_d)
                    dst_ts = _ts(dst_d)
                    chosen = dst_d if dst_ts <= src_ts else src_d
                    # record as ISO string (preserve date-first ordering)
                    dst_meta["date"] = chosen.isoformat()
                else:
                    # if parsing failed, prefer existing dst_meta value
                    dst_meta["date"] = dst_meta.get("date")
            else:
                dst_meta[k] = v
        # write back the possibly updated front matter and existing body
        _write_with_front_matter(dst_file, dst_meta, dst_body)
    else:
        # create new file with merged metadata (src_meta preferred, but exclude company field)
        meta = {}
        if src_meta:
            for k, v in src_meta.items():
                if k == "company":
                    continue
                meta[k] = v
        _write_with_front_matter(dst_file, meta, "\n")

    # append the content (body only, without front matter)
    with dst_file.open("a", encoding="utf-8") as fh:
        fh.write("\n\n<!-- appended from: {} -->\n\n".format(src.name))
        fh.write(src_body)
    return True


def main():
    src = SRC_DIR
    db = DB_DIR
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

        match = choose_match(company_name, existing)
        if match:
            target_file = db / f"{match}.md"
        else:
            # new company -> create new markdown file using a slug filename
            slug = safe_slug(company_name)
            target_file = db / f"{slug}.md"
            if target_file.exists():
                # if collision on slug, add numeric suffix
                i = 1
                while True:
                    candidate = db / f"{slug}-{i}.md"
                    if not candidate.exists():
                        target_file = candidate
                        break
                    i += 1
            print(f"Creating new company entry in DB: {target_file.name}")
            existing.append(target_file.stem)

        # append files into target file
        appended_count = 0
        for f in mdfiles:
            appended = append_markdown_to_company(f, target_file)
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
