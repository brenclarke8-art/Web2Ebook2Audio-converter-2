from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from audio_render import TTSEngine, TTSPipeline, VoiceRouter
from ebook_app.app.state.character_db import CharacterDatabase


def run_audio_render(input_payload: dict[str, Any], output_wav: str | Path) -> Path:
    chapter = input_payload.get("chapter") or {}
    source_segments = chapter.get("segments") or []
    segments = []
    for idx, segment in enumerate(source_segments, start=1):
        text = str(segment.get("normalized_text") or segment.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            {
                "segment_id": str(segment.get("line_id") or segment.get("segment_id") or f"seg_{idx:04d}"),
                "paragraph_id": str(segment.get("paragraph_id") or segment.get("line_id") or f"p_{idx:04d}"),
                "text": text,
                "speaker": segment.get("speaker_name") or segment.get("speaker") or "",
                "gender": segment.get("gender") or "unknown",
                "type": segment.get("character_type") or segment.get("type") or "narration",
                "voice": segment.get("voice_hint") or segment.get("voice") or "",
            }
        )

    work_dir = Path(input_payload.get("work_dir") or ".")
    work_dir.mkdir(parents=True, exist_ok=True)

    router = VoiceRouter(
        narrator_voice=str(input_payload.get("narrator_voice", "af_narrator")),
        default_male_voice=str(input_payload.get("default_male_voice", "am_adam")),
        default_female_voice=str(input_payload.get("default_female_voice", "af_heart")),
    )
    db = CharacterDatabase(path=work_dir / "character_database.json")
    engine = TTSEngine(base_url=str(input_payload.get("tts_base_url", "http://127.0.0.1:8000")))
    pipeline = TTSPipeline(engine=engine, voice_router=router, character_db=db, output_root=work_dir)

    chapter_id = str(chapter.get("id") or input_payload.get("chapter_id") or "chapter")
    synthesis_result = pipeline.synthesize_chapter(chapter_id=chapter_id, segments=segments)

    output_path = Path(output_wav)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path = Path(synthesis_result["chapter_audio"])
    if rendered_path.exists() and rendered_path != output_path:
        output_path.write_bytes(rendered_path.read_bytes())
    return output_path if output_path.exists() else rendered_path


def run_file(input_json: str | Path, output_wav: str | Path) -> Path:
    payload = json.loads(Path(input_json).read_text(encoding="utf-8"))
    return run_audio_render(payload, output_wav)
