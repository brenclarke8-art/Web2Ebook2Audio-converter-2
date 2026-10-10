from bs4 import BeautifulSoup
import re
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

RULES_PATH = Path(__file__).parent / "rules" / "scraper_rules.json"

BAD_WORDS = [
    "next", "prev", "previous", "comment", "login",
    "share", "recommend", "toc", "table-of-contents"
]

COMMON_CONTENT_IDS = [
    "content", "chapter-content", "main-content",
    "text", "chapterBody", "chapter-body"
]


def normalize_domain(url: str) -> str:
    """
    Extract domain cleanly:
    - strip www.
    - strip ports
    - strip subdomains only if rules require it
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Remove port
    if ":" in domain:
        domain = domain.split(":")[0]

    # Remove www.
    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def load_rules_for_domain(url: str) -> dict:
    domain = normalize_domain(url)
    if RULES_PATH.exists():
        rules = json.loads(RULES_PATH.read_text())
        return rules.get(domain, {})
    return {}


def extract_chapter_urls(index_html: str, rules: dict, base_url: str) -> list:
    soup = BeautifulSoup(index_html, "html.parser")

    # Rule-based extraction
    if "chapter_list_selector" in rules:
        anchors = soup.select(rules["chapter_list_selector"])
        urls = []
        for a in anchors:
            href = a.get("href")
            if not href:
                continue
            full = urljoin(base_url, href)
            urls.append(full)
        if urls:
            # Deduplicate
            return list(dict.fromkeys(urls))

    # Generic fallback
    urls = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue

        # Filter out junk links
        if any(bad in href.lower() for bad in BAD_WORDS):
            continue

        # Must contain chapter-like pattern
        if "chapter" in href.lower() or re.search(r"\d+", href):
            full = urljoin(base_url, href)
            urls.append(full)

    # Deduplicate
    return list(dict.fromkeys(urls))


def extract_title(html: str, rules: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Rule-based
    if "title_selector" in rules:
        el = soup.select_one(rules["title_selector"])
        if el and el.text.strip():
            return el.text.strip()

    # Generic fallback: h1, h2, title
    for tag in ["h1", "h2", "title"]:
        el = soup.find(tag)
        if el and el.text.strip():
            return el.text.strip()

    # Fallback: first <p>
    first_p = soup.find("p")
    if first_p and first_p.text.strip():
        return first_p.text.strip()

    return "Untitled Chapter"


def extract_content(html: str, rules: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Rule-based
    if "content_selector" in rules:
        el = soup.select_one(rules["content_selector"])
        if el:
            return str(el)

    # Common ID fallback
    for cid in COMMON_CONTENT_IDS:
        el = soup.find(id=cid)
        if el:
            return str(el)

    # Generic fallback: largest text block
    candidates = soup.find_all(["div", "article", "main"])
    if candidates:
        largest = max(candidates, key=lambda c: len(c.get_text(strip=True)))
        return str(largest)

    # Final fallback: raw HTML
    return html
