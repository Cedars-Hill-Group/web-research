from __future__ import annotations

import csv
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from .openai_agent import CompanyResearchPipeline
from .store import company_dirs, default_metadata, safe_slug, update_metadata_in_files, write_markdown


def _extract_ai_report_field_lines(report: str) -> tuple[str | None, str | None, str]:
    if not report:
        return None, None, ""

    import re

    website_value: str | None = None
    firm_type_value: str | None = None
    kept_lines: list[str] = []

    website_line = re.compile(r"^\s*[-*]?\s*\*{0,2}\s*website\s*\*{0,2}\s*:\s*(.+?)\s*$", re.IGNORECASE)
    firm_type_line = re.compile(r"^\s*[-*]?\s*\*{0,2}\s*firm\s+type\s*\*{0,2}\s*:\s*(.+?)\s*$", re.IGNORECASE)

    for line in report.splitlines():
        website_match = website_line.match(line)
        if website_match:
            extracted = website_match.group(1).strip()
            if extracted and extracted.lower() not in {"not available", "n/a", "na"}:
                website_value = extracted
            continue

        firm_type_match = firm_type_line.match(line)
        if firm_type_match:
            extracted = firm_type_match.group(1).strip()
            if extracted and extracted.lower() not in {"not available", "n/a", "na"}:
                firm_type_value = extracted
            continue

        kept_lines.append(line)

    cleaned_report = "\n".join(kept_lines).strip()
    return website_value, firm_type_value, cleaned_report


def _prompt_missing_ai_metadata(captured: dict[str, str | None]) -> dict[str, str | None]:
    resolved = dict(captured)

    if not resolved.get("focus"):
        resolved["focus"] = input("Enter focus for this company (leave blank to skip): ").strip() or None

    # For firm_type: show AI-inferred value (if any) and let user confirm, edit, or add values.
    ai_firm_type = resolved.get("firm_type")
    if ai_firm_type:
        user_input = input(
            f"Firm type (AI inferred: {ai_firm_type!r}) - press Enter to keep, or enter new/additional values"
            " (comma-separated): "
        ).strip()
        if user_input:
            resolved["firm_type"] = user_input
    else:
        resolved["firm_type"] = input("Enter firm type for this company (leave blank to skip): ").strip() or None

    # Source must always be provided by the user; never use a hardcoded default.
    resolved["source"] = input("Enter source for this company (leave blank to skip): ").strip() or None

    if not resolved.get("prop_type"):
        resolved["prop_type"] = input(
            "Enter property type for this company (comma-separated for multiple, leave blank to skip): "
        ).strip() or None
    if not resolved.get("loan_type"):
        resolved["loan_type"] = input(
            "Enter loan type for this company (comma-separated for multiple, leave blank to skip): "
        ).strip() or None

    return resolved


def _resolve_ai_focus(classifier_result: dict, schema_name: str | None) -> str | None:
    focus = str((classifier_result or {}).get("focus") or "").strip()
    if focus:
        return focus

    schema = str(schema_name or "").strip()
    if schema and schema != "general":
        return schema.replace("_", " ")

    return None


def _load_companies_csv(path: str = "companies.csv") -> tuple[list[dict], list[str] | None]:
    rows: list[dict] = []
    fieldnames: list[str] | None = None
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)
    return rows, fieldnames


def _write_remaining_companies(
    *,
    all_rows: list[dict],
    processed_rows: list[dict],
    fieldnames: list[str] | None,
    path: str = "companies.csv",
) -> None:
    backup = f"{path}.bak.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    shutil.copyfile(path, backup)
    print(f"Backup written to {backup}")

    remaining = [r for r in all_rows if r not in processed_rows]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames or ["company"])
        writer.writeheader()
        for row in remaining:
            writer.writerow(row)

    print("Updated companies.csv with remaining companies.")


def _save_report(
    company: str,
    result: dict,
    *,
    csv_source: str | None = None,
    csv_firm_type: str | None = None,
    interactive: bool = True,
) -> None:
    website_from_body, firm_type_from_body, cleaned_report = _extract_ai_report_field_lines(result["report"])
    ai_website = website_from_body or result["website"]
    focus_from_agent = _resolve_ai_focus(result.get("classifier_agent", {}), result.get("schema"))

    # Merge AI-inferred firm_type with any CSV-supplied value
    merged_firm_type = firm_type_from_body
    if csv_firm_type:
        from .store import append_to_list_field
        merged_firm_type = append_to_list_field(firm_type_from_body, csv_firm_type)

    dirs = company_dirs("data/companies", company)
    meta = default_metadata(
        website=ai_website,
        focus=focus_from_agent,
        firm_type=merged_firm_type,
        source=csv_source,
    )
    meta["schema"] = result["schema"]

    slug = safe_slug(f"{company}-ai-research")
    path = write_markdown(dirs["md"], slug, cleaned_report, meta)
    print(f"Report saved to {path}")

    if not interactive:
        return

    captured = {
        "focus": focus_from_agent,
        "firm_type": merged_firm_type,
        "source": None,
        "prop_type": None,
        "loan_type": None,
    }
    resolved = _prompt_missing_ai_metadata(captured)

    updates: dict[str, str] = {}
    for key in ("focus", "firm_type", "source", "prop_type", "loan_type"):
        value = resolved.get(key)
        if value:
            updates[key] = value

    if updates:
        count = update_metadata_in_files(dirs["md"], updates)
        if count > 0:
            print(f"Updated metadata in {count} file(s).")


