from __future__ import annotations

import json

from ebook_app.text.identify.type_classifier import Pass2Classifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_segments(n: int, chapter_id: str = "ch1") -> list[dict]:
    return [
        {
            "text": f"line {i}",
            "paragraph_id": f"{chapter_id}_p{i:03d}",
            "context_before": "",
            "context_after": "",
            "is_dialogue_candidate": False,
        }
        for i in range(n)
    ]


def _valid_item(entry_id: str, seg_type: str = "narration") -> dict:
    return {
        "id": entry_id,
        "type": seg_type,
        "speaker": "narrator",
        "gender": "unknown",
        "speaker_confidence": 0.9,
        "gender_confidence": 0.5,
        "character_confidence": 0.8,
    }


class _FixedLLMClient:
    """Returns the same pre-built response every call."""

    def __init__(self, response) -> None:
        self._response = response
        self.calls: list[tuple[str, str]] = []
        self.on_conversation = None

    def generate_json(self, *, system: str, user: str):
        self.calls.append((system, user))
        return self._response


class _SequenceLLMClient:
    """Returns queued responses in order, then repeats the last one."""

    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        self.on_conversation = None

    def generate_json(self, *, system: str, user: str):
        self.calls.append((system, user))
        if not self._responses:
            return {}
        if len(self._responses) == 1:
            return self._responses[0]
        return self._responses.pop(0)


class MockEmptyLLMClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.on_conversation = None

    def generate_json(self, *, system: str, user: str):
        self.calls.append((system, user))
        return {}


# ---------------------------------------------------------------------------
# Existing regression test (updated for retry ladder)
# ---------------------------------------------------------------------------

def test_pass2_classifier_keeps_batch_whole_when_llm_response_is_empty():
    """On LLM failure the batch must NOT be split; retries use the same input."""
    client = MockEmptyLLMClient()
    classifier = Pass2Classifier(client, batch_size=8, json_pipeline_enabled=False)
    segments = _make_segments(5)

    output = classifier.classify_segments(segments, chapter_id="ch1")

    # Each retry attempt sends the SAME user payload (batch not split).
    expected_calls = Pass2Classifier.MAX_BATCH_RETRIES + 1
    assert len(client.calls) == expected_calls
    # All retry calls must have the same user payload (same batch, not shrunk).
    user_payloads = [call[1] for call in client.calls]
    assert all(p == user_payloads[0] for p in user_payloads), "batch must not be split on retries"
    # Output still has one entry per input segment with fallback defaults.
    assert len(output) == 5
    assert all(segment["type"] == "narration" for segment in output)


# ---------------------------------------------------------------------------
# New contract-driven tests
# ---------------------------------------------------------------------------

def test_valid_full_array_response_passes_through():
    """A fully valid array response is accepted on the first attempt."""
    segments = _make_segments(3)
    expected_ids = [f"ch1_{i}" for i in range(3)]
    valid_response = [_valid_item(eid) for eid in expected_ids]

    client = _FixedLLMClient(valid_response)
    classifier = Pass2Classifier(client, batch_size=10)
    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(client.calls) == 1, "valid response should not trigger retries"
    assert len(output) == 3
    assert all(seg["type"] == "narration" for seg in output)


def test_single_object_response_is_rejected_and_falls_back():
    """A single dict (not an array) must be rejected and trigger retries + fallback."""
    segments = _make_segments(2)
    single_object = _valid_item("ch1_0")  # dict, not list

    client = _FixedLLMClient(single_object)
    classifier = Pass2Classifier(client, batch_size=10, json_pipeline_enabled=False)
    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(client.calls) == Pass2Classifier.MAX_BATCH_RETRIES + 1
    assert len(output) == 2
    # All fall back to narration defaults
    assert all(seg["type"] == "narration" for seg in output)


def test_wrapper_object_response_is_rejected():
    """A wrapper dict like {'results': [...]} must be rejected (not unwrapped)."""
    segments = _make_segments(2)
    expected_ids = [f"ch1_{i}" for i in range(2)]
    wrapper = {"results": [_valid_item(eid) for eid in expected_ids]}

    client = _FixedLLMClient(wrapper)
    classifier = Pass2Classifier(client, batch_size=10, json_pipeline_enabled=False)
    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(client.calls) == Pass2Classifier.MAX_BATCH_RETRIES + 1
    # Falls back to defaults
    assert all(seg["type"] == "narration" for seg in output)


def test_missing_id_in_response_is_rejected():
    """Response missing one id must fail validation and trigger retries."""
    segments = _make_segments(3)
    # Only return 2 of the 3 expected ids
    partial = [_valid_item("ch1_0"), _valid_item("ch1_1")]

    client = _FixedLLMClient(partial)
    classifier = Pass2Classifier(client, batch_size=10, json_pipeline_enabled=False)
    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(client.calls) == Pass2Classifier.MAX_BATCH_RETRIES + 1
    assert len(output) == 3


