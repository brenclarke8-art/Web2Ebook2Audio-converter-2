# ebook_app/text/parse/html_cleaner.py
import re
from typing import Optional


# ---------------------------------------------------------------------------
# Structural content extractor (anti-scrape / content-density heuristic)
# ---------------------------------------------------------------------------

# Tags that typically contain the bulk of readable prose
_PROSE_TAGS = {"p", "div", "section", "article", "main", "td"}

# Tags that are almost never the story content
_NOISE_TAGS = {
    "script", "style", "nav", "header", "footer", "aside", "form",
    "button", "select", "input", "textarea", "noscript", "iframe",
    "figure", "figcaption", "picture", "source", "meta", "link",
}

# CSS class/id fragments that strongly suggest UI chrome (not content)
_NOISE_PATTERNS = re.compile(
    r"(nav|menu|sidebar|header|footer|breadcrumb|social|share|comment|"
    r"advert|ads?[-_]|banner|popup|modal|overlay|cookie|widget|toolbar|"
    r"reader[-_]?setting|reader[-_]?control)",
    re.IGNORECASE,
)


def _element_is_noise(tag) -> bool:
    """Return True if a BeautifulSoup tag looks like UI chrome."""
    name = getattr(tag, "name", "") or ""
    if name in _NOISE_TAGS:
        return True
    attrs = getattr(tag, "attrs", None) or {}
    combined = " ".join(
        v if isinstance(v, str) else " ".join(v)
        for v in (attrs.get("class", []), [attrs.get("id", "")])
        if v
    )
    return bool(_NOISE_PATTERNS.search(combined))


def _score_element(tag) -> int:
    """Heuristic content score: paragraph count × average text length."""
    if not hasattr(tag, "find_all"):
        return 0
    paragraphs = tag.find_all("p")
    if not paragraphs:
        # Treat block-level text nodes as implicit paragraphs
        text = tag.get_text(separator=" ", strip=True)
        return len(text)
    total_len = sum(len(p.get_text(strip=True)) for p in paragraphs)
    return len(paragraphs) * (total_len // max(len(paragraphs), 1))


def extract_main_content_by_structure(soup) -> Optional[str]:
    """
    Attempt to identify the main prose block by DOM structure and content
    density rather than fixed CSS selectors.

    Strategy
    --------
    1. Remove obvious noise elements (nav, ads, scripts …).
    2. Walk candidate containers (<article>, <main>, <section>, <div>).
    3. Score each by paragraph count × average paragraph length.
    4. Return the text of the highest-scoring container, or ``None`` if
       nothing looks like content (caller falls back to full-body text).
    """
    from bs4 import BeautifulSoup  # local import — may not always be installed

    # 1. Re-parse from the serialised HTML to get an independent copy
    #    (deepcopy of BeautifulSoup is unreliable due to internal back-refs).
    soup_copy = BeautifulSoup(str(soup), "html.parser")

    for tag in list(soup_copy.find_all(True)):
        if _element_is_noise(tag):
            tag.decompose()

    # 2. Known semantic containers first
    for candidate_tag in ("article", "main"):
        el = soup_copy.find(candidate_tag)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 50:
                return text

    # 3. Score all <div> / <section> containers
    best_score = 0
    best_el = None
    for el in soup_copy.find_all(["div", "section"]):
        if _element_is_noise(el):
            continue
        score = _score_element(el)
        if score > best_score:
            best_score = score
            best_el = el

    if best_el is not None and best_score > 100:
        return best_el.get_text(separator="\n", strip=True)

    return None


class TextCleaner:
    ZERO_WIDTH_CHARS = [
        "\u200B", "\u200C", "\u200D", "\uFEFF",
        "\u2060", "\u180E",
    ]
    CONTROL_TOKENS = {
        "raws",
        "translate",
        "forum",
        "reader settings",
        "text",
        "a−",
        "a-",
        "a+",
        "compact",
        "normal",
        "wide",
        "theme",
        "dark",
        "sepia",
        "light",
        "width",
        "default",
        "tools",
        "bottom",
        "top",
        "reset",
        "report bug",
    }
    MIN_CONTROL_MATCHES = 4

    @staticmethod
    def remove_zero_width_chars(text: str) -> str:
        for char in TextCleaner.ZERO_WIDTH_CHARS:
            text = text.replace(char, "")
        return text

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        text = re.sub(r" +", " ", text)
        text = re.sub(r"\n\n+", "\n\n", text)
        text = "\n".join(line.strip() for line in text.split("\n"))
        return text.strip()

    @staticmethod
    def remove_reader_controls(text: str) -> str:
        lines = text.split("\n")
        normalized_lines = [" ".join(line.strip().lower().split()) for line in lines]
        control_matches = sum(1 for line in normalized_lines if line in TextCleaner.CONTROL_TOKENS)
        if control_matches < TextCleaner.MIN_CONTROL_MATCHES:
            return text
        kept = [line for line, normalized in zip(lines, normalized_lines) if normalized not in TextCleaner.CONTROL_TOKENS]
        return "\n".join(kept)

    @staticmethod
    def clean_text(text: str) -> str:
        return TextCleaner.normalize_whitespace(
            TextCleaner.remove_reader_controls(
                TextCleaner.remove_zero_width_chars(text)
            )
        )
