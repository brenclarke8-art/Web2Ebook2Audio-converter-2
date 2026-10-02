"""
Phase 01 — Source Acquisition Processor

Copilot Instructions:
- Follow Phase 00 processor.py EXACTLY.
- Rewrite source acquisition logic cleanly using legacy code ONLY as reference.
- Do NOT import legacy code.
- Do NOT perform filesystem writes.
- Do NOT perform logging.
- Do NOT perform network calls.
- Do NOT use global state.
- Do NOT introduce side effects.
- All logic must be PURE and DETERMINISTIC.
- Helpers MUST return the full chapter_index and full raw_payloads.
- chapter_range MUST be applied ONLY inside process().
"""

from .input_schema import Phase01Input
from .output_schema import Phase01Output


# ---------------------------------------------------------------------------
# Helper functions — PURE, deterministic, NO chapter_range filtering
# ---------------------------------------------------------------------------

def _load_web_source(source: dict) -> (list, dict):
    raw_items = (
        source.get("chapters")
        or source.get("chapter_items")
        or source.get("items")
        or source.get("pages")
        or None
    )

    if raw_items is None:
        direct = (
            source.get("content")
            or source.get("html")
            or source.get("text")
            or source.get("body")
            or source.get("raw_content")
            or ""
        )
        raw_items = [{
            "title": source.get("title") or "Chapter 1",
            "content": direct,
            "source": source.get("url") or "",
        }]

    chapter_index = []
    raw_payloads = {}

    for index, item in enumerate(raw_items, start=1):
        chapter_id = f"ch{index}"

        if isinstance(item, dict):
            title = (
                item.get("title")
                or item.get("name")
                or item.get("heading")
                or f"Chapter {index}"
            )
            payload = (
                item.get("content")
                or item.get("html")
                or item.get("text")
                or item.get("body")
                or item.get("raw")
                or ""
            )
            source_ref = (
                item.get("source")
                or item.get("url")
                or item.get("href")
                or source.get("url")
                or ""
            )
        elif isinstance(item, str):
            title = item.strip() or f"Chapter {index}"
            payload = item
            source_ref = source.get("url") or ""
        else:
            title = f"Chapter {index}"
            payload = str(item)
            source_ref = source.get("url") or ""

        chapter_index.append({
            "chapter_id": chapter_id,
            "title": title,
            "order": index,
            "source_type": "web",
            "source": source_ref,
        })

        raw_payloads[chapter_id] = payload if isinstance(payload, str) else str(payload)

    return chapter_index, raw_payloads


def _load_epub_source(source: dict) -> (list, dict):
    raw_items = (
        source.get("chapters")
        or source.get("chapter_items")
        or source.get("items")
        or source.get("spine")
        or source.get("pages")
        or None
    )

    if raw_items is None:
        direct = (
            source.get("content")
            or source.get("text")
            or source.get("html")
            or ""
        )
        raw_items = [{
            "title": source.get("title") or "Chapter 1",
            "content": direct,
            "source": source.get("file_path") or "",
        }]

    chapter_index = []
    raw_payloads = {}

    for index, item in enumerate(raw_items, start=1):
        chapter_id = f"ch{index}"

        if isinstance(item, dict):
            title = (
                item.get("title")
                or item.get("name")
                or item.get("heading")
                or f"Chapter {index}"
            )
            payload = (
                item.get("content")
                or item.get("text")
                or item.get("html")
                or item.get("body")
                or ""
            )
            source_ref = (
                item.get("source")
                or item.get("href")
                or item.get("url")
                or source.get("file_path")
                or ""
            )
        elif isinstance(item, str):
            title = item.strip() or f"Chapter {index}"
            payload = item
            source_ref = source.get("file_path") or ""
        else:
            title = f"Chapter {index}"
            payload = str(item)
            source_ref = source.get("file_path") or ""

        chapter_index.append({
            "chapter_id": chapter_id,
            "title": title,
            "order": index,
            "source_type": "epub",
            "source": source_ref,
        })

        raw_payloads[chapter_id] = payload if isinstance(payload, str) else str(payload)

    return chapter_index, raw_payloads


def _load_pdf_source(source: dict) -> (list, dict):
    raw_items = (
        source.get("pages")
        or source.get("chapters")
        or source.get("chapter_items")
        or source.get("items")
        or None
    )

    if raw_items is None:
        direct = (
            source.get("content")
            or source.get("text")
            or source.get("html")
            or ""
        )
        raw_items = [{
            "title": source.get("title") or "Page 1",
            "content": direct,
            "source": source.get("file_path") or "",
        }]

    chapter_index = []
    raw_payloads = {}

    for index, item in enumerate(raw_items, start=1):
        chapter_id = f"ch{index}"

        if isinstance(item, dict):
            title = item.get("title") or item.get("name") or f"Page {index}"
            payload = (
                item.get("content")
                or item.get("text")
                or item.get("html")
                or item.get("body")
                or ""
            )
            source_ref = (
                item.get("source")
                or item.get("url")
                or item.get("path")
                or source.get("file_path")
                or ""
            )
        elif isinstance(item, str):
            title = item.strip() or f"Page {index}"
            payload = item
            source_ref = source.get("file_path") or ""
        else:
            title = f"Page {index}"
            payload = str(item)
            source_ref = source.get("file_path") or ""

        chapter_index.append({
            "chapter_id": chapter_id,
            "title": title,
            "order": index,
            "source_type": "pdf",
            "source": source_ref,
        })

        raw_payloads[chapter_id] = payload if isinstance(payload, str) else str(payload)

    return chapter_index, raw_payloads


