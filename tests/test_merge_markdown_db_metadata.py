from pathlib import Path
from scripts.merge_markdown_db import append_markdown_to_company
import yaml

def _read_front(path: Path):
    t = path.read_text(encoding='utf-8')
    parts = t.split('---', 2)
    if len(parts) >= 3:
        return yaml.safe_load(parts[1])
    return {}


def test_merge_updates_existing_metadata(tmp_path):
    src_dir = tmp_path / 'src'
    db_dir = tmp_path / 'db'
    src_dir.mkdir()
    db_dir.mkdir()

    # create src file with metadata
    company = 'Acme Inc'
    src_md = src_dir / 'a.md'
    src_md.write_text('''---\ncompany: Acme Inc\ndate: '2025-12-01T00:00:00Z'\nfocus: team\n---\n\n# New\nNew content\n''', encoding='utf-8')

    dst = db_dir / 'acme-inc.md'
    # create existing dst with metadata
    dst.write_text('''---\ncompany: Acme Inc\ncreated_at: 2025-01-01T00:00:00Z\n---\n\n# Existing\nExisting content\n''', encoding='utf-8')

    appended = append_markdown_to_company(src_md, dst)
    assert appended
    meta = _read_front(dst)
    assert meta.get('company') == 'Acme Inc'
    assert meta.get('focus') == 'team'
    assert meta.get('date') == '2025-12-01T00:00:00Z'


def test_merge_inserts_metadata_when_missing(tmp_path):
    src_dir = tmp_path / 'src'
    db_dir = tmp_path / 'db'
    src_dir.mkdir()
    db_dir.mkdir()

    src_md = src_dir / 'b.md'
    src_md.write_text('''---\ncompany: Beta\nfocus: press\n---\n\n# New\nNew content\n''', encoding='utf-8')

    dst = db_dir / 'beta.md'
    dst.write_text('# Existing\nExisting\n', encoding='utf-8')

    appended = append_markdown_to_company(src_md, dst)
    assert appended
    meta = _read_front(dst)
    assert meta.get('company') == 'Beta'
    # merged focus present
    assert meta.get('focus') == 'press'