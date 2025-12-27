from src.ui_tui import HybridTUI

class DummyDriver:
    def __init__(self):
        self.quit_called = False
        self.close_called = False
    def quit(self):
        self.quit_called = True
    def close(self):
        self.close_called = True


def test_action_quit_closes_driver():
    t = HybridTUI()
    d = DummyDriver()
    t.driver = d
    # call action_quit which should close the driver
    t.action_quit()
    assert d.quit_called or d.close_called


def test_action_finish_closes_driver_when_not_shared():
    t = HybridTUI()
    d = DummyDriver()
    t.driver = d
    t._shared_driver = False
    t.action_finish()
    assert d.quit_called or d.close_called


def test_action_finish_does_not_close_shared_driver():
    t = HybridTUI()
    d = DummyDriver()
    t.driver = d
    t._shared_driver = True
    t.action_finish()
    assert not d.quit_called and not d.close_called
