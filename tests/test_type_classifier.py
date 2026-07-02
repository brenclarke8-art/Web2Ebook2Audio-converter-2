from __future__ import annotations

from ebook_app.text.identify.type_classifier import Pass2Classifier


class MockEmptyLLMClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.on_conversation = None

    def generate_json(self, *, system: str, user: str):
        self.calls.append((system, user))
        return {}


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
