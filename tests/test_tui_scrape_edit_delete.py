from src.ui_tui import HybridTUI
import types


def test_edit_scraped_item_updates_notes_and_focus():
    t = HybridTUI()
    t.collected_pages = [
        {'url': 'http://example.com/a', 'html': '<html></html>', 'md': '# A', 'notes': '', 'focus': ''}
    ]

    t.edit_scraped_item(0, notes='these are notes', focus='team')
    p = t.collected_pages[0]
    assert p['notes'] == 'these are notes'
    assert p['focus'] == 'team'


def test_delete_scraped_item_removes_item():
    t = HybridTUI()
    p = {'url': 'http://example.com/a', 'html': '', 'md': '', 'notes': ''}
    t.collected_pages = [p]
    # scraped_list with children containing an object that has .data == page
    t.scraped_list = types.SimpleNamespace(children=[types.SimpleNamespace(data=p)])

    t.delete_scraped_item(0)
    assert not t.collected_pages
    assert len(list(t.scraped_list.children)) == 0