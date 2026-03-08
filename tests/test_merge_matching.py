from scripts import merge_matching


def test_rank_match_suggestions_prefers_splink_top(monkeypatch):
    def fake_resolve_company_name(_name, _candidates, threshold=0.0):
        if threshold == 0.5:
            return [("Acme Capital LLC", 0.91)]
        return [("Acme Capital LLC", 0.91), ("Acme Partners", 0.63)]

    monkeypatch.setattr(merge_matching, "resolve_company_name", fake_resolve_company_name)

    suggestions, top_name, label = merge_matching.rank_match_suggestions(
        "Acme Capital",
        ["Acme Capital LLC", "Acme Partners", "BridgePoint Lending"],
        threshold=0.75,
        splink_threshold=0.5,
    )

    assert top_name == "Acme Capital LLC"
    assert "splink match" in label
    assert suggestions[0] == "Acme Capital LLC"


def test_prompt_user_for_match_accepts_top(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "y")

    match, custom_name = merge_matching.prompt_user_for_match(
        "Acme Capital",
        ["Acme Capital LLC", "Acme Partners"],
        "Acme Capital LLC",
        "splink match (probability=0.91)",
    )

    assert match == "Acme Capital LLC"
    assert custom_name is None


def test_prompt_user_for_match_create_new(monkeypatch):
    answers = iter(["n", "n", "Acme Custom Name"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    match, custom_name = merge_matching.prompt_user_for_match(
        "Acme Capital",
        ["Acme Capital LLC", "Acme Partners"],
        "Acme Capital LLC",
        "splink match (probability=0.91)",
    )

    assert match is None
    assert custom_name == "Acme Custom Name"


def test_prompt_user_for_match_skip(monkeypatch):
    answers = iter(["n", "s"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    match, custom_name = merge_matching.prompt_user_for_match(
        "Acme Capital",
        ["Acme Capital LLC", "Acme Partners"],
        "Acme Capital LLC",
        "splink match (probability=0.91)",
    )

    assert match is None
    assert custom_name is None


def test_prompt_user_for_match_select_index(monkeypatch):
    answers = iter(["n", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    match, custom_name = merge_matching.prompt_user_for_match(
        "Acme Capital",
        ["Acme Capital LLC", "Acme Partners"],
        "Acme Capital LLC",
        "splink match (probability=0.91)",
    )

    assert match == "Acme Partners"
    assert custom_name is None


def test_prompt_user_for_match_limits_selection_to_top_ten(monkeypatch):
    answers = iter(["11"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    suggestions = [f"Candidate {i}" for i in range(1, 13)]
    match, custom_name = merge_matching.prompt_user_for_match(
        "Acme Capital",
        suggestions,
        None,
        "",
    )

    assert match is None
    assert custom_name is None
