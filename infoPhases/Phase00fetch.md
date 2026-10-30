# Phase 00 Fetch

## Responsibility
Acquire web index/chapter content and return a `source` object for Phase 01.

## Input
- `index_url`
- `chapter_range`
- optional chapter examples for rule learning
- `settings`, `env`

## Output
- `source` with `type`, `url`, `chapters`, `chapter_range`
- standard metadata fields

## Notes
- Performs network fetches.
- Learns and persists domain rules when examples are provided.
