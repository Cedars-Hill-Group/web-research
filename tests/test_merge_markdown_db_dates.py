from pathlib import Path
from scripts.merge_markdown_db import append_markdown_to_company
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
