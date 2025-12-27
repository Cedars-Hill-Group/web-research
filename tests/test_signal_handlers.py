import src.main as main_mod

class DummyDriver:
    def __init__(self):
        self.quit_called = False
    def quit(self):
        self.quit_called = True


def test_make_handler_calls_close_driver():
    d = DummyDriver()
    handler = main_mod._make_handler(d)
    try:
        handler(None, None)
    except SystemExit:
        # handler calls sys.exit(0) after closing the driver; that's fine
        pass
    assert d.quit_called
