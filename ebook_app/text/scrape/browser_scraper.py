# ebook_app/text/scrape/browser_scraper.py
from __future__ import annotations
import logging
import re
import time
import threading
from typing import List, Dict, Optional, Callable

from urllib.parse import urlparse, urlunparse, urljoin

from .base_scraper import BaseScraper
from .errors import ScraperError
from ebook_app.text.parse.html_cleaner import TextCleaner, extract_main_content_by_structure

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JavaScript injected into the browser page to strip anti-copy overlays,
# re-enable text selection, and remove transparent blocking layers.
# ---------------------------------------------------------------------------
_OVERLAY_REMOVAL_JS = """
() => {
    // Re-enable text selection globally
    const styleEl = document.createElement('style');
    styleEl.id = '__ebook_selection_fix';
    if (!document.getElementById('__ebook_selection_fix')) {
        styleEl.textContent = '* { user-select: text !important; -webkit-user-select: text !important; }';
        document.head.appendChild(styleEl);
    }
    // Remove high-z-index overlays and transparent blocking layers
    document.querySelectorAll('*').forEach(el => {
        const st = window.getComputedStyle(el);
        const zIndex = parseInt(st.zIndex, 10);
        const pos = st.position;
        const opacity = parseFloat(st.opacity);
        const bg = st.backgroundColor;
        const isFixed = pos === 'fixed' || pos === 'absolute';
        const isHighZ = !isNaN(zIndex) && zIndex > 1000;
        const isTransparentOverlay = isFixed && (opacity < 0.05 || bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent');
        if (isHighZ && isTransparentOverlay) {
            el.remove();
        }
        // Also remove common modal/overlay class names with high z-index
        const cls = (el.className || '').toString().toLowerCase();
        if (isHighZ && (cls.includes('overlay') || cls.includes('modal') || cls.includes('popup') || cls.includes('blocker'))) {
            el.remove();
        }
    });
    // Remove elements that block pointer events over the content area
    document.querySelectorAll('[style*="pointer-events"]').forEach(el => {
        el.style.pointerEvents = 'auto';
    });
}
"""

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserSessionManager:
    """Shared visible browser session used by all browser scraping calls."""

    _lock = threading.Lock()
    _playwright = None
    _browser = None
    _page = None
    _open_requests = 0
    _consumed_requests = 0
    _owning_thread_ident: Optional[int] = None

    @classmethod
    def request_open(cls) -> int:
        with cls._lock:
            cls._open_requests += 1
            return cls._open_requests

    @classmethod
    def _session_is_alive_locked(cls) -> bool:
        browser = cls._browser
        page = cls._page
        if browser is None or page is None:
            return False
        try:
            if not browser.is_connected():
                return False
            return not page.is_closed()
        except Exception:
            return False

    @classmethod
    def _cleanup_locked(cls) -> None:
        page = cls._page
        browser = cls._browser
        playwright = cls._playwright
        cls._page = None
        cls._browser = None
        cls._playwright = None
        cls._owning_thread_ident = None
        for closer in (
            getattr(page, "close", None),
            getattr(browser, "close", None),
            getattr(playwright, "stop", None),
        ):
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass

    @classmethod
    def get_page(cls, *, browser_channel: Optional[str] = None):
        if not PLAYWRIGHT_AVAILABLE:
            raise ScraperError("Playwright is not installed")
        with cls._lock:
            if cls._session_is_alive_locked():
                if cls._owning_thread_ident == threading.current_thread().ident:
                    return cls._page
                # The playwright session was created on a thread that has since exited.
                # Playwright's sync API uses greenlets tied to the originating thread, so
                # any call from a different thread raises "cannot switch to a different
                # thread (which happens to have exited)".  Close the stale session and
                # open a fresh one on the current thread without consuming a new open
                # request (the user already authorised one browser session).
                logger.debug(
                    "Browser session was created on a different thread; "
                    "reopening in the current thread."
                )
                cls._cleanup_locked()
                # Do NOT consume an extra open-request token here; the token was already
                # consumed when the original session was opened.
            else:
                cls._cleanup_locked()
                if cls._open_requests <= cls._consumed_requests:
                    raise ScraperError(
                        "Browser session is closed. Click 'Open Browser' in Pipeline, then run indexing again."
                    )
                # Consume the open-request token only when opening a genuinely new session
                # (not when recreating an existing one due to a thread mismatch above).
                cls._consumed_requests = cls._open_requests
            playwright = None
            try:
                playwright = sync_playwright().start()
                browser = playwright.chromium.launch(headless=False, channel=browser_channel)
                page = browser.new_page()
                cls._playwright = playwright
                cls._browser = browser
                cls._page = page
                cls._owning_thread_ident = threading.current_thread().ident
                return page
            except Exception:
                # Ensure any partially-created playwright instance is stopped so that
                # _session_is_alive_locked() correctly returns False on the next call.
                if playwright is not None:
                    try:
                        playwright.stop()
                    except Exception:
                        pass
                cls._cleanup_locked()
                raise


