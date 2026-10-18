from pipeline.phases.phase_00_fetch.chapter_parser import extract_chapter_urls


def test_learned_rule_extraction_prioritizes_regex_and_orders_numerically():
    index_html = """
    <html><body>
      <a href="/novel/chapter-10/">Ten</a>
      <a href="/novel/chapter-2/">Two</a>
      <a href="/novel/chapter-1/">One</a>
      <a href="/novel/about/">About</a>
      <a href="https://other.com/novel/chapter-3/">Other Domain</a>
    </body></html>
    """

    rules = {
        "learned": True,
        "chapter_regex": r"^/novel/chapter-([0-9]+)/?$",
        "chapter_url_denylist": [],
    }

    urls = extract_chapter_urls(index_html, rules, "https://example.com/novel/")

    assert urls == [
        "https://example.com/novel/chapter-1/",
        "https://example.com/novel/chapter-2/",
        "https://example.com/novel/chapter-10/",
    ]
