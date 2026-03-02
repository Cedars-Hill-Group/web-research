from src.store import default_metadata, update_metadata_in_files
import tempfile
from pathlib import Path
import yaml


def test_default_metadata_has_website_key():
    meta = default_metadata("https://acme.example/")
    assert "website" in meta
    assert "source_url" not in meta


def test_default_metadata_single_focus_stored_as_list():
    meta = default_metadata("https://acme.example/", focus="real estate")
    assert isinstance(meta["focus"], list)
    assert meta["focus"] == ["real estate"]


def test_default_metadata_single_firm_type_stored_as_list():
    meta = default_metadata("https://acme.example/", firm_type="Balance Sheet Lender")
    assert isinstance(meta["firm_type"], list)
    assert meta["firm_type"] == ["Balance Sheet Lender"]


def test_default_metadata_single_source_stored_as_list():
    meta = default_metadata("https://acme.example/", source="direct")
    assert isinstance(meta["source"], list)
    assert meta["source"] == ["direct"]


def test_default_metadata_multi_value_focus_stored_as_list():
    meta = default_metadata("https://acme.example/", focus="real estate, debt")
    assert isinstance(meta["focus"], list)
    assert meta["focus"] == ["real estate", "debt"]


def test_default_metadata_none_fields_remain_none():
    meta = default_metadata("https://acme.example/")
    assert meta["focus"] is None
    assert meta["firm_type"] is None
    assert meta["source"] is None


def test_update_metadata_normalizes_single_string_to_list():
    with tempfile.TemporaryDirectory() as tmp:
        md_dir = Path(tmp)
        # Write a file that has focus as a plain string (legacy format)
        fm = yaml.safe_dump({"website": "https://acme.example/", "focus": "real estate", "firm_type": "Bridge Lender"}, sort_keys=False)
        (md_dir / "test.md").write_text(f"---\n{fm}---\n\nBody text")
        updated = update_metadata_in_files(md_dir, {"source": "direct"})
        assert updated == 1
        text = (md_dir / "test.md").read_text()
        parts = text.split("---", 2)
        meta = yaml.safe_load(parts[1])
        assert isinstance(meta["focus"], list)
        assert meta["focus"] == ["real estate"]
        assert isinstance(meta["firm_type"], list)
        assert meta["firm_type"] == ["Bridge Lender"]
        assert isinstance(meta["source"], list)
        assert meta["source"] == ["direct"]
