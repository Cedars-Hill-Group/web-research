# ui_tui.py
from textual.app import App, ComposeResult
from textual.widgets import Static, ListView, ListItem, Label, Log, Footer
from pathlib import Path
import threading
import tempfile
import os
import subprocess
import sys

from .scrape import fetch_html
from .browser import close_driver
from .convert import clean_html, html_to_markdown, html_to_clean_markdown
from .store import (
    company_dirs,
    safe_slug,
    write_html,
    write_markdown,
    default_metadata,
)
import urllib.parse
import traceback


class HybridTUI(App):
    """Interactive TUI for site selection, page marking, preview, and saving."""

    BINDINGS = [
        ("f", "finish", "Save and finish"),
        ("q", "quit", "Quit without saving"),
        ("g", "scrape_here", "Scrape current page"),
        ("l", "list_scraped", "List scraped pages"),
        ("c", "commit_scraped", "Commit scraped pages"),
        ("e", "edit_scraped", "Edit selected scraped item"),
        ("d", "delete_scraped", "Delete selected scraped item"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sites = []
        self.driver = None
        self.company = None
        self.company_focus: str | None = None
        self.company_firm_type: str | None = None
        self.filters = {}
        self.collected_pages = []  # scraped pages collected in-memory per session
        self._lock = threading.Lock()
        # flag set by main when the driver instance is shared across batch mode
        self._shared_driver = False

    def compose(self) -> ComposeResult:
        yield Static("Candidate Sites")
        self.site_list = ListView(id="sites")
        yield self.site_list

        yield Static("Scraped Pages")
        self.scraped_list = ListView(id="scraped")
        yield self.scraped_list

        yield Static("Markdown Preview")
        self.preview = Log(highlight=True, id="preview")
        yield self.preview

        yield Footer()

    def on_mount(self):
        # Populate candidate sites with attached data
        for s in self.sites:
            label_text = f"{s['title']} - {s['link']}"
            item = ListItem(Label(label_text))
            item.data = s
            self.site_list.append(item)

    def on_list_view_selected(self, event: ListView.Selected):
        # User selected a candidate site
        if event.list_view.id == "sites":
            site = event.item.data
            try:
                self.driver.get(site["link"])

                self.company = site["title"].split()[0]
                try:
                    self.notify(f"Opened {site['link']} in browser")
                except Exception:
                    pass
            except Exception as e:
                try:
                    self.notify(f"Failed to open {site['link']}: {e}")
                except Exception:
                    pass
                # Attempt to close and nullify driver to avoid further errors
                try:
                    if not getattr(self, '_shared_driver', False):
                        close_driver(self.driver)
                except Exception:
                    pass
                self.driver = None
                return

        # User selected a marked page
        elif event.list_view.id == "marked":
            page = event.item.data
            url = page["url"]

            try:
                html = fetch_html(self.driver, url)
                md = html_to_clean_markdown(html)

                self.preview.clear()
                self.preview.write(md[:2000])  # preview first 2k chars
            except Exception as e:
                try:
                    self.notify(f"Failed to load preview for {url}: {e}")
                except Exception:
                    pass

        # User selected a scraped page
        elif event.list_view.id == "scraped":
            page = event.item.data
            url = page["url"]

            try:
                md = page.get("md") or html_to_clean_markdown(page.get("html", ""))
                self.preview.clear()
                self.preview.write(md[:2000])
                # Keep track of the selected scraped item index for edit/delete actions
                try:
                    self._current_scraped_index = next(i for i, p in enumerate(self.collected_pages) if p.get('url') == url)
                except Exception:
                    self._current_scraped_index = None
                # also show notes/focus in the preview if present
                n = page.get('notes')
                f = page.get('focus')
                if n:
                    try:
                        self.preview.write('\n\n[Notes]\n')
                        self.preview.write(n[:2000])
                    except Exception:
                        pass
                if f:
                    try:
                        self.preview.write(f"\n\n[Focus] {f}")
                    except Exception:
                        pass
            except Exception as e:
                try:
                    self.notify(f"Failed to load preview for scraped {url}: {e}")
                except Exception:
                    pass







    def action_scrape_here(self):
        """Scrape the currently-open page in the browser and store it in-memory for this session."""
        if not self.driver:
            try:
                self.notify("No browser driver available to scrape the current page")
            except Exception:
                pass
            return

        try:
            url = getattr(self.driver, 'current_url', None)
        except Exception:
            url = None

        # fallback to last navigated url or a placeholder when current_url is not available
        if not url:
            url = getattr(self.driver, 'last_get', None) or 'about:unknown'

        try:
            # prefer current DOM content to avoid extra navigation
            html = getattr(self.driver, 'page_source', None) or self.driver.page_source
        except Exception:
            # fallback: navigate and fetch
            try:
                html = fetch_html(self.driver, url)
            except Exception as e:
                try:
                    self.notify(f"Failed to fetch page for scraping: {e}")
                except Exception:
                    pass
                return

        try:
            md = html_to_clean_markdown(html)
        except Exception:
            md = ''

        page = {
            'url': url,
            'html': html,
            'md': md,
            'date': default_metadata(url, focus=self.company_focus).get('date'),
            'notes': '',
            'saved': False,
        }

        with self._lock:
            self.collected_pages.append(page)
            try:
                item = ListItem(Label(url))
                item.data = page
                self.scraped_list.append(item)
            except Exception:
                pass

        try:
            self.notify(f"Scraped: {url}")
        except Exception:
            pass

    def action_list_scraped(self):
        """List collected scraped pages in the preview pane."""
        with self._lock:
            if not self.collected_pages:
                try:
                    self.notify("No scraped pages in memory")
                except Exception:
                    pass
                return
            self.preview.clear()
            for i, p in enumerate(self.collected_pages, 1):
                line = f"{i}. {p.get('url')} {'(saved)' if p.get('saved') else ''}\n"
                try:
                    self.preview.write(line)
                except Exception:
                    pass

    def edit_scraped_item(self, index: int, notes: str | None = None, focus: str | None = None):
        """Programmatically edit a scraped item by index. Updates notes and focus."""
        with self._lock:
            if index is None or index < 0 or index >= len(self.collected_pages):
                raise IndexError("Invalid scraped item index")
            p = self.collected_pages[index]
            if notes is not None:
                p['notes'] = notes
            if focus is not None:
                p['focus'] = focus

            # Update UI list label if present
            try:
                if getattr(self, 'scraped_list', None):
                    for child in list(self.scraped_list.children):
                        if getattr(child, 'data', None) is p:
                            # update label text if possible
                            try:
                                lbl = getattr(child, 'children', [None])[0]
                                if lbl is not None and hasattr(lbl, 'update'):
                                    label_text = p.get('url')
                                    if p.get('notes'):
                                        label_text += ' - ' + (p.get('notes')[:40])
                                    lbl.update(label_text)
                            except Exception:
                                pass
            except Exception:
                pass

    def action_edit_scraped(self):
        """Interactively edit the currently selected scraped item using $EDITOR (or notepad on Windows)."""
        idx = getattr(self, '_current_scraped_index', None)
        if idx is None:
            try:
                self.notify('No scraped item selected for edit')
            except Exception:
                pass
            return

        with self._lock:
            p = self.collected_pages[idx]
            notes = p.get('notes') or ''
            focus = p.get('focus') or ''

        # create a temp file with simple metadata block for editing
        try:
            tf = tempfile.NamedTemporaryFile('w+', delete=False, suffix='.md')
            try:
                tf.write(f"# Edit notes and focus for {p.get('url')}\n")
                tf.write(f"focus: {focus}\n\n")
                tf.write("---\n\n")
                tf.write(notes)
                tf.flush()
            finally:
                tf.close()

            editor = os.environ.get('EDITOR')
            if not editor:
                if sys.platform.startswith('win'):
                    editor_cmd = ['notepad', tf.name]
                else:
                    editor_cmd = ['vi', tf.name]
            else:
                editor_cmd = [editor, tf.name]

            subprocess.call(editor_cmd)

            # read back edited contents
            with open(tf.name, 'r', encoding='utf-8') as fh:
                content = fh.read()

            # parse simple structure: look for a line 'focus: X' and the rest is notes
            new_focus = None
            new_notes = ''
            for line in content.splitlines():
                if line.startswith('focus:'):
                    new_focus = line.split(':', 1)[1].strip()
            # everything after the first '---' is notes
            if '---' in content:
                parts = content.split('---', 1)
                new_notes = parts[1].strip()
            else:
                # if not present, everything after the header
                lines = content.splitlines()
                # skip first two lines (header + focus)
                new_notes = '\n'.join(lines[2:]).strip()

            # apply edits
            with self._lock:
                if new_focus is not None:
                    p['focus'] = new_focus
                p['notes'] = new_notes

            try:
                self.notify(f"Edited scraped item: {p.get('url')}")
            except Exception:
                pass
        finally:
            try:
                os.unlink(tf.name)
            except Exception:
                pass

    def delete_scraped_item(self, index: int):
        """Programmatically delete a scraped item by index."""
        with self._lock:
            if index is None or index < 0 or index >= len(self.collected_pages):
                raise IndexError('Invalid scraped item index')
            p = self.collected_pages.pop(index)

            # remove UI entry if present
            try:
                if getattr(self, 'scraped_list', None):
                    for child in list(self.scraped_list.children):
                        if getattr(child, 'data', None) is p:
                            try:
                                self.scraped_list.children.remove(child)
                            except Exception:
                                # fallback: try to clear and rebuild list next time
                                pass
            except Exception:
                pass

            try:
                self.notify(f"Deleted scraped: {p.get('url')}")
            except Exception:
                pass

    def action_delete_scraped(self):
        idx = getattr(self, '_current_scraped_index', None)
        if idx is None:
            try:
                self.notify('No scraped item selected for deletion')
            except Exception:
                pass
            return
        try:
            self.delete_scraped_item(idx)
        except Exception as e:
            try:
                self.notify(f'Deletion failed: {e}')
            except Exception:
                pass

    def action_commit_scraped(self):
        """Persist all collected scraped pages to the company's markdown directory as individual files and a combined session file."""
        with self._lock:
            if not self.collected_pages:
                try:
                    self.notify("No scraped pages to commit")
                except Exception:
                    pass
                return

            # determine company to save under
            if self.company:
                save_company = self.company
            else:
                first_url = self.collected_pages[0].get('url') if self.collected_pages else None
                if first_url:
                    parsed = urllib.parse.urlparse(first_url)
                    save_company = (parsed.netloc or 'unknown').split(':')[0].lstrip('www.')
                else:
                    save_company = 'unknown'

            dirs = company_dirs('data/companies', save_company)

            combined_parts = []
            saved = []
            for p in self.collected_pages:
                if p.get('saved'):
                    continue
                slug = safe_slug(p.get('url'))
                try:
                    html_path = write_html(dirs['html'], slug, p.get('html', ''))
                    meta = default_metadata(p.get('url'), focus=self.company_focus, company=save_company, firm_type=self.company_firm_type)
                    md_path = write_markdown(dirs['md'], slug, p.get('md', ''), meta)
                    p['saved'] = True
                    p['html_path'] = str(html_path)
                    p['md_path'] = str(md_path)
                    saved.append((p.get('url'), str(md_path)))
                    combined_parts.append(p.get('md', ''))
                except Exception as e:
                    try:
                        self.notify(f"Failed to save scraped page {p.get('url')}: {e}")
                    except Exception:
                        pass

            # write combined session file
            try:
                from datetime import datetime
                session_slug = f"session-{safe_slug(datetime.utcnow().isoformat(timespec='seconds'))}"
                combined_md = "\n\n---\n\n".join([c for c in combined_parts if c])
                # only create a combined session file if more than one page was saved
                if combined_md and len(combined_parts) > 1:
                    combined_path = write_markdown(dirs['md'], session_slug, combined_md, default_metadata(self.collected_pages[0].get('url'), focus=self.company_focus))
                else:
                    combined_path = None
            except Exception:
                combined_path = None

        if saved:
            try:
                msg = f"Committed {len(saved)} pages"
                if combined_path:
                    msg += f" into {combined_path}"
                self.notify(msg)
            except Exception:
                pass

    def action_save(self):
        """Save all collected scraped pages (backwards-compatible alias for commit)."""
        try:
            self.action_commit_scraped()
        except Exception:
            pass

    def action_finish(self):
        """Save all scraped pages and exit the TUI."""
        try:
            self.action_commit_scraped()
        except Exception:
            pass

        # close driver if present only if this TUI owns it (not shared in batch)
        try:
            if not getattr(self, '_shared_driver', False):
                close_driver(self.driver)
                self.driver = None
        except Exception:
            pass

        # clear global reference to this TUI instance if present
        try:
            import src.main as main_mod
            if getattr(main_mod, 'global_tui', None) is self:
                main_mod.global_tui = None
        except Exception:
            pass

        # give textual a clean exit
        try:
            self.exit()
        except Exception:
            pass

    def action_quit(self):
        """Exit the TUI without saving."""
        # close driver if present only if this TUI owns it (not shared in batch)
        try:
            if not getattr(self, '_shared_driver', False):
                close_driver(self.driver)
                self.driver = None
        except Exception:
            pass

        # clear global reference to this TUI instance if present
        try:
            import src.main as main_mod
            if getattr(main_mod, 'global_tui', None) is self:
                main_mod.global_tui = None
        except Exception:
            pass

        try:
            self.exit()
        except Exception:
            pass

    # Additional lifecycle hooks to ensure driver is closed on various shutdown signals
    def on_unmount(self):
        try:
            if not getattr(self, '_shared_driver', False):
                close_driver(self.driver)
                self.driver = None
        except Exception:
            pass

        # clear global reference if this was the active TUI
        try:
            import src.main as main_mod
            if getattr(main_mod, 'global_tui', None) is self:
                main_mod.global_tui = None
        except Exception:
            pass

    def on_stop(self):
        try:
            if not getattr(self, '_shared_driver', False):
                close_driver(self.driver)
                self.driver = None
        except Exception:
            pass

        # clear global reference if this was the active TUI
        try:
            import src.main as main_mod
            if getattr(main_mod, 'global_tui', None) is self:
                main_mod.global_tui = None
        except Exception:
            pass

    def __del__(self):
        try:
            if not getattr(self, '_shared_driver', False):
                close_driver(getattr(self, 'driver', None))
        except Exception:
            pass
        try:
            import src.main as main_mod
            if getattr(main_mod, 'global_tui', None) is self:
                main_mod.global_tui = None
        except Exception:
            pass