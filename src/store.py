# src/store.py
import re
from pathlib import Path
import yaml
from datetime import datetime, UTC

def safe_slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\-]+", "-", text.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"

def company_dirs(base_dir: str, company: str) -> dict[str, Path]:
    root = Path(base_dir) / safe_slug(company)
    dirs = {
        "root": root,
        "html": root / "raw_html",
        "md": root / "markdown",
        "pdf": root / "pdf",
        "assets": root / "assets",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs

def write_html(dir_path: Path, slug: str, html: str) -> Path:
    path = dir_path / f"{slug}.html"
    path.write_text(html, encoding="utf-8")
    return path

def write_markdown(dir_path: Path, slug: str, md: str, meta: dict) -> Path:
    path = dir_path / f"{slug}.md"
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    content = f"---\n{fm}---\n\n{md}"
    path.write_text(content, encoding="utf-8")
    return path


def normalize_list_field(value):
    """Return a normalized field value that becomes a YAML list when comma-separated.

    - If the input is a string containing commas, split on commas and trim items.
    - If the input is already a list, trim items and drop empties.
    - If the input is a single string without commas, return the trimmed string.
    - For None/empty values, return None.
    """
    if value is None:
        return None
    if isinstance(value, list):
        items = [str(v).strip() for v in value if str(v).strip()]
        return items if items else None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(',') if p.strip()]
        if len(parts) >= 2:
            return parts
        return parts[0] if parts else None
    return value


def pretty_company_name(name: str | None) -> str | None:
    """Convert a company identifier into Title Case words without dashes/underscores."""
    if not name:
        return None
    cleaned = re.sub(r"[-_]+", " ", str(name))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else None

def default_metadata(website: str, focus: str | None = None, firm_type: str | None = None, source: str | None = None) -> dict:
    """Return default metadata for a captured page.

    Fields:
      - website: normalized site root (scheme://host/)
      - focus: optional user-provided focus value
      - firm_type: optional firm type classification
      - source: optional source classification
      - date: UTC timestamp

    Note: removed keys: notes, tags, version, city, state, company (company is determined by directory structure).
    """
    # normalize website root
    ws = website or ""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(str(website))
        if not parsed.netloc and parsed.path:
            parsed = urlparse("http://" + str(website))
        if parsed.scheme and parsed.netloc:
            ws = f"{parsed.scheme}://{parsed.netloc}/"
        else:
            ws = str(website)
    except Exception:
        ws = str(website)

    return {
        "website": ws,
        "date": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "focus": normalize_list_field(focus),
        "firm_type": normalize_list_field(firm_type),
        "source": normalize_list_field(source),
    }

def update_metadata_in_files(md_dir: Path, updates: dict) -> int:
    """Update metadata fields in existing markdown files.
    
    Args:
        md_dir: Path to directory containing markdown files
        updates: Dict of metadata fields to update (e.g., {"focus": "value", "firm_type": "value"})
    
    Returns:
        Number of files updated
    """
    if not md_dir.exists():
        return 0
    
    updated_count = 0
    for md_file in md_dir.glob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            
            # Parse existing front matter
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    import yaml
                    try:
                        meta = yaml.safe_load(parts[1]) or {}
                    except Exception:
                        meta = {}
                    body = parts[2]
                    
                    # Normalize existing focus/firm_type/source if they were stored comma-separated
                    for key in ("focus", "firm_type", "source"):
                        if isinstance(meta.get(key), str) and "," in meta.get(key, ""):
                            meta[key] = normalize_list_field(meta.get(key))

                    # Preserve existing date if the file has one
                    existing_date = meta.get("date")

                    # Update metadata with new values
                    for key, value in updates.items():
                        if value is None:
                            continue
                        # Preserve existing date if it exists
                        if key == "date" and existing_date:
                            continue
                        if key == "company":
                            meta[key] = pretty_company_name(value)
                        elif key in ("focus", "firm_type", "source"):
                            meta[key] = normalize_list_field(value)
                        else:
                            meta[key] = value
                    
                    # Ensure date is preserved in the metadata
                    if existing_date:
                        meta["date"] = existing_date
                    
                    # Write back updated file
                    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
                    content = f"---\n{fm}---{body}"
                    md_file.write_text(content, encoding="utf-8")
                    updated_count += 1
        except Exception:
            continue
    
    return updated_count