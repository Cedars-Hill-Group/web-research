import builtins

from src import main


def test_prompt_missing_ai_metadata_prompts_for_firm_type_source_and_missing_fields(monkeypatch):
    # firm_type=None → prompt, source → always prompt, prop_type=None → prompt, loan_type=None → prompt
    answers = iter(["Balance Sheet Lender", "referral", "Multifamily", "Bridge"])

    monkeypatch.setattr(builtins, "input", lambda _: next(answers))

    captured = {
        "focus": "ai-research",
        "firm_type": None,
        "source": None,
        "prop_type": None,
        "loan_type": None,
    }

    resolved = main._prompt_missing_ai_metadata(captured)

    assert resolved["focus"] == "ai-research"
    assert resolved["firm_type"] == "Balance Sheet Lender"
    assert resolved["source"] == "referral"
    assert resolved["prop_type"] == "Multifamily"
    assert resolved["loan_type"] == "Bridge"


def test_prompt_missing_ai_metadata_shows_ai_firm_type_for_confirmation(monkeypatch):
    # When AI already inferred firm_type, user presses Enter to keep it, and still gets prompted for source.
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        if "Firm type" in prompt:
            return ""  # keep AI inferred value
        if "source" in prompt.lower():
            return "newsletter"
        if "property type" in prompt.lower():
            return ""
        if "loan type" in prompt.lower():
            return ""
        return ""

    monkeypatch.setattr(builtins, "input", fake_input)

    captured = {
        "focus": "commercial real estate",
        "firm_type": "Balance Sheet Lender",
        "source": None,
        "prop_type": None,
        "loan_type": None,
    }

    resolved = main._prompt_missing_ai_metadata(captured)

    # firm_type should remain as AI inferred since user pressed Enter
    assert resolved["firm_type"] == "Balance Sheet Lender"
    assert resolved["source"] == "newsletter"
    # Verify that the AI inferred value was shown in the firm_type prompt
    firm_type_prompt = next(p for p in prompts if "Firm type" in p)
    assert "Balance Sheet Lender" in firm_type_prompt


def test_prompt_missing_ai_metadata_user_can_override_ai_firm_type(monkeypatch):
    # When AI inferred firm_type, user can replace it with a different value.
    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt: "Bridge Lender, Debt Fund" if "Firm type" in prompt
        else ("newsletter" if "source" in prompt.lower() else ""),
    )

    captured = {
        "focus": "real estate",
        "firm_type": "Balance Sheet Lender",
        "source": None,
        "prop_type": None,
        "loan_type": None,
    }

    resolved = main._prompt_missing_ai_metadata(captured)

    assert resolved["firm_type"] == "Bridge Lender, Debt Fund"
    assert resolved["source"] == "newsletter"


def test_resolve_ai_focus_prefers_classifier_focus():
    focus = main._resolve_ai_focus({"focus": "commercial real estate lending"}, "commercial_real_estate")
    assert focus == "commercial real estate lending"


def test_resolve_ai_focus_falls_back_to_schema_name():
    focus = main._resolve_ai_focus({}, "commercial_real_estate")
    assert focus == "commercial real estate"


def test_resolve_ai_focus_returns_none_for_general_without_focus():
    focus = main._resolve_ai_focus({}, "general")
    assert focus is None
