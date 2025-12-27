from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import time


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

def fetch_html(driver, url: str) -> str:
    try:
        driver.get(url)
        time.sleep(1.0)
        return driver.page_source
    except Exception as e:
        # Raise a consistent error so callers can handle driver failures gracefully
        raise RuntimeError(f"Driver failed to fetch {url}: {e}") from e