def _load_ocr_source(source: dict) -> (list, dict):
    raw_items = (
        source.get("pages")
        or source.get("chapters")
        or source.get("items")
        or source.get("images")
        or None
    )

    if raw_items is None:
        direct = (
            source.get("content")
            or source.get("text")
            or source.get("ocr")
            or source.get("raw")
            or ""
        )
        raw_items = [{
            "title": source.get("title") or "Page 1",
            "content": direct,
            "source": source.get("file_path") or "",
        }]

    chapter_index = []
    raw_payloads = {}

    for index, item in enumerate(raw_items, start=1):
        chapter_id = f"ch{index}"

        if isinstance(item, dict):
            title = item.get("title") or item.get("name") or f"Page {index}"
            payload = (
                item.get("content")
                or item.get("text")
                or item.get("ocr")
                or item.get("raw")
                or item.get("body")
                or ""
            )
            source_ref = (
                item.get("source")
                or item.get("path")
                or source.get("file_path")
                or ""
            )
        elif isinstance(item, str):
            title = item.strip() or f"Page {index}"
            payload = item
            source_ref = source.get("file_path") or ""
        else:
            title = f"Page {index}"
            payload = str(item)
            source_ref = source.get("file_path") or ""

        chapter_index.append({
            "chapter_id": chapter_id,
            "title": title,
            "order": index,
            "source_type": "ocr",
            "source": source_ref,
        })

        raw_payloads[chapter_id] = payload if isinstance(payload, str) else str(payload)

    return chapter_index, raw_payloads


def _load_text_source(source: dict) -> (list, dict):
    raw_items = (
        source.get("chapters")
        or source.get("chapter_items")
        or source.get("pages")
        or source.get("items")
        or None
    )

    if raw_items is None:
        direct = (
            source.get("content")
            or source.get("text")
            or source.get("raw")
            or source.get("body")
            or ""
        )
        raw_items = [{
            "title": source.get("title") or "Chapter 1",
            "content": direct,
            "source": source.get("file_path") or source.get("path") or "",
        }]

    chapter_index = []
    raw_payloads = {}

    for index, item in enumerate(raw_items, start=1):
        chapter_id = f"ch{index}"

        if isinstance(item, dict):
            title = item.get("title") or item.get("name") or f"Chapter {index}"
            payload = (
                item.get("content")
                or item.get("text")
                or item.get("html")
                or item.get("body")
                or item.get("raw")
                or ""
            )
            source_ref = (
                item.get("source")
                or item.get("path")
                or item.get("url")
                or source.get("file_path")
                or ""
            )
        elif isinstance(item, str):
            title = item.strip() or f"Chapter {index}"
            payload = item
            source_ref = source.get("file_path") or source.get("path") or ""
        else:
            title = f"Chapter {index}"
            payload = str(item)
            source_ref = source.get("file_path") or source.get("path") or ""

        chapter_index.append({
            "chapter_id": chapter_id,
            "title": title,
            "order": index,
            "source_type": "text",
            "source": source_ref,
        })

        raw_payloads[chapter_id] = payload if isinstance(payload, str) else str(payload)

    return chapter_index, raw_payloads


# ---------------------------------------------------------------------------
# Main processor — deterministic, chapter_range applied ONLY here
# ---------------------------------------------------------------------------

def process(input_data: Phase01Input) -> Phase01Output:
    source = input_data.source
    source_type = source.get("type")

    # Dispatch
    if source_type == "web":
        chapter_index, raw_payloads = _load_web_source(source)
    elif source_type == "epub":
        chapter_index, raw_payloads = _load_epub_source(source)
    elif source_type == "pdf":
        chapter_index, raw_payloads = _load_pdf_source(source)
    elif source_type == "ocr":
        chapter_index, raw_payloads = _load_ocr_source(source)
    elif source_type == "text":
        chapter_index, raw_payloads = _load_text_source(source)
    else:
        chapter_index, raw_payloads = [], {}

    # Apply chapter_range deterministically (ONLY here)
    chapter_range = source.get("chapter_range")
    if isinstance(chapter_range, (list, tuple)) and len(chapter_range) == 2:
        start_idx, end_idx = chapter_range
        selected_ids = [
            ch["chapter_id"]
            for ch in chapter_index
            if start_idx <= ch["order"] <= end_idx
        ]
        raw_payloads = {
            cid: raw_payloads[cid]
            for cid in selected_ids
            if cid in raw_payloads
        }

    output = Phase01Output(
        chapter_index=chapter_index,
        raw_payloads=raw_payloads,
        meta={
            "phase": "01_source",
            "version": "1.0.0",
            "timestamp": 0.0,
        },
        input_summary={
            "source_type": source_type,
            "source_fields": list(source.keys()),
        },
        output_summary={
            "chapter_count": len(chapter_index),
        },
        errors=[],
        warnings=[],
        timings={"total_ms": 0.0},
    )

    return output
