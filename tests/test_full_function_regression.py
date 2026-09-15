from __future__ import annotations

from pathlib import Path

from audio_render.tts_service_launcher import resolve_tts_service_python
from scrape_clean.browser_scraper import BrowserSessionManager, WebScraper


class _FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"

    def goto(self, url: str, timeout: int | None = None) -> None:
        self.url = url

    def wait_for_load_state(self, *_args, **_kwargs) -> None:
        return

    def content(self) -> str:
        return (
            "<html><body>"
            "<a href='https://example.com/novel/chapter-1'>Chapter 1</a>"
            "</body></html>"
        )


def test_full_function_manual_index_scan_and_tts_startup_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy_venv_python = tmp_path / "tts_service" / "venv_tts" / "bin" / "python"
    legacy_venv_python.parent.mkdir(parents=True, exist_ok=True)
    legacy_venv_python.write_text("", encoding="utf-8")
    monkeypatch.delenv("EBOOK_AUDIO_STUDIO_TTS_PYTHON", raising=False)

    resolved = resolve_tts_service_python(
        repo_root=tmp_path,
        current_python="/usr/bin/current-python",
    )
    assert resolved == legacy_venv_python.resolve()

    scraper = WebScraper(wait_for_js=False, remove_overlays=False, request_delay=0.0)
    page = _FakePage()

    monkeypatch.setattr(BrowserSessionManager, "get_page", lambda **_: page)
    monkeypatch.setattr(
        scraper,
        "_wait_for_index_confirmation",
        lambda _page, **_kwargs: setattr(_page, "url", "https://example.com/novel/index"),
    )
    monkeypatch.setattr(scraper, "_scroll_to_bottom", lambda _page: None)

    chapter_urls = scraper.scrape_index_page("about:blank", max_pages=1)

    assert chapter_urls == ["https://example.com/novel/chapter-1"]
