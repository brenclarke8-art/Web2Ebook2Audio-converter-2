from __future__ import annotations

import json

from ebook_app.models.dialogue_parser import DialogueParser


class _DummyResponse:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


def test_dialogue_parser_validates_llm_json_contract(monkeypatch):
    parser = DialogueParser(ollama_url="http://example", model="mistral")
    llm_payload = {
        "segments": [
            {
                "text": "“Hello there.”",
                "type": "dialogue",
                "speaker": "Alice",
                "gender": "female",
                "speaker_confidence": 0.95,
                "gender_confidence": 0.8,
                "character_confidence": 0.9,
            }
        ],
        "detected_characters": [{"name": "Alice", "gender": "female", "confidence": 0.94}],
    }

    def _fake_post(*_args, **_kwargs):
        return _DummyResponse({"response": json.dumps(llm_payload)})

    monkeypatch.setattr("ebook_app.models.dialogue_parser.requests.post", _fake_post)
    result = parser.parse("Alice smiled.", chapter_id="ch001")

    assert len(result.segments) == 1
    assert result.segments[0].type == "dialogue"
    assert result.segments[0].speaker == "Alice"
    assert result.segments[0].gender == "female"
    assert result.detected_characters[0].name == "Alice"


def test_dialogue_parser_falls_back_on_invalid_output(monkeypatch):
    parser = DialogueParser(ollama_url="http://example", model="mistral")

    def _fake_post(*_args, **_kwargs):
        return _DummyResponse({"response": "not-json"})

    monkeypatch.setattr("ebook_app.models.dialogue_parser.requests.post", _fake_post)
    result = parser.parse("Fallback content.", chapter_id="ch002")

    assert len(result.segments) == 1
    assert result.segments[0].type == "narration"
    assert result.segments[0].speaker == "narrator"
