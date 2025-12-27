from src.ui_tui import HybridTUI
from pathlib import Path
import types


class DummyDriver:
    def __init__(self, url, html):
        self.current_url = url
        self.page_source = html


def test_action_scrape_here_records_page(monkeypatch):
    t = HybridTUI()
    t.driver = DummyDriver('http://example.com/page', '<html><body><h1>Hi</h1><p>hello</p></body></html>')
    t.company = 'TestCo'

    # Before scraping nothing is present
    assert not t.collected_pages

    # perform scrape
    t.action_scrape_here()

    assert len(t.collected_pages) == 1
    p = t.collected_pages[0]
    assert 'http://example.com/page' == p['url']
    assert 'hello' in p['md']

    # UI list may not be mounted in unit tests; if present it should have an entry
    if getattr(t, 'scraped_list', None) is not None:
        assert len(list(t.scraped_list.children)) == 1


def test_action_commit_scraped_writes_files(tmp_path, monkeypatch):
    # monkeypatch company_dirs to write into tmp_path
    import src.ui_tui as tui_mod
    from src import store

    def _company_dirs(base_dir, company):
        # create under tmp_path/companies
        base = tmp_path / 'companies'
        return store.company_dirs(str(base), company)

    monkeypatch.setattr(tui_mod, 'company_dirs', _company_dirs)

    t = HybridTUI()
    t.company = 'TestCo'
    t.company_focus = 'research'
    t.collected_pages = [
        {
            'url': 'http://example.com/page1',
            'html': '<html><body><h1>P1</h1><p>content1</p></body></html>',
            'md': '# P1\n\ncontent1',
            'date': '2025-01-01T00:00:00Z',
            'notes': '',
            'saved': False,
        },
        {
            'url': 'http://example.com/page2',
            'html': '<html><body><h1>P2</h1><p>content2</p></body></html>',
            'md': '# P2\n\ncontent2',
            'date': '2025-01-02T00:00:00Z',
            'notes': '',
            'saved': False,
        },
    ]

    # ensure scraped_list exists for UI additions
    t.scraped_list = types.SimpleNamespace(children=[])

    # Commit
    t.action_commit_scraped()

    # check files exist in tmp_path
    base = tmp_path / 'companies' / 'testco'
    md_dir = base / 'markdown'
    html_dir = base / 'raw_html'

    md_files = list(md_dir.glob('*.md'))
    html_files = list(html_dir.glob('*.html'))

    assert len(md_files) >= 3  # 2 pages + combined session
    assert len(html_files) >= 2

    # verify saved flags set
    assert all(p.get('saved') for p in t.collected_pages)

    # combined session file exists
    session_files = [p for p in md_files if p.stem.startswith('session-')]
    assert session_files, 'session file should be created'