# tests/test_structured_output.py
"""
Unit tests for ebook_app.text.identify.structured_output.

Covers:
- Valid structured output parsed and post-processed correctly.
- Malformed JSON repaired successfully via repair_fn.
- Empty / whitespace text segments are filtered out.
- Missing speaker receives deterministic fallback assignment.
- CharacterRegistry consistency across multiple segments.
- character_type / segment_type is always a valid, non-empty value.
- sanitize_json_text handles code fences and embedded JSON.
- parse_structured_llm_response returns empty result on terminal failure.
- normalize_segments uses the CharacterRegistry to assign stable character_ids.
"""
from __future__ import annotations

import json

import pytest

from ebook_app.text.identify.structured_output import (
    CharacterRegistry,
    LLMResultInput,
    LLMSegmentInput,
    _coerce_type,
    normalize_segments,
    parse_structured_llm_response,
    sanitize_json_text,
)


# ---------------------------------------------------------------------------
# sanitize_json_text
# ---------------------------------------------------------------------------


def test_sanitize_strips_json_code_fence():
    raw = '```json\n{"segments": []}\n```'
    cleaned = sanitize_json_text(raw)
    assert json.loads(cleaned) == {"segments": []}


def test_sanitize_strips_plain_code_fence():
    raw = "```\n[1, 2, 3]\n```"
    cleaned = sanitize_json_text(raw)
    assert json.loads(cleaned) == [1, 2, 3]


def test_sanitize_plain_json_unchanged():
    raw = '{"segments": []}'
    cleaned = sanitize_json_text(raw)
    assert json.loads(cleaned) == {"segments": []}


def test_sanitize_extracts_embedded_json():
    raw = "Here is the result: [1, 2] — done."
    cleaned = sanitize_json_text(raw)
    assert json.loads(cleaned) == [1, 2]


def test_sanitize_raises_when_no_json_found():
    with pytest.raises(ValueError):
        sanitize_json_text("no json here at all")


def test_sanitize_empty_string_raises():
    with pytest.raises(ValueError):
        sanitize_json_text("")


# ---------------------------------------------------------------------------
# _coerce_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("dialogue", "dialogue"),
        ("DIALOGUE", "dialogue"),
        ("thought", "thought"),
        ("narration", "narration"),
        ("narrator", "narration"),
        ("Narrator", "narration"),
        ("system", "system"),
        ("unknown_type", "narration"),
        ("", "narration"),
        (None, "narration"),
    ],
)
def test_coerce_type(value, expected):
    assert _coerce_type(value) == expected


# ---------------------------------------------------------------------------
# LLMSegmentInput schema validation
# ---------------------------------------------------------------------------


def test_llm_segment_input_defaults():
    seg = LLMSegmentInput()
    assert seg.line_id == ""
    assert seg.raw_text == ""
    assert seg.normalized_text == ""
    assert seg.speaker_name is None
    assert seg.speaker_confidence == 0.0
    assert seg.character_type == "narration"
    assert seg.voice_hint is None


def test_llm_segment_input_coerces_character_type():
    seg = LLMSegmentInput(character_type="Narrator")
    assert seg.character_type == "narration"


def test_llm_segment_input_strips_normalized_text():
    seg = LLMSegmentInput(normalized_text="  hello world  ")
    assert seg.normalized_text == "hello world"


def test_llm_segment_input_coerces_confidence_from_string():
    seg = LLMSegmentInput(speaker_confidence="0.75")
    assert seg.speaker_confidence == pytest.approx(0.75)


def test_llm_segment_input_confidence_invalid_defaults_to_zero():
    seg = LLMSegmentInput(speaker_confidence="not-a-number")
    assert seg.speaker_confidence == 0.0


# ---------------------------------------------------------------------------
# LLMResultInput schema
# ---------------------------------------------------------------------------


def test_llm_result_input_empty_segments():
    result = LLMResultInput()
    assert result.segments == []


def test_llm_result_input_valid_full_segment():
    data = {
        "segments": [
            {
                "line_id": "ch01_s0",
                "raw_text": '"Hello," said Alice.',
                "normalized_text": "Hello, said Alice.",
                "speaker_name": "Alice",
                "speaker_confidence": 0.9,
                "character_type": "dialogue",
                "voice_hint": "female_adult",
            }
        ]
    }
    result = LLMResultInput.model_validate(data)
    assert len(result.segments) == 1
    seg = result.segments[0]
    assert seg.line_id == "ch01_s0"
    assert seg.normalized_text == "Hello, said Alice."
    assert seg.speaker_name == "Alice"
    assert seg.speaker_confidence == pytest.approx(0.9)
    assert seg.character_type == "dialogue"
    assert seg.voice_hint == "female_adult"


