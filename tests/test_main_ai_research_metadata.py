from src.main import _extract_ai_report_field_lines


def test_extract_ai_report_field_lines_moves_website_and_firm_type_to_metadata():
    report = """## Company Overview
- **Company Name**: Acme Capital
- **Website**: https://acme.example/
- **Firm Type**: Balance Sheet Lender

## Description
Acme provides senior debt financing.
"""

    website, firm_type, cleaned = _extract_ai_report_field_lines(report)

    assert website == "https://acme.example/"
    assert firm_type == "Balance Sheet Lender"
    assert "**Website**" not in cleaned
    assert "**Firm Type**" not in cleaned
    assert "## Description" in cleaned


def test_extract_ai_report_field_lines_preserves_body_mentions_and_not_available_values():
    report = """## Company Overview
- **Website**: Not available
- **Firm Type**: N/A

## Description
The website and firm type details were not listed on the source page.
"""

    website, firm_type, cleaned = _extract_ai_report_field_lines(report)

    assert website is None
    assert firm_type is None
    assert "- **Website**:" not in cleaned
    assert "- **Firm Type**:" not in cleaned
    assert "website and firm type details" in cleaned
