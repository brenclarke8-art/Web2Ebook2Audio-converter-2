# ebook_app/phases/phase7_audio.py
"""Phase 7 — Audio Generation.

Drives TTS synthesis for every segment in the final segment list produced
by Phase 6.  Uses the TTSPipeline which wraps TTSEngineContract (remote
TTS service).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List

from ebook_app.phases.phase_base import PhaseBase, PhaseResult

logger = logging.getLogger(__name__)


class Phase7Audio(PhaseBase):
    """Phase 7: generate audio for each segment and concatenate per chapter."""

    def run(self, chapter_id: str, **kwargs) -> PhaseResult:
        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        segments: List[dict] = kwargs.get("segments", [])
        character_db: Any = kwargs.get("character_db")
        work_dir: Any = kwargs.get("work_dir")
        output_dir: Any = kwargs.get("output_dir")

        if not segments:
            return PhaseResult.error_result("No segments provided for audio generation.")

        self._emit_progress(5)

        tts_url: str = self.settings.get("tts_backend_url", "http://127.0.0.1:5005")
        tts_speed: float = float(self.settings.get("tts_speed", 1.0))

        try:
            from ebook_app.tts.tts_client import TTSClient
            from ebook_app.tts.tts_service import TTSEngine
            from ebook_app.tts.tts_pipeline import TTSPipeline
            from ebook_app.tts.voice_router import VoiceRouter

            tts_engine = TTSEngine(client=TTSClient(base_url=tts_url))
            voice_router = VoiceRouter(
                narrator_voice=self.settings.get("narrator_voice", "af_heart"),
                default_male_voice=self.settings.get("default_male_voice", "am_adam"),
                default_female_voice=self.settings.get("default_female_voice", "af_bella"),
            )

            audio_output_root = Path(output_dir or work_dir or ".") / "audio"
            audio_output_root.mkdir(parents=True, exist_ok=True)

            pipeline = TTSPipeline(
                engine=tts_engine,
                voice_router=voice_router,
                character_db=character_db,
                output_root=audio_output_root,
                speed=tts_speed,
            )
        except Exception as exc:
            logger.error("[Phase7] TTS setup failed: %s", exc, exc_info=True)
            return PhaseResult.error_result(f"TTS setup failed: {exc}")

        self._emit_progress(15)

        try:
            result = pipeline.synthesize_chapter(chapter_id, segments)
        except Exception as exc:
            logger.error("[Phase7] Audio generation failed: %s", exc, exc_info=True)
            return PhaseResult.error_result(f"Audio generation failed: {exc}")

        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        self._emit_progress(100)

        chapter_audio = result.get("chapter_audio", "")
        timing = result.get("timing", [])

        return PhaseResult(
            success=True,
            output_text=f"Audio written to: {chapter_audio}\nSegments: {len(timing)}",
            data={
                "chapter_audio": chapter_audio,
                "timing": timing,
            },
        )
