# src/store.py
import re
from pathlib import Path
import yaml
from datetime import datetime

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

def default_metadata(website: str, focus: str | None = None) -> dict:
    """Return default metadata for a captured page.

    Fields:
      - website: normalized site root (scheme://host/)
      - focus: optional user-provided focus value
      - date: UTC timestamp

    Note: removed keys: company, notes, tags, version, city, state (city/state removed per request).
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
        "date": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "focus": focus,
    }