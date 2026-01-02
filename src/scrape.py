from __future__ import annotations
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


def same_domain(url: str, base: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc

def list_internal_links(driver, base_url: str, max_links: int = 50, allow_external: bool = False) -> list[str]:
    driver.get(base_url)
    time.sleep(1.2)
    soup = BeautifulSoup(driver.page_source, "lxml")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base_url, href)
        if allow_external or same_domain(full, base_url):
            links.add(full)
        if len(links) >= max_links:
            break
    return sorted(links)

def _wait_for_dynamic_content(driver, timeout: float = 3.0) -> None:
    """Wait for dynamic content to load using multiple strategies."""
    try:
        # Wait for common content containers to be present
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        # Short additional wait for AJAX/React to render
        time.sleep(0.5)
    except Exception:
        # If wait fails, continue anyway
        pass

def _scroll_to_load_lazy_content(driver) -> None:
    """Scroll the page to trigger lazy-loaded content."""
    try:
        # Get initial height
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        # Scroll down in chunks to trigger lazy loading
        scroll_pause = 0.3
        scroll_attempts = 0
        max_scrolls = 3  # Limit to 3 scrolls to avoid infinite loops
        
        while scroll_attempts < max_scrolls:
            # Scroll to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause)
            
            # Calculate new height
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scroll_attempts += 1
        
        # Scroll back to top
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.2)
    except Exception:
        # If scrolling fails, continue anyway
        pass

def fetch_html(driver, url: str, wait_for_dynamic: bool = True, scroll_for_lazy: bool = True) -> str:
    """Fetch HTML with improved handling for dynamic and lazy-loaded content.
    
    Args:
        driver: Selenium WebDriver instance
        url: URL to fetch
        wait_for_dynamic: Wait for dynamic content to load (SPAs, AJAX)
        scroll_for_lazy: Scroll to trigger lazy-loaded content
        
    Returns:
        HTML page source
    """
    try:
        driver.get(url)
        
        # Wait for dynamic content
        if wait_for_dynamic:
            _wait_for_dynamic_content(driver)
        else:
            time.sleep(1.0)
        
        # Scroll to load lazy content
        if scroll_for_lazy:
            _scroll_to_load_lazy_content(driver)
        
        return driver.page_source
    except Exception as e:
        # Raise a consistent error so callers can handle driver failures gracefully
        raise RuntimeError(f"Driver failed to fetch {url}: {e}") from e