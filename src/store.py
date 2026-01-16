# src/store.py
import re
from pathlib import Path
import yaml
from datetime import datetime, timezone

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

def pretty_company_name_enhanced(name: str | None) -> str | None:
    """Convert a company identifier into properly capitalized words with acronym support.
    
    Removes dashes/underscores, capitalizes first letter of each word, and properly
    capitalizes common acronyms and business entity suffixes like LLC, LLP, Inc, etc.
    """
    if not name:
        return None
    
    # Remove dashes and underscores, normalize spaces
    cleaned = re.sub(r"[-_]+", " ", str(name))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    
    if not cleaned:
        return None
    
    # Apply title case first
    words = cleaned.title().split()
    
    # Common acronyms and terms that should be all caps
    acronyms = {
        'Llc', 'Lllc', 'Llp', 'Lp', 'Pc', 'Pa', 'Pllc', 'Plc',
        'Inc', 'Corp', 'Ltd', 'Usa', 'Uk', 'Us', 'Cpa', 'Md', 'Dds',
        'Phd', 'Mba', 'Ceo', 'Cfo', 'Cto', 'Hr', 'It', 'Ai', 'Vc',
        'Pe', 'Re', 'Reit', 'Etf', 'Ira', 'Hsa', 'Fico', 'Api'
    }
    
    # Process each word
    result = []
    for word in words:
        # Check if word should be all caps
        if word in acronyms:
            result.append(word.upper())
        # Check if word ends with 's (possessive) and base is an acronym
        elif word.endswith("'S") or word.endswith("'s"):
            base = word[:-2]
            if base in acronyms:
                result.append(base.upper() + word[-2:])
            else:
                result.append(word)
        else:
            result.append(word)
    
    return ' '.join(result)

def default_metadata(website: str, focus: str | None = None, firm_type: str | None = None, source: str | None = None, prop_type: str | None = None, loan_type: str | None = None) -> dict:
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

    meta = {
        "website": ws,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "focus": normalize_list_field(focus),
        "firm_type": normalize_list_field(firm_type),
        "source": normalize_list_field(source),
    }

    # Only include prop_type when provided (user left blank -> omit field)
    prop_val = normalize_list_field(prop_type)
    if prop_val is not None:
        meta["prop_type"] = prop_val

    # Only include loan_type when provided (user left blank -> omit field)
    loan_val = normalize_list_field(loan_type)
    if loan_val is not None:
        meta["loan_type"] = loan_val

    return meta

def update_metadata_in_files(md_dir: Path, updates: dict, append_mode: bool = True) -> int:
    """Update metadata fields in existing markdown files.
    
    Args:
        md_dir: Path to directory containing markdown files
        updates: Dict of metadata fields to update (e.g., {"focus": "value", "firm_type": "value"})
        append_mode: If True, append metadata updates to a "metadata_updates" section instead of overwriting.
                     If False, overwrite metadata as before.
    
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
                    
                    if append_mode:
                        # APPEND MODE: Add metadata update entry to metadata_updates list
                        # Preserve existing date if the file has one
                        existing_date = meta.get("date")
                        
                        # Build the update entry with timestamp
                        update_entry = {}
                        for key, value in updates.items():
                            if value is None:
                                continue
                            if key == "company":
                                update_entry[key] = pretty_company_name(value)
                            elif key in ("focus", "firm_type", "source", "prop_type", "loan_type"):
                                update_entry[key] = normalize_list_field(value)
                            else:
                                update_entry[key] = value
                        
                        # Add timestamp to this update
                        update_entry["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                        
                        # Initialize metadata_updates list if it doesn't exist
                        if "metadata_updates" not in meta:
                            meta["metadata_updates"] = []
                        elif not isinstance(meta["metadata_updates"], list):
                            meta["metadata_updates"] = []
                        
                        # Append the new update entry
                        meta["metadata_updates"].append(update_entry)
                    else:
                        # OVERWRITE MODE: Replace metadata as before (original behavior)
                        # Normalize existing focus/firm_type/source/prop_type/loan_type if they were stored comma-separated
                        for key in ("focus", "firm_type", "source", "prop_type", "loan_type"):
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
                            elif key in ("focus", "firm_type", "source", "prop_type", "loan_type"):
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