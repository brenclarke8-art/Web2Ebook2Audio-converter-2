"""
Tests for ebook_app/text/parse/structured_llm_pipeline.py.

Scenarios covered
-----------------
- valid structured output passes validation and post-processing
- malformed JSON (code fences, trailing commas, smart quotes) repaired successfully
- empty/whitespace-only segments are filtered out
- missing speaker is replaced by deterministic fallback (Narrator / Unknown)
- CharacterRegistry assigns consistent IDs across multiple segments
- character_type always populated (defaults to "narration")
- validate_and_post_process repair_callback path
- LLMSegment schema rejects out-of-range confidence values
- LLMSegment normalized_text defaults to raw_text when omitted
- post_process_segments accepts both field-name aliases
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from ebook_app.text.parse.structured_llm_pipeline import (
    CharacterRegistry,
    LLMExtractionResult,
    LLMSegment,
    parse_llm_json,
    post_process_segments,
    validate_and_post_process,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_segment(
    line_id: str = "seg_0",
    raw_text: str = "Hello there.",
    normalized_text: str = "",
    speaker_name: str | None = "Alice",
    speaker_confidence: float = 0.9,
    character_type: str = "dialogue",
    voice_hint: str | None = None,
) -> dict:
    seg: dict = {
        "line_id": line_id,
        "raw_text": raw_text,
        "normalized_text": normalized_text or raw_text,
        "speaker_name": speaker_name,
        "speaker_confidence": speaker_confidence,
        "character_type": character_type,
    }
    if voice_hint is not None:
        seg["voice_hint"] = voice_hint
    return seg


# ===========================================================================
# LLMSegment Pydantic schema
# ===========================================================================


class Test_LLMSegment:
    def test_valid_segment_passes(self):
        seg = LLMSegment(
            line_id="s1",
            raw_text="We must go now.",
            normalized_text="We must go now.",
            speaker_name="Alice",
            speaker_confidence=0.85,
            character_type="dialogue",
        )
        assert seg.line_id == "s1"
        assert seg.character_type == "dialogue"

    def test_normalized_text_defaults_to_raw_text_when_omitted(self):
        seg = LLMSegment(line_id="s1", raw_text="Hello.")
        # normalized_text was omitted — effective_text() should fall back to raw_text
        assert seg.effective_text() == "Hello."

    def test_normalized_text_stripped(self):
        seg = LLMSegment(line_id="s1", raw_text="X", normalized_text="  trimmed  ")
        assert seg.normalized_text == "trimmed"

    def test_speaker_name_none_accepted(self):
        seg = LLMSegment(line_id="s1", raw_text="X", speaker_name=None)
        assert seg.speaker_name is None

    def test_speaker_name_empty_string_coerced_to_none(self):
        seg = LLMSegment(line_id="s1", raw_text="X", speaker_name="   ")
        assert seg.speaker_name is None

    def test_character_type_defaults_to_narration(self):
        seg = LLMSegment(line_id="s1", raw_text="X")
        assert seg.character_type == "narration"

    def test_invalid_character_type_coerced_to_narration(self):
        # The field_validator normalises unrecognised types to "narration" at runtime.
        # The type: ignore suppresses the static type-checker, which correctly
        # flags the literal mismatch — the coercion is intentional for LLM robustness.
        seg = LLMSegment(line_id="s1", raw_text="X", character_type="monologue")  # type: ignore[arg-type]
        assert seg.character_type == "narration"

    def test_invalid_character_type_via_model_validate_coerced_to_narration(self):
        # model_validate() (used when parsing dicts from JSON) also coerces invalid types.
        seg = LLMSegment.model_validate({"line_id": "s1", "raw_text": "X", "character_type": "soliloquy"})
        assert seg.character_type == "narration"

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            LLMSegment(line_id="s1", raw_text="X", speaker_confidence=1.5)

    def test_negative_confidence_rejected(self):
        with pytest.raises(ValidationError):
            LLMSegment(line_id="s1", raw_text="X", speaker_confidence=-0.1)


# ===========================================================================
# LLMExtractionResult schema
# ===========================================================================


class Test_LLMExtractionResult:
    def test_valid_result_passes(self):
        data = {
            "segments": [
                {
                    "line_id": "s1",
                    "raw_text": "Hello.",
                    "normalized_text": "Hello.",
                    "speaker_name": "Alice",
                    "speaker_confidence": 0.9,
                    "character_type": "dialogue",
                }
            ]
        }
        result = LLMExtractionResult.model_validate(data)
        assert len(result.segments) == 1
        assert result.segments[0].speaker_name == "Alice"

    def test_empty_segments_list_accepted(self):
        result = LLMExtractionResult.model_validate({"segments": []})
        assert result.segments == []


# ===========================================================================
# CharacterRegistry
# ===========================================================================


class Test_CharacterRegistry:
    def test_first_speaker_gets_char_1(self):
        reg = CharacterRegistry()
        info = reg.get_or_create("Alice")
        assert info["character_id"] == "char_1"
        assert info["display_name"] == "Alice"

    def test_same_name_returns_same_id(self):
        reg = CharacterRegistry()
        id1 = reg.get_or_create("Alice")["character_id"]
        id2 = reg.get_or_create("Alice")["character_id"]
        assert id1 == id2

    def test_name_lookup_is_case_insensitive(self):
        reg = CharacterRegistry()
        id_lower = reg.get_or_create("alice")["character_id"]
        id_upper = reg.get_or_create("ALICE")["character_id"]
        assert id_lower == id_upper

    def test_different_names_get_different_ids(self):
        reg = CharacterRegistry()
        id_alice = reg.get_or_create("Alice")["character_id"]
        id_bob = reg.get_or_create("Bob")["character_id"]
        assert id_alice != id_bob

    def test_ids_are_sequential(self):
        reg = CharacterRegistry()
        reg.get_or_create("Alice")
        reg.get_or_create("Bob")
        reg.get_or_create("Carol")
        ids = [info["character_id"] for info in reg.all_characters()]
        assert ids == ["char_1", "char_2", "char_3"]

    def test_all_characters_returns_registered_entries(self):
        reg = CharacterRegistry()
        reg.get_or_create("Alice")
        reg.get_or_create("Bob")
        chars = reg.all_characters()
        names = [c["display_name"] for c in chars]
        assert "Alice" in names
        assert "Bob" in names

    def test_empty_string_gets_narrator_key(self):
        reg = CharacterRegistry()
        info = reg.get_or_create("")
        assert info["display_name"] == "Narrator"

    def test_len(self):
        reg = CharacterRegistry()
        assert len(reg) == 0
        reg.get_or_create("Alice")
        assert len(reg) == 1
        reg.get_or_create("Bob")
        assert len(reg) == 2

    def test_consistency_across_multiple_segments(self):
        """The same speaker appearing in many segments always resolves to the same ID."""
        reg = CharacterRegistry()
        speakers = ["Alice", "Bob", "Alice", "Carol", "Bob", "Alice"]
        ids = [reg.get_or_create(name)["character_id"] for name in speakers]
        assert ids[0] == ids[2] == ids[5], "Alice must map to the same ID every time"
        assert ids[1] == ids[4], "Bob must map to the same ID every time"
        assert ids[0] != ids[1] != ids[3], "distinct speakers must have distinct IDs"


# ===========================================================================
# parse_llm_json
# ===========================================================================


class Test_ParseLlmJson:
    def test_passes_through_dict(self):
        data = {"key": "value"}
        assert parse_llm_json(data) is data

    def test_passes_through_list(self):
        data = [1, 2, 3]
        assert parse_llm_json(data) is data

    def test_parses_plain_json_string(self):
        result = parse_llm_json('{"segments": []}')
        assert result == {"segments": []}

    def test_strips_code_fence_json(self):
        fenced = '```json\n{"segments": []}\n```'
        result = parse_llm_json(fenced)
        assert result == {"segments": []}

    def test_strips_code_fence_no_language(self):
        fenced = '```\n[1, 2, 3]\n```'
        result = parse_llm_json(fenced)
        assert result == [1, 2, 3]

    def test_repairs_trailing_comma(self):
        malformed = '[{"id":"a","type":"narration",}]'
        result = parse_llm_json(malformed)
        assert result[0]["id"] == "a"

    def test_repairs_smart_quotes(self):
        # Build a string that uses LEFT/RIGHT DOUBLE QUOTATION MARKs (\u201c / \u201d)
        # instead of straight ASCII quotes — a common LLM output artifact.
        ldqm = "\u201c"  # "  LEFT DOUBLE QUOTATION MARK
        rdqm = "\u201d"  # "  RIGHT DOUBLE QUOTATION MARK
        malformed = f'[{{{ldqm}id{rdqm}:{ldqm}a{rdqm},{ldqm}type{rdqm}:{ldqm}narration{rdqm}}}]'
        result = parse_llm_json(malformed)
        assert result[0]["id"] == "a"

    def test_repairs_fenced_plus_trailing_comma(self):
        malformed = '```json\n[{"id":"ch1_0","type":"narration","speaker":"narrator",}]\n```'
        result = parse_llm_json(malformed)
        assert result[0]["type"] == "narration"

    def test_raises_value_error_on_non_json(self):
        with pytest.raises(ValueError, match="Unable to parse"):
            parse_llm_json("NOT JSON AT ALL !!!")

    def test_raises_value_error_on_empty_string(self):
        with pytest.raises(ValueError, match="empty"):
            parse_llm_json("")

    def test_raises_value_error_on_none(self):
        with pytest.raises(ValueError, match="empty"):
            parse_llm_json(None)

    def test_extracts_snippet_from_surrounding_text(self):
        noisy = 'Here is the JSON:\n[{"id":"a"}]\nEnd.'
        result = parse_llm_json(noisy)
        assert result[0]["id"] == "a"


# ===========================================================================
# post_process_segments
# ===========================================================================


class Test_PostProcessSegments:
    def test_valid_segment_passes_through(self):
        reg = CharacterRegistry()
        segs = [
            {
                "line_id": "s1",
                "text": "Hello there.",
                "type": "dialogue",
                "speaker": "Alice",
            }
        ]
        result = post_process_segments(segs, reg)
        assert len(result) == 1
        assert result[0]["text"] == "Hello there."
        assert result[0]["segment_type"] == "dialogue"
        assert result[0]["speaker"] == "Alice"
        assert result[0]["character_id"] == "char_1"

    def test_empty_text_segments_are_dropped(self):
        reg = CharacterRegistry()
        segs = [
            {"line_id": "s1", "text": "   ", "type": "narration", "speaker": "narrator"},
            {"line_id": "s2", "text": "", "type": "narration", "speaker": "narrator"},
            {"line_id": "s3", "text": "Actual content.", "type": "narration", "speaker": "narrator"},
        ]
        result = post_process_segments(segs, reg)
        assert len(result) == 1
        assert result[0]["text"] == "Actual content."

    def test_whitespace_only_raw_text_dropped(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "raw_text": "   ", "type": "narration"}]
        result = post_process_segments(segs, reg)
        assert result == []

    def test_missing_speaker_gets_narrator_fallback_for_narration(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "text": "The sun rose.", "type": "narration", "speaker": ""}]
        result = post_process_segments(segs, reg)
        assert result[0]["speaker"] == "Narrator"

    def test_missing_speaker_gets_unknown_fallback_for_dialogue(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "text": '"Who is there?"', "type": "dialogue", "speaker": ""}]
        result = post_process_segments(segs, reg)
        assert result[0]["speaker"] == "Unknown"

    def test_none_speaker_gets_narrator_fallback(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "text": "Narration.", "type": "narration", "speaker": None}]
        result = post_process_segments(segs, reg)
        assert result[0]["speaker"] == "Narrator"

    def test_null_like_speaker_strings_fall_back_to_narrator(self):
        """'none', 'n/a', 'null', 'undefined' (any case) should be treated as missing."""
        reg = CharacterRegistry()
        for null_val in ("none", "None", "NONE", "n/a", "N/A", "null", "undefined"):
            segs = [{"line_id": "s1", "text": "Narration.", "type": "narration", "speaker": null_val}]
            result = post_process_segments(segs, CharacterRegistry())
            assert result[0]["speaker"] == "Narrator", f"Expected Narrator for speaker={null_val!r}"

    def test_invalid_type_defaults_to_narration(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "text": "Text.", "type": "monologue", "speaker": "Alice"}]
        result = post_process_segments(segs, reg)
        assert result[0]["segment_type"] == "narration"

    def test_missing_type_defaults_to_narration(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "text": "Text.", "speaker": "Alice"}]
        result = post_process_segments(segs, reg)
        assert result[0]["segment_type"] == "narration"

    def test_speaker_trailing_punctuation_stripped(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "text": "Hello.", "type": "dialogue", "speaker": "Alice."}]
        result = post_process_segments(segs, reg)
        assert result[0]["speaker"] == "Alice"

    def test_accepts_speaker_name_alias(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "text": "Hello.", "type": "dialogue", "speaker_name": "Bob"}]
        result = post_process_segments(segs, reg)
        assert result[0]["speaker"] == "Bob"

    def test_accepts_normalized_text_alias(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "normalized_text": "  Hello!  ", "type": "dialogue", "speaker": "Alice"}]
        result = post_process_segments(segs, reg)
        assert result[0]["text"] == "Hello!"

    def test_accepts_paragraph_id_alias(self):
        reg = CharacterRegistry()
        segs = [{"paragraph_id": "ch1_p0", "text": "Hello.", "type": "narration", "speaker": "narrator"}]
        result = post_process_segments(segs, reg)
        assert result[0]["line_id"] == "ch1_p0"

    def test_character_id_consistent_across_segments(self):
        """The same speaker always gets the same character_id."""
        reg = CharacterRegistry()
        segs = [
            {"line_id": "s1", "text": "Hi.", "type": "dialogue", "speaker": "Alice"},
            {"line_id": "s2", "text": "Hello.", "type": "narration", "speaker": "narrator"},
            {"line_id": "s3", "text": "Bye.", "type": "dialogue", "speaker": "Alice"},
        ]
        result = post_process_segments(segs, reg)
        assert result[0]["character_id"] == result[2]["character_id"]
        assert result[0]["character_id"] != result[1]["character_id"]

    def test_voice_hint_preserved(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "text": "Hi.", "type": "dialogue", "speaker": "Alice", "voice_hint": "calm_female"}]
        result = post_process_segments(segs, reg)
        assert result[0]["voice_hint"] == "calm_female"

    def test_voice_hint_none_when_absent(self):
        reg = CharacterRegistry()
        segs = [{"line_id": "s1", "text": "Hi.", "type": "narration", "speaker": "narrator"}]
        result = post_process_segments(segs, reg)
        assert result[0]["voice_hint"] is None

    def test_all_valid_types_accepted(self):
        reg = CharacterRegistry()
        for seg_type in ("dialogue", "thought", "narration"):
            segs = [{"line_id": "s1", "text": "Text.", "type": seg_type, "speaker": "Alice"}]
            result = post_process_segments(segs, reg)
            assert result[0]["segment_type"] == seg_type

    def test_type_classification_always_populated(self):
        """Every output segment must have a non-empty segment_type."""
        reg = CharacterRegistry()
        segs = [
            {"line_id": "s1", "text": "Narration."},  # no type at all
            {"line_id": "s2", "text": '"Hi."', "type": "UNKNOWN_TYPE"},
            {"line_id": "s3", "text": '"Bye."', "type": "dialogue"},
        ]
        result = post_process_segments(segs, reg)
        assert all(r["segment_type"] in {"dialogue", "thought", "narration"} for r in result)

    def test_empty_input_returns_empty_list(self):
        reg = CharacterRegistry()
        assert post_process_segments([], reg) == []


# ===========================================================================
# validate_and_post_process
# ===========================================================================


class Test_ValidateAndPostProcess:
    def _make_valid_raw(self) -> list:
        return [
            {
                "line_id": "s1",
                "raw_text": "Hello.",
                "normalized_text": "Hello.",
                "speaker_name": "Alice",
                "speaker_confidence": 0.9,
                "character_type": "dialogue",
            }
        ]

    def test_valid_list_response_succeeds(self):
        reg = CharacterRegistry()
        result, success = validate_and_post_process(self._make_valid_raw(), reg)
        assert success
        assert len(result) == 1
        assert result[0]["speaker"] == "Alice"
        assert result[0]["segment_type"] == "dialogue"

    def test_valid_wrapped_response_succeeds(self):
        reg = CharacterRegistry()
        wrapped = {"segments": self._make_valid_raw()}
        result, success = validate_and_post_process(json.dumps(wrapped), reg)
        assert success
        assert len(result) == 1

    def test_fenced_json_is_accepted(self):
        reg = CharacterRegistry()
        fenced = f"```json\n{json.dumps(self._make_valid_raw())}\n```"
        result, success = validate_and_post_process(fenced, reg)
        assert success
        assert result[0]["speaker"] == "Alice"

    def test_malformed_json_repaired_via_callback(self):
        """repair_callback provides a corrected response when primary parse fails."""
        reg = CharacterRegistry()
        valid_data = self._make_valid_raw()

        def _repair(raw):
            return valid_data

        result, success = validate_and_post_process("NOT JSON", reg, repair_callback=_repair)
        assert success
        assert len(result) == 1

    def test_empty_segments_filtered_end_to_end(self):
        reg = CharacterRegistry()
        raw = [
            {
                "line_id": "s1",
                "raw_text": "   ",
                "normalized_text": "",
                "speaker_name": "Alice",
                "speaker_confidence": 0.9,
                "character_type": "dialogue",
            },
            {
                "line_id": "s2",
                "raw_text": "Hello.",
                "normalized_text": "Hello.",
                "speaker_name": "Alice",
                "speaker_confidence": 0.9,
                "character_type": "dialogue",
            },
        ]
        result, success = validate_and_post_process(raw, reg)
        assert success
        assert len(result) == 1
        assert result[0]["text"] == "Hello."

    def test_missing_speaker_fallback_applied_end_to_end(self):
        reg = CharacterRegistry()
        raw = [
            {
                "line_id": "s1",
                "raw_text": "Narration.",
                "normalized_text": "Narration.",
                "speaker_name": None,
                "speaker_confidence": 0.0,
                "character_type": "narration",
            }
        ]
        result, success = validate_and_post_process(raw, reg)
        assert success
        assert result[0]["speaker"] == "Narrator"

    def test_all_invalid_returns_false_and_empty(self):
        reg = CharacterRegistry()
        result, success = validate_and_post_process("NOT JSON", reg)
        assert not success
        assert result == []

    def test_repair_callback_failure_returns_false(self):
        """If both primary parse and repair_callback fail, return ([], False)."""
        reg = CharacterRegistry()

        def _broken_repair(raw):
            raise RuntimeError("repair failed")

        result, success = validate_and_post_process("GARBAGE", reg, repair_callback=_broken_repair)
        assert not success
        assert result == []


# ===========================================================================
# _validate_pass2 dead-code regression (segmenter.py)
# ===========================================================================


class Test_ValidatePass2SegmentsEnvelope:
    """The segmenter must now correctly unwrap {"segments": [...]} envelopes."""

    def test_segments_envelope_is_unwrapped(self):
        from ebook_app.text.segment.segmenter import DialogueSegmentationService

        # The segmenter calls the client with chapter_id suffixed by the pass
        # number (_p0 = summary, _p1 = character extraction, _p2 = type/speaker).
        # For a single-chunk parse with chapter_id="ch-envelope", the client sees
        # chapter_ids "ch-envelope_p0", "ch-envelope_p1", "ch-envelope_p2".
        class _EnvelopeClient:
            def ask_json_any(self, *, system, user, chapter_id):
                if chapter_id.endswith("_p0"):
                    return {"summary": "Test."}
                if chapter_id.endswith("_p1"):
                    return []
                if chapter_id.endswith("_p2"):
                    id_lines = json.loads(user)
                    # Return a {"segments": [...]} envelope — previously rejected
                    return {
                        "segments": [
                            {"id": entry["id"], "type": "dialogue", "speaker": "Alice"}
                            for entry in id_lines
                        ]
                    }
                return []

        service = DialogueSegmentationService(client=_EnvelopeClient())
        result = service.parse(text='"Hello."\n"Bye."', chapter_id="ch-envelope")

        # With the fix the envelope is unwrapped and types/speakers come through
        assert result.diagnostics.validation_passed
        assert all(s.type == "dialogue" for s in result.segments)
        assert all(s.speaker == "Alice" for s in result.segments)
