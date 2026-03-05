"""Entity resolution engine for matching company names using splink.

Uses probabilistic record linkage via the splink library to identify whether
a candidate company name refers to an existing company in the database.

Key functions:
    resolve_company_name  – score a candidate against a list of known names
    find_best_match       – return the single best match above a threshold
"""

from __future__ import annotations

import difflib
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_LEGAL_SUFFIXES = {
    "llc",
    "l.l.c",
    "inc",
    "inc.",
    "corp",
    "corp.",
    "co",
    "co.",
    "company",
    "ltd",
    "ltd.",
    "lp",
    "llp",
    "pllc",
    "plc",
}


def _normalise_company_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", value.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _strip_legal_suffixes(value: str) -> str:
    tokens = value.split()
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens).strip()


def _fallback_similarity(candidate: str, target: str) -> float:
    c_norm = _normalise_company_name(candidate)
    t_norm = _normalise_company_name(target)

    if not c_norm or not t_norm:
        return 0.0
    if c_norm == t_norm:
        return 1.0

    c_base = _strip_legal_suffixes(c_norm)
    t_base = _strip_legal_suffixes(t_norm)
    if c_base and t_base and c_base == t_base:
        return 0.97

    seq_score = difflib.SequenceMatcher(a=c_norm, b=t_norm).ratio()
    base_score = difflib.SequenceMatcher(a=c_base or c_norm, b=t_base or t_norm).ratio()

    c_tokens = set((c_base or c_norm).split())
    t_tokens = set((t_base or t_norm).split())
    token_score = (len(c_tokens & t_tokens) / len(c_tokens | t_tokens)) if (c_tokens and t_tokens) else 0.0

    # Weighted blend tuned to keep exact/base matches high while penalising unrelated names.
    return min(1.0, (0.5 * base_score) + (0.35 * seq_score) + (0.15 * token_score))


def _fallback_resolve_company_name(
    candidate: str,
    existing: list[str],
    threshold: float,
) -> list[tuple[str, float]]:
    results: list[tuple[str, float]] = []
    for name in existing:
        probability = _fallback_similarity(candidate, name)
        if probability >= threshold:
            results.append((name, probability))
    results.sort(key=lambda x: x[1], reverse=True)
    return results

# ---------------------------------------------------------------------------
# Splink settings
# ---------------------------------------------------------------------------
# Pre-specified m/u probabilities calibrated for company-name matching.
# m  = P(observation | same entity)
# u  = P(observation | different entity)
#
# Comparison levels (Jaro-Winkler on the *company_name* field):
#   Exact match         – m=0.60, u=0.001  → P≈0.97 at prior=0.05
#   JW >= 0.88          – m=0.25, u=0.010  → P≈0.57 at prior=0.05
#   JW >= 0.70          – m=0.15, u=0.050  → P≈0.14 at prior=0.05
#   All other           – m=0.001,u=0.939  → P≈0.00 at prior=0.05
# ---------------------------------------------------------------------------

_SPLINK_SETTINGS: dict = {
    "link_type": "link_only",
    # 5 % of random pairs from different sources are assumed to be the same
    # entity.  Tune this upward if the DB grows very large.
    "probability_two_random_records_match": 0.05,
    "comparisons": [
        {
            "output_column_name": "company_name",
            "comparison_levels": [
                {
                    "sql_condition": (
                        "company_name_l IS NULL AND company_name_r IS NULL"
                    ),
                    "label_for_charts": "Null",
                    "is_null_level": True,
                },
                {
                    "sql_condition": "company_name_l = company_name_r",
                    "label_for_charts": "Exact match",
                    "m_probability": 0.60,
                    "u_probability": 0.001,
                },
                {
                    "sql_condition": (
                        "jaro_winkler_similarity(company_name_l, company_name_r)"
                        " >= 0.88"
                    ),
                    "label_for_charts": "Jaro-Winkler >= 0.88",
                    "m_probability": 0.25,
                    "u_probability": 0.010,
                },
                {
                    "sql_condition": (
                        "jaro_winkler_similarity(company_name_l, company_name_r)"
                        " >= 0.70"
                    ),
                    "label_for_charts": "Jaro-Winkler >= 0.70",
                    "m_probability": 0.15,
                    "u_probability": 0.050,
                },
                {
                    "sql_condition": "1=1",
                    "label_for_charts": "All other",
                    "m_probability": 0.001,
                    "u_probability": 0.939,
                },
            ],
        }
    ],
    # Empty list → compare the candidate against ALL existing records.
    # This is intentional: the DB is expected to be small enough that an
    # exhaustive comparison is cheap.
    "blocking_rules_to_generate_predictions": [],
}


def resolve_company_name(
    candidate: str,
    existing: list[str],
    threshold: float = 0.0,
) -> list[tuple[str, float]]:
    """Score *candidate* against every name in *existing* using splink.

    Args:
        candidate: The company name to resolve.
        existing:  List of known company names from the database.
        threshold: Only return matches whose ``match_probability`` is at
                   least this value.  Defaults to 0.0 (return all).

    Returns:
        A list of ``(name, probability)`` tuples sorted by probability
        descending.  Returns an empty list when *existing* is empty or when
        splink cannot be imported.
    """
    if not existing:
        return []

    try:
        import pandas as pd
        from splink import DuckDBAPI, Linker
    except ImportError:
        logger.warning(
            "splink or pandas is not installed; using deterministic fallback matching."
        )
        return _fallback_resolve_company_name(candidate, existing, threshold)

    import warnings

    df_candidate = pd.DataFrame(
        [{"unique_id": "__candidate__", "company_name": candidate}]
    )
    df_existing = pd.DataFrame(
        [
            {"unique_id": f"db_{i}", "company_name": name}
            for i, name in enumerate(existing)
        ]
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            linker = Linker(
                [df_candidate, df_existing],
                _SPLINK_SETTINGS,
                db_api=DuckDBAPI(),
            )
            preds = linker.inference.predict(
                threshold_match_probability=threshold
            )
            df_preds = preds.as_pandas_dataframe()
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            logger.warning("splink prediction failed: %s", exc)
            return _fallback_resolve_company_name(candidate, existing, threshold)

    if df_preds.empty:
        return []

    # Normalise orientation: candidate is always on the left (source_dataset_l)
    # but splink may flip pairs.  Filter rows involving our candidate.
    mask_l = df_preds["unique_id_l"] == "__candidate__"
    mask_r = df_preds["unique_id_r"] == "__candidate__"

    results: list[tuple[str, float]] = []

    for _, row in df_preds[mask_l].iterrows():
        results.append(
            (str(row["company_name_r"]), float(row["match_probability"]))
        )
    for _, row in df_preds[mask_r].iterrows():
        results.append(
            (str(row["company_name_l"]), float(row["match_probability"]))
        )

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def find_best_match(
    candidate: str,
    existing: list[str],
    threshold: float = 0.5,
) -> tuple[str | None, float]:
    """Return the best matching name from *existing* above *threshold*.

    Args:
        candidate: The company name to resolve.
        existing:  List of known company names from the database.
        threshold: Minimum ``match_probability`` required to return a match.
                   Defaults to 0.5 (>50 % likely same entity).

    Returns:
        ``(best_match_name, probability)`` if a match is found, or
        ``(None, 0.0)`` if no match exceeds *threshold*.
    """
    matches = resolve_company_name(candidate, existing, threshold=threshold)
    if matches:
        return matches[0]
    return (None, 0.0)
