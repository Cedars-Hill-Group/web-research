from src.ui_tui import HybridTUI
from src.store import company_dirs
import yaml
from pathlib import Path
import shutil

class DummyDriver:
    def __init__(self, html):
        self.page_source = html
        self.last_get = None
    def get(self, url):
        self.last_get = url
    def execute_script(self, script):
        pass


def _read_front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = parts[1]
    return yaml.safe_load(fm)


def test_process_mark_saves_focus_and_location(tmp_path, monkeypatch):
    # point company_dirs to a temp base so we don't pollute repo
    orig = company_dirs
    def tmp_company_dirs(base, company):
        return orig(str(tmp_path / "data"), company)
    # ui_tui imports company_dirs at module import time; patch the reference there
    monkeypatch.setattr("src.ui_tui.company_dirs", tmp_company_dirs)

    html = "<html><body><div class='content'>About us</div><div>New York, NY</div></body></html>"
    driver = DummyDriver(html)

    tui = HybridTUI()
    tui.driver = driver
    tui.company = "TestCo"
    tui.company_focus = "strategy"

    # perform a scrape then commit
    # ensure driver can return page_source and action_scrape_here records it
    tui.action_scrape_here()
    tui.action_commit_scraped()

    # find created markdown
    dirs = tmp_company_dirs("ignored", "TestCo")
    md_files = list((dirs["md"]).glob("*.md"))
    assert len(md_files) == 1
    fm = _read_front_matter(md_files[0])
    assert fm.get("focus") == "strategy"
    # city/state removed from metadata — ensure they are not present
    assert "city" not in fm and "state" not in fm


def test_action_save_uses_company_focus_and_writes_meta(tmp_path, monkeypatch):
    orig = company_dirs
    def tmp_company_dirs(base, company):
        return orig(str(tmp_path / "data"), company)
    # ui_tui imports company_dirs at module import time; patch the reference there
    monkeypatch.setattr("src.ui_tui.company_dirs", tmp_company_dirs)

    html = "<html><body><h1>Contact</h1><div class='address'>Los Angeles, CA</div></body></html>"
    driver = DummyDriver(html)

    tui = HybridTUI()
    tui.driver = driver
    tui.company = "SaveCo"
    tui.company_focus = "team"

    # scrape current page and save
    tui.action_scrape_here()
    tui.action_save()

    dirs = tmp_company_dirs("ignored", "SaveCo")
    md_files = list((dirs["md"]).glob("*.md"))
    assert len(md_files) == 1
    fm = _read_front_matter(md_files[0])
    assert fm.get("focus") == "team"
    # city/state removed from metadata — ensure they are not present
    assert "city" not in fm and "state" not in fm