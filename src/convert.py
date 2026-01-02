from __future__ import annotations
from bs4 import BeautifulSoup, Comment, NavigableString
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
    "[role='complementary']",
    ".nav",
    ".navbar",
    ".navigation",
    ".breadcrumb",
    ".breadcrumbs",
    ".cookie",
    ".cookie-banner",
    ".cookie-consent",
    ".cookie-notice",
    ".gdpr",
    ".signup",
    ".subscribe",
    ".newsletter",
    ".sidebar",
    ".side-bar",
    "aside",
    ".advert",
    ".advertisement",
    ".ads",
    ".ad",
    ".promo",
    ".promotion",
    ".share",
    ".social",
    ".social-share",
    ".social-media",
    ".comments",
    ".comment",
    ".site-footer",
    ".site-header",
    ".popup",
    ".modal",
    ".overlay",
    ".menu",
    ".search-form",
    ".search-bar",
    "#search",
    ".related-posts",
    ".related-articles",
    ".author-bio",
    ".tags",
    ".categories",
]

# Regex for class/id names that often indicate non-content elements
BOILERPLATE_CLASS_RE = re.compile(r"\b(sidebar|side-bar|nav|navigation|menu|header|footer|cookie|gdpr|banner|promo|promotion|advert|advertisement|ads?|social|share|subscribe|signup|comment|breadcrumbs?|popup|modal|overlay|search|author-bio|tags|categories|related)\b", re.I)

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
RETAIN_CLASS_RE = re.compile(r"\b(team|press|news|member|staff|profile|about|service|product|feature|benefit|solution|overview|description|content|main|article|post|entry)\b", re.I)


def calculate_text_density(element) -> float:
    """Calculate text density as ratio of text length to tag count.
    
    Higher density indicates more actual content vs. markup/navigation.
    """
    try:
        # Get all text
        text = element.get_text(separator=" ", strip=True)
        text_len = len(text)
        
        if text_len == 0:
            return 0.0
        
        # Count tags
        tag_count = len(element.find_all())
        
        # Avoid division by zero
        if tag_count == 0:
            tag_count = 1
        
        # Calculate density
        density = text_len / tag_count
        
        return density
    except Exception:
        return 0.0


def find_content_by_density(soup, min_density: float = 30.0, min_text_length: int = 200) -> BeautifulSoup | None:
    """Find the main content container by analyzing text density.
    
    Args:
        soup: BeautifulSoup object
        min_density: Minimum text density threshold
        min_text_length: Minimum text length to consider
        
    Returns:
        BeautifulSoup element with highest content density, or None
    """
    try:
        # Common content container tags to check
        content_candidates = []
        
        # Check semantic HTML5 tags first
        for tag in ['main', 'article', '[role="main"]', '.main-content', '#main', '#content', '.content']:
            elements = soup.select(tag)
            for elem in elements:
                text_len = len(elem.get_text(strip=True))
                if text_len >= min_text_length:
                    density = calculate_text_density(elem)
                    content_candidates.append((density, text_len, elem))
        
        # Check divs and sections with high text density
        for elem in soup.find_all(['div', 'section', 'article']):
            text_len = len(elem.get_text(strip=True))
            if text_len >= min_text_length:
                density = calculate_text_density(elem)
                if density >= min_density:
                    content_candidates.append((density, text_len, elem))
        
        # Sort by density (primary) and text length (secondary)
        if content_candidates:
            content_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            return content_candidates[0][2]
        
        return None
    except Exception:
        return None


def extract_main_content_smart(html: str) -> str:
    """Extract main content using multiple strategies with fallbacks.
    
    Strategies (in order):
    1. Readability library (Mozilla's algorithm)
    2. Semantic HTML5 tags (main, article)
    3. Text density analysis
    4. Full HTML (last resort)
    """
    soup = BeautifulSoup(html, "lxml")
    
    # Strategy 1: Try readability first
    try:
        doc = Document(html)
        content = doc.summary(html_partial=True)
        if content and len(content) > 200:
            return content
    except Exception:
        pass
    
    # Strategy 2: Look for semantic HTML5 elements
    try:
        # Try <main> tag
        main_tag = soup.find('main')
        if main_tag:
            text_len = len(main_tag.get_text(strip=True))
            if text_len > 200:
                return str(main_tag)
        
        # Try <article> tag
        article_tag = soup.find('article')
        if article_tag:
            text_len = len(article_tag.get_text(strip=True))
            if text_len > 200:
                return str(article_tag)
        
        # Try role="main"
        role_main = soup.find(attrs={"role": "main"})
        if role_main:
            text_len = len(role_main.get_text(strip=True))
            if text_len > 200:
                return str(role_main)
    except Exception:
        pass
    
    # Strategy 3: Text density analysis
    try:
        content_elem = find_content_by_density(soup, min_density=25.0, min_text_length=150)
        if content_elem:
            return str(content_elem)
    except Exception:
        pass
    
    # Strategy 4: Return full HTML (will be cleaned by clean_html)
    return html


def extract_main_content(html: str) -> str:
    """Readability isolates primary article/content area."""
    doc = Document(html)
    return doc.summary(html_partial=True)


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

    # Use smart content extraction with multiple strategies
    if use_readability:
        try:
            main = extract_main_content_smart(html)
            # Only use extracted content if it's substantial
            if main and len(main) > 200:
                html = main
        except Exception:
            # if extraction fails, continue with the original html
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
        r"^\s*(Share|Share on|Share this)\s*$",
        r"^\s*©.*$",
        r"^\s*All rights reserved\.?$",
        r"^\s*(Privacy|Terms|Contact|Cookies?)\s*$",
        r"^\s*Accept (all )?cookies\s*$",
        r"^\s*Manage (your )?preferences\s*$",
        r"^\s*Learn more\s*$",
        r"^\s*Read more\s*$",
        r"^\s*Close\s*$",
        r"^\s*Menu\s*$",
        r"^\s*Skip to (main )?content\s*$",
        r"^\s*Home\s*$",
        r"^\s*Search\s*$",
        r"^\s*(Open|Close) (menu|navigation)\s*$",
        r"^\s*\[.*?\]\s*$",  # Links like [Home] [About]
        r"^\s*\|+\s*$",  # Separator lines
        r"^\s*[-_=]{3,}\s*$",  # Separator lines
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

    # Remove common image alt text that's navigation
    clean = re.sub(r"!\[(?:Home|Menu|Search|Logo|Icon)\]\([^)]+\)", "", clean, flags=re.I)
    
    # Remove excessive list markers from navigation
    clean = re.sub(r"(\n\s*[\*\-]\s*){5,}", "\n\n", clean)

    # collapse multiple blank lines to a maximum of two
    clean = re.sub(r"\n{3,}", "\n\n", clean)

    # trim leading/trailing whitespace
    clean = clean.strip() + "\n"

    return clean