import time
from urllib.parse import urljoin

from .input_schema import Phase00FetchInput
from .output_schema import Phase00FetchOutput
from .fetcher import fetch_html
from .chapter_parser import (
    load_rules_for_domain,
    extract_chapter_urls,
    extract_title,
    extract_content,
)


def _normalize_url(base_url: str, href: str) -> str:
    if not href:
        return ""
    href = str(href).strip()
    if not href:
        return ""
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(base_url, href)


def _coerce_range(raw_range, total_chapters: int):
    if not raw_range:
        start = 1
        end = total_chapters
    else:
        start, end = raw_range
        start = int(start) if start is not None else 1
        end = int(end) if end is not None else total_chapters

    start = max(1, start)
    end = max(start, end)
    if total_chapters <= 0:
        return 1, 0

    start = min(start, total_chapters)
    end = min(end, total_chapters)
    return start, end


def process(input_data: Phase00FetchInput) -> Phase00FetchOutput:
    start = time.time()
    warnings = []
    errors = []

    index_url = (input_data.index_url or "").strip()
    request_range = list(input_data.chapter_range) if input_data.chapter_range else [1, 1]

    if not index_url:
        errors.append("Index URL is empty.")
        return Phase00FetchOutput(
            source={},
            meta={"phase": "00_fetch", "version": "1.0.0"},
            input_summary={"index_url": index_url, "chapter_range": request_range},
            output_summary={},
            errors=errors,
            warnings=warnings,
            timings={"total_ms": (time.time() - start) * 1000},
        )

    # 1) Fetch index page
    index_html = fetch_html(index_url)
    if not index_html:
        errors.append(f"Failed to fetch index URL: {index_url}")
        return Phase00FetchOutput(
            source={},
            meta={"phase": "00_fetch", "version": "1.0.0"},
            input_summary={"index_url": index_url, "chapter_range": request_range},
            output_summary={},
            errors=errors,
            warnings=warnings,
            timings={"total_ms": (time.time() - start) * 1000},
        )

    # 2) Load rules and extract chapter URLs
    rules = load_rules_for_domain(index_url)
    chapter_urls = extract_chapter_urls(index_html, rules)
    if not chapter_urls:
        errors.append("No chapter URLs found.")
        return Phase00FetchOutput(
            source={},
            meta={"phase": "00_fetch", "version": "1.0.0"},
            input_summary={"index_url": index_url, "chapter_range": request_range},
            output_summary={},
            errors=errors,
            warnings=warnings,
            timings={"total_ms": (time.time() - start) * 1000},
        )

    # 3) Apply range with clamping and warnings
    requested_start, requested_end = request_range
    total_chapters = len(chapter_urls)
    clamped_start, clamped_end = _coerce_range(request_range, total_chapters)

    if requested_start is None or requested_end is None:
        warnings.append("Chapter range was missing values; defaulted to the full chapter list.")
    elif requested_start < 1 or requested_end < 1:
        warnings.append(
            f"Requested chapter range [{requested_start}, {requested_end}] is below 1; "
            f"clamped to [{clamped_start}, {clamped_end}]."
        )
    elif requested_start > total_chapters or requested_end > total_chapters:
        warnings.append(
            f"Requested chapter range [{requested_start}, {requested_end}] exceeds available chapters "
            f"({total_chapters}); clamped to [{clamped_start}, {clamped_end}]."
        )

    selected_urls = chapter_urls[clamped_start - 1:clamped_end]

    # 4) Fetch each selected chapter; skip failures individually
    chapters = []
    for href in selected_urls:
        chapter_url = _normalize_url(index_url, href)
        if not chapter_url:
            warnings.append("Encountered an empty chapter URL; skipped.")
            continue

        chapter_html = fetch_html(chapter_url)
        if not chapter_html:
            warnings.append(f"Failed to fetch chapter URL: {chapter_url}")
            continue

        title = extract_title(chapter_html, rules)
        if not title or not str(title).strip():
            title = "Untitled Chapter"
            warnings.append(f"Title extraction failed for {chapter_url}; used fallback title.")

        content = extract_content(chapter_html, rules)
        if not content:
            warnings.append(f"Content extraction failed for {chapter_url}; skipped chapter.")
            continue

        chapters.append({
            "title": str(title).strip() or "Untitled Chapter",
            "content": content,
            "source": chapter_url,
        })

    if not chapters and selected_urls:
        warnings.append("No valid chapter content could be extracted from the requested range.")

    source = {
        "type": "web",
        "url": index_url,
        "chapters": chapters,
        "chapter_range": [clamped_start, clamped_end],
    }

    output = Phase00FetchOutput(
        source=source,
        meta={
            "phase": "00_fetch",
            "version": "1.0.0",
            "timestamp": time.time(),
        },
        input_summary={
            "index_url": index_url,
            "chapter_range": request_range,
        },
        output_summary={
            "total_available_chapters": total_chapters,
            "requested_range": list(request_range),
            "final_range": [clamped_start, clamped_end],
            "chapter_count": len(chapters),
        },
        errors=errors,
        warnings=warnings,
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
