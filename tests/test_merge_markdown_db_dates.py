from pathlib import Path
from scripts.merge_markdown_db import append_markdown_to_company, _resolve_template
import re
import yaml


def _read_front(path: Path):
    t = path.read_text(encoding='utf-8')
    parts = t.split('---', 2)
    if len(parts) >= 3:
        return yaml.safe_load(parts[1]), parts[2]
    return {}, t


def test_preserve_older_date(tmp_path):
    src = tmp_path / 'src'
    db = tmp_path / 'db'
    src.mkdir()
    db.mkdir()

    # src has newer date
    src_md = src / 's.md'
    src_md.write_text('''---\ncompany: X\ndate: '2025-12-10T00:00:00Z'\n---\n\n# New\n''', encoding='utf-8')

    dst = db / 'x.md'
    dst.write_text('''---\ncompany: X\ndate: '2025-11-01T00:00:00Z'\n---\n\n# Existing\n''', encoding='utf-8')

    appended = append_markdown_to_company(src_md, dst)
    assert appended
    meta, body = _read_front(dst)
    assert meta.get('date').startswith('2025-11-01')


def test_move_date_from_body_to_meta(tmp_path):
    src = tmp_path / 'src'
    db = tmp_path / 'db'
    src.mkdir()
    db.mkdir()

    src_md = src / 's2.md'
    src_md.write_text('''---\ncompany: Y\ndate: '2025-12-01T00:00:00Z'\n---\n\n# New\n''', encoding='utf-8')

    dst = db / 'y.md'
    # date present in body, no front matter
    dst.write_text('# Existing\nPublished: 2022-05-01\nExisting\n', encoding='utf-8')

    appended = append_markdown_to_company(src_md, dst)
    assert appended
    meta, body = _read_front(dst)
    # ensure date was moved from body into metadata and preserved
    assert meta.get('date') == '2022-05-01' or meta.get('date').startswith('2022-05-01')
    assert '2022-05-01' not in body


def test_append_uses_template_for_new_file(tmp_path):
    """When creating a new DB file, the provided template_content should be used as the base."""
    src_md = tmp_path / 'src.md'
    src_md.write_text(
        "---\nschema: commercial_real_estate\n---\n\nResearch content here.\n",
        encoding='utf-8',
    )

    template = "---\nwebsite:\ndate:\n---\n\n## Basic Underwriting\n\n## Overview\n"
    dst = tmp_path / 'dst.md'
    # dst does not exist yet

    appended = append_markdown_to_company(src_md, dst, template_content=template)
    assert appended
    content = dst.read_text(encoding="utf-8")
    assert "## Basic Underwriting" in content
    assert "## Overview" in content
    assert "Research content here" in content


def test_resolve_template_from_schemas_dir(tmp_path):
    """_resolve_template should find template.md inside a schema-class subdirectory."""
    schemas = tmp_path / "schemas"
    cls_dir = schemas / "general"
    cls_dir.mkdir(parents=True)
    tpl_file = cls_dir / "template.md"
    tpl_file.write_text("---\nwebsite:\n---\n## Basic Underwriting\n", encoding="utf-8")

    result = _resolve_template("general", schemas, None)
    assert result is not None
    assert "Basic Underwriting" in result


def test_resolve_template_falls_back_to_path(tmp_path):
    """_resolve_template should fall back to a provided file path."""
    fallback = tmp_path / "my_template.md"
    fallback.write_text("## Fallback Template\n", encoding="utf-8")

    result = _resolve_template("unknown_class", tmp_path / "no_schemas", fallback)
    assert result is not None
    assert "Fallback Template" in result


def test_resolve_template_returns_none_when_unavailable(tmp_path):
    result = _resolve_template(None, tmp_path, None)
    assert result is None


def test_appended_comment_includes_date(tmp_path):
    """The <!-- appended from: ... --> tag should include a date stamp."""
    src_md = tmp_path / 'source.md'
    src_md.write_text(
        "---\nwebsite: https://example.com/\n---\n\nContent here.\n",
        encoding='utf-8',
    )
    dst = tmp_path / 'dst.md'

    appended = append_markdown_to_company(src_md, dst)
    assert appended

    content = dst.read_text(encoding='utf-8')
    # Tag should match "<!-- appended from: source.md on YYYY-MM-DD -->"
    assert re.search(r'<!-- appended from: source\.md on \d{4}-\d{2}-\d{2} -->', content)
