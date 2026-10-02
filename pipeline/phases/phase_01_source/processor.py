"""
Phase 01 — Source Acquisition Processor

Copilot Instructions:
- Follow Phase 00 processor.py EXACTLY.
- Rewrite source acquisition logic cleanly using legacy code ONLY as reference:
    legacy/ebook_app/text/*
    legacy/ebook_app/scrape/*
    legacy/ebook_app/parse/*
    legacy/ebook_app/epub/*
    legacy/ebook_app/pdf/*
    legacy/ebook_app/ocr/*
- Do NOT import legacy code.
- Do NOT perform filesystem writes.
- Do NOT perform logging.
- Do NOT perform network calls.
- Do NOT use global state.
- Do NOT introduce side effects.
- All logic must be PURE and DETERMINISTIC.
- Implement source-type dispatch inside process().
- Implement helper functions for each source type and let Copilot fill them in.
"""

import time
from .input_schema import Phase01Input
from .output_schema import Phase01Output


# ---------------------------------------------------------------------------
# Helper stubs Copilot will fill in using legacy code as reference
# ---------------------------------------------------------------------------

def _load_web_source(source: dict) -> (list, dict):
    """Extract raw chapter HTML/text for a web source while retaining the full chapter list."""
    raw_items = source.get("chapters")
    if raw_items is None:
        raw_items = source.get("chapter_items")
    if raw_items is None:
        raw_items = source.get("items")
    if raw_items is None:
        raw_items = source.get("pages")

    if raw_items is None:
        has_direct_content = any(
            source.get(key) is not None
            for key in ("content", "html", "text", "body", "raw_content")
        )
        if has_direct_content:
            raw_items = [{
                "title": source.get("title") or "Chapter 1",
                "content": source.get("content") or source.get("html") or source.get("text") or source.get("body") or source.get("raw_content") or "",
                "source": source.get("url") or "",
            }]
        else:
            raw_items = []

    def parse_selection(value):
        if value in (None, "", [], {}):
            return None
        if isinstance(value, int):
            return {value}
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if "-" in value:
                pieces = value.split("-")
                if len(pieces) == 2:
                    s = pieces[0].strip().lower().replace("ch", "")
                    e = pieces[1].strip().lower().replace("ch", "")
                    try:
                        start = max(1, int(s))
                        end = max(start, int(e))
                        return set(range(start, end + 1))
                    except ValueError:
                        return None
            if "," in value:
                selected = set()
                for piece in value.split(","):
                    try:
                        selected.add(int(piece.strip().replace("ch", "")))
                    except ValueError:
                        pass
                return selected or None
            try:
                return {int(value.replace("ch", ""))}
            except ValueError:
                return None
        if isinstance(value, (list, tuple, set)):
            selected = set()
            for item in value:
                if isinstance(item, int):
                    selected.add(item)
                elif isinstance(item, str):
                    try:
                        selected.add(int(item.replace("ch", "")))
                    except ValueError:
                        pass
            return selected or None
        if isinstance(value, dict):
            start = value.get("start", value.get("min"))
            end = value.get("end", value.get("max"))
            if start is None and end is None:
                return None
            start_num = 1 if start is None else int(start)
            end_num = start_num if end is None else int(end)
            return set(range(max(1, start_num), max(start_num, end_num) + 1))
        return None

    selected = parse_selection(source.get("chapter_range"))
    chapter_index = []
    raw_payloads = {}

    for index, item in enumerate(raw_items, start=1):
        chapter_id = f"ch{index}"
        if isinstance(item, dict):
            title = item.get("title") or item.get("name") or item.get("heading") or f"Chapter {index}"
            payload = (
                item.get("content")
                or item.get("html")
                or item.get("text")
                or item.get("body")
                or item.get("raw")
                or ""
            )
            source_ref = item.get("source") or item.get("url") or item.get("href") or source.get("url") or ""
        elif isinstance(item, str):
            title = item if item.strip() else f"Chapter {index}"
            payload = item
            source_ref = source.get("url") or ""
        else:
            title = f"Chapter {index}"
            payload = str(item)
            source_ref = source.get("url") or ""

        chapter_index.append({
            "chapter_id": chapter_id,
            "title": title,
            "source_type": "web",
            "source": source_ref,
        })

        if selected is None or index in selected:
            raw_payloads[chapter_id] = payload if isinstance(payload, str) else str(payload)

    return chapter_index, raw_payloads


