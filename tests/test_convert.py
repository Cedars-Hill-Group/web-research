from src.convert import clean_markdown


def test_clean_markdown_removes_boilerplate():
    md = """
# Title

Some content

Back to top

© 2025 Company


"""
    out = clean_markdown(md)
    assert "Back to top" not in out
    assert "© 2025 Company" not in out
    assert out.count('\n\n') <= 1
