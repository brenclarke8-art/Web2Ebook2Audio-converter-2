from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from llm_process import DialogueParser


def run_llm_process(input_payload: dict[str, Any]) -> dict[str, Any]:
    chapter = input_payload.get("chapter") or {}
    text = str(chapter.get("text", "") or "")
    parser = DialogueParser()
    parsed = parser.parse(text)
    return {
        "chapter": {
            "title": chapter.get("title", ""),
            "source": chapter.get("source", {}),
            "segments": [asdict(segment) for segment in parsed.segments],
            "characters": [asdict(character) for character in parsed.detected_characters],
            "raw_text": text,
        }
    }


def run_file(input_json: str | Path, output_json: str | Path) -> Path:
    input_path = Path(input_json)
    output_path = Path(output_json)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    result = run_llm_process(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
