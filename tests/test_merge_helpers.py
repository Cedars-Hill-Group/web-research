from scripts import merge_helpers


def test_parse_front_matter_with_yaml():
    text = "---\ncompany: Acme\nsource: web\n---\n\n## Body\n"
    meta, body = merge_helpers.parse_front_matter(text)

    assert meta["company"] == "Acme"
    assert meta["source"] == "web"
    assert "## Body" in body


def test_parse_front_matter_without_yaml():
    text = "## No Front Matter\n"
    meta, body = merge_helpers.parse_front_matter(text)

    assert meta == {}
    assert body == text


def test_write_with_front_matter_round_trip(tmp_path):
    path = tmp_path / "out.md"
    merge_helpers.write_with_front_matter(path, {"company": "Acme"}, "## Body\n")

    content = path.read_text(encoding="utf-8")
    assert content.startswith("---")
    meta, body = merge_helpers.parse_front_matter(content)
    assert meta["company"] == "Acme"
    assert "## Body" in body


def test_insert_under_heading_existing_heading():
    body = "## Overview\n\nExisting text\n"
    updated = merge_helpers.insert_under_heading(body, "Overview", "New text")

    block = updated.split("## Overview", 1)[1]
    assert "Existing text" in block
    assert "New text" in block


def test_insert_under_heading_missing_heading_creates_section():
    body = "## Existing\n\nBody\n"
    updated = merge_helpers.insert_under_heading(body, "Basic Underwriting", "Inserted")

    assert "## Basic Underwriting" in updated
    assert "Inserted" in updated


def test_extract_h2_headings():
    body = "## One\nText\n## Two\nText\n"
    headings = merge_helpers.extract_h2_headings(body)
    assert headings == ["One", "Two"]


def test_parse_h2_sections_with_preamble():
    body = "Preamble line\n\n## One\nA\n\n## Two\nB\n"
    preamble, sections = merge_helpers.parse_h2_sections(body)

    assert "Preamble line" in preamble
    assert sections[0][0] == "One"
    assert "A" in sections[0][1]
    assert sections[1][0] == "Two"
    assert "B" in sections[1][1]


def test_insert_source_sections_into_template_matches_headings():
    template = "## Overview\n\n## Description\n\n"
    source = "## Overview\nOverview text\n\n## Description\nDescription text\n"

    merged = merge_helpers.insert_source_sections_into_template(template, source, "<!-- source -->")
    overview_block = merged.split("## Overview", 1)[1].split("## Description", 1)[0]
    description_block = merged.split("## Description", 1)[1]

    assert "Overview text" in overview_block
    assert "Description text" in description_block


def test_insert_source_sections_into_template_preserves_unmatched_sections():
    template = "## Overview\n\n## Description\n\n"
    source = "## Unknown\nUnknown text\n"

    merged = merge_helpers.insert_source_sections_into_template(template, source, "<!-- source -->")
    overview_block = merged.split("## Overview", 1)[1].split("## Description", 1)[0]

    assert "### Unknown" in overview_block
    assert "Unknown text" in overview_block


def test_parse_date_iso_and_date_only():
    assert merge_helpers.parse_date("2026-01-01T10:20:30Z") is not None
    assert merge_helpers.parse_date("2026-01-01") is not None
    assert merge_helpers.parse_date("invalid-date") is None
