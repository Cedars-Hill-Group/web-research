from src.convert import html_to_clean_markdown


def test_retain_team_and_press_sections():
    html = '''
<html><body>
  <header>Site header</header>
  <nav>Site nav</nav>
  <main>
    <div id="team"><h2>Team</h2><p>Member A</p></div>
    <div id="press"><h2>Press</h2><p>Article 1</p></div>
  </main>
  <footer>Site footer</footer>
</body></html>
'''
    md = html_to_clean_markdown(html)
    assert "Team" in md
    assert "Member A" in md
    assert "Press" in md
    assert "Article 1" in md


def test_retain_from_real_sample_if_available():
    import pathlib
    p = pathlib.Path("data/companies/tyko/raw_html/https-tykocapital-com.html")
    if not p.exists():
        return
    html = p.read_text(encoding="utf-8")
    md = html_to_clean_markdown(html)
    assert "Team" in md
    assert "Press" in md
