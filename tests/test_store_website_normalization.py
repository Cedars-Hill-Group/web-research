from src.store import default_metadata


def test_website_normalization_strips_path_and_query():
    meta = default_metadata("https://example.com/about?x=1")
    assert meta["website"] == "https://example.com/"


def test_website_normalization_handles_no_scheme():
    meta = default_metadata("example.com/about")
    # should add http:// and normalize to root
    assert meta["website"] in ("http://example.com/", "https://example.com/")


def test_website_fallback_on_invalid_url():
    meta = default_metadata("not a url")
    assert "website" in meta