def _load_epub_source(source: dict) -> (list, dict):
    """Extract raw EPUB chapter text while preserving the full chapter index."""
    raw_items = source.get("chapters")
    if raw_items is None:
        raw_items = source.get("chapter_items")
    if raw_items is None:
        raw_items = source.get("items")
    if raw_items is None:
        raw_items = source.get("spine")
    if raw_items is None:
        raw_items = source.get("pages")
    if raw_items is None:
        direct = source.get("content") or source.get("text") or source.get("html") or ""
        raw_items = [{"title": source.get("title") or "Chapter 1", "content": direct, "source": source.get("file_path") or ""}]

    def parse_selection(value):
        if value in (None, "", [], {}):
            return None
        if isinstance(value, int):
            return {value}
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if "-" in value:
                pieces = value.split("-")
                if len(pieces) == 2:
                    try:
                        start = max(1, int(pieces[0].strip().replace("ch", "")))
                        end = max(start, int(pieces[1].strip().replace("ch", "")))
                        return set(range(start, end + 1))
                    except ValueError:
                        return None
            if "," in value:
                selected = set()
                for piece in value.split(","):
                    try:
                        selected.add(int(piece.strip().replace("ch", "")))
                    except ValueError:
                        pass
                return selected or None
            try:
                return {int(value.replace("ch", ""))}
            except ValueError:
                return None
        if isinstance(value, (list, tuple, set)):
            selected = set()
            for item in value:
                if isinstance(item, int):
                    selected.add(item)
                elif isinstance(item, str):
                    try:
                        selected.add(int(item.replace("ch", "")))
                    except ValueError:
                        pass
            return selected or None
        if isinstance(value, dict):
            start = value.get("start", value.get("min"))
            end = value.get("end", value.get("max"))
            if start is None and end is None:
                return None
            start_num = 1 if start is None else int(start)
            end_num = start_num if end is None else int(end)
            return set(range(max(1, start_num), max(start_num, end_num) + 1))
        return None

    selected = parse_selection(source.get("chapter_range"))
    chapter_index = []
    raw_payloads = {}

    for index, item in enumerate(raw_items, start=1):
        chapter_id = f"ch{index}"
        if isinstance(item, dict):
            title = item.get("title") or item.get("name") or item.get("heading") or f"Chapter {index}"
            payload = item.get("content") or item.get("text") or item.get("html") or item.get("body") or ""
            source_ref = item.get("source") or item.get("href") or item.get("url") or source.get("file_path") or ""
        elif isinstance(item, str):
            title = item if item.strip() else f"Chapter {index}"
            payload = item
            source_ref = source.get("file_path") or ""
        else:
            title = f"Chapter {index}"
            payload = str(item)
            source_ref = source.get("file_path") or ""

        chapter_index.append({
            "chapter_id": chapter_id,
            "title": title,
            "source_type": "epub",
            "source": source_ref,
        })

        if selected is None or index in selected:
            raw_payloads[chapter_id] = payload if isinstance(payload, str) else str(payload)

    return chapter_index, raw_payloads


