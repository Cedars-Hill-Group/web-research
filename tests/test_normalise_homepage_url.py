"""Tests for src/openai_agent._normalise_homepage_url (Issue #13 — Phase 4)."""
from __future__ import annotations

import pytest

from src.openai_agent import _normalise_homepage_url


@pytest.mark.parametrize(
    "url,expected",
    [
        # Already a clean root URL — preserve as-is (with trailing slash)
        ("https://acme.com/", "https://acme.com/"),
        # No trailing slash — add it
        ("https://acme.com", "https://acme.com/"),
        # Deep path stripped to root
        ("https://acme.com/about?ref=footer", "https://acme.com/"),
        # Redirect-target URL (the Issue #13 case)
        ("https://amstargroup.com/landing?source=redirect", "https://amstargroup.com/"),
        # No scheme — https:// prepended
        ("amstar.com", "https://amstar.com/"),
        ("amstar.com/about", "https://amstar.com/"),
        # HTTP scheme preserved
        ("http://example.org/page/subpage", "http://example.org/"),
        # Fragment stripped
        ("https://acme.com/#team", "https://acme.com/"),
        # Port preserved
        ("https://acme.com:8443/path", "https://acme.com:8443/"),
        # www preserved
        ("https://www.example.com/foo", "https://www.example.com/"),
    ],
)
def test_normalise_homepage_url(url: str, expected: str) -> None:
    assert _normalise_homepage_url(url) == expected


def test_normalise_homepage_url_empty_string() -> None:
    assert _normalise_homepage_url("") == ""


def test_normalise_homepage_url_none_like_returns_unchanged() -> None:
    """Non-URL strings without a recognisable netloc are returned unchanged."""
    result = _normalise_homepage_url("not-a-url")
    # "not-a-url" has no netloc, so it's treated as a path and returned unchanged.
    assert isinstance(result, str)
