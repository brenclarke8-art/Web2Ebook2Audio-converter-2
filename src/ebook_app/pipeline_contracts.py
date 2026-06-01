# src/ebook_app/pipeline_contracts.py
"""
Authoritative contracts for the Web-Novel → EPUB3 Audiobook pipeline.

All other modules (scrapers, LLM parsers, TTS engines, EPUB builders, etc.)
MUST conform to the interfaces and data schemas defined here.

This file is the single source of truth for:
- Pipeline step names
- File naming conventions
- JSON schemas
- Class/method signatures
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypedDict, List, Dict, Any, Optional, runtime_checkable, Callable


# ---------------------------------------------------------------------------
# Global pipeline constants
# ---------------------------------------------------------------------------

PIPELINE_STEPS: List[str] = [
    "scrape_index",
    "scrape_chapters",
    "clean_chapters",
    "plan_clean_review",
    "llm_semantic_analysis",
    "normalize_llm_output",
    "smart_review_dialogue",
    "tts_generate",
    "epub_build",
]

# Progress callback type: (step_key, value 0-100) -> None
ProgressCallback = Callable[[str, int], None]


def chapter_id(idx: int, *, start_index: int = 1) -> str:
    """Canonical chapter ID format: ch1, ch2, ... based on chapter index."""
    chapter_number = max(1, int(start_index) + int(idx))
    return f"ch{chapter_number}"


# ---------------------------------------------------------------------------
# Core data schemas
# ---------------------------------------------------------------------------

class ChapterDict(TypedDict, total=False):
    """Scraped chapter structure stored in chapters.json."""
    title: str
    content: str          # raw HTML or text
    url: str              # or source_url
    source_url: str


class SegmentDict(TypedDict, total=False):
    """Normalized semantic segment (post-Phase 6A)."""
    text: str
    type: str                     # "narration" | "dialogue" | etc.
    speaker: str                  # "narrator" or character name
    gender: str                   # "male" | "female" | "unknown"
    speaker_confidence: float
    gender_confidence: float
    character_confidence: float
    paragraph_id: str | int


class DetectedCharacterDict(TypedDict, total=False):
    """Character as detected by LLM (pre-voice assignment)."""
    name: str
    gender: str                   # "male" | "female" | "unknown"
    confidence: float


class FinalCharacterDict(TypedDict, total=False):
    """Character entry after voice assignment."""
    name: str
    gender: str
    voice: str                    # voice ID used by TTS


class ChapterInfoRaw(TypedDict, total=False):
    """Raw LLM output per chapter (Phase 5)."""
    chapter_index: int
    chapter_id: str
    title: str
    segments: List[SegmentDict]
    detected_characters: List[DetectedCharacterDict]


class ChapterInfoNormalized(TypedDict, total=False):
    """Normalized LLM output per chapter (Phase 6A)."""
    chapter_id: str
    segments: List[SegmentDict]
    characters: List[DetectedCharacterDict]


class ChapterInfoFinal(TypedDict, total=False):
    """Final per-chapter info (Phase 6B)."""
    chapter_id: str
    segments: List[SegmentDict]
    characters: List[FinalCharacterDict]


class ReviewPlanClean(TypedDict, total=False):
    """Cleaned-text review plan (Phase 4)."""
    mode: str                     # "skip" | "semi" | "full"
    sample: int
    total_chapters: int
    needs_review: List[int]       # chapter indices


class ReviewPlanSemantic(TypedDict, total=False):
    """Semantic review plan (Phase 6B)."""
    total_chapters: int
    needs_review: List[int]       # chapter indices


class AudioTimingEntry(TypedDict, total=False):
    """Timing entry for a single segment (for SMIL)."""
    paragraph_id: str | int
    clip_begin: float
    clip_end: float


AudioTimingMap = Dict[str, List[AudioTimingEntry]]  # chapter_id -> list[timing]


class CharacterDBEntry(TypedDict, total=False):
    """Canonical character DB entry stored in character_database.json."""
    name: str
    gender: str
    voice: str
    description: str


# ---------------------------------------------------------------------------
# Scraper contracts
# ---------------------------------------------------------------------------

@runtime_checkable
class IndexScraper(Protocol):
    """
    Contract for index scraping.

    Implementations:
      - HttpWebScraper
      - WebScraper
    """

    def scrape_index_page(self, url: str, max_pages: int = ...) -> List[str]:
        """
        Return a flat list of chapter URLs in reading order.

        MUST NOT return None.
        """


@runtime_checkable
class ChapterScraper(Protocol):
    """
    Contract for chapter scraping.

    Implementations:
      - HttpWebScraper
      - WebScraper
    """

    def scrape_chapters(self, urls: List[str]) -> List[ChapterDict]:
        """
        Given a list of chapter URLs, return a list of ChapterDict.

        Each dict MUST contain at least:
          - "content": str
          - "title": str
        """


# ---------------------------------------------------------------------------
# LLM / Dialogue parser contracts
# ---------------------------------------------------------------------------

class SegmentLike(Protocol):
    """Runtime shape of a Segment object returned by DialogueParser."""
    text: str
    type: str
    speaker: str
    gender: str
    speaker_confidence: float
    gender_confidence: float
    character_confidence: float
    paragraph_id: int | str


class DetectedCharacterLike(Protocol):
    """Runtime shape of a detected character object."""
    name: str
    gender: str
    confidence: float


class DialogueParseResult(Protocol):
    """Result object returned by DialogueParser.parse()."""
    segments: List[SegmentLike]
    detected_characters: List[DetectedCharacterLike]


@runtime_checkable
class DialogueParserContract(Protocol):
    """
    Contract for DialogueParser used in Phase 5.

    Must be constructible with:
      - llm_url: str
      - model: str
      - timeout_s: int
      - retries: int
      - llm_mode: str
      - llm_strict_quotes: bool
      - llm_log_path: str
    """

    def parse(self, text: str, chapter_id: str) -> DialogueParseResult:
        """
        Run semantic analysis on a single chapter.

        MUST return an object with:
          - .segments: list[SegmentLike]
          - .detected_characters: list[DetectedCharacterLike]
        """


# ---------------------------------------------------------------------------
# Voice routing contracts
# ---------------------------------------------------------------------------

@runtime_checkable
class VoiceRouterContract(Protocol):
    """
    Contract for VoiceRouter.

    Must be constructible with:
      - character_voices: dict-like
      - default_male_voice: str
      - default_female_voice: str
      - narrator_voice: str
    """

    def get_voice_for_segment(self, *, speaker: str, seg_type: str, gender: str) -> str:
        """
        Return a voice ID for a given segment.

        MUST be pure with respect to:
          - speaker
          - seg_type
          - gender
        """


# ---------------------------------------------------------------------------
# TTS engine contracts
# ---------------------------------------------------------------------------

@runtime_checkable
class TTSEngineContract(Protocol):
    """
    Contract for local/remote TTS backends.

    Implementations:
      - TTSEngine (local CLI)
      - TTSClient (remote HTTP)
    """

    def generate_audio(
        self,
        *,
        text: str,
        output_filename: str,
        voice: str,
        speed: float,
    ) -> Path:
        """
        Generate a single audio file.

        MUST:
          - Write the file into the configured output directory.
          - Return the full Path to the generated file.
        """

    def get_last_audio_duration(self) -> float:
        """
        Return the duration (in seconds) of the last generated audio clip.
        """

    def concatenate_audio_files(
        self,
        files: List[str],
        output_path: Path,
    ) -> None:
        """
        Concatenate multiple audio files into a single file at output_path.
        """


# ---------------------------------------------------------------------------
# EPUB builder contracts
# ---------------------------------------------------------------------------

class TextSegment(TypedDict):
    """EPUB SMIL text segment."""
    paragraph_id: str | int
    clip_begin: float
    clip_end: float


@runtime_checkable
class EPUBBuilderContract(Protocol):
    """
    Contract for EPUBBuilder used in Phase 8.

    Must be constructible with:
      - title: str
      - author: str
      - output_dir: str
      - work_dir: str
    """

    def add_chapter(self, *, filename: str, xhtml: str, title: str) -> None:
        """
        Add a chapter XHTML file to the EPUB.
        """

    def add_audio(
        self,
        *,
        chapter_filename: str,
        audio_path: str,
        segments: List[TextSegment],
    ) -> None:
        """
        Attach audio + SMIL timing to a chapter.
        """

    def build(self) -> Path:
        """
        Build the final EPUB file and return its path.
        """


# ---------------------------------------------------------------------------
# File naming & locations (documentation only)
# ---------------------------------------------------------------------------

"""
All paths are relative to work_dir unless otherwise noted.

