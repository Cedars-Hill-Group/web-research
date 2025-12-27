import src.main as main_mod
from src.ui_tui import HybridTUI

class DummyPreview:
    def __init__(self):
        self.messages = []
    def write(self, msg):
        self.messages.append(msg)


def test_global_tui_cleared_on_quit():
    tui = HybridTUI()
    main_mod.global_tui = tui

    tui.action_quit()

    assert main_mod.global_tui is None


