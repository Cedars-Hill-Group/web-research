import builtins

from src import main


def test_prompt_missing_ai_metadata_prompts_only_for_missing(monkeypatch):
    answers = iter(["Balance Sheet Lender", "Multifamily", "Bridge"])  # firm_type, prop_type, loan_type

    monkeypatch.setattr(builtins, "input", lambda _: next(answers))

    captured = {
        "focus": "ai-research",
        "firm_type": None,
        "source": "ai-research",
        "prop_type": None,
        "loan_type": None,
    }

    resolved = main._prompt_missing_ai_metadata(captured)

    assert resolved["focus"] == "ai-research"
    assert resolved["source"] == "ai-research"
    assert resolved["firm_type"] == "Balance Sheet Lender"
    assert resolved["prop_type"] == "Multifamily"
    assert resolved["loan_type"] == "Bridge"


def test_resolve_ai_focus_prefers_classifier_focus():
    focus = main._resolve_ai_focus({"focus": "commercial real estate lending"}, "commercial_real_estate")
    assert focus == "commercial real estate lending"


def test_resolve_ai_focus_falls_back_to_schema_name():
    focus = main._resolve_ai_focus({}, "commercial_real_estate")
    assert focus == "commercial real estate"


def test_resolve_ai_focus_returns_none_for_general_without_focus():
    focus = main._resolve_ai_focus({}, "general")
    assert focus is None