def test_duplicate_id_in_response_is_rejected():
    """Response with a duplicate id must fail validation."""
    segments = _make_segments(2)
    duplicate = [_valid_item("ch1_0"), _valid_item("ch1_0")]  # ch1_1 missing, ch1_0 duped

    client = _FixedLLMClient(duplicate)
    classifier = Pass2Classifier(client, batch_size=10, json_pipeline_enabled=False)
    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(client.calls) == Pass2Classifier.MAX_BATCH_RETRIES + 1
    assert len(output) == 2


def test_invalid_confidence_range_is_rejected():
    """Confidence value > 1.0 must fail validation."""
    segments = _make_segments(1)
    bad_confidence = _valid_item("ch1_0")
    bad_confidence["speaker_confidence"] = 1.5  # out of range

    client = _FixedLLMClient([bad_confidence])
    classifier = Pass2Classifier(client, batch_size=10, json_pipeline_enabled=False)
    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(client.calls) == Pass2Classifier.MAX_BATCH_RETRIES + 1
    assert output[0]["type"] == "narration"  # fallback
    assert output[0]["llm_status"] == "FAILED_FORMAT"


def test_malformed_json_is_repaired_deterministically():
    segments = _make_segments(1)
    malformed = (
        '```json\n[{"id":"ch1_0","type":"narration","speaker":"narrator","gender":"unknown",'
        '"speaker_confidence":0.9,"gender_confidence":0.8,"character_confidence":0.7,}]\n```'
    )
    client = _FixedLLMClient(malformed)
    classifier = Pass2Classifier(client, batch_size=10)

    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(client.calls) == 1
    assert output[0]["type"] == "narration"
    assert output[0]["llm_status"] == "OK"


def test_model_repair_fallback_is_invoked_when_deterministic_repair_fails():
    segments = _make_segments(1)
    repaired = [_valid_item("ch1_0", "dialogue")]
    client = _SequenceLLMClient(["NOT JSON", repaired])
    classifier = Pass2Classifier(client, batch_size=10, json_repair_max_retries=1)

    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(client.calls) == 2
    assert "JSON repair assistant" in client.calls[1][0]
    assert output[0]["type"] == "dialogue"
    assert output[0]["llm_status"] == "OK"


def test_switches_to_single_segment_mode_after_failure_threshold(monkeypatch):
    monkeypatch.setattr(Pass2Classifier, "MAX_BATCH_RETRIES", 0)
    segments = _make_segments(5)
    client = _SequenceLLMClient([{}])
    classifier = Pass2Classifier(
        client,
        batch_size=2,
        json_repair_max_retries=0,
        fallback_failure_threshold=1,
        segment_mode="batch",
    )

    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(output) == 5
    assert all(item["llm_status"] == "FAILED_FORMAT" for item in output)
    assert all(isinstance(call[1], str) and call[1].strip().startswith("[") for call in client.calls)
    payload_sizes = [len(json.loads(call[1])) for call in client.calls]
    assert payload_sizes == [2, 1, 1, 1]


def test_validate_batch_response_accepts_valid_input():
    """_validate_batch_response returns (items, None) for a conforming response."""
    items = [_valid_item("x_0"), _valid_item("x_1", "dialogue")]
    result, error = Pass2Classifier._validate_batch_response(items, ["x_0", "x_1"])
    assert error is None
    assert result == items


def test_validate_batch_response_rejects_non_array():
    _, error = Pass2Classifier._validate_batch_response({"id": "x_0"}, ["x_0"])
    assert error is not None
    assert "array" in error.lower()


def test_validate_batch_response_rejects_missing_keys():
    item = {"id": "x_0", "type": "narration"}  # missing required keys
    _, error = Pass2Classifier._validate_batch_response([item], ["x_0"])
    assert error is not None
    assert "missing" in error.lower()
    # The error should mention at least some of the missing required keys
    for expected_missing in ("speaker", "gender", "speaker_confidence"):
        assert expected_missing in error, f"Expected '{expected_missing}' in error: {error}"


def test_validate_batch_response_rejects_invalid_type_enum():
    item = _valid_item("x_0")
    item["type"] = "monologue"  # not in enum
    _, error = Pass2Classifier._validate_batch_response([item], ["x_0"])
    assert error is not None
    assert "invalid type" in error.lower()


def test_validate_batch_response_rejects_confidence_out_of_range():
    item = _valid_item("x_0")
    item["gender_confidence"] = -0.1
    _, error = Pass2Classifier._validate_batch_response([item], ["x_0"])
    assert error is not None
    assert "out of range" in error.lower()


def test_validate_batch_response_rejects_extra_ids():
    items = [_valid_item("x_0"), _valid_item("x_99")]  # x_99 not expected
    _, error = Pass2Classifier._validate_batch_response(items, ["x_0"])
    assert error is not None
    assert "mismatch" in error.lower()
