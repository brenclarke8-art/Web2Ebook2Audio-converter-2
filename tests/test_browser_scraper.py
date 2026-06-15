from ebook_app.text.scrape.browser_scraper import BrowserSessionManager, WebScraper


class _FakePage:
    def __init__(self) -> None:
        self.url = ""

    def goto(self, url: str, timeout: int | None = None) -> None:
        self.url = url

    def content(self) -> str:
        return "<html><body><div>content</div></body></html>"

    def title(self) -> str:
        return "Title"


def test_scrape_index_page_scrolls_each_page(monkeypatch) -> None:
    scraper = WebScraper(wait_for_js=False, remove_overlays=False, request_delay=0.0)
    page = _FakePage()
    scroll_calls: list[str] = []

    monkeypatch.setattr(BrowserSessionManager, "get_page", lambda **_: page)
    monkeypatch.setattr(scraper, "_wait_for_index_confirmation", lambda *a, **kw: None)
    monkeypatch.setattr(scraper, "_scroll_to_bottom", lambda p: scroll_calls.append(p.url))

    next_links_by_url = {
        "https://example.com/index": ["https://example.com/index?page=2"],
        "https://example.com/index?page=2": [],
    }

    def _fake_extract_links(_soup, current, *_args):
        return [], next_links_by_url.get(current, [])

    monkeypatch.setattr(scraper, "_extract_links", _fake_extract_links)

    urls = scraper.scrape_index_page("https://example.com/index", max_pages=5)

    assert urls == []
    assert scroll_calls == [
        "https://example.com/index",
        "https://example.com/index?page=2",
    ]


def test_scrape_chapters_scrolls_before_extract(monkeypatch) -> None:
    scraper = WebScraper(wait_for_js=False, remove_overlays=False, request_delay=0.0)
    page = _FakePage()
    scroll_calls: list[str] = []

    monkeypatch.setattr(BrowserSessionManager, "get_page", lambda **_: page)
    monkeypatch.setattr(scraper, "_scroll_to_bottom", lambda p: scroll_calls.append(p.url))
    monkeypatch.setattr(scraper, "_extract_content", lambda _soup: "chapter text")

    results = scraper.scrape_chapters(
        ["https://example.com/ch1", "https://example.com/ch2"]
    )

    assert [result["url"] for result in results] == [
        "https://example.com/ch1",
        "https://example.com/ch2",
    ]
    assert scroll_calls == [
        "https://example.com/ch1",
        "https://example.com/ch2",
    ]
