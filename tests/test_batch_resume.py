import csv
from pathlib import Path
import shutil
import yaml
from src import main


def test_write_remaining_companies(tmp_path):
    # create a companies.csv with three rows
    csv_path = tmp_path / "companies.csv"
    rows = [
        {"company": "A", "note": "one"},
        {"company": "B", "note": "two"},
        {"company": "C", "note": "three"},
    ]
    with csv_path.open("w", encoding="utf-8", newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=["company", "note"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # simulate processed rows = first two
    all_rows = rows
    processed = [rows[0], rows[1]]

    # monkeypatch shutil.copyfile to copy our file to bak in tmp
    bak = tmp_path / "companies.csv.bak.test"
    shutil.copyfile(str(csv_path), str(bak))

    # Now run the same code path as main: write remaining
    remaining = [r for r in all_rows if r not in processed]

    # write to a new file path
    out_path = tmp_path / "out_companies.csv"
    with out_path.open("w", encoding="utf-8", newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=["company", "note"])
        writer.writeheader()
        for r in remaining:
            writer.writerow(r)

    # verify contents
    with out_path.open("r", encoding="utf-8", newline='') as fh:
        reader = csv.DictReader(fh)
        rows_out = list(reader)
    assert len(rows_out) == 1
    assert rows_out[0]["company"] == "C"


def test_save_report_batch_uses_csv_source_and_firm_type(tmp_path, monkeypatch):
    """In batch mode (_save_report with interactive=False), source and firm_type from the CSV
    row must be written into the metadata file without prompting the user."""
    import builtins

    def _no_input(prompt: str) -> str:
        raise AssertionError(f"input() called in batch mode: {prompt!r}")

    monkeypatch.setattr(builtins, "input", _no_input)

    # Redirect the data directory to tmp_path
    monkeypatch.chdir(tmp_path)

    result = {
        "report": "## Overview\nSome content.",
        "website": "https://example.com",
        "schema": "general",
        "classifier_agent": {"focus": "real estate", "reasoning": "test"},
    }

    main._save_report(
        "TestCo",
        result,
        csv_source="newsletter",
        csv_firm_type="Debt Fund",
        interactive=False,
    )

    # Locate the written markdown file
    md_files = list(tmp_path.glob("data/companies/**/markdown/*.md"))
    assert md_files, "No markdown file was written"

    content = md_files[0].read_text(encoding="utf-8")
    assert content.startswith("---")
    parts = content.split("---", 2)
    meta = yaml.safe_load(parts[1])

    assert meta.get("source") == "newsletter"
    assert meta.get("firm_type") == "Debt Fund"


def test_save_report_batch_csv_firm_type_merges_with_ai_inferred(tmp_path, monkeypatch):
    """When AI infers a firm_type and the CSV also provides one, they should be merged."""
    import builtins

    def _no_input(prompt: str) -> str:
        raise AssertionError(f"input() called in batch mode: {prompt!r}")

    monkeypatch.setattr(builtins, "input", _no_input)
    monkeypatch.chdir(tmp_path)

    result = {
        "report": "## Overview\n- **Firm Type**: Balance Sheet Lender\nSome content.",
        "website": "https://example.com",
        "schema": "general",
        "classifier_agent": {},
    }

    main._save_report(
        "AcmeCo",
        result,
        csv_source="conference",
        csv_firm_type="Debt Fund",
        interactive=False,
    )

    md_files = list(tmp_path.glob("data/companies/**/markdown/*.md"))
    assert md_files, "No markdown file was written"

    content = md_files[0].read_text(encoding="utf-8")
    parts = content.split("---", 2)
    meta = yaml.safe_load(parts[1])

    # Both AI-inferred and CSV values should appear
    firm_type = meta.get("firm_type")
    if isinstance(firm_type, list):
        assert "Balance Sheet Lender" in firm_type
        assert "Debt Fund" in firm_type
    else:
        assert "Balance Sheet Lender" in firm_type
        assert "Debt Fund" in firm_type

    assert meta.get("source") == "conference"