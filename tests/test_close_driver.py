from src.browser import close_driver

class Dummy:
    def __init__(self):
        self.quit_called = False
        self.close_called = False
    def quit(self):
        self.quit_called = True
    def close(self):
        self.close_called = True


def test_close_driver_prefers_quit():
    d = Dummy()
    close_driver(d)
    assert d.quit_called
    assert not d.close_called


def test_close_driver_handles_none():
    close_driver(None)  # should not raise
