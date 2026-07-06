from __future__ import annotations

import json

from ebook_app.text.identify.type_classifier import Pass2Classifier


class MockEmptyLLMClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.on_conversation = None

    def generate_json(self, *, system: str, user: str):
        self.calls.append((system, user))
        return {}


class MockSingleItemLLMClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.on_conversation = None

    def generate_json(self, *, system: str, user: str):
        self.calls.append((system, user))
        return {
            "id": "ch1_0",
            "type": "dialogue",
            "speaker": "Alice",
            "gender": "female",
            "speaker_confidence": 0.9,
            "gender_confidence": 0.8,
            "character_confidence": 0.85,
        }


def test_pass2_classifier_keeps_batch_whole_when_llm_response_is_empty():
    client = MockEmptyLLMClient()
    classifier = Pass2Classifier(client, batch_size=8)
    segments = [
        {
            "text": f"line {idx}",
            "paragraph_id": f"ch1_p{idx:03d}",
            "context_before": "",
            "context_after": "",
            "is_dialogue_candidate": False,
        }
        for idx in range(5)
    ]

    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(client.calls) == 1
    assert len(output) == 5
    assert all(segment["type"] == "narration" for segment in output)


def test_pass2_classifier_accepts_single_object_llm_response():
    client = MockSingleItemLLMClient()
    classifier = Pass2Classifier(client, batch_size=8)
    segments = [
        {
            "text": f"line {idx}",
            "paragraph_id": f"ch1_p{idx:03d}",
            "context_before": "",
            "context_after": "",
            "is_dialogue_candidate": False,
        }
        for idx in range(3)
    ]

    output = classifier.classify_segments(segments, chapter_id="ch1")

    assert len(client.calls) == 1
    _, user_payload = client.calls[0]
    sent_entries = json.loads(user_payload)
    assert sent_entries[0]["id"] == "ch1_0"
    assert len(output) == 3
    assert output[0]["type"] == "dialogue"
    assert output[0]["speaker"] == "Alice"
    assert output[1]["type"] == "narration"
    assert output[2]["type"] == "narration"
