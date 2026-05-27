from typing import Dict, List, Optional, Tuple, Union
import requests
from bs4 import BeautifulSoup
import logging
import re
import time
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

# Try to import Playwright (optional dependency)
try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
    logger.debug("Playwright is available")
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.debug("Playwright not available, browser mode disabled")


class TextCleaner:
    """Utilities for cleaning obfuscated text"""

    # Zero-width and invisible characters used in obfuscation
    ZERO_WIDTH_CHARS = [
        '\u200B',  # Zero Width Space
        '\u200C',  # Zero Width Non-Joiner
        '\u200D',  # Zero Width Joiner
        '\uFEFF',  # Zero Width No-Break Space (BOM)
        '\u2060',  # Word Joiner
        '\u180E',  # Mongolian Vowel Separator
    ]

    @staticmethod
    def remove_zero_width_chars(text: str) -> str:
        """Remove zero-width characters used for obfuscation"""
        for char in TextCleaner.ZERO_WIDTH_CHARS:
            text = text.replace(char, '')
        return text

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize excessive whitespace while preserving paragraph breaks"""
        # Replace multiple spaces with single space
        text = re.sub(r' +', ' ', text)
        # Replace more than 2 newlines with exactly 2 (paragraph break)
        text = re.sub(r'\n\n+', '\n\n', text)
        # Remove spaces at start/end of lines
        text = '\n'.join(line.strip() for line in text.split('\n'))
        return text.strip()

    @staticmethod
    def clean_text(text: str) -> str:
        """Apply all text cleaning operations"""
        text = TextCleaner.remove_zero_width_chars(text)
        text = TextCleaner.normalize_whitespace(text)
        return text


class BrowserScraper:
    """Handles advanced web scraping using headless browser (Playwright)"""

    # JavaScript that extracts text nodes with their real visual positions via getBoundingClientRect().
    # Returns a list of {text, top, left, height, tag} objects sorted by DOM order;
    # Python sorts by (top, left) to get visual/reading order.
    _JS_VISUAL_ORDER_SCRIPT = """
    (params) => {
        const cssSelectors    = params.cssSelectors    || [];
        const excludeSelectors = params.excludeSelectors || [];
        const skipTags  = new Set(['script','style','nav','footer','header','noscript','iframe']);

        // Resolve containers
        let containers = [];
        if (cssSelectors.length > 0) {
            cssSelectors.forEach(sel => {
                try { document.querySelectorAll(sel).forEach(el => containers.push(el)); } catch(e) {}
            });
        }
        if (containers.length === 0 && document.body) {
            containers = [document.body];
        }

        // Collect excluded element roots
        const excludedRoots = [];
        excludeSelectors.forEach(sel => {
            try { document.querySelectorAll(sel).forEach(el => excludedRoots.push(el)); } catch(e) {}
        });
        function isExcluded(el) {
            for (const root of excludedRoots) {
                if (root === el || root.contains(el)) return true;
            }
            return false;
        }

        const results   = [];
        const seenNodes = new WeakSet();

        containers.forEach(container => {
            // Walk all TEXT nodes inside this container
            const walker = document.createTreeWalker(container, 4 /* SHOW_TEXT */);
            let node;
            while ((node = walker.nextNode())) {
                if (seenNodes.has(node)) continue;
                seenNodes.add(node);

                const text = (node.nodeValue || '').trim();
                if (!text) continue;

                const parent = node.parentElement;
                if (!parent) continue;
                if (isExcluded(parent)) continue;

                const tag = parent.tagName.toLowerCase();
                if (skipTags.has(tag)) continue;

                // Skip hidden elements
                try {
                    const style = window.getComputedStyle(parent);
                    if (style.display === 'none' ||
                        style.visibility === 'hidden' ||
                        parseFloat(style.opacity ?? '1') < 0.01) continue;
                } catch(e) {}

                const rect = parent.getBoundingClientRect();
                // Skip zero-size elements (truly hidden)
                if (rect.width === 0 && rect.height === 0) continue;

                results.push({
                    text:   text,
                    top:    Math.round(rect.top    + window.scrollY),
                    left:   Math.round(rect.left   + window.scrollX),
                    height: Math.round(rect.height),
                    tag:    tag
                });
            }
        });

        return results;
    }
    """

    def __init__(self, wait_for_js: bool = True,
                 use_existing_browser: bool = True, browser_cdp_url: str = 'http://127.0.0.1:9222',
                 remove_overlays: bool = True, timeout: int = 30):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright not installed. Install with: pip install playwright")

        self.wait_for_js = wait_for_js
        self.use_existing_browser = use_existing_browser
        self.browser_cdp_url = browser_cdp_url
        self.remove_overlays = remove_overlays
        self.timeout = timeout * 1000  # Convert to milliseconds
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.playwright = None
        self._owns_browser = True
        self._owns_context = True
        self._using_attached_browser = False

        logger.debug(f"BrowserScraper initialized: wait_js={wait_for_js}, "
                    f"use_existing_browser={use_existing_browser}, cdp_url={browser_cdp_url}, "
                    f"rm_overlays={remove_overlays}, timeout={timeout}s")

    def __enter__(self):
        """Context manager entry - start browser"""
        logger.debug("Starting Playwright browser")
        self.playwright = sync_playwright().start()

        if self.use_existing_browser:
            try:
                logger.info(f"Attaching to existing browser via CDP: {self.browser_cdp_url}")
                self.browser = self.playwright.chromium.connect_over_cdp(self.browser_cdp_url, timeout=self.timeout)
                self._owns_browser = False
                self._using_attached_browser = True

                if self.browser.contexts:
                    self.context = self.browser.contexts[0]
                    self._owns_context = False
                    logger.info("Using existing browser context from attached browser")
                else:
                    self.context = self.browser.new_context()
                    self._owns_context = True
                    logger.info("No existing context found; created a new context on attached browser")

                logger.info("Successfully attached to user-opened browser session")
            except Exception as e:
                logger.error(f"Failed to attach to existing browser at {self.browser_cdp_url}: {e}")
                raise RuntimeError(
                    f"Could not attach to existing browser at {self.browser_cdp_url}. "
                    "Please start Edge with remote debugging enabled using the GUI button."
                ) from e
        else:
            raise RuntimeError(
                "BrowserScraper now requires use_existing_browser=True. "
                "Please open a browser with remote debugging enabled and attach to it."
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup browser"""
        logger.debug("Cleaning up browser")
        if self.context and self._owns_context:
            self.context.close()
        if self.browser and self._owns_browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        logger.debug("Browser cleanup complete")

    def _get_page(self):
        """Get a page for scraping; reuse existing user page when attached via CDP."""
        if self._using_attached_browser and self.context and self.context.pages:
            page = self.context.pages[0]
            logger.debug(f"Reusing existing browser page: {page.url}")
            return page, False

        if not self.context:
            raise RuntimeError("Browser context is not initialized. Use BrowserScraper inside a 'with' statement.")

        page = self.context.new_page()
        return page, True

    def _js_extract_visual_order_text(self, page, css_selectors: list = None,
                                       exclude_selectors: list = None) -> Optional[str]:
        """
        Extract text from the live rendered page in visual (top-to-bottom, left-to-right) order
        by querying real pixel positions via getBoundingClientRect() in the browser.
        Returns reconstructed text, or None if extraction fails.
        """
        try:
            results = page.evaluate(
                self._JS_VISUAL_ORDER_SCRIPT,
                {'cssSelectors': css_selectors or [], 'excludeSelectors': exclude_selectors or []}
            )
        except Exception as e:
            logger.warning(f"JS visual order extraction failed: {e}")
            return None

        if not results:
            logger.debug("JS visual order extraction returned no results")
            return None

        logger.debug(f"JS extracted {len(results)} text nodes for visual ordering")

        # Sort by document Y position (top), then X (left) for multi-column layouts.
        # The JS guarantees 'top' and 'left' are always set; default=0 is a safe
        # fallback that places any hypothetically incomplete entry at the top-left.
        results.sort(key=lambda x: (x.get('top', 0), x.get('left', 0)))

        # Reconstruct paragraphs: group consecutive text nodes that overlap vertically
        # (i.e., belong to the same visual "block"), then separate groups with blank lines.
        paragraphs = []
        current_parts: list = []
        prev_bottom: Optional[float] = None

        for item in results:
            top    = item.get('top', 0)
            height = item.get('height', 20)
            bottom = top + height
            text   = item.get('text', '').strip()
            if not text:
                continue

            # A gap between this element's top and the previous element's bottom
            # indicates a new paragraph (allow 2px tolerance for sub-pixel rounding).
            if prev_bottom is not None and top > prev_bottom + 2:
                if current_parts:
                    paragraphs.append(' '.join(current_parts))
                current_parts = [text]
            else:
                current_parts.append(text)

            # Track the furthest bottom reached so far in this group
            prev_bottom = max(prev_bottom or 0, bottom)

        if current_parts:
            paragraphs.append(' '.join(current_parts))

        result_text = '\n\n'.join(paragraphs).strip()
        logger.debug(f"Visual order reconstruction: {len(paragraphs)} paragraphs, "
                     f"{len(result_text)} characters")
        return result_text if result_text else None

    def scrape_page(self, url: str,
                    visual_order_params: Optional[dict] = None
                    ) -> Union[str, Tuple[str, Optional[str]]]:
        """
        Scrape a single page using the user-opened browser.

        Args:
            url: The URL to scrape.
            visual_order_params: Optional dict with keys ``'css_selectors'`` and
                ``'exclude_selectors'``.  When provided the method **also**
                performs JS-based visual-order text extraction while the page is
                still live and returns a ``(html, visual_text)`` tuple.
                ``visual_text`` is ``None`` when JS extraction produces no
                output; callers should fall back to HTML parsing in that case.
                When *not* provided (the default) the method returns just the
                raw HTML string, preserving the original API contract.
        """
        if not self.context:
            raise RuntimeError("Browser not started. Use 'with BrowserScraper()' context manager")

        logger.debug(f"Browser scraping: {url}")

        page, should_close = self._get_page()

        try:
            # Navigate to page and wait for DOM content
            logger.debug(f"Navigating to {url}")
            page.goto(url, timeout=self.timeout, wait_until='domcontentloaded')

            # Wait for JavaScript content to load
            if self.wait_for_js:
                logger.debug("Waiting for full page load")
                try:
                    page.wait_for_load_state('load', timeout=self.timeout)
                    # Additional wait for JavaScript to execute and render content
                    logger.debug("Waiting for JavaScript content to render (3 seconds)")
                    time.sleep(3)
                except Exception as e:
                    logger.warning(f"Page load timeout: {e}")

            # Remove anti-copy overlays
            if self.remove_overlays:
                logger.debug("Removing overlay elements")
                self._remove_overlays(page)

            # Get page HTML
            logger.debug("Extracting page HTML")
            html = page.content()
            logger.debug(f"Extracted {len(html)} bytes of HTML")

            if visual_order_params is not None:
                logger.debug("Performing JS visual-order text extraction")
                visual_text = self._js_extract_visual_order_text(
                    page,
                    visual_order_params.get('css_selectors'),
                    visual_order_params.get('exclude_selectors'),
                )
                return html, visual_text

            return html

        finally:
            if should_close:
                page.close()

    def _remove_overlays(self, page: Page):
        """Remove anti-copy overlay elements"""
        overlay_script = """
        () => {
            // Remove elements with high z-index (likely overlays)
            const elements = document.querySelectorAll('*');
            elements.forEach(el => {
                const style = window.getComputedStyle(el);
                const zIndex = parseInt(style.zIndex);

                // Remove high z-index overlays
                if (zIndex > 1000) {
                    el.remove();
                }

                // Remove position:fixed/absolute elements that block content
                if ((style.position === 'fixed' || style.position === 'absolute') &&
                    (style.width === '100%' || style.height === '100%')) {
                    // Check if it's transparent or has low opacity
                    const opacity = parseFloat(style.opacity);
                    if (opacity < 0.1) {
                        el.remove();
                    }
                }

                // Remove elements with user-select: none (anti-copy)
                if (style.userSelect === 'none' && el.children.length === 0) {
                    el.style.userSelect = 'auto';
                }
            });

            // Enable text selection globally
            document.body.style.userSelect = 'auto';
            document.body.style.webkitUserSelect = 'auto';
        }
        """
        try:
            page.evaluate(overlay_script)
            logger.debug("Overlay removal script executed")
        except Exception as e:
            logger.warning(f"Failed to remove overlays: {e}")


