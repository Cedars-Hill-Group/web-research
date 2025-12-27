# Archived Tests — Marking UI & Worker

This file documents tests that were archived (skipped) after removing the in-page "mark" widget and background mark worker. These tests are retained for historical context and to make it easy to reintroduce the covered behaviors if the feature is restored.

## Archived tests

- `tests/test_inject_hotkey.py` and `tests/test_inject_hotkey_persistent.py`:
  - Purpose: Verified that the in-page JavaScript hotkey and visible fallback widget were injected into pages and remained active across SPA navigations and DOM mutations.
  - Why archived: The in-page mark UI and hotkey were removed in favor of explicit scraping commands in the TUI (see `src/ui_tui.py` - `action_scrape_here`). These tests would no longer be meaningful against the updated architecture.

- `tests/test_mark_queue_routing.py` and `scripts/test_worker.py`:
  - Purpose: Verified that a background worker and a Flask endpoint accepted posted URLs from pages and routed them into a worker queue for processing.
  - Why archived: The background mark worker and Flask endpoint were removed; marking is now performed explicitly by interacting with the TUI or via programmatic calls to `fetch_html`.

## Reinstating archived tests

If you decide to reintroduce an in-page marking workflow or a background mark worker in the future, these tests can be restored by:

1. Re-enabling the tests (remove the `pytest.skip(...)` call).
2. Ensuring the build/test environment provides the necessary test harness (a test Flask server, a worker queue, and headless browser mocks).

## Related functions to test instead

- `HybridTUI.action_scrape_here` — explicit TUI-driven scraping of the currently-open page.
- `HybridTUI.action_commit_scraped` / `action_save` — commit or save collected scraped pages to disk.
- `src/scrape.fetch_html` — programmatic page fetch for headless or scripted captures.

These functions represent the current, supported capture workflow and should be the focus of new tests.
