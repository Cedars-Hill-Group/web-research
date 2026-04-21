"""Unit tests for _check_applies_when — the declarative catalog condition evaluator."""
from __future__ import annotations

import pytest

from src.main import _check_applies_when


# ---------------------------------------------------------------------------
# No condition (always applies)
# ---------------------------------------------------------------------------


def test_no_condition_returns_true():
    assert _check_applies_when(None, {}) is True


def test_empty_condition_dict_returns_true():
    assert _check_applies_when({}, {"focus": ["commercial_real_estate"]}) is True


# ---------------------------------------------------------------------------
# contains_any operator
# ---------------------------------------------------------------------------


def test_contains_any_passes_when_list_field_contains_value():
    applies_when = {"focus": {"contains_any": ["commercial_real_estate"]}}
    meta = {"focus": ["commercial_real_estate", "multifamily"]}
    assert _check_applies_when(applies_when, meta) is True


def test_contains_any_passes_when_string_field_matches():
    """A scalar string metadata value is treated as a single-element list."""
    applies_when = {"focus": {"contains_any": ["commercial_real_estate"]}}
    meta = {"focus": "commercial_real_estate"}
    assert _check_applies_when(applies_when, meta) is True


def test_contains_any_fails_when_value_absent():
    applies_when = {"focus": {"contains_any": ["commercial_real_estate"]}}
    meta = {"focus": ["technology", "healthcare"]}
    assert _check_applies_when(applies_when, meta) is False


def test_contains_any_fails_when_field_missing_from_metadata():
    applies_when = {"focus": {"contains_any": ["commercial_real_estate"]}}
    assert _check_applies_when(applies_when, {}) is False


def test_contains_any_passes_for_one_of_multiple_allowed_values():
    applies_when = {"focus": {"contains_any": ["commercial_real_estate", "multifamily"]}}
    meta = {"focus": ["multifamily"]}
    assert _check_applies_when(applies_when, meta) is True


# ---------------------------------------------------------------------------
# Multiple conditions (all must pass)
# ---------------------------------------------------------------------------


def test_all_conditions_must_be_satisfied():
    applies_when = {
        "focus": {"contains_any": ["commercial_real_estate"]},
        "firm_type": {"contains_any": ["real_estate"]},
    }
    meta = {"focus": ["commercial_real_estate"], "firm_type": "real_estate"}
    assert _check_applies_when(applies_when, meta) is True


def test_fails_when_only_one_of_two_conditions_met():
    applies_when = {
        "focus": {"contains_any": ["commercial_real_estate"]},
        "firm_type": {"contains_any": ["real_estate"]},
    }
    meta = {"focus": ["commercial_real_estate"], "firm_type": "private_equity"}
    assert _check_applies_when(applies_when, meta) is False


# ---------------------------------------------------------------------------
# Unknown operator — gracefully ignored (field passes)
# ---------------------------------------------------------------------------


def test_unknown_operator_does_not_cause_error():
    """Unrecognised operators are ignored; the condition is treated as passing."""
    applies_when = {"focus": {"unknown_op": ["commercial_real_estate"]}}
    meta = {"focus": ["technology"]}
    # No contains_any key → nothing to fail → returns True
    assert _check_applies_when(applies_when, meta) is True
