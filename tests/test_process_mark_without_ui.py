from src.ui_tui import HybridTUI
from pathlib import Path
import shutil

class DummyDriver:
    def get(self, url):
        self._page_source = f'<html><head><title>Test page</title></head><body><p>dummy for {url}</p></body></html>'
    @property
    def page_source(self):
        return getattr(self, '_page_source','')
    def execute_script(self, script):
        return None


def test_commit_scraped_without_ui():
    t = HybridTUI()
    t.company = None
    t.driver = DummyDriver()

    # remove any prior files
    target = Path('data') / 'companies' / 'example-com'
    if target.exists():
        shutil.rmtree(target)

    url = 'https://example.com/test-unit'
    # simulate scraping by adding to collected_pages
    t.collected_pages = [{
        'url': url,
        'html': '<html><body><h1>Test</h1></body></html>',
        'md': '# Test',
        'date': None,
        'notes': '',
        'saved': False,
    }]

    t.action_commit_scraped()

    md = Path('data') / 'companies' / 'example-com' / 'markdown' / 'https-example-com-test-unit.md'
    assert md.exists()
