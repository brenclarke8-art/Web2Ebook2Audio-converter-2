import time
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from .input_schema import Phase00FetchInput
from .output_schema import Phase00FetchOutput
from .fetcher import fetch_html
from .chapter_parser import (
    load_rules_for_domain,
    extract_chapter_urls,
    extract_title,
    extract_content,
)
from .infer_rules import RuleInferenceError, generate_learned_rule


def _error_output(start: float, index_url: str, chapter_range: list[int], errors: list[str], warnings: list[str]) -> Phase00FetchOutput:
    return Phase00FetchOutput(
        source={},
        meta={"phase": "00_fetch", "version": "1.0.0"},
        input_summary={"index_url": index_url, "chapter_range": chapter_range},
        output_summary={},
        errors=errors,
        warnings=warnings,
        timings={"total_ms": (time.time() - start) * 1000},
    )


def process(input_data: Phase00FetchInput) -> Phase00FetchOutput:
    start = time.time()
    warnings = []
    errors = []

    index_url = (input_data.index_url or "").strip()
    request_range = list(input_data.chapter_range or [1, 1])

    if not index_url:
        errors.append("Index URL is empty.")
        return _error_output(start, index_url, request_range, errors, warnings)

    # 1) Fetch index page
    index_result = fetch_html(index_url)
    if not index_result["ok"]:
        errors.append(f"Failed to fetch index URL: {index_url} ({index_result['error']})")
        return _error_output(start, index_url, request_range, errors, warnings)

    index_html = index_result["html"]

    # 2) Resolve learned rule (if examples provided), then extract chapter URLs
    chapter_examples = [
        (input_data.chapter_example_1 or "").strip(),
        (input_data.chapter_example_2 or "").strip(),
        (input_data.chapter_example_3 or "").strip(),
    ]

    any_examples = any(chapter_examples)
    all_examples = all(chapter_examples)

    if any_examples and not all_examples:
        errors.append("Provide all three chapter example URLs (chapter_example_1, chapter_example_2, chapter_example_3).")
        return _error_output(start, index_url, request_range, errors, warnings)

    learned_rule_domain = None
    learned_rule = None
    learning_debug = None

    if all_examples:
        try:
            learned_rule_domain, learned_rule, learning_debug = generate_learned_rule(
                index_url=index_url,
                chapter_example_1=chapter_examples[0],
                chapter_example_2=chapter_examples[1],
                chapter_example_3=chapter_examples[2],
            )
        except RuleInferenceError as exc:
            errors.append(f"Invalid chapter training data: {exc}")
            return _error_output(start, index_url, request_range, errors, warnings)

    rules = load_rules_for_domain(index_url)
    if learned_rule:
        rules = {**rules, **learned_rule}

    chapter_urls = extract_chapter_urls(index_html, rules, index_url)

    if not chapter_urls:
        errors.append("No chapter URLs found.")
        return _error_output(start, index_url, request_range, errors, warnings)

    # 3) Apply chapter range
    requested_start, requested_end = request_range
    total_chapters = len(chapter_urls)

    start_idx = max(1, min(requested_start, total_chapters))
    end_idx = max(start_idx, min(requested_end, total_chapters))

    selected_urls = chapter_urls[start_idx - 1 : end_idx]

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

        chapters.append(
            {
                "title": title or "Untitled Chapter",
                "content": content,
                "source": chapter_url,
            }
        )

    if not chapters and selected_urls:
        warnings.append("No valid chapter content could be extracted from the requested range.")

    source = {
        "type": "web",
        "url": index_url,
        "chapters": chapters,
        "chapter_range": [start_idx, end_idx],
    }

    meta = {
        "phase": "00_fetch",
        "version": "1.0.0",
        "timestamp": time.time(),
    }

    if learned_rule and learned_rule_domain:
        meta["learned_rule"] = {"domain": learned_rule_domain, "rule": learned_rule}

    if learning_debug:
        meta["learning_debug"] = learning_debug

    output = Phase00FetchOutput(
        source=source,
        meta=meta,
        input_summary={
            "index_url": index_url,
            "chapter_range": request_range,
            "chapter_examples_provided": bool(all_examples),
        },
        output_summary={
            "total_available_chapters": total_chapters,
            "requested_range": request_range,
            "final_range": [start_idx, end_idx],
            "chapter_count": len(chapters),
            "rule_learned": bool(learned_rule),
        },
        errors=errors,
        warnings=warnings,
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
