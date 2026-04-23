from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from .entity_resolution import find_best_match
from .openai_agent import CompanyResearchPipeline, _load_template_for_class, _normalise_homepage_url
from .config import load_config, resolve_storage_paths
from .store import (
    append_to_list_field,
    company_dirs,
    default_metadata,
    pretty_company_name_enhanced,
    safe_slug,
    update_metadata_in_files,
    write_markdown,
)


ReportResult = dict[str, Any]
BatchRunResult = tuple[list[dict], list[dict], list[str], list[str] | None]

_UNAVAILABLE_VALUES = {"not available", "n/a", "na"}
_WEBSITE_LINE_RE = re.compile(
    r"^\s*[-*]?\s*\*{0,2}\s*website\s*\*{0,2}\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
_FIRM_TYPE_LINE_RE = re.compile(
    r"^\s*[-*]?\s*\*{0,2}\s*firm\s+type\s*\*{0,2}\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)


def _check_applies_when(
    applies_when: dict[str, Any] | None,
    doc_metadata: dict[str, Any],
) -> bool:
    """Return True when *applies_when* conditions are satisfied by *doc_metadata*.

    Each key in *applies_when* is a metadata field name; the value is a
    condition dict.  The only supported operator today is ``contains_any``,
    which passes when the document field (treated as a list) contains at least
    one of the listed values.  An absent or empty *applies_when* is treated as
    "always applies".

    This convention is designed to be stored in the ontology-core attributes
    catalog as a top-level ``"applies_when"`` key, mapping each field name to
    its condition dict, so that branching logic is declarative and data-driven
    rather than hard-coded in consuming applications.  For example, to restrict
    ``loan_type`` to companies whose ``firm_type`` includes ``"lender"``::

        {
          "applies_when": {
            "loan_type": {"firm_type": {"contains_any": ["lender"]}}
          }
        }

    Adding a new conditional property therefore requires only a catalog change
    in ``ontology-core`` — no code change is needed here.
    """
    if not applies_when:
        return True
    for field, condition in applies_when.items():
        meta_value = doc_metadata.get(field, [])
        if isinstance(meta_value, str):
            meta_value = [meta_value]
        if "contains_any" in condition:
            if not any(v in meta_value for v in condition["contains_any"]):
                return False
    return True


def _llm_normalize_catalog_properties(
    file_path: Path,
    *,
    api_key: str | None,
    model: str,
) -> None:
    """Normalize catalog properties and NAICS fields via the CompanySanitizer LLM workflow.

    Uses the same LLM classification prompts as
    :class:`~data_platform.actions.sanitize_company.CompanySanitizer` to:

    1. Select catalog-normalized values for ``focus``, ``firm_type``,
       ``loan_structure``, and ``loan_type`` metadata fields.
       ``loan_structure`` and ``loan_type`` are only written when the company's
       ``firm_type`` satisfies the ``applies_when`` condition stored in the
       ontology-core catalog (e.g. ``firm_type`` must contain ``"lender"``).
    2. Assign NAICS sector/industry codes (``naics_code``, ``naics_title``,
       ``naics_sector_code``, ``naics_sector_title``) via a separate LLM call.

    The ``applies_when`` conditions are read from the raw ontology-core catalog
    at runtime so that branching rules remain in the catalog — not in this code.

    Results are written back to *file_path*.  Website identification is still
    left to the ``sanitize_on_save`` pass to avoid duplicate LLM calls.

    Fails silently when ``data-platform`` is not installed or the LLM call
    fails — the file is left with its existing AI-inferred values.
    """
    try:
        from data_platform.actions.llm_client import LLMClient  # noqa: PLC0415
        from data_platform.actions.sanitize_company import CompanySanitizer  # noqa: PLC0415
        from data_platform.ontology_adapter import (  # noqa: PLC0415
            AttributesCatalog,
            get_attributes_catalog,
            get_catalog,
        )
    except ImportError:
        return

    try:
        # Fetch applies_when conditions from the raw ontology catalog.
        # The catalog uses a flat dict structure, with an optional top-level
        # "applies_when" key that maps field names to their conditions.
        # These declarative rules drive which properties are written for a
        # given company without hardcoding focus values in this module.
        applies_when_map: dict[str, dict[str, Any] | None] = {}
        try:
            raw = get_catalog("attributes")
            raw_applies_when = raw.get("applies_when") or {}
            if isinstance(raw_applies_when, dict):
                for field, condition in raw_applies_when.items():
                    applies_when_map[field] = condition
        except Exception:  # noqa: BLE001
            pass

        full_catalog = get_attributes_catalog()
        # focus/firm_type are always classified; loan_structure and loan_type are
        # conditionally included per their applies_when rules in the catalog
        # (both restricted to companies whose firm_type contains "lender").
        # Website and NAICS are handled separately.
        target_fields = {"focus", "firm_type", "loan_structure", "loan_type"}
        filtered_catalog = AttributesCatalog(
            properties=[p for p in full_catalog.properties if p.field in target_fields]
        )
        if not filtered_catalog.properties:
            return

        llm = LLMClient(api_key=api_key or None, model=model)
        sanitizer = CompanySanitizer(
            kb_root=file_path.parent.parent,
            llm_client=llm,
            attributes_catalog=filtered_catalog,
            companies_folder=file_path.parent.name,
        )
        doc = sanitizer._reader.read_file(file_path)
        changes = sanitizer._normalize_properties(doc)
        changes.update(sanitizer._classify_naics(doc))
        # Drop fields whose applies_when conditions are not met by this document.
        # Fields with no applies_when entry in the catalog are always kept.
        changes = {
            field: value
            for field, value in changes.items()
            if _check_applies_when(applies_when_map.get(field), doc.metadata)
        }
        if changes:
            CompanySanitizer._write_metadata(file_path, {**doc.metadata, **changes})
            print(f"  LLM-normalized metadata fields: {sorted(changes)}")
    except Exception as exc:  # noqa: BLE001
        # Never let normalization errors abort the research flow.
        print(f"  LLM metadata normalization skipped: {exc}")


def _try_sanitize_research_output(
    file_path: Path,
    *,
    api_key: str | None,
    model: str,
) -> None:
    """Run LLM-based metadata sanitisation on a freshly written staging file.

    Uses ``data_platform.actions.CompanySanitizer`` to normalise ``firm_type``
    and ``focus`` against the attributes catalog, fill in a missing ``website``
    field, and assign NAICS codes.

    The sanitiser is pointed at the staging markdown directory so it operates
    on the file written by the research pipeline before it is merged into the
    KB.  This enriches the metadata carried into the merge step.

    This is a best-effort enrichment step — any import or runtime failures are
    caught and reported without aborting the rest of the research workflow.

    Requires ``data-platform`` to be installed and
    ``data_platform.sanitize_on_save: true`` in *config.yaml*.
    """
    try:
        from data_platform.actions.llm_client import LLMClient  # noqa: PLC0415
        from data_platform.actions.sanitize_company import CompanySanitizer  # noqa: PLC0415
    except ImportError:
        return

    try:
        llm = LLMClient(api_key=api_key or None, model=model)
        # Point the reader at the staging company dir, treating the markdown
        # sub-folder as the "companies" folder within a temporary KB root so
        # CompanySanitizer's KnowledgeBaseReader can locate the file.
        sanitizer = CompanySanitizer(
            kb_root=file_path.parent.parent,
            llm_client=llm,
            companies_folder=file_path.parent.name,
        )
        result = sanitizer.sanitize_file(file_path)
        if result.success and result.changes:
            print(f"  Sanitized metadata fields: {sorted(result.changes)}")
    except Exception as exc:  # noqa: BLE001
        # Never let sanitisation errors abort the research flow.
        print(f"  Sanitization skipped: {exc}")


def _print_processed_companies(processed_companies: list[str]) -> None:
    if not processed_companies:
        return
    print(f"\nProcessed {len(processed_companies)} company/companies:")
    for company in processed_companies:
        print(f"  - {company}")


def _is_yes(value: str) -> bool:
    return value.strip().lower() == "y"


def _collect_companies(rows: Iterable[dict]) -> list[tuple[str, dict]]:
    companies: list[tuple[str, dict]] = []
    for row in rows:
        name = (row.get("company") or row.get("name") or "").strip()
        if name:
            companies.append((name, row))
    return companies


def _print_research_result(result: ReportResult) -> None:
    print(f"\n✓ Website identified: {result['website']}")
    print(f"✓ Schema applied:     {result['schema']}")
    print(f"✓ Classifier notes:   {result['classifier_agent'].get('reasoning', '')}\n")
    print("--- Report ---")
    print(result["report"])
    print("--------------\n")


def _extract_ai_report_field_lines(report: str) -> tuple[str | None, str | None, str]:
    """Extract website and firm type lines from AI markdown and return cleaned report text."""
    if not report:
        return None, None, ""

    website_value: str | None = None
    firm_type_value: str | None = None
    kept_lines: list[str] = []

    for line in report.splitlines():
        website_match = _WEBSITE_LINE_RE.match(line)
        if website_match:
            extracted = website_match.group(1).strip()
            if extracted and extracted.lower() not in _UNAVAILABLE_VALUES:
                website_value = extracted
            continue

        firm_type_match = _FIRM_TYPE_LINE_RE.match(line)
        if firm_type_match:
            extracted = firm_type_match.group(1).strip()
            if extracted and extracted.lower() not in _UNAVAILABLE_VALUES:
                firm_type_value = extracted
            continue

        kept_lines.append(line)

    cleaned_report = "\n".join(kept_lines).strip()
    return website_value, firm_type_value, cleaned_report


def _prompt_missing_ai_metadata(captured: dict[str, str | None]) -> dict[str, str | None]:
    """Prompt for the remaining metadata fields that require user input.

    ``focus``, ``firm_type``, ``loan_type``, and ``loan_structure`` are no
    longer prompted here — they are determined automatically by the LLM
    catalog-normalization workflow in :func:`_llm_normalize_catalog_properties`.
    This function handles only the fields that have no automated source:

    * ``source`` — where the company lead came from (always asked).
    * ``prop_type`` — property type(s) for CRE-focused companies.
    """
    resolved = dict(captured)

    # Source must always be provided by the user; never use a hardcoded default.
    resolved["source"] = input("Enter source for this company (leave blank to skip): ").strip() or None

    if not resolved.get("prop_type"):
        resolved["prop_type"] = input(
            "Enter property type for this company (comma-separated for multiple, leave blank to skip): "
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


# ---------------------------------------------------------------------------
# Direct-to-KB helpers (interactive mode 1)
# ---------------------------------------------------------------------------

def _insert_under_heading(body: str, heading: str, addition: str) -> str:
    """Insert *addition* under a markdown heading, creating the heading if absent."""
    if not addition.strip():
        return body

    lines = body.splitlines()
    target_idx: int | None = None
    for i, line in enumerate(lines):
        stripped = line.lstrip("#").strip()
        if stripped.lower() == heading.lower():
            target_idx = i
            break

    addition_block = addition.strip()

    if target_idx is None:
        prefix = "\n\n" if body.strip() else ""
        return f"{body.rstrip()}{prefix}## {heading}\n\n{addition_block}\n"

    insert_at = target_idx + 1
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1

    new_lines = lines[:insert_at] + ["", addition_block, ""] + lines[insert_at:]
    return "\n".join(new_lines).strip() + "\n"


def _kb_clean_company_filename(name: str, db_dir: Path) -> Path:
    """Return a unique ``<name>.md`` path inside *db_dir*.

    Applies the same Title-Case prettification used by the merge script so
    file names in the KB are consistent regardless of how a company is added.
    """
    pretty = pretty_company_name_enhanced(name) or safe_slug(name)
    pretty = re.sub(r'[<>:"/\\|?*]+', " ", pretty)
    pretty = re.sub(r"\s+", " ", pretty).strip() or "Company"
    idx = 1
    while True:
        suffix = "" if idx == 1 else f" {idx}"
        path = db_dir / f"{pretty}{suffix}.md"
        if not path.exists():
            return path
        idx += 1


def _resolve_against_kb(
    company_name: str,
    website: str | None,
    db_dir: Path,
) -> tuple[Path | None, str | None]:
    """Check whether *company_name* already exists in the KB and prompt the user.

    Resolution is attempted in three tiers (same strategy as the merge script):

    1. **Deterministic** — ``data-platform`` ``CompanyRepository`` matching by
       website domain then normalised name (if the package is installed).
    2. **Probabilistic** — splink / difflib fallback via
       :func:`~src.entity_resolution.find_best_match`.
    3. **Interactive** — the user confirms, creates, or skips.

    Returns:
        ``(matched_path, None)`` — company already in the KB; use existing file.
        ``(None, new_name)``     — company is new; create a file with this name.
        ``(None, None)``         — skip this company entirely.
    """
    existing = [p.stem for p in db_dir.glob("*.md")] if db_dir.exists() else []

    if not existing:
        print(f"  No existing KB entries found for '{company_name}'.")
        resp = input("Create a new company entry? (Y/n): ").strip().lower()
        if resp in {"", "y", "yes"}:
            custom_name = input(
                f"Enter company name for KB (or press Enter to use '{company_name}'): "
            ).strip()
            return (None, custom_name or company_name)
        return (None, None)

    # Tier 1: deterministic matching via data-platform CompanyRepository.
    try:
        from data_platform.knowledge_base.reader import KnowledgeBaseReader  # noqa: PLC0415
        from data_platform.repositories.companies import CompanyRepository  # noqa: PLC0415
        from data_platform.ontology_adapter import Company  # noqa: PLC0415

        reader = KnowledgeBaseReader(db_dir.parent, folder_map={"company": db_dir.name})
        repo = CompanyRepository()
        for doc in reader.read_all(object_type="company"):
            doc_name = str(doc.metadata.get("name") or doc.path.stem)
            doc_ws = str(doc.metadata.get("website") or "")
            repo.save(Company(id=doc.path.stem, name=doc_name, website=doc_ws or None))

        candidate = Company(id="__probe__", name=company_name, website=website or None)
        matched = repo.resolve(candidate)
        if matched:
            matched_file = db_dir / f"{matched.id}.md"
            if matched_file.exists():
                if website and matched.website:
                    label = f"domain match ({matched.website})"
                else:
                    label = f"name match ({matched.name!r})"
                confirm = input(
                    f"Found {label} in KB: '{matched.id}'. Use it? (y/n): "
                ).strip().lower()
                if confirm == "y":
                    return (matched_file, None)
    except Exception:  # noqa: BLE001
        pass

    # Tier 2: probabilistic matching via splink / difflib.
    best_name, prob = find_best_match(company_name, existing, threshold=0.75)
    if best_name:
        confirm = input(
            f"Found similar company in KB: '{best_name}' (score={prob:.2f}). Use it? (y/n): "
        ).strip().lower()
        if confirm == "y":
            return (db_dir / f"{best_name}.md", None)

    # Tier 3: interactive — no automatic match found.
    print(f"  No matching company found in KB for '{company_name}'.")
    resp = input("Create a new company entry? (Y/n): ").strip().lower()
    if resp in {"", "y", "yes"}:
        custom_name = input(
            f"Enter company name for KB (or press Enter to use '{company_name}'): "
        ).strip()
        return (None, custom_name or company_name)
    return (None, None)


def _write_research_direct_to_kb(
    company: str,
    result: ReportResult,
    db_file: Path,
    *,
    schemas_dir: str | None = None,
    sanitize: bool = False,
    sanitize_api_key: str | None = None,
    sanitize_model: str = "gpt-4o-mini",
) -> None:
    """Write an AI research result directly into a KB markdown file.

    Creates or updates *db_file*:

    * When the file does not yet exist, the schema-class template is used as
      the starting structure (falling back to an empty body when no template
      is found).
    * The cleaned AI research text is inserted under the ``## Basic
      Underwriting`` heading (the heading is created if absent).
    * Minimal front-matter (``website``, ``schema``, ``date``) is written so
      that the file is immediately valid.
    * The ``CompanySanitizer`` LLM workflow is then called to populate or
      normalise ``focus``, ``firm_type``, ``loan_structure``, ``loan_type``,
      and NAICS codes — and to confirm / overwrite the ``website`` field.
    """
    schema_name = result.get("schema", "general")
    website_from_body, _firm_type_from_body, cleaned_report = _extract_ai_report_field_lines(
        result.get("report", "")
    )
    ai_website = website_from_body or result.get("website", "") or ""

    # Load template for this schema class (if available).
    template_content: str | None = None
    if schemas_dir:
        try:
            template_content = _load_template_for_class(schemas_dir, schema_name)
        except Exception:  # noqa: BLE001
            pass

    # Start from template (if present) or a blank body.
    if template_content:
        if template_content.startswith("---"):
            parts = template_content.split("---", 2)
            if len(parts) >= 3:
                try:
                    dst_meta: dict = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    dst_meta = {}
                dst_body = parts[2]
            else:
                dst_meta = {}
                dst_body = template_content
        else:
            dst_meta = {}
            dst_body = template_content
    else:
        dst_meta = {}
        dst_body = ""

    # Set minimal front-matter; CompanySanitizer will normalise/fill other fields.
    dst_meta["website"] = ai_website
    dst_meta["schema"] = schema_name
    if not dst_meta.get("date"):
        dst_meta["date"] = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

    # Insert the cleaned research report under the "Basic Underwriting" heading.
    if cleaned_report.strip():
        dst_body = _insert_under_heading(dst_body, "Basic Underwriting", cleaned_report.strip())

    # Write the file.
    db_file.parent.mkdir(parents=True, exist_ok=True)
    fm = yaml.safe_dump(dst_meta, sort_keys=False, allow_unicode=True)
    db_file.write_text(f"---\n{fm}---\n{dst_body.lstrip()}", encoding="utf-8")
    print(f"Report saved directly to KB: {db_file}")

    # Call the CompanySanitizer LLM workflow to populate metadata.
    if sanitize:
        _try_sanitize_research_output(
            db_file,
            api_key=sanitize_api_key,
            model=sanitize_model,
        )
    else:
        _llm_normalize_catalog_properties(
            db_file,
            api_key=sanitize_api_key,
            model=sanitize_model,
        )


def _load_companies_csv(path: str = "companies.csv") -> tuple[list[dict], list[str] | None]:
    """Load companies CSV rows and raw field names."""
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
    """Rewrite companies CSV after removing rows already processed."""
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
    result: ReportResult,
    *,
    csv_source: str | None = None,
    csv_firm_type: str | None = None,
    interactive: bool = True,
    source_dir: str | None = None,
    sanitize: bool = False,
    sanitize_api_key: str | None = None,
    sanitize_model: str = "gpt-4o-mini",
) -> None:
    """Persist one company report and optionally prompt for interactive metadata updates."""
    website_from_body, firm_type_from_body, cleaned_report = _extract_ai_report_field_lines(result["report"])
    ai_website = website_from_body or result["website"]
    focus_from_agent = _resolve_ai_focus(result.get("classifier_agent", {}), result.get("schema"))

    # Merge AI-inferred firm_type with any CSV-supplied value
    merged_firm_type = firm_type_from_body
    if csv_firm_type:
        merged_firm_type = append_to_list_field(firm_type_from_body, csv_firm_type)

    dirs = company_dirs(source_dir or "data/companies", company)
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

    # Normalize focus and firm_type against the attributes catalog via LLM.
    # When full sanitization is enabled (sanitize_on_save), it already runs
    # _normalize_properties as part of a broader enrichment pass, so we skip
    # the focused call to avoid duplicate LLM requests for the same fields.
    if sanitize:
        _try_sanitize_research_output(
            path,
            api_key=sanitize_api_key,
            model=sanitize_model,
        )
    else:
        _llm_normalize_catalog_properties(
            path,
            api_key=sanitize_api_key,
            model=sanitize_model,
        )

    if not interactive:
        return

    captured = {
        "source": None,
        "prop_type": None,
    }
    resolved = _prompt_missing_ai_metadata(captured)

    updates: dict[str, str] = {}
    for key in ("source", "prop_type"):
        value = resolved.get(key)
        if value:
            updates[key] = value

    if updates:
        count = update_metadata_in_files(dirs["md"], updates)
        if count > 0:
            print(f"Updated metadata in {count} file(s).")


def _run_interactive(
    pipeline: CompanyResearchPipeline,
    db_dir: str,
    *,
    schemas_dir: str | None = None,
    sanitize: bool = False,
    sanitize_api_key: str | None = None,
    sanitize_model: str = "gpt-4o-mini",
) -> list[str]:
    """Run interactive single-company research loop, writing directly to the KB.

    New workflow (no local staging):

    1. Prompt for a company name.
    2. Run the :class:`~src.openai_agent.WebsiteAgent` to find the company's
       website (user may override the result).
    3. Resolve the company against the KB using tiered entity matching.
       - If the company already exists, report the existing file and loop.
       - If new, proceed to research.
    4. Run the full research pipeline (reusing the pre-found website URL so the
       WebsiteAgent is not called twice).
    5. Write the cleaned report directly into the KB under the
       ``## Basic Underwriting`` heading.
    6. Call the ``CompanySanitizer`` LLM workflow to normalise metadata fields
       (``focus``, ``firm_type``, NAICS codes, etc.) and confirm the website.
    """
    print("\n=== AI Research Mode (Interactive) ===")
    print("Companies are researched and written directly to the knowledge base.\n")

    db_path = Path(db_dir)
    db_path.mkdir(parents=True, exist_ok=True)

    processed_companies: list[str] = []

    while True:
        company = input("Enter company name (or 'q' to quit): ").strip()
        if company.lower() == "q":
            break

        # Step 1: Discover the company website.
        print(f"\nFinding website for '{company}'…")
        website_url = ""
        try:
            website_result = pipeline.find_website(company)
            website_url = _normalise_homepage_url(website_result.get("website", "") or "")
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"  Could not find website automatically: {exc}")

        if website_url:
            print(f"  Found website: {website_url}")
            override = input("  Press Enter to accept, or type a different URL: ").strip()
            if override:
                website_url = _normalise_homepage_url(override)
        else:
            website_url = input("  Enter website URL (or press Enter to skip): ").strip()
            if website_url:
                website_url = _normalise_homepage_url(website_url)

        # Step 2: Entity resolution against the KB.
        matched_path, new_name = _resolve_against_kb(company, website_url or None, db_path)

        if matched_path is None and new_name is None:
            print(f"  Skipped: {company}")
            continue

        if matched_path is not None:
            print(f"  Company already exists in KB: {matched_path.name}")
            processed_companies.append(company)
            another = input("Research another company? (y/n): ").strip().lower()
            if another != "y":
                break
            continue

        # Step 3: Research the new company (reuse the pre-found website).
        print(f"\nResearching '{company}'…")
        try:
            result = pipeline.run(company, website=website_url or None)
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"  Error during research: {exc}")
            continue

        _print_research_result(result)

        save = input("Save to knowledge base? (y/n): ").strip().lower()
        if not _is_yes(save):
            continue

        # Step 4: Write directly to KB and run CompanySanitizer.
        assert new_name is not None  # guaranteed by _resolve_against_kb logic
        target_file = _kb_clean_company_filename(new_name, db_path)
        _write_research_direct_to_kb(
            new_name,
            result,
            target_file,
            schemas_dir=schemas_dir,
            sanitize=sanitize,
            sanitize_api_key=sanitize_api_key,
            sanitize_model=sanitize_model,
        )

        processed_companies.append(company)

        another = input("Research another company? (y/n): ").strip().lower()
        if another != "y":
            break

    return processed_companies


