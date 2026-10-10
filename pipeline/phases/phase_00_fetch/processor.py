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


def process(input_data: Phase00FetchInput) -> Phase00FetchOutput:
    start = time.time()
    warnings = []
    errors = []

    index_url = (input_data.index_url or "").strip()
    request_range = list(input_data.chapter_range or [1, 1])

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
    index_result = fetch_html(index_url)
    if not index_result["ok"]:
        errors.append(f"Failed to fetch index URL: {index_url} ({index_result['error']})")
        return Phase00FetchOutput(
            source={},
            meta={"phase": "00_fetch", "version": "1.0.0"},
            input_summary={"index_url": index_url, "chapter_range": request_range},
            output_summary={},
            errors=errors,
            warnings=warnings,
            timings={"total_ms": (time.time() - start) * 1000},
        )

    index_html = index_result["html"]

    # 2) Load rules and extract chapter URLs
    rules = load_rules_for_domain(index_url)
    chapter_urls = extract_chapter_urls(index_html, rules, index_url)

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

    # 3) Apply chapter range
    requested_start, requested_end = request_range
    total_chapters = len(chapter_urls)

    start_idx = max(1, min(requested_start, total_chapters))
    end_idx = max(start_idx, min(requested_end, total_chapters))

    selected_urls = chapter_urls[start_idx - 1:end_idx]

    # 4) Fetch chapters
    chapters = []
    for chapter_url in selected_urls:
        result = fetch_html(chapter_url)
        if not result["ok"]:
            warnings.append(f"Failed to fetch chapter URL: {chapter_url} ({result['error']})")
            continue

        html = result["html"]

        title = extract_title(html, rules)
        content = extract_content(html, rules)

        if not content:
            warnings.append(f"Content extraction failed for {chapter_url}; skipped.")
            continue

        chapters.append({
            "title": title or "Untitled Chapter",
            "content": content,
            "source": chapter_url,
        })

    if not chapters and selected_urls:
        warnings.append("No valid chapter content could be extracted from the requested range.")

    source = {
        "type": "web",
        "url": index_url,
        "chapters": chapters,
        "chapter_range": [start_idx, end_idx],
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
            "requested_range": request_range,
            "final_range": [start_idx, end_idx],
            "chapter_count": len(chapters),
        },
        errors=errors,
        warnings=warnings,
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
