from bs4 import BeautifulSoup
import re
import json
from pathlib import Path

RULES_PATH = Path(__file__).parent / "rules" / "scraper_rules.json"

def load_rules_for_domain(url: str) -> dict:
    domain = url.split("/")[2]
    if RULES_PATH.exists():
        rules = json.loads(RULES_PATH.read_text())
        return rules.get(domain, {})
    return {}

def extract_chapter_urls(index_html: str, rules: dict) -> list:
    soup = BeautifulSoup(index_html, "html.parser")

    # Rule-based extraction
    if "chapter_list_selector" in rules:
        anchors = soup.select(rules["chapter_list_selector"])
        urls = [a.get("href") for a in anchors if a.get("href")]
        if urls:
            return urls

    # Generic fallback
    urls = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        if "chapter" in href.lower() or re.search(r"\d+", href):
            urls.append(href)

    return urls

def extract_title(html: str, rules: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Rule-based
    if "title_selector" in rules:
        el = soup.select_one(rules["title_selector"])
        if el and el.text.strip():
            return el.text.strip()

    # Generic fallback
    for tag in ["h1", "h2", "title"]:
        el = soup.find(tag)
        if el and el.text.strip():
            return el.text.strip()

    return "Untitled Chapter"

def extract_content(html: str, rules: dict) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Rule-based
    if "content_selector" in rules:
        el = soup.select_one(rules["content_selector"])
        if el:
            return str(el)

    # Generic fallback: largest text block
    candidates = soup.find_all(["div", "article", "main"])
    if candidates:
        largest = max(candidates, key=lambda c: len(c.text))
        return str(largest)

    return html  # fallback to raw HTML
