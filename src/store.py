# src/store.py
from __future__ import annotations
import re
from pathlib import Path
import yaml
from datetime import datetime, timezone

def safe_slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\-]+", "-", text.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"

def company_dirs(base_dir: str, company: str) -> dict[str, Path]:
    # Use prettified name with proper capitalization and acronym handling
    pretty = pretty_company_name_enhanced(company)
    if not pretty:
        pretty = safe_slug(company)
    else:
        # Ensure no filesystem-unsafe characters
        pretty = re.sub(r'[<>:"/\\|?*]+', " ", pretty)
        pretty = re.sub(r"\s+", " ", pretty).strip()
    
    root = Path(base_dir) / pretty
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


def _as_list(value):
    """Ensure a normalized value is always a list (or None).

    Wraps a single string in a list so that single-value fields are stored
    consistently as lists rather than bare strings.
    """
    if value is None:
        return None
    return value if isinstance(value, list) else [value]


def append_to_list_field(existing, new_value):
    """Append new_value to an existing list field, avoiding duplicates.
    
    Args:
        existing: The existing value (None, str, or list)
        new_value: The value to append (str or list)
    
    Returns:
        The combined list, or None if both are None/empty
    """
    if new_value is None:
        return existing
    
    # Normalize the new value first
    normalized_new = normalize_list_field(new_value)
    if normalized_new is None:
        return existing
    
    # Convert to list if needed
    new_list = normalized_new if isinstance(normalized_new, list) else [normalized_new]
    
    # If existing is None/empty, return new as-is
    if existing is None:
        return new_list if len(new_list) > 1 else new_list[0]
    
    # Convert existing to list if needed
    existing_list = existing if isinstance(existing, list) else [existing]
    
    # Append new items, avoiding duplicates (case-insensitive)
    existing_lower = [str(item).lower() for item in existing_list]
    for item in new_list:
        if str(item).lower() not in existing_lower:
            existing_list.append(item)
    
    # Return as list if multiple items, otherwise as string
    return existing_list if len(existing_list) > 1 else existing_list[0]


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
    except (ValueError, TypeError):
        ws = str(website)

    meta = {
        "website": ws,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "focus": _as_list(normalize_list_field(focus)),
        "firm_type": _as_list(normalize_list_field(firm_type)),
        "source": _as_list(normalize_list_field(source)),
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

def update_metadata_in_files(md_dir: Path, updates: dict) -> int:
    """Update metadata fields in existing markdown files.
    
    For list fields (focus, firm_type, source, prop_type, loan_type), appends new values
    to existing ones. For other fields, only adds if they don't exist.
    Never overwrites the date field.
    
    Args:
        md_dir: Path to directory containing markdown files
        updates: Dict of metadata fields to add/append (e.g., {"focus": "value", "firm_type": "value"})
    
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
                    try:
                        meta = yaml.safe_load(parts[1]) or {}
                    except yaml.YAMLError:
                        meta = {}
                    body = parts[2]
                    
                    # Normalize existing focus/firm_type/source/prop_type/loan_type if they were stored comma-separated
                    for key in ("focus", "firm_type", "source", "prop_type", "loan_type"):
                        if isinstance(meta.get(key), str) and "," in meta.get(key, ""):
                            meta[key] = normalize_list_field(meta.get(key))
                    # Ensure focus/firm_type/source are always stored as lists
                    for key in ("focus", "firm_type", "source"):
                        if meta.get(key) is not None:
                            meta[key] = _as_list(meta[key])

                    # Preserve existing date if the file has one
                    existing_date = meta.get("date")

                    # Update metadata fields
                    file_changed = False
                    for key, value in updates.items():
                        if value is None:
                            continue
                        # Never overwrite existing date
                        if key == "date" and existing_date:
                            continue
                        
                        # For list fields, append to existing values
                        if key in ("focus", "firm_type", "source", "prop_type", "loan_type"):
                            if key in meta and meta.get(key) is not None:
                                # Append to existing list
                                result = append_to_list_field(meta[key], value)
                                meta[key] = _as_list(result) if key in ("focus", "firm_type", "source") else result
                                file_changed = True
                            else:
                                # Field doesn't exist or is None, add new value
                                new_val = normalize_list_field(value)
                                meta[key] = _as_list(new_val) if key in ("focus", "firm_type", "source") else new_val
                                if meta[key] is not None:
                                    file_changed = True
                        else:
                            # For non-list fields, only add if they don't exist
                            if key not in meta or meta.get(key) is None:
                                if key == "company":
                                    meta[key] = pretty_company_name(value)
                                else:
                                    meta[key] = value
                                file_changed = True
                    
                    # Only write back if something changed
                    if file_changed:
                        # Ensure date is preserved in the metadata
                        if existing_date:
                            meta["date"] = existing_date
                        
                        # Write back updated file
                        fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
                        content = f"---\n{fm}---{body}"
                        md_file.write_text(content, encoding="utf-8")
                        updated_count += 1
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            continue
    
    return updated_count