class WebScraper:
    """Handles web scraping and content extraction"""

    def __init__(self, css_selectors: List[str] = None, use_visual_order: bool = False,
                 wait_for_js: bool = True,
                 use_existing_browser: bool = True, browser_cdp_url: str = 'http://127.0.0.1:9222',
                 remove_overlays: bool = True, browser_timeout: int = 30,
                 exclude_selectors: List[str] = None):
        logger.debug("Initializing WebScraper (browser mode only)")

        # Check if Playwright is available
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed - required for browser scraper")
            raise ImportError(
                "Playwright not installed. Install with: pip install playwright && "
                "python -m playwright install msedge"
            )

        self.css_selectors = css_selectors or []
        self.use_visual_order = use_visual_order
        self.wait_for_js = wait_for_js
        self.use_existing_browser = use_existing_browser
        self.browser_cdp_url = browser_cdp_url
        self.remove_overlays = remove_overlays
        self.browser_timeout = browser_timeout
        self.exclude_selectors = exclude_selectors or []
        self.chapters = []

        logger.debug(f"WebScraper configured: browser mode, "
                    f"{len(self.css_selectors)} selectors, {len(self.exclude_selectors)} exclude selectors, "
                    f"visual_order={use_visual_order}, wait_js={wait_for_js}, "
                    f"use_existing_browser={use_existing_browser}, cdp_url={browser_cdp_url}, "
                    f"timeout={browser_timeout}s")

    def scrape_chapters(self, urls: List[str]) -> List[Dict]:
        """Scrape multiple URLs using browser mode"""
        logger.debug(f"Starting scrape_chapters with {len(urls)} URLs")
        logger.info("Using browser mode for all URLs")
        return self._scrape_chapters_browser(urls)

    def scrape_index_page(self, index_url: str, max_pages: int = 50) -> List[str]:
        """Scrape a book index / table-of-contents page and return chapter URLs in order.

        The method loads *index_url* with a browser (to handle JavaScript-rendered
        chapter lists) and then walks every ``<a href>`` element.  Links that look
        like individual chapter pages are collected; all others are discarded.

        A URL is treated as a chapter link when it:

        * shares the same host as *index_url*, **and**
        * its path contains ``chapter`` (case-insensitive) **or**
          has a numeric segment that follows the book's path prefix.

        If the index spans multiple pages (pagination), the method automatically
        follows "next page" links to collect all chapters.

        Args:
            index_url: URL of the book's chapter-list / index page.
            max_pages: Maximum number of index pages to follow (default: 50).

        Returns:
            Deduplicated list of absolute chapter URLs in the order they appear
            across all index pages.
        """
        logger.info(f"Scraping book index page: {index_url}")
        parsed_index = urlparse(index_url)
        base_url = f"{parsed_index.scheme}://{parsed_index.netloc}"
        host = parsed_index.netloc

        chapter_urls: List[str] = []
        seen_chapters: set = set()
        seen_index_pages: set = set()
        pages_to_visit = [index_url]

        with BrowserScraper(
            self.wait_for_js,
            self.use_existing_browser,
            self.browser_cdp_url,
            self.remove_overlays,
            self.browser_timeout
        ) as browser:
            page_count = 0
            while pages_to_visit and page_count < max_pages:
                current_page_url = pages_to_visit.pop(0)

                # Skip if we've already visited this page
                if current_page_url in seen_index_pages:
                    continue

                seen_index_pages.add(current_page_url)
                page_count += 1

                logger.info(f"Scraping index page {page_count}/{max_pages}: {current_page_url}")
                html = browser.scrape_page(current_page_url)
                soup = BeautifulSoup(html, 'html.parser')

                # Extract chapter URLs and pagination links
                page_chapters, next_page_links = self._extract_chapter_and_pagination_links(
                    soup, current_page_url, base_url, host, parsed_index.path
                )

                # Add newly found chapters
                for chapter_url in page_chapters:
                    if chapter_url not in seen_chapters:
                        seen_chapters.add(chapter_url)
                        chapter_urls.append(chapter_url)

                # Add pagination links to visit queue
                for next_link in next_page_links:
                    if next_link not in seen_index_pages and next_link not in pages_to_visit:
                        pages_to_visit.append(next_link)
                        logger.debug(f"Found pagination link: {next_link}")

        logger.info(f"Found {len(chapter_urls)} chapter URLs across {page_count} index page(s)")
        logger.debug(f"Chapter URLs: {chapter_urls[:5]}{'...' if len(chapter_urls) > 5 else ''}")
        return chapter_urls

    def _extract_chapter_and_pagination_links(self, soup: BeautifulSoup, current_url: str,
                                               base_url: str, host: str, index_path: str) -> Tuple[List[str], List[str]]:
        """Extract chapter links and pagination links from an index page.

        Args:
            soup: BeautifulSoup object of the index page
            current_url: URL of the current index page
            base_url: Base URL of the site
            host: Hostname of the site
            index_path: Path of the original index URL

        Returns:
            Tuple of (chapter_urls, pagination_urls)
        """
        chapter_urls: List[str] = []
        pagination_urls: List[str] = []

        current_parsed = urlparse(current_url)
        index_path_clean = index_path.rstrip('/')

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue

            # Resolve to absolute URL
            if href.startswith('//'):
                href = current_parsed.scheme + ':' + href
            elif href.startswith('/'):
                href = base_url + href
            elif not href.startswith('http'):
                # Relative URL - resolve against current page
                href = urljoin(current_url, href)

            # Must be on the same host
            link_host = urlparse(href).netloc
            if link_host != host:
                continue

            link_path = urlparse(href).path.lower()
            link_text = a_tag.get_text(strip=True).lower()

            # Detect pagination links
            # Common patterns: "next", "next page", page numbers, etc.
            is_pagination = (
                # Link text contains pagination keywords
                any(keyword in link_text for keyword in ['next', 'siguiente', '»', '>', 'page', 'página']) or
                # URL contains page/p parameter
                re.search(r'[?&](page|p)=\d+', href.lower()) or
                # URL path contains /page/N or /p/N pattern
                re.search(r'/(page|p)/\d+', link_path)
            )

            # Detect chapter links
            is_chapter_path = re.search(r'chapter', link_path)
            is_deeper_numeric = (
                re.search(r'/\d+/?$', link_path)
                and link_path.startswith(index_path_clean)
                and link_path != index_path_clean + '/'
            )

            if is_pagination:
                pagination_urls.append(href)
            elif is_chapter_path or is_deeper_numeric:
                chapter_urls.append(href)

        return chapter_urls, pagination_urls

    def _scrape_chapters_browser(self, urls: List[str]) -> List[Dict]:
        """Scrape all URLs using browser mode"""
        with BrowserScraper(
            self.wait_for_js,
            self.use_existing_browser,
            self.browser_cdp_url,
            self.remove_overlays,
            self.browser_timeout
        ) as browser:
            for i, url in enumerate(urls, 1):
                try:
                    logger.debug(f"Processing URL {i}/{len(urls)}")
                    logger.info(f"[{i}/{len(urls)}] Scraping (browser): {url}")
                    chapter = self._scrape_single_browser(url, browser)
                    self.chapters.append(chapter)
                    logger.info(f"✓ Successfully scraped: {url}")
                except Exception as e:
                    logger.error(f"✗ Error scraping {url}: {e}")
                    logger.debug(f"Exception details: {type(e).__name__}: {str(e)}")

        logger.debug(f"scrape_chapters complete: {len(self.chapters)} chapters collected")
        return self.chapters

    def _scrape_single_browser(self, url: str, browser: BrowserScraper) -> Dict:
        """Scrape a single URL using browser"""
        logger.debug(f"Fetching URL (browser): {url}")

        if self.use_visual_order:
            # Pass selector info so the JS extractor can focus on the right containers
            # and skip excluded elements, matching the CSS-selector logic used in
            # _extract_content for the non-visual path.
            visual_params = {
                'css_selectors': self.css_selectors,
                'exclude_selectors': self.exclude_selectors,
            }
            result = browser.scrape_page(url, visual_order_params=visual_params)
            html, visual_text = result  # always a 2-tuple when visual_order_params given

            # Parse the HTML only for title detection
            soup = BeautifulSoup(html, 'html.parser')
            title = self._detect_title(soup)

            if visual_text:
                logger.debug(f"Using JS visual-order text ({len(visual_text)} chars)")
                content = TextCleaner.clean_text(visual_text)
            else:
                # JS extraction failed; fall back to standard BS4 DOM-order extraction
                logger.warning("JS visual-order extraction returned no text; falling back to DOM order")
                content = self._extract_content(soup)
                content = TextCleaner.clean_text(content)

            return {'url': url, 'content': content, 'title': title}

        html = browser.scrape_page(url)
        soup = BeautifulSoup(html, 'html.parser')
        return self._process_soup(soup, url)

    def _process_soup(self, soup: BeautifulSoup, url: str) -> Dict:
        """Process BeautifulSoup object to extract content"""
        # Remove script, style, nav, and footer elements
        logger.debug("Removing script, style, nav, and footer elements")
        removed_count = 0
        for script in soup(['script', 'style', 'nav', 'footer']):
            script.decompose()
            removed_count += 1
        logger.debug(f"Removed {removed_count} unwanted elements")

        # Remove elements matching exclude selectors
        if self.exclude_selectors:
            logger.debug(f"Applying {len(self.exclude_selectors)} exclude selectors")
            for selector in self.exclude_selectors:
                try:
                    elements = soup.select(selector)
                    logger.debug(f"Found {len(elements)} elements matching exclude selector '{selector}'")
                    for elem in elements:
                        elem.decompose()
                        removed_count += 1
                except Exception as e:
                    logger.warning(f"Error applying exclude selector '{selector}': {e}")
            logger.debug(f"Total removed after exclusions: {removed_count} elements")

        # Extract content – use noveldex.io-specific path when appropriate
        if self._is_noveldex_url(url):
            logger.debug("Detected noveldex.io URL – using CSS-order extraction")
            content = self._extract_content_noveldex(soup)
        else:
            logger.debug("Extracting content")
            content = self._extract_content(soup)

        # Clean the extracted text
        logger.debug("Cleaning extracted text")
        content = TextCleaner.clean_text(content)
        logger.debug(f"Content extracted and cleaned: {len(content)} characters")

        logger.debug("Detecting title")
        title = self._detect_title(soup)
        logger.debug(f"Title detected: '{title}'")

        return {
            'url': url,
            'content': content,
            'title': title
        }

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract content using CSS selectors"""
        logger.debug("Starting content extraction")
        content = ''

        if self.css_selectors:
            logger.debug(f"Using {len(self.css_selectors)} CSS selectors")
            for selector in self.css_selectors:
                logger.debug(f"Applying selector: '{selector}'")
                elements = soup.select(selector)
                logger.debug(f"Found {len(elements)} elements matching '{selector}'")
                for elem in elements:
                    if self.use_visual_order:
                        logger.debug("Extracting text in visual order")
                        text = self._extract_text_visual_order(elem)
                    else:
                        logger.debug("Extracting text in DOM order")
                        text = self._extract_text_from_element(elem)
                    if text:
                        logger.debug(f"Added {len(text)} characters from element")
                        content += text + '\n\n'

        # Fallback to body if no selectors matched
        if not content:
            logger.debug("No content from selectors, using fallback to body")
            if self.use_visual_order:
                body = soup.find('body')
                if body:
                    logger.debug("Extracting from body in visual order")
                    content = self._extract_text_visual_order(body)
                else:
                    logger.debug("No body found, extracting all text")
                    content = self._extract_text_from_element(soup)
            else:
                logger.debug("Extracting all text in DOM order")
                content = self._extract_text_from_element(soup)

        logger.debug(f"Content extraction complete: {len(content)} total characters")
        return content

    def _extract_text_from_element(self, element) -> str:
        """Extract text from element, handling fragmented DOM"""
        # For fragmented DOMs (spans within spans), we need deep traversal
        texts = []

        def collect_text(node):
            """Recursively collect text from all nodes"""
            if hasattr(node, 'string') and node.string:
                text = str(node.string).strip()
                if text:
                    texts.append(text)
            elif hasattr(node, 'children'):
                for child in node.children:
                    collect_text(child)

        collect_text(element)

        # Join with spaces and normalize
        result = ' '.join(texts)
        # Convert to paragraphs at block elements
        result = element.get_text(separator='\n', strip=True)
        return result

    def _extract_text_visual_order(self, element) -> str:
        """
        Extract text in visual reading order (top-to-bottom, left-to-right)
        instead of HTML DOM order.

        This uses a heuristic approach based on element types and common patterns.
        For more accurate results, a headless browser with rendering would be needed.
        """
        logger.debug("Starting visual order text extraction")
        # Get all text-bearing leaf elements (elements that contain actual text)
        text_elements = []

        def extract_elements(elem, depth=0):
            """Recursively extract text elements with metadata"""
            if depth > 50:  # Prevent infinite recursion
                return

            # Skip if not a tag element
            if not hasattr(elem, 'name'):
                return

            # Skip non-visible elements
            if elem.name in ['script', 'style', 'nav', 'footer', 'header']:
                return

            # Check if this element has any tag children
            has_element_children = False
            if hasattr(elem, 'children'):
                has_element_children = any(hasattr(child, 'name') for child in elem.children)

            if not has_element_children:
                # This is a leaf element - get all its text
                text = elem.get_text(separator=' ', strip=True)
                if text:
                    # Get positioning hints from element
                    position_hint = self._get_position_hint(elem)
                    text_elements.append({
                        'text': text,
                        'tag': elem.name,
                        'position': position_hint,
                        'depth': depth
                    })
            else:
                # This element has children - recurse into them
                for child in elem.children:
                    if hasattr(child, 'name'):
                        extract_elements(child, depth + 1)

        extract_elements(element)
        logger.debug(f"Extracted {len(text_elements)} text elements")

        # Sort by position hint (top-to-bottom, left-to-right)
        logger.debug("Sorting elements by visual position")
        text_elements.sort(key=lambda x: (x['position']['top'], x['position']['left'], x['depth']))

        # Combine text with appropriate spacing
        logger.debug("Combining text with spacing")
        result = []
        for item in text_elements:
            text = item['text']
            if text:
                # Add extra newline for block-level elements
                if item['tag'] in ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote', 'article', 'section']:
                    result.append(text)
                else:
                    result.append(text)

        final_text = '\n\n'.join(result).strip()
        logger.debug(f"Visual order extraction complete: {len(final_text)} characters")
        return final_text

    # Scaling factor used when converting a CSS 'order' integer to a pixel-range
    # top-position proxy in _get_position_hint().  100 keeps order values well
    # separated while staying in a range comparable to real pixel offsets.
    _CSS_ORDER_SCALE_FACTOR = 100

    @staticmethod
    def _is_noveldex_url(url: str) -> bool:
        """Return True if *url* belongs to noveldex.io (exact hostname match)."""
        try:
            hostname = urlparse(url).hostname or ''
            return hostname == 'noveldex.io' or hostname.endswith('.noveldex.io')
        except Exception:
            return False

    def _extract_content_noveldex(self, soup: BeautifulSoup) -> str:
        """
        Extract chapter content from noveldex.io pages.

        noveldex.io scrambles paragraph order in the DOM and uses the CSS
        ``order`` flexbox property (e.g. ``style="...order: 1;..."``) to set
        the correct visual reading sequence.  This method collects every
        text-bearing leaf element together with its ``order`` value, sorts
        them in ascending order, and returns the reconstructed text.
        """
        logger.debug("Using noveldex.io CSS-order-based extraction")

        # Pick a content container via the configured CSS selectors, or fall
        # back to <body>.
        container = None
        for selector in self.css_selectors:
            try:
                elements = soup.select(selector)
                if elements:
                    container = elements[0]
                    logger.debug(f"noveldex: found container with selector '{selector}'")
                    break
            except Exception as e:
                logger.debug(f"noveldex: selector '{selector}' failed: {e}")
        if container is None:
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

    def _get_position_hint(self, element) -> Dict[str, float]:
        """
        Get position hint for an element based on CSS classes and styles.
        Returns a dict with 'top' and 'left' estimates.

        This is a heuristic approach. For accurate positioning, use Selenium with
        element.location property.
        """
        top = 0.0
        left = 0.0

        # Safety check - only process tag elements
        if not hasattr(element, 'get'):
            return {'top': top, 'left': left}

        # Check for inline styles
        style = element.get('style', '')
        if style:
            # CSS flexbox 'order' property: use as the primary top-position proxy
            # so that visual-order sorting respects noveldex.io-style scrambling.
            m = re.search(r'\border\s*:\s*(-?\d+)', style)
            if m:
                try:
                    top = float(m.group(1)) * self._CSS_ORDER_SCALE_FACTOR
                except ValueError:
                    pass

            # Parse simple top/left values
            if 'top:' in style:
                try:
                    top_val = style.split('top:')[1].split(';')[0].strip()
                    if 'px' in top_val:
                        top = float(top_val.replace('px', ''))
                except:
                    pass

            if 'left:' in style:
                try:
                    left_val = style.split('left:')[1].split(';')[0].strip()
                    if 'px' in left_val:
                        left = float(left_val.replace('px', ''))
                except:
                    pass

        # Check for common positioning classes
        classes = element.get('class', [])
        if isinstance(classes, list):
            class_str = ' '.join(classes)
        else:
            class_str = str(classes)

        # Heuristic: elements with 'right' in class might be on the right
        if 'right' in class_str.lower():
            left += 1000
        elif 'left' in class_str.lower():
            left -= 1000

        # Heuristic: elements with 'top' in class might be higher
        if 'top' in class_str.lower():
            top -= 1000
        elif 'bottom' in class_str.lower():
            top += 1000

        # Use DOM order as fallback for elements at same position
        # This is handled by depth parameter in sorting

        return {'top': top, 'left': left}

    def _detect_title(self, soup: BeautifulSoup) -> str:
        """Auto-detect chapter title"""
        logger.debug("Detecting chapter title")
        for tag in ['h1', 'h2', 'title']:
            logger.debug(f"Checking for <{tag}> element")
            element = soup.find(tag)
            if element:
                title = element.get_text(strip=True)
                logger.debug(f"Found <{tag}> with text: '{title}' (length: {len(title)})")
                if title and len(title) < 200:
                    logger.debug(f"Using title from <{tag}>: '{title}'")
                    return title
        logger.debug("No suitable title found, using default 'Chapter'")
        return 'Chapter'
