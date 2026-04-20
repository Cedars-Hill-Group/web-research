import builtins

from src import main


def test_prompt_missing_ai_metadata_prompts_for_source_prop_type_and_loan_type(monkeypatch):
    """focus and firm_type are no longer prompted — only source, prop_type, and loan_type."""
    answers = iter(["referral", "Multifamily", "Bridge"])

    monkeypatch.setattr(builtins, "input", lambda _: next(answers))

    captured = {
        "source": None,
        "prop_type": None,
        "loan_type": None,
    }

    resolved = main._prompt_missing_ai_metadata(captured)

    assert resolved["source"] == "referral"
    assert resolved["prop_type"] == "Multifamily"
    assert resolved["loan_type"] == "Bridge"


def test_prompt_missing_ai_metadata_source_only_required(monkeypatch):
    """When source is the only missing field, only one prompt is issued."""
    prompts_seen: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts_seen.append(prompt)
        if "source" in prompt.lower():
            return "newsletter"
        return ""

    monkeypatch.setattr(builtins, "input", fake_input)

    captured = {
        "source": None,
        "prop_type": None,
        "loan_type": None,
    }

    resolved = main._prompt_missing_ai_metadata(captured)

    assert resolved["source"] == "newsletter"
    assert resolved["prop_type"] is None
    assert resolved["loan_type"] is None
    # Confirm that no firm_type or focus prompt was issued
    assert not any("firm" in p.lower() for p in prompts_seen)
    assert not any("focus" in p.lower() for p in prompts_seen)


def test_prompt_missing_ai_metadata_blank_source_leaves_none(monkeypatch):
    """Pressing Enter for source leaves it as None."""
    monkeypatch.setattr(builtins, "input", lambda _: "")

    captured = {"source": None, "prop_type": None, "loan_type": None}
    resolved = main._prompt_missing_ai_metadata(captured)

    assert resolved["source"] is None


def test_resolve_ai_focus_prefers_classifier_focus():
    focus = main._resolve_ai_focus({"focus": "commercial real estate lending"}, "commercial_real_estate")
    assert focus == "commercial real estate lending"


def test_resolve_ai_focus_falls_back_to_schema_name():
    focus = main._resolve_ai_focus({}, "commercial_real_estate")
    assert focus == "commercial real estate"


def test_resolve_ai_focus_returns_none_for_general_without_focus():
    focus = main._resolve_ai_focus({}, "general")
    assert focus is None

