# src/ebook_app/models/multispeaker_tts.py
"""Multi-speaker TTS orchestrator — synthesises segments with per-character voices."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ebook_app.models.character_db import Character, CharacterDatabase
from ebook_app.models.dialogue_parser import Segment
from ebook_app.models.tts_engine_cli import TTSEngineCLI


@dataclass
class SynthesisResult:
    """Result of synthesising a single :class:`~ebook_app.models.dialogue_parser.Segment`.

    :param segment:    The source segment.
    :param wav_path:   Path to the synthesised WAV file.
    :param duration_s: Duration in seconds (populated after synthesis).
    """

    segment: Segment
    wav_path: str
    duration_s: float = 0.0


class MultiSpeakerTTS:
    """Synthesises a list of :class:`Segment` objects using per-character voices.

    Characters without an explicit voice assignment fall back to *default_voice*.

    Usage::

        tts = MultiSpeakerTTS(engine=engine, character_db=db, output_dir="/tmp/audio")
        results = tts.synthesise_segments(segments, chapter_id="ch01")

    TODO: populate duration_s via forced alignment or audio file inspection.
    """

    DEFAULT_NARRATOR_VOICE = "af_heart"

    def __init__(
        self,
        engine: TTSEngineCLI,
        character_db: CharacterDatabase,
        output_dir: str,
        default_voice: str = DEFAULT_NARRATOR_VOICE,
    ) -> None:
        self._engine = engine
        self._db = character_db
        self._output_dir = Path(output_dir)
        self._default_voice = default_voice

    def synthesise_segments(
        self,
        segments: list[Segment],
        chapter_id: str = "ch",
        speed: float = 1.0,
    ) -> list[SynthesisResult]:
        """Synthesise each segment and return :class:`SynthesisResult` objects.

        TODO: implement actual synthesis; currently returns empty stubs.
        """
        results: list[SynthesisResult] = []
        for i, seg in enumerate(segments):
            voice = self._resolve_voice(seg.speaker)
            wav_path = str(self._output_dir / f"{chapter_id}_{i:04d}.wav")
            # TODO: uncomment when engine is configured
            # wav_path = self._engine.synthesise(seg.text, voice, wav_path, speed)
            results.append(SynthesisResult(segment=seg, wav_path=wav_path))
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_voice(self, speaker: str) -> str:
        """Return the voice assigned to *speaker*, falling back to default."""
        character: Character | None = self._db.get(speaker)
        if character is not None:
            return character.voice
        return self._default_voice