def test_llm_result_input_accepts_bare_list():
    """parse_structured_llm_response wraps bare lists; direct validation requires dict."""
    raw = json.dumps(
        [
            {
                "line_id": "s1",
                "normalized_text": "Narration.",
                "character_type": "narration",
            }
        ]
    )
    result = parse_structured_llm_response(raw)
    assert len(result.segments) == 1
    assert result.segments[0].character_type == "narration"


# ---------------------------------------------------------------------------
# parse_structured_llm_response
# ---------------------------------------------------------------------------


def test_parse_valid_json_returns_result():
    payload = {
        "segments": [
            {
                "line_id": "s1",
                "raw_text": "She whispered.",
                "normalized_text": "She whispered.",
                "speaker_name": "Eva",
                "speaker_confidence": 0.88,
                "character_type": "narration",
            }
        ]
    }
    result = parse_structured_llm_response(json.dumps(payload))
    assert len(result.segments) == 1
    assert result.segments[0].speaker_name == "Eva"


def test_parse_markdown_wrapped_json():
    payload = {"segments": [{"normalized_text": "Hello.", "character_type": "dialogue", "speaker_name": "Bob"}]}
    raw = f"```json\n{json.dumps(payload)}\n```"
    result = parse_structured_llm_response(raw)
    assert result.segments[0].speaker_name == "Bob"
    assert result.segments[0].character_type == "dialogue"


def test_parse_bare_list_accepted():
    segments = [
        {"line_id": "s1", "normalized_text": "Narration.", "character_type": "narration"}
    ]
    result = parse_structured_llm_response(json.dumps(segments))
    assert len(result.segments) == 1


def test_parse_malformed_json_without_repair_returns_empty():
    result = parse_structured_llm_response("this is not json")
    assert result.segments == []


def test_parse_malformed_json_repaired_successfully():
    """repair_fn returns valid JSON; parse uses the repaired version."""
    valid_payload = {"segments": [{"normalized_text": "Fixed.", "character_type": "narration"}]}

    def _repair(_broken: str) -> str:
        return json.dumps(valid_payload)

    result = parse_structured_llm_response("bad json", repair_fn=_repair)
    assert len(result.segments) == 1
    assert result.segments[0].normalized_text == "Fixed."


def test_parse_repair_fn_also_fails_returns_empty():
    def _bad_repair(_: str) -> str:
        return "still broken"

    result = parse_structured_llm_response("also broken", repair_fn=_bad_repair)
    assert result.segments == []


def test_parse_repair_fn_raises_returns_empty():
    def _raising_repair(_: str) -> str:
        raise RuntimeError("repair exploded")

    result = parse_structured_llm_response("broken", repair_fn=_raising_repair)
    assert result.segments == []


# ---------------------------------------------------------------------------
# normalize_segments
# ---------------------------------------------------------------------------


def _make_result(*segs: dict) -> LLMResultInput:
    return LLMResultInput(segments=[LLMSegmentInput(**s) for s in segs])


def test_normalize_empty_text_filtered():
    result = _make_result(
        {"normalized_text": "", "character_type": "narration"},
        {"normalized_text": "  ", "character_type": "dialogue"},
        {"normalized_text": "Real text.", "character_type": "narration"},
    )
    registry = CharacterRegistry()
    output = normalize_segments(result, registry)
    assert len(output) == 1
    assert output[0]["text"] == "Real text."


def test_normalize_missing_speaker_fallback_narration():
    result = _make_result({"normalized_text": "Narration.", "character_type": "narration", "speaker_name": None})
    registry = CharacterRegistry()
    output = normalize_segments(result, registry, default_narrator="Narrator")
    assert output[0]["speaker"] == "Narrator"


def test_normalize_missing_speaker_fallback_dialogue():
    result = _make_result({"normalized_text": "Said something.", "character_type": "dialogue", "speaker_name": None})
    registry = CharacterRegistry()
    output = normalize_segments(result, registry, default_unknown="Unknown")
    assert output[0]["speaker"] == "Unknown"


def test_normalize_missing_speaker_fallback_thought():
    result = _make_result({"normalized_text": "Thought something.", "character_type": "thought", "speaker_name": None})
    registry = CharacterRegistry()
    output = normalize_segments(result, registry, default_unknown="Unknown")
    assert output[0]["speaker"] == "Unknown"


def test_normalize_speaker_name_assigned():
    result = _make_result({"normalized_text": "Hello.", "character_type": "dialogue", "speaker_name": "Alice"})
    registry = CharacterRegistry()
    output = normalize_segments(result, registry)
    assert output[0]["speaker"] == "Alice"


def test_normalize_segment_type_always_populated():
    """Even with an invalid character_type, segment_type is always valid."""
    result = _make_result({"normalized_text": "Text.", "character_type": "GARBAGE_TYPE"})
    registry = CharacterRegistry()
    output = normalize_segments(result, registry)
    assert output[0]["segment_type"] in {"dialogue", "thought", "narration", "system"}