class WebScraper:
    """
    Playwright-based scraper for JS-heavy sites.

    Contract-compliant:
      - scrape_index_page(url, max_pages)
      - scrape_chapters(urls)
    """

    def __init__(
        self,
        *,
        wait_for_js: bool = True,
        remove_overlays: bool = True,
        browser_timeout: int = 30,
        browser_headless: bool = True,
        manual_navigation: bool = False,
        manual_navigation_timeout_sec: int = 120,
        max_index_pages: int = 50,
        browser_channel: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        request_delay: float = 0.5,
        cloudflare_wait: int = 10,
    ):
        self.wait_for_js = wait_for_js
        self.remove_overlays = remove_overlays
        self.browser_timeout = browser_timeout
        self.browser_headless = browser_headless
        self.manual_navigation = manual_navigation
        self.manual_navigation_timeout_sec = manual_navigation_timeout_sec
        self.max_index_pages = max_index_pages
        self.browser_channel = browser_channel
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.request_delay = request_delay
        self.cloudflare_wait = cloudflare_wait

        self._pagination_keywords = {
            "next", "siguiente", "suivant", "continue",
            "older", "more", "page", "pages", ">>", "›", "»"
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_index_page(
        self,
        index_url: str,
        max_pages: int = 50,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[str]:

        if not PLAYWRIGHT_AVAILABLE:
            raise ScraperError("Playwright is not installed")

        effective_max = max_pages if max_pages > 0 else self.max_index_pages

        parsed = urlparse(index_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        host = parsed.netloc
        index_path = parsed.path.rstrip("/")

        chapter_urls: List[str] = []
        seen_chapters: set = set()
        seen_index: set = set()
        queue = [index_url]
        page_num = 0

        # If the index URL itself looks like a specific chapter page (not a TOC/list page),
        # include it as the first chapter so the caller always gets the URL they provided.
        # Heuristic: path contains "chapter" AND the URL has either a query string
        # (e.g. /chapter.php?ch=488) or ends with a numeric segment (e.g. /chapters/1).
        index_path_lower = parsed.path.lower()
        _ends_with_digits = bool(re.search(r"/\d+/?$", parsed.path))
        if "chapter" in index_path_lower and (parsed.query or _ends_with_digits):
            canonical_index = self._canonicalize(index_url)
            seen_chapters.add(canonical_index)
            chapter_urls.append(index_url)

        page = BrowserSessionManager.get_page(browser_channel=self.browser_channel)

        self._wait_for_index_confirmation(
            page,
            index_url=index_url,
            progress_callback=progress_callback,
        )
        start_url = page.url or index_url
        queue = [start_url]

        while queue and page_num < effective_max:
                current = queue.pop(0)
                canonical = self._canonicalize(current)
                if canonical in seen_index:
                    continue
                seen_index.add(canonical)
                page_num += 1

                if progress_callback:
                    progress_callback(f"Scraping index page {page_num}/{effective_max}: {current}")

                try:
                    page.goto(current, timeout=self.browser_timeout * 1000)

                    if self.wait_for_js:
                        page.wait_for_load_state("networkidle")

                    # Handle Cloudflare / anti-scraping challenge pages
                    if self._is_challenge_page(page):
                        logger.info(
                            "Challenge page detected on index %s — waiting up to %ds for resolution.",
                            current, self.cloudflare_wait,
                        )
                        if not self._wait_for_challenge(page, self.cloudflare_wait):
                            logger.warning("Challenge not resolved for index page %s — skipping.", current)
                            continue
                        if self.wait_for_js:
                            try:
                                page.wait_for_load_state("networkidle", timeout=self.browser_timeout * 1000)
                            except Exception:
                                pass

                    if self.remove_overlays:
                        self._remove_overlays(page)

                    self._scroll_to_bottom(page)

                    soup_html = page.content()
                except Exception as exc:
                    logger.warning("Failed to fetch index page %s: %s", current, exc)
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(soup_html, "html.parser")

                chapters, next_pages = self._extract_links(
                    soup, current, base_url, host, index_path
                )

                for ch in chapters:
                    c = self._canonicalize(ch)
                    if c not in seen_chapters:
                        seen_chapters.add(c)
                        chapter_urls.append(ch)

                for np in next_pages:
                    c = self._canonicalize(np)
                    if c not in seen_index:
                        queue.append(np)

                if self.request_delay > 0:
                    time.sleep(self.request_delay)

        logger.info("Browser index scrape complete: %d chapter URLs discovered.", len(chapter_urls))
        return chapter_urls

    def scrape_chapters(
        self,
        urls: List[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Dict[str, str]]:

        if not PLAYWRIGHT_AVAILABLE:
            raise ScraperError("Playwright is not installed")

        results: List[Dict[str, str]] = []
        total = len(urls)

        page = BrowserSessionManager.get_page(browser_channel=self.browser_channel)

        for idx, url in enumerate(urls, start=1):
                if progress_callback:
                    progress_callback(idx, total, url)

                try:
                    page.goto(url, timeout=self.browser_timeout * 1000)

                    if self.wait_for_js:
                        page.wait_for_load_state("networkidle")

                    # Handle Cloudflare / anti-scraping challenge pages
                    if self._is_challenge_page(page):
                        logger.info(
                            "Challenge page detected for chapter %s — waiting up to %ds.",
                            url, self.cloudflare_wait,
                        )
                        if progress_callback:
                            progress_callback(idx, total, f"⚠ Anti-scraping challenge — waiting {self.cloudflare_wait}s… {url}")
                        resolved = self._wait_for_challenge(page, self.cloudflare_wait)
                        if not resolved:
                            # Retry once
                            logger.warning("Challenge not resolved for %s, retrying navigation.", url)
                            try:
                                page.goto(url, timeout=self.browser_timeout * 1000)
                                if self.wait_for_js:
                                    page.wait_for_load_state("networkidle")
                            except Exception:
                                pass
                        elif self.wait_for_js:
                            try:
                                page.wait_for_load_state("networkidle", timeout=self.browser_timeout * 1000)
                            except Exception:
                                pass

                    # Detect unexpected redirect away from the target domain
                    final_url = page.url
                    if self._is_redirected_away(url, final_url):
                        logger.warning(
                            "Redirected away from %s → %s; attempting to navigate back.",
                            url, final_url,
                        )
                        try:
                            page.goto(url, timeout=self.browser_timeout * 1000)
                            if self.wait_for_js:
                                page.wait_for_load_state("networkidle")
                        except Exception:
                            pass

                    if self.remove_overlays:
                        self._remove_overlays(page)

                    self._scroll_to_bottom(page)

                    title = page.title()
                    html = page.content()

                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "html.parser")

                    for tag in soup(["script", "style", "nav", "footer"]):
                        tag.decompose()

                    _netloc = urlparse(url).netloc
                    if _netloc == "noveldex.io" or _netloc.endswith(".noveldex.io"):
                        content = self._extract_content_noveldex(soup)
                    else:
                        content = self._extract_content(soup)

                    results.append({
                        "url": url,
                        "title": title or "Untitled",
                        "content": TextCleaner.clean_text(content),
                    })

                except Exception as exc:
                    logger.error("Browser chapter fetch failed %s: %s", url, exc)
                    results.append({
                        "url": url,
                        "title": "Failed to scrape",
                        "content": "",
                        "error": str(exc),
                    })

                if self.request_delay > 0:
                    time.sleep(self.request_delay)

        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _canonicalize(url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params,
                           parsed.query, parsed.fragment))

    def _extract_links(
        self,
        soup,
        current_url: str,
        base_url: str,
        host: str,
        index_path: str,
    ):
        import re
        chapter_urls = []
        pagination_urls = []

        cur_parsed = urlparse(current_url)

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            # Normalize
            if href.startswith("//"):
                href = cur_parsed.scheme + ":" + href
            elif href.startswith("/"):
                href = base_url + href
            elif not href.startswith("http"):
                href = urljoin(current_url, href)

            if urlparse(href).netloc != host:
                continue

            link_path = urlparse(href).path.lower()
            link_text = a.get_text(strip=True).lower()

            is_pag = (
                any(k in link_text for k in self._pagination_keywords)
                or re.search(r"[?&](page|p)=\d+", href.lower())
                or re.search(r"/(page|p)/\d+", link_path)
                or bool(re.fullmatch(r"\d{1,4}", link_text))
            )

            is_ch = (
                "chapter" in link_path
                or (
                    bool(re.search(r"/\d+/?$", link_path))
                    and link_path.startswith(index_path)
                    and link_path != index_path + "/"
                )
            )

            if is_pag:
                pagination_urls.append(href)
            elif is_ch:
                chapter_urls.append(href)

        return chapter_urls, pagination_urls

    def _extract_content_noveldex(self, soup) -> str:
        """
        Extract chapter content from noveldex.io pages.

        noveldex.io scrambles paragraph order in the DOM and uses the CSS
        ``order`` flexbox property (e.g. ``style="...order: 1;..."``) to set
        the correct visual reading sequence.  This method collects every
        text-bearing leaf element together with its ``order`` value, sorts
        them in ascending order, and returns the reconstructed text.
        """
        logger.debug("Using noveldex.io CSS-order-based extraction")

        container = soup.find('body') or soup
        logger.debug("noveldex: using <body> as content container")

        ordered_elements = []

        def collect(elem, inherited_order: int = 0, has_explicit_order: bool = False) -> None:
            """Walk the subtree; inherit parent order when child has none.

            Only leaf elements that sit within an explicitly-ordered subtree
            (i.e. the element itself or an ancestor has an inline ``order:``
            CSS property) are collected.  This prevents navigation text,
            chapter titles rendered outside the flex-ordered content area, and
            other site chrome from polluting the extracted chapter text.
            """
            if not hasattr(elem, 'name') or elem.name is None:
                return
            if elem.name in ['script', 'style', 'nav', 'footer', 'header', 'noscript']:
                return

            # Parse inline 'order' value if present
            style = elem.get('style', '') or ''
            order_val = inherited_order
            explicit_here = False
            m = re.search(r'\border\s*:\s*(-?\d+)', style)
            if m:
                try:
                    order_val = int(m.group(1))
                    explicit_here = True
                except ValueError:
                    pass

            is_in_ordered_subtree = has_explicit_order or explicit_here

            # Leaf element: collect its text only when inside an ordered subtree
            has_tag_children = any(
                hasattr(child, 'name') and child.name for child in elem.children
            )
            if not has_tag_children:
                text = elem.get_text(strip=True)
                if text and is_in_ordered_subtree:
                    ordered_elements.append({'order': order_val, 'text': text, 'tag': elem.name})
            else:
                for child in elem.children:
                    collect(child, order_val, is_in_ordered_subtree)

        collect(container)
        logger.debug(f"noveldex: collected {len(ordered_elements)} leaf elements (explicitly ordered only)")

        if not ordered_elements:
            logger.debug("noveldex: no ordered elements found; falling back to regular extraction")
            return self._extract_content(soup)

        # Sort ascending by CSS order value → correct reading sequence
        ordered_elements.sort(key=lambda x: x['order'])

        texts = [item['text'] for item in ordered_elements if item['text']]
        result = '\n\n'.join(texts).strip()
        logger.debug(f"noveldex: extraction complete – {len(result)} characters")
        return result

    def _extract_content(self, soup):
        # 1. Structural / content-density heuristic (anti-scrape bypass)
        structural = extract_main_content_by_structure(soup)
        if structural:
            return structural
        # 2. Fallback: full body text
        if soup.body:
            return soup.body.get_text(separator="\n\n", strip=True)
        return soup.get_text(separator="\n\n", strip=True)

    def _remove_overlays(self, page):
        try:
            page.evaluate(_OVERLAY_REMOVAL_JS)
        except Exception as exc:
            logger.debug("Overlay removal failed (non-fatal): %s", exc)

    def _scroll_to_bottom(self, page) -> None:
        max_scroll_attempts = 15
        pause_between_scroll_ms = 150
        try:
            page.evaluate(
                """
                async ([maxScrollAttempts, pauseBetweenScrollMs]) => {
                    const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
                    const getHeight = () => Math.max(
                        document.body ? document.body.scrollHeight : 0,
                        document.documentElement ? document.documentElement.scrollHeight : 0,
                    );
                    let lastHeight = 0;
                    for (let i = 0; i < maxScrollAttempts; i++) {
                        const currentHeight = getHeight();
                        window.scrollTo(0, currentHeight);
                        await sleep(pauseBetweenScrollMs);
                        const nextHeight = getHeight();
                        if (nextHeight <= lastHeight) {
                            break;
                        }
                        lastHeight = nextHeight;
                    }
                }
                """,
                [max_scroll_attempts, pause_between_scroll_ms],
            )
        except Exception as exc:
            logger.debug("Auto-scroll to bottom failed (non-fatal): %s", exc)

    @staticmethod
    def _is_challenge_page(page) -> bool:
        """Return True if the browser is showing an anti-scraping/Cloudflare challenge."""
        try:
            url = (page.url or "").lower()
            title = ""
            try:
                title = (page.title() or "").lower()
            except Exception:
                pass
            indicators = [
                "challenge",
                "cloudflare",
                "checking your browser",
                "ddos-guard",
                "just a moment",
                "cf-challenge",
                "attention required",
                "ray id",
                "security check",
            ]
            return any(ind in url or ind in title for ind in indicators)
        except Exception:
            return False

    def _wait_for_challenge(self, page, wait_sec: int) -> bool:
        """
        Wait up to *wait_sec* seconds for an anti-scraping challenge to resolve.

        Returns True if the challenge page is no longer showing, False if timed out.
        The user can solve the challenge manually in the visible browser window.
        """
        deadline = time.time() + max(1, wait_sec)
        while time.time() < deadline:
            if not self._is_challenge_page(page):
                logger.info("Challenge resolved.")
                return True
            time.sleep(1.0)
        return False

    @staticmethod
    def _is_redirected_away(original_url: str, current_url: str) -> bool:
        """
        Return True if *current_url* is on a completely different host than
        *original_url*, indicating an unexpected redirect (e.g. to a login page
        or anti-bot service on a different domain).
        """
        try:
            orig_host = urlparse(original_url).netloc.lower().split(":")[0]  # strip port
            curr_host = urlparse(current_url).netloc.lower().split(":")[0]
            if not orig_host or not curr_host:
                return False
            orig_parts = orig_host.rsplit(".", 2)
            curr_parts = curr_host.rsplit(".", 2)
            # Only compare root domains when each host has at least two labels
            if len(orig_parts) >= 2 and len(curr_parts) >= 2:
                orig_root = ".".join(orig_parts[-2:])
                curr_root = ".".join(curr_parts[-2:])
                return orig_root != curr_root
            # Fall back to exact host comparison for single-label or unusual hosts
            return orig_host != curr_host
        except Exception:
            return False

    def _wait_for_index_confirmation(
        self,
        page,
        *,
        index_url: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        timeout_sec = max(10, int(self.manual_navigation_timeout_sec))
        if progress_callback:
            progress_callback(
                "Opening browser. Load the correct index page, then click the embedded 'Use This Page' button."
            )

        try:
            page.goto(index_url, timeout=self.browser_timeout * 1000)
        except Exception as exc:
            raise ScraperError(f"Could not open index page in browser: {exc}") from exc

        confirm_js = """
        () => {
            if (window.__ebook_index_confirmed !== true) {
                window.__ebook_index_confirmed = false;
            }
            const existing = document.getElementById('__ebook_index_confirm_btn');
            if (existing) return;
            const button = document.createElement('button');
            button.id = '__ebook_index_confirm_btn';
            button.textContent = 'Use This Page';
            Object.assign(button.style, {
                position: 'fixed',
                top: '12px',
                right: '12px',
                zIndex: '2147483647',
                padding: '10px 14px',
                background: '#2d7ef7',
                color: '#ffffff',
                fontSize: '14px',
                border: '0',
                borderRadius: '6px',
                cursor: 'pointer'
            });
            button.addEventListener('click', () => {
                window.__ebook_index_confirmed = true;
                button.textContent = 'Page Confirmed';
                button.style.background = '#2ea043';
            });
            document.body.appendChild(button);
        }
        """

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                page.evaluate(confirm_js)
                confirmed = page.evaluate("() => window.__ebook_index_confirmed === true")
                if confirmed:
                    return
            except Exception:
                pass
            time.sleep(0.4)

        raise ScraperError(
            "Timed out waiting for browser page confirmation. Open Browser again and click 'Use This Page'."
        )
