from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml


def insert_under_heading(body: str, heading: str, addition: str) -> str:
    """Insert content under a markdown heading (case-insensitive)."""
    if not addition.strip():
        return body

    lines = body.splitlines()
    target_idx = None
    for i, line in enumerate(lines):
        stripped = line.lstrip("#").strip()
        if stripped.lower() == heading.lower():
            target_idx = i
            break

    addition_block = addition.strip()

    if target_idx is None:
        prefix = "\n\n" if body.strip() else ""
        return f"{body.rstrip()}{prefix}## {heading}\n\n{addition_block}\n"

    insert_at = target_idx + 1
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1

    new_lines = lines[:insert_at] + ["", addition_block, ""] + lines[insert_at:]
    return "\n".join(new_lines).strip() + "\n"


def normalize_heading(heading: str) -> str:
    return re.sub(r"\s+", " ", heading).strip().lower()


def extract_h2_headings(body: str) -> list[str]:
    headings: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^\s{0,3}##\s+(.+?)\s*$", line)
        if not m:
            continue
        heading = re.sub(r"\s+#+\s*$", "", m.group(1)).strip()
        if heading:
            headings.append(heading)
    return headings


def parse_h2_sections(body: str) -> tuple[str, list[tuple[str, str]]]:
    """Split markdown into preamble and level-2 sections."""
    preamble_lines: list[str] = []
    sections: list[tuple[str, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_heading, current_lines
        if current_heading is None:
            return
        sections.append((current_heading, "\n".join(current_lines).strip()))
        current_heading = None
        current_lines = []

    for line in body.splitlines():
        m = re.match(r"^\s{0,3}##\s+(.+?)\s*$", line)
        if m:
            flush()
            heading = re.sub(r"\s+#+\s*$", "", m.group(1)).strip()
            current_heading = heading
            current_lines = []
            continue

        if current_heading is None:
            preamble_lines.append(line)
        else:
            current_lines.append(line)

    flush()
    return "\n".join(preamble_lines).strip(), sections


def insert_source_sections_into_template(dst_body: str, src_body: str, source_tag: str) -> str:
    """Merge source sections into matching template `##` headings."""
    template_headings = extract_h2_headings(dst_body)
    fallback_heading = template_headings[0] if template_headings else "Overview"

    preamble, src_sections = parse_h2_sections(src_body)
    if not src_sections:
        addition = f"{source_tag}\n\n{src_body.strip()}".strip() + "\n"
        return insert_under_heading(dst_body, fallback_heading, addition)

    section_map: dict[str, list[tuple[str, str]]] = {}
    for heading, content in src_sections:
        key = normalize_heading(heading)
        section_map.setdefault(key, []).append((heading, content))

    inserted_any = False
    for heading in template_headings:
        key = normalize_heading(heading)
        matches = section_map.pop(key, [])
        for _, content in matches:
            if not (content or "").strip():
                continue
            addition = f"{source_tag}\n\n{content.strip()}\n"
            dst_body = insert_under_heading(dst_body, heading, addition)
            inserted_any = True

    leftovers: list[str] = []
    if preamble.strip():
        leftovers.append(preamble.strip())
    for heading_groups in section_map.values():
        for heading, content in heading_groups:
            block = f"### {heading}\n\n{(content or '').strip()}".strip()
            if block:
                leftovers.append(block)

    if leftovers:
        addition = f"{source_tag}\n\n" + "\n\n".join(leftovers).strip() + "\n"
        dst_body = insert_under_heading(dst_body, fallback_heading, addition)
        inserted_any = True

    if not inserted_any:
        addition = f"{source_tag}\n\n{src_body.strip()}".strip() + "\n"
        dst_body = insert_under_heading(dst_body, fallback_heading, addition)

    return dst_body


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Return `(meta, body)` from markdown text with optional YAML front matter."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            body = parts[2]
            try:
                meta = yaml.safe_load(fm) or {}
            except yaml.YAMLError:
                meta = {}
            return meta, body
    return {}, text


def write_with_front_matter(path: Path, meta: dict, body: str) -> None:
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    content = f"---\n{fm}---\n{body.lstrip()}"
    path.write_text(content, encoding="utf-8")


def parse_date(value: str) -> datetime | None:
    """Parse ISO-like date strings and date-only values to datetime."""
    if not value:
        return None
    v = str(value).strip()
    try:
        if v.endswith("Z"):
            return datetime.fromisoformat(v[:-1] + "+00:00")
        return datetime.fromisoformat(v)
    except ValueError:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", v)
        if m:
            try:
                return datetime.fromisoformat(m.group(1))
            except ValueError:
                return None
        return None
