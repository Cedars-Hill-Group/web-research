# main.py
import threading
import time
import yaml
import sys
import subprocess
from flask import Flask
from datetime import datetime, UTC


from .browser import get_driver
from .search import search_official_site
from .ui_tui import HybridTUI
from .store import company_dirs, write_markdown, default_metadata, safe_slug
import shutil
from pathlib import Path

app = Flask(__name__)
global_tui = None   # holds the active TUI instance


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
            source=source or None
        )
        
        # Write markdown file with the content/notes
        slug = safe_slug(f"{company_name}-manual")
        write_markdown(dirs['md'], slug, content, meta)
        
        print(f"✓ Successfully saved {company_name} to database.")
        return True
    except Exception as e:
        print(f"✗ Error saving to database: {e}")
        return False


def save_company_metadata_if_no_scraping(company_name: str, focus: str | None = None, firm_type: str | None = None, source: str | None = None) -> bool:
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
    if not (focus or firm_type or source):
        return False
    
    try:
        dirs = company_dirs('data/companies', company_name)
        meta = default_metadata(
            website="",
            focus=focus,
            firm_type=firm_type,
            source=source
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

    # Choose input mode: single or batch
    mode = input("Choose input mode - (1) Single company, (2) Batch from companies.csv: ").strip()
    if mode == "2":
        # Batch mode
        import csv
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
                source = input("Enter source for this company (leave blank to skip): ").strip()
                
                # Update TUI instance for any future commits
                tui.company_focus = focus or None
                tui.company_firm_type = firm_type or None
                tui.company_source = source or None
                
                # Check if any pages were scraped
                pages_scraped = len(tui.collected_pages) > 0
                
                # Update already-saved markdown files if values were provided
                if focus or firm_type or source:
                    from pathlib import Path
                    from .store import company_dirs, safe_slug, update_metadata_in_files
                    dirs = company_dirs('data/companies', name)
                    updates = {}
                    if focus:
                        updates['focus'] = focus
                    if firm_type:
                        updates['firm_type'] = firm_type
                    if source:
                        updates['source'] = source
                    count = update_metadata_in_files(dirs['md'], updates)
                    if count > 0:
                        print(f"  Updated metadata in {count} file(s).")
                    
                    # If no pages were scraped but metadata was provided, create a metadata-only entry
                    if not pages_scraped:
                        if save_company_metadata_if_no_scraping(name, focus or None, firm_type or None, source or None):
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
                        bak = f"companies.csv.bak.{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
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

    # Single mode fallback
    while True:
        company = input("Enter company name (or 'q' to quit): ").strip()
        if company.lower() == "q":
            print("Exiting.")
            return

        # Search results loop - allow user to request more results
        start_index = 1
        sites = []
        
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
                    print("\nOkay, let's continue.\n")
                else:
                    print("\nOkay, let's try again.\n")
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
                print("Exiting.")
                return
            
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

            tui.filters = cfg.get("filters", {})

            global_tui = tui
            tui.run()

            # prompt for focus, firm_type, and source after scraping is complete
            try:
                focus = input("Enter focus for this company (leave blank to skip): ").strip()
                firm_type = input("Enter firm type for this company (leave blank to skip): ").strip()
                source = input("Enter source for this company (leave blank to skip): ").strip()
                
                # Update TUI instance
                tui.company_focus = focus or None
                tui.company_firm_type = firm_type or None
                tui.company_source = source or None
                
                # Check if any pages were scraped
                pages_scraped = len(tui.collected_pages) > 0
                
                # Update already-saved markdown files if values were provided
                if focus or firm_type or source:
                    from pathlib import Path
                    from .store import company_dirs, safe_slug, update_metadata_in_files
                    dirs = company_dirs('data/companies', company)
                    updates = {}
                    if focus:
                        updates['focus'] = focus
                    if firm_type:
                        updates['firm_type'] = firm_type
                    if source:
                        updates['source'] = source
                    count = update_metadata_in_files(dirs['md'], updates)
                    if count > 0:
                        print(f"Updated metadata in {count} file(s).")
                    
                    # If no pages were scraped but metadata was provided, create a metadata-only entry
                    if not pages_scraped:
                        if save_company_metadata_if_no_scraping(company, focus or None, firm_type or None, source or None):
                            pass  # Success message already printed
            except Exception as e:
                print(f"Error updating metadata: {e}")

            # close the shared driver now that the interactive session ended
            try:
                from .browser import close_driver
                close_driver(driver)
                print("Browser closed.")
            except Exception:
                pass

            # offer to run the merge tool for any newly scraped markdown
            try:
                resp = input("Run merge tool to add markdown files to DB now? (y/n): ").strip().lower()
                if resp == "y":
                    subprocess.run([sys.executable, "scripts/merge_markdown_db.py"], check=False)
            except Exception:
                pass
            break

        elif choice == "n":
            print("\nOkay, let's try again.\n")
            continue

        elif choice == "q":
            print("Exiting.")
            return

        else:
            print("Invalid input. Returning to company prompt.\n")

if __name__ == "__main__":
    run()