def _load_pdf_source(source: dict) -> (list, dict):
    """Extract raw PDF chapter/page text while preserving the full chapter index."""
    raw_items = source.get("pages")
    if raw_items is None:
        raw_items = source.get("chapters")
    if raw_items is None:
        raw_items = source.get("chapter_items")
    if raw_items is None:
        raw_items = source.get("items")
    if raw_items is None:
        direct = source.get("content") or source.get("text") or source.get("html") or ""
        raw_items = [{"title": source.get("title") or "Page 1", "content": direct, "source": source.get("file_path") or ""}]

    def parse_selection(value):
        if value in (None, "", [], {}):
            return None
        if isinstance(value, int):
            return {value}
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if "-" in value:
                pieces = value.split("-")
                if len(pieces) == 2:
                    try:
                        start = max(1, int(pieces[0].strip().replace("ch", "")))
                        end = max(start, int(pieces[1].strip().replace("ch", "")))
                        return set(range(start, end + 1))
                    except ValueError:
                        return None
            if "," in value:
                selected = set()
                for piece in value.split(","):
                    try:
                        selected.add(int(piece.strip().replace("ch", "")))
                    except ValueError:
                        pass
                return selected or None
            try:
                return {int(value.replace("ch", ""))}
            except ValueError:
                return None
        if isinstance(value, (list, tuple, set)):
            selected = set()
            for item in value:
                if isinstance(item, int):
                    selected.add(item)
                elif isinstance(item, str):
                    try:
                        selected.add(int(item.replace("ch", "")))
                    except ValueError:
                        pass
            return selected or None
        if isinstance(value, dict):
            start = value.get("start", value.get("min"))
            end = value.get("end", value.get("max"))
            if start is None and end is None:
                return None
            start_num = 1 if start is None else int(start)
            end_num = start_num if end is None else int(end)
            return set(range(max(1, start_num), max(start_num, end_num) + 1))
        return None

    selected = parse_selection(source.get("chapter_range"))
    chapter_index = []
    raw_payloads = {}

    for index, item in enumerate(raw_items, start=1):
        chapter_id = f"ch{index}"
        if isinstance(item, dict):
            title = item.get("title") or item.get("name") or f"Page {index}"
            payload = item.get("content") or item.get("text") or item.get("html") or item.get("body") or ""
            source_ref = item.get("source") or item.get("url") or item.get("path") or source.get("file_path") or ""
        elif isinstance(item, str):
            title = item if item.strip() else f"Page {index}"
            payload = item
            source_ref = source.get("file_path") or ""
        else:
            title = f"Page {index}"
            payload = str(item)
            source_ref = source.get("file_path") or ""

        chapter_index.append({
            "chapter_id": chapter_id,
            "title": title,
            "source_type": "pdf",
            "source": source_ref,
        })

        if selected is None or index in selected:
            raw_payloads[chapter_id] = payload if isinstance(payload, str) else str(payload)

    return chapter_index, raw_payloads


def _load_ocr_source(source: dict) -> (list, dict):
    """Extract OCR text for image-derived chapters while preserving the full chapter list."""
    raw_items = source.get("pages")
    if raw_items is None:
        raw_items = source.get("chapters")
    if raw_items is None:
        raw_items = source.get("items")
    if raw_items is None:
        raw_items = source.get("images")
    if raw_items is None:
        direct = source.get("content") or source.get("text") or source.get("ocr") or source.get("raw") or ""
        raw_items = [{"title": source.get("title") or "Page 1", "content": direct, "source": source.get("file_path") or ""}]

    def parse_selection(value):
        if value in (None, "", [], {}):
            return None
        if isinstance(value, int):
            return {value}
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if "-" in value:
                pieces = value.split("-")
                if len(pieces) == 2:
                    try:
                        start = max(1, int(pieces[0].strip().replace("ch", "")))
                        end = max(start, int(pieces[1].strip().replace("ch", "")))
                        return set(range(start, end + 1))
                    except ValueError:
                        return None
            if "," in value:
                selected = set()
                for piece in value.split(","):
                    try:
                        selected.add(int(piece.strip().replace("ch", "")))
                    except ValueError:
                        pass
                return selected or None
            try:
                return {int(value.replace("ch", ""))}
            except ValueError:
                return None
        if isinstance(value, (list, tuple, set)):
            selected = set()
            for item in value:
                if isinstance(item, int):
                    selected.add(item)
                elif isinstance(item, str):
                    try:
                        selected.add(int(item.replace("ch", "")))
                    except ValueError:
                        pass
            return selected or None
        if isinstance(value, dict):
            start = value.get("start", value.get("min"))
            end = value.get("end", value.get("max"))
            if start is None and end is None:
                return None
            start_num = 1 if start is None else int(start)
            end_num = start_num if end is None else int(end)
            return set(range(max(1, start_num), max(start_num, end_num) + 1))
        return None

    selected = parse_selection(source.get("chapter_range"))
    chapter_index = []
    raw_payloads = {}

    for index, item in enumerate(raw_items, start=1):
        chapter_id = f"ch{index}"
        if isinstance(item, dict):
            title = item.get("title") or item.get("name") or f"Page {index}"
            payload = item.get("content") or item.get("text") or item.get("ocr") or item.get("raw") or item.get("body") or ""
            source_ref = item.get("source") or item.get("path") or source.get("file_path") or ""
        elif isinstance(item, str):
            title = item if item.strip() else f"Page {index}"
            payload = item
            source_ref = source.get("file_path") or ""
        else:
            title = f"Page {index}"
            payload = str(item)
            source_ref = source.get("file_path") or ""

        chapter_index.append({
            "chapter_id": chapter_id,
            "title": title,
            "source_type": "ocr",
            "source": source_ref,
        })

        if selected is None or index in selected:
            raw_payloads[chapter_id] = payload if isinstance(payload, str) else str(payload)

    return chapter_index, raw_payloads


