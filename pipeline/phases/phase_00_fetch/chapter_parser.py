from bs4 import BeautifulSoup
import re
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .infer_rules import extract_chapter_number, normalize_domain

RULES_PATH = Path(__file__).parent / "rules" / "scraper_rules.json"

BAD_WORDS = [
    "next", "prev", "previous", "comment", "login",
    "share", "recommend", "toc", "table-of-contents"
]

COMMON_CONTENT_IDS = [
    "content", "chapter-content", "main-content",
    "text", "chapterBody", "chapter-body"
]


def load_rules_for_domain(url: str) -> dict:
    domain = normalize_domain(url)
    if RULES_PATH.exists():
        rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        return rules.get(domain, {})
    return {}


def _path(url: str) -> str:
    return urlparse(url).path


def looks_like_chapter_number(url: str) -> bool:
    parts = _path(url).strip("/").split("/")
    return any(p.isdigit() for p in parts)


def anchor_is_ui(text: str, rules: dict) -> bool:
    t = text.lower().strip()
    deny = rules.get("anchor_denylist", [])
    if len(t.split()) == 1 and any(w in t for w in deny):
        return True
    return False


def parent_is_ignored(a, rules: dict) -> bool:
    ignore = rules.get("ignore_parents", [])
    return a.find_parent(ignore) is not None


def url_matches_regex(url: str, rules: dict) -> bool:
    pattern = rules.get("chapter_url_regex")
    if not pattern:
        return False
    return bool(re.match(pattern, _path(url)))


def url_allowed(url: str, rules: dict) -> bool:
    allow = rules.get("chapter_url_allowlist", [])
    path = _path(url).lower()
    return any(w in path for w in allow)


def url_denied(url: str, rules: dict) -> bool:
    deny = rules.get("chapter_url_denylist", [])
    path = _path(url).lower()
    return any(w in path for w in deny)


def generic_chapter_detection(url: str, rules: dict) -> bool:
    path = _path(url).lower()

    if url_denied(url, rules):
        return False

    if rules.get("use_numeric_fallback", True) and looks_like_chapter_number(url):
        return True

    if rules.get("use_chapter_keyword_fallback", True):
        if "chapter" in path:
            return True

        if re.search(r"(?:^|/)(?:ch|ep|part)[_\-\d/]", path):
            return True

    return False


def _dedupe(urls: list[str]) -> list[str]:
    return list(dict.fromkeys(urls))


def _sort_urls_by_chapter_number(urls: list[str], chapter_regex: str) -> list[str]:
    sortable = []
    unsorted = []

    for url in urls:
        number = extract_chapter_number(url, chapter_regex)
        if number is None:
            unsorted.append(url)
        else:
            sortable.append((number, url))

    ordered = [url for _, url in sorted(sortable, key=lambda item: item[0])]
    return ordered + unsorted


def _extract_by_learned_rule(soup: BeautifulSoup, rules: dict, base_url: str) -> list[str]:
    chapter_regex = rules.get("chapter_regex")
    if not chapter_regex:
        return []

    base_domain = normalize_domain(base_url)
    urls = []

    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue

        full = urljoin(base_url, href)
        if normalize_domain(full) != base_domain:
            continue

        if url_denied(full, rules):
            continue

        if re.search(chapter_regex, _path(full)):
            urls.append(full)

    unique = _dedupe(urls)
    return _sort_urls_by_chapter_number(unique, chapter_regex)


def _extract_by_existing_rule_selector(soup: BeautifulSoup, rules: dict, base_url: str) -> list[str]:
    if "chapter_list_selector" not in rules:
        return []

    anchors = soup.select(rules["chapter_list_selector"])
    urls = []

    for a in anchors:
        href = a.get("href")
        if not href:
            continue

        full = urljoin(base_url, href)
        text = a.get_text(strip=True)

        if anchor_is_ui(text, rules):
            continue

        urls.append(full)

    return _dedupe(urls)


def _extract_with_legacy_fallback(soup: BeautifulSoup, rules: dict, base_url: str) -> list[str]:
    urls = []

    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue

        full = urljoin(base_url, href)
        text = a.get_text(strip=True)

        if anchor_is_ui(text, rules):
            continue

        if parent_is_ignored(a, rules):
            continue

        if url_matches_regex(full, rules):
            urls.append(full)
            continue

        if url_allowed(full, rules):
            urls.append(full)
            continue

        if generic_chapter_detection(full, rules):
            urls.append(full)

    return _dedupe(urls)


def extract_chapter_urls(index_html: str, rules: dict, base_url: str) -> list:
    soup = BeautifulSoup(index_html, "html.parser")

    if rules.get("learned"):
        learned_urls = _extract_by_learned_rule(soup, rules, base_url)
        if learned_urls:
            return learned_urls

    selector_urls = _extract_by_existing_rule_selector(soup, rules, base_url)
    if selector_urls:
        return selector_urls

    return _extract_with_legacy_fallback(soup, rules, base_url)


def extract_title(html: str, rules: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    if "title_selector" in rules:
        el = soup.select_one(rules["title_selector"])
        if el and el.text.strip():
            return el.text.strip()

    for tag in ["h1", "h2", "title"]:
        el = soup.find(tag)
        if el and el.text.strip():
            return el.text.strip()

    first_p = soup.find("p")
    if first_p and first_p.text.strip():
        return first_p.text.strip()

    return "Untitled Chapter"


def extract_content(html: str, rules: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    if "content_selector" in rules:
        el = soup.select_one(rules["content_selector"])
        if el:
            return str(el)

    for cid in COMMON_CONTENT_IDS:
        el = soup.find(id=cid)
        if el:
            return str(el)

    candidates = soup.find_all(["div", "article", "main"])
    if candidates:
        largest = max(candidates, key=lambda c: len(c.get_text(strip=True)))
        return str(largest)

    return html
