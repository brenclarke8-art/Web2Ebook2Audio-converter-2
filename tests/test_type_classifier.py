from __future__ import annotations

from ebook_app.text.identify.type_classifier import Pass2Classifier


class MockEmptyLLMClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.on_conversation = None

    def generate_json(self, *, system: str, user: str):
        self.calls.append((system, user))
        return {}

class MockStaticLLMClient:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.on_conversation = None

    def generate_json(self, *, system: str, user: str):
        return self.payload


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


def test_pass2_classifier_remaps_shifted_single_id():
    client = MockStaticLLMClient(
        [{"id": "ch3_82", "type": "dialogue", "speaker": "Roman", "gender": "male"}]
    )
    classifier = Pass2Classifier(client, batch_size=4)
    segments = [
        {
            "text": "'My husband is so cool...'",
            "paragraph_id": "ch3_80",
            "context_before": "",
            "context_after": "",
            "is_dialogue_candidate": True,
        }
    ]

    output = classifier.classify_segments(segments, chapter_id="ch3")

    assert output[0]["type"] == "dialogue"
    assert output[0]["speaker"] == "Roman"


def test_pass2_classifier_uses_partial_match_and_falls_back_for_missing():
    client = MockStaticLLMClient(
        {"id": "ch3_100", "type": "dialogue", "speaker": "Roman", "gender": "male"}
    )
    classifier = Pass2Classifier(client, batch_size=8)
    segments = [
        {"text": "Before leaving...", "paragraph_id": "ch3_100", "context_before": "", "context_after": ""},
        {"text": "'I guess I passed...'", "paragraph_id": "ch3_101", "context_before": "", "context_after": ""},
    ]

    output = classifier.classify_segments(segments, chapter_id="ch3")

    assert output[0]["type"] == "dialogue"
    assert output[0]["speaker"] == "Roman"
    assert output[1]["type"] == "narration"
    assert output[1]["speaker"] == "narrator"
