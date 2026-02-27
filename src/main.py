# main.py
import threading
import time
import yaml
import sys
import subprocess
import re
import csv
from flask import Flask
from datetime import datetime, timezone


from .browser import get_driver
from .search import search_official_site
from .ui_tui import HybridTUI
from .store import company_dirs, write_markdown, default_metadata, safe_slug
import shutil
from pathlib import Path

app = Flask(__name__)
global_tui = None   # holds the active TUI instance


def _extract_ai_report_field_lines(report: str) -> tuple[str | None, str | None, str]:
    """Extract website/firm type field-line values and return report body without those lines.

    This targets schema-style field lines (for example, "- **Website**: ...") so that
    website and firm type live in markdown metadata instead of being duplicated in the
    markdown body for AI Research mode saves.
    """
    if not report:
        return None, None, ""

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


def bypass_scraping_and_add_to_db(company_name: str) -> bool:
    """Allow user to manually enter company data and add it directly to the database without scraping.
    
    Args:
        company_name: The name of the company
        
    Returns:
        True if data was successfully added, False otherwise
    """
    print(f"\n--- Adding {company_name} to database without scraping ---")
    
    # Prompt for website
    website = input("Enter company website (or press Enter to skip): ").strip()
    if not website:
        website = ""
    
    # Prompt for focus
    focus = input("Enter focus (or press Enter to skip): ").strip()
    
    # Prompt for firm type
    firm_type = input("Enter firm type (or press Enter to skip): ").strip()

    # Prompt for property type
    prop_type = input("Enter property type (comma-separated for multiple, or press Enter to skip): ").strip()
    
    # Prompt for loan type
    loan_type = input("Enter loan type (comma-separated for multiple, or press Enter to skip): ").strip()
    
    # Prompt for source
    source = input("Enter source (or press Enter to skip): ").strip()
    
    # Prompt for content/notes
    content = input("Enter any notes or content about the company (or press Enter to skip): ").strip()
    
    # Confirm before saving
    print(f"\nAbout to save:")
    print(f"  Company: {company_name}")
    print(f"  Website: {website if website else '(none)'}")
    print(f"  Focus: {focus if focus else '(none)'}")
    print(f"  Firm Type: {firm_type if firm_type else '(none)'}")
    print(f"  Source: {source if source else '(none)'}")
    print(f"  Property Type: {prop_type if prop_type else '(none)'}")
    print(f"  Loan Type: {loan_type if loan_type else '(none)'}")
    if content:
        print(f"  Notes: {content[:100]}...")
    
    confirm = input("\nProceed with saving? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return False
    
    try:
        dirs = company_dirs('data/companies', company_name)
        
        # Create metadata
        meta = default_metadata(
            website=website,
            focus=focus or None,
            firm_type=firm_type or None,
            source=source or None,
            prop_type=prop_type or None,
            loan_type=loan_type or None,
        )
        
        # Write markdown file with the content/notes
        slug = safe_slug(f"{company_name}-manual")
        write_markdown(dirs['md'], slug, content, meta)
        
        print(f"✓ Successfully saved {company_name} to database.")
        return True
    except Exception as e:
        print(f"✗ Error saving to database: {e}")
        return False


def save_company_metadata_if_no_scraping(company_name: str, focus: str | None = None, firm_type: str | None = None, source: str | None = None, prop_type: str | None = None, loan_type: str | None = None) -> bool:
    """If user provided metadata but no pages were scraped, create a placeholder markdown file
    with that metadata so the company is still added to the database.
    
    Args:
        company_name: The name of the company
        focus: Optional focus value
        firm_type: Optional firm type value
        source: Optional source value
        
    Returns:
        True if a placeholder was created, False otherwise
    """
    # Only create placeholder if there's at least one metadata field provided
    if not (focus or firm_type or source or prop_type or loan_type):
        return False
    
    try:
        dirs = company_dirs('data/companies', company_name)
        meta = default_metadata(
            website="",
            focus=focus,
            firm_type=firm_type,
            source=source,
            prop_type=prop_type,
            loan_type=loan_type,
        )
        
        # Create a placeholder markdown file with a note that no pages were scraped
        placeholder_content = "(No pages scraped - metadata only)"
        slug = safe_slug(f"{company_name}-metadata")
        write_markdown(dirs['md'], slug, placeholder_content, meta)
        
        print(f"  Created metadata-only entry for {company_name}.")
        return True
    except Exception as e:
        print(f"  Failed to create metadata entry: {e}")
        return False



def run_server():
    # disable the reloader so the server runs in the same process
    app.run(port=5000, debug=False, use_reloader=False, threaded=True)


def _make_handler(d):
    """Return a signal handler that will close the given driver and exit."""
    try:
        from .browser import close_driver
    except Exception:
        close_driver = None

    def _handler(signum, frame):
        try:
            if close_driver:
                close_driver(d)
        except Exception:
            pass
        try:
            import sys
            sys.exit(0)
        except SystemExit:
            raise
        except Exception:
            pass

    return _handler


def _ensure_driver_alive(driver, user_agent=None):
    """Return a working driver. If the provided driver appears closed or unusable,
    attempt to create a fresh driver via get_driver and return it.
    """
    try:
        # Prefer checking session_id when available: webdriver will set this to None after quit
        sid = getattr(driver, 'session_id', None)
        if sid is None:
            raise Exception("no session")
        # also attempt to access a simple property to catch other failure modes
        _ = driver.current_url
        return driver
    except Exception:
        # treat as unusable - attempt to construct a fresh driver
        try:
            new = get_driver(user_agent)

            return new
        except Exception:
            # last resort: return None so callers can handle
            return None


def _prompt_missing_ai_metadata(captured: dict[str, str | None]) -> dict[str, str | None]:
    """Prompt only for metadata fields not captured by AI agents."""
    resolved = dict(captured)

    if not resolved.get("focus"):
        resolved["focus"] = input("Enter focus for this company (leave blank to skip): ").strip() or None
    if not resolved.get("firm_type"):
        resolved["firm_type"] = input("Enter firm type for this company (leave blank to skip): ").strip() or None
    if not resolved.get("source"):
        resolved["source"] = input("Enter source for this company (leave blank to skip): ").strip() or None
    if not resolved.get("prop_type"):
        resolved["prop_type"] = input("Enter property type for this company (comma-separated for multiple, leave blank to skip): ").strip() or None
    if not resolved.get("loan_type"):
        resolved["loan_type"] = input("Enter loan type for this company (comma-separated for multiple, leave blank to skip): ").strip() or None

    return resolved


def _resolve_ai_focus(classifier_result: dict, schema_name: str | None) -> str | None:
    """Resolve company focus from classifier output with schema-based fallback."""
    focus = str((classifier_result or {}).get("focus") or "").strip()
    if focus:
        return focus

    schema = str(schema_name or "").strip()
    if schema and schema != "general":
        return schema.replace("_", " ")

    return None


def _run_openai_research(cfg: dict, driver) -> tuple[object, list[str]]:
    """Interactive AI-assisted company research using the OpenAI multi-agent pipeline."""
    from .openai_agent import CompanyResearchPipeline

    print("\n=== AI Research Mode (OpenAI) ===")
    print("This mode uses OpenAI to identify company websites, classify the company,")
    print("and generate a structured description and summary.\n")

    try:
        pipeline = CompanyResearchPipeline.from_config()
    except (ImportError, ValueError) as exc:
        print(f"Error initialising OpenAI pipeline: {exc}")
        return driver, []

    processed_companies: list[str] = []

    while True:
        company = input("Enter company name (or 'q' to quit): ").strip()
        if company.lower() == "q":
            print("Exiting AI research mode.")
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

        website_from_body, firm_type_from_body, cleaned_report = _extract_ai_report_field_lines(result["report"])
        ai_website = website_from_body or result["website"]
        focus_from_agent = _resolve_ai_focus(result.get("classifier_agent", {}), result.get("schema"))

        # Save AI report output first
        save = input("Save report to markdown file? (y/n): ").strip().lower()
        if save == "y":
            from .store import company_dirs, safe_slug, default_metadata, write_markdown, update_metadata_in_files
            dirs = company_dirs("data/companies", company)
            meta = default_metadata(
                website=ai_website,
                focus=focus_from_agent,
                firm_type=firm_type_from_body,
                source="ai-research",
            )
            meta["schema"] = result["schema"]
            slug = safe_slug(f"{company}-ai-research")
            path = write_markdown(dirs["md"], slug, cleaned_report, meta)
            print(f"Report saved to {path}\n")

            captured = {
                "focus": focus_from_agent,
                "firm_type": firm_type_from_body,
                "source": "ai-research",
                "prop_type": None,
                "loan_type": None,
            }
            resolved = _prompt_missing_ai_metadata(captured)
            updates = {}
            if resolved.get("focus"):
                updates["focus"] = resolved["focus"]
            if resolved.get("firm_type"):
                updates["firm_type"] = resolved["firm_type"]
            if resolved.get("source"):
                updates["source"] = resolved["source"]
            if resolved.get("prop_type"):
                updates["prop_type"] = resolved["prop_type"]
            if resolved.get("loan_type"):
                updates["loan_type"] = resolved["loan_type"]

            if updates:
                count = update_metadata_in_files(dirs['md'], updates)
                if count > 0:
                    print(f"Updated metadata in {count} file(s).")
        else:
            print("Report not saved; AI mode does not support manual scraping.")

        processed_companies.append(company)

        another = input("Research another company? (y/n): ").strip().lower()
        if another != "y":
            break

    return driver, processed_companies


def _run_openai_research_batch(cfg: dict, driver) -> tuple[object, list[dict], list[dict], list[str], list[str] | None]:
    """Batch AI-assisted research from companies.csv with automatic report saves.

    Returns:
        (driver, all_rows, processed_rows, processed_names, fieldnames)
    """
    from .openai_agent import CompanyResearchPipeline
    from .store import company_dirs, safe_slug, default_metadata, write_markdown

    print("\n=== AI Batch Research Mode (OpenAI + companies.csv) ===")
    print("This mode processes each company from companies.csv using the OpenAI pipeline.")
    print("Reports are auto-saved to markdown with metadata.\n")

    rows: list[dict] = []
    fieldnames: list[str] | None = None
    try:
        with open("companies.csv", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = reader.fieldnames
            for row in reader:
                rows.append(row)
    except Exception:
        print("Failed to read companies.csv or file missing.")
        return driver, [], [], [], None

    companies: list[tuple[str, dict]] = []
    for row in rows:
        name = (row.get("company") or row.get("name") or "").strip()
        if name:
            companies.append((name, row))

    if not companies:
        print("No companies loaded from companies.csv. Exiting.")
        return driver, rows, [], [], fieldnames

    try:
        pipeline = CompanyResearchPipeline.from_config()
    except (ImportError, ValueError) as exc:
        print(f"Error initialising OpenAI pipeline: {exc}")
        return driver, rows, [], [], fieldnames

    context = input("Enter optional context to apply to all companies (or press Enter to skip): ").strip()
    continue_on_error = input("Continue to next company if one fails? (y/n): ").strip().lower() != "n"

    processed_rows: list[dict] = []
    processed_companies: list[str] = []

    total = len(companies)
    for index, (company, row) in enumerate(companies, start=1):
        print(f"\n[{index}/{total}] Researching '{company}'…")
        try:
            result = pipeline.run(company, context)
            website_from_body, firm_type_from_body, cleaned_report = _extract_ai_report_field_lines(result["report"])
            ai_website = website_from_body or result["website"]
            focus_from_agent = _resolve_ai_focus(result.get("classifier_agent", {}), result.get("schema"))

            dirs = company_dirs("data/companies", company)
            metadata = default_metadata(
                website=ai_website,
                focus=focus_from_agent,
                firm_type=firm_type_from_body,
                source="ai-research",
            )
            metadata["schema"] = result["schema"]
            slug = safe_slug(f"{company}-ai-research")
            path = write_markdown(dirs["md"], slug, cleaned_report, metadata)

            print(f"  ✓ Website: {result['website']}")
            print(f"  ✓ Schema:  {result['schema']}")
            print(f"  ✓ Saved:   {path}")

            processed_rows.append(row)
            processed_companies.append(company)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ Failed: {exc}")
            if not continue_on_error:
                print("Stopping batch due to error.")
                break

    return driver, rows, processed_rows, processed_companies, fieldnames


def run():
    global global_tui

    # Load config
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))

    # Start Flask server
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(1.0)

    driver = get_driver(cfg["scrape"].get("user_agent"))

    # register signal handlers that will close the driver on SIGINT/SIGTERM
    try:
        from .browser import close_driver
        import signal

        signal.signal(signal.SIGINT, _make_handler(driver))
        try:
            signal.signal(signal.SIGTERM, _make_handler(driver))
        except Exception:
            # some platforms may not support SIGTERM
            pass
    except Exception:
        pass

    # Choose input mode: single, batch, or AI-assisted
    mode = input(
        "Choose input mode - (1) Single company, (2) Batch from companies.csv, "
        "(3) AI Research (OpenAI), (4) AI Batch from companies.csv: "
    ).strip()
    if mode == "3":
        driver, processed_companies = _run_openai_research(cfg, driver)

        # close driver when AI workflow is done
        try:
            from .browser import close_driver
            close_driver(driver)
            print("Browser closed.")
        except Exception:
            pass

        if processed_companies:
            print(f"\nProcessed {len(processed_companies)} company/companies:")
            for comp in processed_companies:
                print(f"  - {comp}")

            try:
                resp = input("\nRun merge tool to add markdown files to DB now? (y/n): ").strip().lower()
                if resp == "y":
                    subprocess.run([sys.executable, "scripts/merge_markdown_db.py"], check=False)
            except Exception:
                pass

        return
    elif mode == "4":
        driver, rows, processed_rows, processed_companies, fieldnames = _run_openai_research_batch(cfg, driver)

        try:
            from .browser import close_driver
            close_driver(driver)
            print("Browser closed.")
        except Exception:
            pass

        if processed_companies:
            print(f"\nProcessed {len(processed_companies)} company/companies:")
            for comp in processed_companies:
                print(f"  - {comp}")

            try:
                resp = input("Remove processed companies from companies.csv so you can resume later? (y/n): ").strip().lower()
                if resp == "y":
                    try:
                        bak = f"companies.csv.bak.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                        shutil.copyfile("companies.csv", bak)
                        print(f"Backup written to {bak}")
                    except Exception:
                        print("Failed to write backup of companies.csv")

                    remaining = [r for r in rows if r not in processed_rows]
                    try:
                        with open("companies.csv", "w", encoding="utf-8", newline="") as fh:
                            writer = csv.DictWriter(fh, fieldnames=fieldnames or ("company",))
                            writer.writeheader()
                            for r in remaining:
                                writer.writerow(r)
                        print("Updated companies.csv with remaining companies.")
                    except Exception:
                        print("Failed to update companies.csv")
            except Exception:
                pass

            try:
                resp = input("Run merge tool to add markdown files to DB now? (y/n): ").strip().lower()
                if resp == "y":
                    subprocess.run([sys.executable, "scripts/merge_markdown_db.py"], check=False)
            except Exception:
                pass

        return
    elif mode == "2":
        # Batch mode
        rows = []
        fieldnames = None
        try:
            with open("companies.csv", encoding="utf-8", newline='') as fh:
                reader = csv.DictReader(fh)
                fieldnames = reader.fieldnames
                for row in reader:
                    rows.append(row)
        except Exception:
            print("Failed to read companies.csv or file missing.")
            rows = []

        # extract names for display
        companies = []
        for row in rows:
            name = (row.get("company") or row.get("name") or "").strip()
            if name:
                companies.append((name, row))

        if not companies:
            print("No companies loaded from companies.csv. Exiting.")
            return

        prompt_each = input("Prompt for each company search result? (y/n): ").strip().lower() == "y"

        # start a single worker once for the session
        tui_worker_started = False
        processed_rows = []

        for name, row in companies:
            print(f"\nProcessing: {name}")
            
            # Search results loop - allow user to request more results
            start_index = 1
            sites = []
            
            while True:
                # Fetch results (initial or additional)
                if start_index == 1:
                    sites = search_official_site(name, max_results=3, start_index=start_index)
                else:
                    # Fetch next batch of results
                    more_sites = search_official_site(name, max_results=3, start_index=start_index)
                    if more_sites:
                        sites.extend(more_sites)
                    else:
                        print("  No more results available.")
                        start_index -= 3  # Roll back for retry
                        continue

                if not sites:
                    print("  No results found. Skipping.")
                    break

                # Display current results
                print("\n  Search results:")
                display_count = min(len(sites), start_index + 2)  # Show current batch
                for i in range(start_index - 1, display_count):
                    s = sites[i]
                    print(f"  {i+1}. {s['title']} - {s['link']}")
                    print(f"     {s['snippet']}\n")

                if prompt_each:
                    # Enhanced prompt with more options
                    choice = input("  Options: (y)es to continue, (m)ore results, (x)skip company and delete from batch, (s)kip scraping but add manually, (q)uit batch: ").strip().lower()
                    
                    if choice == "q":
                        print("Exiting batch early.")
                        # Break out of both loops
                        sites = None
                        break
                    
                    elif choice == "x":
                        # Skip company and mark for deletion from CSV
                        print(f"  Skipping {name} and will remove from companies.csv.")
                        processed_rows.append(row)  # Mark as processed so it gets removed
                        sites = None
                        break
                    
                    elif choice == "m":
                        # Request more results
                        start_index += 3
                        if start_index > 91:  # Google Custom Search API limit
                            print("  Reached maximum results (100). Can't fetch more.")
                            start_index = 88  # Reset to last valid batch
                            continue
                        print("  Fetching more results...")
                        continue
                    
                    elif choice == "s":
                        # Skip scraping and add manually to database
                        if bypass_scraping_and_add_to_db(name):
                            processed_rows.append(row)
                        sites = None
                        break
                    
                    elif choice == "y":
                        # Continue with scraping using current sites
                        break
                    
                    else:
                        print("  Invalid choice. Skipping this company.")
                        sites = None
                        break
                else:
                    print("  Auto-accepting first result for this company.")
                    break
            
            # Check if we need to exit the main loop (quit was selected)
            if prompt_each and choice == "q":
                break
            
            # Skip to next company if no valid sites
            if not sites:
                continue

            tui = HybridTUI()
            # ensure shared browser driver is alive before assigning to TUI
            driver = _ensure_driver_alive(driver, cfg["scrape"].get("user_agent"))
            tui.sites = sites
            tui.driver = driver
            tui.company = name
            # indicate that this TUI is sharing the driver provided by the batch loop
            tui._shared_driver = True

            tui.filters = cfg.get("filters", {})

            global_tui = tui

            print("  Launching TUI; press 'g' to scrape the current page, 'c' to commit scraped pages, or 'f' to save and finish this company, then close the TUI to continue batch.")
            tui.run()

            # prompt for focus, firm_type, and source after scraping is complete
            try:
                focus = input("Enter focus for this company (leave blank to skip): ").strip()
                firm_type = input("Enter firm type for this company (leave blank to skip): ").strip()
                prop_type = input("Enter property type for this company (comma-separated for multiple, leave blank to skip): ").strip()
                loan_type = input("Enter loan type for this company (comma-separated for multiple, leave blank to skip): ").strip()
                source = input("Enter source for this company (leave blank to skip): ").strip()
                
                # Update TUI instance for any future commits
                tui.company_focus = focus or None
                tui.company_firm_type = firm_type or None
                tui.company_source = source or None
                tui.company_prop_type = prop_type or None
                tui.company_loan_type = loan_type or None
                
                # Check if any pages were scraped
                pages_scraped = len(tui.collected_pages) > 0
                
                # Update already-saved markdown files if values were provided
                if focus or firm_type or source or prop_type or loan_type:
                    from pathlib import Path
                    from .store import company_dirs, safe_slug, update_metadata_in_files
                    dirs = company_dirs('data/companies', name)
                    updates = {}
                    if focus:
                        updates['focus'] = focus
                    if firm_type:
                        updates['firm_type'] = firm_type
                    if prop_type:
                        updates['prop_type'] = prop_type
                    if loan_type:
                        updates['loan_type'] = loan_type
                    if source:
                        updates['source'] = source
                    count = update_metadata_in_files(dirs['md'], updates)
                    if count > 0:
                        print(f"  Updated metadata in {count} file(s).")
                    
                    # If no pages were scraped but metadata was provided, create a metadata-only entry
                    if not pages_scraped:
                        if save_company_metadata_if_no_scraping(name, focus or None, firm_type or None, source or None, prop_type or None, loan_type or None):
                            pass  # Success message already printed
            except Exception as e:
                print(f"  Error updating metadata: {e}")

            # mark as processed (we launched and completed the TUI)
            processed_rows.append(row)

            # After returning from the TUI, ensure the driver is still usable for the next company.
            driver = _ensure_driver_alive(driver, cfg["scrape"].get("user_agent"))

        print("Batch processing complete. Exiting.")

        # close the shared driver now that batch work is done
        try:
            from .browser import close_driver
            close_driver(driver)
            print("Browser closed.")
        except Exception:
            pass

        # Offer to remove processed companies from companies.csv so user can resume later
        try:
            if processed_rows:
                resp = input("Remove processed companies from companies.csv so you can resume later? (y/n): ").strip().lower()
                if resp == "y":
                    # backup
                    try:
                        bak = f"companies.csv.bak.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                        shutil.copyfile("companies.csv", bak)
                        print(f"Backup written to {bak}")
                    except Exception:
                        print("Failed to write backup of companies.csv")

                    # compute remaining rows and write
                    remaining = [r for r in rows if r not in processed_rows]
                    try:
                        with open("companies.csv", "w", encoding="utf-8", newline='') as fh:
                            writer = csv.DictWriter(fh, fieldnames=fieldnames or ("company",))
                            writer.writeheader()
                            for r in remaining:
                                writer.writerow(r)
                        print("Updated companies.csv with remaining companies.")
                    except Exception:
                        print("Failed to update companies.csv")
        except Exception:
            pass

        # offer to run the merge tool
        try:
            resp = input("Run merge tool to add markdown files to DB now? (y/n): ").strip().lower()
            if resp == "y":
                subprocess.run([sys.executable, "scripts/merge_markdown_db.py"], check=False)
        except Exception:
            pass

        return

    # Single mode - allow multiple companies before updating database
    print("\n=== Single Company Mode (Multiple Companies) ===")
    print("Enter companies one at a time. After each company is processed,")
    print("you'll be asked if you want to continue entering more companies.\n")
    
    processed_companies = []  # Track companies for later database update
    
    while True:
        company = input("Enter company name (or 'q' to quit): ").strip()
        if company.lower() == "q":
            print("Exiting.")
            break

        # Search results loop - allow user to request more results
        start_index = 1
        sites = []
        choice = None
        
        while True:
            # Fetch results (initial or additional)
            if start_index == 1:
                sites = search_official_site(company, max_results=3, start_index=start_index)
            else:
                # Fetch next batch of results
                more_sites = search_official_site(company, max_results=3, start_index=start_index)
                if more_sites:
                    sites.extend(more_sites)
                else:
                    print("No more results available.")
                    start_index -= 3  # Roll back for retry
                    continue

            if not sites:
                print("No results found. Try again.")
                break

            # Display current results
            print("\nSearch results:")
            display_count = min(len(sites), start_index + 2)  # Show current batch
            for i in range(start_index - 1, display_count):
                s = sites[i]
                print(f"{i+1}. {s['title']} - {s['link']}")
                print(f"   {s['snippet']}\n")

            choice = input("Options: (y)es to continue, (m)ore results, (s)kip scraping but add manually, (n)ew search, (q)uit: ").strip().lower()

            if choice == "s":
                # Skip scraping and add manually to database
                if bypass_scraping_and_add_to_db(company):
                    print("\nAdded manually.\n")
                    processed_companies.append(company)
                else:
                    print("\nCancelled manual entry.\n")
                sites = None
                break
            
            elif choice == "m":
                # Request more results
                start_index += 3
                if start_index > 91:  # Google Custom Search API limit
                    print("Reached maximum results (100). Can't fetch more.")
                    start_index = 88  # Reset to last valid batch
                    continue
                print("Fetching more results...")
                continue
            
            elif choice == "y":
                # Continue with scraping using current sites
                break
            
            elif choice == "n":
                print("\nOkay, let's try again.\n")
                sites = None
                break
            
            elif choice == "q":
                print("\nExiting.")
                break
            
            else:
                print("Invalid input. Try again.")
                continue
        
        # Skip to next company if no valid sites or user chose new search
        if not sites:
            continue

        elif choice == "y":
            tui = HybridTUI()
            tui.sites = sites
            tui.driver = driver
            tui.company = company
            tui._shared_driver = True  # Keep driver open for next company

            tui.filters = cfg.get("filters", {})

            global_tui = tui
            tui.run()

            # prompt for focus, firm_type, and source after scraping is complete
            try:
                focus = input("Enter focus for this company (leave blank to skip): ").strip()
                firm_type = input("Enter firm type for this company (leave blank to skip): ").strip()
                prop_type = input("Enter property type for this company (comma-separated for multiple, leave blank to skip): ").strip()
                loan_type = input("Enter loan type for this company (comma-separated for multiple, leave blank to skip): ").strip()
                source = input("Enter source for this company (leave blank to skip): ").strip()
                
                # Update TUI instance
                tui.company_focus = focus or None
                tui.company_firm_type = firm_type or None
                tui.company_source = source or None
                tui.company_prop_type = prop_type or None
                tui.company_loan_type = loan_type or None
                
                # Check if any pages were scraped
                pages_scraped = len(tui.collected_pages) > 0
                
                # Update already-saved markdown files if values were provided
                if focus or firm_type or source or prop_type or loan_type:
                    from pathlib import Path
                    from .store import company_dirs, safe_slug, update_metadata_in_files
                    dirs = company_dirs('data/companies', company)
                    updates = {}
                    if focus:
                        updates['focus'] = focus
                    if firm_type:
                        updates['firm_type'] = firm_type
                    if prop_type:
                        updates['prop_type'] = prop_type
                    if loan_type:
                        updates['loan_type'] = loan_type
                    if source:
                        updates['source'] = source
                    count = update_metadata_in_files(dirs['md'], updates)
                    if count > 0:
                        print(f"Updated metadata in {count} file(s).")
                    
                    # If no pages were scraped but metadata was provided, create a metadata-only entry
                    if not pages_scraped:
                        if save_company_metadata_if_no_scraping(company, focus or None, firm_type or None, source or None, prop_type or None, loan_type or None):
                            pass  # Success message already printed
            except Exception as e:
                print(f"Error updating metadata: {e}")

            # Keep track of processed company
            processed_companies.append(company)

            # Ensure the driver is still alive for next company
            driver = _ensure_driver_alive(driver, cfg["scrape"].get("user_agent"))

            # Ask if user wants to continue with another company
            continue_choice = input("\nContinue entering more companies? (y/n): ").strip().lower()
            if continue_choice != "y":
                print("\nFinished entering companies. Processing database...")
                break

        elif choice == "n":
            print("\nOkay, let's try again.\n")
            continue

        elif choice == "q":
            print("\nExiting.")
            break

        else:
            print("Invalid input. Returning to company prompt.\n")

    # After all companies are processed, close the driver and offer to run merge tool
    try:
        from .browser import close_driver
        close_driver(driver)
        print("Browser closed.")
    except Exception:
        pass

    # offer to run the merge tool for any newly scraped markdown
    if processed_companies:
        print(f"\nProcessed {len(processed_companies)} company/companies:")
        for comp in processed_companies:
            print(f"  - {comp}")
        
        try:
            resp = input("\nRun merge tool to add markdown files to DB now? (y/n): ").strip().lower()
            if resp == "y":
                subprocess.run([sys.executable, "scripts/merge_markdown_db.py"], check=False)
        except Exception:
            pass
    else:
        print("No companies were processed.")

if __name__ == "__main__":
    run()