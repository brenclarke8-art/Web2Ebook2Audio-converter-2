from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scrape_clean import HttpWebScraper, TextCleaner, TextNormalizer


def run_scrape_clean(input_payload: dict[str, Any]) -> dict[str, Any]:
    source = input_payload.get("source") or {}
    chapter_text = str(source.get("text", "") or "")
    if not chapter_text and source.get("url"):
        scraper = HttpWebScraper()
        chapter_data = scraper.scrape_chapters([str(source["url"])])
        chapter_text = chapter_data[0].get("content", "") if chapter_data else ""

    cleaned = TextCleaner.clean_text(chapter_text)
    normalized = TextNormalizer.normalize(cleaned)
    return {
        "chapter": {
            "title": source.get("title", ""),
            "source": source,
            "text": normalized,
        }
    }


def run_file(input_json: str | Path, output_json: str | Path) -> Path:
    input_path = Path(input_json)
    output_path = Path(output_json)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    result = run_scrape_clean(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
