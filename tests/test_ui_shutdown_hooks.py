from src.ui_tui import HybridTUI

class DummyDriver:
    def __init__(self):
        self.quit_called = False
    def quit(self):
        self.quit_called = True


def test_on_unmount_closes_driver():
    t = HybridTUI()
    d = DummyDriver()
    t.driver = d
    t.on_unmount()
    assert d.quit_called
    assert t.driver is None


def test_on_stop_closes_driver():
    t = HybridTUI()
    d = DummyDriver()
    t.driver = d
    t.on_stop()
    assert d.quit_called
    assert t.driver is None


def test_del_closes_driver():
    t = HybridTUI()
    d = DummyDriver()
    t.driver = d
    # trigger __del__ explicitly
    t.__del__()
    assert d.quit_called
    # __del__ may not set t.driver to None but should at least have called quit