def _run_interactive(pipeline: CompanyResearchPipeline) -> list[str]:
    print("\n=== AI Research Mode (Interactive) ===")
    print("This project now runs only on the OpenAI multi-agent research pipeline.\n")

    processed_companies: list[str] = []

    while True:
        company = input("Enter company name (or 'q' to quit): ").strip()
        if company.lower() == "q":
            break

        context = input("Enter optional context (industry, location, etc.) or press Enter to skip: ").strip()

        print(f"\nResearching '{company}'…")
        try:
            result = pipeline.run(company, context)
        except Exception as exc:  # noqa: BLE001
            print(f"Error during research: {exc}")
            continue

        print(f"\n✓ Website identified: {result['website']}")
        print(f"✓ Schema applied:     {result['schema']}")
        print(f"✓ Classifier notes:   {result['classifier_agent'].get('reasoning', '')}\n")
        print("--- Report ---")
        print(result["report"])
        print("--------------\n")

        save = input("Save report to markdown file? (y/n): ").strip().lower()
        if save == "y":
            _save_report(company, result)

        processed_companies.append(company)

        another = input("Research another company? (y/n): ").strip().lower()
        if another != "y":
            break

    return processed_companies


def _run_batch(pipeline: CompanyResearchPipeline) -> tuple[list[dict], list[dict], list[str], list[str] | None]:
    print("\n=== AI Batch Research Mode (companies.csv) ===")
    print("This mode processes each company from companies.csv using the OpenAI pipeline.\n")

    rows, fieldnames = _load_companies_csv("companies.csv")

    companies: list[tuple[str, dict]] = []
    for row in rows:
        name = (row.get("company") or row.get("name") or "").strip()
        if name:
            companies.append((name, row))

    if not companies:
        print("No companies loaded from companies.csv. Exiting.")
        return rows, [], [], fieldnames

    context = input("Enter optional context to apply to all companies (or press Enter to skip): ").strip()
    continue_on_error = input("Continue to next company if one fails? (y/n): ").strip().lower() != "n"

    processed_rows: list[dict] = []
    processed_companies: list[str] = []

    total = len(companies)
    for index, (company, row) in enumerate(companies, start=1):
        print(f"\n[{index}/{total}] Researching '{company}'…")
        try:
            result = pipeline.run(company, context)
            csv_source = (row.get("source") or "").strip() or None
            csv_firm_type = (row.get("firm_type") or "").strip() or None
            _save_report(company, result, csv_source=csv_source, csv_firm_type=csv_firm_type, interactive=False)
            print(f"  ✓ Website: {result['website']}")
            print(f"  ✓ Schema:  {result['schema']}")
            processed_rows.append(row)
            processed_companies.append(company)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ Failed: {exc}")
            if not continue_on_error:
                print("Stopping batch due to error.")
                break

    return rows, processed_rows, processed_companies, fieldnames


def run() -> None:
    try:
        pipeline = CompanyResearchPipeline.from_config()
    except (ImportError, ValueError) as exc:
        print(f"Error initialising OpenAI pipeline: {exc}")
        return

    mode = input("Choose mode - (1) AI Interactive, (2) AI Batch from companies.csv: ").strip()

    if mode == "2":
        try:
            rows, processed_rows, processed_companies, fieldnames = _run_batch(pipeline)
        except FileNotFoundError:
            print("companies.csv not found.")
            return

        if processed_companies:
            print(f"\nProcessed {len(processed_companies)} company/companies:")
            for company in processed_companies:
                print(f"  - {company}")

            resp = input("Remove processed companies from companies.csv so you can resume later? (y/n): ").strip().lower()
            if resp == "y":
                try:
                    _write_remaining_companies(
                        all_rows=rows,
                        processed_rows=processed_rows,
                        fieldnames=fieldnames,
                        path="companies.csv",
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"Failed to update companies.csv: {exc}")
    else:
        processed_companies = _run_interactive(pipeline)

        if processed_companies:
            print(f"\nProcessed {len(processed_companies)} company/companies:")
            for company in processed_companies:
                print(f"  - {company}")

    resp = input("\nRun merge tool to add markdown files to DB now? (y/n): ").strip().lower()
    if resp == "y":
        subprocess.run([sys.executable, "scripts/merge_markdown_db.py"], check=False)


if __name__ == "__main__":
    run()