def _run_batch(
    pipeline: CompanyResearchPipeline,
    source_dir: str,
    *,
    sanitize: bool = False,
    sanitize_api_key: str | None = None,
    sanitize_model: str = "gpt-4o-mini",
) -> BatchRunResult:
    """Run batch research using companies.csv rows."""
    print("\n=== AI Batch Research Mode (companies.csv) ===")
    print("This mode processes each company from companies.csv using the OpenAI pipeline.\n")

    rows, fieldnames = _load_companies_csv("companies.csv")

    companies = _collect_companies(rows)

    if not companies:
        print("No companies loaded from companies.csv. Exiting.")
        return rows, [], [], fieldnames

    continue_on_error = input("Continue to next company if one fails? (y/n): ").strip().lower() != "n"

    processed_rows: list[dict] = []
    processed_companies: list[str] = []

    total = len(companies)
    for index, (company, row) in enumerate(companies, start=1):
        print(f"\n[{index}/{total}] Researching '{company}'…")
        try:
            csv_schema_class = (row.get("schema_class") or "").strip() or None
            result = pipeline.run(company, schema_class=csv_schema_class)
            csv_source = (row.get("source") or "").strip() or None
            csv_firm_type = (row.get("firm_type") or "").strip() or None
            _save_report(
                company,
                result,
                csv_source=csv_source,
                csv_firm_type=csv_firm_type,
                interactive=False,
                source_dir=source_dir,
                sanitize=sanitize,
                sanitize_api_key=sanitize_api_key,
                sanitize_model=sanitize_model,
            )
            print(f"  ✓ Website: {result['website']}")
            print(f"  ✓ Schema:  {result['schema']}")
            processed_rows.append(row)
            processed_companies.append(company)
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"  ✗ Failed: {exc}")
            if not continue_on_error:
                print("Stopping batch due to error.")
                break

    return rows, processed_rows, processed_companies, fieldnames


