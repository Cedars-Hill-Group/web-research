from src.store import default_metadata


def test_default_metadata_has_website_key():
    meta = default_metadata("https://acme.example/")
    assert "website" in meta
    assert "source_url" not in meta
