"""Tests for src/entity_resolution.py (splink-based company name matching)."""
from __future__ import annotations

from src.entity_resolution import find_best_match, resolve_company_name


# ---------------------------------------------------------------------------
# resolve_company_name
# ---------------------------------------------------------------------------

class TestResolveCompanyName:
    def test_exact_match_returns_high_probability(self):
        existing = ["Acme Capital LLC", "BridgePoint Lending"]
        results = resolve_company_name("Acme Capital LLC", existing)
        assert results, "Expected at least one result"
        best_name, best_prob = results[0]
        assert best_name == "Acme Capital LLC"
        assert best_prob > 0.9

    def test_similar_name_matches_above_threshold(self):
        """A name that is slightly different (JW >= 0.88) should match."""
        existing = ["Acme Capital LLC", "BridgePoint Lending", "Cornerstone Finance"]
        results = resolve_company_name("Acme Capital", existing)
        names = [n for n, _ in results]
        assert "Acme Capital LLC" in names

    def test_spacing_variant_matches(self):
        """'Bridge Point Lending' should match 'BridgePoint Lending'."""
        existing = ["BridgePoint Lending", "Cornerstone Finance"]
        results = resolve_company_name("Bridge Point Lending", existing, threshold=0.5)
        assert results, "Expected a match for the spacing variant"
        assert results[0][0] == "BridgePoint Lending"

    def test_unrelated_name_not_returned_above_threshold(self):
        """A completely different company should produce no matches above 0.5."""
        existing = ["Acme Capital LLC", "BridgePoint Lending"]
        results = resolve_company_name("Completely New Company", existing, threshold=0.5)
        assert results == [], f"Expected no match, got {results}"

    def test_empty_existing_returns_empty_list(self):
        results = resolve_company_name("Acme Capital", [])
        assert results == []

    def test_results_sorted_by_probability_descending(self):
        existing = [
            "Acme Capital LLC",
            "Acme Capital Partners",
            "BridgePoint Lending",
        ]
        results = resolve_company_name("Acme Capital", existing, threshold=0.0)
        probs = [p for _, p in results]
        assert probs == sorted(probs, reverse=True), "Results should be sorted descending"

    def test_threshold_filters_results(self):
        existing = ["Acme Capital LLC", "BridgePoint Lending", "Delta Realty"]
        all_results = resolve_company_name("Acme Capital", existing, threshold=0.0)
        filtered = resolve_company_name("Acme Capital", existing, threshold=0.5)
        assert len(filtered) <= len(all_results)
        assert all(p >= 0.5 for _, p in filtered)


# ---------------------------------------------------------------------------
# find_best_match
# ---------------------------------------------------------------------------

class TestFindBestMatch:
    def test_finds_close_name(self):
        existing = ["Acme Capital LLC", "BridgePoint Lending"]
        name, prob = find_best_match("Acme Capital", existing)
        assert name == "Acme Capital LLC"
        assert prob >= 0.5

    def test_returns_none_when_no_match(self):
        existing = ["Acme Capital LLC", "BridgePoint Lending"]
        name, prob = find_best_match("Completely Different Corp", existing)
        assert name is None
        assert prob == 0.0

    def test_returns_none_for_empty_existing(self):
        name, prob = find_best_match("Acme Capital", [])
        assert name is None
        assert prob == 0.0

    def test_exact_match_returns_full_name(self):
        existing = ["BridgePoint Lending", "Acme Capital LLC"]
        name, prob = find_best_match("Acme Capital LLC", existing)
        assert name == "Acme Capital LLC"
        assert prob > 0.9

    def test_custom_threshold_respected(self):
        """With a very high threshold, even a close match should be rejected."""
        existing = ["Acme Capital LLC"]
        # "Acme Capital" vs "Acme Capital LLC" → JW-based probability ~0.57
        # A threshold of 0.99 should reject it.
        name, prob = find_best_match("Acme Capital", existing, threshold=0.99)
        assert name is None
        assert prob == 0.0
