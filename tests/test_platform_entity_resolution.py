"""Tests for the data-platform integration points in scripts/merge_matching.py
(Phase 3 — entity resolution via CompanyRepository).

All data-platform imports are mocked so these tests run without data-platform
being installed.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts import merge_matching


# ---------------------------------------------------------------------------
# resolve_with_company_repo
# ---------------------------------------------------------------------------

class TestResolveWithCompanyRepo:
    def _make_repo(self, matched_company=None):
        repo = MagicMock()
        repo.resolve.return_value = matched_company
        return repo

    def _make_company(self, id_="acme-capital-llc", name="Acme Capital LLC", website="https://acme.com/"):
        company = MagicMock()
        company.id = id_
        company.name = name
        company.website = website
        return company

    def test_returns_none_when_no_match(self):
        repo = self._make_repo(matched_company=None)
        with patch("scripts.merge_matching.resolve_with_company_repo", wraps=merge_matching.resolve_with_company_repo):
            # Mock the data_platform import inside the function
            mock_company_cls = MagicMock()
            mock_company_cls.return_value = MagicMock()
            with patch.dict("sys.modules", {"data_platform.ontology_adapter": MagicMock(Company=mock_company_cls)}):
                stem, label = merge_matching.resolve_with_company_repo("Acme Capital", None, repo)
        assert stem is None
        assert label == ""

    def test_returns_stem_and_domain_label_on_website_match(self):
        matched = self._make_company(id_="acme-capital-llc", website="https://acme.com/")
        repo = self._make_repo(matched_company=matched)
        mock_company_cls = MagicMock()
        mock_company_cls.return_value = MagicMock()
        with patch.dict("sys.modules", {"data_platform.ontology_adapter": MagicMock(Company=mock_company_cls)}):
            stem, label = merge_matching.resolve_with_company_repo(
                "Acme Capital", "https://acme.com/", repo
            )
        assert stem == "acme-capital-llc"
        assert "domain match" in label

    def test_returns_stem_and_name_label_when_no_website(self):
        matched = self._make_company(id_="acme-capital", website=None)
        repo = self._make_repo(matched_company=matched)
        mock_company_cls = MagicMock()
        mock_company_cls.return_value = MagicMock()
        with patch.dict("sys.modules", {"data_platform.ontology_adapter": MagicMock(Company=mock_company_cls)}):
            stem, label = merge_matching.resolve_with_company_repo(
                "Acme Capital", None, repo
            )
        assert stem == "acme-capital"
        assert "name match" in label

    def test_returns_none_when_import_error(self):
        import sys
        original = sys.modules.get("data_platform.ontology_adapter")
        sys.modules["data_platform.ontology_adapter"] = None  # type: ignore[assignment]
        try:
            stem, label = merge_matching.resolve_with_company_repo("Acme", None, MagicMock())
        finally:
            if original is None:
                del sys.modules["data_platform.ontology_adapter"]
            else:
                sys.modules["data_platform.ontology_adapter"] = original
        assert stem is None
        assert label == ""


# ---------------------------------------------------------------------------
# rank_match_suggestions — repo kwarg integration
# ---------------------------------------------------------------------------

class TestRankMatchSuggestionsWithRepo:
    def test_deterministic_match_takes_priority_over_splink(self, monkeypatch):
        """When repo finds a match that is in candidates, splink is not consulted."""
        def fake_resolve_company_name(_name, _candidates, threshold=0.0):
            # Splink would prefer "Acme Partners" but repo should win
            return [("Acme Partners", 0.95)]

        monkeypatch.setattr(merge_matching, "resolve_company_name", fake_resolve_company_name)

        # Build a mock repo that returns a deterministic match
        matched = MagicMock()
        matched.id = "acme-capital-llc"
        matched.name = "Acme Capital LLC"
        matched.website = "https://acme.com/"
        mock_repo = MagicMock()
        mock_repo.resolve.return_value = matched

        mock_company_cls = MagicMock()
        with patch.dict("sys.modules", {"data_platform.ontology_adapter": MagicMock(Company=mock_company_cls)}):
            suggestions, top_name, label = merge_matching.rank_match_suggestions(
                "Acme Capital",
                ["acme-capital-llc", "Acme Partners"],
                threshold=0.75,
                splink_threshold=0.5,
                repo=mock_repo,
                website="https://acme.com/",
            )

        assert top_name == "acme-capital-llc"
        assert "deterministic" in label

    def test_falls_back_to_splink_when_repo_returns_none(self, monkeypatch):
        """When repo returns None, the existing splink chain is used."""
        def fake_resolve_company_name(_name, _candidates, threshold=0.0):
            if threshold == 0.5:
                return [("Acme Capital LLC", 0.91)]
            return [("Acme Capital LLC", 0.91)]

        monkeypatch.setattr(merge_matching, "resolve_company_name", fake_resolve_company_name)

        mock_repo = MagicMock()
        mock_repo.resolve.return_value = None

        mock_company_cls = MagicMock()
        with patch.dict("sys.modules", {"data_platform.ontology_adapter": MagicMock(Company=mock_company_cls)}):
            suggestions, top_name, label = merge_matching.rank_match_suggestions(
                "Acme Capital",
                ["Acme Capital LLC", "Acme Partners"],
                threshold=0.75,
                splink_threshold=0.5,
                repo=mock_repo,
            )

        assert top_name == "Acme Capital LLC"
        assert "splink match" in label

    def test_no_repo_uses_original_behaviour(self, monkeypatch):
        """Omitting repo= falls back to splink exactly as before (backward compat)."""
        def fake_resolve_company_name(_name, _candidates, threshold=0.0):
            if threshold == 0.5:
                return [("Acme Capital LLC", 0.88)]
            return [("Acme Capital LLC", 0.88)]

        monkeypatch.setattr(merge_matching, "resolve_company_name", fake_resolve_company_name)

        suggestions, top_name, label = merge_matching.rank_match_suggestions(
            "Acme Capital",
            ["Acme Capital LLC", "Acme Partners"],
            threshold=0.75,
            splink_threshold=0.5,
        )

        assert top_name == "Acme Capital LLC"
        assert "splink match" in label
