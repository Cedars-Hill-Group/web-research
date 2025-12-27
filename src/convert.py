from bs4 import BeautifulSoup, Comment
from readability import Document
import markdownify
import re

# Common selectors/classes/ids that usually indicate boilerplate content
DEFAULT_BOILERPLATE_SELECTORS = [
    "header",
    "footer",
    "nav",
    "[role='banner']",
    "[role='navigation']",
    ".nav",
    ".navbar",
    ".breadcrumb",
    ".breadcrumbs",
    ".cookie",
    ".cookie-banner",
    ".cookie-consent",
    ".signup",
    ".subscribe",
    ".newsletter",
    ".sidebar",
    "aside",
    ".advert",
    ".ads",
    ".promo",
    ".share",
    ".social",
    ".comments",
    ".comment",
    ".site-footer",
    ".site-header",
]

# Regex for class/id names that often indicate non-content elements
BOILERPLATE_CLASS_RE = re.compile(r"\b(sidebar|nav|header|footer|cookie|banner|promo|advert|ads|social|share|subscribe|signup|comment|breadcrumbs?)\b", re.I)

# Defaults for selectors to retain (sections we generally want to keep)
DEFAULT_RETAIN_SELECTORS = [
    "#team",
    "[id*='team']",
    ".team",
    ".team-member",
    ".our-team",
    "#press",
    "[id*='press']",
    ".press",
    ".press-release",
    ".press-releases",
    ".news",
    ".news-item",
]

# Regex to detect classes/ids that indicate content we should retain
RETAIN_CLASS_RE = re.compile(r"\b(team|press|news|member|staff|profile)\b", re.I)


def clean_html(html: str, remove_selectors: list[str] | None = None, collapse_whitespace: bool = True, use_readability: bool = True, retain_selectors: list[str] | None = None) -> str:
    """Clean HTML by optionally extracting the main content and removing boilerplate.

    Args:
        html: raw HTML string
        remove_selectors: optional list of additional CSS selectors to remove
        collapse_whitespace: whether to collapse repeated whitespace in text nodes
        use_readability: whether to try to extract the main content area first
        retain_selectors: optional list of CSS selectors that should be preserved

    Returns:
        cleaned HTML string
    """
    # Keep a copy of original HTML so we can restore small retained sections
    original_html = html

    # Prefer the readability-extracted content when available and enabled
    if use_readability:
        try:
            main = extract_main_content(html)
            # readability can sometimes return tiny fragments; fall back if too small
            if main and len(main) > 200:
                html = main
        except Exception:
            # if readability fails, continue with the original html
            pass

    # parse both original and current HTML so we can bring in retained fragments if needed
    original_soup = BeautifulSoup(original_html, "lxml")
    soup = BeautifulSoup(html, "lxml")

    # Remove comments
    for c in soup.find_all(string=lambda text: isinstance(text, Comment)):
        c.extract()

    # Merge caller-specified selectors with sensible defaults
    selectors = list(DEFAULT_BOILERPLATE_SELECTORS)
    if remove_selectors:
        selectors = list(set(selectors + list(remove_selectors)))

    # Merge retain selectors
    retain = list(DEFAULT_RETAIN_SELECTORS)
    if retain_selectors:
        retain = list(set(retain + list(retain_selectors)))

    # If readability trimmed off large sections, bring in any retained fragments
    try:
        # if the current soup doesn't contain a retain selector but the original does, append it
        for rsel in retain:
            try:
                if not soup.select_one(rsel):
                    for otag in original_soup.select(rsel):
                        # append a copy of the original retained fragment to the body
                        try:
                            copy = BeautifulSoup(str(otag), "lxml")
                            if soup.body:
                                soup.body.append(copy)
                            else:
                                soup.append(copy)
                        except Exception:
                            pass
            except Exception:
                # ignore bad selectors
                pass
    except Exception:
        pass

    def tag_contains_retain(tag):
        """Return True if a tag or any of its descendants looks like content we should keep."""
        # Check tag id/classes directly
        tag_id = tag.get("id", "") or ""
        if RETAIN_CLASS_RE.search(tag_id):
            return True
        for c in tag.get("class") or []:
            if isinstance(c, str) and RETAIN_CLASS_RE.search(c):
                return True
        # Check descendants for id/class matches
        for d in tag.find_all(True):
            if RETAIN_CLASS_RE.search(d.get("id", "") or ""):
                return True
            for c in d.get("class") or []:
                if isinstance(c, str) and RETAIN_CLASS_RE.search(c):
                    return True
        # Also check CSS selectors that might match inside the tag
        try:
            for rsel in retain:
                if tag.select_one(rsel):
                    return True
        except Exception:
            # ignore selector syntax issues
            pass
        return False

    for sel in selectors:
        for tag in list(soup.select(sel)):
            # skip removal if this element contains retained content
            if tag_contains_retain(tag):
                continue
            try:
                tag.decompose()
            except Exception:
                try:
                    tag.extract()
                except Exception:
                    pass

    # Remove elements whose class or id looks like boilerplate (regex match)
    for tag in list(soup.find_all(True)):
        classes = tag.get("class") or []
        tag_id = tag.get("id", "") or ""
        # check each class value
        # skip if tag looks like content to retain
        if tag_contains_retain(tag):
            continue
        if any(BOILERPLATE_CLASS_RE.search(c) for c in classes if isinstance(c, str)) or BOILERPLATE_CLASS_RE.search(tag_id):
            try:
                tag.decompose()
            except Exception:
                try:
                    tag.extract()
                except Exception:
                    pass

    # Optionally collapse whitespace in text nodes
    if collapse_whitespace:
        for t in soup.find_all(text=True):
            # skip large preformatted blocks
            if t.parent and t.parent.name in ("pre", "code"):
                continue
            t.replace_with(" ".join(t.split()))

    return str(soup)

