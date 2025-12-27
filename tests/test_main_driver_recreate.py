import types
from src import main


class DummyClosedDriver:
    def __init__(self):
        self.session_id = None


class DummyAliveDriver:
    def __init__(self):
        self.session_id = 'alive'
        self.current_url = 'http://example.com'


def test_ensure_driver_alive_replaces_closed(monkeypatch):
    # monkeypatch get_driver to return a sentinel
    monkeypatch.setattr(main, 'get_driver', lambda ua=None: 'NEW_DRIVER')

    closed = DummyClosedDriver()
    new = main._ensure_driver_alive(closed, user_agent='ua')
    assert new == 'NEW_DRIVER'


def test_ensure_driver_alive_keeps_alive():
    alive = DummyAliveDriver()
    res = main._ensure_driver_alive(alive, user_agent='ua')
    assert res is alive