def run() -> None:
    """CLI entry point for interactive and batch research modes."""
    try:
        pipeline = CompanyResearchPipeline.from_config()
    except (ImportError, ValueError) as exc:
        print(f"Error initialising OpenAI pipeline: {exc}")
        return

    storage = resolve_storage_paths("config.yaml")
    source_dir = str(storage["source_dir"])
    database_dir = str(storage["database_dir"])

    # Load data-platform sanitisation config (Phase 6).
    cfg = load_config("config.yaml") if Path("config.yaml").exists() else {}
    dp_cfg = cfg.get("data_platform") or {}
    sanitize = bool(dp_cfg.get("sanitize_on_save", False))
    oa_cfg = cfg.get("openai") or {}
    sanitize_api_key = oa_cfg.get("api_key") or None
    sanitize_model = str(oa_cfg.get("model", "gpt-4o-mini"))
    schemas_dir = str(oa_cfg.get("schemas_dir") or "schemas")

    mode = input("Choose mode - (1) AI Interactive, (2) AI Batch from companies.csv: ").strip()

    if mode == "2":
        try:
            rows, processed_rows, processed_companies, fieldnames = _run_batch(
                pipeline,
                source_dir,
                sanitize=sanitize,
                sanitize_api_key=sanitize_api_key,
                sanitize_model=sanitize_model,
            )
        except FileNotFoundError:
            print("companies.csv not found.")
            return

        _print_processed_companies(processed_companies)
        if processed_companies:
            resp = input("Remove processed companies from companies.csv so you can resume later? (y/n): ").strip().lower()
            if _is_yes(resp):
                try:
                    _write_remaining_companies(
                        all_rows=rows,
                        processed_rows=processed_rows,
                        fieldnames=fieldnames,
                        path="companies.csv",
                    )
                except (OSError, ValueError, RuntimeError) as exc:
                    print(f"Failed to update companies.csv: {exc}")

        resp = input("\nRun merge tool to add markdown files to DB now? (y/n): ").strip().lower()
        if _is_yes(resp):
            subprocess.run([sys.executable, "scripts/merge_markdown_db.py", "--config", "config.yaml"], check=False)
    else:
        processed_companies = _run_interactive(
            pipeline,
            database_dir,
            schemas_dir=schemas_dir,
            sanitize=sanitize,
            sanitize_api_key=sanitize_api_key,
            sanitize_model=sanitize_model,
        )
        _print_processed_companies(processed_companies)



if __name__ == "__main__":
    run()

