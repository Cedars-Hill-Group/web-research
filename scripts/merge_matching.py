from __future__ import annotations

import difflib

from src.entity_resolution import resolve_company_name


MAX_PROMPT_CANDIDATES = 10


def rank_match_suggestions(
    name: str,
    candidates: list[str],
    *,
    threshold: float,
    splink_threshold: float,
) -> tuple[list[str], str | None, str]:
    """Return ranked suggestions plus optional top suggestion and label."""
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
