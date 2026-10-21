Web2Ebook2Audio Converter - Project Overview
Vision

Web2Ebook2Audio is a modular pipeline that converts web novels, ebooks, PDFs, OCR sources, and plain text into clean, structured audiobook-ready content.

The system is designed around a strict phase architecture where each phase owns exactly one responsibility and passes a well-defined contract to the next phase.

Core goals:

Support web novels and serialized fiction.
Support EPUB, PDF, OCR, and plain-text sources.
Generate high-quality audiobooks.
Support both simple and advanced character voice assignment.
Support partial-book processing.
Remain deterministic and reproducible wherever possible.
Minimize duplicate LLM work.
Allow future expansion without schema migrations.
Architectural Philosophy

The pipeline follows four core principles:

1. Single Responsibility Per Phase

Each phase owns exactly one concern.

Example:

Phase 03 = structural segmentation

NOT

Phase 03 = segmentation + character detection


This keeps phases easy to test, maintain, and replace.

2. Canonical Contracts

Every phase communicates through structured schemas.

Example:

Phase03Output


becomes

Phase04Input


No hidden assumptions.

No ad-hoc data sharing.

3. Canonical Character IDs

After character discovery, the system never relies on raw character names.

Example:

char_001


instead of:

Sarah
Sarah Carter
Miss Carter
The Detective


All later phases use:

character_id


for stability and consistency.

4. LLM Decisions Are Made Once

Expensive semantic decisions should happen only once.

Example:

Character discovery
Speaker attribution
Thought attribution


are performed once and reused downstream.

High-Level Pipeline
Phase 00 Fetch
Phase 01 Source
Phase 02 Cleaning

Phase 03 Segmentation
Phase 04 Character Registry
Phase 05 Semantic Enrichment
Phase 06 Voice Assignment

Phase 07 TTS
Phase 08 Timing
Phase 09 Packaging
Phase 10 Validation

Phase 00 - Fetch
Purpose

Remote acquisition layer.

Only phase allowed to perform network operations.

Responsibilities
Fetch index page
Discover chapter URLs
Apply chapter range
Download chapters
Extract basic metadata
Extract raw chapter content
Build source descriptor
Output
source


Example:

{
    "type": "web",
    "url": "...",
    "chapters": [...]
}

Does Not
Generate chapter IDs
Generate chapter_index
Generate raw_payloads
Clean text
Phase 01 - Source
Purpose

Source normalization layer.

Convert supported sources into a common internal format.

Supported inputs:

web
epub
pdf
ocr
text

Responsibilities
Discover full chapter structure
Build chapter_index
Generate chapter IDs
Build raw_payloads
Preserve source ordering
Outputs
chapter_index
raw_payloads

Phase 02 - Cleaning
Purpose

Convert raw source content into normalized text.

Responsibilities
Remove HTML noise
Normalize whitespace
Clean extraction artifacts
Preserve story content
Outputs
normalized_chapters
chapter_stats


Example:

{
    "ch1": "Clean chapter text..."
}

Phase 03 - Segmentation
Purpose

Structural segmentation.

Deterministic.

No AI.

Responsibilities
Detect chapter titles
Detect headings
Detect scene breaks
Create atomic segments
Identify structural markers
Outputs
segments
segmentation_stats


Segment example:

{
    "segment_id": "ch1_seg0001",
    "chapter_id": "ch1",
    "sequence": 1,
    "paragraph_index": 1,
    "structural_type": "paragraph",
    "text": "...",
    "text_markers": ["double_quote"]
}

Phase 04 - Character Registry
Purpose

Book-wide character discovery.

First LLM-driven phase.

Responsibilities
Discover characters
Resolve aliases
Create canonical IDs
Build cast database
Outputs
character_registry
segments


Character example:

{
    "character_id": "char_001",
    "canonical_name": "Sarah Carter",
    "aliases": [
        "Sarah",
        "Miss Carter"
    ],
    "character_profile": {}
}

Phase 05 - Semantic Enrichment
Purpose

Story understanding.

This phase owns semantic interpretation.

Responsibilities
Narration detection
Dialogue detection
Thought detection
Speaker attribution
POV detection
Emotion tagging
Outputs
enriched_segments
character_registry


Example:

{
    "segment_id": "ch1_seg0007",
    "primary_type": "dialogue",
    "speaker_id": "char_001",
    "emotion_tag": "happy",
    "classification_confidence": 0.92,
    "speaker_confidence": 0.90
}

Phase 06 - Voice Assignment
Purpose

Map characters to voices.

No story analysis.

No LLM reasoning.

Responsibilities
Assign narrator voice
Assign character voices
Build voice registry
Create TTS-ready segments
Outputs
voice_registry
voice_segments


Voice assignment example:

{
    "voice_id": "voice_char_001",
    "character_id": "char_001",
    "voice_role": "character"
}

Voice Modes
Manual Mode

User manually maps voices.

Example:

Narrator -> Aria
Sarah -> Jenny
John -> Guy


Configuration:

settings.tts.voice_mode = "manual"

Adaptive Mode

Future enhancement.

Allows:

character profile analysis
emotion-aware rendering
intelligent voice assignment

Configuration:

settings.tts.voice_mode = "adaptive"

Phase 07 - TTS
Purpose

Generate audio from voice segments.

Future responsibilities:

Provider integration
Audio generation
Retry handling
Audio chunk management

Potential providers:

Edge TTS
Azure Speech
ElevenLabs
OpenAI

Phase 08 - Timing
Purpose

Generate timing and alignment metadata.

Future responsibilities:

Segment timing
Chapter timing
Synchronization data
Playback alignment
Phase 09 - Packaging
Purpose

Assemble final deliverables.

Potential outputs:

M4B
MP3
EPUB
JSON
Metadata packages

Phase 10 - Validation
Purpose

Final quality assurance layer.

Future responsibilities:

Missing audio detection
Voice consistency checks
Schema validation
Timing validation
Packaging validation
Development Principles

Every phase follows the same structure:

input_schema.py
output_schema.py
processor.py
runner.py
debug.py
tests/

processor.py

Contains business logic only.

Must remain:

deterministic when possible
testable
side-effect free
runner.py

Responsible for orchestration only.

Calls:

process()


and manages phase execution.

debug.py

Responsible only for writing artifacts.

No business logic.

tests/

Validate:

schema compliance
responsibility boundaries
edge cases
deterministic behavior
