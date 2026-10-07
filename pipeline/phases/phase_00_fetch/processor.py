import time
from .input_schema import Phase00FetchInput
from .output_schema import Phase00FetchOutput
from .fetcher import fetch_html
from .chapter_parser import (
    load_rules_for_domain,
    extract_chapter_urls,
    extract_title,
    extract_content
)

def process(input_data: Phase00FetchInput) -> Phase00FetchOutput:
    start = time.time()
    warnings = []
    errors = []

    # Fetch index page
    index_html = fetch_html(input_data.index_url)
    if not index_html:
        errors.append(f"Failed to fetch index URL: {input_data.index_url}")
        return Phase00FetchOutput(
            source={},
            meta={"phase": "00_fetch", "version": "1.0.0"},
            input_summary={},
            output_summary={},
            errors=errors,
            warnings=warnings,
            timings={"total_ms": (time.time() - start) * 1000}
        )

    # Load rules
    rules = load_rules_for_domain(input_data.index_url)

    # Extract chapter URLs
    chapter_urls = extract_chapter_urls(index_html, rules)
    if not chapter_urls:
        errors.append("No chapter URLs found.")
        return Phase00FetchOutput(
            source={},
            meta={"phase": "00_fetch", "version": "1.0.0"},
            input_summary={},
            output_summary={},
            errors=errors,
            warnings=warnings,
            timings={"total_ms": (time.time() - start) * 1000}
        )

    # Apply chapter_range
    start_idx, end_idx = input_data.chapter_range
    selected_urls = chapter_urls[start_idx - 1 : end_idx]

    chapters = []
    for url in selected_urls:
        html = fetch_html(url)
        if not html:
            warnings.append(f"Failed to fetch chapter URL: {url}")
            continue

        title = extract_title(html, rules)
        content = extract_content(html, rules)

        chapters.append({
            "title": title,
            "content": content,
            "source": url
        })

    source = {
        "type": "web",
        "url": input_data.index_url,
        "chapters": chapters,
        "chapter_range": input_data.chapter_range
    }

    output = Phase00FetchOutput(
        source=source,
        meta={
            "phase": "00_fetch",
            "version": "1.0.0",
            "timestamp": time.time()
        },
        input_summary={
            "index_url": input_data.index_url,
            "chapter_range": input_data.chapter_range
        },
        output_summary={
            "chapter_count": len(chapters)
        },
        errors=errors,
        warnings=warnings,
        timings={"total_ms": (time.time() - start) * 1000}
    )

    return output
