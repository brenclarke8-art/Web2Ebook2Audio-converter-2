# ebook_app/tts/tts_pipeline.py
"""
TTS Pipeline
------------
High-level orchestration for text-to-speech generation.

This module wraps the low-level TTSEngineContract and provides:
    - per-segment synthesis
    - per-chapter synthesis
    - timing extraction
    - concatenation
    - preview generation

The PipelineController uses this module to keep TTS logic clean and modular.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List

from ebook_app.tts.voice_router import VoiceRouter
from ebook_app.tts.tts_service import TTSEngineContract
from ebook_app.app.state.character_db import CharacterDatabase


class TTSPipeline:
    """
    High-level TTS orchestrator.

    Responsibilities:
        - Generate per-segment WAVs
        - Concatenate into chapter WAV
        - Produce timing metadata
        - Provide segment-level preview
    """

    def __init__(
        self,
        engine: TTSEngineContract,
        voice_router: VoiceRouter,
        character_db: CharacterDatabase,
        output_root: Path,
        speed: float = 1.0,
    ) -> None:
        self.engine = engine
        self.voice_router = voice_router
        self.character_db = character_db
        self.output_root = output_root
        self.speed = float(speed)

    # ------------------------------------------------------------------
    # Segment-level synthesis
    # ------------------------------------------------------------------

    def synthesize_segment(
        self,
        chapter_id: str,
        segment: Dict,
    ) -> Path:
        """
        Generate a single WAV file for a segment.

        Returns
        -------
        Path
            Path to the generated WAV file.
        """
        text = (segment.get("text") or "").strip()
        if not text:
            raise ValueError("Segment text is empty.")

        voice = self.voice_router.get_voice_for_segment(segment, self.character_db)

        seg_id = segment.get("segment_id")
        if not seg_id:
            raise ValueError("Segment missing segment_id.")

        chapter_dir = self.output_root / chapter_id
        chapter_dir.mkdir(parents=True, exist_ok=True)

        out_path = chapter_dir / f"{seg_id}.wav"

        self.engine.generate_audio(
            text=text,
            output_filename=str(out_path),
            voice=voice,
            speed=self.speed,
        )

        return out_path

    # ------------------------------------------------------------------
    # Chapter-level synthesis
    # ------------------------------------------------------------------

    def synthesize_chapter(
        self,
        chapter_id: str,
        segments: List[Dict],
    ) -> Dict:
        """
        Generate all segment WAVs for a chapter, then concatenate.

        Returns
        -------
        dict
            {
                "chapter_audio": "path/to/chXXX.wav",
                "timing": [
                    {
                        "paragraph_id": "...",
                        "clip_begin": 0.0,
                        "clip_end": 1.23
                    }
                ]
            }
        """
        chapter_dir = self.output_root / chapter_id
        chapter_dir.mkdir(parents=True, exist_ok=True)

        segment_paths: List[str] = []
        timing: List[Dict] = []
        current_time = 0.0

        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue

            voice = self.voice_router.get_voice_for_segment(seg, self.character_db)

            seg_id = seg.get("segment_id")
            if not seg_id:
                raise ValueError(f"Segment missing segment_id in {chapter_id}")

            seg_path = chapter_dir / f"{seg_id}.wav"

            self.engine.generate_audio(
                text=text,
                output_filename=str(seg_path),
                voice=voice,
                speed=self.speed,
            )

            duration = float(self.engine.get_last_audio_duration() or 0.0)

            paragraph_id = seg.get("paragraph_id")
            if not paragraph_id:
                raise ValueError(f"Segment missing paragraph_id in {chapter_id}")

            timing.append(
                {
                    "paragraph_id": paragraph_id,
                    "clip_begin": current_time,
                    "clip_end": current_time + duration,
                }
            )

            current_time += duration
            segment_paths.append(str(seg_path))

        # Concatenate
        chapter_audio = chapter_dir / f"{chapter_id}.wav"
        if segment_paths:
            self.engine.concatenate_audio_files(segment_paths, chapter_audio)

        return {
            "chapter_audio": str(chapter_audio),
            "timing": timing,
        }

    # ------------------------------------------------------------------
    # Preview synthesis
    # ------------------------------------------------------------------

    def preview_segment(
        self,
        chapter_id: str,
        segment: Dict,
    ) -> Path:
        """
        Generate a preview WAV for a single segment.
        """
        preview_dir = self.output_root / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)

        text = (segment.get("text") or "").strip()
        if not text:
            raise ValueError("Segment text is empty.")

        voice = self.voice_router.get_voice_for_segment(segment, self.character_db)

        seg_id = segment.get("segment_id")
        if not seg_id:
            raise ValueError("Segment missing segment_id.")

        out_path = preview_dir / f"{seg_id}_preview.wav"

        self.engine.generate_audio(
            text=text,
            output_filename=str(out_path),
            voice=voice,
            speed=self.speed,
        )

        return out_path
