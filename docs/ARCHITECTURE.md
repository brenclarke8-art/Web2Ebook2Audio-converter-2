# Pipeline Architecture

## Overview

Web2Ebook2Audio Converter 2 is a phase-based content pipeline that transforms source material into structured audiobook export artifacts.

**Pipeline Flow:**
```
Web/EPUB/PDF/OCR/Text Input
    ↓
Phase 00: Bootstrap & Fetch (config + chapter acquisition)
    ↓
Phase 01: Source Normalization (chapter/payload extraction)
    ↓
Phase 02: Text Cleaning (HTML removal, normalization)
    ↓
Phase 03: Structural Segmentation (paragraph/section division)
    ↓
Phase 04: Character Discovery (canonical character IDs)
    ↓
Phase 05: Semantic Enrichment (speaker/dialogue attribution)
    ↓
Phase 06: Voice Assignment (character-to-voice mapping)
    ↓
Phase 07: TTS Generation (audio synthesis)
    ↓
Phase 08: Audio Stitching (chapter assembly)
    ↓
Phase 09: Final Packaging (EPUB + audio bundle)
    ↓
Phase 10: Export & Validation (output generation)
    ↓
Audiobook Artifacts (MP3/WAV + EPUB)
```

## Phase Contracts

### Consistent Architecture Pattern

Every phase follows the same pattern:

**Input:** `PhaseXXInput` schema
- Contracts from previous phase
- Settings from Phase 00 bootstrap

**Processing:** Pure deterministic logic
- No filesystem writes (only in debug.py)
- No logging side effects
- No network calls (except Phase 00 fetch)
- Deterministic outputs

**Output:** `PhaseXXOutput` schema
- Canonical contract for next phase
- Debug artifacts written by debug.py

**Structure:**
```
pipeline/phases/phase_XX_name/
├── input_schema.py      # Input contract definition
├── output_schema.py     # Output contract definition
├── processor.py         # Pure business logic
├── runner.py            # Orchestration wrapper
├── debug.py             # Debug artifact writer
├── tasks.md             # Phase specification
└── tests/               # Regression tests
```

## Design Decisions

### 1. Deterministic Outputs
- All timestamps set to `0.0` (not `time.time()`)
- All timings are fixed values
- Same input → same output every time
- Enables reliable regression testing

### 2. Separation of Concerns
- **Processor:** Pure logic only, no I/O
- **Debug:** Filesystem writes for artifacts
- **Runner:** Orchestration and error handling

### 3. Schema Contracts
- Each phase declares input/output schemas
- Schemas are Pydantic models (type-safe)
- Schemas match actual implementation
- No implicit coercions or conversions

### 4. No Context in Processors
- `process()` takes only input model
- No `context` parameter needed
- Stateless functions (pure logic)
- Easier testing and composition

### 5. Phase Numbering
- Phase 00: Bootstrap (config validation)
- Phase 00: Fetch (network calls)
- Phases 01-06: Core text processing
- Phase 07: TTS audio generation
- Phases 08-10: Assembly and export

## Data Flow

### Input Sources
1. **Web URLs:** fetch chapters via HTTP
2. **EPUB Files:** extract content from .epub
3. **PDF Files:** extract text via OCR
4. **OCR Results:** process OCR-extracted text
5. **Raw Text:** parse chapters from text

### Processing Pipeline

**Phase 00-01:** Normalization
- Extract chapters from diverse sources
- Normalize to common format
- Output: `chapter_index` + `raw_payloads`

**Phase 02-03:** Text Processing
- Remove HTML/formatting noise
- Split into structural units (segments)
- Output: `segments` with metadata

**Phase 04-06:** Semantic Analysis
- Discover and register characters
- Assign speaker/dialogue attribution
- Map characters to voice profiles
- Output: `enriched_segments` + `character_registry`

**Phase 07-10:** Audio Packaging
- Generate audio from text (TTS)
- Stitch audio into chapters
- Package with EPUB and metadata
- Export final artifacts

### Output Artifacts
- **Audio:** MP3/WAV files per chapter
- **EPUB:** Enhanced ebook format
- **Metadata:** Character guide, timing info
- **Index:** Chapter-to-file mapping

## Dependencies & Interactions

### Phase Dependencies
- Phase 00 → 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10
- Linear flow (no branching/merging)
- Each phase depends only on previous output

### External Integrations
- **Phase 00 Fetch:** HTTP requests (network)
- **Phase 07 TTS:** Text-to-speech library
- **Phase 10 Export:** File I/O operations

### Testing Strategy
- Unit tests: Processor logic isolation
- Integration tests: Phase-to-phase contracts
- Regression tests: Fixed input/output snapshots
- Live tests: Real network/TTS calls (optional)

## Error Handling

Each phase output includes:
- `errors: List[str]` - Critical issues
- `warnings: List[str]` - Non-critical issues
- `timings: Dict[str, float]` - Performance metrics
- `meta: Dict[str, Any]` - Metadata (phase, version, timestamp)

**Error Propagation:**
- Errors stop pipeline execution
- Warnings allow continuation
- Runner decides on error behavior

## Performance Considerations

1. **Deterministic:** Outputs always match (no timing variance)
2. **Stateless:** No shared state between phases
3. **Composable:** Phases can run independently
4. **Debuggable:** Debug artifacts for each phase
5. **Testable:** Regression snapshots locked in tests

## Future Extensions

- **Phase 07 Enhancement:** Support multiple TTS backends
- **Phase 06 Enhancement:** Add emotional voice selection
- **Parallel Processing:** Independent chapter processing
- **Streaming:** Process chapters without waiting for all
- **Caching:** Memoize expensive computations