def extract_main_content(html: str) -> str:
    """Readability isolates primary article/content area."""
    doc = Document(html)
    return doc.summary(html_partial=True)


def html_to_markdown(html: str, sanitize: bool = True) -> str:
    """Convert HTML to Markdown and optionally sanitize the result."""
    md = markdownify.markdownify(html, heading_style="ATX", strip=["script", "style"])
    if sanitize:
        md = clean_markdown(md)
    return md


def html_to_clean_markdown(html: str, extra_remove: list[str] | None = None, extra_retain: list[str] | None = None) -> str:
    """Full pipeline: extract main content, remove boilerplate, convert to markdown, and sanitize."""
    cleaned_html = clean_html(html, remove_selectors=extra_remove, collapse_whitespace=True, use_readability=True, retain_selectors=extra_retain)
    return html_to_markdown(cleaned_html, sanitize=True)


# discover_location removed — city/state extraction no longer used per request


def clean_markdown(md: str) -> str:
    """Sanitize markdown by removing common site boilerplate lines and extra whitespace."""
    # Remove common short boilerplate lines (privacy, terms, subscribe, share)
    patterns = [
        r"^\s*Back to top\s*$",
        r"^\s*Subscribe( to)?\s*$",
        r"^\s*Sign up\s*$",
        r"^\s*Follow (us|on)\s*$",
        r"^\s*(Share|Share on)\s*$",
        r"^\s*©.*$",
        r"^\s*All rights reserved\.?$",
        r"^\s*(Privacy|Terms|Contact|Cookies?)\s*$",
    ]

    lines = md.splitlines()
    out_lines = []
    for ln in lines:
        skip = False
        for p in patterns:
            if re.search(p, ln, re.I):
                skip = True
                break
        if skip:
            continue
        # drop lines that are extremely short and not likely to be content
        if len(ln.strip()) < 10 and re.match(r"^[^a-zA-Z0-9]*$", ln.strip() or ""):
            continue
        out_lines.append(ln.rstrip())

    clean = "\n".join(out_lines)

    # collapse multiple blank lines to a maximum of two
    clean = re.sub(r"\n{3,}", "\n\n", clean)

    # trim leading/trailing whitespace
    clean = clean.strip() + "\n"

    return clean