def _load_text_source(source: dict) -> (list, dict):
    """Extract raw text chapters while preserving the full chapter index."""
    raw_items = source.get("chapters")
    if raw_items is None:
        raw_items = source.get("chapter_items")
    if raw_items is None:
        raw_items = source.get("pages")
    if raw_items is None:
        raw_items = source.get("items")
    if raw_items is None:
        direct = source.get("content") or source.get("text") or source.get("raw") or source.get("body") or ""
        raw_items = [{"title": source.get("title") or "Chapter 1", "content": direct, "source": source.get("file_path") or source.get("path") or ""}]

    def parse_selection(value):
        if value in (None, "", [], {}):
            return None
        if isinstance(value, int):
            return {value}
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if "-" in value:
                pieces = value.split("-")
                if len(pieces) == 2:
                    try:
                        start = max(1, int(pieces[0].strip().replace("ch", "")))
                        end = max(start, int(pieces[1].strip().replace("ch", "")))
                        return set(range(start, end + 1))
                    except ValueError:
                        return None
            if "," in value:
                selected = set()
                for piece in value.split(","):
                    try:
                        selected.add(int(piece.strip().replace("ch", "")))
                    except ValueError:
                        pass
                return selected or None
            try:
                return {int(value.replace("ch", ""))}
            except ValueError:
                return None
        if isinstance(value, (list, tuple, set)):
            selected = set()
            for item in value:
                if isinstance(item, int):
                    selected.add(item)
                elif isinstance(item, str):
                    try:
                        selected.add(int(item.replace("ch", "")))
                    except ValueError:
                        pass
            return selected or None
        if isinstance(value, dict):
            start = value.get("start", value.get("min"))
            end = value.get("end", value.get("max"))
            if start is None and end is None:
                return None
            start_num = 1 if start is None else int(start)
            end_num = start_num if end is None else int(end)
            return set(range(max(1, start_num), max(start_num, end_num) + 1))
        return None

    selected = parse_selection(source.get("chapter_range"))
    chapter_index = []
    raw_payloads = {}

    for index, item in enumerate(raw_items, start=1):
        chapter_id = f"ch{index}"
        if isinstance(item, dict):
            title = item.get("title") or item.get("name") or f"Chapter {index}"
            payload = item.get("content") or item.get("text") or item.get("html") or item.get("body") or item.get("raw") or ""
            source_ref = item.get("source") or item.get("path") or item.get("url") or source.get("file_path") or ""
        elif isinstance(item, str):
            title = item if item.strip() else f"Chapter {index}"
            payload = item
            source_ref = source.get("file_path") or source.get("path") or ""
        else:
            title = f"Chapter {index}"
            payload = str(item)
            source_ref = source.get("file_path") or source.get("path") or ""

        chapter_index.append({
            "chapter_id": chapter_id,
            "title": title,
            "source_type": "text",
            "source": source_ref,
        })

        if selected is None or index in selected:
            raw_payloads[chapter_id] = payload if isinstance(payload, str) else str(payload)

    return chapter_index, raw_payloads


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

def process(input_data: Phase01Input) -> Phase01Output:
    start = time.time()

    source = input_data.source
    source_type = source.get("type")

    # Dispatch based on source type
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
        chapter_index, raw_payloads = [], []

    output = Phase01Output(
        chapter_index=chapter_index,
        raw_payloads=raw_payloads,
        meta={
            "phase": "01_source",
            "version": "1.0.0",
            "timestamp": time.time(),
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
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
