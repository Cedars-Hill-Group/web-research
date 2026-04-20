from __future__ import annotations

import difflib

from src.entity_resolution import resolve_company_name


MAX_PROMPT_CANDIDATES = 10


def build_company_repo_from_db(db_dir):
    """Load existing KB company files into a :class:`CompanyRepository`.

    Uses :class:`~data_platform.knowledge_base.reader.KnowledgeBaseReader` to
    scan *db_dir* and populates a fresh
    :class:`~data_platform.repositories.companies.CompanyRepository` with one
    :class:`~data_platform.ontology_adapter.Company` entry per markdown file,
    indexed by both normalised name and website domain.

    Returns ``None`` when ``data-platform`` is not installed.
    """
    try:
        from data_platform.knowledge_base.reader import KnowledgeBaseReader
        from data_platform.repositories.companies import CompanyRepository
        from data_platform.ontology_adapter import Company
    except ImportError:
        return None

    reader = KnowledgeBaseReader(
        db_dir.parent,
        folder_map={"company": db_dir.name},
    )
    repo = CompanyRepository()
    for doc in reader.read_all(object_type="company"):
        name = str(doc.metadata.get("name") or doc.path.stem)
        website = str(doc.metadata.get("website") or "")
        company = Company(
            id=doc.path.stem,
            name=name,
            website=website or None,
        )
        repo.save(company)
    return repo


def resolve_with_company_repo(
    name: str,
    website: str | None,
    repo,
) -> tuple[str | None, str]:
    """Try deterministic entity resolution via :class:`CompanyRepository`.

    Applies the tiered strategy built into
    :meth:`~data_platform.repositories.companies.CompanyRepository.resolve`:
    1. Website-domain match (exact, normalised).
    2. Normalised-name match (legal suffixes and punctuation stripped).

    Parameters
    ----------
    name:
        Candidate company name.
    website:
        Candidate website URL (may be ``None``).
    repo:
        A populated :class:`~data_platform.repositories.companies.CompanyRepository`.

    Returns
    -------
    tuple[str | None, str]
        ``(matched_id, match_label)`` if a match was found, or ``(None, "")``
        when no deterministic match exists.
    """
    try:
        from data_platform.ontology_adapter import Company
    except ImportError:
        return None, ""

    candidate = Company(id="__probe__", name=name, website=website or None)
    matched = repo.resolve(candidate)
    if matched:
        if website and matched.website:
            label = f"domain match ({matched.website})"
        else:
            label = f"name match ({matched.name!r})"
        return matched.id, label
    return None, ""


def rank_match_suggestions(
    name: str,
    candidates: list[str],
    *,
    threshold: float,
    splink_threshold: float,
    repo=None,
    website: str | None = None,
) -> tuple[list[str], str | None, str]:
    """Return ranked suggestions plus optional top suggestion and label.

    When *repo* is provided, deterministic entity resolution via
    :class:`~data_platform.repositories.companies.CompanyRepository` is tried
    first (Issue #17).  If it finds a match that is present in *candidates*,
    that match is returned immediately without invoking splink.  Otherwise the
    existing splink → difflib fallback chain is used.
    """
    # 1. Deterministic resolution (data-platform CompanyRepository).
    if repo is not None:
        matched_stem, match_label = resolve_with_company_repo(name, website, repo)
        if matched_stem and matched_stem in candidates:
            return candidates, matched_stem, f"deterministic {match_label}"

    # 2. Probabilistic resolution (splink with difflib fallback).
    splink_matches = resolve_company_name(name, candidates, threshold=splink_threshold)
    splink_all = resolve_company_name(name, candidates, threshold=0.0)
    matched_names = {match_name for match_name, _ in splink_matches}
    close_splink = [candidate_name for candidate_name, _ in splink_all if candidate_name not in matched_names]

    difflib_best = difflib.get_close_matches(name, candidates, n=1, cutoff=threshold)
    difflib_close = difflib.get_close_matches(name, candidates, n=5, cutoff=threshold / 2)

    seen: set[str] = set()
    suggestions: list[str] = []
    for candidate_name in [match_name for match_name, _ in splink_matches] + close_splink + difflib_close:
        if candidate_name in seen:
            continue
        seen.add(candidate_name)
        suggestions.append(candidate_name)

    if splink_matches:
        top_name, top_probability = splink_matches[0]
        label = f"splink match (probability={top_probability:.2f})"
        return suggestions, top_name, label

    if difflib_best:
        return suggestions, difflib_best[0], "difflib match"

    return suggestions, None, ""


def prompt_user_for_match(
    name: str,
    suggestions: list[str],
    top_name: str | None,
    top_label: str,
) -> tuple[str | None, str | None]:
    """Prompt user to confirm top match or choose/create/skip."""
    if top_name:
        confirm = input(
            f"Found {top_label} in DB: '{top_name}' for '{name}'. Use it? (y/n): "
        ).strip().lower()
        if confirm == "y":
            return top_name, None

    selectable_suggestions = suggestions[:MAX_PROMPT_CANDIDATES]

    if len(suggestions) > MAX_PROMPT_CANDIDATES:
        print(
            f"No suitable automatic match. Candidates (showing top {MAX_PROMPT_CANDIDATES} of {len(suggestions)}):"
        )
    else:
        print("No suitable automatic match. Candidates:")

    for index, candidate_name in enumerate(selectable_suggestions, start=1):
        print(f"  {index}. {candidate_name}")

    response = input("Enter number to choose existing, 'n' for new, or 's' to skip: ").strip().lower()
    if response == "s":
        return None, None

    if response == "n":
        custom_name = input(f"Enter company name for database (or press Enter to use '{name}'): ").strip()
        return None, custom_name or name

    try:
        selected_index = int(response) - 1
        if 0 <= selected_index < len(selectable_suggestions):
            return selectable_suggestions[selected_index], None
    except ValueError:
        pass

    return None, None

