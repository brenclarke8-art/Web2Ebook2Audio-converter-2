from __future__ import annotations

import json

from ebook_app.models.dialogue_parser import DialogueParser


class _DummyResponse:
    def __init__(self, body: dict):
        self._body = body
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


def test_dialogue_parser_validates_llm_json_contract(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/chat", model="mistral:instruct")
    llm_payload = {
        "characters": ["Alice"],
        "segments": [
            {
                "text": "\"Hello there.\"",
                "type": "dialogue",
                "speaker": "Alice",
            }
        ],
    }

    def _fake_post(*_args, **_kwargs):
        return _DummyResponse({"message": {"content": json.dumps(llm_payload)}})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    result = parser.parse("Alice smiled.", chapter_id="ch001")

    assert len(result.segments) == 1
    assert result.segments[0].type == "dialogue"
    assert result.segments[0].speaker == "Alice"
    assert result.detected_characters[0].name == "Alice"


def test_dialogue_parser_cleans_ui_noise_before_prompt(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/chat", model="mistral:instruct")
    captured_payload: dict = {}

    def _fake_post(*_args, **kwargs):
        captured_payload.update(kwargs.get("json", {}))
        return _DummyResponse({"message": {"content": json.dumps({"segments": [], "characters": []})}})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    parser.parse(
        "Next Chapter\nSubscribe now\nActual story line.\nAnother story paragraph.",
        chapter_id="ch-clean",
    )

    user_msg = captured_payload.get("messages", [{}, {"content": "{}"}])[1].get("content", "{}")
    user_payload = json.loads(user_msg)
    cleaned_text = user_payload["text"]
    assert "Next Chapter" not in cleaned_text
    assert "Subscribe now" not in cleaned_text
    assert "Actual story line." in cleaned_text


def test_dialogue_parser_writes_llm_communication_log(monkeypatch, tmp_path):
    log_file = tmp_path / "llm_communication.jsonl"
    parser = DialogueParser(
        ollama_url="http://example/api/chat",
        model="mistral:instruct",
        llm_log_path=str(log_file),
    )

    def _fake_post(*_args, **_kwargs):
        return _DummyResponse({"message": {"content": json.dumps({"segments": [], "characters": []})}})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    parser.parse("Story text only.", chapter_id="ch-log")

    lines = [line for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 1
    records = [json.loads(line) for line in lines]
    assert records[0].get("request")
    assert "response_raw" in records[0] or "error" in records[0]


def test_dialogue_parser_falls_back_on_invalid_output(monkeypatch):
    parser = DialogueParser(ollama_url="http://example/api/chat", model="mistral:instruct")

    def _fake_post(*_args, **_kwargs):
        return _DummyResponse({"message": {"content": "not-json"}})

    monkeypatch.setattr("ebook_app.services.llm_client.requests.post", _fake_post)
    result = parser.parse("Fallback content.", chapter_id="ch002")

    assert len(result.segments) == 1
    assert result.segments[0].type == "narration"
    assert result.segments[0].speaker == "narrator"


def test_dialogue_parser_migrates_generate_endpoint_to_chat():
    parser = DialogueParser(ollama_url="http://127.0.0.1:11434/api/generate", model="mistral")
    assert parser.ollama_url == "http://127.0.0.1:11434/api/chat"


def test_dialogue_parser_keeps_chat_endpoint_unchanged():
    parser = DialogueParser(ollama_url="http://127.0.0.1:11434/api/chat", model="mistral")
    assert parser.ollama_url == "http://127.0.0.1:11434/api/chat"


def test_dialogue_parser_keeps_custom_endpoint_unchanged():
    parser = DialogueParser(ollama_url="http://example.local/custom-endpoint", model="mistral")
    assert parser.ollama_url == "http://example.local/custom-endpoint"