def test_normalize_segment_type_coerced_from_narrator():
    result = _make_result({"normalized_text": "Text.", "character_type": "narrator"})
    registry = CharacterRegistry()
    output = normalize_segments(result, registry)
    assert output[0]["segment_type"] == "narration"


def test_normalize_required_fields_present():
    result = _make_result({
        "line_id": "s1",
        "normalized_text": "Hello world.",
        "character_type": "dialogue",
        "speaker_name": "Bob",
        "speaker_confidence": 0.8,
        "voice_hint": "male_calm",
    })
    registry = CharacterRegistry()
    output = normalize_segments(result, registry)
    assert len(output) == 1
    item = output[0]
    for key in ("line_id", "text", "segment_type", "speaker", "character_id", "speaker_confidence", "voice_hint"):
        assert key in item, f"Missing required key: {key}"


# ---------------------------------------------------------------------------
# CharacterRegistry
# ---------------------------------------------------------------------------


def test_character_registry_creates_new_entry():
    reg = CharacterRegistry()
    char = reg.get_or_create("Alice")
    assert char["display_name"] == "Alice"
    assert char["character_id"].startswith("char_")


def test_character_registry_same_name_returns_same_id():
    reg = CharacterRegistry()
    c1 = reg.get_or_create("Alice")
    c2 = reg.get_or_create("Alice")
    assert c1["character_id"] == c2["character_id"]


def test_character_registry_case_insensitive():
    reg = CharacterRegistry()
    c1 = reg.get_or_create("Alice")
    c2 = reg.get_or_create("ALICE")
    c3 = reg.get_or_create("alice")
    assert c1["character_id"] == c2["character_id"] == c3["character_id"]


def test_character_registry_different_names_different_ids():
    reg = CharacterRegistry()
    c1 = reg.get_or_create("Alice")
    c2 = reg.get_or_create("Bob")
    assert c1["character_id"] != c2["character_id"]


def test_character_registry_incremental_ids():
    reg = CharacterRegistry()
    c1 = reg.get_or_create("Alice")
    c2 = reg.get_or_create("Bob")
    # IDs are sequential
    id1 = int(c1["character_id"].replace("char_", ""))
    id2 = int(c2["character_id"].replace("char_", ""))
    assert id2 == id1 + 1


def test_character_registry_empty_name_uses_unknown_key():
    reg = CharacterRegistry()
    c1 = reg.get_or_create("")
    c2 = reg.get_or_create("   ")
    assert c1["character_id"] == c2["character_id"]


def test_character_registry_consistency_across_multiple_segments():
    """Same speaker in multiple segments always maps to the same character_id."""
    result = _make_result(
        {"normalized_text": "Hello.", "character_type": "dialogue", "speaker_name": "Carol"},
        {"normalized_text": "Narration.", "character_type": "narration", "speaker_name": "Narrator"},
        {"normalized_text": "Goodbye.", "character_type": "dialogue", "speaker_name": "Carol"},
    )
    registry = CharacterRegistry()
    output = normalize_segments(result, registry)
    carol_ids = {item["character_id"] for item in output if item["speaker"] == "Carol"}
    assert len(carol_ids) == 1, "Carol must have exactly one consistent character_id"


def test_character_registry_all_characters():
    reg = CharacterRegistry()
    reg.get_or_create("Alice")
    reg.get_or_create("Bob")
    all_chars = reg.all_characters()
    names = {c["display_name"] for c in all_chars}
    assert names == {"Alice", "Bob"}


# ---------------------------------------------------------------------------
# End-to-end: parse + normalize
# ---------------------------------------------------------------------------


def test_end_to_end_valid_payload():
    payload = {
        "segments": [
            {
                "line_id": "s1",
                "raw_text": '"We should go," Alice said.',
                "normalized_text": "We should go, Alice said.",
                "speaker_name": "Alice",
                "speaker_confidence": 0.91,
                "character_type": "dialogue",
                "voice_hint": "female_adult_calm",
            },
            {
                "line_id": "s2",
                "raw_text": "Bob nodded.",
                "normalized_text": "Bob nodded.",
                "speaker_name": "Narrator",
                "speaker_confidence": 0.0,
                "character_type": "narration",
            },
        ]
    }
    registry = CharacterRegistry()
    result = parse_structured_llm_response(json.dumps(payload))
    output = normalize_segments(result, registry)

    assert len(output) == 2
    assert output[0]["text"] == "We should go, Alice said."
    assert output[0]["speaker"] == "Alice"
    assert output[0]["segment_type"] == "dialogue"
    assert output[0]["voice_hint"] == "female_adult_calm"

    assert output[1]["text"] == "Bob nodded."
    assert output[1]["segment_type"] == "narration"


