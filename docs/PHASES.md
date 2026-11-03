# Pipeline Phases

This document provides an overview of all 11 pipeline phases. For detailed specifications, see the `tasks.md` file in each phase directory.

## Quick Reference

| Phase | Name | Responsibility | Input | Output |
|-------|------|-----------------|-------|--------|
| 00 Bootstrap | Config Validation | Normalize settings, validate readiness | Raw config/env | Normalized config |
| 00 Fetch | Chapter Acquisition | Fetch web chapters, parse URLs | Index URL + range | HTML content per chapter |
| 01 | Source Normalization | Extract chapters from diverse sources | Raw content (web/epub/pdf/ocr/text) | `chapter_index` + `raw_payloads` |
| 02 | Text Cleaning | Remove HTML, normalize whitespace, stats | Raw payloads | `normalized_chapters` + `chapter_stats` |
| 03 | Segmentation | Split into structural units | Normalized chapters | `segments` (with offsets) |
| 04 | Character Registry | Discover characters, assign canonical IDs | Segments | `character_registry` |
| 05 | Semantic Enrichment | Attribution (speaker/dialogue/POV) | Segments + registry | `enriched_segments` |
| 06 | Voice Assignment | Map characters to voice profiles | Enriched segments | `voice_assignments` |
| 07 | TTS Generation | Synthesize audio from text | Assignments + audio config | Audio chunks per segment |
| 08 | Audio Stitching | Assemble audio into chapters | Audio chunks | Audiobook manifest |
| 09 | Packaging | Bundle audiobook + EPUB | Audiobook manifest | `package_manifest` |
| 10 | Export & Validation | Write final files, generate metadata | Package manifest | Export index + written paths |

## Phase Descriptions

### Phase 00: Bootstrap

**Responsibility:** Config validation and readiness checks

**Input:**
- Raw settings (config file, environment variables)
- Environment mode (development/production)

**Processing:**
- Normalize configuration format
- Validate all required settings present
- Check dependencies available
- Generate readiness report

**Output:**
- Normalized config object
- Readiness report (boolean flags)
- Input/output summaries

**Key Files:** `phase_00_bootstrap/processor.py`

---

### Phase 00: Fetch

**Responsibility:** Acquire chapters from web sources

**Input:**
- Index URL (where chapter list lives)
- Chapter range (which chapters to download)

**Processing:**
- Fetch index page
- Extract chapter URLs (via rules or heuristics)
- Fetch each chapter HTML
- Learn/refine extraction rules
- Apply chapter range filter

**Output:**
- Raw HTML content per chapter
- Chapter metadata (title, URL, order)
- Learned rules for future runs

**Key Files:** `phase_00_fetch/processor.py`, `chapter_parser.py`, `fetcher.py`

**Network Call:** Yes (HTTP requests)

---

### Phase 01: Source Normalization

**Responsibility:** Extract chapters from diverse sources

**Input:**
- Source object (type: web/epub/pdf/ocr/text)
- Chapter list or raw content

**Processing:**
- Detect source type
- Load source-specific parser
- Extract chapters and content
- Normalize to common chapter structure
- Apply chapter range filter

**Output:**
- `chapter_index`: List of chapter metadata
- `raw_payloads`: Dict mapping chapter_id → raw_content

**Quality:** ✅ Best-aligned phase; clean contract

---

### Phase 02: Text Cleaning

**Responsibility:** Remove noise, normalize text

**Input:**
- Raw payloads (HTML/text blobs)

**Processing:**
- Strip HTML tags
- Collapse multiple whitespace
- Normalize paragraphs
- Generate per-chapter statistics (word count, char count)
- Handle encoding issues

**Output:**
- `normalized_chapters`: Clean text per chapter
- `chapter_stats`: Word/char counts, etc.

---

### Phase 03: Segmentation

**Responsibility:** Split into structural units

**Input:**
- Normalized chapters

**Processing:**
- Parse paragraphs and sentences
- Detect structural markers (chapter breaks, etc.)
- Create segments with type (paragraph/dialogue/action)
- Track source offsets for debugging

**Output:**
- `segments`: List of segment objects
  - `segment_id`: Unique identifier
  - `text`: Segment text
  - `structural_type`: paragraph/dialogue/action/etc
  - `source_offset_start/end`: Char positions in source

---

### Phase 04: Character Registry

**Responsibility:** Discover and canonicalize characters

**Input:**
- Segments with speaker mentions

**Processing:**
- Extract character name mentions
- Resolve aliases to canonical names
- Track first appearance per character
- Classify importance (major/minor)
- Assign canonical IDs (char_001, char_002, etc.)

**Output:**
- `character_registry`: List of character objects
  - `character_id`: Canonical ID
  - `canonical_name`: Resolved name
  - `aliases`: All known names
  - `importance`: major/minor
  - `first_seen_segment`: First occurrence

---

### Phase 05: Semantic Enrichment

