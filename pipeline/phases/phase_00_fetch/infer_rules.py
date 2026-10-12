import json
import re
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests

RULES_PATH = Path(__file__).parent.parent / "rules" / "scraper_rules.json"

DEFAULT_DENYLIST = [
    "login", "register", "account", "search", "raws",
    "download", "upload", "comment", "share"
]

DEFAULT_IGNORE_PARENTS = ["nav", "header", "footer", "aside"]


def infer_regex_from_paths(p1: str, p2: str) -> str:
    a_parts = p1.strip("/").split("/")
    b_parts = p2.strip("/").split("/")
    out = []

    for ap, bp in zip(a_parts, b_parts):
        if ap.isdigit() and bp.isdigit():
            out.append(r"\d+")
        else:
            out.append(re.escape(ap))

    return "^/" + "/".join(out) + "$"


def infer_selectors_from_index_html(index_html: str, chapter1_url: str):
    soup = BeautifulSoup(index_html, "html.parser")

    # Find anchor matching chapter1_url
    def matches(h):
        if not h:
            return False
        # match relative or absolute
        return chapter1_url.endswith(h) or h in chapter1_url

    a = soup.find("a", href=matches)
    if not a:
        return None

    parent = a.find_parent()
    if not parent:
        return None

    tag = parent.name
    classes = parent.get("class", [])

    if classes:
        return f"{tag}.{classes[0]} a"
    else:
        return f"{tag} a"


def infer_rules_from_urls(index_url: str, chapter1_url: str, chapter2_url: str):
    domain = urlparse(chapter1_url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    p1 = urlparse(chapter1_url).path
    p2 = urlparse(chapter2_url).path

    # Infer regex
    chapter_url_regex = infer_regex_from_paths(p1, p2)

    # Allowlist = stable path segments except numeric
    allowlist = [seg for seg in p1.strip("/").split("/") if not seg.isdigit()]

    # Fallback behavior
    last_segment = p1.strip("/").split("/")[-1]
    use_numeric_fallback = last_segment.isdigit()
    use_keyword_fallback = "chapter" in p1.lower()

    # Fetch index HTML
    try:
        index_html = requests.get(index_url, timeout=10).text
    except Exception:
        index_html = None

    chapter_list_selector = None
    if index_html:
        chapter_list_selector = infer_selectors_from_index_html(index_html, chapter1_url)

    rules = {
        "chapter_url_regex": chapter_url_regex,
        "chapter_url_allowlist": allowlist,
        "chapter_url_denylist": DEFAULT_DENYLIST,
        "anchor_denylist": DEFAULT_DENYLIST,
        "ignore_parents": DEFAULT_IGNORE_PARENTS,
        "use_numeric_fallback": use_numeric_fallback,
        "use_chapter_keyword_fallback": use_keyword_fallback
    }

    if chapter_list_selector:
        rules["chapter_list_selector"] = chapter_list_selector

    return domain, rules


def write_rules_to_json(domain: str, rules: dict):
    if RULES_PATH.exists():
        data = json.loads(RULES_PATH.read_text())
    else:
        data = {}

    data[domain] = rules
    RULES_PATH.write_text(json.dumps(data, indent=2))
    return True


# CLI entrypoint
def generate_rules(index_url: str, chapter1_url: str, chapter2_url: str):
    domain, rules = infer_rules_from_urls(index_url, chapter1_url, chapter2_url)
    write_rules_to_json(domain, rules)
    return domain, rules