def test_end_to_end_whitespace_segments_dropped():
    payload = {
        "segments": [
            {"normalized_text": "   ", "character_type": "narration"},
            {"normalized_text": "Real line.", "character_type": "narration"},
            {"normalized_text": "", "character_type": "dialogue"},
        ]
    }
    registry = CharacterRegistry()
    result = parse_structured_llm_response(json.dumps(payload))
    output = normalize_segments(result, registry)
    assert len(output) == 1
    assert output[0]["text"] == "Real line."


def test_end_to_end_all_segments_have_required_fields():
    payload = {
        "segments": [
            {"normalized_text": "Alpha.", "character_type": "narration"},
            {"normalized_text": "Beta.", "character_type": "dialogue", "speaker_name": "Bob"},
        ]
    }
    registry = CharacterRegistry()
    result = parse_structured_llm_response(json.dumps(payload))
    output = normalize_segments(result, registry)
    for item in output:
        for key in ("line_id", "text", "segment_type", "speaker", "character_id", "speaker_confidence", "voice_hint"):
            assert key in item
        assert item["segment_type"] in {"dialogue", "thought", "narration", "system"}
        assert item["speaker"]
        assert item["character_id"]


# ---------------------------------------------------------------------------
# segmenter._validate_pass2 fix: wrapped {"segments":[...]} accepted
# ---------------------------------------------------------------------------


def test_validate_pass2_accepts_wrapped_segments_envelope():
    """
    Regression: _validate_pass2 must unwrap {"segments": [...]} before the
    single-object dict check, otherwise multi-segment wrapped responses are
    silently dropped.
    """
    from ebook_app.text.segment.segmenter import DialogueSegmentationService

    class _WrappedClient:
        def ask_json_any(self, *, system, user, chapter_id):
            if chapter_id.endswith("_p0"):
                return {"summary": "Test."}
            if chapter_id.endswith("_p1"):
                return [{"name": "Alice", "gender": "female", "confidence": 0.9}]
            if chapter_id.endswith("_p2"):
                id_lines = json.loads(user)
                items = [
                    {"id": entry["id"], "type": "dialogue", "speaker": "Alice"}
                    for entry in id_lines
                ]
                # Wrap in {"segments": [...]} — this was previously broken
                return {"segments": items}
            return []

    service = DialogueSegmentationService(client=_WrappedClient())
    result = service.parse(text='"Hello."\n"Goodbye."', chapter_id="ch-wrap-fix")

    assert result.diagnostics.validation_passed
    assert all(s.type == "dialogue" for s in result.segments)
    assert all(s.speaker == "Alice" for s in result.segments)


# ---------------------------------------------------------------------------
# segmenter end-to-end: empty text segments dropped + guaranteed type/speaker
# ---------------------------------------------------------------------------


def test_segmenter_drops_whitespace_only_segments():
    """parse() must not emit segments with empty/whitespace text."""
    from ebook_app.text.segment.segmenter import DialogueSegmentationService

    class _SpaceClient:
        def ask_json_any(self, *, system, user, chapter_id):
            if chapter_id.endswith("_p0"):
                return {"summary": "Test."}
            if chapter_id.endswith("_p1"):
                return []
            if chapter_id.endswith("_p2"):
                id_lines = json.loads(user)
                # Return valid types/speakers
                return [
                    {"id": entry["id"], "type": "narration", "speaker": "narrator"}
                    for entry in id_lines
                ]
            return []

    service = DialogueSegmentationService(client=_SpaceClient())
    # Feed a mix of real content and whitespace-only paragraphs
    result = service.parse(text="Real paragraph.\n\n   \n\nAnother real one.", chapter_id="ch-space")

    for seg in result.segments:
        assert seg.text.strip() != "", f"Empty segment found: {seg!r}"


def test_segmenter_guarantees_type_and_speaker_on_every_segment():
    """Every segment returned by parse() must have a non-empty type and speaker."""
    from ebook_app.text.segment.segmenter import DialogueSegmentationService

    class _WeirdClient:
        def ask_json_any(self, *, system, user, chapter_id):
            if chapter_id.endswith("_p0"):
                return {"summary": "Test."}
            if chapter_id.endswith("_p1"):
                return []
            if chapter_id.endswith("_p2"):
                id_lines = json.loads(user)
                # Return garbage types / empty speakers
                return [
                    {"id": entry["id"], "type": "garbage_type", "speaker": ""}
                    for entry in id_lines
                ]
            return []

    service = DialogueSegmentationService(client=_WeirdClient())
    result = service.parse(text="Some text here.", chapter_id="ch-guarantee")

    valid_types = {"dialogue", "thought", "narration", "system"}
    for seg in result.segments:
        assert seg.type in valid_types, f"Invalid type: {seg.type!r}"
        assert seg.speaker, f"Empty speaker on segment: {seg!r}"
