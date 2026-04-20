from scripts import merge_existing_data


def test_run_merge_deletes_processed_company_dir_when_all_duplicates(tmp_path, monkeypatch):
    source_dir = tmp_path / "data" / "companies"
    company_dir = source_dir / "Acme"
    md_dir = company_dir / "markdown"
    md_dir.mkdir(parents=True)
    (md_dir / "report.md").write_text("---\ncompany: Acme\n---\n\nBody", encoding="utf-8")

    db_dir = tmp_path / "db"
    db_dir.mkdir()

    monkeypatch.setattr(merge_existing_data, "choose_match", lambda name, existing, **kwargs: (None, "Acme"))
    monkeypatch.setattr(merge_existing_data, "append_markdown_to_company", lambda *args, **kwargs: False)

    code = merge_existing_data.run_merge(source_dir=source_dir, db_dir=db_dir, keep_merged_source=False)

    assert code == 0
    assert not company_dir.exists()


def test_run_merge_respects_keep_merged_source_flag(tmp_path, monkeypatch):
    source_dir = tmp_path / "data" / "companies"
    company_dir = source_dir / "Acme"
    md_dir = company_dir / "markdown"
    md_dir.mkdir(parents=True)
    (md_dir / "report.md").write_text("---\ncompany: Acme\n---\n\nBody", encoding="utf-8")

    db_dir = tmp_path / "db"
    db_dir.mkdir()

    monkeypatch.setattr(merge_existing_data, "choose_match", lambda name, existing, **kwargs: (None, "Acme"))
    monkeypatch.setattr(merge_existing_data, "append_markdown_to_company", lambda *args, **kwargs: False)

    code = merge_existing_data.run_merge(source_dir=source_dir, db_dir=db_dir, keep_merged_source=True)

    assert code == 0
    assert company_dir.exists()