**Responsibility:** Add speaker/dialogue/POV attribution

**Input:**
- Segments
- Character registry

**Processing:**
- Classify segment semantic type (narration/dialogue/thought/action)
- Assign speaker to dialogue segments
- Track point-of-view character
- Link referenced characters
- Assign emotion tags

**Output:**
- `enriched_segments`: Segments with semantic metadata
  - `primary_type`: narration/dialogue/thought/action
  - `speaker_id`: Who is speaking
  - `pov_character_id`: Whose perspective
  - `referenced_characters`: Characters mentioned
  - `emotion_tag`: sentiment/emotion

---

### Phase 06: Voice Assignment

**Responsibility:** Map characters to voice profiles

**Input:**
- Enriched segments
- Character registry

**Processing:**
- Define voice profiles (tone, gender, age, accent)
- Assign each character to voice
- Create voice/segment mapping
- Generate voice assignment manifest

**Output:**
- `voice_assignments`: Segment → voice mapping
- `assignment_manifest`: Overview of all assignments

---

### Phase 07: TTS Generation

**Responsibility:** Synthesize audio from text

**Input:**
- Enriched segments
- Voice assignments

**Processing:**
- For each segment, select voice (based on speaker/POV)
- Call TTS service to generate audio
- Return audio chunk with timing metadata

**Output:**
- Audio chunks per segment
- `audio_index`: Segment → audio file mapping
- Timing metadata (duration, sample rate)

**Network Call:** Yes (TTS service)

**Note:** Currently missing implementation; see Phase 07 TTS task

---

### Phase 08: Audio Stitching

**Responsibility:** Assemble audio into chapters

**Input:**
- Audio chunks per segment
- Audio index and timing

**Processing:**
- Group segments by chapter
- Stitch audio chunks in order
- Add chapter markers/metadata
- Generate chapter-level audio files

**Output:**
- `audiobook_manifest`: Audio files per chapter
- Chapter timing metadata
- Audio quality metrics

---

### Phase 09: Packaging

**Responsibility:** Bundle audiobook + EPUB

**Input:**
- Audiobook manifest (audio per chapter)
- EPUB content
- Metadata (characters, timing, etc.)

**Processing:**
- Create EPUB structure with enhanced metadata
- Create audiobook package
- Generate combined manifest
- Create index for quick lookup

**Output:**
- `package_manifest`: Combined audiobook + EPUB
- `package_index`: Lookup table

---

### Phase 10: Export & Validation

**Responsibility:** Write final files and validate

**Input:**
- Package manifest

**Processing:**
- Validate all files present
- Create output directory structure
- Write audio files
- Write EPUB file
- Write metadata files
- Generate export index

**Output:**
- Export directory with all files
- `export_index`: File locations and manifest
- File count and validation report

**Filesystem Write:** Yes (final export)

---

## Data Contracts

Each phase has strict input/output contracts defined in:
- `phase_XX_name/input_schema.py`: Input model
- `phase_XX_name/output_schema.py`: Output model

See `docs/examples/schemas/` for example JSON schemas.

## Testing

Each phase has:
- `phase_XX_name/tests/test_contracts.py`: Input/output validation
- `phase_XX_name/tests/test_processor.py`: Logic tests
- `phase_XX_name/tests/test_runner.py`: Integration tests

Run all tests:
```bash
python -m pytest pipeline/tests -q
```

Run non-live tests:
```bash
python -m pytest -m "not live" pipeline/tests -q
```

## Performance Notes

- **Phase 00 Fetch:** Network-dependent (1-10 seconds per chapter)
- **Phase 07 TTS:** Slowest phase (depends on TTS service)
- **Phases 01-06:** Fast (text processing)
- **Phases 08-10:** Medium (audio assembly, file I/O)

Total pipeline time: Dominated by network (fetch) and TTS.

## Error Handling

Each phase can produce:
- **Errors:** Critical issues that halt processing
- **Warnings:** Non-critical issues that log but continue

Common errors:
- Missing/invalid input schema
- Network failures (Phase 00)
- Unsupported source type (Phase 01)
- TTS service unavailable (Phase 07)

## Debugging

Each phase writes debug artifacts to:
```
<artifact_root>/phases/phase_XX_name/
├── meta.json              # Phase metadata
├── input_summary.json     # Input overview
├── output_summary.json    # Output overview
├── [phase-specific files] # Debug artifacts
```

Example: Phase 03 writes:
```
phases/phase_03_segmentation/
├── meta.json
├── segments.json
├── segment_summary.json
```

## Future Enhancements

- **Parallel Chapter Processing:** Process chapters independently
- **Streaming Pipeline:** Process without waiting for all chapters
- **Alternative TTS Backends:** Support multiple TTS services
- **Checkpoint/Resume:** Save state between phases
- **Caching:** Memoize expensive computations
- **Quality Metrics:** Add chapter-level quality scoring
