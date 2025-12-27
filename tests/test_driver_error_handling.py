from src.scrape import fetch_html
from src.ui_tui import HybridTUI
from src.browser import close_driver

class FailingDriver:
    def __init__(self):
        self.quit_called = False
    def get(self, url):
        raise OSError("connect failed")
    def execute_script(self, script):
        pass
    def quit(self):
        self.quit_called = True


def test_fetch_html_raises_runtime_error_on_driver_failure():
    d = FailingDriver()
    try:
        fetch_html(d, "http://example.com")
        assert False, "fetch_html should raise RuntimeError when driver fails"
    except RuntimeError as e:
        assert "Driver failed to fetch" in str(e)


def test_on_list_view_select_handles_driver_error(monkeypatch):
    # Ensure close_driver is invoked and self.driver is nulled when driver.get fails
    d = FailingDriver()
    tui = HybridTUI()
    tui.driver = d

    class Item:
        pass
    class ListView:
        pass
    class Event:
        pass

    item = Item()
    item.data = {"title": "FailCo", "link": "http://example.com"}
    lv = ListView()
    lv.id = "sites"
    ev = Event()
    ev.list_view = lv
    ev.item = item

    tui.on_list_view_selected(ev)

    # driver should be set to None after handling the failure
    assert tui.driver is None
