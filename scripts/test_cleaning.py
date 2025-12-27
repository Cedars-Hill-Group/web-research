import sys, os
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.convert import html_to_clean_markdown

p = Path("data/companies/tyko/raw_html/https-tykocapital-com.html")
if not p.exists():
    import pytest
    pytest.skip("Sample HTML not present; skipping script test", allow_module_level=True)
html = p.read_text(encoding="utf-8")
md = html_to_clean_markdown(html)
print(md[:1000])

out = Path("tmp_cleaned.md")
out.write_text(md, encoding="utf-8")
print(f"Wrote cleaned markdown to {out}")
