# main.py
import threading
import time
import yaml
import sys
import subprocess
from flask import Flask


from .browser import get_driver
from .search import search_official_site
from .ui_tui import HybridTUI
import shutil
from datetime import datetime

app = Flask(__name__)
global_tui = None   # holds the active TUI instance


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
            sites = search_official_site(name, max_results=3)

            if not sites:
                print("  No results found. Skipping.")
                continue

            print("\n  Search results:")
            for i, s in enumerate(sites, start=1):
                print(f"  {i}. {s['title']} - {s['link']}")
                print(f"     {s['snippet']}\n")

            if prompt_each:
                choice = input("  Are these results satisfactory? (y/n/q to quit batch): ").strip().lower()
                if choice == "q":
                    print("Exiting batch early.")
                    break
                if choice != "y":
                    print("  Skipping this company.")
                    continue
            else:
                print("  Auto-accepting first result for this company.")

            tui = HybridTUI()
            # ensure shared browser driver is alive before assigning to TUI
            driver = _ensure_driver_alive(driver, cfg["scrape"].get("user_agent"))
            tui.sites = sites
            tui.driver = driver
            tui.company = name
            # indicate that this TUI is sharing the driver provided by the batch loop
            tui._shared_driver = True
            # prompt for focus when running batch (allow blank to skip)
            try:
                focus = input("Enter focus for this company (leave blank to skip): ").strip()
                tui.company_focus = focus or None
            except Exception:
                tui.company_focus = None

            tui.filters = cfg.get("filters", {})

            global_tui = tui

            print("  Launching TUI; press 'g' to scrape the current page, 'c' to commit scraped pages, or 'f' to save and finish this company, then close the TUI to continue batch.")
            tui.run()

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
                        bak = f"companies.csv.bak.{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
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

        sites = search_official_site(company, max_results=3)

        if not sites:
            print("No results found. Try again.")
            continue

        print("\nSearch results:")
        for i, s in enumerate(sites, start=1):
            print(f"{i}. {s['title']} - {s['link']}")
            print(f"   {s['snippet']}\n")

        choice = input("Are these results satisfactory? (y/n/q): ").strip().lower()

        if choice == "y":
            tui = HybridTUI()
            tui.sites = sites
            tui.driver = driver
            tui.company = company
            # prompt for focus for single company
            try:
                focus = input("Enter focus for this company (leave blank to skip): ").strip()
                tui.company_focus = focus or None
            except Exception:
                tui.company_focus = None

            tui.filters = cfg.get("filters", {})

            global_tui = tui
            tui.run()
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