Phase 1:
  - raw_chapter_urls.json
  - chapter_urls.json

Phase 2:
  - chapters.json  # list[ChapterDict]

Phase 3:
  - chXXX_cleaned.txt

Phase 4:
  - clean_review_plan.json  # ReviewPlanClean

Phase 5:
  - chXXX_llm_raw.json      # ChapterInfoRaw
  - chXXX/chXXX_chapter_info.json
  - chapter_info_all.json   # dict[str(idx) -> ChapterInfoRaw]

Phase 6A:
  - chXXX_llm_normalized.json  # ChapterInfoNormalized

Phase 6B:
  - character_database.json        # list[CharacterDBEntry]
  - semantic_review_plan.json      # ReviewPlanSemantic
  - chXXX_segments_final.json      # list[SegmentDict]
  - chXXX_characters_final.json    # list[FinalCharacterDict]
  - chXXX_chapter_info_final.json  # ChapterInfoFinal

Phase 7:
  - audio/chXXX/chXXX_segYYY.wav
  - audio/chXXX/chXXX.wav
  - audio_timing.json              # AudioTimingMap

Phase 7B (preview):
  - previews/chXXX_segYYY_preview.wav

Phase 8:
  - Final EPUB written to settings.output_dir via EPUBBuilder.build()
"""
